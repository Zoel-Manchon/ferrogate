"""Asset: raiz de agregado del core domain.

Jerarquia site -> linea -> maquina. Los tags solo se manipulan a traves
de la raiz, que es quien garantiza la unicidad de nombres y la
pertenencia al tenant.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ferrogate.assets.domain.tag_definition import TagDefinition
from ferrogate.shared.domain.identifiers import AssetId, TagId, TenantId
from ferrogate.shared.errors import DomainError


@dataclass(slots=True)
class Asset:
    id: AssetId
    tenant_id: TenantId
    name: str
    parent_id: AssetId | None = None
    tags: dict[TagId, TagDefinition] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise DomainError("el activo necesita nombre")
        if self.parent_id == self.id:
            raise DomainError("un activo no puede ser padre de si mismo")

    def add_tag(self, tag: TagDefinition) -> None:
        if any(t.name == tag.name for t in self.tags.values()):
            raise DomainError(
                f"el activo {self.name!r} ya tiene un tag llamado {tag.name!r}"
            )
        self.tags[tag.id] = tag

    def remove_tag(self, tag_id: TagId) -> None:
        tag = self.tags.get(tag_id)
        if tag is None:
            raise DomainError(f"tag {tag_id} no pertenece a {self.name!r}")
        if tag.has_history:
            raise DomainError(
                f"el tag {tag.name!r} tiene historico: archivalo en lugar de borrarlo"
            )
        del self.tags[tag_id]

    def tag_named(self, name: str) -> TagDefinition:
        for tag in self.tags.values():
            if tag.name == name:
                return tag
        raise DomainError(f"el activo {self.name!r} no tiene tag {name!r}")
