"""Mapeo declarativo de tags.

El mapa vive en YAML, no en codigo. Anadir un dispositivo es editar un
fichero, no recompilar: es lo que separa un gateway de un script.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True, slots=True)
class TagMapping:
    asset_id: str
    tag_name: str
    unit_id: int
    register: int
    register_count: int = 2
    word_order: str = "big"

    def __post_init__(self) -> None:
        if self.word_order not in ("big", "little"):
            raise ValueError(f"word_order invalido: {self.word_order}")


@dataclass(frozen=True, slots=True)
class SiteConfig:
    tenant_id: str
    gateway_id: str
    device_host: str
    device_port: int
    poll_interval_seconds: float
    mappings: tuple[TagMapping, ...]

    @staticmethod
    def load(path: Path) -> "SiteConfig":
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return SiteConfig(
            tenant_id=data["tenant_id"],
            gateway_id=data["gateway_id"],
            device_host=data["device"]["host"],
            device_port=int(data["device"]["port"]),
            poll_interval_seconds=float(data.get("poll_interval_seconds", 5.0)),
            mappings=tuple(TagMapping(**m) for m in data["tags"]),
        )
