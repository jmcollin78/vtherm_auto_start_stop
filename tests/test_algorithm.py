"""Detection algorithm (tasks 3.1, 3.2, 3.3)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from homeassistant.util import dt as dt_util

from custom_components.vtherm_auto_start_stop.algorithm import (
    DT_MIN,
    ERROR_THRESHOLD,
    AutoStartStopDetectionAlgorithm,
    resolve_params,
)
from custom_components.vtherm_auto_start_stop.const import (
    LEVEL_FAST,
    LEVEL_MEDIUM,
    LEVEL_NONE,
    LEVEL_SLOW,
    LEVEL_VERY_SLOW,
)

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=dt_util.UTC)


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def make(level=LEVEL_FAST) -> AutoStartStopDetectionAlgorithm:
    return AutoStartStopDetectionAlgorithm(level, "FakeThermostat")


# ---------------------------------------------------------------------------
# resolve_params (task 3.2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "level", [LEVEL_VERY_SLOW, LEVEL_SLOW, LEVEL_MEDIUM, LEVEL_FAST]
)
def test_resolve_params_known_levels(level):
    """Every configured level maps to its table entry."""
    params = resolve_params(level)
    assert params.dt_min == DT_MIN[level]
    assert params.error_threshold == ERROR_THRESHOLD[level]


def test_resolve_params_none_level():
    """The `none` level disables detection: zero duration and zero threshold."""
    params = resolve_params(LEVEL_NONE)
    assert params.dt_min == 0
    assert params.error_threshold == 0


@pytest.mark.parametrize("level", ["auto_start_stop_personnalise", "", "unknown"])
def test_resolve_params_unknown_level_falls_back(level):
    """An unknown level must never break the control cycle."""
    params = resolve_params(level)
    assert params.dt_min == DT_MIN[LEVEL_SLOW]
    assert params.error_threshold == ERROR_THRESHOLD[LEVEL_SLOW]


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def test_none_level_never_detects():
    algo = make(LEVEL_NONE)
    algo.set_level(LEVEL_NONE)
    assert algo.should_be_turned_off("heat", 20.0, 25.0, 1.0, at(0)) is False


def test_missing_parameters_stay_idle():
    """A partially initialized thermostat does not trigger anything."""
    algo = make()
    assert algo.should_be_turned_off("heat", None, 19.0, 0.0, at(0)) is False
    assert algo.should_be_turned_off(None, 20.0, 19.0, 0.0, at(0)) is False


def test_heating_stops_when_overshoot_is_confirmed():
    """A sustained positive overshoot with a rising slope asks for a stop."""
    algo = make(LEVEL_FAST)
    # Overshoot: current above target, still rising.
    for minutes in range(0, 30, 1):
        decision = algo.should_be_turned_off("heat", 20.0, 21.0, 0.1, at(minutes))
    assert decision is True
    assert algo.accumulated_error <= -algo.accumulated_error_threshold


def test_heating_continues_while_temperature_is_far_below():
    """No stop while the room is below the target."""
    algo = make(LEVEL_FAST)
    for minutes in range(0, 30, 1):
        decision = algo.should_be_turned_off("heat", 21.0, 18.0, 0.05, at(minutes))
    assert decision is False


def test_two_measurements_in_the_same_cycle_accumulate_once():
    """The runtime clock is shared, so a double refresh is a no-op (3.1/3.3)."""
    algo = make(LEVEL_SLOW)
    algo.should_be_turned_off("heat", 20.0, 19.0, 0.0, at(0))
    after_first = algo.accumulated_error
    # Same clock value: the second measurement of the cycle is ignored.
    algo.should_be_turned_off("heat", 20.0, 19.0, 0.0, at(0))
    assert algo.accumulated_error == after_first


def test_accumulation_grows_with_elapsed_cycles():
    """A longer interval weights the error more."""
    algo_a = make(LEVEL_SLOW)
    algo_a.should_be_turned_off("heat", 20.0, 19.0, 0.0, at(0))
    algo_a.should_be_turned_off("heat", 20.0, 19.0, 0.0, at(2))
    one_cycle = algo_a.accumulated_error

    algo_b = make(LEVEL_SLOW)
    algo_b.should_be_turned_off("heat", 20.0, 19.0, 0.0, at(0))
    algo_b.should_be_turned_off("heat", 20.0, 19.0, 0.0, at(4))
    two_cycles = algo_b.accumulated_error

    assert two_cycles > one_cycle


def test_accumulation_is_capped_at_the_threshold():
    algo = make(LEVEL_FAST)
    for minutes in range(0, 60, 1):
        algo.should_be_turned_off("heat", 30.0, 10.0, 0.0, at(minutes))
    assert algo.accumulated_error <= algo.accumulated_error_threshold


def test_sign_change_halves_the_accumulation():
    """A reversed error does not restart the accumulation from zero."""
    algo = make(LEVEL_SLOW)
    algo.should_be_turned_off("heat", 20.0, 19.0, 0.0, at(0))
    algo.should_be_turned_off("heat", 20.0, 18.0, 0.0, at(2))
    positive = algo.accumulated_error
    assert positive > 0
    algo.should_be_turned_off("heat", 20.0, 22.0, 0.0, at(4))
    assert algo.accumulated_error < positive


def test_cooling_stops_on_a_negative_overshoot():
    """The cooling branch mirrors the heating one."""
    algo = make(LEVEL_FAST)
    for minutes in range(0, 30, 1):
        decision = algo.should_be_turned_off("cool", 20.0, 19.0, -0.1, at(minutes))
    assert decision is True


def test_switch_delay_blocks_an_immediate_reversal():
    """Two decisions cannot follow each other within `dt_min`."""
    algo = make(LEVEL_VERY_SLOW)
    minutes = 0
    while not algo.should_be_turned_off("heat", 20.0, 22.0, 0.1, at(minutes)):
        minutes += 1
        assert minutes < 200, "the stop was never detected"
    assert algo.last_switch_date == at(minutes)
    # Immediately afterwards the opposite condition holds but the delay blocks it.
    assert algo.should_be_turned_off("heat", 25.0, 15.0, -0.1, at(minutes + 1)) is True


def test_reset_switch_delay_allows_an_immediate_decision():
    algo = make(LEVEL_VERY_SLOW)
    for minutes in range(0, 90, 1):
        algo.should_be_turned_off("heat", 20.0, 22.0, 0.1, at(minutes))
    algo.reset_switch_delay()
    algo.should_be_turned_off("heat", 25.0, 15.0, -0.1, at(91))
    assert algo.should_be_turned_off("heat", 25.0, 15.0, -0.1, at(92)) is False


def test_set_level_resets_the_accumulation():
    algo = make(LEVEL_SLOW)
    algo.should_be_turned_off("heat", 20.0, 19.0, 0.0, at(0))
    assert algo.accumulated_error != 0
    algo.set_level(LEVEL_FAST)
    assert algo.accumulated_error == 0
    assert algo.dt_min == DT_MIN[LEVEL_FAST]


def test_restore_rebuilds_the_published_state():
    algo = make(LEVEL_SLOW)
    algo.restore(-3.5, at(10))
    assert algo.accumulated_error == -3.5
    assert algo.last_switch_date == at(10)


def test_restore_without_values_is_a_noop():
    algo = make(LEVEL_SLOW)
    algo.restore(None, None)
    assert algo.accumulated_error == 0
    assert algo.last_switch_date is None


def test_full_cycle_at_120_seconds_accumulates_once():
    """Task 3.3: two refreshes 120 s apart count exactly one cycle.

    ``CYCLE_SEC`` is 120 s, so a measurement taken two minutes after the previous
    one weights the error by exactly one cycle, and a second refresh taken on the
    same clock adds nothing.
    """
    algo = make(LEVEL_SLOW)
    algo.should_be_turned_off("heat", 20.0, 19.0, 0.0, at(0))
    before = algo.accumulated_error

    # 1 °C of error, weighted by 120 s / 120 s = 1 cycle.
    algo.should_be_turned_off("heat", 20.0, 19.0, 0.0, at(2))
    assert algo.accumulated_error - before == pytest.approx(1.0)

    # The second refresh of the same cycle adds nothing.
    after_one_cycle = algo.accumulated_error
    algo.should_be_turned_off("heat", 20.0, 19.0, 0.0, at(2))
    assert algo.accumulated_error == pytest.approx(after_one_cycle)
