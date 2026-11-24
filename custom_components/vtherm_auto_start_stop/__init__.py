"""The VTherm auto start/stop integration.

One integration, two entry shapes: a single optional **global** entry providing
installation-wide defaults, and per-thermostat **dedicated** entries (which may
be exclusions). The integration registers a feature-manager factory through
``vtherm_api``; the core then instantiates one manager per eligible thermostat,
refreshes it each cycle and resolves it as the auto-start/stop decision owner.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CoreState, HomeAssistant
from vtherm_api.log_collector import get_vtherm_logger

from .const import (
    CONF_VTHERM_UNIQUE_ID,
    DATA_ENTRIES,
    DOMAIN,
    PLATFORMS,
    VT_DOMAIN,
)
from .factory import (
    AutoStartStopManagerFactory,
    register_factory,
    unregister_factory,
)

_LOGGER = get_vtherm_logger(__name__)


def _entry_config(entry: ConfigEntry) -> dict[str, Any]:
    """Return the effective values of an entry (options override data)."""
    return dict(entry.options or entry.data)


def _entries(hass: HomeAssistant) -> dict[str, dict[str, Any]]:
    """Return the plugin entries registry (``entry_id`` -> values)."""
    return hass.data.setdefault(DOMAIN, {}).setdefault(DATA_ENTRIES, {})


async def _reload_thermostats(
    hass: HomeAssistant, source_entry: ConfigEntry | None = None
) -> None:
    """Reload the thermostats whose resolution may have changed.

    A dedicated or exclusion entry only affects its own thermostat; the global
    entry affects every thermostat without a dedicated one. Reloading the
    thermostat re-runs the factory, so a manager appears, disappears or picks up
    new values without any other action.
    """
    target: str | None = None
    if source_entry is not None:
        target = _entry_config(source_entry).get(CONF_VTHERM_UNIQUE_ID)

    overrides = {
        _entry_config(entry).get(CONF_VTHERM_UNIQUE_ID)
        for entry in hass.config_entries.async_entries(DOMAIN)
        if _entry_config(entry).get(CONF_VTHERM_UNIQUE_ID)
    }

    tasks = []
    for thermostat_entry in hass.config_entries.async_entries(VT_DOMAIN):
        if target is not None:
            if thermostat_entry.unique_id != target:
                continue
        elif source_entry is not None and thermostat_entry.unique_id in overrides:
            # The global entry does not cover a thermostat with its own entry.
            continue
        tasks.append(hass.config_entries.async_reload(thermostat_entry.entry_id))
    if tasks:
        await asyncio.gather(*tasks)


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register the factory as soon as the integration is loaded."""
    del config
    register_factory(hass, AutoStartStopManagerFactory(hass))
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one global, dedicated or exclusion entry."""
    _entries(hass)[entry.entry_id] = _entry_config(entry)
    register_factory(hass, AutoStartStopManagerFactory(hass))
    entry.async_on_unload(entry.add_update_listener(_async_update_options))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    if hass.state == CoreState.running:
        await _reload_thermostats(hass, entry)
    return True


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply changed options and reload the affected thermostats."""
    _entries(hass)[entry.entry_id] = _entry_config(entry)
    await _reload_thermostats(hass, entry)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an entry, removing the factory once no entry remains."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False

    _entries(hass).pop(entry.entry_id, None)
    if not _entries(hass):
        unregister_factory(hass)
        hass.data.pop(DOMAIN, None)
    await _reload_thermostats(hass, entry)
    return True
