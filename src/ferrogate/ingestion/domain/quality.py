"""Codigos de calidad al estilo OPC-UA.

Un dato malo NUNCA se descarta en silencio: se almacena con su calidad.
Perder la distincion entre "no hay dato" y "el dato es basura" es el
error clasico de los pipelines de telemetria caseros.
"""
from __future__ import annotations

from enum import StrEnum


class Quality(StrEnum):
    GOOD = "good"
    UNCERTAIN = "uncertain"
    BAD = "bad"

    @property
    def is_usable(self) -> bool:
        return self is not Quality.BAD


class QualityReason(StrEnum):
    OK = "ok"
    OUT_OF_RANGE = "out_of_range"
    STALE = "stale"
    DEVICE_TIMEOUT = "device_timeout"
    DECODE_ERROR = "decode_error"
    CLOCK_SKEW = "clock_skew"
