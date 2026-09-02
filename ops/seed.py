#!/usr/bin/env python3
"""Enrolamiento inicial: tenants, gateways, activos y tags.

Lee los certificados de ops/pki/out y los enrola en Postgres. Sin esto la
ingesta rechaza todo por "gateway desconocido", que es el comportamiento
correcto: un gateway no enrolado no puede escribir.

Idempotente: se puede ejecutar varias veces.

IMPORTANTE: las tablas llevan RLS con FORCE, asi que cada INSERT se hace
dentro de su tenant_scope. Si intentas insertar sin fijar la variable de
sesion, la politica WITH CHECK rechaza la fila. Eso es la prueba de que
el aislamiento esta activo, no un estorbo.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.x509 import load_pem_x509_certificate
from sqlalchemy import create_engine, text

# Dentro del contenedor la PKI llega por el montaje /certs del servicio;
# desde el host, por la ruta del repo. Nunca una ruta absoluta como
# argumento: Git Bash las convierte a rutas de Windows y rompe el comando.
PKI = Path(os.getenv("PKI_DIR", str(Path(__file__).resolve().parent / "pki" / "out")))

# El asset_id debe coincidir con el de edge/ferrogate_edge/config/*.yaml
SITES = [
    {
        "tenant": "acme",
        "name": "ACME Manufacturing",
        "gateway": "planta-norte",
        "site": "Planta Norte",
        "asset_id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
        "asset_name": "Contador general - Linea 1",
    },
    {
        "tenant": "globex",
        "name": "Globex Industrial",
        "gateway": "planta-sur",
        "site": "Planta Sur",
        "asset_id": uuid.UUID("22222222-2222-2222-2222-222222222222"),
        "asset_name": "Contador general - Linea 1",
    },
]

# (nombre, unidad, registro Modbus, rango bajo, rango alto)
# Los rangos NO son decorativos: son lo que produce calidad BAD cuando el
# simulador inyecta un valor fuera de rango.
TAGS = [
    ("voltage_l1", "V", 0, 180.0, 280.0),
    ("voltage_l2", "V", 2, 180.0, 280.0),
    ("voltage_l3", "V", 4, 180.0, 280.0),
    ("current_l1", "A", 6, 0.0, 100.0),
    ("total_power", "W", 52, 0.0, 60000.0),
    ("frequency", "Hz", 70, 45.0, 55.0),
]


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("falta DATABASE_URL", file=sys.stderr)
        return 1
    if not PKI.exists():
        print(f"no existe {PKI}: ejecuta 'make pki' primero", file=sys.stderr)
        return 1

    engine = create_engine(url)

    with engine.connect() as conn:
        for site in SITES:
            tenant = site["tenant"]
            cert_path = PKI / f"{tenant}.{site['gateway']}.crt"
            if not cert_path.exists():
                print(f"falta {cert_path.name}", file=sys.stderr)
                return 1

            cert_pem = cert_path.read_bytes()
            certificate = load_pem_x509_certificate(cert_pem)
            fingerprint = certificate.fingerprint(hashes.SHA256()).hex()

            with conn.begin():
                # La tabla tenants no lleva RLS: es el catalogo raiz.
                conn.execute(
                    text("INSERT INTO tenants (id, name) VALUES (:id, :name) "
                         "ON CONFLICT (id) DO NOTHING"),
                    {"id": tenant, "name": site["name"]},
                )
                # A partir de aqui, todo dentro del scope del tenant.
                conn.execute(
                    text("SELECT set_config('ferrogate.tenant_id', :tid, TRUE)"),
                    {"tid": tenant},
                )
                conn.execute(
                    text("""
                        INSERT INTO gateways
                            (id, tenant_id, site, cert_serial, cert_sha256, cert_pem)
                        VALUES (:gid, :tid, :site, :serial, :fp, :pem)
                        ON CONFLICT (tenant_id, id) DO UPDATE
                            SET cert_pem = EXCLUDED.cert_pem,
                                cert_sha256 = EXCLUDED.cert_sha256,
                                cert_serial = EXCLUDED.cert_serial,
                                revoked_at = NULL
                    """),
                    {
                        "gid": site["gateway"], "tid": tenant, "site": site["site"],
                        "serial": str(certificate.serial_number),
                        "fp": fingerprint, "pem": cert_pem.decode(),
                    },
                )
                conn.execute(
                    text("INSERT INTO assets (id, tenant_id, name) "
                         "VALUES (:id, :tid, :name) "
                         "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name"),
                    {"id": site["asset_id"], "tid": tenant,
                     "name": site["asset_name"]},
                )
                for name, unit, register, low, high in TAGS:
                    conn.execute(
                        text("""
                            INSERT INTO tags
                                (id, tenant_id, asset_id, name, data_type, unit,
                                 range_low, range_high, modbus_unit, modbus_reg)
                            VALUES (:id, :tid, :aid, :name, 'float32', :unit,
                                    :low, :high, 1, :reg)
                            ON CONFLICT (tenant_id, asset_id, name) DO NOTHING
                        """),
                        {
                            "id": uuid.uuid4(), "tid": tenant,
                            "aid": site["asset_id"], "name": name, "unit": unit,
                            "low": low, "high": high, "reg": register,
                        },
                    )

            print(f"  {tenant}/{site['gateway']}: enrolado "
                  f"({len(TAGS)} tags, huella {fingerprint[:16]}...)")

    # Verificacion explicita: el enrolamiento a medias es la causa numero
    # uno de "todo corre pero no llegan datos".
    with engine.connect() as conn:
        problems = []
        for site in SITES:
            tenant = site["tenant"]
            with conn.begin():
                if not conn.execute(
                    text("SELECT 1 FROM tenants WHERE id = :t"), {"t": tenant}
                ).fetchone():
                    problems.append(f"tenant {tenant} no quedo insertado")
                    continue
                conn.execute(
                    text("SELECT set_config('ferrogate.tenant_id', :t, TRUE)"),
                    {"t": tenant},
                )
                gw = conn.execute(
                    text("SELECT cert_pem FROM gateways WHERE tenant_id = :t "
                         "AND id = :g AND revoked_at IS NULL"),
                    {"t": tenant, "g": site["gateway"]},
                ).fetchone()
                if not gw or not gw.cert_pem.strip():
                    problems.append(f"gateway {tenant}/{site['gateway']} sin certificado")
                n = conn.execute(
                    text("SELECT count(*) AS n FROM tags WHERE tenant_id = :t"),
                    {"t": tenant},
                ).fetchone().n
                if n != len(TAGS):
                    problems.append(f"{tenant}: {n} tags, se esperaban {len(TAGS)}")

    if problems:
        print("\nENROLAMIENTO INCOMPLETO:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    print("\nEnrolamiento completo y verificado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
