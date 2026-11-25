"""Parameter inheritance and initialization-only control defaults."""

from __future__ import annotations

import pytest

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
    STOP_MODE_DRY,
    STOP_MODE_FAN_ONLY,
)
from custom_components.vtherm_auto_start_stop.models import (
    default_config,
    effective_config,
    has_dedicated_instance,
    initial_control_defaults,
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
            },
        ),
        # Dedicated only: the defaults are completed by the dedicated layer.
        (
            {"ded": dedicated_entry()},
            {
                CONF_LEVEL: LEVEL_FAST,
            },
        ),
        # Both: the dedicated layer wins on every key it defines.
        (
            {"global": global_entry(), "ded": dedicated_entry()},
            {
                CONF_LEVEL: LEVEL_FAST,
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
    assert config == {CONF_LEVEL: LEVEL_FAST}
    assert initial_control_defaults(entries) == {
        CONF_STOP_MODE: STOP_MODE_FAN_ONLY,
        CONF_ENABLED: enabled,
    }


@pytest.mark.parametrize("global_enabled", [False, True])
@pytest.mark.parametrize("dedicated_enabled", [False, True])
def test_legacy_controls_are_not_parameter_overrides(global_enabled, dedicated_enabled):
    entries = {
        "global": global_entry(enabled=global_enabled),
        "ded": dedicated_entry(enabled=dedicated_enabled),
    }
    config = effective_config(entries, VT_A)
    assert config is not None
    assert config == {CONF_LEVEL: LEVEL_FAST}
    assert initial_control_defaults(entries)[CONF_ENABLED] is global_enabled
    assert effective_config(entries, VT_B) == {CONF_LEVEL: LEVEL_MEDIUM}


@pytest.mark.parametrize("enabled", [False, True])
def test_dedicated_configuration_works_without_global(enabled):
    entries = {"ded": dedicated_entry(enabled=enabled)}
    config = effective_config(entries, VT_A)
    assert config is not None
    assert config == {CONF_LEVEL: LEVEL_FAST}
    assert initial_control_defaults(entries) == {
        CONF_ENABLED: default_config()[CONF_ENABLED],
        CONF_STOP_MODE: "off",
    }
    assert effective_config(entries, VT_B) is None


@pytest.mark.parametrize(
    "entries",
    [{"global": {}}, {"ded": {CONF_VTHERM_UNIQUE_ID: VT_A}}],
)
def test_entry_without_parameters_uses_plugin_defaults(entries):
    assert effective_config(entries, VT_A) == {CONF_LEVEL: default_config()[CONF_LEVEL]}


@pytest.mark.parametrize("enabled", [False, True])
def test_removing_dedicated_restores_global(enabled):
    entries = {
        "global": global_entry(enabled=enabled),
        "ded": dedicated_entry(enabled=not enabled),
    }
    entries.pop("ded")
    assert effective_config(entries, VT_A) == {CONF_LEVEL: LEVEL_MEDIUM}


def test_removing_global_keeps_only_dedicated_configuration():
    entries = {"global": global_entry(), "ded": dedicated_entry(enabled=False)}
    entries.pop("global")
    config = effective_config(entries, VT_A)
    assert config[CONF_LEVEL] == LEVEL_FAST
    assert config == {CONF_LEVEL: LEVEL_FAST}
    assert effective_config(entries, VT_B) is None


def test_custom_parameters_cascade_like_other_parameters():
    """Custom values flow through the same global/dedicated cascade."""
    # Global carries the custom pair at personnalise.
    global_custom = {**global_entry(level=LEVEL_PERSONNALISE), CONF_DT_MIN: 60}
    # Dedicated carries a narrower minimum duration: it must win.
    dedicated = {
        CONF_VTHERM_UNIQUE_ID: VT_A,
        CONF_LEVEL: LEVEL_PERSONNALISE,
        CONF_DT_MIN: 20,
        CONF_ERROR_THRESHOLD: 25,
    }
    config = effective_config({"global": global_custom, "ded": dedicated}, VT_A)
    assert config[CONF_DT_MIN] == 20
    assert config[CONF_ERROR_THRESHOLD] == 25


def test_dedicated_inherits_missing_custom_key_from_global():
    global_custom = {**global_entry(level=LEVEL_PERSONNALISE), CONF_DT_MIN: 60}
    dedicated = {
        CONF_VTHERM_UNIQUE_ID: VT_A,
        CONF_LEVEL: LEVEL_PERSONNALISE,
        # No CONF_DT_MIN: it inherits the global value.
    }
    config = effective_config({"global": global_custom, "ded": dedicated}, VT_A)
    assert config[CONF_DT_MIN] == 60


def test_custom_keys_flow_only_when_present():
    """Layers without custom values leave the base dict untouched."""
    entries = {"global": global_entry(level=LEVEL_FAST), "ded": dedicated_entry()}
    assert effective_config(entries, VT_A) == {CONF_LEVEL: LEVEL_FAST}


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
    assert legacy_level({CONF_LEVEL: "auto_start_stop_none"}) is None


def test_legacy_level_ignores_unknown_and_missing():
    assert legacy_level({CONF_LEVEL: "unknown"}) is None
    assert legacy_level({}) is None
    assert legacy_level(None) is None
