"""Shared fixtures: a fake thermostat and a fake Home Assistant runtime.

The plugin modules under test are pure enough to run without the Home Assistant
test harness: the manager only touches ``hass.data``, the config-entry registry,
the dispatcher and the thermostat object. The fixtures below provide exactly
that surface, so the tests exercise the real code without booting a core.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from homeassistant.util import dt as dt_util

from custom_components.vtherm_auto_start_stop.const import (
    CONF_ENABLED,
    CONF_LEVEL,
    CONF_STOP_MODE,
    CONF_VTHERM_UNIQUE_ID,
    DATA_MANAGERS,
    DOMAIN,
    LEVEL_SLOW,
    STOP_MODE_OFF,
)

VT_UNIQUE_ID = "vtherm-uid-1"


class FakeConfigEntries:
    """The slice of the config-entry registry the plugin reads."""

    def __init__(self) -> None:
        self.entries: list[Any] = []

    def async_entries(self, domain: str | None = None) -> list[Any]:
        if domain is None:
            return list(self.entries)
        return [e for e in self.entries if e.domain == domain]

    def async_get_entry(self, entry_id: str) -> Any | None:
        for entry in self.entries:
            if entry.entry_id == entry_id:
                return entry
        return None

    def async_update_entry(self, entry: Any, options: dict) -> None:
        entry.options = dict(options)


def make_entry(
    data: dict,
    entry_id: str = "entry-id",
    title: str = "Instance",
    options: dict | None = None,
) -> SimpleNamespace:
    """Build a config entry carrying the values the plugin reads."""
    return SimpleNamespace(
        domain=DOMAIN,
        entry_id=entry_id,
        title=title,
        data=dict(data),
        options=dict(options or {}),
    )


class FakeThermostat:
    """An over_climate thermostat, with the runtime contract the manager reads."""

    def __init__(self, hass: SimpleNamespace, unique_id: str = VT_UNIQUE_ID) -> None:
        self.hass = hass
        self.unique_id = unique_id
        self.entity_id = "climate.thermostat"
        self.name = "Thermostat"
        self.now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=dt_util.UTC)
        self.requested_hvac_mode = "heat"
        self.target_temperature = 20.0
        self.current_temperature = 19.0
        self.last_temperature_slope = 0.0
        self.vtherm_hvac_modes = ["off", "heat", "cool", "fan_only", "dry"]
        self.has_valve_regulation = False
        self.entry_infos: dict[str, Any] = {}
        self.refresh_requests = 0
        self.events: list[tuple[str, dict]] = []
        self.attribute_updates = 0
        self.state_writes = 0

    # -- runtime API -----------------------------------------------------

    async def async_request_state_refresh(self) -> None:
        """Record an immediate refresh request."""
        self.refresh_requests += 1

    def send_event(self, event_type: str, data: dict) -> None:
        """Record an emitted event."""
        self.events.append((event_type, data))

    def update_custom_attributes(self) -> None:
        """Record an attribute republication."""
        self.attribute_updates += 1

    def async_write_ha_state(self) -> None:
        """Record a state write."""
        self.state_writes += 1

    # -- helpers used by the tests ---------------------------------------

    def advance(self, minutes: float) -> None:
        """Move the shared cycle clock forward."""
        self.now = self.now + timedelta(minutes=minutes)

    def __str__(self) -> str:
        return f"FakeThermostat-{self.name}"


@pytest.fixture
def fake_hass() -> SimpleNamespace:
    """A Home Assistant stand-in with the surface the plugin uses."""
    hass = SimpleNamespace(
        data={DOMAIN: {"entries": {}}},
        config_entries=FakeConfigEntries(),
    )
    hass.data[DOMAIN].setdefault(DATA_MANAGERS, {})
    return hass


@pytest.fixture
def thermostat(fake_hass: SimpleNamespace) -> FakeThermostat:
    """A thermostat bound to the fake Home Assistant."""
    return FakeThermostat(fake_hass)


@pytest.fixture
def add_global_entry(fake_hass: SimpleNamespace):
    """Add a global (installation-wide) config entry."""

    def _add(level: str = LEVEL_SLOW, stop_mode: str = STOP_MODE_OFF, enabled=True):
        entry = {
            CONF_LEVEL: level,
            CONF_STOP_MODE: stop_mode,
            CONF_ENABLED: enabled,
        }
        fake_hass.data[DOMAIN]["entries"]["global"] = entry
        return entry

    return _add


@pytest.fixture
def add_dedicated_entry(fake_hass: SimpleNamespace):
    """Add a dedicated config entry for a thermostat."""

    def _add(
        unique_id: str = VT_UNIQUE_ID,
        level: str = LEVEL_SLOW,
        stop_mode: str = STOP_MODE_OFF,
        enabled=True,
        excluded: bool = False,
    ):
        entry = {CONF_VTHERM_UNIQUE_ID: unique_id}
        if excluded:
            entry["excluded"] = True
        else:
            entry.update(
                {
                    CONF_LEVEL: level,
                    CONF_STOP_MODE: stop_mode,
                    CONF_ENABLED: enabled,
                }
            )
        fake_hass.data[DOMAIN]["entries"][unique_id] = entry
        return entry

    return _add


@pytest.fixture(autouse=True)
def silence_side_effects(monkeypatch):
    """Keep the tests focused: no event log, no dispatcher, no registry lookups."""
    import custom_components.vtherm_auto_start_stop.manager as manager_module

    monkeypatch.setattr(manager_module, "write_event_log", lambda *a, **k: None)
    monkeypatch.setattr(manager_module, "async_dispatcher_send", lambda *a, **k: None)
    monkeypatch.setattr(manager_module, "ensure_entities", lambda *a, **k: None)
    return None


@pytest.fixture
def manager_factory(fake_hass: SimpleNamespace):
    """Build a manager bound to a thermostat, as the core would."""
    from custom_components.vtherm_auto_start_stop.manager import AutoStartStopManager

    def _build(thermostat: FakeThermostat) -> Any:
        return AutoStartStopManager(thermostat, fake_hass)

    return _build
