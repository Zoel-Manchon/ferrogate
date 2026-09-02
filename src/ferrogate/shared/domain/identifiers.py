"""Identificadores del kernel compartido.

TenantId es un value object, nunca un str suelto. Todo repositorio y todo
caso de uso lo exige explicitamente: es la frontera de aislamiento.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}$")


class InvalidIdentifier(ValueError):
    """El identificador no cumple la forma exigida por el dominio."""


@dataclass(frozen=True, slots=True)
class TenantId:
    value: str

    def __post_init__(self) -> None:
        if not _SLUG.match(self.value):
            raise InvalidIdentifier(f"tenant id invalido: {self.value!r}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class GatewayId:
    value: str

    def __post_init__(self) -> None:
        if not _SLUG.match(self.value):
            raise InvalidIdentifier(f"gateway id invalido: {self.value!r}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class AssetId:
    value: uuid.UUID

    @staticmethod
    def new() -> AssetId:
        return AssetId(uuid.uuid4())

    def __str__(self) -> str:
        return str(self.value)


@dataclass(frozen=True, slots=True)
class TagId:
    value: uuid.UUID

    @staticmethod
    def new() -> TagId:
        return TagId(uuid.uuid4())

    def __str__(self) -> str:
        return str(self.value)
