"""Entity creation (tasks 5.1, 5.2, 5.3)."""

from __future__ import annotations

import pytest

from custom_components.vtherm_auto_start_stop.const import (
    CONF_ENABLED,
    CONF_VTHERM_UNIQUE_ID,
    DATA_ADD_ENTITIES,
    DATA_CREATED,
    DOMAIN,
    PLATFORMS,
    PLATFORM_SELECT,
    PLATFORM_SWITCH,
)
from custom_components.vtherm_auto_start_stop.registry import (
    dedicated_entry,
    ensure_entities,
    get_manager,
    register_callback,
    reset_entities,
    unregister_callback,
)
from tests.conftest import make_entry

VT = "vtherm-uid-1"


@pytest.fixture
def captured(monkeypatch):
    """Replace the control classes by recorders."""
    import custom_components.vtherm_auto_start_stop.select as select_module
    import custom_components.vtherm_auto_start_stop.switch as switch_module

    monkeypatch.setattr(
        "custom_components.vtherm_auto_start_stop.registry.prepare_entity_ids",
        lambda *args: True,
    )
    created = {platform: [] for platform in PLATFORMS}

    class FakeControl:
        def __init__(self, hass, entry, unique_id):
            self.args = (hass, entry, unique_id)

    monkeypatch.setattr(select_module, "AutoStartStopStopModeSelect", FakeControl)
    monkeypatch.setattr(switch_module, "AutoStartStopEnableSwitch", FakeControl)
    return created


def add_platforms(fake_hass, unique_id=VT, created=None):
    """Register the callbacks of both dedicated platforms."""
    for platform in PLATFORMS:
        register_callback(fake_hass, platform, unique_id, created[platform].extend)


@pytest.mark.parametrize("enabled", [False, True])
def test_entities_created_for_a_dedicated_entry(fake_hass, captured, enabled):
    """Task 5.1: a dedicated instance owns one switch and one select."""
    fake_hass.config_entries.entries.append(
        make_entry(
            {CONF_VTHERM_UNIQUE_ID: VT},
            entry_id="ded",
            options={CONF_ENABLED: enabled},
        )
    )
    add_platforms(fake_hass, created=captured)
    ensure_entities(fake_hass, VT)

    assert all(len(entities) == 1 for entities in captured.values())
    assert fake_hass.data[DOMAIN][DATA_CREATED][VT] is True


def test_no_entity_without_a_dedicated_entry(fake_hass, captured):
    """Task 5.1: a thermostat configured only globally owns no entity."""
    add_platforms(fake_hass, created=captured)
    ensure_entities(fake_hass, VT)

    assert all(entities == [] for entities in captured.values())
    assert VT not in fake_hass.data[DOMAIN].get(DATA_CREATED, {})


def test_entities_created_once(fake_hass, captured):
    """A second registration does not duplicate the entities."""
    fake_hass.config_entries.entries.append(
        make_entry({CONF_VTHERM_UNIQUE_ID: VT}, entry_id="ded")
    )
    add_platforms(fake_hass, created=captured)
    ensure_entities(fake_hass, VT)
    ensure_entities(fake_hass, VT)

    assert all(len(entities) == 1 for entities in captured.values())


def test_entities_wait_for_both_platform_callbacks(fake_hass, captured):
    """Registration is deferred until both dedicated platforms are ready."""
    fake_hass.config_entries.entries.append(
        make_entry({CONF_VTHERM_UNIQUE_ID: VT}, entry_id="ded")
    )
    register_callback(fake_hass, PLATFORM_SWITCH, VT, captured[PLATFORM_SWITCH].extend)
    ensure_entities(fake_hass, VT)
    assert all(entities == [] for entities in captured.values())
    register_callback(fake_hass, PLATFORM_SELECT, VT, captured[PLATFORM_SELECT].extend)
    ensure_entities(fake_hass, VT)
    assert all(len(entities) == 1 for entities in captured.values())


def test_entities_recreated_after_a_reset(fake_hass, captured):
    """A reload forgets the creation marker and rebuilds the entities once."""
    fake_hass.config_entries.entries.append(
        make_entry({CONF_VTHERM_UNIQUE_ID: VT}, entry_id="ded")
    )
    add_platforms(fake_hass, created=captured)
    ensure_entities(fake_hass, VT)
    reset_entities(fake_hass, VT)
    ensure_entities(fake_hass, VT)

    assert all(len(entities) == 2 for entities in captured.values())


def test_missing_callbacks_are_ignored(fake_hass, captured):
    ensure_entities(fake_hass, VT)
    assert fake_hass.data[DOMAIN].get(DATA_ADD_ENTITIES, {}) == {}


def test_unloading_both_platforms_releases_all_callbacks(fake_hass, captured):
    add_platforms(fake_hass, created=captured)
    unregister_callback(fake_hass, PLATFORM_SWITCH, VT)
    assert set(fake_hass.data[DOMAIN][DATA_ADD_ENTITIES][VT]) == {PLATFORM_SELECT}
    unregister_callback(fake_hass, PLATFORM_SELECT, VT)
    assert fake_hass.data[DOMAIN][DATA_ADD_ENTITIES] == {}


def test_get_manager_returns_none_before_registration(fake_hass):
    assert get_manager(fake_hass, VT) is None
