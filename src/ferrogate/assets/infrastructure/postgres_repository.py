"""AssetRepository sobre Postgres, siempre dentro de tenant_scope.

El WHERE tenant_id no es lo que protege: lo que protege es la politica
RLS. El filtro explicito esta para que el plan de consulta use el indice,
no como control de seguridad.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ferrogate.assets.domain.asset import Asset
from ferrogate.assets.domain.tag_definition import TagDefinition
from ferrogate.assets.domain.value_objects import (
    DataType,
    Deadband,
    EngineeringRange,
    ModbusAddress,
    Scaling,
    Unit,
)
from ferrogate.shared.domain.identifiers import AssetId, TagId, TenantId
from ferrogate.shared.infrastructure.persistence.tenant_session import tenant_scope


class PostgresAssetRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get(self, tenant_id: TenantId, asset_id: AssetId) -> Asset | None:
        with self._engine.connect() as conn, tenant_scope(conn, tenant_id) as scoped:
            row = scoped.execute(
                text("SELECT id, tenant_id, name, parent_id FROM assets "
                     "WHERE id = :aid AND tenant_id = :tid"),
                {"aid": str(asset_id), "tid": str(tenant_id)},
            ).fetchone()
            if row is None:
                return None
            asset = Asset(
                id=AssetId(row.id),
                tenant_id=TenantId(row.tenant_id),
                name=row.name,
                parent_id=AssetId(row.parent_id) if row.parent_id else None,
            )
            for tag_row in scoped.execute(
                text("SELECT * FROM tags WHERE asset_id = :aid AND tenant_id = :tid"),
                {"aid": str(asset_id), "tid": str(tenant_id)},
            ):
                asset.add_tag(_to_tag(tag_row))
            return asset

    def list_for_tenant(self, tenant_id: TenantId) -> Sequence[Asset]:
        with self._engine.connect() as conn, tenant_scope(conn, tenant_id) as scoped:
            rows = scoped.execute(
                text("SELECT id FROM assets WHERE tenant_id = :tid"),
                {"tid": str(tenant_id)},
            ).fetchall()
        return [a for a in (self.get(tenant_id, AssetId(r.id)) for r in rows) if a]


# row es un Row de SQLAlchemy: sus columnas se resuelven en runtime,
# asi que Any es la anotacion honesta y no una rendicion.
def _to_tag(row: Any) -> TagDefinition:
    return TagDefinition(
        id=TagId(row.id),
        name=row.name,
        data_type=DataType(row.data_type),
        unit=Unit(row.unit),
        scaling=Scaling(factor=row.scale_factor, offset=row.scale_offset),
        engineering_range=(
            EngineeringRange(row.range_low, row.range_high)
            if row.range_low is not None and row.range_high is not None
            else None
        ),
        deadband=Deadband(row.deadband),
        modbus_address=(
            ModbusAddress(unit_id=row.modbus_unit, register=row.modbus_reg)
            if row.modbus_reg is not None
            else None
        ),
        opcua_node_id=row.opcua_node_id,
        has_history=row.has_history,
    )
