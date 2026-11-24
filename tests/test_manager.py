"""Manager behaviour (tasks 4.1 to 4.5, 5.2, 5.3, 7.2)."""

from __future__ import annotations

import pytest
from homeassistant.core import State

from custom_components.vtherm_auto_start_stop.const import (
    ATTR_ACCUMULATED_ERROR,
    ATTR_DTMIN,
    ATTR_ENABLE,
    ATTR_IS_CONFIGURED,
    ATTR_IS_STOP_DETECTED,
    ATTR_LEVEL,
    ATTR_STOP_MODE,
    CONF_ENABLED,
    CONF_LEVEL,
    CONF_STOP_MODE,
    DATA_MANAGERS,
    DOMAIN,
    LEVEL_FAST,
    LEVEL_NONE,
    LEVEL_SLOW,
    MANAGER_ATTRIBUTES_KEY,
    MANAGER_NAME,
    STOP_MODE_DRY,
    STOP_MODE_FAN_ONLY,
    STOP_MODE_OFF,
)
from vtherm_api.const import EventType
from custom_components.vtherm_auto_start_stop.models import initial_control_defaults

VT_UNIQUE_ID = "vtherm-uid-1"


def install(manager_factory, thermostat, add_global_entry=None, **kwargs):
    """Attach a manager to the thermostat, as the core would."""
    manager = manager_factory(thermostat)
    manager.post_init(thermostat.entry_infos)
    if manager.is_configured and not manager.controls_ready:
        entries = thermostat.hass.data[DOMAIN]["entries"]
        values = initial_control_defaults(entries)
        for entry in entries.values():
            if entry.get("vtherm_unique_id") == thermostat.unique_id:
                values.update({key: entry[key] for key in values if key in entry})
        manager.restore_entity_state(values[CONF_ENABLED], values[CONF_STOP_MODE])
    return manager


# ---------------------------------------------------------------------------
# Registration (task 4.1)
# ---------------------------------------------------------------------------


def test_stable_name(manager_factory, thermostat, add_global_entry):
    """The delegation resolves the manager by this exact name."""
    add_global_entry()
    manager = install(manager_factory, thermostat)
    assert manager.name == MANAGER_NAME == "auto_start_stop"


def test_manager_registered_in_domain_data(
    manager_factory, thermostat, add_global_entry, fake_hass
):
    add_global_entry()
    manager = install(manager_factory, thermostat)
    assert fake_hass.data[DOMAIN][DATA_MANAGERS][VT_UNIQUE_ID] is manager
    assert manager.is_configured is True


def test_manager_detached_without_configuration(manager_factory, thermostat, fake_hass):
    """No entry at all: the manager stays inert, as the core feature disabled."""
    manager = install(manager_factory, thermostat)
    assert manager.is_configured is False
    assert VT_UNIQUE_ID not in fake_hass.data[DOMAIN][DATA_MANAGERS]


@pytest.mark.parametrize("dedicated", [False, True])
async def test_disabled_manager_stays_configured(
    manager_factory,
    thermostat,
    add_global_entry,
    add_dedicated_entry,
    fake_hass,
    dedicated,
):
    """Disabled detection retains its configuration and frozen diagnostics."""
    add_global_entry(enabled=dedicated)
    if dedicated:
        add_dedicated_entry(enabled=False)
    manager = install(manager_factory, thermostat)
    manager.restore_state(
        State(
            thermostat.entity_id,
            "heat",
            {MANAGER_ATTRIBUTES_KEY: {ATTR_ACCUMULATED_ERROR: -1.25}},
        )
    )
    for _ in range(10):
        thermostat.advance(1)
        assert await manager.refresh_state() is False

    assert manager.is_configured is True
    assert fake_hass.data[DOMAIN][DATA_MANAGERS][VT_UNIQUE_ID] is manager
    assert thermostat.refresh_requests == 0

    attributes: dict = {}
    manager.add_custom_attributes(attributes)
    assert attributes[ATTR_IS_CONFIGURED] is True
    section = attributes[MANAGER_ATTRIBUTES_KEY]
    assert section[ATTR_ENABLE] is False
    assert section[ATTR_IS_STOP_DETECTED] is False
    assert section[ATTR_ACCUMULATED_ERROR] == -1.25


# ---------------------------------------------------------------------------
# Refresh and transitions (task 4.3)
# ---------------------------------------------------------------------------


async def test_refresh_without_transition_does_not_request_a_refresh(
    manager_factory, thermostat, add_global_entry
):
    """A cycle that keeps the same decision costs no recalculation."""
    add_global_entry(level=LEVEL_FAST)
    manager = install(manager_factory, thermostat)
    await manager.refresh_state()
    assert thermostat.refresh_requests == 0


async def test_transition_requests_an_immediate_refresh(
    manager_factory, thermostat, add_global_entry
):
    """A decision taken on a state-change path is applied in the same cycle."""
    add_global_entry(level=LEVEL_FAST)
    manager = install(manager_factory, thermostat)
    thermostat.target_temperature = 20.0
    thermostat.current_temperature = 22.0
    thermostat.last_temperature_slope = 6.0

    detected = False
    for _ in range(40):
        thermostat.advance(1)
        detected = await manager.refresh_state()
        if detected:
            break

    assert detected is True
    assert thermostat.refresh_requests == 1


async def test_refresh_and_update_if_changed_reports_the_change(
    manager_factory, thermostat, add_global_entry
):
    add_global_entry(level=LEVEL_FAST)
    manager = install(manager_factory, thermostat)
    first = await manager.refresh_and_update_if_changed()
    assert first is False

    thermostat.current_temperature = 22.0
    thermostat.last_temperature_slope = 6.0
    changed = False
    for _ in range(40):
        thermostat.advance(1)
        changed = await manager.refresh_and_update_if_changed()
        if changed:
            break
    assert changed is True


async def test_disabled_manager_releases_a_detected_stop(
    manager_factory, thermostat, add_global_entry
):
    """Turning the switch off releases the applied stop in the same cycle."""
    add_global_entry(level=LEVEL_FAST)
    manager = install(manager_factory, thermostat)
    thermostat.current_temperature = 22.0
    thermostat.last_temperature_slope = 6.0
    for _ in range(40):
        thermostat.advance(1)
        if await manager.refresh_state():
            break
    assert manager.is_detected is True

    await manager.async_set_enabled(False)
    assert manager.enabled is False
    assert manager.is_detected is False
    assert await manager.refresh_state() is False


async def test_disabled_manager_does_not_accumulate(
    manager_factory, thermostat, add_global_entry
):
    add_global_entry(level=LEVEL_FAST, enabled=False)
    manager = install(manager_factory, thermostat)
    for _ in range(10):
        thermostat.advance(1)
        await manager.refresh_state()
    assert manager.is_detected is False


# ---------------------------------------------------------------------------
# Published attributes (task 4.5)
# ---------------------------------------------------------------------------


def test_attribute_section_is_published_verbatim(
    manager_factory, thermostat, add_global_entry
):
    add_global_entry(level=LEVEL_SLOW, stop_mode=STOP_MODE_FAN_ONLY)
    manager = install(manager_factory, thermostat)
    attributes: dict = {}
    manager.add_custom_attributes(attributes)

    assert attributes[ATTR_IS_CONFIGURED] is True
    section = attributes[MANAGER_ATTRIBUTES_KEY]
    assert section[ATTR_ENABLE] is True
    assert section[ATTR_LEVEL] == LEVEL_SLOW
    assert section[ATTR_STOP_MODE] == STOP_MODE_FAN_ONLY
    assert section[ATTR_IS_STOP_DETECTED] is False
    assert section[ATTR_DTMIN] == 30
    assert ATTR_ACCUMULATED_ERROR in section


# ---------------------------------------------------------------------------
# Stop-mode arbitration (tasks 4.4, 5.3)
# ---------------------------------------------------------------------------


async def test_stop_modes_filtered_by_accepted_hvac_modes(
    manager_factory, thermostat, add_global_entry
):
    add_global_entry()
    manager = install(manager_factory, thermostat)
    assert manager.stop_modes == [STOP_MODE_OFF, STOP_MODE_FAN_ONLY, STOP_MODE_DRY]

    thermostat.vtherm_hvac_modes = ["off", "heat", "cool"]
    assert manager.stop_modes == [STOP_MODE_OFF]


async def test_changing_the_stop_mode_reapplies_the_stop(
    manager_factory, thermostat, add_global_entry
):
    """A new stop mode is applied while a stop is active."""
    add_global_entry(level=LEVEL_FAST)
    manager = install(manager_factory, thermostat)
    thermostat.current_temperature = 22.0
    thermostat.last_temperature_slope = 6.0
    for _ in range(40):
        thermostat.advance(1)
        if await manager.refresh_state():
            break
    assert manager.is_detected is True

    requests = thermostat.refresh_requests
    await manager.async_set_stop_mode(STOP_MODE_DRY)
    assert manager.stop_mode == STOP_MODE_DRY
    assert thermostat.refresh_requests == requests + 1


async def test_changing_the_stop_mode_without_stop_does_not_refresh(
    manager_factory, thermostat, add_global_entry
):
    add_global_entry(level=LEVEL_FAST)
    manager = install(manager_factory, thermostat)
    requests = thermostat.refresh_requests
    await manager.async_set_stop_mode(STOP_MODE_DRY)
    assert manager.stop_mode == STOP_MODE_DRY
    assert thermostat.refresh_requests == requests


async def test_unknown_stop_mode_is_normalized(
    manager_factory, thermostat, add_global_entry
):
    add_global_entry()
    manager = install(manager_factory, thermostat)
    await manager.async_set_stop_mode("not_a_mode")
    assert manager.stop_mode == STOP_MODE_OFF


# ---------------------------------------------------------------------------
# Events (task 4.4)
# ---------------------------------------------------------------------------


async def test_transition_sends_the_core_event(
    manager_factory, thermostat, add_global_entry
):
    add_global_entry(level=LEVEL_FAST)
    manager = install(manager_factory, thermostat)
    thermostat.current_temperature = 22.0
    thermostat.last_temperature_slope = 6.0
    for _ in range(40):
        thermostat.advance(1)
        if await manager.refresh_state():
            break

    assert thermostat.events, "an event must be sent on a transition"
    event_type, data = thermostat.events[-1]
    assert event_type == EventType.AUTO_START_STOP_EVENT
    assert data["type"] == "stop"
    assert data["name"] == MANAGER_NAME
    assert data["hvac_mode"] == STOP_MODE_OFF


async def test_release_requests_a_refresh_too(
    manager_factory, thermostat, add_global_entry
):
    """Task 4.4: the reverse transition also applies in the same cycle."""
    add_global_entry(level=LEVEL_FAST)
    manager = install(manager_factory, thermostat)
    thermostat.current_temperature = 22.0
    thermostat.last_temperature_slope = 6.0
    for _ in range(40):
        thermostat.advance(1)
        if await manager.refresh_state():
            break
    assert manager.is_detected is True
    requests = thermostat.refresh_requests

    # The room cools down again: the stop must be released in the same cycle.
    thermostat.current_temperature = 15.0
    thermostat.last_temperature_slope = -6.0
    released = False
    for _ in range(60):
        thermostat.advance(1)
        if not await manager.refresh_state():
            released = True
            break

    assert released is True
    assert thermostat.refresh_requests > requests
    event_type, data = thermostat.events[-1]
    assert event_type == EventType.AUTO_START_STOP_EVENT
    assert data["type"] == "start"
    assert data["hvac_mode"] == "heat"


async def test_entity_state_is_reconciled(
    manager_factory, thermostat, add_global_entry
):
    """The restored entity state is pushed into the manager (5.2/5.3)."""
    add_global_entry(level=LEVEL_SLOW, enabled=True)
    manager = install(manager_factory, thermostat)
    manager.restore_entity_state(False, STOP_MODE_DRY)
    assert manager.enabled is False
    assert manager.stop_mode == STOP_MODE_DRY


async def test_bootstrap_waits_for_both_controls_and_applies_mode_first(
    manager_factory, thermostat, add_global_entry, monkeypatch
):
    from custom_components.vtherm_auto_start_stop.registry import control_state

    add_global_entry(level=LEVEL_FAST, enabled=True)
    state = control_state(thermostat.hass, thermostat.unique_id)
    state.enabled = True
    manager = manager_factory(thermostat)
    manager.post_init({})
    manager.restore_state(State(thermostat.entity_id, "off", {
        MANAGER_ATTRIBUTES_KEY: {ATTR_IS_STOP_DETECTED: True, ATTR_ACCUMULATED_ERROR: -4.5}
    }))
    thermostat.current_temperature = 24
    thermostat.last_temperature_slope = 6
    for _ in range(10):
        thermostat.advance(1)
        assert await manager.refresh_state() is False
    assert manager.controls_ready is False
    assert manager.enabled is False
    assert manager.is_auto_stop_detected is False
    assert manager._algorithm.accumulated_error == -4.5
    assert thermostat.refresh_requests == 0
    original = manager.async_set_enabled

    async def enable_after_mode(enabled):
        assert manager.stop_mode == STOP_MODE_DRY
        assert manager.controls_ready is True
        await original(enabled)

    monkeypatch.setattr(manager, "async_set_enabled", enable_after_mode)
    state.stop_mode = STOP_MODE_DRY
    await manager.async_initialize_controls(state.enabled, state.stop_mode)
    assert manager.enabled is True


def test_none_level_is_not_detected(manager_factory, thermostat, add_global_entry):
    add_global_entry(level=LEVEL_NONE)
    manager = install(manager_factory, thermostat)
    assert manager.is_detected is False


async def test_stop_listening_unregisters(
    manager_factory, thermostat, add_global_entry, fake_hass
):
    add_global_entry()
    manager = install(manager_factory, thermostat)
    manager.stop_listening()
    assert VT_UNIQUE_ID not in fake_hass.data[DOMAIN][DATA_MANAGERS]


def test_dedicated_layer_overrides_global(
    manager_factory, thermostat, add_global_entry, add_dedicated_entry
):
    add_global_entry(level=LEVEL_SLOW)
    add_dedicated_entry(level=LEVEL_FAST)
    manager = install(manager_factory, thermostat)
    assert manager._algorithm.level == LEVEL_FAST


# ---------------------------------------------------------------------------
# Delegation contract: the names the core actually reads
# ---------------------------------------------------------------------------


async def test_core_arbitration_names_are_exposed(
    manager_factory, thermostat, add_global_entry
):
    """The core arbitration reads `is_auto_stop_detected` and `stop_mode`.

    Once the feature is delegated, the core resolves
    ``vtherm.auto_start_stop_manager`` to this manager and reads it through its
    own property names, so the plugin must expose them or the arbitration would
    fail with an ``AttributeError`` at the next state computation.
    """
    add_global_entry(level=LEVEL_FAST, stop_mode=STOP_MODE_DRY)
    manager = install(manager_factory, thermostat)

    assert manager.is_auto_stop_detected is manager.is_detected
    assert manager.stop_mode == STOP_MODE_DRY
    assert manager.auto_start_stop_enable is True


async def test_core_entities_can_drive_the_manager(
    manager_factory, thermostat, add_global_entry
):
    """The core switch and select call `set_auto_start_stop_*` on the manager."""
    add_global_entry(level=LEVEL_SLOW, enabled=True)
    manager = install(manager_factory, thermostat)

    await manager.set_auto_start_stop_enable(False)
    assert manager.enabled is False
    assert manager.auto_start_stop_enable is False

    await manager.set_auto_start_stop_stop_mode(STOP_MODE_FAN_ONLY)
    assert manager.stop_mode == STOP_MODE_FAN_ONLY


async def test_reset_switch_delay_is_called_by_the_core(
    manager_factory, thermostat, add_global_entry
):
    """The core resets the delay when the target temperature changes."""
    add_global_entry(level=LEVEL_FAST)
    manager = install(manager_factory, thermostat)
    thermostat.current_temperature = 22.0
    thermostat.last_temperature_slope = 6.0
    for _ in range(40):
        thermostat.advance(1)
        if await manager.refresh_state():
            break
    assert manager.is_detected is True

    manager.reset_switch_delay()
    assert manager._algorithm.last_switch_date is None


def test_restore_state_reads_the_attribute_section(
    manager_factory, thermostat, add_global_entry
):
    from types import SimpleNamespace

    add_global_entry(level=LEVEL_SLOW)
    manager = install(manager_factory, thermostat)
    old_state = SimpleNamespace(
        attributes={
            MANAGER_ATTRIBUTES_KEY: {
                ATTR_IS_STOP_DETECTED: True,
                ATTR_ACCUMULATED_ERROR: -4.5,
            }
        }
    )
    manager.restore_state(old_state)
    assert manager.is_detected is True
    assert manager._algorithm.accumulated_error == -4.5


def test_restore_state_without_section_is_a_noop(
    manager_factory, thermostat, add_global_entry
):
    from types import SimpleNamespace

    add_global_entry()
    manager = install(manager_factory, thermostat)
    manager.restore_state(SimpleNamespace(attributes={}))
    assert manager.is_detected is False
    manager.restore_state(None)
    assert manager.is_detected is False
