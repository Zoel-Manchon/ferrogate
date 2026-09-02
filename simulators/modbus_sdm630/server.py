"""Servidor Modbus TCP que simula un Eastron SDM630.

Expone los registros de entrada (funcion 04) como float32 big-endian,
dos registros por magnitud, que es como los publica el contador real.

Variables de entorno:
    TENANT_ID, GATEWAY_ID   solo para el log, el simulador no es multi-tenant
    MODBUS_PORT             por defecto 5020
    UNIT_ID                 por defecto 1
    FAULT_TAG / FAULT_MODE  inyecta un fallo en una magnitud concreta
"""
from __future__ import annotations

import asyncio
import logging
import os
import struct
import time

from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
)
from pymodbus.server import StartAsyncTcpServer

from plant import FaultMode, SignalGenerator
from register_map import INPUT_REGISTERS

log = logging.getLogger("sdm630")

# El SDM630 sirve la palabra alta primero. Si inviertes esto, los valores
# salen como numeros absurdos: es el error clasico al integrar Modbus.
WORD_ORDER_BIG_ENDIAN = True


def encode_float32(value: float) -> list[int]:
    high, low = struct.unpack(">HH", struct.pack(">f", value))
    return [high, low] if WORD_ORDER_BIG_ENDIAN else [low, high]


def build_generators() -> dict[int, SignalGenerator]:
    fault_tag = os.getenv("FAULT_TAG", "")
    fault_mode = FaultMode(os.getenv("FAULT_MODE", "none"))

    generators: dict[int, SignalGenerator] = {}
    for register, (name, _unit, low, high) in INPUT_REGISTERS.items():
        generators[register] = SignalGenerator(
            low=low,
            high=high,
            fault=fault_mode if name == fault_tag else FaultMode.NONE,
        )
    return generators


async def drive(context: ModbusServerContext, unit_id: int) -> None:
    """Refresca los registros una vez por segundo."""
    generators = build_generators()
    started = time.monotonic()
    energy = 0.0

    while True:
        elapsed = time.monotonic() - started
        slave = context[unit_id]

        for register, generator in generators.items():
            name = INPUT_REGISTERS[register][0]

            # La energia es un contador acumulado, no una senal periodica.
            if name == "import_active_energy":
                energy += 0.01
                value: float | None = energy
            else:
                value = generator.sample(elapsed)

            # DROPOUT: no se escribe nada, el registro se queda obsoleto.
            # El gateway debe marcarlo como STALE, no leerlo como valido.
            if value is None:
                continue

            slave.setValues(4, register, encode_float32(value))

        await asyncio.sleep(1.0)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    port = int(os.getenv("MODBUS_PORT", "5020"))
    unit_id = int(os.getenv("UNIT_ID", "1"))

    # 0x0000..0x004C cubre el bloque que declaramos en register_map.
    block = ModbusSequentialDataBlock(0, [0] * 0x0100)
    context = ModbusServerContext(
        slaves={unit_id: ModbusSlaveContext(ir=block)}, single=False
    )

    log.info(
        "SDM630 simulado en 0.0.0.0:%s unit=%s tenant=%s gateway=%s fault=%s",
        port, unit_id,
        os.getenv("TENANT_ID", "-"), os.getenv("GATEWAY_ID", "-"),
        os.getenv("FAULT_MODE", "none"),
    )

    asyncio.create_task(drive(context, unit_id))
    await StartAsyncTcpServer(context=context, address=("0.0.0.0", port))


if __name__ == "__main__":
    asyncio.run(main())
