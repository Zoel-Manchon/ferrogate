"""Sesion con scope de tenant.

set_config(..., TRUE) hace el ajuste local a la transaccion: al terminar,
el valor desaparece. Con un pool de conexiones eso es imprescindible, o
la siguiente peticion hereda el tenant de la anterior.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy.engine import Connection
from sqlalchemy.sql import text

from ferrogate.shared.domain.identifiers import TenantId


@contextmanager
def tenant_scope(connection: Connection, tenant_id: TenantId) -> Iterator[Connection]:
    with connection.begin():
        connection.execute(
            text("SELECT set_config('ferrogate.tenant_id', :tid, TRUE)"),
            {"tid": str(tenant_id)},
        )
        yield connection
