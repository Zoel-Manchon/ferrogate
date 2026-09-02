"""La ACL del broker debe permitir los topics que el edge publica.

Este desajuste es invisible en ejecucion: Mosquitto deniega y nadie se
entera. El edge no se queja, la ingesta no recibe, y los paneles salen
vacios sin un solo error en los logs. Por eso hay test.
"""
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "edge"))

from ferrogate_edge.domain.tag_mapping import SiteConfig  # noqa: E402

CONFIGS = sorted((ROOT / "edge/ferrogate_edge/config").glob("*.yaml"))


def acl_rules(directive: str) -> dict[str, list[str]]:
    rules: dict[str, list[str]] = {}
    user = None
    for line in (ROOT / "ops/mosquitto/acl").read_text().splitlines():
        line = line.strip()
        if line.startswith("#") or not line:
            continue
        if line.startswith("user "):
            user = line.split(maxsplit=1)[1]
            rules[user] = []
        elif line.startswith(f"topic {directive} ") and user:
            rules[user].append(line.split(maxsplit=2)[2])
    return rules


def matches(pattern: str, topic: str) -> bool:
    regex = "^" + re.escape(pattern).replace(r"\#", ".*").replace(r"\+", "[^/]+") + "$"
    return re.match(regex, topic) is not None


@pytest.mark.parametrize("path", CONFIGS, ids=lambda p: p.stem)
def test_el_gateway_puede_publicar_su_topic(path):
    config = SiteConfig.load(path)
    username = f"{config.tenant_id}.{config.gateway_id}"
    topic = f"ferrogate/{config.tenant_id}/{config.gateway_id}/telemetry/data"

    rules = acl_rules("write")
    assert username in rules, (
        f"el CN {username!r} no tiene reglas en la ACL: el broker denegara "
        "toda publicacion en silencio"
    )
    assert any(matches(p, topic) for p in rules[username]), (
        f"ninguna regla de {username!r} permite {topic!r}: {rules[username]}"
    )


@pytest.mark.parametrize("path", CONFIGS, ids=lambda p: p.stem)
def test_un_gateway_no_puede_publicar_en_el_topic_de_otro(path):
    config = SiteConfig.load(path)
    username = f"{config.tenant_id}.{config.gateway_id}"
    rules = acl_rules("write")

    for other in CONFIGS:
        if other == path:
            continue
        other_config = SiteConfig.load(other)
        foreign = (
            f"ferrogate/{other_config.tenant_id}/{other_config.gateway_id}"
            "/telemetry/data"
        )
        assert not any(matches(p, foreign) for p in rules[username]), (
            f"{username!r} puede publicar en {foreign!r}"
        )


def test_la_ingesta_no_puede_publicar():
    """Solo lee. Si pudiera publicar, podria inyectar telemetria falsa."""
    assert acl_rules("write").get("platform-ingest", []) == []
    assert acl_rules("read").get("platform-ingest") == ["ferrogate/#"]
