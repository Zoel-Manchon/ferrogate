"""Publicador MQTT sobre mTLS.

Sin certificado cliente no hay conexion. tls_insecure NUNCA se activa:
verificar el certificado del broker es lo que impide un man-in-the-middle
dentro de la red industrial, que es justo donde nadie mira.
"""
from __future__ import annotations

import ssl
from pathlib import Path

import aiomqtt


def build_tls_context(ca: Path, cert: Path, key: Path) -> ssl.SSLContext:
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(ca))
    context.load_cert_chain(certfile=str(cert), keyfile=str(key))
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


class MqttPublisher:
    def __init__(self, client: aiomqtt.Client) -> None:
        self._client = client

    async def publish(self, topic: str, payload: bytes) -> None:
        # QoS 1: al menos una vez. El duplicado lo resuelve el numero de
        # secuencia en el lado de la ingesta.
        await self._client.publish(topic, payload, qos=1)
