"""Alarmas: la maquina de estados que justifica el modelado DDD.

    Normal --(supera umbral, sostenido)--> Active
    Active --(acknowledge)--> Acknowledged
    Active --(vuelve a normal + histeresis)--> Cleared
    Acknowledged --(vuelve a normal + histeresis)--> Cleared
    Cleared --> Normal

Dos reglas que se ven en toda planta real y que casi ningun proyecto de
portfolio implementa:

- Histeresis: la alarma no se limpia en el mismo umbral en que salta, o
  un valor oscilando genera cientos de alarmas por minuto (chattering).
- Tiempo minimo sostenido: un pico de un ciclo no es una alarma.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ferrogate.shared.domain.identifiers import TagId, TenantId
from ferrogate.shared.errors import DomainError


class AlarmState(str, Enum):
    NORMAL = "normal"
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    CLEARED = "cleared"


class Comparison(str, Enum):
    ABOVE = "above"
    BELOW = "below"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class AlarmRule:
    tenant_id: TenantId
    tag_id: TagId
    comparison: Comparison
    threshold: float
    hysteresis: float
    min_duration_seconds: float
    severity: Severity = Severity.WARNING

    def __post_init__(self) -> None:
        if self.hysteresis < 0:
            raise DomainError("la histeresis no puede ser negativa")
        if self.min_duration_seconds < 0:
            raise DomainError("la duracion minima no puede ser negativa")

    def breaches(self, value: float) -> bool:
        if self.comparison is Comparison.ABOVE:
            return value > self.threshold
        return value < self.threshold

    def has_recovered(self, value: float) -> bool:
        if self.comparison is Comparison.ABOVE:
            return value < self.threshold - self.hysteresis
        return value > self.threshold + self.hysteresis


@dataclass(slots=True)
class AlarmInstance:
    rule: AlarmRule
    state: AlarmState = AlarmState.NORMAL
    breach_started_at: datetime | None = None
    activated_at: datetime | None = None
    acknowledged_by: str | None = None
    transitions: list[tuple[datetime, AlarmState]] = field(default_factory=list)

    def evaluate(self, value: float, now: datetime) -> AlarmState:
        if self.state in (AlarmState.NORMAL, AlarmState.CLEARED):
            if self.rule.breaches(value):
                if self.breach_started_at is None:
                    self.breach_started_at = now
                held = (now - self.breach_started_at).total_seconds()
                if held >= self.rule.min_duration_seconds:
                    self._transition(AlarmState.ACTIVE, now)
                    self.activated_at = now
            else:
                self.breach_started_at = None
                if self.state is AlarmState.CLEARED:
                    self._transition(AlarmState.NORMAL, now)
        elif self.state in (AlarmState.ACTIVE, AlarmState.ACKNOWLEDGED):
            if self.rule.has_recovered(value):
                self._transition(AlarmState.CLEARED, now)
                self.breach_started_at = None
        return self.state

    def acknowledge(self, operator: str, now: datetime) -> None:
        if self.state is not AlarmState.ACTIVE:
            raise DomainError(
                f"solo se reconoce una alarma activa; estado actual: {self.state.value}"
            )
        if not operator.strip():
            raise DomainError("el reconocimiento necesita operador identificado")
        self.acknowledged_by = operator
        self._transition(AlarmState.ACKNOWLEDGED, now)

    def _transition(self, new_state: AlarmState, now: datetime) -> None:
        self.state = new_state
        self.transitions.append((now, new_state))
