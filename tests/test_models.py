"""Layered configuration resolution and dedicated enable overrides."""

from __future__ import annotations

import pytest

from custom_components.vtherm_auto_start_stop.const import (
    CONF_ENABLED,
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


@pytest.mark.parametrize("enabled", [False, True])
def test_dedicated_layer_inherits_undefined_keys(enabled):
    """A dedicated entry only overrides the keys it carries."""
    entries = {
        "global": global_entry(
            level=LEVEL_MEDIUM, stop_mode=STOP_MODE_FAN_ONLY, enabled=enabled
        ),
        "ded": {CONF_VTHERM_UNIQUE_ID: VT_A, CONF_LEVEL: LEVEL_FAST},
    }
    config = effective_config(entries, VT_A)
    assert config[CONF_LEVEL] == LEVEL_FAST
    assert config[CONF_STOP_MODE] == STOP_MODE_FAN_ONLY
    assert config[CONF_ENABLED] is enabled


@pytest.mark.parametrize("global_enabled", [False, True])
@pytest.mark.parametrize("dedicated_enabled", [False, True])
def test_dedicated_enable_state_wins(global_enabled, dedicated_enabled):
    entries = {
        "global": global_entry(enabled=global_enabled),
        "ded": dedicated_entry(enabled=dedicated_enabled),
    }
    config = effective_config(entries, VT_A)
    assert config is not None
    assert config[CONF_ENABLED] is dedicated_enabled
    assert effective_config(entries, VT_B)[CONF_ENABLED] is global_enabled


@pytest.mark.parametrize("enabled", [False, True])
def test_dedicated_configuration_works_without_global(enabled):
    entries = {"ded": dedicated_entry(enabled=enabled)}
    config = effective_config(entries, VT_A)
    assert config is not None
    assert config[CONF_ENABLED] is enabled
    assert effective_config(entries, VT_B) is None


@pytest.mark.parametrize(
    "entries",
    [{"global": {}}, {"ded": {CONF_VTHERM_UNIQUE_ID: VT_A}}],
)
def test_entry_without_parameters_uses_plugin_defaults(entries):
    assert effective_config(entries, VT_A) == default_config()


@pytest.mark.parametrize("enabled", [False, True])
def test_removing_dedicated_restores_global(enabled):
    entries = {
        "global": global_entry(enabled=enabled),
        "ded": dedicated_entry(enabled=not enabled),
    }
    entries.pop("ded")
    assert effective_config(entries, VT_A) == global_entry(enabled=enabled)


def test_removing_global_keeps_only_dedicated_configuration():
    entries = {"global": global_entry(), "ded": dedicated_entry(enabled=False)}
    entries.pop("global")
    config = effective_config(entries, VT_A)
    assert config[CONF_LEVEL] == LEVEL_FAST
    assert config[CONF_ENABLED] is False
    assert effective_config(entries, VT_B) is None


@pytest.mark.parametrize(
    "entries",
    [{}, {"global": global_entry()}, {"other": {CONF_VTHERM_UNIQUE_ID: VT_B}}],
)
def test_has_no_dedicated_instance(entries):
    assert has_dedicated_instance(entries, VT_A) is False


@pytest.mark.parametrize("enabled", [False, True])
def test_has_dedicated_instance_even_when_disabled(enabled):
    entries = {"ded": dedicated_entry(enabled=enabled)}
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
