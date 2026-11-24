"""Global control coverage and persistent entity-owned operational states."""

from unittest.mock import AsyncMock

import pytest
from homeassistant.core import State
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er, restore_state as rs
from homeassistant.helpers.dispatcher import async_dispatcher_send

from custom_components.vtherm_auto_start_stop.const import (
    CONF_ENABLED, CONF_ENTITY_IDS_ADOPTED, CONF_LEVEL, CONF_STOP_MODE, CONF_VTHERM_UNIQUE_ID,
    DATA_ENTRIES, DOMAIN, ENTITY_ENABLE_SUFFIX,
    ENTITY_STOP_MODE_SUFFIX, LEVEL_FAST, LEVEL_SLOW, MANAGER_NAME, VT_DOMAIN,
)
from custom_components.vtherm_auto_start_stop.registry import ensure_entities, get_manager
from tests.test_setup import (
    custom_integrations, fake_api, mock_versatile_thermostat,
    register_core_entry, runtime_for,
)
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry, mock_restore_cache, mock_restore_cache_with_extra_data,
)


@pytest.fixture(autouse=True)
def runtime_dispatcher(monkeypatch):
    monkeypatch.setattr(
        "custom_components.vtherm_auto_start_stop.manager.async_dispatcher_send",
        async_dispatcher_send,
    )
    monkeypatch.setattr(
        "custom_components.vtherm_auto_start_stop.manager.ensure_entities",
        ensure_entities,
    )


def attach_managers(hass, fake_api, cores):
    managers = []
    for core in cores:
        runtime = runtime_for(hass, core)
        manager = fake_api.managers[MANAGER_NAME].create(runtime)
        manager.post_init(runtime.entry_infos)
        managers.append(manager)
    return managers


async def test_global_only_entities_do_not_create_or_modify_configurations(
    hass, fake_api, monkeypatch
):
    monkeypatch.setattr(hass.config_entries, "async_reload", AsyncMock(return_value=True))
    cores = [register_core_entry(hass, name) for name in ("chambre", "salon")]
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_LEVEL: LEVEL_FAST, CONF_ENABLED: False, CONF_STOP_MODE: "off"
    })
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    managers = attach_managers(hass, fake_api, cores)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    switches, selects = [], []
    for core in cores:
        switches.append(registry.async_get_entity_id(
            "switch", DOMAIN, f"{core.unique_id}_{ENTITY_ENABLE_SUFFIX}"
        ))
        selects.append(registry.async_get_entity_id(
            "select", DOMAIN, f"{core.unique_id}_{ENTITY_STOP_MODE_SUFFIX}"
        ))
    assert all(switches) and all(selects)
    assert len(er.async_entries_for_config_entry(registry, entry.entry_id)) == 4
    before_data, before_options = dict(entry.data), dict(entry.options)
    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": selects[0], "option": "dry"}, blocking=True,
    )
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": switches[0]}, blocking=True,
    )
    assert managers[0].enabled is True and managers[0].stop_mode == "dry"
    assert managers[1].enabled is False and managers[1].stop_mode == "off"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert entry.data == before_data and entry.options == before_options
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    managers = attach_managers(hass, fake_api, cores)
    await hass.async_block_till_done()
    assert hass.states.get(switches[0]).state == "on"
    assert hass.states.get(selects[0]).state == "dry"
    assert hass.states.get(switches[1]).state == "off"


@pytest.fixture
async def global_controls(hass, fake_api, monkeypatch):
    reload = AsyncMock(return_value=True)
    monkeypatch.setattr(hass.config_entries, "async_reload", reload)
    cores = [register_core_entry(hass, name) for name in ("chambre", "salon")]
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_LEVEL: LEVEL_FAST, CONF_ENABLED: False, CONF_STOP_MODE: "off"
    })
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    managers = attach_managers(hass, fake_api, cores)
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    ids = [{
        "switch": registry.async_get_entity_id("switch", DOMAIN, f"{core.unique_id}_{ENTITY_ENABLE_SUFFIX}"),
        "select": registry.async_get_entity_id("select", DOMAIN, f"{core.unique_id}_{ENTITY_STOP_MODE_SUFFIX}"),
    } for core in cores]
    return entry, cores, managers, ids, reload


async def test_default_edits_initialize_only_new_entities(
    hass, fake_api, global_controls
):
    entry, cores, managers, ids, reload = global_controls
    await hass.services.async_call(
        "select", "select_option", {"entity_id": ids[0]["select"], "option": "dry"}, blocking=True
    )
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": ids[0]["switch"]}, blocking=True
    )
    reload.reset_mock()
    hass.config_entries.async_update_entry(
        entry, options={CONF_ENABLED: True, CONF_STOP_MODE: "fan_only"}
    )
    await hass.async_block_till_done()
    reload.assert_not_awaited()
    assert [(manager.enabled, manager.stop_mode) for manager in managers] == [
        (True, "dry"), (False, "off")
    ]
    replacements = attach_managers(hass, fake_api, cores)
    assert [(manager.enabled, manager.stop_mode) for manager in replacements] == [
        (True, "dry"), (False, "off")
    ]
    core = register_core_entry(hass, "new")
    new = attach_managers(hass, fake_api, [core])[0]
    await hass.async_block_till_done()
    assert new.enabled is True and new.stop_mode == "fan_only"
    registry = er.async_get(hass)
    assert len(er.async_entries_for_config_entry(registry, entry.entry_id)) == 6
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    restored = attach_managers(hass, fake_api, [*cores, core])
    await hass.async_block_till_done()
    assert [(manager.enabled, manager.stop_mode) for manager in restored] == [
        (True, "dry"), (False, "off"), (True, "fan_only")
    ]
    reload.reset_mock()
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_LEVEL: LEVEL_SLOW}
    )
    await hass.async_block_till_done()
    assert {args.args[0] for args in reload.await_args_list} == {
        core.entry_id for core in [*cores, core]
    }
    for manager in restored:
        manager.post_init({})
        assert manager._algorithm.level == LEVEL_SLOW
    assert [(manager.enabled, manager.stop_mode) for manager in restored] == [
        (True, "dry"), (False, "off"), (True, "fan_only")
    ]


async def test_failed_platform_unload_preserves_controls(hass, global_controls, monkeypatch):
    entry, _, managers, ids, _ = global_controls
    monkeypatch.setattr(hass.config_entries, "async_unload_platforms", AsyncMock(return_value=False))
    assert not await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert all(manager.is_configured for manager in managers)
    assert all(hass.states.get(pair["switch"]).state == "off" for pair in ids)


async def test_ownership_handover_and_coverage_removal(hass, fake_api, global_controls):
    global_entry, cores, managers, ids, _ = global_controls
    registry = er.async_get(hass)
    original_rows = {entity_id: registry.async_get(entity_id).id for pair in ids for entity_id in pair.values()}
    await hass.services.async_call(
        "select", "select_option", {"entity_id": ids[0]["select"], "option": "dry"}, blocking=True
    )
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": ids[0]["switch"]}, blocking=True
    )
    local = MockConfigEntry(domain=DOMAIN, data={
        CONF_VTHERM_UNIQUE_ID: cores[0].unique_id, CONF_LEVEL: LEVEL_SLOW
    })
    local.add_to_hass(hass)
    assert await hass.config_entries.async_setup(local.entry_id)
    await hass.async_block_till_done()
    assert er.async_entries_for_config_entry(registry, local.entry_id) == []
    assert await hass.config_entries.async_unload(local.entry_id)
    assert await hass.config_entries.async_setup(local.entry_id)
    await hass.async_block_till_done()
    assert {entity_id: registry.async_get(entity_id).id for pair in ids for entity_id in pair.values()} == original_rows
    assert await hass.config_entries.async_remove(global_entry.entry_id)
    await hass.async_block_till_done()
    assert {row.entity_id for row in er.async_entries_for_config_entry(registry, local.entry_id)} == set(ids[0].values())
    assert all(registry.async_get(entity_id) is None for entity_id in ids[1].values())
    assert all(hass.states.get(entity_id) is None for entity_id in ids[1].values())
    assert managers[1].is_configured is False
    assert get_manager(hass, cores[1].unique_id) is None
    replacement = attach_managers(hass, fake_api, [cores[0]])[0]
    await hass.async_block_till_done()
    assert replacement.enabled is True and replacement.stop_mode == "dry"
    assert replacement._algorithm.level == LEVEL_SLOW
    assert all(registry.async_get(entity_id).id == original_rows[entity_id] for entity_id in ids[0].values())
    assert await hass.config_entries.async_remove(local.entry_id)
    await hass.async_block_till_done()
    assert all(registry.async_get(entity_id) is None for entity_id in ids[0].values())
    assert all(hass.states.get(entity_id) is None for entity_id in ids[0].values())


async def test_global_addition_preserves_dedicated_entity_states(hass, fake_api, monkeypatch):
    monkeypatch.setattr(hass.config_entries, "async_reload", AsyncMock(return_value=True))
    core = register_core_entry(hass, "local")
    local = MockConfigEntry(domain=DOMAIN, data={
        CONF_VTHERM_UNIQUE_ID: core.unique_id, CONF_LEVEL: LEVEL_SLOW
    })
    local.add_to_hass(hass)
    assert await hass.config_entries.async_setup(local.entry_id)
    await hass.async_block_till_done()
    manager = attach_managers(hass, fake_api, [core])[0]
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    rows = er.async_entries_for_config_entry(registry, local.entry_id)
    ids = {row.domain: row.entity_id for row in rows}
    await hass.services.async_call(
        "select", "select_option", {"entity_id": ids["select"], "option": "dry"}, blocking=True
    )
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": ids["switch"]}, blocking=True
    )
    global_entry = MockConfigEntry(domain=DOMAIN, data={CONF_ENABLED: False, CONF_STOP_MODE: "off"})
    global_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(global_entry.entry_id)
    await hass.async_block_till_done()
    assert {row.id for row in er.async_entries_for_config_entry(registry, global_entry.entry_id)} == {row.id for row in rows}
    assert manager.enabled is True and manager.stop_mode == "dry"
    assert hass.states.get(ids["switch"]).state == "on"
    assert hass.states.get(ids["select"]).state == "dry"
    assert await hass.config_entries.async_remove(local.entry_id)
    await hass.async_block_till_done()
    manager.post_init({})
    assert manager.enabled is True and manager.stop_mode == "dry"


@pytest.mark.parametrize("versioned", [False, True])
@pytest.mark.parametrize("saved", ["switch", "select", "both"])
async def test_native_restoration_and_one_time_legacy_migration(
    hass, fake_api, monkeypatch, versioned, saved
):
    monkeypatch.setattr(hass.config_entries, "async_reload", AsyncMock(return_value=True))
    core = register_core_entry(hass, "chambre")
    ids = {"switch": "switch.historical_enable", "select": "select.historical_mode"}
    hass.config_entries.async_update_entry(
        core, data={**core.data, "auto_start_stop_entity_ids": ids}
    )
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_VTHERM_UNIQUE_ID: core.unique_id, CONF_ENABLED: False, CONF_STOP_MODE: "dry"
    })
    entry.add_to_hass(hass)
    states = [State(ids[domain], "on" if domain == "switch" else "fan_only")
              for domain in ids if saved in (domain, "both")]
    if versioned:
        mock_restore_cache_with_extra_data(hass, [
            (state, {f"{DOMAIN}_state_version": 1, "value": state.state == "on" if state.domain == "switch" else state.state})
            for state in states
        ])
    else:
        mock_restore_cache(hass, states)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    manager = attach_managers(hass, fake_api, [core])[0]
    await hass.async_block_till_done()
    assert manager.enabled is (versioned and saved in ("switch", "both"))
    assert manager.stop_mode == ("fan_only" if versioned and saved in ("select", "both") else "dry")
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": ids["switch"]}, blocking=True
    )
    await hass.services.async_call(
        "select", "select_option", {"entity_id": ids["select"], "option": "off"}, blocking=True
    )
    assert entry.options == {}
    assert entry.data[CONF_ENABLED] is False and entry.data[CONF_STOP_MODE] == "dry"
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert DOMAIN not in hass.data
    stored = rs.async_get(hass).last_states
    serialized = [(stored[entity_id].state, stored[entity_id].extra_data.as_dict()) for entity_id in ids.values()]
    mock_restore_cache_with_extra_data(hass, serialized)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    manager = attach_managers(hass, fake_api, [core])[0]
    await hass.async_block_till_done()
    assert manager.enabled is True and manager.stop_mode == "off"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


@pytest.mark.parametrize("mode", ["heat", "dry"])
async def test_invalid_restored_mode_is_reported_without_enabling(
    hass, fake_api, monkeypatch, caplog, mode
):
    monkeypatch.setattr(hass.config_entries, "async_reload", AsyncMock(return_value=True))
    core = register_core_entry(hass, "local")
    ids = {"switch": "switch.historical_enable", "select": "select.historical_mode"}
    hass.config_entries.async_update_entry(core, data={**core.data, "auto_start_stop_entity_ids": ids})
    mock_restore_cache_with_extra_data(hass, [
        (State(ids["switch"], "off"), {f"{DOMAIN}_state_version": 1, "value": False}),
        (State(ids["select"], mode), {f"{DOMAIN}_state_version": 1, "value": mode}),
    ])
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_ENABLED: True, CONF_STOP_MODE: "fan_only"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    runtime = runtime_for(hass, core)
    runtime.vtherm_hvac_modes = ["off", "heat"]
    manager = fake_api.managers[MANAGER_NAME].create(runtime)
    manager.post_init(runtime.entry_infos)
    await hass.async_block_till_done()
    assert manager.enabled is False and manager.stop_mode == "off"
    assert hass.states.get(ids["select"]).state == "off"
    assert hass.states.get(ids["select"]).attributes["options"] == ["off"]
    assert "unsupported" in caplog.text or "invalid saved control" in caplog.text
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "select", "select_option", {"entity_id": ids["select"], "option": "dry"}, blocking=True
        )
    assert entry.options == {}
    assert manager.enabled is False and manager.stop_mode == "off"


@pytest.mark.parametrize("saved", ["switch", "select", "both"])
async def test_global_controls_retain_partial_historical_core_states(
    hass, fake_api, monkeypatch, saved
):
    monkeypatch.setattr(hass.config_entries, "async_reload", AsyncMock(return_value=True))
    core = register_core_entry(hass, "chambre")
    ids = {
        "switch": "switch.thermostat_chambre_enable_auto_start_stop",
        "select": "select.chambre_thermostat_chambre_auto_start_stop_stop_mode",
    }
    hass.config_entries.async_update_entry(core, data={**core.data, "auto_start_stop_entity_ids": ids})
    mock_restore_cache(hass, [
        State(ids[domain], "on" if domain == "switch" else "dry")
        for domain in ids if saved in (domain, "both")
    ])
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_ENABLED: False, CONF_STOP_MODE: "off"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    manager = attach_managers(hass, fake_api, [core])[0]
    await hass.async_block_till_done()
    assert manager.enabled is (saved in ("switch", "both"))
    assert manager.stop_mode == ("dry" if saved in ("select", "both") else "off")
    registry = er.async_get(hass)
    assert {row.entity_id for row in er.async_entries_for_config_entry(registry, entry.entry_id)} == set(ids.values())
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_adoption_is_per_entity_including_later_thermostats(
    hass, fake_api, global_controls
):
    entry, _, _, _, _ = global_controls
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_ENTITY_IDS_ADOPTED: True}
    )
    await hass.async_block_till_done()
    core = register_core_entry(hass, "new")
    ids = {"switch": "switch.new_historical_enable", "select": "select.new_historical_mode"}
    hass.config_entries.async_update_entry(core, data={**core.data, "auto_start_stop_entity_ids": ids})
    registry = er.async_get(hass)
    previous = registry.async_get_or_create(
        "select", DOMAIN, f"{core.unique_id}_{ENTITY_STOP_MODE_SUFFIX}",
        config_entry=entry, suggested_object_id="obsolete_plugin_name",
    )
    attach_managers(hass, fake_api, [core])
    await hass.async_block_till_done()
    assert registry.async_get(ids["select"]).id == previous.id
    for domain, entity_id in ids.items():
        assert registry.async_get(entity_id).options[DOMAIN][CONF_ENTITY_IDS_ADOPTED] is True
        renamed = f"{domain}.user_renamed_new_{domain}"
        registry.async_update_entity(entity_id, new_entity_id=renamed)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    for domain in ids:
        assert registry.async_get(f"{domain}.user_renamed_new_{domain}") is not None
        assert registry.async_get(ids[domain]) is None


async def test_old_dedicated_adoption_flag_preserves_existing_renames(
    hass, fake_api, monkeypatch
):
    monkeypatch.setattr(hass.config_entries, "async_reload", AsyncMock(return_value=True))
    core = register_core_entry(hass, "local")
    ids = {"switch": "switch.original_activation", "select": "select.original_mode"}
    hass.config_entries.async_update_entry(core, data={**core.data, "auto_start_stop_entity_ids": ids})
    local = MockConfigEntry(domain=DOMAIN, data={
        CONF_VTHERM_UNIQUE_ID: core.unique_id, CONF_ENTITY_IDS_ADOPTED: True,
    })
    local.add_to_hass(hass)
    registry = er.async_get(hass)
    existing = registry.async_get_or_create(
        "select", DOMAIN, f"{core.unique_id}_{ENTITY_STOP_MODE_SUFFIX}",
        config_entry=local, suggested_object_id="already_renamed_mode",
    )
    assert await hass.config_entries.async_setup(local.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get(existing.entity_id).id == existing.id
    assert registry.async_get(existing.entity_id).options[DOMAIN][CONF_ENTITY_IDS_ADOPTED] is True
    assert registry.async_get(ids["switch"]) is not None
    assert registry.async_get(ids["select"]) is None
    global_entry = MockConfigEntry(domain=DOMAIN, data={CONF_ENABLED: False})
    global_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(global_entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get(existing.entity_id).id == existing.id
    assert registry.async_get(existing.entity_id).config_entry_id == global_entry.entry_id
    assert registry.async_get(ids["select"]) is None


async def test_global_discovery_excludes_initially_ineligible_thermostats(
    hass, fake_api, monkeypatch
):
    monkeypatch.setattr(hass.config_entries, "async_reload", AsyncMock(return_value=True))
    eligible = register_core_entry(hass, "eligible")
    valve = register_core_entry(hass, "valve")
    other_type = register_core_entry(hass, "switch")
    hass.config_entries.async_update_entry(
        valve, data={**valve.data, "auto_regulation_mode": "auto_regulation_valve"}
    )
    hass.config_entries.async_update_entry(
        other_type, data={"thermostat_type": "thermostat_over_switch"}
    )
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_ENABLED: False})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    rows = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
    assert len(rows) == 2
    assert all(row.unique_id.startswith(f"{eligible.unique_id}_") for row in rows)


@pytest.mark.parametrize("kind", ["valve", "switch"])
async def test_eligibility_changes_remove_controls_and_managers(
    hass, fake_api, global_controls, kind
):
    entry, cores, managers, ids, _ = global_controls
    await hass.services.async_call(
        "select", "select_option",
        {"entity_id": ids[0]["select"], "option": "dry"}, blocking=True,
    )
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": ids[0]["switch"]}, blocking=True,
    )
    runtime = runtime_for(hass, cores[0])
    if kind == "valve":
        runtime.has_valve_regulation = True
    else:
        runtime.entry_infos["thermostat_type"] = "thermostat_over_switch"
    factory = fake_api.managers[MANAGER_NAME]
    assert factory.supports(runtime) is False
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    assert all(registry.async_get(entity_id) is None for entity_id in ids[0].values())
    assert all(hass.states.get(entity_id) is None for entity_id in ids[0].values())
    assert get_manager(hass, cores[0].unique_id) is None
    assert managers[0].is_configured is False
    assert len(er.async_entries_for_config_entry(registry, entry.entry_id)) == 2
    runtime.has_valve_regulation = False
    runtime.entry_infos = dict(cores[0].data)
    assert factory.supports(runtime) is True
    manager = factory.create(runtime)
    manager.post_init(runtime.entry_infos)
    await hass.async_block_till_done()
    assert len(er.async_entries_for_config_entry(registry, entry.entry_id)) == 4
    assert manager.enabled is True and manager.stop_mode == "dry"
