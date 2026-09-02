from __future__ import annotations

import json
import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

log = logging.getLogger("security")


class PostgresSecurityLog:
    """Sin tenant_scope: la tabla no lleva RLS y el tenant no esta probado."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def reject(
        self,
        claimed_tenant: str | None,
        claimed_gateway: str | None,
        event: str,
        detail: dict,
    ) -> None:
        try:
            with self._engine.connect() as conn, conn.begin():
                conn.execute(
                    text("INSERT INTO security_events "
                         "(claimed_tenant, claimed_gateway, event, detail) "
                         "VALUES (:t, :g, :e, CAST(:d AS jsonb))"),
                    {"t": claimed_tenant, "g": claimed_gateway,
                     "e": event, "d": json.dumps(detail)},
                )
        except Exception:
            # Que falle la auditoria NUNCA debe tumbar el consumidor: seria
            # una forma trivial de denegacion de servicio.
            log.exception("no se pudo registrar el evento de seguridad %s", event)
