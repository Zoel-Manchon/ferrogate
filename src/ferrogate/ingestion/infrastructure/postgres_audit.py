from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ferrogate.shared.domain.identifiers import TenantId
from ferrogate.shared.infrastructure.persistence.tenant_session import tenant_scope


class PostgresAuditLog:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def record(self, tenant_id: TenantId, event: str, detail: dict[str, Any]) -> None:
        with self._engine.connect() as conn, tenant_scope(conn, tenant_id) as scoped:
            scoped.execute(
                text("INSERT INTO audit_events (tenant_id, event, detail) "
                     "VALUES (:tid, :ev, CAST(:dt AS jsonb))"),
                {"tid": str(tenant_id), "ev": event, "dt": json.dumps(detail)},
            )
