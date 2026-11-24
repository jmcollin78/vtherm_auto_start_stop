"""Shared registry of the plugin runtime objects.

The entities of a thermostat can only be created once its dedicated entry has
forwarded both platforms **and** the plugin entry has been loaded (which may
happen after the thermostat). The manager therefore asks for entity creation on
registration and on each refresh; :func:`ensure_entities` creates them exactly
once, when both ``async_add_entities`` callbacks are known.
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
    PLATFORM_SELECT,
    PLATFORM_SWITCH,
)
from .models import entry_config

if TYPE_CHECKING:
    from .manager import AutoStartStopManager


def _domain_data(hass: HomeAssistant) -> dict:
    return hass.data.setdefault(DOMAIN, {})


def managers(hass: HomeAssistant) -> dict[str, "AutoStartStopManager"]:
    """Return the live managers keyed by thermostat unique id."""
    return _domain_data(hass).setdefault(DATA_MANAGERS, {})


def get_manager(hass: HomeAssistant, vtherm_unique_id: str):
    """Return the live manager of a thermostat, if attached."""
    return managers(hass).get(vtherm_unique_id)


def register_callback(hass: HomeAssistant, platform: str, unique_id: str, cb) -> None:
    """Store the add-entities callback of one platform for a thermostat."""
    _domain_data(hass).setdefault(DATA_ADD_ENTITIES, {}).setdefault(unique_id, {})[
        platform
    ] = cb


def unregister_callback(hass: HomeAssistant, platform: str, unique_id: str) -> None:
    """Forget the add-entities callback of one platform."""
    bucket = _domain_data(hass).get(DATA_ADD_ENTITIES, {}).get(unique_id)
    if bucket is not None:
        bucket.pop(platform, None)


def dedicated_entry(hass: HomeAssistant, unique_id: str):
    """Return the dedicated entry of a thermostat, including when disabled."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        values = entry_config(entry)
        if values.get(CONF_VTHERM_UNIQUE_ID) != unique_id:
            continue
        return entry
    return None


def ensure_entities(hass: HomeAssistant, unique_id: str) -> None:
    """Create the switch and the select of a thermostat, once.

    Called on manager registration and on each refresh, so a plugin entry loaded
    after the thermostat still ends up creating its entities.
    """
    bucket = _domain_data(hass).get(DATA_ADD_ENTITIES, {}).get(unique_id)
    if not bucket:
        return
    switch_cb = bucket.get(PLATFORM_SWITCH)
    select_cb = bucket.get(PLATFORM_SELECT)
    if switch_cb is None or select_cb is None:
        return

    created = _domain_data(hass).setdefault(DATA_CREATED, {})
    if created.get(unique_id):
        return

    entry = dedicated_entry(hass, unique_id)
    if entry is None:
        return
    created[unique_id] = True

    # Imported here to avoid a circular import with the platforms, which import
    # this module to register their callbacks.
    from .select import AutoStartStopStopModeSelect
    from .switch import AutoStartStopEnableSwitch

    switch_cb([AutoStartStopEnableSwitch(hass, entry, unique_id)])
    select_cb([AutoStartStopStopModeSelect(hass, entry, unique_id)])


def reset_entities(hass: HomeAssistant, unique_id: str) -> None:
    """Forget that entities were created, so they can be recreated on reload."""
    data = _domain_data(hass)
    data.get(DATA_CREATED, {}).pop(unique_id, None)
