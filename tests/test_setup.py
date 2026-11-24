"""Integration setup and factory registration (tasks 1.1, 1.3)."""

from __future__ import annotations

from unittest.mock import AsyncMock, call

import pytest
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
    STOP_MODE_FAN_ONLY,
    VT_DOMAIN,
)
from custom_components.vtherm_auto_start_stop.factory import (
    AutoStartStopManagerFactory,
    register_factory,
    unregister_factory,
)
from custom_components.vtherm_auto_start_stop.select import AutoStartStopStopModeSelect
from custom_components.vtherm_auto_start_stop.switch import AutoStartStopEnableSwitch
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


def register_core_entry(hass, unique_id):
    entry = MockConfigEntry(
        domain=VT_DOMAIN,
        unique_id=unique_id,
        data={"thermostat_type": "thermostat_over_climate"},
    )
    entry.add_to_hass(hass)
    return entry


def runtime_for(hass, core_entry):
    runtime = FakeThermostat(hass, core_entry.unique_id)
    runtime.entry_infos = dict(core_entry.data)
    return runtime


@pytest.mark.parametrize("global_enabled", [False, True])
async def test_global_option_changes_preserve_dedicated_overrides(
    hass, fake_api, monkeypatch, global_enabled
):
    """Only inheriting thermostats reload when a full override exists."""
    local_core = register_core_entry(hass, "local")
    other_core = register_core_entry(hass, "other")
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
            CONF_VTHERM_UNIQUE_ID: local_core.unique_id,
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
        assert reload.await_args_list == [call(other_core.entry_id)]
        for core, expected in (
            (local_core, not global_enabled), (other_core, enabled)
        ):
            runtime = runtime_for(hass, core)
            assert factory.supports(runtime)
            manager = factory.create(runtime)
            manager.post_init(runtime.entry_infos)
            assert manager.enabled is expected


@pytest.mark.parametrize("enabled", [False, True])
async def test_removing_dedicated_entry_restores_global(
    hass, fake_api, monkeypatch, enabled
):
    core = register_core_entry(hass, "local")
    reload = AsyncMock(return_value=True)
    monkeypatch.setattr(hass.config_entries, "async_reload", reload)
    global_entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_ENABLED: enabled}
    )
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
        call(local_core.entry_id), call(other_core.entry_id)
    ]
    factory = fake_api.managers[MANAGER_NAME]
    local_runtime = runtime_for(hass, local_core)
    assert factory.supports(local_runtime)
    assert factory.supports(runtime_for(hass, other_core)) is (not remove)
    manager = factory.create(local_runtime)
    manager.post_init(local_runtime.entry_infos)
    assert manager.enabled is False
    assert manager._algorithm.level == LEVEL_SLOW


async def test_disabled_dedicated_controls_follow_configuration_and_can_be_recreated(
    hass, fake_api, monkeypatch
):
    """Persisted settings win over restored entity state and survive edits."""
    import custom_components.vtherm_auto_start_stop.manager as manager_module

    monkeypatch.setattr(manager_module, "async_dispatcher_send", async_dispatcher_send)
    core = register_core_entry(hass, "local")
    monkeypatch.setattr(
        hass.config_entries, "async_reload", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        AutoStartStopEnableSwitch, "async_get_last_state",
        AsyncMock(return_value=State("switch.previous", "on")),
    )
    monkeypatch.setattr(
        AutoStartStopStopModeSelect, "async_get_last_state",
        AsyncMock(return_value=State("select.previous", "dry")),
    )
    global_entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_ENABLED: False}
    )
    global_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(global_entry.entry_id)
    await hass.async_block_till_done()

    registry = er.async_get(hass)
    switch_uid = f"{core.unique_id}_{ENTITY_ENABLE_SUFFIX}"
    select_uid = f"{core.unique_id}_{ENTITY_STOP_MODE_SUFFIX}"
    assert registry.async_get_entity_id("switch", DOMAIN, switch_uid) is None
    assert registry.async_get_entity_id("select", DOMAIN, select_uid) is None

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
    assert await hass.config_entries.async_setup(local_entry.entry_id)
    await hass.async_block_till_done()

    switch_id = registry.async_get_entity_id("switch", DOMAIN, switch_uid)
    select_id = registry.async_get_entity_id("select", DOMAIN, select_uid)
    assert manager.enabled is False
    assert manager.stop_mode == STOP_MODE_OFF
    assert hass.states.get(switch_id).state == "off"
    assert hass.states.get(select_id).state == STOP_MODE_OFF

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": switch_id}, blocking=True
    )
    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": select_id, "option": STOP_MODE_FAN_ONLY}, blocking=True,
    )
    await hass.async_block_till_done()
    assert manager.enabled is True
    assert manager.stop_mode == STOP_MODE_FAN_ONLY
    assert local_entry.options[CONF_ENABLED] is True
    assert local_entry.options[CONF_VTHERM_UNIQUE_ID] == core.unique_id
    assert hass.data[DOMAIN]["entries"][local_entry.entry_id][CONF_ENABLED] is True
    assert hass.data[DOMAIN]["entries"][global_entry.entry_id][CONF_ENABLED] is False
    assert hass.states.get(switch_id).state == "on"

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
    assert hass.states.get(select_id).state == STOP_MODE_OFF

    assert await hass.config_entries.async_remove(local_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(switch_id) is None
    assert hass.states.get(select_id) is None

    replacement = MockConfigEntry(domain=DOMAIN, data=data)
    replacement.add_to_hass(hass)
    assert await hass.config_entries.async_setup(replacement.entry_id)
    await hass.async_block_till_done()
    switch_id = registry.async_get_entity_id("switch", DOMAIN, switch_uid)
    select_id = registry.async_get_entity_id("select", DOMAIN, select_uid)
    assert switch_id is not None
    assert select_id is not None
    assert hass.states.get(switch_id).state == "off"
    assert hass.states.get(select_id).state == STOP_MODE_OFF
