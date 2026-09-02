"""Eventos de dominio. Todo evento lleva tenant: la auditoria tambien esta
aislada por tenant, no solo los datos."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ferrogate.shared.domain.identifiers import TenantId


@dataclass(frozen=True, slots=True)
class DomainEvent:
    tenant_id: TenantId
    event_id: uuid.UUID = field(default_factory=uuid.uuid4)
    occurred_at: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )

    @property
    def name(self) -> str:
        return type(self).__name__
