from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ferrogate.shared.domain.identifiers import GatewayId, TenantId
from ferrogate.shared.infrastructure.persistence.tenant_session import tenant_scope


class PostgresGatewayRegistry:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def certificate_pem(
        self, tenant_id: TenantId, gateway_id: GatewayId
    ) -> bytes | None:
        with self._engine.connect() as conn, tenant_scope(conn, tenant_id) as scoped:
            row = scoped.execute(
                text("SELECT cert_pem FROM gateways WHERE tenant_id = :tid "
                     "AND id = :gid AND revoked_at IS NULL"),
                {"tid": str(tenant_id), "gid": str(gateway_id)},
            ).fetchone()
        # Un gateway revocado devuelve None y la ingesta rechaza el sobre.
        return row.cert_pem.encode() if row else None

    def last_sequence(
        self, tenant_id: TenantId, gateway_id: GatewayId
    ) -> int | None:
        with self._engine.connect() as conn, tenant_scope(conn, tenant_id) as scoped:
            row = scoped.execute(
                text("SELECT last_sequence FROM gateways "
                     "WHERE tenant_id = :tid AND id = :gid"),
                {"tid": str(tenant_id), "gid": str(gateway_id)},
            ).fetchone()
        return row.last_sequence if row else None

    def record_sequence(
        self, tenant_id: TenantId, gateway_id: GatewayId, sequence: int
    ) -> None:
        with self._engine.connect() as conn, tenant_scope(conn, tenant_id) as scoped:
            scoped.execute(
                text("UPDATE gateways SET last_sequence = :seq "
                     "WHERE tenant_id = :tid AND id = :gid"),
                {"seq": sequence, "tid": str(tenant_id), "gid": str(gateway_id)},
            )
