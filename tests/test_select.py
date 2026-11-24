"""The combined select controls activation and the automatic stop mode."""

from unittest.mock import Mock

import pytest
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vtherm_auto_start_stop.const import (
    ATTR_ACCUMULATED_ERROR,
    CONF_ENABLED,
    CONF_LEVEL,
    CONF_STOP_MODE,
    CONF_VTHERM_UNIQUE_ID,
    DATA_ENTRIES,
    DATA_MANAGERS,
    DOMAIN,
    LEVEL_FAST,
    MANAGER_ATTRIBUTES_KEY,
    SELECT_DISABLED,
    STOP_MODE_DRY,
    STOP_MODE_FAN_ONLY,
    STOP_MODE_OFF,
)
from custom_components.vtherm_auto_start_stop.manager import AutoStartStopManager
from custom_components.vtherm_auto_start_stop.select import AutoStartStopStopModeSelect
from tests.conftest import FakeThermostat


@pytest.fixture
def selection(hass, monkeypatch):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_VTHERM_UNIQUE_ID: "thermostat",
            CONF_ENABLED: False,
            CONF_LEVEL: LEVEL_FAST,
            CONF_STOP_MODE: STOP_MODE_DRY,
        },
    )
    entry.add_to_hass(hass)
    hass.data[DOMAIN] = {
        DATA_ENTRIES: {entry.entry_id: dict(entry.data)},
        DATA_MANAGERS: {},
    }
    thermostat = FakeThermostat(hass, "thermostat")
    manager = AutoStartStopManager(thermostat, hass)
    manager.post_init({})
    entity = AutoStartStopStopModeSelect(hass, entry, thermostat.unique_id)
    entity.hass = hass
    entity.entity_id = "select.auto_start_stop"
    monkeypatch.setattr(entity, "async_write_ha_state", Mock())
    return entry, thermostat, manager, entity


@pytest.mark.parametrize("fan", [False, True])
@pytest.mark.parametrize("dry", [False, True])
def test_options_contain_only_disabled_and_compatible_stop_modes(selection, fan, dry):
    _, thermostat, _, entity = selection
    thermostat.vtherm_hvac_modes = ["off", "heat", "cool", "auto"]
    expected = [SELECT_DISABLED, STOP_MODE_OFF]
    if fan:
        thermostat.vtherm_hvac_modes.append(STOP_MODE_FAN_ONLY)
        expected.append(STOP_MODE_FAN_ONLY)
    if dry:
        thermostat.vtherm_hvac_modes.append(STOP_MODE_DRY)
        expected.append(STOP_MODE_DRY)
    assert entity.options == expected


@pytest.mark.parametrize("enabled", [False, True])
def test_current_option_projects_enable_state(selection, enabled):
    _, _, manager, entity = selection
    manager.restore_entity_state(enabled, STOP_MODE_DRY)
    assert entity.current_option == (STOP_MODE_DRY if enabled else SELECT_DISABLED)


def test_unavailable_select_uses_saved_configuration(selection, hass):
    _, _, _, entity = selection
    hass.data[DOMAIN][DATA_MANAGERS].clear()
    assert entity.available is False
    assert entity.current_option == SELECT_DISABLED


async def test_disabled_preserves_mode_and_releases_a_detected_stop(selection, hass):
    entry, thermostat, manager, entity = selection
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_ENABLED: True}
    )
    manager.restore_entity_state(True, STOP_MODE_DRY)
    manager._is_stop_detected = True
    manager._algorithm.restore(-1.25, None)

    await entity.async_select_option(SELECT_DISABLED)

    assert manager.enabled is False
    assert manager.is_detected is False
    assert manager.stop_mode == STOP_MODE_DRY
    assert entry.options[CONF_ENABLED] is False
    assert entry.options[CONF_STOP_MODE] == STOP_MODE_DRY
    assert entity.current_option == SELECT_DISABLED
    assert thermostat.refresh_requests == 1
    for _ in range(10):
        thermostat.advance(1)
        assert await manager.refresh_state() is False
    attributes = {}
    manager.add_custom_attributes(attributes)
    assert attributes[MANAGER_ATTRIBUTES_KEY][ATTR_ACCUMULATED_ERROR] == -1.25


@pytest.mark.parametrize("option", [STOP_MODE_OFF, STOP_MODE_FAN_ONLY, STOP_MODE_DRY])
async def test_mode_enables_and_is_saved_atomically(
    selection, hass, monkeypatch, option
):
    entry, _, manager, entity = selection
    update = Mock(wraps=hass.config_entries.async_update_entry)
    monkeypatch.setattr(hass.config_entries, "async_update_entry", update)
    set_enabled = manager.async_set_enabled

    async def enable_after_mode(enabled):
        assert manager.stop_mode == option
        await set_enabled(enabled)

    monkeypatch.setattr(manager, "async_set_enabled", enable_after_mode)
    await entity.async_select_option(option)

    update.assert_called_once()
    saved = update.call_args.kwargs["options"]
    assert saved[CONF_ENABLED] is True
    assert saved[CONF_STOP_MODE] == option
    assert saved[CONF_VTHERM_UNIQUE_ID] == "thermostat"
    assert entry.options == saved
    assert manager.enabled is True
    assert manager.stop_mode == option
    assert entity.current_option == option


@pytest.mark.parametrize("option", ["heat", "cool", "auto", "fan_only", "invalid"])
async def test_unsupported_selection_does_not_change_anything(selection, option):
    entry, thermostat, manager, entity = selection
    thermostat.vtherm_hvac_modes = ["off", "heat"]
    with pytest.raises(ServiceValidationError):
        await entity.async_select_option(option)
    assert entry.options == {}
    assert manager.enabled is False
    assert manager.stop_mode == STOP_MODE_DRY
    assert thermostat.refresh_requests == 0


async def test_missing_entry_is_reported_without_changing_runtime(
    selection, hass, monkeypatch
):
    _, _, manager, entity = selection
    monkeypatch.setattr(hass.config_entries, "async_get_entry", lambda entry_id: None)
    with pytest.raises(ServiceValidationError):
        await entity.async_select_option(STOP_MODE_OFF)
    assert manager.enabled is False
    assert manager.stop_mode == STOP_MODE_DRY
