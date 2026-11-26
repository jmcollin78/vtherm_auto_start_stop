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
    CONF_ERROR_THRESHOLD,
    CONF_LEVEL,
    CONF_DT_MIN,
    CONF_STOP_MODE,
    DATA_MANAGERS,
    DOMAIN,
    LEVEL_FAST,
    LEVEL_MEDIUM,
    LEVEL_PERSONNALISE,
    LEVEL_SLOW,
    MANAGER_ATTRIBUTES_KEY,
    MANAGER_NAME,
    STOP_MODE_DRY,
    STOP_MODE_FAN_ONLY,
    STOP_MODE_OFF,
)
from vtherm_api.const import EventType
from custom_components.vtherm_auto_start_stop.algorithm import DT_MIN, ERROR_THRESHOLD
from custom_components.vtherm_auto_start_stop.models import initial_control_defaults

VT_UNIQUE_ID = "vtherm-uid-1"


def install(manager_factory, thermostat, add_global_entry=None, **kwargs):
    """Attach a manager to the thermostat, as the core would.

    ``post_init`` leaves the bridge empty on purpose: the five entities own the
    seeding and the restore cascade. The helper therefore feeds the complete
    restored set, exactly as the entities would.
    """
    manager = manager_factory(thermostat)
    manager.post_init(thermostat.entry_infos)
    if manager.is_configured and not manager.controls_ready:
        entries = thermostat.hass.data[DOMAIN]["entries"]
        values = initial_control_defaults(entries, thermostat.unique_id)
        manager.restore_entity_state(
            values[CONF_ENABLED],
            values[CONF_STOP_MODE],
            values[CONF_DT_MIN],
            values[CONF_ERROR_THRESHOLD],
        )
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


async def test_refresh_state_republishes_when_stop_modes_change(
    manager_factory, thermostat, add_global_entry
):
    """When the underlying's hvac_modes become available mid-lifecycle, the manager
    must re-publish so the select entity is notified of the new option set."""
    add_global_entry()
    # Start with the pre-underlying-attached hvac list (the default build_hvac_list).
    thermostat.vtherm_hvac_modes = ["off", "heat", "cool"]
    manager = install(manager_factory, thermostat)
    assert manager.stop_modes == [STOP_MODE_OFF]

    # First refresh: the cache is initialised from the current value; no
    # republication is expected because nothing has changed.
    before = thermostat.attribute_updates
    await manager.refresh_state()
    assert thermostat.attribute_updates == before

    # The underlyings are now initialised and expose their accepted hvac_modes:
    # a new fan_only and dry appear. refresh_state must detect the change and
    # re-publish so the select entity learns of the new options.
    thermostat.vtherm_hvac_modes = ["off", "heat", "cool", "fan_only", "dry"]
    before = thermostat.attribute_updates
    await manager.refresh_state()
    assert thermostat.attribute_updates == before + 1

    # A second refresh with an unchanged list does not re-publish.
    await manager.refresh_state()
    assert thermostat.attribute_updates == before + 1


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


async def test_refresh_is_a_no_op_before_the_controls_are_ready(
    manager_factory, thermostat, add_global_entry
):
    """Detection never runs before the controls supplied enable and stop mode."""
    add_global_entry(level=LEVEL_FAST, enabled=True)
    manager = manager_factory(thermostat)
    manager._configured = True
    assert manager.controls_ready is False
    thermostat.current_temperature = 24
    for _ in range(10):
        thermostat.advance(1)
        assert await manager.refresh_state() is False
    assert thermostat.refresh_requests == 0


def test_none_literal_fonds_to_the_default_level(
    manager_factory, thermostat, add_global_entry
):
    """The removed ``none`` literal no longer disables the manager.

    An unknown level seeds the SLOW pair, which derives back to SLOW.
    """
    entry = add_global_entry(level=LEVEL_SLOW, enabled=True)
    entry[CONF_LEVEL] = "auto_start_stop_none"
    manager = install(manager_factory, thermostat)
    assert manager.is_configured is True
    assert manager.level == LEVEL_SLOW


def test_personnalise_applies_custom_parameters(manager_factory, thermostat, fake_hass):
    """A personnalise level reads the custom values from the entry cascade."""
    fake_hass.data[DOMAIN]["entries"]["global"] = {
        CONF_LEVEL: LEVEL_PERSONNALISE,
        CONF_STOP_MODE: STOP_MODE_OFF,
        CONF_ENABLED: True,
        CONF_DT_MIN: 45,
        CONF_ERROR_THRESHOLD: 25,
    }
    manager = install(manager_factory, thermostat)
    assert manager.is_configured is True
    assert manager.level == LEVEL_PERSONNALISE
    assert manager.dt_min == 45
    assert manager.error_threshold == 25


# ---------------------------------------------------------------------------
# Post-init behaviour (task 4.2)
# ---------------------------------------------------------------------------


async def test_post_init_registers_without_seeding_the_bridge(
    manager_factory, thermostat, add_global_entry, monkeypatch
):
    """Task 4.2: the manager attaches at post_init but seeds nothing.

    Seeding belongs to the five entities: a value already restored from an
    entity state must always win over the entry seed, so the bridge has to stay
    empty until the entities publish their own value.
    """
    from custom_components.vtherm_auto_start_stop.registry import control_state

    add_global_entry(level=LEVEL_FAST, enabled=True)
    manager = manager_factory(thermostat)
    manager.post_init({})

    assert manager.is_configured is True
    assert manager.controls_ready is False
    assert manager.enabled is False

    state = control_state(thermostat.hass, thermostat.unique_id)
    assert state.enabled is None
    assert state.stop_mode is None
    assert state.dt_min is None
    assert state.error_threshold is None


async def test_controls_initialisation_applies_the_mode_before_enabling(
    manager_factory, thermostat, add_global_entry, monkeypatch
):
    """The mode must be known before detection is enabled."""
    from custom_components.vtherm_auto_start_stop.registry import control_state

    add_global_entry(level=LEVEL_FAST, enabled=False)
    manager = manager_factory(thermostat)
    manager.post_init({})
    assert manager.enabled is False

    original = manager.async_set_enabled
    seen: list[str] = []

    async def enable_after_mode(enabled):
        seen.append(manager.stop_mode)
        assert manager.controls_ready is True
        await original(enabled)

    monkeypatch.setattr(manager, "async_set_enabled", enable_after_mode)
    state = control_state(thermostat.hass, thermostat.unique_id)
    state.stop_mode = STOP_MODE_DRY
    await manager.async_initialize_controls(True, STOP_MODE_DRY)

    assert seen == [STOP_MODE_DRY]
    assert manager.enabled is True
    assert manager.stop_mode == STOP_MODE_DRY


# ---------------------------------------------------------------------------
# Parameter writes (tasks 3.4, 5.2)
# ---------------------------------------------------------------------------


async def test_apply_level_writes_both_parameters_atomically(
    manager_factory, thermostat, add_global_entry
):
    """D5: selecting a level writes one coherent pair and publishes once."""
    from custom_components.vtherm_auto_start_stop.registry import control_state

    add_global_entry(level=LEVEL_SLOW, enabled=True)
    manager = install(manager_factory, thermostat)
    notifications: list[str] = []
    original = manager._publish_update
    manager._publish_update = lambda: (
        notifications.append(manager.level),
        original(),
    )[1]

    await manager.apply_level(LEVEL_FAST)

    assert manager.level == LEVEL_FAST
    assert manager.dt_min == DT_MIN[LEVEL_FAST]
    assert manager.error_threshold == ERROR_THRESHOLD[LEVEL_FAST]
    assert notifications == [LEVEL_FAST]
    state = control_state(thermostat.hass, thermostat.unique_id)
    assert state.level == LEVEL_FAST
    assert state.dt_min == DT_MIN[LEVEL_FAST]
    assert state.error_threshold == ERROR_THRESHOLD[LEVEL_FAST]


async def test_apply_parameters_derives_the_level(
    manager_factory, thermostat, add_global_entry
):
    """Writing an arbitrary pair derives ``personnalise``."""
    add_global_entry(level=LEVEL_SLOW, enabled=True)
    manager = install(manager_factory, thermostat)

    await manager.apply_parameters(45, 25)

    assert manager.dt_min == 45
    assert manager.error_threshold == 25
    assert manager.level == LEVEL_PERSONNALISE


async def test_apply_parameters_derives_a_named_level_from_its_pair(
    manager_factory, thermostat, add_global_entry
):
    """A pair matching a named level derives that level, never a stored label."""
    add_global_entry(level=LEVEL_SLOW, enabled=True)
    manager = install(manager_factory, thermostat)

    await manager.apply_parameters(DT_MIN[LEVEL_MEDIUM], ERROR_THRESHOLD[LEVEL_MEDIUM])

    assert manager.level == LEVEL_MEDIUM


async def test_apply_parameters_does_not_notify_when_nothing_changed(
    manager_factory, thermostat, add_global_entry
):
    """A no-op write does not wake the five entities."""
    add_global_entry(level=LEVEL_FAST, enabled=True)
    manager = install(manager_factory, thermostat)
    count = 0
    original = manager._publish_update

    def count_publish():
        nonlocal count
        count += 1
        original()

    manager._publish_update = count_publish
    await manager.apply_parameters(DT_MIN[LEVEL_FAST], ERROR_THRESHOLD[LEVEL_FAST])

    assert count == 0


async def test_parameter_change_updates_the_published_level(
    manager_factory, thermostat, add_global_entry
):
    """Task 5.4: the published level follows a parameter write, no reload."""
    add_global_entry(level=LEVEL_SLOW, enabled=True)
    manager = install(manager_factory, thermostat)

    attributes: dict = {}
    manager.add_custom_attributes(attributes)
    assert attributes[MANAGER_ATTRIBUTES_KEY][ATTR_LEVEL] == LEVEL_SLOW

    await manager.apply_parameters(45, 25)
    attributes = {}
    manager.add_custom_attributes(attributes)
    section = attributes[MANAGER_ATTRIBUTES_KEY]
    assert section[ATTR_LEVEL] == LEVEL_PERSONNALISE
    assert section[ATTR_DTMIN] == 45

    await manager.apply_level(LEVEL_FAST)
    attributes = {}
    manager.add_custom_attributes(attributes)
    section = attributes[MANAGER_ATTRIBUTES_KEY]
    assert section[ATTR_LEVEL] == LEVEL_FAST
    assert section[ATTR_DTMIN] == DT_MIN[LEVEL_FAST]
