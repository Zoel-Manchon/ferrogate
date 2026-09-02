from __future__ import annotations

from typing import Protocol

from ferrogate.shared.domain.identifiers import GatewayId, TenantId


class GatewayRegistry(Protocol):
    """Certificados enrolados. La ingesta verifica firmas contra esto."""

    def certificate_pem(
        self, tenant_id: TenantId, gateway_id: GatewayId
    ) -> bytes | None: ...

    def last_sequence(
        self, tenant_id: TenantId, gateway_id: GatewayId
    ) -> int | None: ...

    def record_sequence(
        self, tenant_id: TenantId, gateway_id: GatewayId, sequence: int
    ) -> None: ...
