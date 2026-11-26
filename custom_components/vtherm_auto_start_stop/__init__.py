"""The VTherm auto start/stop integration.

One integration, two entry shapes: a single optional **global** entry providing
installation-wide defaults, and per-thermostat **dedicated** overrides.
The integration registers a feature-manager factory through
``vtherm_api``; the core then instantiates one manager per eligible thermostat,
refreshes it each cycle and resolves it as the auto-start/stop decision owner.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CoreState, Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from vtherm_api.log_collector import get_vtherm_logger

from .const import (
    DATA_ENTRIES,
    DATA_UNLOADING,
    DOMAIN,
    PLATFORMS,
)
from .factory import (
    AutoStartStopManagerFactory,
    register_factory,
    unregister_factory,
)
from .models import entry_config
from .registry import (
    async_attach_managers,
    async_reconcile_entities,
    covered_thermostats,
    entity_owner,
    ensure_all_entities,
    get_manager,
    prepare_entity_ids,
)

_LOGGER = get_vtherm_logger(__name__)


def _entries(hass: HomeAssistant) -> dict[str, dict[str, Any]]:
    """Return the plugin entries registry (``entry_id`` -> values)."""
    return hass.data.setdefault(DOMAIN, {}).setdefault(DATA_ENTRIES, {})


async def _reresolve_managers(hass: HomeAssistant) -> None:
    """Re-resolve every manager after a coverage or seed change.

    A change to an entry no longer reloads any thermostat: the entry grants
    coverage and seeds, so re-running the managers' ``post_init`` and recreating
    the missing controls is enough. The existing managers keep their live state;
    a thermostat that gained or lost coverage gains or loses its controls here.

    Creating a covering entry while Home Assistant runs does not rebuild the
    thermostats, so a thermostat covered for the first time has no plugin
    manager yet. Attaching the missing managers here makes its controls available
    immediately, without waiting for a restart and without reloading anything.
    """
    await async_reconcile_entities(hass)
    await async_attach_managers(hass)
    for unique_id in covered_thermostats(hass):
        manager = get_manager(hass, unique_id)
        if manager is not None:
            manager.post_init({})


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
            await _reresolve_managers(hass)
        complete = True
    finally:
        if not complete:
            _entries(hass).pop(entry.entry_id, None)
            await async_reconcile_entities(hass)
    return True


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply changed options without reloading any thermostat.

    The entry only grants coverage and seeds controls that have no restored
    state, so a change is absorbed by a re-resolution of the managers rather than
    a reload of the Versatile Thermostat entries.
    """
    _entries(hass)[entry.entry_id] = entry_config(entry)
    if hass.state == CoreState.running:
        await _reresolve_managers(hass)


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
    await async_reconcile_entities(hass)
    if not _entries(hass):
        hass.data.pop(DOMAIN, None)
    return True
