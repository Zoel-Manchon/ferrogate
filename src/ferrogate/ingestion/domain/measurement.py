from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ferrogate.ingestion.domain.quality import Quality, QualityReason
from ferrogate.shared.domain.identifiers import AssetId, TagId, TenantId
from ferrogate.shared.errors import DomainError


@dataclass(frozen=True, slots=True)
class Measurement:
    tenant_id: TenantId
    asset_id: AssetId
    tag_id: TagId
    tag_name: str
    value: float
    unit: str
    quality: Quality
    reason: QualityReason
    source_timestamp: datetime
    received_timestamp: datetime

    def __post_init__(self) -> None:
        if self.source_timestamp.tzinfo is None:
            raise DomainError("source_timestamp debe llevar zona horaria")
        if self.received_timestamp.tzinfo is None:
            raise DomainError("received_timestamp debe llevar zona horaria")

    @property
    def latency_seconds(self) -> float:
        return (self.received_timestamp - self.source_timestamp).total_seconds()
