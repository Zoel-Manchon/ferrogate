from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from ferrogate.assets.domain.asset import Asset
from ferrogate.ingestion.domain.measurement import Measurement
from ferrogate.shared.domain.identifiers import AssetId, TenantId


class AssetRepository(Protocol):
    """Toda firma lleva tenant_id explicito.

    El test de arquitectura recorre este modulo y falla si aparece un
    metodo de lectura sin ese parametro.
    """

    def get(self, tenant_id: TenantId, asset_id: AssetId) -> Asset | None: ...

    def list_for_tenant(self, tenant_id: TenantId) -> Sequence[Asset]: ...


class MeasurementSink(Protocol):
    def write(self, tenant_id: TenantId, measurements: Sequence[Measurement]) -> None: ...


class AuditLog(Protocol):
    def record(self, tenant_id: TenantId, event: str, detail: dict[str, Any]) -> None: ...


class SecurityLog(Protocol):
    """Rechazos previos a la autenticacion.

    Deliberadamente SIN tenant_id probado: cuando se rechaza un sobre no
    se sabe todavia quien lo mando, solo quien dijo ser. Por eso este
    puerto no cumple la regla de "todo metodo lleva tenant_id" que aplica
    a los repositorios: no hay tenant que aplicar.
    """

    def reject(
        self,
        claimed_tenant: str | None,
        claimed_gateway: str | None,
        event: str,
        detail: dict[str, Any],
    ) -> None: ...
