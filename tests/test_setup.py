"""Integration setup and factory registration (tasks 1.1, 1.3)."""

from __future__ import annotations

from unittest.mock import AsyncMock, call

import pytest
from homeassistant.config_entries import ConfigEntryDisabler, ConfigEntryState
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockModule,
    mock_integration,
    mock_platform,
)

from custom_components.vtherm_auto_start_stop.const import (
    CONF_ENABLED,
    CONF_ENTITY_IDS_ADOPTED,
    CONF_LEVEL,
    CONF_STOP_MODE,
    CONF_VTHERM_UNIQUE_ID,
    DATA_FACTORY_REGISTERED,
    DOMAIN,
    ENTITY_ENABLE_SUFFIX,
    ENTITY_STOP_MODE_SUFFIX,
    LEVEL_FAST,
    LEVEL_SLOW,
    MANAGER_NAME,
    STOP_MODE_OFF,
    STOP_MODE_DRY,
    STOP_MODE_FAN_ONLY,
    VT_DOMAIN,
)
from custom_components.vtherm_auto_start_stop.factory import (
    AutoStartStopManagerFactory,
    register_factory,
    unregister_factory,
)
from tests.conftest import FakeThermostat


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):  # noqa: PT004
    return enable_custom_integrations


@pytest.fixture(autouse=True)
def mock_versatile_thermostat(hass):
    """Satisfy the declared dependency so the plugin can load."""
    mock_integration(hass, MockModule("versatile_thermostat"))
    mock_platform(hass, "versatile_thermostat.config_flow", None)
    return None


class FakeAPI:
    """The slice of ``VThermAPI`` the registration uses."""

    def __init__(self) -> None:
        self.managers: dict = {}
        self.register_calls = 0
        self.unregister_calls = 0

    def get_feature_manager(self, name: str):
        return self.managers.get(name)

    def register_feature_manager(self, factory) -> None:
        self.register_calls += 1
        self.managers[factory.name] = factory

    def unregister_feature_manager(self, name: str) -> None:
        self.unregister_calls += 1
        self.managers.pop(name, None)


@pytest.fixture
def fake_api(hass, monkeypatch):
    """Patch ``VThermAPI.get_vtherm_api`` to return a recording API."""
    import vtherm_api

    api = FakeAPI()
    monkeypatch.setattr(
        vtherm_api.VThermAPI,
        "get_vtherm_api",
        classmethod(lambda cls, hass: api),
    )
    return api


def test_factory_registered_once(hass: HomeAssistant, fake_api, caplog):
    """Task 1.3: the registration is idempotent and logged."""
    with caplog.at_level("INFO"):
        register_factory(hass, AutoStartStopManagerFactory(hass))
        register_factory(hass, AutoStartStopManagerFactory(hass))

    assert fake_api.register_calls == 1
    assert fake_api.managers[MANAGER_NAME].name == MANAGER_NAME
    assert hass.data[DOMAIN][DATA_FACTORY_REGISTERED] is True
    assert "registered under the stable name" in caplog.text


def test_registration_is_skipped_without_the_api(hass: HomeAssistant, monkeypatch):
    """The plugin must not crash when the core is not loaded yet."""
    import vtherm_api

    monkeypatch.setattr(
        vtherm_api.VThermAPI,
        "get_vtherm_api",
        classmethod(lambda cls, hass: None),
    )
    register_factory(hass, AutoStartStopManagerFactory(hass))
    assert hass.data[DOMAIN].get(DATA_FACTORY_REGISTERED) is None


def test_unregister_removes_the_factory(hass: HomeAssistant, fake_api):
    register_factory(hass, AutoStartStopManagerFactory(hass))
    unregister_factory(hass)
    assert fake_api.unregister_calls == 1
    assert MANAGER_NAME not in fake_api.managers
    assert hass.data[DOMAIN][DATA_FACTORY_REGISTERED] is False


async def test_integration_loads(hass: HomeAssistant, fake_api):
    """Task 1.1: the integration sets up and tears down cleanly."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_LEVEL: LEVEL_SLOW,
            CONF_STOP_MODE: STOP_MODE_OFF,
            CONF_ENABLED: True,
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert MANAGER_NAME in fake_api.managers

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert MANAGER_NAME not in fake_api.managers
    assert hass.data.get(DOMAIN) is None


async def test_entry_values_are_recorded(hass: HomeAssistant, fake_api):
    """The entries registry holds the values the resolution consumes."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_LEVEL: LEVEL_SLOW,
            CONF_STOP_MODE: STOP_MODE_OFF,
            CONF_ENABLED: True,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.data[DOMAIN]["entries"][entry.entry_id] == {
        CONF_LEVEL: LEVEL_SLOW,
        CONF_STOP_MODE: STOP_MODE_OFF,
        CONF_ENABLED: True,
    }


async def test_dedicated_personnalise_exposes_custom_dtmin(
    hass: HomeAssistant, fake_api, monkeypatch
):
    """A dedicated personnalise entry feeds the custom values to the manager."""
    from custom_components.vtherm_auto_start_stop.const import (
        ATTR_DTMIN,
        CONF_DT_MIN,
        CONF_ERROR_THRESHOLD,
        LEVEL_PERSONNALISE,
        MANAGER_ATTRIBUTES_KEY,
    )

    monkeypatch.setattr(
        hass.config_entries, "async_reload", AsyncMock(return_value=True)
    )
    core = register_core_entry(hass, "local")
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_VTHERM_UNIQUE_ID: core.unique_id,
            CONF_LEVEL: LEVEL_PERSONNALISE,
            CONF_STOP_MODE: STOP_MODE_OFF,
            CONF_ENABLED: True,
            CONF_DT_MIN: 45,
            CONF_ERROR_THRESHOLD: 25,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    runtime = runtime_for(hass, core)
    manager = fake_api.managers[MANAGER_NAME].create(runtime)
    manager.post_init(runtime.entry_infos)
    await hass.async_block_till_done()
    assert manager.is_configured is True

    attributes: dict = {}
    manager.add_custom_attributes(attributes)
    section = attributes[MANAGER_ATTRIBUTES_KEY]
    assert section[ATTR_DTMIN] == 45
    assert section["auto_start_stop_level"] == LEVEL_PERSONNALISE
    assert section["auto_start_stop_accumulated_error_threshold"] == 25


def register_core_entry(hass, unique_id):
    entry = MockConfigEntry(
        domain=VT_DOMAIN,
        unique_id=unique_id,
        data={"thermostat_type": "thermostat_over_climate"},
    )
    entry.add_to_hass(hass)
    return entry


def runtime_for(hass, core_entry):
    runtime = FakeThermostat(hass, core_entry.unique_id or core_entry.entry_id)
    runtime.entry_infos = dict(core_entry.data)
    return runtime


@pytest.mark.parametrize("global_enabled", [False, True])
@pytest.mark.parametrize("entry_id_identity", [False, True])
async def test_global_option_changes_preserve_dedicated_overrides(
    hass, fake_api, monkeypatch, global_enabled, entry_id_identity
):
    """Initialization defaults never reload or reset existing thermostats."""
    local_core = register_core_entry(hass, "local")
    other_core = register_core_entry(hass, "other")
    target_uid = local_core.unique_id
    if entry_id_identity:
        target_uid = local_core.entry_id
        for core in (local_core, other_core):
            hass.config_entries.async_update_entry(core, unique_id=None)
    reload = AsyncMock(return_value=True)
    monkeypatch.setattr(hass.config_entries, "async_reload", reload)
    global_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_LEVEL: LEVEL_SLOW,
            CONF_STOP_MODE: STOP_MODE_OFF,
            CONF_ENABLED: global_enabled,
        },
    )
    local_entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_VTHERM_UNIQUE_ID: target_uid,
            CONF_LEVEL: LEVEL_SLOW,
            CONF_STOP_MODE: STOP_MODE_OFF,
            CONF_ENABLED: not global_enabled,
        },
    )
    for entry in (global_entry, local_entry):
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    factory = fake_api.managers[MANAGER_NAME]
    for enabled in (global_enabled, not global_enabled, global_enabled):
        reload.reset_mock()
        hass.config_entries.async_update_entry(
            global_entry, options={CONF_ENABLED: enabled}
        )
        await hass.async_block_till_done()
        reload.assert_not_awaited()
        for core, expected in (
            (local_core, global_enabled),
            (other_core, global_enabled),
        ):
            runtime = runtime_for(hass, core)
            assert factory.supports(runtime)
            manager = factory.create(runtime)
            manager.post_init(runtime.entry_infos)
            assert manager.enabled is expected


async def test_dedicated_core_entry_id_reload_targets_only_its_thermostat(
    hass, fake_api, monkeypatch
):
    core = register_core_entry(hass, "local")
    register_core_entry(hass, "other")
    hass.config_entries.async_update_entry(core, unique_id=None)
    local = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_VTHERM_UNIQUE_ID: core.entry_id, CONF_ENABLED: False},
    )
    local.add_to_hass(hass)
    reload = AsyncMock(return_value=True)
    monkeypatch.setattr(hass.config_entries, "async_reload", reload)
    assert await hass.config_entries.async_setup(local.entry_id)
    await hass.async_block_till_done()
    reload.reset_mock()
    hass.config_entries.async_update_entry(local, options={CONF_LEVEL: LEVEL_FAST})
    await hass.async_block_till_done()
    reload.assert_awaited_once_with(core.entry_id)


@pytest.mark.parametrize("enabled", [False, True])
async def test_removing_dedicated_entry_restores_global(
    hass, fake_api, monkeypatch, enabled
):
    core = register_core_entry(hass, "local")
    reload = AsyncMock(return_value=True)
    monkeypatch.setattr(hass.config_entries, "async_reload", reload)
    global_entry = MockConfigEntry(domain=DOMAIN, data={CONF_ENABLED: enabled})
    local_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_VTHERM_UNIQUE_ID: core.unique_id, CONF_ENABLED: enabled},
        options={CONF_ENABLED: not enabled},
    )
    for entry in (global_entry, local_entry):
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    reload.reset_mock()

    assert await hass.config_entries.async_remove(local_entry.entry_id)
    await hass.async_block_till_done()

    assert reload.await_args_list == [call(core.entry_id)]
    assert local_entry.entry_id not in hass.data[DOMAIN]["entries"]
    factory = fake_api.managers[MANAGER_NAME]
    runtime = runtime_for(hass, core)
    assert factory.supports(runtime)
    manager = factory.create(runtime)
    manager.post_init(runtime.entry_infos)
    assert manager.enabled is enabled


@pytest.mark.parametrize("remove", [False, True])
async def test_global_changes_refresh_partially_overridden_thermostats(
    hass, fake_api, monkeypatch, remove
):
    local_core = register_core_entry(hass, "local")
    other_core = register_core_entry(hass, "other")
    reload = AsyncMock(return_value=True)
    monkeypatch.setattr(hass.config_entries, "async_reload", reload)
    global_entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_ENABLED: True, CONF_LEVEL: LEVEL_FAST}
    )
    local_entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_VTHERM_UNIQUE_ID: local_core.unique_id, CONF_ENABLED: False},
    )
    for entry in (global_entry, local_entry):
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    reload.reset_mock()

    if remove:
        assert await hass.config_entries.async_remove(global_entry.entry_id)
    else:
        hass.config_entries.async_update_entry(
            global_entry, options={CONF_LEVEL: LEVEL_SLOW}
        )
    await hass.async_block_till_done()

    assert reload.await_args_list == [
        call(local_core.entry_id),
        call(other_core.entry_id),
    ]
    factory = fake_api.managers[MANAGER_NAME]
    local_runtime = runtime_for(hass, local_core)
    assert factory.supports(local_runtime)
    assert factory.supports(runtime_for(hass, other_core)) is (not remove)
    manager = factory.create(local_runtime)
    manager.post_init(local_runtime.entry_infos)
    assert manager.enabled is True
    assert manager._algorithm.level == LEVEL_SLOW


async def test_parameter_entries_preserve_global_controls_and_entity_choices(
    hass, fake_api, monkeypatch
):
    """Parameter entries neither own nor reset globally supplied controls."""
    import custom_components.vtherm_auto_start_stop.manager as manager_module

    monkeypatch.setattr(manager_module, "async_dispatcher_send", async_dispatcher_send)
    core = register_core_entry(hass, "local")
    monkeypatch.setattr(
        hass.config_entries, "async_reload", AsyncMock(return_value=True)
    )
    global_entry = MockConfigEntry(domain=DOMAIN, data={CONF_ENABLED: False})
    global_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(global_entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    switch_uid = f"{core.unique_id}_{ENTITY_ENABLE_SUFFIX}"
    select_uid = f"{core.unique_id}_{ENTITY_STOP_MODE_SUFFIX}"
    assert registry.async_get_entity_id("switch", DOMAIN, switch_uid) is not None
    assert registry.async_get_entity_id("select", DOMAIN, select_uid) is not None

    runtime = runtime_for(hass, core)
    manager = fake_api.managers[MANAGER_NAME].create(runtime)
    manager.post_init(runtime.entry_infos)
    data = {
        CONF_VTHERM_UNIQUE_ID: core.unique_id,
        CONF_LEVEL: LEVEL_SLOW,
        CONF_STOP_MODE: STOP_MODE_OFF,
        CONF_ENABLED: False,
    }
    local_entry = MockConfigEntry(domain=DOMAIN, data=data)
    local_entry.add_to_hass(hass)
    existing_select = registry.async_get_or_create(
        "select",
        DOMAIN,
        select_uid,
        config_entry=local_entry,
        suggested_object_id="existing_auto_start_stop",
    )
    existing_switch = registry.async_get_or_create(
        "switch",
        DOMAIN,
        switch_uid,
        config_entry=local_entry,
        suggested_object_id="existing_enable_auto_start_stop",
    )
    assert await hass.config_entries.async_setup(local_entry.entry_id)
    await hass.async_block_till_done()

    switch_id = registry.async_get_entity_id("switch", DOMAIN, switch_uid)
    select_id = registry.async_get_entity_id("select", DOMAIN, select_uid)
    assert manager.enabled is False
    assert manager.stop_mode == STOP_MODE_OFF
    assert switch_id == existing_switch.entity_id
    assert select_id == existing_select.entity_id
    assert hass.states.get(switch_id).state == "off"
    assert hass.states.get(select_id).state == STOP_MODE_OFF
    assert {
        item.entity_id
        for item in er.async_entries_for_config_entry(registry, global_entry.entry_id)
    } == {switch_id, select_id}

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": select_id, "option": STOP_MODE_FAN_ONLY},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert manager.enabled is False
    assert manager.stop_mode == STOP_MODE_FAN_ONLY
    assert local_entry.options == {}
    assert hass.data[DOMAIN]["entries"][local_entry.entry_id][CONF_ENABLED] is False
    assert hass.data[DOMAIN]["entries"][global_entry.entry_id][CONF_ENABLED] is False
    assert hass.states.get(select_id).state == STOP_MODE_FAN_ONLY

    async def reload_manager(entry_id):
        manager.post_init(runtime.entry_infos)
        return True

    monkeypatch.setattr(
        hass.config_entries, "async_reload", AsyncMock(side_effect=reload_manager)
    )
    hass.config_entries.async_update_entry(
        local_entry,
        options={CONF_ENABLED: False, CONF_STOP_MODE: STOP_MODE_OFF},
    )
    await hass.async_block_till_done()
    assert manager.enabled is False
    assert hass.states.get(switch_id).state == "off"
    assert hass.states.get(select_id).state == STOP_MODE_FAN_ONLY

    assert await hass.config_entries.async_unload(local_entry.entry_id)
    assert await hass.config_entries.async_setup(local_entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get_entity_id("select", DOMAIN, select_uid) == select_id
    assert registry.async_get_entity_id("switch", DOMAIN, switch_uid) == switch_id
    assert hass.states.get(switch_id).state == "off"
    assert hass.states.get(select_id).state == STOP_MODE_FAN_ONLY
    assert manager.enabled is False
    assert manager.stop_mode == STOP_MODE_FAN_ONLY

    hass.config_entries.async_update_entry(
        local_entry, options={CONF_ENABLED: True, CONF_STOP_MODE: STOP_MODE_DRY}
    )
    await hass.async_block_till_done()
    assert manager.enabled is False
    assert hass.states.get(select_id).state == STOP_MODE_FAN_ONLY

    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": switch_id},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert manager.enabled is False
    assert local_entry.options[CONF_STOP_MODE] == STOP_MODE_DRY
    assert hass.states.get(switch_id).state == "off"
    assert hass.states.get(select_id).state == STOP_MODE_FAN_ONLY

    assert await hass.config_entries.async_remove(local_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(select_id).state == STOP_MODE_FAN_ONLY
    assert hass.states.get(switch_id).state == "off"

    replacement = MockConfigEntry(domain=DOMAIN, data=data)
    replacement.add_to_hass(hass)
    assert await hass.config_entries.async_setup(replacement.entry_id)
    await hass.async_block_till_done()
    switch_id = registry.async_get_entity_id("switch", DOMAIN, switch_uid)
    select_id = registry.async_get_entity_id("select", DOMAIN, select_uid)
    assert switch_id is not None
    assert select_id is not None
    assert hass.states.get(switch_id).state == "off"
    assert hass.states.get(select_id).state == STOP_MODE_FAN_ONLY
    assert len(er.async_entries_for_config_entry(registry, global_entry.entry_id)) == 2
    assert er.async_entries_for_config_entry(registry, replacement.entry_id) == []


@pytest.mark.parametrize("enabled", [False, True])
async def test_upgrade_reuses_owned_plugin_controls_without_core_history(
    hass, fake_api, monkeypatch, enabled
):
    """Setup preserves the select and settings and never touches other owners."""
    import custom_components.vtherm_auto_start_stop.manager as manager_module

    monkeypatch.setattr(manager_module, "async_dispatcher_send", async_dispatcher_send)
    monkeypatch.setattr(
        hass.config_entries, "async_reload", AsyncMock(return_value=True)
    )
    core = register_core_entry(hass, "local")
    local = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_VTHERM_UNIQUE_ID: core.unique_id,
            CONF_ENABLED: not enabled,
            CONF_STOP_MODE: STOP_MODE_OFF,
        },
        options={CONF_ENABLED: enabled, CONF_STOP_MODE: STOP_MODE_DRY},
    )
    other = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_VTHERM_UNIQUE_ID: "other"},
        disabled_by=ConfigEntryDisabler.USER,
    )
    local.add_to_hass(hass)
    other.add_to_hass(hass)
    registry = er.async_get(hass)
    switch_uid = f"{core.unique_id}_{ENTITY_ENABLE_SUFFIX}"
    legacy = registry.async_get_or_create(
        "switch",
        DOMAIN,
        switch_uid,
        config_entry=local,
    )
    core_switch = registry.async_get_or_create(
        "switch",
        VT_DOMAIN,
        switch_uid,
        config_entry=core,
    )
    other_switch = registry.async_get_or_create(
        "switch",
        DOMAIN,
        f"other_{ENTITY_ENABLE_SUFFIX}",
        config_entry=other,
    )
    select_uid = f"{core.unique_id}_{ENTITY_STOP_MODE_SUFFIX}"
    existing_select = registry.async_get_or_create(
        "select",
        DOMAIN,
        select_uid,
        config_entry=local,
        suggested_object_id="user_selected_auto_start_stop",
    )
    original_data = dict(local.data)
    original_options = dict(local.options)
    for _ in range(2):
        assert await hass.config_entries.async_setup(local.entry_id)
        runtime = runtime_for(hass, core)
        manager = fake_api.managers[MANAGER_NAME].create(runtime)
        manager.post_init(runtime.entry_infos)
        await hass.async_block_till_done()

        assert registry.async_get(legacy.entity_id).id == legacy.id
        assert registry.async_get(core_switch.entity_id) == core_switch
        assert registry.async_get(other_switch.entity_id) == other_switch
        assert local.data == original_data
        assert local.options == original_options
        assert manager.enabled is enabled
        assert manager.stop_mode == STOP_MODE_DRY
        assert registry.async_get_entity_id("select", DOMAIN, select_uid) == (
            existing_select.entity_id
        )
        assert hass.states.get(existing_select.entity_id).state == STOP_MODE_DRY
        assert hass.states.get(legacy.entity_id).state == ("on" if enabled else "off")
        assert await hass.config_entries.async_unload(local.entry_id)


@pytest.mark.parametrize("custom_ids", [False, True])
@pytest.mark.parametrize("existing_switch", [False, True])
@pytest.mark.parametrize("lookup", ["unique_id", "entry_id", "climate_registry"])
@pytest.mark.parametrize("global_coverage", [False, True])
async def test_historical_ids_preserve_card_services_and_later_user_renames(
    hass, fake_api, monkeypatch, custom_ids, existing_switch, lookup, global_coverage
):
    """Adopt exact core IDs once, including after global-only delegation."""
    import custom_components.vtherm_auto_start_stop.manager as manager_module

    monkeypatch.setattr(manager_module, "async_dispatcher_send", async_dispatcher_send)
    monkeypatch.setattr(
        hass.config_entries, "async_reload", AsyncMock(return_value=True)
    )
    ids = {
        "switch": "switch.thermostat_chambre_enable_auto_start_stop",
        "select": "select.chambre_thermostat_chambre_auto_start_stop_stop_mode",
    }
    if custom_ids:
        ids = {
            "switch": "switch.my_custom_activation",
            "select": "select.my_custom_mode",
        }
    core = register_core_entry(hass, "chambre")
    target_uid = core.unique_id
    registry = er.async_get(hass)
    if lookup != "unique_id":
        target_uid = core.entry_id
        hass.config_entries.async_update_entry(core, unique_id=None)
        if lookup == "climate_registry":
            registry.async_get_or_create(
                "climate",
                VT_DOMAIN,
                target_uid,
                config_entry=core,
                suggested_object_id="thermostat_chambre",
            )
    hass.config_entries.async_update_entry(
        core, data={**core.data, "auto_start_stop_entity_ids": ids}
    )
    global_entry = MockConfigEntry(domain=DOMAIN, data={CONF_ENABLED: False})
    if global_coverage:
        global_entry.add_to_hass(hass)

    local = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_VTHERM_UNIQUE_ID: target_uid,
            CONF_ENABLED: False,
            CONF_STOP_MODE: STOP_MODE_DRY,
        },
    )
    local.add_to_hass(hass)
    select_uid = f"{target_uid}_{ENTITY_STOP_MODE_SUFFIX}"
    switch_uid = f"{target_uid}_{ENTITY_ENABLE_SUFFIX}"
    old_select = registry.async_get_or_create(
        "select",
        DOMAIN,
        select_uid,
        config_entry=local,
        suggested_object_id="combined_plugin_test_select",
    )
    old_switch = None
    if existing_switch:
        old_switch = registry.async_get_or_create(
            "switch",
            DOMAIN,
            switch_uid,
            config_entry=local,
            suggested_object_id="earlier_plugin_test_switch",
        )
    if global_coverage:
        assert await hass.config_entries.async_setup(global_entry.entry_id)
    if local.state is not ConfigEntryState.LOADED:
        assert await hass.config_entries.async_setup(local.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get_entity_id("switch", DOMAIN, switch_uid) == ids["switch"]
    assert registry.async_get_entity_id("select", DOMAIN, select_uid) == ids["select"]
    assert registry.async_get(ids["select"]).id == old_select.id
    if old_switch is not None:
        assert registry.async_get(ids["switch"]).id == old_switch.id

    runtime = runtime_for(hass, core)
    manager = fake_api.managers[MANAGER_NAME].create(runtime)
    manager.post_init(runtime.entry_infos)
    await hass.async_block_till_done()
    card_config = {
        "autoStartStopEnableEntity": ids["switch"],
        "autoStartStopStopModeEntity": ids["select"],
    }
    assert hass.states.get(ids["switch"]).state == "off"
    assert hass.states.get(ids["select"]).state == STOP_MODE_DRY
    assert hass.states.get(ids["select"]).attributes["options"] == [
        STOP_MODE_OFF,
        STOP_MODE_FAN_ONLY,
        STOP_MODE_DRY,
    ]
    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": card_config["autoStartStopEnableEntity"]},
        blocking=True,
    )
    await hass.services.async_call(
        "select",
        "select_option",
        {
            "entity_id": card_config["autoStartStopStopModeEntity"],
            "option": STOP_MODE_FAN_ONLY,
        },
        blocking=True,
    )
    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": card_config["autoStartStopEnableEntity"]},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert manager.enabled is False
    assert manager.stop_mode == STOP_MODE_FAN_ONLY
    assert hass.states.get(ids["switch"]).state == "off"
    assert hass.states.get(ids["select"]).state == STOP_MODE_FAN_ONLY

    renamed_id = "select.user_renamed_after_migration"
    registry.async_update_entity(ids["select"], new_entity_id=renamed_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(local.entry_id)
    assert await hass.config_entries.async_setup(local.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get_entity_id("select", DOMAIN, select_uid) == renamed_id
    assert registry.async_get(renamed_id).id == old_select.id
    assert registry.async_get_entity_id("switch", DOMAIN, switch_uid) == ids["switch"]
    owner = global_entry if global_coverage else local
    assert len(er.async_entries_for_config_entry(registry, owner.entry_id)) == 2


@pytest.mark.parametrize("remembered", [False, True])
@pytest.mark.parametrize("cleanup_before_setup", [False, True])
async def test_core_cleanup_defers_the_whole_pair_and_recovers_deleted_history(
    hass, fake_api, monkeypatch, remembered, cleanup_before_setup
):
    """No suffixes, duplicates or metadata-only thermostat reloads."""
    core = register_core_entry(hass, "pending")
    local = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_VTHERM_UNIQUE_ID: core.unique_id, CONF_ENABLED: False},
    )
    local.add_to_hass(hass)
    registry = er.async_get(hass)
    historical = {}
    for domain, suffix in (
        ("switch", "enable_auto_start_stop"),
        ("select", "auto_start_stop_stop_mode"),
    ):
        legacy = registry.async_get_or_create(
            domain,
            VT_DOMAIN,
            f"{core.unique_id}_{suffix}",
            config_entry=core,
            suggested_object_id=f"original_pending_{suffix}",
        )
        historical[domain] = legacy.entity_id
    if remembered:
        hass.config_entries.async_update_entry(
            core, data={**core.data, "auto_start_stop_entity_ids": historical}
        )
    if cleanup_before_setup:
        for entity_id in historical.values():
            registry.async_remove(entity_id)
        await hass.async_block_till_done()
    reload = AsyncMock(return_value=True)
    monkeypatch.setattr(hass.config_entries, "async_reload", reload)
    assert await hass.config_entries.async_setup(local.entry_id)
    await hass.async_block_till_done()
    reload.reset_mock()
    if not cleanup_before_setup:
        assert er.async_entries_for_config_entry(registry, local.entry_id) == []
        assert not local.data.get(CONF_ENTITY_IDS_ADOPTED)
        registry.async_remove(historical["switch"])
        await hass.async_block_till_done()
        assert er.async_entries_for_config_entry(registry, local.entry_id) == []
        registry.async_remove(historical["select"])
        await hass.async_block_till_done()
    assert {
        entity.domain: entity.entity_id
        for entity in er.async_entries_for_config_entry(registry, local.entry_id)
    } == historical
    assert all(
        row.options[DOMAIN][CONF_ENTITY_IDS_ADOPTED]
        for row in er.async_entries_for_config_entry(registry, local.entry_id)
    )
    reload.assert_not_awaited()


@pytest.mark.parametrize("domain", ["switch", "select"])
@pytest.mark.parametrize("conflict", ["platform", "owner", "state", "plugin_unique_id"])
async def test_conflicting_identity_fails_setup_without_mutating_either_control(
    hass, fake_api, domain, conflict
):
    core = register_core_entry(hass, "conflict")
    historical = {
        "switch": "switch.historical_activation",
        "select": "select.historical_stop_mode",
    }
    hass.config_entries.async_update_entry(
        core, data={**core.data, "auto_start_stop_entity_ids": historical}
    )
    local = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_VTHERM_UNIQUE_ID: core.unique_id, CONF_ENABLED: False},
    )
    local.add_to_hass(hass)
    registry = er.async_get(hass)
    foreign = None
    if conflict == "state":
        hass.states.async_set(historical[domain], "off")
    else:
        platform, owner = VT_DOMAIN, core
        suffix = (
            "enable_auto_start_stop" if domain == "switch" else ENTITY_STOP_MODE_SUFFIX
        )
        if conflict == "platform":
            platform = "unrelated_integration"
        elif conflict == "owner":
            owner = register_core_entry(hass, "foreign")
        else:
            platform = DOMAIN
            owner = MockConfigEntry(
                domain=DOMAIN,
                data={CONF_VTHERM_UNIQUE_ID: "foreign"},
                disabled_by=ConfigEntryDisabler.USER,
            )
            owner.add_to_hass(hass)
            suffix = (
                ENTITY_ENABLE_SUFFIX if domain == "switch" else ENTITY_STOP_MODE_SUFFIX
            )
        foreign = registry.async_get_or_create(
            domain,
            platform,
            f"{core.unique_id}_{suffix}",
            config_entry=owner,
            suggested_object_id=historical[domain].split(".", 1)[1],
        )
    original_data = dict(local.data)
    assert not await hass.config_entries.async_setup(local.entry_id)
    await hass.async_block_till_done()
    assert local.state is ConfigEntryState.SETUP_ERROR
    assert local.data == original_data
    assert er.async_entries_for_config_entry(registry, local.entry_id) == []
    if foreign is not None:
        assert registry.async_get(foreign.entity_id) == foreign
    else:
        assert hass.states.get(historical[domain]).state == "off"
    free_domain = "select" if domain == "switch" else "switch"
    assert registry.async_get(historical[free_domain]) is None


@pytest.mark.parametrize(
    "invalid",
    [[], {"switch": None}, {"select": "switch.wrong"}, {"climate": "climate.wrong"}],
)
async def test_invalid_historical_identity_metadata_fails_explicitly(
    hass, fake_api, invalid
):
    core = register_core_entry(hass, "invalid")
    hass.config_entries.async_update_entry(
        core, data={**core.data, "auto_start_stop_entity_ids": invalid}
    )
    local = MockConfigEntry(domain=DOMAIN, data={CONF_VTHERM_UNIQUE_ID: core.unique_id})
    local.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(local.entry_id)
    assert local.state is ConfigEntryState.SETUP_ERROR
    assert er.async_entries_for_config_entry(er.async_get(hass), local.entry_id) == []


@pytest.mark.parametrize("unrelated", ["platform", "owner", "domain", "suffix"])
async def test_unrelated_deleted_history_is_neither_adopted_nor_removed(
    hass, fake_api, monkeypatch, unrelated
):
    monkeypatch.setattr(
        hass.config_entries, "async_reload", AsyncMock(return_value=True)
    )
    core = register_core_entry(hass, "local")
    registry = er.async_get(hass)
    owner, domain, platform = core, "select", VT_DOMAIN
    unique_id = f"{core.unique_id}_auto_start_stop_stop_mode"
    if unrelated == "platform":
        platform = "unrelated_integration"
    elif unrelated == "owner":
        owner = register_core_entry(hass, "other")
    elif unrelated == "domain":
        domain = "sensor"
    else:
        unique_id = f"{core.unique_id}_unrelated_mode"
    foreign = registry.async_get_or_create(
        domain,
        platform,
        unique_id,
        config_entry=owner,
        suggested_object_id="unrelated_historical_control",
    )
    registry.async_remove(foreign.entity_id)
    local = MockConfigEntry(domain=DOMAIN, data={CONF_VTHERM_UNIQUE_ID: core.unique_id})
    local.add_to_hass(hass)
    plugin_uid = f"{core.unique_id}_{ENTITY_STOP_MODE_SUFFIX}"
    existing = registry.async_get_or_create(
        "select",
        DOMAIN,
        plugin_uid,
        config_entry=local,
        suggested_object_id="keep_existing_plugin_mode",
    )
    assert await hass.config_entries.async_setup(local.entry_id)
    await hass.async_block_till_done()
    assert (
        registry.async_get_entity_id("select", DOMAIN, plugin_uid) == existing.entity_id
    )
    assert not local.data.get(CONF_ENTITY_IDS_ADOPTED)
    assert (
        registry.deleted_entities[(domain, platform, unique_id)].entity_id
        == foreign.entity_id
    )


async def test_pending_core_control_does_not_hide_a_conflict_on_the_other_control(
    hass, fake_api
):
    core = register_core_entry(hass, "pending")
    registry = er.async_get(hass)
    core_switch = registry.async_get_or_create(
        "switch",
        VT_DOMAIN,
        f"{core.unique_id}_enable_auto_start_stop",
        config_entry=core,
        suggested_object_id="pending_core_activation",
    )
    conflicting_select = registry.async_get_or_create(
        "select",
        "unrelated_integration",
        "foreign",
        config_entry=core,
        suggested_object_id="conflicting_stop_mode",
    )
    hass.config_entries.async_update_entry(
        core,
        data={
            **core.data,
            "auto_start_stop_entity_ids": {
                "switch": core_switch.entity_id,
                "select": conflicting_select.entity_id,
            },
        },
    )
    local = MockConfigEntry(domain=DOMAIN, data={CONF_VTHERM_UNIQUE_ID: core.unique_id})
    local.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(local.entry_id)
    assert local.state is ConfigEntryState.SETUP_ERROR
    assert registry.async_get(core_switch.entity_id) == core_switch
    assert registry.async_get(conflicting_select.entity_id) == conflicting_select
    assert er.async_entries_for_config_entry(registry, local.entry_id) == []
