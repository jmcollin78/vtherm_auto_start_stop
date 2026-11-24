"""Entity creation (tasks 5.1, 5.2, 5.3)."""

from __future__ import annotations

import pytest

from custom_components.vtherm_auto_start_stop.const import (
    CONF_ENABLED,
    CONF_VTHERM_UNIQUE_ID,
    DATA_ADD_ENTITIES,
    DATA_CREATED,
    DOMAIN,
)
from custom_components.vtherm_auto_start_stop.registry import (
    dedicated_entry,
    ensure_entities,
    get_manager,
    register_callback,
    reset_entities,
)
from tests.conftest import make_entry

VT = "vtherm-uid-1"


@pytest.fixture
def captured(monkeypatch):
    """Replace the select class by a recorder."""
    import custom_components.vtherm_auto_start_stop.select as select_module

    created = []

    class FakeSelect:
        def __init__(self, hass, entry, unique_id):
            self.args = (hass, entry, unique_id)

    monkeypatch.setattr(select_module, "AutoStartStopStopModeSelect", FakeSelect)
    return created


def add_select_callback(fake_hass, unique_id=VT, created=None):
    """Register the select callback, as the platform does on setup."""
    register_callback(fake_hass, unique_id, created.extend)


@pytest.mark.parametrize("enabled", [False, True])
def test_entities_created_for_a_dedicated_entry(fake_hass, captured, enabled):
    """Task 5.1: a dedicated instance owns exactly one select."""
    fake_hass.config_entries.entries.append(
        make_entry(
            {CONF_VTHERM_UNIQUE_ID: VT},
            entry_id="ded",
            options={CONF_ENABLED: enabled},
        )
    )
    add_select_callback(fake_hass, created=captured)
    ensure_entities(fake_hass, VT)

    assert len(captured) == 1
    assert fake_hass.data[DOMAIN][DATA_CREATED][VT] is True


def test_no_entity_without_a_dedicated_entry(fake_hass, captured):
    """Task 5.1: a thermostat configured only globally owns no entity."""
    add_select_callback(fake_hass, created=captured)
    ensure_entities(fake_hass, VT)

    assert captured == []
    assert VT not in fake_hass.data[DOMAIN].get(DATA_CREATED, {})


def test_entities_created_once(fake_hass, captured):
    """A second registration does not duplicate the entities."""
    fake_hass.config_entries.entries.append(
        make_entry({CONF_VTHERM_UNIQUE_ID: VT}, entry_id="ded")
    )
    add_select_callback(fake_hass, created=captured)
    ensure_entities(fake_hass, VT)
    ensure_entities(fake_hass, VT)

    assert len(captured) == 1


def test_entities_wait_for_the_select_callback(fake_hass, captured):
    """Registration is deferred until the dedicated platform is ready."""
    fake_hass.config_entries.entries.append(
        make_entry({CONF_VTHERM_UNIQUE_ID: VT}, entry_id="ded")
    )
    ensure_entities(fake_hass, VT)
    assert captured == []
    add_select_callback(fake_hass, created=captured)
    ensure_entities(fake_hass, VT)
    assert len(captured) == 1


def test_entities_recreated_after_a_reset(fake_hass, captured):
    """A reload forgets the creation marker and rebuilds the entities once."""
    fake_hass.config_entries.entries.append(
        make_entry({CONF_VTHERM_UNIQUE_ID: VT}, entry_id="ded")
    )
    add_select_callback(fake_hass, created=captured)
    ensure_entities(fake_hass, VT)
    reset_entities(fake_hass, VT)
    ensure_entities(fake_hass, VT)

    assert len(captured) == 2


def test_missing_callbacks_are_ignored(fake_hass, captured):
    ensure_entities(fake_hass, VT)
    assert fake_hass.data[DOMAIN].get(DATA_ADD_ENTITIES, {}) == {}


def test_get_manager_returns_none_before_registration(fake_hass):
    assert get_manager(fake_hass, VT) is None
