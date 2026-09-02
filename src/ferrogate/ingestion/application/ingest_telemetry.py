"""Caso de uso de ingesta.

Orden deliberado de las comprobaciones:

1. Identidad probada por el certificado manda sobre lo que diga el topic.
2. El activo tiene que pertenecer al tenant de esa identidad.
3. Solo entonces se normaliza y se evalua la calidad.

Invertir 1 y 2 es exactamente como se cuelan datos de un tenant en otro.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from ferrogate.ingestion.application.ports import (
    AssetRepository,
    AuditLog,
    MeasurementSink,
)
from ferrogate.ingestion.domain.measurement import Measurement
from ferrogate.ingestion.domain.quality import Quality, QualityReason
from ferrogate.shared.domain.clock import Clock
from ferrogate.shared.domain.identifiers import AssetId
from ferrogate.shared.errors import (
    DomainError,
    SecurityViolation,
    TenantIsolationViolation,
)
from ferrogate.shared.security.gateway_identity import GatewayIdentity

MAX_CLOCK_SKEW_SECONDS = 300


@dataclass(frozen=True, slots=True)
class RawSample:
    asset_id: AssetId
    tag_name: str
    raw_value: float
    source_timestamp: datetime


class IngestTelemetry:
    def __init__(
        self,
        assets: AssetRepository,
        sink: MeasurementSink,
        audit: AuditLog,
        clock: Clock,
    ) -> None:
        self._assets = assets
        self._sink = sink
        self._audit = audit
        self._clock = clock

    def __call__(
        self,
        identity: GatewayIdentity,
        topic: str,
        samples: Sequence[RawSample],
    ) -> None:
        if not identity.owns_topic(topic):
            self._audit.record(
                identity.tenant_id,
                "ingest.topic_identity_mismatch",
                {"topic": topic, "identity": identity.to_san_uri()},
            )
            raise SecurityViolation(
                f"el gateway {identity.gateway_id} no puede publicar en {topic!r}"
            )

        now = self._clock.now()
        out: list[Measurement] = []

        for sample in samples:
            asset = self._assets.get(identity.tenant_id, sample.asset_id)
            if asset is None:
                self._audit.record(
                    identity.tenant_id,
                    "ingest.unknown_asset",
                    {"asset_id": str(sample.asset_id)},
                )
                continue
            if asset.tenant_id != identity.tenant_id:
                self._audit.record(
                    identity.tenant_id,
                    "ingest.cross_tenant_asset",
                    {"asset_id": str(sample.asset_id)},
                )
                raise TenantIsolationViolation(
                    f"activo {sample.asset_id} no pertenece a {identity.tenant_id}"
                )

            try:
                tag = asset.tag_named(sample.tag_name)
            except DomainError:
                # Simetrico con el activo desconocido de arriba. Un tag que el
                # gateway envia y la plataforma aun no tiene definido es la
                # situacion normal durante una puesta en marcha, no un fallo
                # del sobre: descartar la muestra y seguir. Dejarlo propagar
                # tiraba el sobre ENTERO, incluidas las muestras validas que
                # fuesen delante, y sin dejar rastro auditable.
                self._audit.record(
                    identity.tenant_id,
                    "ingest.unknown_tag",
                    {"asset_id": str(sample.asset_id), "tag_name": sample.tag_name},
                )
                continue

            value = tag.to_engineering(sample.raw_value)

            quality, reason = Quality.GOOD, QualityReason.OK
            if not tag.is_in_range(value):
                quality, reason = Quality.BAD, QualityReason.OUT_OF_RANGE
            elif abs((now - sample.source_timestamp).total_seconds()) > MAX_CLOCK_SKEW_SECONDS:
                quality, reason = Quality.UNCERTAIN, QualityReason.CLOCK_SKEW

            out.append(
                Measurement(
                    tenant_id=identity.tenant_id,
                    asset_id=asset.id,
                    tag_id=tag.id,
                    tag_name=tag.name,
                    value=value,
                    unit=tag.unit.value,
                    quality=quality,
                    reason=reason,
                    source_timestamp=sample.source_timestamp,
                    received_timestamp=now,
                )
            )

        if out:
            self._sink.write(identity.tenant_id, out)
        else:
            # Aceptar un sobre y no escribir nada es un caso real y hasta
            # ahora invisible: el contador de aceptados subia igual.
            self._audit.record(
                identity.tenant_id, "ingest.no_measurements",
                {"topic": topic, "samples_received": len(samples)},
            )
