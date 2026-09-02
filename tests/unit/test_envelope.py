import json
from datetime import UTC, datetime, timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from ferrogate.shared.errors import SecurityViolation
from ferrogate.shared.security.envelope import Envelope, Sample, sign, verify

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
URN = "urn:ferrogate:tenant:acme:gateway:planta-norte"
OTHER_URN = "urn:ferrogate:tenant:globex:gateway:planta-sur"


def make_keypair(urn: str):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "gw")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(NOW - timedelta(days=1))
        .not_valid_after(NOW + timedelta(days=365))
        .add_extension(
            x509.SubjectAlternativeName([x509.UniformResourceIdentifier(urn)]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    return (
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
        cert.public_bytes(serialization.Encoding.PEM),
    )


def make_envelope(urn=URN, sequence=1, sent_at=None):
    return Envelope(
        identity=urn,
        sequence=sequence,
        sent_at=(sent_at or NOW).isoformat(),
        samples=[Sample("a1", "voltage_l1", 232.5, NOW.isoformat())],
    )


def test_un_sobre_valido_se_verifica():
    priv, cert = make_keypair(URN)
    raw = sign(make_envelope(), priv)
    identity, envelope = verify(raw, cert, now=NOW)
    assert str(identity.tenant_id) == "acme"
    assert envelope.samples[0].raw_value == 232.5


def test_manipular_un_valor_invalida_la_firma():
    priv, cert = make_keypair(URN)
    raw = sign(make_envelope(), priv)
    payload = json.loads(raw)
    payload["samples"][0]["raw_value"] = 999.0
    with pytest.raises(SecurityViolation, match="manipulado"):
        verify(json.dumps(payload).encode(), cert, now=NOW)


def test_no_se_puede_suplantar_a_otro_tenant():
    """Globex firma con su clave pero declara ser acme."""
    priv_globex, _ = make_keypair(OTHER_URN)
    _, cert_acme = make_keypair(URN)
    raw = sign(make_envelope(urn=URN), priv_globex)
    with pytest.raises(SecurityViolation):
        verify(raw, cert_acme, now=NOW)


def test_reenvio_rechazado_por_secuencia():
    priv, cert = make_keypair(URN)
    raw = sign(make_envelope(sequence=5), priv)
    verify(raw, cert, now=NOW, last_sequence=4)
    with pytest.raises(SecurityViolation, match="reenvio"):
        verify(raw, cert, now=NOW, last_sequence=5)


def test_sobre_viejo_rechazado():
    priv, cert = make_keypair(URN)
    raw = sign(make_envelope(sent_at=NOW - timedelta(hours=2)), priv)
    with pytest.raises(SecurityViolation, match="ventana temporal"):
        verify(raw, cert, now=NOW)


def test_payload_gigante_rechazado_antes_de_parsear():
    _, cert = make_keypair(URN)
    with pytest.raises(SecurityViolation, match="demasiado grande"):
        verify(b"x" * (300 * 1024), cert, now=NOW)


def test_basura_no_revienta():
    _, cert = make_keypair(URN)
    for junk in [b"", b"{", b"null", b'{"signature":"@@@"}', b"\xff\xfe"]:
        with pytest.raises(SecurityViolation):
            verify(junk, cert, now=NOW)
