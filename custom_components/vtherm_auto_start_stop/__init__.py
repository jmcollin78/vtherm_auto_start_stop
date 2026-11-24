"""The VTherm auto start/stop integration.

One integration, two entry shapes: a single optional **global** entry providing
installation-wide defaults, and per-thermostat **dedicated** overrides.
The integration registers a feature-manager factory through
``vtherm_api``; the core then instantiates one manager per eligible thermostat,
refreshes it each cycle and resolves it as the auto-start/stop decision owner.
"""

from __future__ import annotations

import asyncio
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CoreState, Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from vtherm_api.log_collector import get_vtherm_logger

from .const import (
    CONF_VTHERM_UNIQUE_ID,
    DATA_ENTRIES,
    DATA_UNLOADING,
    DOMAIN,
    PLATFORMS,
    VT_DOMAIN,
)
from .factory import (
    AutoStartStopManagerFactory,
    register_factory,
    unregister_factory,
)
from .models import PARAMETER_KEYS, entry_config
from .registry import (
    async_reconcile_entities,
    covered_thermostats,
    entity_owner,
    ensure_all_entities,
    prepare_entity_ids,
)

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
    for config in _entries(hass).values():
        unique_id = config.get(CONF_VTHERM_UNIQUE_ID)
        if unique_id and all(key in config for key in PARAMETER_KEYS):
            overrides.add(unique_id)

    tasks = []
    for thermostat_entry in hass.config_entries.async_entries(VT_DOMAIN):
        thermostat_ids = (thermostat_entry.entry_id, thermostat_entry.unique_id)
        if target is not None:
            if target not in thermostat_ids:
                continue
        elif source_entry is not None and any(
            identity in overrides for identity in thermostat_ids
        ):
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
    _entries(hass)[entry.entry_id] = entry_config(entry)
    complete = False
    try:
        await async_reconcile_entities(hass)
        for unique_id in covered_thermostats(hass):
            owner = entity_owner(hass, unique_id)
            if owner is not None:
                prepare_entity_ids(hass, owner, unique_id)

        @callback
        def registry_changed(event: Event) -> None:
            if event.data["action"] == "remove":
                ensure_all_entities(hass)
            elif event.data["entity_id"].startswith("climate."):
                hass.async_create_task(async_reconcile_entities(hass))

        entry.async_on_unload(
            hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, registry_changed)
        )
        register_factory(hass, AutoStartStopManagerFactory(hass))
        entry.async_on_unload(entry.add_update_listener(_async_update_options))
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        if hass.state == CoreState.running:
            await _reload_thermostats(hass, entry)
        complete = True
    finally:
        if not complete:
            _entries(hass).pop(entry.entry_id, None)
            await async_reconcile_entities(hass)
    return True


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply changed options and reload the affected thermostats."""
    previous = _entries(hass).get(entry.entry_id, {})
    current = entry_config(entry)
    _entries(hass)[entry.entry_id] = current
    if all(
        previous.get(key) == current.get(key)
        for key in (*PARAMETER_KEYS, CONF_VTHERM_UNIQUE_ID)
    ):
        return
    await _reload_thermostats(hass, entry)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an entry, removing the factory once no entry remains."""
    unloading = hass.data.setdefault(DOMAIN, {}).setdefault(DATA_UNLOADING, set())
    unloading.add(entry.entry_id)
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        unloading.discard(entry.entry_id)
        return False
    await async_reconcile_entities(hass, remove_registry=False)
    _entries(hass).pop(entry.entry_id, None)
    unloading.discard(entry.entry_id)
    if not _entries(hass):
        unregister_factory(hass)
    await _reload_thermostats(hass, entry)
    if not _entries(hass):
        hass.data.pop(DOMAIN, None)
    return True
