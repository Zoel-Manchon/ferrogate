"""Simulador de planta con inyeccion de fallos.

Sin fallos inyectables no se pueden testear ni las alarmas ni los codigos
de calidad, y la demo no demuestra nada. Los modos cubren lo que de
verdad rompe en campo.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum


class FaultMode(str, Enum):
    NONE = "none"
    STUCK_AT = "stuck_at"          # sensor congelado: el valor no cambia
    OUT_OF_RANGE = "out_of_range"  # pico fisicamente imposible
    DRIFT = "drift"                # deriva lenta, la mas dificil de detectar
    DROPOUT = "dropout"            # el dispositivo deja de responder


@dataclass
class SignalGenerator:
    """Curva de carga por turnos + ruido, con fallo inyectable."""

    low: float
    high: float
    period_seconds: float = 3600.0
    noise: float = 0.01
    fault: FaultMode = FaultMode.NONE
    _drift: float = field(default=0.0, init=False)
    _last: float | None = field(default=None, init=False)

    def sample(self, t: float) -> float | None:
        if self.fault is FaultMode.DROPOUT:
            return None
        if self.fault is FaultMode.STUCK_AT and self._last is not None:
            return self._last

        mid = (self.low + self.high) / 2
        amp = (self.high - self.low) / 2
        value = mid + amp * math.sin(2 * math.pi * t / self.period_seconds)
        value += random.gauss(0, amp * self.noise)

        if self.fault is FaultMode.DRIFT:
            self._drift += (self.high - self.low) * 0.0005
            value += self._drift
        elif self.fault is FaultMode.OUT_OF_RANGE and random.random() < 0.05:
            value = self.high * 10

        self._last = value
        return value
