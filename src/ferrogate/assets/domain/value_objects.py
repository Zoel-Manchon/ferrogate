from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ferrogate.shared.errors import DomainError


class DataType(StrEnum):
    FLOAT32 = "float32"
    INT16 = "int16"
    UINT16 = "uint16"
    INT32 = "int32"
    BOOL = "bool"


class Unit(StrEnum):
    VOLT = "V"
    AMPERE = "A"
    WATT = "W"
    KILOWATT_HOUR = "kWh"
    HERTZ = "Hz"
    CELSIUS = "degC"
    BAR = "bar"
    PERCENT = "%"
    NONE = ""


@dataclass(frozen=True, slots=True)
class Scaling:
    """valor_ingenieria = raw * factor + offset."""

    factor: float = 1.0
    offset: float = 0.0

    def __post_init__(self) -> None:
        if self.factor == 0:
            raise DomainError("el factor de escala no puede ser 0")

    def apply(self, raw: float) -> float:
        return raw * self.factor + self.offset


@dataclass(frozen=True, slots=True)
class EngineeringRange:
    low: float
    high: float

    def __post_init__(self) -> None:
        if self.low >= self.high:
            raise DomainError(f"rango invalido: {self.low} >= {self.high}")

    def contains(self, value: float) -> bool:
        return self.low <= value <= self.high


@dataclass(frozen=True, slots=True)
class Deadband:
    """Banda muerta: cambios menores no generan muestra nueva."""

    absolute: float = 0.0

    def __post_init__(self) -> None:
        if self.absolute < 0:
            raise DomainError("la banda muerta no puede ser negativa")

    def is_significant(self, previous: float | None, current: float) -> bool:
        if previous is None:
            return True
        return abs(current - previous) > self.absolute


@dataclass(frozen=True, slots=True)
class ModbusAddress:
    unit_id: int
    register: int
    register_count: int = 2
    function: str = "input"

    def __post_init__(self) -> None:
        if not 1 <= self.unit_id <= 247:
            raise DomainError(f"unit id fuera de rango Modbus: {self.unit_id}")
        if not 0 <= self.register <= 0xFFFF:
            raise DomainError(f"registro fuera de rango: {self.register}")
        if self.function not in ("input", "holding"):
            raise DomainError(f"funcion Modbus no soportada: {self.function}")
