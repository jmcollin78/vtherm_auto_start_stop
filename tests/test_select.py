"""Independent activation and automatic stop-mode entity controls."""

from unittest.mock import AsyncMock, Mock

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
    LEVEL_PERSONNALISE,
    LEVEL_SLOW,
    LEVELS,
    MANAGER_ATTRIBUTES_KEY,
    STOP_MODE_DRY,
    STOP_MODE_FAN_ONLY,
    STOP_MODE_OFF,
)
from custom_components.vtherm_auto_start_stop.algorithm import DT_MIN, ERROR_THRESHOLD
from custom_components.vtherm_auto_start_stop.manager import AutoStartStopManager
from custom_components.vtherm_auto_start_stop.select import (
    AutoStartStopLevelSelect,
    AutoStartStopStopModeSelect,
)
from tests.conftest import FakeThermostat


@pytest.fixture
async def selection(hass, monkeypatch):
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
    manager.restore_entity_state(
        False,
        STOP_MODE_DRY,
        DT_MIN[LEVEL_FAST],
        ERROR_THRESHOLD[LEVEL_FAST],
    )
    entity = AutoStartStopStopModeSelect(hass, entry, thermostat.unique_id)
    entity.hass = hass
    entity.entity_id = "select.auto_start_stop"
    monkeypatch.setattr(entity, "async_write_ha_state", Mock())
    await entity.async_added_to_hass()
    yield entry, thermostat, manager, entity
    await entity.async_will_remove_from_hass()


@pytest.fixture
def enable_switch(selection, hass, monkeypatch):
    from custom_components.vtherm_auto_start_stop.switch import (
        AutoStartStopEnableSwitch,
    )

    entry, thermostat, _, _ = selection
    entity = AutoStartStopEnableSwitch(hass, entry, thermostat.unique_id)
    entity.hass = hass
    entity.entity_id = "switch.auto_start_stop"
    monkeypatch.setattr(entity, "async_write_ha_state", Mock())
    return entity


@pytest.mark.parametrize("fan", [False, True])
@pytest.mark.parametrize("dry", [False, True])
def test_options_contain_only_compatible_stop_modes(selection, fan, dry):
    _, thermostat, _, entity = selection
    thermostat.vtherm_hvac_modes = ["off", "heat", "cool", "auto"]
    expected = [STOP_MODE_OFF]
    if fan:
        thermostat.vtherm_hvac_modes.append(STOP_MODE_FAN_ONLY)
        expected.append(STOP_MODE_FAN_ONLY)
    if dry:
        thermostat.vtherm_hvac_modes.append(STOP_MODE_DRY)
        expected.append(STOP_MODE_DRY)
    assert entity.options == expected


@pytest.mark.parametrize("enabled", [False, True])
def test_current_option_does_not_depend_on_enable_state(selection, enabled):
    _, _, manager, entity = selection
    manager.restore_entity_state(enabled, STOP_MODE_DRY)
    assert entity.current_option == STOP_MODE_DRY


def test_unavailable_select_uses_saved_configuration(selection, hass):
    _, _, _, entity = selection
    hass.data[DOMAIN][DATA_MANAGERS].clear()
    assert entity.available is False
    assert entity.current_option == STOP_MODE_DRY


async def test_switch_off_preserves_mode_and_releases_a_detected_stop(
    selection, enable_switch, hass
):
    entry, thermostat, manager, entity = selection
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_ENABLED: True}
    )
    manager.restore_entity_state(True, STOP_MODE_DRY)
    manager._is_stop_detected = True
    manager._algorithm.restore(-1.25, None)

    await enable_switch.async_turn_off()

    assert manager.enabled is False
    assert manager.is_detected is False
    assert manager.stop_mode == STOP_MODE_DRY
    assert entry.options == {}
    assert enable_switch.is_on is False
    assert entity.current_option == STOP_MODE_DRY
    assert thermostat.refresh_requests == 1
    for _ in range(10):
        thermostat.advance(1)
        assert await manager.refresh_state() is False
    attributes = {}
    manager.add_custom_attributes(attributes)
    assert attributes[MANAGER_ATTRIBUTES_KEY][ATTR_ACCUMULATED_ERROR] == -1.25


@pytest.mark.parametrize("option", [STOP_MODE_OFF, STOP_MODE_FAN_ONLY, STOP_MODE_DRY])
@pytest.mark.parametrize("enabled", [False, True])
async def test_mode_change_preserves_enable_state(
    selection, hass, monkeypatch, option, enabled
):
    entry, _, manager, entity = selection
    initial_mode = STOP_MODE_DRY if option == STOP_MODE_OFF else STOP_MODE_OFF
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, CONF_ENABLED: enabled, CONF_STOP_MODE: initial_mode},
    )
    manager.restore_entity_state(enabled, initial_mode)
    update = Mock(wraps=hass.config_entries.async_update_entry)
    monkeypatch.setattr(hass.config_entries, "async_update_entry", update)
    set_enabled = AsyncMock(wraps=manager.async_set_enabled)
    monkeypatch.setattr(manager, "async_set_enabled", set_enabled)
    await entity.async_select_option(option)

    update.assert_not_called()
    assert entry.options == {}
    assert manager.enabled is enabled
    assert manager.stop_mode == option
    assert entity.current_option == option
    set_enabled.assert_not_awaited()


async def test_switch_on_uses_saved_mode(selection, enable_switch):
    entry, _, manager, entity = selection
    await enable_switch.async_turn_on()
    assert entry.options == {}
    assert manager.enabled is True
    assert manager.stop_mode == STOP_MODE_DRY
    assert enable_switch.is_on is True
    assert entity.current_option == STOP_MODE_DRY


async def test_switch_startup_applies_saved_mode_before_enabling(
    selection, enable_switch, hass, monkeypatch
):
    entry, _, manager, _ = selection
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_ENABLED: True}
    )
    from custom_components.vtherm_auto_start_stop.registry import control_state

    state = control_state(hass, "thermostat")
    state.enabled = None
    manager._controls_ready = False
    manager._stop_mode = STOP_MODE_OFF
    original = manager.async_set_enabled

    async def enable_after_mode(enabled):
        assert manager.stop_mode == STOP_MODE_DRY
        await original(enabled)

    monkeypatch.setattr(manager, "async_set_enabled", enable_after_mode)
    await enable_switch.async_added_to_hass()
    assert manager.enabled is True
    await enable_switch.async_will_remove_from_hass()


@pytest.mark.parametrize("enabled", [False, True])
async def test_switch_missing_entry_does_not_change_runtime(
    selection, enable_switch, hass, monkeypatch, enabled
):
    _, thermostat, manager, _ = selection
    monkeypatch.setattr(hass.config_entries, "async_get_entry", lambda entry_id: None)
    action = enable_switch.async_turn_on if enabled else enable_switch.async_turn_off
    with pytest.raises(ServiceValidationError):
        await action()
    assert manager.enabled is False
    assert manager.stop_mode == STOP_MODE_DRY
    assert thermostat.refresh_requests == 0


@pytest.mark.parametrize(
    "option", ["heat", "cool", "auto", "fan_only", "disabled", "invalid"]
)
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


# ---------------------------------------------------------------------------
# Level selector (tasks 2.1, 2.2, 2.3)
# ---------------------------------------------------------------------------


@pytest.fixture
async def level_selection(selection, hass, monkeypatch):
    """The level selector, attached to the same manager as the stop-mode one."""
    from custom_components.vtherm_auto_start_stop.select import (
        AutoStartStopLevelSelect,
    )

    entry, thermostat, manager, _ = selection
    entity = AutoStartStopLevelSelect(hass, entry, thermostat.unique_id)
    entity.hass = hass
    entity.entity_id = "select.auto_start_stop_level"
    monkeypatch.setattr(entity, "async_write_ha_state", Mock())
    await entity.async_added_to_hass()
    yield entity
    await entity.async_will_remove_from_hass()


def test_level_options_are_the_five_levels(level_selection):
    """The selector offers every level, the custom label included."""
    assert level_selection.options == list(LEVELS)


def test_level_reads_the_derived_pair(level_selection, selection):
    """The current option is derived, never a stored label."""
    _, _, manager, _ = selection
    assert level_selection.current_option == manager.level
    assert level_selection.current_option == LEVEL_FAST


async def test_selecting_a_named_level_writes_both_parameters(
    level_selection, selection
):
    """Task 2.2: one selection, one coherent pair, one notification."""
    _, _, manager, _ = selection
    published: list[str] = []
    original = manager._publish_update
    manager._publish_update = lambda: (published.append(manager.level), original())[1]

    await level_selection.async_select_option(LEVEL_SLOW)

    assert manager.level == LEVEL_SLOW
    assert manager.dt_min == DT_MIN[LEVEL_SLOW]
    assert manager.error_threshold == ERROR_THRESHOLD[LEVEL_SLOW]
    assert published == [LEVEL_SLOW]
    assert level_selection.current_option == LEVEL_SLOW


async def test_selecting_personnalise_on_a_named_level_is_refused(
    level_selection, selection
):
    """Task 2.3: selecting the custom label never changes anything."""
    _, _, manager, _ = selection
    assert manager.level == LEVEL_FAST
    with pytest.raises(ServiceValidationError):
        await level_selection.async_select_option(LEVEL_PERSONNALISE)
    assert manager.level == LEVEL_FAST
    assert manager.dt_min == DT_MIN[LEVEL_FAST]


async def test_personnalise_is_a_no_op_when_already_custom(level_selection, selection):
    """On a custom pair, re-selecting the custom label simply confirms it."""
    _, _, manager, _ = selection
    await manager.apply_parameters(45, 25)
    assert manager.level == LEVEL_PERSONNALISE
    await level_selection.async_select_option(LEVEL_PERSONNALISE)
    assert manager.level == LEVEL_PERSONNALISE
    assert manager.dt_min == 45


@pytest.mark.parametrize("option", ["bad_level", "", "auto_start_stop_none"])
async def test_unknown_level_option_is_refused(level_selection, selection, option):
    _, _, manager, _ = selection
    before = manager.level
    with pytest.raises(ServiceValidationError):
        await level_selection.async_select_option(option)
    assert manager.level == before


async def test_level_selection_without_a_manager_is_reported(
    level_selection, selection, hass
):
    """An orphaned selector raises instead of silently doing nothing."""
    _, _, manager, _ = selection
    hass.data[DOMAIN][DATA_MANAGERS].clear()
    with pytest.raises(ServiceValidationError):
        await level_selection.async_select_option(LEVEL_SLOW)
    assert manager.level == LEVEL_FAST
