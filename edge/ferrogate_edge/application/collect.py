"""Ciclo de recoleccion: leer, firmar, publicar o encolar.

Regla de oro: primero se drena el buffer, luego se publica lo nuevo. Al
reves, un enlace intermitente entrega los datos desordenados.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from ferrogate_edge.application.ports import Buffer, DeviceReader, Publisher
from ferrogate_edge.domain.tag_mapping import SiteConfig
from ferrogate.shared.security.envelope import Envelope, sign

log = logging.getLogger("edge.collect")
DRAIN_BATCH = 50


class CollectCycle:
    def __init__(
        self,
        config: SiteConfig,
        reader: DeviceReader,
        publisher: Publisher,
        buffer: Buffer,
        private_key_pem: bytes,
    ) -> None:
        self._config = config
        self._reader = reader
        self._publisher = publisher
        self._buffer = buffer
        self._key = private_key_pem
        # Se retoma donde quedo: reiniciar el colector no debe hacer que
        # la plataforma lo tome por un reenvio.
        self._sequence = buffer.last_sequence()
        self._published = 0

    @property
    def topic(self) -> str:
        return (
            f"ferrogate/{self._config.tenant_id}/{self._config.gateway_id}"
            f"/telemetry/data"
        )

    @property
    def identity_urn(self) -> str:
        return (
            f"urn:ferrogate:tenant:{self._config.tenant_id}"
            f":gateway:{self._config.gateway_id}"
        )

    async def run_once(self) -> None:
        await self._drain()

        samples = await self._reader.read_all()
        if not samples:
            return

        self._sequence += 1
        # Se persiste ANTES de publicar. Si el proceso muere entre ambos,
        # se pierde un numero de secuencia, que es inofensivo; reutilizarlo
        # no lo seria.
        self._buffer.set_sequence(self._sequence)
        envelope = Envelope(
            identity=self.identity_urn,
            sequence=self._sequence,
            sent_at=datetime.now(tz=timezone.utc).isoformat(),
            samples=list(samples),
        )
        payload = sign(envelope, self._key)

        try:
            await self._publisher.publish(self.topic, payload)
            self._published += 1
            if self._published % 20 == 1:
                log.info("publicados %d sobres (seq=%d, %d muestras)",
                         self._published, self._sequence, len(samples))
        except Exception:
            # No se pierde: a disco. El enlace caido es el caso normal,
            # no la excepcion.
            self._buffer.enqueue(self.topic, payload)
            log.warning("publicacion fallida, encolado (profundidad=%d)",
                        self._buffer.depth())

    async def _drain(self) -> None:
        pending = self._buffer.peek(DRAIN_BATCH)
        for row_id, topic, payload in pending:
            try:
                await self._publisher.publish(topic, payload)
            except Exception:
                return  # sigue caido; se reintenta en el proximo ciclo
            self._buffer.ack(row_id)
        if pending:
            log.info("reenviados %d sobres del buffer", len(pending))
