"""Lector Modbus TCP.

Un fallo de lectura NO tumba el ciclo: se omite ese tag y se sigue. Un
registro caido no debe cegar al resto del contador.
"""
from __future__ import annotations

import logging
import struct
from datetime import datetime, timezone

from pymodbus.client import AsyncModbusTcpClient

from ferrogate_edge.domain.tag_mapping import SiteConfig, TagMapping
from ferrogate.shared.security.envelope import Sample

log = logging.getLogger("edge.modbus")


def decode_float32(registers: list[int], word_order: str) -> float:
    high, low = (registers[0], registers[1]) if word_order == "big" else (
        registers[1], registers[0]
    )
    return struct.unpack(">f", struct.pack(">HH", high, low))[0]


class ModbusDeviceReader:
    def __init__(self, config: SiteConfig) -> None:
        self._config = config
        self._client = AsyncModbusTcpClient(config.device_host, port=config.device_port)

    async def read_all(self) -> list[Sample]:
        if not self._client.connected:
            await self._client.connect()
        if not self._client.connected:
            log.warning("dispositivo %s:%s inalcanzable",
                        self._config.device_host, self._config.device_port)
            return []

        now = datetime.now(tz=timezone.utc).isoformat()
        samples: list[Sample] = []
        for mapping in self._config.mappings:
            sample = await self._read_one(mapping, now)
            if sample is not None:
                samples.append(sample)
        return samples

    async def _read_one(self, mapping: TagMapping, now: str) -> Sample | None:
        try:
            result = await self._client.read_input_registers(
                mapping.register, count=mapping.register_count, slave=mapping.unit_id
            )
            if result.isError():
                log.debug("lectura con error en %s", mapping.tag_name)
                return None
            value = decode_float32(result.registers, mapping.word_order)
        except Exception:
            log.debug("excepcion leyendo %s", mapping.tag_name, exc_info=True)
            return None

        return Sample(
            asset_id=mapping.asset_id,
            tag_name=mapping.tag_name,
            raw_value=float(value),
            source_timestamp=now,
        )

    async def close(self) -> None:
        self._client.close()
