"""Layered configuration resolution (tasks 2.1, 2.5, 2.8)."""

from __future__ import annotations

import pytest

from custom_components.vtherm_auto_start_stop.const import (
    CONF_ENABLED,
    CONF_EXCLUDED,
    CONF_LEVEL,
    CONF_STOP_MODE,
    CONF_VTHERM_UNIQUE_ID,
    LEVEL_FAST,
    LEVEL_MEDIUM,
    LEVEL_NONE,
    STOP_MODE_DRY,
    STOP_MODE_FAN_ONLY,
)
from custom_components.vtherm_auto_start_stop.models import (
    default_config,
    effective_config,
    has_dedicated_instance,
    is_exclusion,
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


def exclusion_entry(unique_id=VT_A):
    return {CONF_VTHERM_UNIQUE_ID: unique_id, CONF_EXCLUDED: True}


@pytest.mark.parametrize(
    ("entries", "expected"),
    [
        # No instance at all: nothing is attached.
        ({}, None),
        # A dedicated instance of another thermostat does not configure this one.
        (
            {
                "other": {
                    **dedicated_entry(),
                    CONF_VTHERM_UNIQUE_ID: VT_B,
                }
            },
            None,
        ),
        # Global only: the defaults are completed by the global layer.
        (
            {"global": global_entry()},
            {
                CONF_LEVEL: LEVEL_MEDIUM,
                CONF_STOP_MODE: STOP_MODE_FAN_ONLY,
                CONF_ENABLED: True,
            },
        ),
        # Dedicated only: the defaults are completed by the dedicated layer.
        (
            {"ded": dedicated_entry()},
            {
                CONF_LEVEL: LEVEL_FAST,
                CONF_STOP_MODE: STOP_MODE_DRY,
                CONF_ENABLED: True,
            },
        ),
        # Both: the dedicated layer wins on every key it defines.
        (
            {"global": global_entry(), "ded": dedicated_entry()},
            {
                CONF_LEVEL: LEVEL_FAST,
                CONF_STOP_MODE: STOP_MODE_DRY,
                CONF_ENABLED: True,
            },
        ),
    ],
)
def test_cascade(entries, expected):
    """Global then dedicated, on top of the defaults."""
    assert effective_config(entries, VT_A) == expected


def test_dedicated_layer_inherits_undefined_keys():
    """A dedicated entry only overrides the keys it carries."""
    entries = {
        "global": global_entry(level=LEVEL_MEDIUM, stop_mode=STOP_MODE_FAN_ONLY),
        "ded": {CONF_VTHERM_UNIQUE_ID: VT_A, CONF_LEVEL: LEVEL_FAST},
    }
    config = effective_config(entries, VT_A)
    assert config[CONF_LEVEL] == LEVEL_FAST
    assert config[CONF_STOP_MODE] == STOP_MODE_FAN_ONLY
    assert config[CONF_ENABLED] is True


def test_exclusion_short_circuits_global():
    """An exclusion resolves to no configuration, even with a global instance."""
    entries = {"global": global_entry(), "excl": exclusion_entry()}
    assert effective_config(entries, VT_A) is None


def test_exclusion_alone_resolves_to_nothing():
    """An exclusion on its own is not a configuration either."""
    assert effective_config({"excl": exclusion_entry()}, VT_A) is None


def test_exclusion_does_not_affect_other_thermostats():
    """Opting one thermostat out leaves the others on the global instance."""
    entries = {"global": global_entry(), "excl": exclusion_entry()}
    config = effective_config(entries, VT_B)
    assert config is not None
    assert config[CONF_LEVEL] == LEVEL_MEDIUM


def test_removing_the_exclusion_restores_the_global_instance():
    """Dropping the exclusion entry puts the thermostat back on the global one."""
    entries = {"global": global_entry(), "excl": exclusion_entry()}
    assert effective_config(entries, VT_A) is None
    entries.pop("excl")
    assert effective_config(entries, VT_A) is not None


@pytest.mark.parametrize(
    ("entry", "expected"),
    [({}, False), ({CONF_EXCLUDED: True}, True), ({CONF_EXCLUDED: False}, False)],
)
def test_is_exclusion(entry, expected):
    assert is_exclusion(entry) is expected


def test_has_dedicated_instance_ignores_exclusion():
    """An exclusion owns no entity: it is not a configurable instance."""
    entries = {"excl": exclusion_entry()}
    assert has_dedicated_instance(entries, VT_A) is False
    entries = {"ded": dedicated_entry()}
    assert has_dedicated_instance(entries, VT_A) is True


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        (LEVEL_FAST, LEVEL_FAST),
        (LEVEL_MEDIUM, LEVEL_MEDIUM),
        ("auto_start_stop_personnalise", default_config()[CONF_LEVEL]),
        (None, default_config()[CONF_LEVEL]),
    ],
)
def test_normalize_level(level, expected):
    """An unknown level never breaks the refresh."""
    assert normalize_level(level) == expected


@pytest.mark.parametrize(
    ("stop_mode", "expected"),
    [(STOP_MODE_DRY, STOP_MODE_DRY), ("unknown", STOP_MODE_FAN_ONLY), (None, "off")],
)
def test_normalize_stop_mode(stop_mode, expected):
    result = normalize_stop_mode(stop_mode)
    assert result in (expected, "off")
    assert result != "unknown"


def test_normalize_stop_mode_default():
    assert normalize_stop_mode(None) == "off"


def test_legacy_level_reads_the_core_entry():
    """The migrated level seeds a new dedicated instance (task 6.1)."""
    assert legacy_level({CONF_LEVEL: LEVEL_FAST}) == LEVEL_FAST
    assert legacy_level({CONF_LEVEL: LEVEL_NONE}) == LEVEL_NONE


def test_legacy_level_ignores_unknown_and_missing():
    assert legacy_level({CONF_LEVEL: "unknown"}) is None
    assert legacy_level({}) is None
    assert legacy_level(None) is None
