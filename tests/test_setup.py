"""Integration setup and factory registration (tasks 1.1, 1.3)."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
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
    DATA_FACTORY_REGISTERED,
    DOMAIN,
    LEVEL_SLOW,
    MANAGER_NAME,
    STOP_MODE_OFF,
)
from custom_components.vtherm_auto_start_stop.factory import (
    AutoStartStopManagerFactory,
    register_factory,
    unregister_factory,
)


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
