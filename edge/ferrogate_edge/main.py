"""Punto de entrada del colector edge.

Un colector = un sitio = un tenant. Aqui NO hay logica multi-tenant: esa
vive en la plataforma. Meterla aqui seria modelar algo que no existe.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
from pathlib import Path

import aiomqtt

from ferrogate_edge.application.collect import CollectCycle
from ferrogate_edge.domain.tag_mapping import SiteConfig
from ferrogate_edge.infrastructure.buffer.sqlite_buffer import SqliteBuffer
from ferrogate_edge.infrastructure.modbus.reader import ModbusDeviceReader
from ferrogate_edge.infrastructure.mqtt.publisher import MqttPublisher, build_tls_context

log = logging.getLogger("edge")


async def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    config = SiteConfig.load(Path(os.environ["SITE_CONFIG"]))
    certs = Path(os.getenv("CERT_DIR", "/certs"))
    key_path = certs / f"{config.tenant_id}.{config.gateway_id}.key"

    tls = build_tls_context(
        ca=certs / "ca.crt",
        cert=certs / f"{config.tenant_id}.{config.gateway_id}.crt",
        key=key_path,
    )
    buffer = SqliteBuffer(Path(os.getenv("BUFFER_PATH", "/var/lib/ferrogate/outbox.db")))
    reader = ModbusDeviceReader(config)

    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stopping.set)

    log.info("colector %s/%s -> %s:%s (%d tags, buffer=%d)",
             config.tenant_id, config.gateway_id,
             config.device_host, config.device_port,
             len(config.mappings), buffer.depth())

    while not stopping.is_set():
        try:
            async with aiomqtt.Client(
                hostname=os.getenv("MQTT_HOST", "mosquitto"),
                port=int(os.getenv("MQTT_PORT", "8883")),
                tls_context=tls,
            ) as client:
                cycle = CollectCycle(
                    config=config,
                    reader=reader,
                    publisher=MqttPublisher(client),
                    buffer=buffer,
                    private_key_pem=key_path.read_bytes(),
                )
                while not stopping.is_set():
                    await cycle.run_once()
                    await asyncio.sleep(config.poll_interval_seconds)
        except aiomqtt.MqttError:
            # El broker caido no es un error fatal: el buffer absorbe.
            log.warning("broker inalcanzable, reintento en 5s")
            await asyncio.sleep(5)

    await reader.close()
    buffer.close()
    log.info("colector detenido")


if __name__ == "__main__":
    asyncio.run(main())
