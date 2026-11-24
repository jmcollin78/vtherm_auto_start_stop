"""Shared registry of the plugin runtime objects.

The select of a thermostat is created once its dedicated entry has registered
its ``async_add_entities`` callback, which may happen after the thermostat loads.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant

from .const import (
    CONF_VTHERM_UNIQUE_ID,
    DATA_ADD_ENTITIES,
    DATA_CREATED,
    DATA_MANAGERS,
    DOMAIN,
)
from .models import entry_config

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .manager import AutoStartStopManager


def _domain_data(hass: HomeAssistant) -> dict:
    return hass.data.setdefault(DOMAIN, {})


def managers(hass: HomeAssistant) -> dict[str, "AutoStartStopManager"]:
    """Return the live managers keyed by thermostat unique id."""
    return _domain_data(hass).setdefault(DATA_MANAGERS, {})


def get_manager(hass: HomeAssistant, vtherm_unique_id: str):
    """Return the live manager of a thermostat, if attached."""
    return managers(hass).get(vtherm_unique_id)


def register_callback(
    hass: HomeAssistant, unique_id: str, cb: AddEntitiesCallback
) -> None:
    """Store the select add-entities callback for a thermostat."""
    _domain_data(hass).setdefault(DATA_ADD_ENTITIES, {})[unique_id] = cb


def unregister_callback(hass: HomeAssistant, unique_id: str) -> None:
    """Forget the select add-entities callback."""
    _domain_data(hass).get(DATA_ADD_ENTITIES, {}).pop(unique_id, None)


def dedicated_entry(hass: HomeAssistant, unique_id: str):
    """Return the dedicated entry of a thermostat, including when disabled."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        values = entry_config(entry)
        if values.get(CONF_VTHERM_UNIQUE_ID) != unique_id:
            continue
        return entry
    return None


def ensure_entities(hass: HomeAssistant, unique_id: str) -> None:
    """Create the select of a thermostat, once.

    Called on manager registration and on each refresh, so a plugin entry loaded
    after the thermostat still ends up creating its select.
    """
    select_cb = _domain_data(hass).get(DATA_ADD_ENTITIES, {}).get(unique_id)
    if select_cb is None:
        return

    created = _domain_data(hass).setdefault(DATA_CREATED, {})
    if created.get(unique_id):
        return

    entry = dedicated_entry(hass, unique_id)
    if entry is None:
        return
    created[unique_id] = True

    # Imported here to avoid a circular import with the platform, which imports
    # this module to register their callbacks.
    from .select import AutoStartStopStopModeSelect
    select_cb([AutoStartStopStopModeSelect(hass, entry, unique_id)])


def reset_entities(hass: HomeAssistant, unique_id: str) -> None:
    """Forget that entities were created, so they can be recreated on reload."""
    data = _domain_data(hass)
    data.get(DATA_CREATED, {}).pop(unique_id, None)
