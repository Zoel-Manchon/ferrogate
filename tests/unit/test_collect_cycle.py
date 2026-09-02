import asyncio, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "edge"))

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from ferrogate_edge.application.collect import CollectCycle
from ferrogate_edge.domain.tag_mapping import SiteConfig, TagMapping
from ferrogate_edge.infrastructure.buffer.sqlite_buffer import SqliteBuffer
from ferrogate.shared.security.envelope import Sample

CONFIG = SiteConfig(
    tenant_id="acme", gateway_id="planta-norte",
    device_host="x", device_port=5020, poll_interval_seconds=1.0,
    mappings=(TagMapping("a1", "voltage_l1", 1, 0),),
)


def key_pem():
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return k.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption())


class FakeReader:
    async def read_all(self):
        return [Sample("a1", "voltage_l1", 232.0, "2026-06-01T12:00:00+00:00")]
    async def close(self): ...


class BrokenPublisher:
    async def publish(self, topic, payload):
        raise ConnectionError("enlace caido")


class RecordingPublisher:
    def __init__(self): self.sent = []
    async def publish(self, topic, payload): self.sent.append((topic, payload))


def test_si_el_enlace_cae_no_se_pierde_el_dato(tmp_path):
    buf = SqliteBuffer(tmp_path / "o.db")
    cycle = CollectCycle(CONFIG, FakeReader(), BrokenPublisher(), buf, key_pem())
    asyncio.run(cycle.run_once())
    assert buf.depth() == 1


def test_al_recuperar_se_drena_el_buffer_primero(tmp_path):
    buf = SqliteBuffer(tmp_path / "o.db")
    pem = key_pem()
    asyncio.run(CollectCycle(CONFIG, FakeReader(), BrokenPublisher(), buf, pem).run_once())
    asyncio.run(CollectCycle(CONFIG, FakeReader(), BrokenPublisher(), buf, pem).run_once())
    assert buf.depth() == 2

    publisher = RecordingPublisher()
    asyncio.run(CollectCycle(CONFIG, FakeReader(), publisher, buf, pem).run_once())
    # 2 del buffer + 1 nuevo, y el buffer queda vacio
    assert len(publisher.sent) == 3
    assert buf.depth() == 0


def test_el_topic_lo_construye_el_propio_gateway():
    cycle = CollectCycle(CONFIG, FakeReader(), RecordingPublisher(),
                         SqliteBuffer(pathlib.Path("/tmp/t.db")), key_pem())
    assert cycle.topic == "ferrogate/acme/planta-norte/telemetry/data"
    assert cycle.identity_urn == "urn:ferrogate:tenant:acme:gateway:planta-norte"


def test_la_secuencia_sobrevive_a_un_reinicio(tmp_path):
    """Sin esto, el gateway queda mudo tras el primer reinicio."""
    path = tmp_path / "o.db"
    pem = key_pem()

    buf = SqliteBuffer(path)
    pub = RecordingPublisher()
    for _ in range(3):
        asyncio.run(CollectCycle(CONFIG, FakeReader(), pub, buf, pem).run_once())
    assert buf.last_sequence() == 3
    buf.close()

    # "Reinicio" del colector con el mismo volumen
    buf2 = SqliteBuffer(path)
    pub2 = RecordingPublisher()
    asyncio.run(CollectCycle(CONFIG, FakeReader(), pub2, buf2, pem).run_once())
    assert buf2.last_sequence() == 4, "la secuencia se reinicio: replay garantizado"

    import json
    assert json.loads(pub2.sent[0][1])["sequence"] == 4
