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
    CONF_ERROR_THRESHOLD,
    CONF_DT_MIN,
    DEFAULT_ERROR_THRESHOLD,
    DEFAULT_DT_MIN,
    LEVEL_FAST,
    LEVEL_MEDIUM,
    LEVEL_PERSONNALISE,
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


def test_resolve_params_removed_none_literal_fonds_to_slow():
    """The removed "none" literal no longer resolves to a real level."""
    params = resolve_params("auto_start_stop_none")
    assert params.dt_min == DT_MIN[LEVEL_SLOW]
    assert params.error_threshold == ERROR_THRESHOLD[LEVEL_SLOW]


@pytest.mark.parametrize("level", ["", "auto_start_stop_bogus"])
def test_resolve_params_unknown_level_falls_back(level):
    """An unknown level must never break the control cycle."""
    params = resolve_params(level)
    assert params.dt_min == DT_MIN[LEVEL_SLOW]
    assert params.error_threshold == ERROR_THRESHOLD[LEVEL_SLOW]


def test_resolve_params_personnalise_reads_config():
    """personnalise resolves the custom per-instance values."""
    params = resolve_params(
        LEVEL_PERSONNALISE, {CONF_DT_MIN: 45, CONF_ERROR_THRESHOLD: 25}
    )
    assert params.dt_min == 45
    assert params.error_threshold == 25


@pytest.mark.parametrize("config", [None, {}])
def test_resolve_params_personnalise_falls_back_to_slow(config):
    """Absent custom values fall back to the SLOW-derived defaults."""
    params = resolve_params(LEVEL_PERSONNALISE, config)
    assert params.dt_min == DEFAULT_DT_MIN
    assert params.error_threshold == DEFAULT_ERROR_THRESHOLD


@pytest.mark.parametrize(
    ("config", "dt_min"),
    [
        # Non-numeric, null, NaN and inf must all be ignored.
        ({CONF_DT_MIN: "forty"}, DEFAULT_DT_MIN),
        ({CONF_DT_MIN: None}, DEFAULT_DT_MIN),
        ({CONF_DT_MIN: float("nan")}, DEFAULT_DT_MIN),
        ({CONF_DT_MIN: float("inf")}, DEFAULT_DT_MIN),
        # Unknown level still resolves the custom values to the fallback.
    ],
)
def test_resolve_params_personnalise_ignores_invalid_values(config, dt_min):
    params = resolve_params(LEVEL_PERSONNALISE, config)
    assert params.dt_min == dt_min


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


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


def test_reset_switch_delay_keeps_the_accumulation():
    """An explicit target change clears the delay but not the observation.

    ``reset_switch_delay`` is the deliberate user-change hook (preset or target
    temperature). It must keep the accumulated deviation intact: D11 removes the
    reset from :meth:`set_params`, and the delay reset is a separate decision.
    """
    algo = make(LEVEL_SLOW)
    algo.should_be_turned_off("heat", 20.0, 19.0, 0.0, at(0))
    algo.should_be_turned_off("heat", 20.0, 19.0, 0.0, at(2))
    accumulated = algo.accumulated_error
    assert accumulated != 0
    algo.reset_switch_delay()
    assert algo.accumulated_error == accumulated
    assert algo.last_switch_date is None


def test_set_level_preserves_the_accumulation():
    """D11: changing the level no longer discards the observed deviation."""
    algo = make(LEVEL_SLOW)
    algo.should_be_turned_off("heat", 20.0, 19.0, 0.0, at(0))
    algo.should_be_turned_off("heat", 20.0, 19.0, 0.0, at(2))
    accumulated = algo.accumulated_error
    assert accumulated != 0
    algo.set_level(LEVEL_FAST)
    assert algo.accumulated_error == accumulated
    assert algo.dt_min == DT_MIN[LEVEL_FAST]


def test_set_params_personnalise_applies_custom_values():
    algo = make(LEVEL_PERSONNALISE)
    algo.set_params(LEVEL_PERSONNALISE, {CONF_DT_MIN: 45, CONF_ERROR_THRESHOLD: 25})
    assert algo.level == LEVEL_PERSONNALISE
    assert algo.dt_min == 45
    assert algo.accumulated_error_threshold == 25


def test_set_params_does_not_reset_the_accumulation():
    """D11: setting parameters never touches the accumulated deviation."""
    algo = make(LEVEL_PERSONNALISE)
    algo.set_params(LEVEL_PERSONNALISE, {CONF_DT_MIN: 45, CONF_ERROR_THRESHOLD: 25})
    algo.should_be_turned_off("heat", 20.0, 19.0, 0.0, at(0))
    algo.should_be_turned_off("heat", 20.0, 19.0, 0.0, at(2))
    before = algo.accumulated_error
    assert before != 0
    algo.set_params(LEVEL_PERSONNALISE, {CONF_DT_MIN: 60, CONF_ERROR_THRESHOLD: 30})
    assert algo.accumulated_error == before
    assert algo.dt_min == 60
    assert algo.accumulated_error_threshold == 30


def test_set_params_does_not_touch_the_last_switch_date():
    """5.2c: the switch delay is measured from the last real decision."""
    algo = make(LEVEL_VERY_SLOW)
    minutes = 0
    while not algo.should_be_turned_off("heat", 20.0, 22.0, 0.1, at(minutes)):
        minutes += 1
        assert minutes < 200, "the stop was never detected"
    switch_date = algo.last_switch_date
    assert switch_date == at(minutes)
    algo.set_level(LEVEL_FAST)
    assert algo.last_switch_date == switch_date


def test_faster_level_can_detect_on_the_next_cycle():
    """5.2c: a saturated accumulation against a lower threshold detects at once.

    VERY_SLOW has threshold 20; FAST has threshold 2. With the deviation
    saturated at 20 and the time since the last decision already above the new
    ``dt_min``, the stop is detected on the next cycle.
    """
    algo = make(LEVEL_VERY_SLOW)
    # Saturate the accumulation at 20 while heating overshoots.
    for minutes in range(0, 100, 1):
        algo.should_be_turned_off("heat", 30.0, 10.0, 0.0, at(minutes))
    for minutes in range(100, 200, 1):
        # Keep accumulating with a sign that saturates negatively.
        algo.should_be_turned_off("heat", 20.0, 40.0, 0.0, at(minutes))
    assert algo.accumulated_error <= -algo.accumulated_error_threshold

    # The user selects FAST: the threshold drops to 2, below the saturation.
    algo.set_level(LEVEL_FAST)
    assert algo.accumulated_error_threshold == ERROR_THRESHOLD[LEVEL_FAST]
    # A decided stop on the very next measurement (already beyond dt_min).
    detected = algo.should_be_turned_off("heat", 20.0, 40.0, 0.0, at(200))
    assert detected is True


def test_slower_level_cannot_detect_on_the_next_cycle():
    """5.2c: raising the threshold puts the accumulation back under it."""
    algo = make(LEVEL_FAST)
    # Saturate the accumulation at 2 while cooling overshoots upward.
    for minutes in range(0, 100, 1):
        algo.should_be_turned_off("heat", 20.0, 40.0, 0.0, at(minutes))
    saturated = algo.accumulated_error
    assert saturated <= -ERROR_THRESHOLD[LEVEL_FAST]

    # The user selects VERY_SLOW (threshold 20): the accumulation is now under
    # the new threshold, so no stop can be detected on that cycle alone.
    algo.set_level(LEVEL_VERY_SLOW)
    assert algo.accumulated_error_threshold == ERROR_THRESHOLD[LEVEL_VERY_SLOW]
    assert algo.accumulated_error == saturated
    assert abs(algo.accumulated_error) < algo.accumulated_error_threshold


def test_accumulation_is_bounded_with_the_current_threshold():
    """5.2d: the bound follows the current threshold, never a scaled one."""
    algo = make(LEVEL_VERY_SLOW)
    for minutes in range(0, 60, 1):
        algo.should_be_turned_off("heat", 30.0, 10.0, 0.0, at(minutes))
    assert abs(algo.accumulated_error) == algo.accumulated_error_threshold

    # Lowering the threshold bounds the existing accumulation to the new value.
    algo.set_level(LEVEL_FAST)
    algo.should_be_turned_off("heat", 30.0, 10.0, 0.0, at(60))
    assert abs(algo.accumulated_error) == ERROR_THRESHOLD[LEVEL_FAST]


def test_raising_the_threshold_does_not_inflate_the_accumulation():
    """5.2d: the accumulation keeps its magnitude, never scaled up."""
    algo = make(LEVEL_FAST)
    for minutes in range(0, 30, 1):
        algo.should_be_turned_off("heat", 20.0, 30.0, 0.0, at(minutes))
    magnitude = abs(algo.accumulated_error)
    assert magnitude == ERROR_THRESHOLD[LEVEL_FAST]

    algo.set_level(LEVEL_VERY_SLOW)
    algo.should_be_turned_off("heat", 20.0, 20.5, 0.0, at(30))
    assert abs(algo.accumulated_error) < ERROR_THRESHOLD[LEVEL_VERY_SLOW]
