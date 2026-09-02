"""Consumidor MQTT.

Orden de comprobaciones, y el orden es la seguridad:

1. Se parsea la identidad DECLARADA solo para localizar el certificado.
2. Se verifica la firma contra ese certificado. Si falla, se acabo.
3. Solo entonces la identidad se considera probada.
4. El topic se comprueba contra la identidad probada, no al reves.

Un gateway revocado no tiene certificado en el registro: paso 1 falla y
el sobre se descarta aunque su firma fuese buena en su dia.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime

from ferrogate.ingestion.application.ingest_telemetry import IngestTelemetry, RawSample
from ferrogate.ingestion.application.ports import SecurityLog
from ferrogate.shared.domain.clock import Clock
from ferrogate.shared.domain.identifiers import AssetId
from ferrogate.shared.errors import DomainError, SecurityViolation
from ferrogate.shared.security.envelope import verify
from ferrogate.shared.security.gateway_identity import GatewayIdentity
from ferrogate.tenancy.application.ports import GatewayRegistry

log = logging.getLogger("ingest")

# El camino feliz tambien se registra. Si solo se registran los errores,
# "todo funciona" y "no llega nada" producen exactamente los mismos logs
# -- silencio -- y son indistinguibles. Se resume cada N sobres para no
# inundar.
LOG_EVERY = 20


class EnvelopeProcessor:
    def __init__(
        self,
        registry: GatewayRegistry,
        ingest: IngestTelemetry,
        security: SecurityLog,
        clock: Clock,
    ) -> None:
        self._registry = registry
        self._ingest = ingest
        self._security = security
        self._clock = clock
        self._accepted = 0
        self._samples = 0

    def process(self, topic: str, raw: bytes) -> None:
        try:
            claimed = self._claimed_identity(raw)
        except SecurityViolation as exc:
            self._security.reject(None, None, "ingest.unreadable_identity",
                                  {"topic": topic, "reason": str(exc)})
            log.warning("sobre sin identidad legible en %s", topic)
            return

        certificate = self._registry.certificate_pem(
            claimed.tenant_id, claimed.gateway_id
        )
        if certificate is None:
            self._security.reject(
                str(claimed.tenant_id), str(claimed.gateway_id),
                "ingest.unknown_or_revoked_gateway", {"topic": topic},
            )
            return

        last = self._registry.last_sequence(claimed.tenant_id, claimed.gateway_id)

        try:
            identity, envelope = verify(
                raw, certificate, now=self._clock.now(), last_sequence=last
            )
        except SecurityViolation as exc:
            self._security.reject(
                str(claimed.tenant_id), str(claimed.gateway_id),
                "ingest.envelope_rejected", {"topic": topic, "reason": str(exc)},
            )
            log.warning("sobre rechazado en %s: %s", topic, exc)
            return

        samples = [
            RawSample(
                asset_id=AssetId(_uuid(s.asset_id)),
                tag_name=s.tag_name,
                raw_value=s.raw_value,
                source_timestamp=_ts(s.source_timestamp),
            )
            for s in envelope.samples
        ]

        try:
            self._ingest(identity, topic, samples)
        except DomainError as exc:
            # DomainError, no SecurityViolation: TenantIsolationViolation es su
            # HERMANA, no su hija, asi que un activo de otro tenant se escapaba
            # de este except y acababa en el catch-all del bucle como un
            # stacktrace, sin quedar registrado como rechazo de seguridad.
            self._security.reject(
                str(identity.tenant_id), str(identity.gateway_id),
                "ingest.rejected_by_domain", {"topic": topic, "reason": str(exc)},
            )
            log.warning("ingesta rechazada: %s", exc)
            return

        self._registry.record_sequence(
            identity.tenant_id, identity.gateway_id, envelope.sequence
        )

        self._accepted += 1
        self._samples += len(samples)
        if self._accepted % LOG_EVERY == 1:
            log.info(
                "aceptados %d sobres / %d muestras (ultimo: %s seq=%d)",
                self._accepted, self._samples, identity.tenant_id,
                envelope.sequence,
            )

    @staticmethod
    def _claimed_identity(raw: bytes) -> GatewayIdentity:
        try:
            declared = json.loads(raw)["identity"]
        except (ValueError, KeyError, TypeError) as exc:
            raise SecurityViolation("sin campo identity") from exc
        return GatewayIdentity.from_san_uri(declared)


def _uuid(value: str) -> uuid.UUID:
    return uuid.UUID(value)


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value)
