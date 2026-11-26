"""Entity creation (tasks 5.1, 5.2, 5.3)."""

from __future__ import annotations

import pytest

from custom_components.vtherm_auto_start_stop.const import (
    CONF_ENABLED,
    CONF_VTHERM_UNIQUE_ID,
    DATA_ADD_ENTITIES,
    DATA_CREATED,
    DATA_ENTITIES,
    DATA_ENTRIES,
    DOMAIN,
    PLATFORM_NUMBER,
    PLATFORM_SELECT,
    PLATFORM_SWITCH,
    PLATFORMS,
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

#: The number of controls the registry creates per platform: one switch, the
#: stop-mode select and the level select, then the two parameter numbers.
EXPECTED_PER_PLATFORM = {
    PLATFORM_SWITCH: 1,
    PLATFORM_SELECT: 2,
    PLATFORM_NUMBER: 2,
}


def counts(captured) -> dict[str, int]:
    """Return the number of controls created per platform."""
    return {platform: len(entities) for platform, entities in captured.items()}


@pytest.fixture
def captured(monkeypatch):
    """Replace the control classes by recorders."""
    import custom_components.vtherm_auto_start_stop.number as number_module
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

    for module, names in (
        (switch_module, ("AutoStartStopEnableSwitch",)),
        (select_module, ("AutoStartStopStopModeSelect", "AutoStartStopLevelSelect")),
        (
            number_module,
            ("AutoStartStopDtMinNumber", "AutoStartStopErrorThresholdNumber"),
        ),
    ):
        for name in names:
            monkeypatch.setattr(module, name, FakeControl)
    return created


def add_platforms(fake_hass, unique_id="ded", created=None):
    """Register callbacks and loaded coverage."""
    for entry in fake_hass.config_entries.entries:
        fake_hass.data[DOMAIN][DATA_ENTRIES][entry.entry_id] = entry.data
    for platform in PLATFORMS:
        register_callback(fake_hass, platform, unique_id, created[platform].extend)


@pytest.mark.parametrize("enabled", [False, True])
def test_entities_created_for_a_dedicated_entry(fake_hass, captured, enabled):
    """Task 5.1: a dedicated instance owns the five controls."""
    fake_hass.config_entries.entries.append(
        make_entry(
            {CONF_VTHERM_UNIQUE_ID: VT},
            entry_id="ded",
            options={CONF_ENABLED: enabled},
        )
    )
    add_platforms(fake_hass, created=captured)
    ensure_entities(fake_hass, VT)

    assert counts(captured) == EXPECTED_PER_PLATFORM
    assert fake_hass.data[DOMAIN][DATA_CREATED][VT] == "ded"


def test_no_entity_without_coverage(fake_hass, captured):
    """No entry means no controls."""
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

    assert counts(captured) == EXPECTED_PER_PLATFORM


def test_entities_wait_for_every_platform_callback(fake_hass, captured):
    """Registration is deferred until the three platforms are ready."""
    fake_hass.config_entries.entries.append(
        make_entry({CONF_VTHERM_UNIQUE_ID: VT}, entry_id="ded")
    )
    fake_hass.data[DOMAIN][DATA_ENTRIES]["ded"] = {CONF_VTHERM_UNIQUE_ID: VT}
    register_callback(
        fake_hass, PLATFORM_SWITCH, "ded", captured[PLATFORM_SWITCH].extend
    )
    register_callback(
        fake_hass, PLATFORM_SELECT, "ded", captured[PLATFORM_SELECT].extend
    )
    ensure_entities(fake_hass, VT)
    assert all(entities == [] for entities in captured.values())

    register_callback(
        fake_hass, PLATFORM_NUMBER, "ded", captured[PLATFORM_NUMBER].extend
    )
    ensure_entities(fake_hass, VT)
    assert counts(captured) == EXPECTED_PER_PLATFORM


def test_entities_recreated_after_a_reset(fake_hass, captured):
    """A reload forgets the creation marker and rebuilds the entities once."""
    fake_hass.config_entries.entries.append(
        make_entry({CONF_VTHERM_UNIQUE_ID: VT}, entry_id="ded")
    )
    add_platforms(fake_hass, created=captured)
    ensure_entities(fake_hass, VT)
    reset_entities(fake_hass, VT)
    ensure_entities(fake_hass, VT)

    assert counts(captured) == {
        platform: count * 2 for platform, count in EXPECTED_PER_PLATFORM.items()
    }


def test_missing_callbacks_are_ignored(fake_hass, captured):
    ensure_entities(fake_hass, VT)
    assert fake_hass.data[DOMAIN].get(DATA_ADD_ENTITIES, {}) == {}


def test_unloading_every_platform_releases_all_callbacks(fake_hass, captured):
    add_platforms(fake_hass, created=captured)
    unregister_callback(fake_hass, PLATFORM_SWITCH, "ded")
    assert set(fake_hass.data[DOMAIN][DATA_ADD_ENTITIES]["ded"]) == {
        PLATFORM_SELECT,
        PLATFORM_NUMBER,
    }
    unregister_callback(fake_hass, PLATFORM_SELECT, "ded")
    assert set(fake_hass.data[DOMAIN][DATA_ADD_ENTITIES]["ded"]) == {PLATFORM_NUMBER}
    unregister_callback(fake_hass, PLATFORM_NUMBER, "ded")
    assert fake_hass.data[DOMAIN][DATA_ADD_ENTITIES] == {}


def test_get_manager_returns_none_before_registration(fake_hass):
    assert get_manager(fake_hass, VT) is None


def test_dedicated_entry_is_found_by_thermostat(fake_hass):
    entry = make_entry({CONF_VTHERM_UNIQUE_ID: VT}, entry_id="ded")
    fake_hass.config_entries.entries.append(entry)
    assert dedicated_entry(fake_hass, VT) is entry
    assert dedicated_entry(fake_hass, "other") is None
