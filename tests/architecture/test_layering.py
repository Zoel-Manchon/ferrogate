"""Tests de arquitectura.

Estos fallan el build. Sin ellos, la arquitectura hexagonal se erosiona
en tres semanas y el README acaba mintiendo.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

SRC = pathlib.Path(__file__).resolve().parents[2] / "src" / "ferrogate"

FORBIDDEN_IN_DOMAIN = {
    "sqlalchemy", "psycopg", "fastapi", "pymodbus", "asyncua",
    "aiomqtt", "paho", "influxdb_client", "requests", "httpx",
}


def _imports(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
    return found


@pytest.mark.parametrize("path", sorted(SRC.rglob("domain/*.py")), ids=str)
def test_domain_no_importa_infraestructura(path: pathlib.Path) -> None:
    leaked = _imports(path) & FORBIDDEN_IN_DOMAIN
    assert not leaked, f"{path.name} importa infraestructura: {sorted(leaked)}"


@pytest.mark.parametrize("path", sorted(SRC.rglob("application/*.py")), ids=str)
def test_aplicacion_no_importa_infraestructura(path: pathlib.Path) -> None:
    leaked = _imports(path) & FORBIDDEN_IN_DOMAIN
    assert not leaked, f"{path.name} importa infraestructura: {sorted(leaked)}"
