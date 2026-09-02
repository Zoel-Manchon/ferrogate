"""Sobre firmado de telemetria.

El servicio de ingesta es un cliente MQTT: NO ve el certificado del gateway
que publico. Si se fiara del topic, toda la seguridad dependeria de que la
ACL de Mosquitto este bien configurada, y un broker mal reconfigurado
abriria el paso entre tenants sin que nada lo detecte.

Por eso cada envio va firmado con la clave privada del gateway, y la
ingesta lo verifica contra el certificado enrolado en Postgres. El broker
queda fuera de la base de confianza: puede reenviar, reordenar o mezclar
mensajes, pero no puede fabricar uno valido.

Contra reenvio (replay) hay dos controles: una ventana temporal sobre
sent_at y un numero de secuencia monotono por gateway.
"""
from __future__ import annotations

import base64
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509 import load_pem_x509_certificate

from ferrogate.shared.errors import SecurityViolation
from ferrogate.shared.security.gateway_identity import GatewayIdentity

MAX_ENVELOPE_BYTES = 256 * 1024
MAX_SAMPLES = 500
DEFAULT_MAX_AGE = timedelta(minutes=10)

_PSS = padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32)


@dataclass(frozen=True, slots=True)
class Sample:
    asset_id: str
    tag_name: str
    raw_value: float
    source_timestamp: str


@dataclass(frozen=True, slots=True)
class Envelope:
    identity: str
    sequence: int
    sent_at: str
    samples: list[Sample] = field(default_factory=list)

    def canonical_bytes(self) -> bytes:
        """Serializacion canonica: claves ordenadas y sin espacios.

        Si esto no es deterministico, la firma falla de forma intermitente
        y depurarlo es una pesadilla.
        """
        body: dict[str, Any] = {
            "identity": self.identity,
            "sequence": self.sequence,
            "sent_at": self.sent_at,
            "samples": [asdict(s) for s in self.samples],
        }
        return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()


def sign(envelope: Envelope, private_key_pem: bytes) -> bytes:
    key = serialization.load_pem_private_key(private_key_pem, password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise SecurityViolation("solo se admiten claves RSA")
    signature = key.sign(envelope.canonical_bytes(), _PSS, hashes.SHA256())
    payload = {
        "identity": envelope.identity,
        "sequence": envelope.sequence,
        "sent_at": envelope.sent_at,
        "samples": [asdict(s) for s in envelope.samples],
        "signature": base64.b64encode(signature).decode(),
    }
    return json.dumps(payload, separators=(",", ":")).encode()


def verify(
    raw: bytes,
    certificate_pem: bytes,
    now: datetime,
    last_sequence: int | None = None,
    max_age: timedelta = DEFAULT_MAX_AGE,
) -> tuple[GatewayIdentity, Envelope]:
    """Verifica y devuelve la identidad PROBADA, nunca la declarada.

    El orden importa: tamano, forma, firma, frescura, secuencia. Se valida
    el tamano antes de parsear para no gastar CPU en un payload gigante.
    """
    if len(raw) > MAX_ENVELOPE_BYTES:
        raise SecurityViolation(f"sobre demasiado grande: {len(raw)} bytes")

    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise SecurityViolation("sobre ilegible") from exc
    if not isinstance(payload, dict):
        raise SecurityViolation("el sobre no es un objeto")

    try:
        signature = base64.b64decode(payload["signature"], validate=True)
        samples = [Sample(**s) for s in payload["samples"]]
        envelope = Envelope(
            identity=payload["identity"],
            sequence=int(payload["sequence"]),
            sent_at=payload["sent_at"],
            samples=samples,
        )
    except (KeyError, TypeError, ValueError, base64.binascii.Error) as exc:
        raise SecurityViolation("sobre malformado") from exc

    if len(envelope.samples) > MAX_SAMPLES:
        raise SecurityViolation(f"demasiadas muestras: {len(envelope.samples)}")

    certificate = load_pem_x509_certificate(certificate_pem)
    public_key = certificate.public_key()
    if not isinstance(public_key, rsa.RSAPublicKey):
        raise SecurityViolation("el certificado enrolado no lleva clave RSA")

    try:
        public_key.verify(
            signature, envelope.canonical_bytes(), _PSS, hashes.SHA256()
        )
    except InvalidSignature as exc:
        raise SecurityViolation("firma invalida: el sobre fue manipulado") from exc

    sent_at = _parse_timestamp(envelope.sent_at)
    if abs((now - sent_at).total_seconds()) > max_age.total_seconds():
        raise SecurityViolation(f"sobre fuera de la ventana temporal: {envelope.sent_at}")

    if last_sequence is not None and envelope.sequence <= last_sequence:
        raise SecurityViolation(
            f"secuencia {envelope.sequence} ya vista (ultima {last_sequence}): reenvio"
        )

    # La identidad se toma del sobre FIRMADO, nunca del topic.
    return GatewayIdentity.from_san_uri(envelope.identity), envelope


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SecurityViolation(f"timestamp invalido: {value!r}") from exc
    if parsed.tzinfo is None:
        raise SecurityViolation("el timestamp debe llevar zona horaria")
    return parsed.astimezone(timezone.utc)
