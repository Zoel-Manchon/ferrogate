from datetime import datetime, timedelta, timezone

import pytest

from ferrogate.alarming.domain.alarm import (
    AlarmInstance, AlarmRule, AlarmState, Comparison,
)
from ferrogate.shared.domain.identifiers import TagId, TenantId
from ferrogate.shared.errors import DomainError

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _rule(**kw):
    defaults = dict(
        tenant_id=TenantId("acme"), tag_id=TagId.new(),
        comparison=Comparison.ABOVE, threshold=100.0,
        hysteresis=5.0, min_duration_seconds=10.0,
    )
    return AlarmRule(**{**defaults, **kw})


def test_un_pico_corto_no_activa_la_alarma():
    alarm = AlarmInstance(rule=_rule())
    alarm.evaluate(120.0, T0)
    assert alarm.evaluate(95.0, T0 + timedelta(seconds=3)) is AlarmState.NORMAL


def test_supera_umbral_sostenido_activa():
    alarm = AlarmInstance(rule=_rule())
    alarm.evaluate(120.0, T0)
    assert alarm.evaluate(120.0, T0 + timedelta(seconds=11)) is AlarmState.ACTIVE


def test_histeresis_evita_el_chattering():
    alarm = AlarmInstance(rule=_rule())
    alarm.evaluate(120.0, T0)
    alarm.evaluate(120.0, T0 + timedelta(seconds=11))
    # 98 esta por debajo del umbral pero dentro de la banda de histeresis
    assert alarm.evaluate(98.0, T0 + timedelta(seconds=20)) is AlarmState.ACTIVE
    assert alarm.evaluate(94.0, T0 + timedelta(seconds=30)) is AlarmState.CLEARED


def test_no_se_reconoce_una_alarma_que_no_esta_activa():
    alarm = AlarmInstance(rule=_rule())
    with pytest.raises(DomainError):
        alarm.acknowledge("operador1", T0)
