"""Puerto TenantContext.

Ningun repositorio se construye sin uno. El adaptador de Postgres lo usa
para fijar la variable de sesion que activa las politicas RLS; el test de
arquitectura falla el build si aparece un repositorio que no lo exige.
"""
from __future__ import annotations

from typing import Protocol

from ferrogate.shared.domain.identifiers import TenantId
from ferrogate.shared.errors import TenantIsolationViolation


class TenantContext(Protocol):
    @property
    def tenant_id(self) -> TenantId: ...

    def assert_owns(self, other: TenantId) -> None: ...


class FixedTenantContext:
    def __init__(self, tenant_id: TenantId) -> None:
        self._tenant_id = tenant_id

    @property
    def tenant_id(self) -> TenantId:
        return self._tenant_id

    def assert_owns(self, other: TenantId) -> None:
        if other != self._tenant_id:
            raise TenantIsolationViolation(
                f"contexto {self._tenant_id} intento acceder a {other}"
            )
