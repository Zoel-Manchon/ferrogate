"""Ningun metodo de repositorio puede consultar sin tenant explicito.

Este test es el que convierte "tenemos cuidado con el tenant_id" en una
garantia comprobable. Es lo primero que ensenaria en una entrevista.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

SRC = pathlib.Path(__file__).resolve().parents[2] / "src" / "ferrogate"

READ_PREFIXES = ("get", "list", "find", "search", "load", "count", "exists")


def _repository_protocols(path: pathlib.Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name.endswith(
            ("Repository", "Sink", "AuditLog")
        ):
            yield node


@pytest.mark.parametrize("path", sorted(SRC.rglob("application/ports.py")), ids=str)
def test_puertos_exigen_tenant(path: pathlib.Path) -> None:
    for cls in _repository_protocols(path):
        for fn in cls.body:
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if fn.name.startswith("_"):
                continue
            params = {a.arg for a in fn.args.args}
            if fn.name.startswith(READ_PREFIXES) or fn.name in ("write", "record"):
                assert "tenant_id" in params, (
                    f"{cls.name}.{fn.name} no exige tenant_id: "
                    "es un camino abierto entre tenants"
                )
