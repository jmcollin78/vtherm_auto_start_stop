"""Vocabulary shared with the core feature (tasks 4.5, 2.6, 2.7)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from custom_components.vtherm_auto_start_stop import const as plugin_const


def test_off_reason_matches_the_core_vocabulary():
    """The plugin relies on the core arbitration's own off reason.

    The reason is set by ``versatile_thermostat`` when it applies the stop the
    plugin asks for; the plugin therefore reproduces the value so the attribute
    section, the card and the summaries agree. Nothing is invented here: the
    constant is the core literal.
    """
    assert plugin_const.HVAC_OFF_REASON_AUTO_START_STOP == "hvac_off_auto_start_stop"


def test_attribute_keys_match_the_core_feature():
    """The section is reproduced verbatim, so existing cards keep rendering."""
    assert plugin_const.MANAGER_ATTRIBUTES_KEY == "auto_start_stop_manager"
    assert plugin_const.ATTR_IS_CONFIGURED == "is_auto_start_stop_configured"
    assert plugin_const.ATTR_ENABLE == "auto_start_stop_enable"
    assert plugin_const.ATTR_LEVEL == "auto_start_stop_level"
    assert plugin_const.ATTR_DTMIN == "auto_start_stop_dtmin"
    assert plugin_const.ATTR_ACCUMULATED_ERROR == "auto_start_stop_accumulated_error"
    assert (
        plugin_const.ATTR_ACCUMULATED_ERROR_THRESHOLD
        == "auto_start_stop_accumulated_error_threshold"
    )
    assert plugin_const.ATTR_LAST_SWITCH_DATE == "auto_start_stop_last_switch_date"
    assert plugin_const.ATTR_IS_STOP_DETECTED == "is_auto_stop_detected"
    assert plugin_const.ATTR_STOP_MODE == "auto_start_stop_stop_mode"


def test_levels_and_stop_modes_match_the_core_values():
    """The migration writes these literals into the core entry, so they are fixed."""
    assert plugin_const.LEVELS == [
        "auto_start_stop_very_slow",
        "auto_start_stop_slow",
        "auto_start_stop_medium",
        "auto_start_stop_fast",
        "auto_start_stop_personnalise",
    ]
    assert plugin_const.STOP_MODES == ["off", "fan_only", "dry"]


def test_stable_manager_name():
    """The delegation resolves the manager by this exact name."""
    assert plugin_const.MANAGER_NAME == "auto_start_stop"


def test_legacy_keys():
    """The migration reads exactly these keys from the core entry."""
    assert plugin_const.LEGACY_LEVEL == "auto_start_stop_level"
    assert plugin_const.LEGACY_ENTITY_IDS == "auto_start_stop_entity_ids"
    assert plugin_const.LEGACY_THERMOSTAT_TYPE == "thermostat_type"
    assert plugin_const.LEGACY_REGULATION_MODE == "auto_regulation_mode"
    assert plugin_const.LEGACY_REGULATION_VALVE == "auto_regulation_valve"
    assert plugin_const.THERMOSTAT_TYPE_CLIMATE == "thermostat_over_climate"


@pytest.mark.parametrize(
    "filename", ["strings.json", "translations/en.json", "translations/fr.json"]
)
def test_configuration_translations_match_direct_flow(filename):
    """The flow only seeds: parameters are set on the entities."""
    root = Path(plugin_const.__file__).parent
    content = json.loads((root / filename).read_text(encoding="utf-8"))
    steps = content["config"]["step"]
    assert set(steps) == {"global", "thermostat", "thermostat_options"}
    assert set(content["config"]["abort"]) == {"already_configured"}
    # The flow no longer carries a detection parameter: those live on the
    # number and select entities.
    for step in ("global", "thermostat_options"):
        assert set(steps[step]["data"]) == {
            plugin_const.CONF_STOP_MODE,
            plugin_const.CONF_ENABLED,
        }
    assert steps["global"]["data"]["enabled"]
    init_data = content["options"]["step"]["init"]["data"]
    assert set(init_data) == {plugin_const.CONF_STOP_MODE, plugin_const.CONF_ENABLED}
    assert init_data["enabled"]
    initial_label = steps["global"]["data"]["enabled"].lower()
    assert "initial" in initial_label
    assert "initial" in steps["global"]["data"][plugin_const.CONF_STOP_MODE].lower()


@pytest.mark.parametrize(
    "filename", ["strings.json", "translations/en.json", "translations/fr.json"]
)
def test_independent_control_translations_match_entity_options(filename):
    """Every one of the five controls has its own label."""
    root = Path(plugin_const.__file__).parent
    content = json.loads((root / filename).read_text(encoding="utf-8"))
    assert set(content["entity"]) == {"switch", "select", "number"}

    switch = content["entity"]["switch"][plugin_const.ENTITY_ENABLE_SUFFIX]
    assert switch["name"]

    select = content["entity"]["select"][plugin_const.ENTITY_STOP_MODE_SUFFIX]
    assert select["name"]
    assert set(select["state"]) == set(plugin_const.STOP_MODES)
    assert all(select["state"].values())

    level = content["entity"]["select"][plugin_const.ENTITY_LEVEL_SUFFIX]
    assert level["name"]
    assert set(level["state"]) == set(plugin_const.LEVELS)
    assert all(level["state"].values())

    number = content["entity"]["number"]
    assert set(number) == {
        plugin_const.ENTITY_DT_MIN_SUFFIX,
        plugin_const.ENTITY_ERROR_THRESHOLD_SUFFIX,
    }
    assert all(entry["name"] for entry in number.values())

    assert set(content["selector"][plugin_const.CONF_STOP_MODE]["options"]) == set(
        plugin_const.STOP_MODES
    )
    exceptions = content["exceptions"]
    assert "{option}" in exceptions["invalid_auto_start_stop_option"]["message"]
    assert exceptions["missing_configuration"]["message"]
    assert "{entity_id}" in exceptions["entity_id_conflict"]["message"]
    bound = exceptions["invalid_auto_start_stop_bound"]["message"]
    for placeholder in ("{entity_id}", "{min}", "{max}", "{value}"):
        assert placeholder in bound
    assert "{level}" in exceptions["level_already_named"]["message"]


def test_every_constant_is_referenced():
    """Task 1.2: no constant is declared and left unused.

    A constant that nothing reads is a leftover of an earlier design: it invites
    a future reader to trust a vocabulary the plugin does not actually use.
    """
    from pathlib import Path

    import custom_components.vtherm_auto_start_stop as package

    root = Path(package.__file__).parent
    const_source = (root / "const.py").read_text(encoding="utf-8")
    import re

    names = set(
        re.findall(r"^([A-Z][A-Z0-9_]*)\s*(?::[^=]+)?=", const_source, re.MULTILINE)
    )
    assert names, "no constant found in const.py"

    sources = list(root.glob("*.py"))
    concatenated = "\n".join(
        path.read_text(encoding="utf-8") for path in sources if path.name != "const.py"
    )

    unused = sorted(
        name for name in names if not re.search(rf"\b{name}\b", concatenated)
    )
    assert unused == [], f"unused constants: {unused}"
