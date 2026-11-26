"""Level derivation, coverage gate and initialization-only control seeds."""

from __future__ import annotations

import pytest

from custom_components.vtherm_auto_start_stop.algorithm import DT_MIN, ERROR_THRESHOLD
from custom_components.vtherm_auto_start_stop.const import (
    CONF_ENABLED,
    CONF_ERROR_THRESHOLD,
    CONF_LEVEL,
    CONF_DT_MIN,
    CONF_STOP_MODE,
    CONF_VTHERM_UNIQUE_ID,
    LEVEL_FAST,
    LEVEL_MEDIUM,
    LEVEL_PERSONNALISE,
    LEVEL_SLOW,
    LEVEL_VERY_SLOW,
    STOP_MODE_DRY,
    STOP_MODE_FAN_ONLY,
    STOP_MODE_OFF,
)
from custom_components.vtherm_auto_start_stop.models import (
    NAMED_LEVELS,
    default_config,
    derive_level,
    has_dedicated_instance,
    initial_control_defaults,
    is_covered,
    legacy_level,
    normalize_level,
    normalize_stop_mode,
)

VT_A = "vtherm-a"
VT_B = "vtherm-b"


def global_entry(level=LEVEL_MEDIUM, stop_mode=STOP_MODE_FAN_ONLY, enabled=True):
    return {CONF_LEVEL: level, CONF_STOP_MODE: stop_mode, CONF_ENABLED: enabled}


def dedicated_entry(level=LEVEL_FAST, stop_mode=STOP_MODE_DRY, enabled=True):
    return {
        CONF_VTHERM_UNIQUE_ID: VT_A,
        CONF_LEVEL: level,
        CONF_STOP_MODE: stop_mode,
        CONF_ENABLED: enabled,
    }


# ---------------------------------------------------------------------------
# derive_level (task 1.1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "level", [LEVEL_VERY_SLOW, LEVEL_SLOW, LEVEL_MEDIUM, LEVEL_FAST]
)
def test_derive_level_recognises_every_named_pair(level):
    """Each named level's own pair reads back as that level."""
    assert derive_level(DT_MIN[level], ERROR_THRESHOLD[level]) == level


@pytest.mark.parametrize(
    "level", [LEVEL_VERY_SLOW, LEVEL_SLOW, LEVEL_MEDIUM, LEVEL_FAST]
)
def test_derive_level_tolerates_float_rendering(level):
    """A ``number`` entity renders ``30`` as ``30.0``; the level must still match."""
    assert derive_level(float(DT_MIN[level]), float(ERROR_THRESHOLD[level])) == level


def test_derive_level_arbitrary_pair_is_personnalise():
    assert derive_level(17, 7) == LEVEL_PERSONNALISE


def test_derive_level_mixed_pair_is_personnalise():
    """A pair mixing two levels matches neither."""
    assert derive_level(DT_MIN[LEVEL_SLOW], ERROR_THRESHOLD[LEVEL_FAST]) == (
        LEVEL_PERSONNALISE
    )


def test_derive_level_slow_defaults_pair_is_slow():
    """The plugin default pair (30 / 10) is the SLOW level, not a custom pair."""
    assert derive_level(30.0, 10.0) == LEVEL_SLOW


@pytest.mark.parametrize("pair", [(None, 10), ("thirty", 10), (30, None), ({}, [])])
def test_derive_level_ignores_non_numeric_values(pair):
    assert derive_level(*pair) == LEVEL_PERSONNALISE


def test_named_levels_exclude_personnalise():
    assert LEVEL_PERSONNALISE not in NAMED_LEVELS
    assert set(NAMED_LEVELS) == set(DT_MIN)


# ---------------------------------------------------------------------------
# is_covered (task 1.2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("entries", "expected"),
    [
        ({}, False),
        # A dedicated instance of another thermostat does not cover this one.
        ({"other": {**dedicated_entry(), CONF_VTHERM_UNIQUE_ID: VT_B}}, False),
        ({"global": global_entry()}, True),
        ({"ded": dedicated_entry()}, True),
        ({"global": global_entry(), "ded": dedicated_entry()}, True),
    ],
)
def test_is_covered(entries, expected):
    assert is_covered(entries, VT_A) is expected


@pytest.mark.parametrize("enabled", [False, True])
def test_is_covered_ignores_the_enable_state(enabled):
    """A disabled instance still covers its thermostat."""
    assert is_covered({"global": global_entry(enabled=enabled)}, VT_A) is True


# ---------------------------------------------------------------------------
# initial_control_defaults (task 1.3)
# ---------------------------------------------------------------------------


def test_defaults_without_any_entry():
    values = initial_control_defaults({}, VT_A)
    assert values[CONF_ENABLED] is True
    assert values[CONF_STOP_MODE] == STOP_MODE_OFF
    assert values[CONF_LEVEL] == LEVEL_SLOW
    assert values[CONF_DT_MIN] == 30
    assert values[CONF_ERROR_THRESHOLD] == 10


@pytest.mark.parametrize("enabled", [False, True])
def test_global_entry_seeds_the_five_controls(enabled):
    values = initial_control_defaults({"global": global_entry(enabled=enabled)}, VT_A)
    assert values[CONF_ENABLED] is enabled
    assert values[CONF_STOP_MODE] == STOP_MODE_FAN_ONLY
    # MEDIUM: its table pair is seeded, so the level and its values agree.
    assert values[CONF_LEVEL] == LEVEL_MEDIUM
    assert values[CONF_DT_MIN] == DT_MIN[LEVEL_MEDIUM]
    assert values[CONF_ERROR_THRESHOLD] == ERROR_THRESHOLD[LEVEL_MEDIUM]


def test_dedicated_entry_wins_over_the_global_one():
    entries = {"global": global_entry(level=LEVEL_MEDIUM), "ded": dedicated_entry()}
    values = initial_control_defaults(entries, VT_A)
    assert values[CONF_LEVEL] == LEVEL_FAST
    assert values[CONF_DT_MIN] == DT_MIN[LEVEL_FAST]
    assert values[CONF_STOP_MODE] == STOP_MODE_DRY


def test_dedicated_entry_of_another_thermostat_does_not_seed():
    entries = {
        "global": global_entry(level=LEVEL_MEDIUM),
        "other": {**dedicated_entry(), CONF_VTHERM_UNIQUE_ID: VT_B},
    }
    values = initial_control_defaults(entries, VT_A)
    assert values[CONF_LEVEL] == LEVEL_MEDIUM


def test_named_level_ignores_a_stale_custom_pair():
    """A leftover custom key never contradicts the chosen named level."""
    entries = {"global": global_entry(level=LEVEL_FAST)}
    entries["global"].update({CONF_DT_MIN: 99, CONF_ERROR_THRESHOLD: 49})
    values = initial_control_defaults(entries, VT_A)
    assert values[CONF_LEVEL] == LEVEL_FAST
    assert values[CONF_DT_MIN] == DT_MIN[LEVEL_FAST]
    assert values[CONF_ERROR_THRESHOLD] == ERROR_THRESHOLD[LEVEL_FAST]


def test_custom_pair_seeds_its_value_and_derived_label():
    entries = {
        "ded": {
            CONF_VTHERM_UNIQUE_ID: VT_A,
            CONF_LEVEL: LEVEL_PERSONNALISE,
            CONF_DT_MIN: 45,
            CONF_ERROR_THRESHOLD: 25,
        }
    }
    values = initial_control_defaults(entries, VT_A)
    assert values[CONF_LEVEL] == LEVEL_PERSONNALISE
    assert values[CONF_DT_MIN] == 45
    assert values[CONF_ERROR_THRESHOLD] == 25


def test_custom_pair_matching_a_named_level_seeds_that_level():
    """A stored custom pair equal to a named one derives the named label."""
    entries = {
        "ded": {
            CONF_VTHERM_UNIQUE_ID: VT_A,
            CONF_LEVEL: LEVEL_PERSONNALISE,
            CONF_DT_MIN: DT_MIN[LEVEL_FAST],
            CONF_ERROR_THRESHOLD: ERROR_THRESHOLD[LEVEL_FAST],
        }
    }
    assert initial_control_defaults(entries, VT_A)[CONF_LEVEL] == LEVEL_FAST


def test_custom_level_without_values_falls_back_to_the_defaults():
    entries = {"ded": {CONF_VTHERM_UNIQUE_ID: VT_A, CONF_LEVEL: LEVEL_PERSONNALISE}}
    values = initial_control_defaults(entries, VT_A)
    assert values[CONF_DT_MIN] == 30
    assert values[CONF_ERROR_THRESHOLD] == 10
    assert values[CONF_LEVEL] == LEVEL_SLOW


def test_multiple_global_entries_produce_one_deterministic_seed():
    """One seed per control, stable whatever the registration order."""
    first = {"global-a": global_entry(level=LEVEL_FAST, enabled=False)}
    second = {**first, "global-b": global_entry(level=LEVEL_MEDIUM, enabled=True)}
    assert initial_control_defaults(first, VT_A) == initial_control_defaults(
        second, VT_A
    )


# ---------------------------------------------------------------------------
# Remaining helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        (LEVEL_FAST, LEVEL_FAST),
        (LEVEL_MEDIUM, LEVEL_MEDIUM),
        (LEVEL_PERSONNALISE, LEVEL_PERSONNALISE),
        ("auto_start_stop_none", LEVEL_SLOW),
        ("unknown", LEVEL_SLOW),
        (None, LEVEL_SLOW),
    ],
)
def test_normalize_level(level, expected):
    """An unknown level never breaks the refresh."""
    assert normalize_level(level) == expected


@pytest.mark.parametrize(
    ("stop_mode", "expected"),
    [(STOP_MODE_DRY, STOP_MODE_DRY), ("unknown", STOP_MODE_OFF), (None, "off")],
)
def test_normalize_stop_mode(stop_mode, expected):
    assert normalize_stop_mode(stop_mode) == expected


def test_has_dedicated_instance():
    assert has_dedicated_instance({"ded": dedicated_entry()}, VT_A) is True
    assert has_dedicated_instance({"global": global_entry()}, VT_A) is False


def test_default_config_is_the_slow_pair():
    values = default_config()
    assert values[CONF_LEVEL] == LEVEL_SLOW
    assert values[CONF_DT_MIN] == DT_MIN[LEVEL_SLOW]
    assert values[CONF_ERROR_THRESHOLD] == ERROR_THRESHOLD[LEVEL_SLOW]


def test_legacy_level_reads_the_core_entry():
    """The migrated level seeds a new dedicated instance (task 6.1)."""
    assert legacy_level({CONF_LEVEL: LEVEL_FAST}) == LEVEL_FAST
    assert legacy_level({CONF_LEVEL: "auto_start_stop_none"}) is None


def test_legacy_level_ignores_unknown_and_missing():
    assert legacy_level({CONF_LEVEL: "unknown"}) is None
    assert legacy_level({}) is None
    assert legacy_level(None) is None
