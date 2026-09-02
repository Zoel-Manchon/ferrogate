"""TagDefinition: entidad interna del agregado Asset.

Concentra las invariantes que hacen que este proyecto no sea un CRUD:
una definicion de tag no puede quedar en un estado que produzca datos
sin sentido fisico.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ferrogate.assets.domain.value_objects import (
    DataType,
    Deadband,
    EngineeringRange,
    ModbusAddress,
    Scaling,
    Unit,
)
from ferrogate.shared.domain.identifiers import TagId
from ferrogate.shared.errors import DomainError


@dataclass(slots=True)
class TagDefinition:
    id: TagId
    name: str
    data_type: DataType
    unit: Unit
    scaling: Scaling = field(default_factory=Scaling)
    engineering_range: EngineeringRange | None = None
    deadband: Deadband = field(default_factory=Deadband)
    modbus_address: ModbusAddress | None = None
    opcua_node_id: str | None = None
    has_history: bool = False

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise DomainError("el tag necesita nombre")
        if self.modbus_address is None and self.opcua_node_id is None:
            raise DomainError(
                f"el tag {self.name!r} no tiene direccion de origen"
            )
        if self.modbus_address is not None and self.opcua_node_id is not None:
            raise DomainError(
                f"el tag {self.name!r} tiene dos origenes; elige uno"
            )

    def change_unit(self, unit: Unit) -> None:
        """Una vez hay historico, cambiar la unidad corrompe la serie."""
        if self.has_history and unit != self.unit:
            raise DomainError(
                f"el tag {self.name!r} ya tiene historico: no se puede pasar "
                f"de {self.unit.value!r} a {unit.value!r}"
            )
        self.unit = unit

    def to_engineering(self, raw: float) -> float:
        return self.scaling.apply(raw)

    def is_in_range(self, engineering_value: float) -> bool:
        if self.engineering_range is None:
            return True
        return self.engineering_range.contains(engineering_value)
