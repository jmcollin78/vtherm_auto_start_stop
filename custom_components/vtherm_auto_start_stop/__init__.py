"""The VTherm auto start/stop integration.

One integration, two entry shapes: a single optional **global** entry providing
installation-wide defaults, and per-thermostat **dedicated** overrides.
The integration registers a feature-manager factory through
``vtherm_api``; the core then instantiates one manager per eligible thermostat,
refreshes it each cycle and resolves it as the auto-start/stop decision owner.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers import entity_registry as er
from vtherm_api.log_collector import get_vtherm_logger

from .const import (
    CONF_VTHERM_UNIQUE_ID,
    DATA_ENTRIES,
    DOMAIN,
    ENTITY_ENABLE_SUFFIX,
    PLATFORMS,
    VT_DOMAIN,
)
from .factory import (
    AutoStartStopManagerFactory,
    register_factory,
    unregister_factory,
)
from .models import CONFIG_KEYS, entry_config
from .registry import reset_entities

_LOGGER = get_vtherm_logger(__name__)


def _entries(hass: HomeAssistant) -> dict[str, dict[str, Any]]:
    """Return the plugin entries registry (``entry_id`` -> values)."""
    return hass.data.setdefault(DOMAIN, {}).setdefault(DATA_ENTRIES, {})


async def _reload_thermostats(
    hass: HomeAssistant, source_entry: ConfigEntry | None = None
) -> None:
    """Reload the thermostats whose resolution may have changed.

    A dedicated entry only affects its own thermostat; the global
    entry affects every thermostat inheriting at least one field. Reloading the
    thermostat re-runs the factory, so a manager appears, disappears or picks up
    new values without any other action.
    """
    target: str | None = None
    if source_entry is not None:
        target = entry_config(source_entry).get(CONF_VTHERM_UNIQUE_ID)

    overrides: set[str] = set()
    for entry in hass.config_entries.async_entries(DOMAIN):
        config = entry_config(entry)
        unique_id = config.get(CONF_VTHERM_UNIQUE_ID)
        if unique_id and all(key in config for key in CONFIG_KEYS):
            overrides.add(unique_id)

    tasks = []
    for thermostat_entry in hass.config_entries.async_entries(VT_DOMAIN):
        if target is not None:
            if thermostat_entry.unique_id != target:
                continue
        elif source_entry is not None and thermostat_entry.unique_id in overrides:
            # A complete dedicated configuration inherits no global field.
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
    """Set up one global or dedicated entry."""
    values = entry_config(entry)
    _entries(hass)[entry.entry_id] = values
    unique_id = values.get(CONF_VTHERM_UNIQUE_ID)
    if unique_id:
        registry = er.async_get(hass)
        switch_id = registry.async_get_entity_id(
            "switch", DOMAIN, f"{unique_id}_{ENTITY_ENABLE_SUFFIX}"
        )
        legacy_switch = registry.async_get(switch_id) if switch_id else None
        if (
            legacy_switch is not None
            and legacy_switch.config_entry_id == entry.entry_id
        ):
            _LOGGER.info(
                "%s - removing superseded enable switch %s", entry.title, switch_id
            )
            registry.async_remove(legacy_switch.entity_id)
    register_factory(hass, AutoStartStopManagerFactory(hass))
    entry.async_on_unload(entry.add_update_listener(_async_update_options))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    if hass.state == CoreState.running:
        await _reload_thermostats(hass, entry)
    return True


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply changed options and reload the affected thermostats."""
    _entries(hass)[entry.entry_id] = entry_config(entry)
    await _reload_thermostats(hass, entry)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an entry, removing the factory once no entry remains."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False

    unique_id = entry_config(entry).get(CONF_VTHERM_UNIQUE_ID)
    if unique_id:
        reset_entities(hass, unique_id)
    _entries(hass).pop(entry.entry_id, None)
    if not _entries(hass):
        unregister_factory(hass)
        hass.data.pop(DOMAIN, None)
    await _reload_thermostats(hass, entry)
    return True
