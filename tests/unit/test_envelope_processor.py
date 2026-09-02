"""El camino completo de la ingesta, con dobles en lugar de infraestructura.

Estos son los tests que demuestran el aislamiento entre tenants sin
necesidad de levantar docker.
"""
from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from ferrogate.assets.domain.asset import Asset
from ferrogate.assets.domain.tag_definition import TagDefinition
from ferrogate.assets.domain.value_objects import (
    DataType,
    EngineeringRange,
    ModbusAddress,
    Unit,
)
from ferrogate.ingestion.application.ingest_telemetry import IngestTelemetry
from ferrogate.ingestion.infrastructure.mqtt_ingest import EnvelopeProcessor
from ferrogate.shared.domain.clock import FrozenClock
from ferrogate.shared.domain.identifiers import AssetId, TagId, TenantId
from ferrogate.shared.security.envelope import Envelope, Sample, sign

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
ACME_ASSET = AssetId(__import__("uuid").UUID("11111111-1111-1111-1111-111111111111"))


def keypair(urn):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "gw")])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(NOW - timedelta(days=1))
            .not_valid_after(NOW + timedelta(days=365))
            .add_extension(x509.SubjectAlternativeName(
                [x509.UniformResourceIdentifier(urn)]), critical=False)
            .sign(key, hashes.SHA256()))
    return (key.private_bytes(serialization.Encoding.PEM,
                              serialization.PrivateFormat.PKCS8,
                              serialization.NoEncryption()),
            cert.public_bytes(serialization.Encoding.PEM))


def build_asset(tenant):
    asset = Asset(id=ACME_ASSET, tenant_id=TenantId(tenant), name="contador-1")
    asset.add_tag(TagDefinition(
        id=TagId.new(), name="voltage_l1", data_type=DataType.FLOAT32,
        unit=Unit.VOLT, engineering_range=EngineeringRange(180.0, 280.0),
        modbus_address=ModbusAddress(unit_id=1, register=0)))
    return asset


class FakeAssets:
    def __init__(self, asset): self._asset = asset
    def get(self, tenant_id, asset_id):
        return self._asset if self._asset.tenant_id == tenant_id else None
    def list_for_tenant(self, tenant_id): return []


class FakeSink:
    def __init__(self): self.written = []
    def write(self, tenant_id, measurements):
        self.written.append((str(tenant_id), list(measurements)))


class FakeAudit:
    def __init__(self): self.events = []
    def record(self, tenant_id, event, detail):
        self.events.append((str(tenant_id), event))


class FakeSecurity:
    """Registra lo RECLAMADO, no lo probado."""
    def __init__(self): self.events = []
    def reject(self, claimed_tenant, claimed_gateway, event, detail):
        self.events.append((claimed_tenant, event))


class FakeRegistry:
    def __init__(self, certs): self._certs, self.sequences = certs, {}
    def certificate_pem(self, tenant_id, gateway_id):
        return self._certs.get((str(tenant_id), str(gateway_id)))
    def last_sequence(self, tenant_id, gateway_id):
        return self.sequences.get((str(tenant_id), str(gateway_id)))
    def record_sequence(self, tenant_id, gateway_id, sequence):
        self.sequences[(str(tenant_id), str(gateway_id))] = sequence


def build(certs, tenant="acme"):
    sink, audit, security = FakeSink(), FakeAudit(), FakeSecurity()
    clock = FrozenClock(NOW)
    processor = EnvelopeProcessor(
        registry=FakeRegistry(certs),
        ingest=IngestTelemetry(FakeAssets(build_asset(tenant)), sink, audit, clock),
        security=security, clock=clock)
    return processor, sink, security


def envelope(urn, value=232.0, sequence=1):
    return Envelope(identity=urn, sequence=sequence, sent_at=NOW.isoformat(),
                    samples=[Sample(str(ACME_ASSET), "voltage_l1", value,
                                    NOW.isoformat())])


ACME_URN = "urn:ferrogate:tenant:acme:gateway:planta-norte"
GLOBEX_URN = "urn:ferrogate:tenant:globex:gateway:planta-sur"


def test_camino_feliz_escribe_la_medida():
    priv, cert = keypair(ACME_URN)
    proc, sink, _ = build({("acme", "planta-norte"): cert})
    proc.process("ferrogate/acme/planta-norte/telemetry/data",
                 sign(envelope(ACME_URN), priv))
    assert len(sink.written) == 1
    tenant, measurements = sink.written[0]
    assert tenant == "acme" and measurements[0].value == 232.0


def test_globex_no_puede_escribir_como_acme():
    """El ataque principal: firmar con clave propia declarando otro tenant."""
    priv_globex, cert_globex = keypair(GLOBEX_URN)
    _, cert_acme = keypair(ACME_URN)
    proc, sink, audit = build({("acme", "planta-norte"): cert_acme,
                               ("globex", "planta-sur"): cert_globex})
    proc.process("ferrogate/acme/planta-norte/telemetry/data",
                 sign(envelope(ACME_URN), priv_globex))
    assert sink.written == []
    assert any("rejected" in e for _, e in audit.events)


def test_gateway_revocado_es_rechazado():
    priv, _ = keypair(ACME_URN)
    proc, sink, audit = build({})  # sin certificado enrolado = revocado
    proc.process("ferrogate/acme/planta-norte/telemetry/data",
                 sign(envelope(ACME_URN), priv))
    assert sink.written == []
    assert any("revoked" in e for _, e in audit.events)


def test_publicar_en_el_topic_de_otro_es_rechazado():
    priv, cert = keypair(ACME_URN)
    proc, sink, _ = build({("acme", "planta-norte"): cert})
    proc.process("ferrogate/globex/planta-sur/telemetry/data",
                 sign(envelope(ACME_URN), priv))
    assert sink.written == []


def test_reenvio_del_mismo_sobre_solo_entra_una_vez():
    priv, cert = keypair(ACME_URN)
    proc, sink, _ = build({("acme", "planta-norte"): cert})
    raw = sign(envelope(ACME_URN, sequence=7), priv)
    proc.process("ferrogate/acme/planta-norte/telemetry/data", raw)
    proc.process("ferrogate/acme/planta-norte/telemetry/data", raw)
    assert len(sink.written) == 1


def test_valor_fuera_de_rango_se_marca_bad_pero_se_guarda():
    priv, cert = keypair(ACME_URN)
    proc, sink, _ = build({("acme", "planta-norte"): cert})
    proc.process("ferrogate/acme/planta-norte/telemetry/data",
                 sign(envelope(ACME_URN, value=9999.0), priv))
    _, measurements = sink.written[0]
    assert measurements[0].quality.value == "bad"
    assert measurements[0].reason.value == "out_of_range"


def test_un_tenant_inexistente_no_tumba_la_ingesta():
    """El rechazo de un gateway desconocido NO puede lanzar excepcion.

    Auditar bajo el tenant reclamado violaba la clave foranea cuando ese
    tenant no existe, y la excepcion se escapaba del procesador. Un
    atacante podia provocar un error por mensaje con una URN inventada.
    """
    priv, _ = keypair("urn:ferrogate:tenant:inventado:gateway:falso")
    proc, sink, security = build({})
    proc.process("ferrogate/inventado/falso/telemetry/data",
                 sign(envelope("urn:ferrogate:tenant:inventado:gateway:falso"), priv))
    assert sink.written == []
    assert ("inventado", "ingest.unknown_or_revoked_gateway") in security.events


def test_un_sobre_basura_se_registra_sin_identidad():
    proc, sink, security = build({})
    proc.process("ferrogate/x/y/telemetry/data", b"{}")
    assert sink.written == []
    assert (None, "ingest.unreadable_identity") in security.events


class AssetsDeOtroTenant:
    """Devuelve un activo que NO pertenece a quien lo pide.

    El FakeAssets normal ya filtra por tenant, asi que nunca llega a la
    comprobacion de pertenencia dentro del caso de uso. Este doble existe
    para ejercitar esa ultima linea de defensa.
    """

    def __init__(self, asset):
        self._asset = asset

    def get(self, tenant_id, asset_id):
        return self._asset

    def list_for_tenant(self, tenant_id):
        return []


def build_con_auditoria(certs, assets=None, tenant="acme"):
    sink, audit, security = FakeSink(), FakeAudit(), FakeSecurity()
    clock = FrozenClock(NOW)
    repo = assets if assets is not None else FakeAssets(build_asset(tenant))
    processor = EnvelopeProcessor(
        registry=FakeRegistry(certs),
        ingest=IngestTelemetry(repo, sink, audit, clock),
        security=security, clock=clock)
    return processor, sink, audit, security


def test_un_tag_desconocido_no_descarta_las_muestras_validas():
    """Un tag sin definir es lo normal durante una puesta en marcha.

    Antes tiraba el sobre ENTERO por una excepcion de dominio que nadie
    capturaba: las muestras validas del mismo envio se perdian y no
    quedaba rastro auditable de por que.
    """
    priv, cert = keypair(ACME_URN)
    proc, sink, audit, _ = build_con_auditoria({("acme", "planta-norte"): cert})
    env = Envelope(
        identity=ACME_URN, sequence=1, sent_at=NOW.isoformat(),
        samples=[
            Sample(str(ACME_ASSET), "tag_que_no_existe", 1.0, NOW.isoformat()),
            Sample(str(ACME_ASSET), "voltage_l1", 232.0, NOW.isoformat()),
        ])
    proc.process("ferrogate/acme/planta-norte/telemetry/data", sign(env, priv))

    assert len(sink.written) == 1
    _, measurements = sink.written[0]
    assert [m.tag_name for m in measurements] == ["voltage_l1"]
    assert ("acme", "ingest.unknown_tag") in audit.events


def test_activo_de_otro_tenant_queda_registrado_como_rechazo():
    """TenantIsolationViolation es HERMANA de SecurityViolation, no hija.

    Por eso se escapaba del except del procesador y acababa como un
    stacktrace en el catch-all del bucle, sin registro de seguridad.
    """
    priv, cert = keypair(ACME_URN)
    proc, sink, _, security = build_con_auditoria(
        {("acme", "planta-norte"): cert},
        assets=AssetsDeOtroTenant(build_asset("globex")))
    proc.process("ferrogate/acme/planta-norte/telemetry/data",
                 sign(envelope(ACME_URN), priv))

    assert sink.written == []
    assert ("acme", "ingest.rejected_by_domain") in security.events
