"""Sink de InfluxDB con un bucket por tenant.

El bucket se deriva del tenant PROBADO por la firma, nunca de un campo
del mensaje. Asi una consulta o un mensaje mal formado no pueden escribir
en el bucket de otro cliente.
"""
from __future__ import annotations

import logging
from collections.abc import Sequence

from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

from ferrogate.ingestion.domain.measurement import Measurement
from ferrogate.shared.domain.identifiers import TenantId

log = logging.getLogger("influx")


class InfluxMeasurementSink:
    def __init__(self, client: InfluxDBClient, org: str) -> None:
        self._write = client.write_api(write_options=SYNCHRONOUS)
        self._org = org
        self._written = 0
        self._batches = 0

    @staticmethod
    def bucket_for(tenant_id: TenantId) -> str:
        return f"tenant-{tenant_id}"

    def write(self, tenant_id: TenantId, measurements: Sequence[Measurement]) -> None:
        points = [
            Point("telemetry")
            .tag("asset_id", str(m.asset_id))
            .tag("tag_id", str(m.tag_id))
            .tag("tag_name", m.tag_name)
            .tag("unit", m.unit)
            .tag("quality", m.quality.value)
            .tag("reason", m.reason.value)
            .field("value", float(m.value))
            .field("latency_seconds", m.latency_seconds)
            .time(m.source_timestamp, WritePrecision.NS)
            for m in measurements
        ]
        bucket = self.bucket_for(tenant_id)
        try:
            self._write.write(bucket=bucket, org=self._org, record=points)
        except Exception:
            # Se relanza, pero deja claro EN QUE bucket y con que org fallo:
            # el 401 o el "bucket not found" son los errores tipicos y sin
            # este contexto se confunden con "no llegan datos".
            log.exception(
                "fallo escribiendo %d puntos en bucket=%s org=%s",
                len(points), bucket, self._org,
            )
            raise
        self._written += len(points)
        if self._batches % 20 == 0:
            # A nivel INFO: la escritura efectiva es el unico hecho que
            # distingue "el pipeline funciona" de "el pipeline corre".
            log.info("escritos %d puntos acumulados en %s (org=%s)",
                     self._written, bucket, self._org)
        self._batches += 1
