"""Composition root del servicio de ingesta.

Es el UNICO sitio donde se instancian adaptadores concretos. El dominio y
los casos de uso solo conocen puertos; por eso los tests de arquitectura
pueden prohibir que importen sqlalchemy o influxdb y siguen pasando.
"""
from __future__ import annotations

import asyncio
import logging
import os
import ssl
from pathlib import Path

import aiomqtt
from influxdb_client import InfluxDBClient
from sqlalchemy import create_engine

from ferrogate.assets.infrastructure.postgres_repository import PostgresAssetRepository
from ferrogate.ingestion.application.ingest_telemetry import IngestTelemetry
from ferrogate.ingestion.infrastructure.influx_sink import InfluxMeasurementSink
from ferrogate.ingestion.infrastructure.mqtt_ingest import EnvelopeProcessor
from ferrogate.ingestion.infrastructure.postgres_audit import PostgresAuditLog
from ferrogate.ingestion.infrastructure.postgres_security_log import PostgresSecurityLog
from ferrogate.shared.domain.clock import SystemClock
from ferrogate.tenancy.infrastructure.postgres_registry import PostgresGatewayRegistry

log = logging.getLogger("platform")


def build_tls_context() -> ssl.SSLContext:
    certs = Path(os.getenv("CERT_DIR", "/certs"))
    ctx = ssl.create_default_context(
        ssl.Purpose.SERVER_AUTH, cafile=str(certs / "ca.crt")
    )
    ctx.load_cert_chain(
        certfile=str(certs / "platform-ingest.crt"),
        keyfile=str(certs / "platform-ingest.key"),
    )
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


async def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    influx = InfluxDBClient(
        url=os.environ["INFLUX_URL"],
        token=os.environ["INFLUX_TOKEN"],
        org=os.environ["INFLUX_ORG"],
    )
    clock = SystemClock()
    audit = PostgresAuditLog(engine)

    processor = EnvelopeProcessor(
        registry=PostgresGatewayRegistry(engine),
        ingest=IngestTelemetry(
            assets=PostgresAssetRepository(engine),
            sink=InfluxMeasurementSink(influx, org=os.environ["INFLUX_ORG"]),
            audit=audit,
            clock=clock,
        ),
        security=PostgresSecurityLog(engine),
        clock=clock,
    )

    while True:
        try:
            async with aiomqtt.Client(
                hostname=os.getenv("MQTT_HOST", "mosquitto"),
                port=int(os.getenv("MQTT_PORT", "8883")),
                tls_context=build_tls_context(),
            ) as client:
                await client.subscribe("ferrogate/+/+/telemetry/#", qos=1)
                log.info("ingesta escuchando")
                async for message in client.messages:
                    try:
                        processor.process(str(message.topic), bytes(message.payload))
                    except Exception:
                        # Un sobre malo nunca tumba el consumidor entero.
                        log.exception("fallo procesando %s", message.topic)
        except aiomqtt.MqttError:
            log.warning("broker inalcanzable, reintento en 5s")
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
