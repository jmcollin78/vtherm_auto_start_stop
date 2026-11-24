"""Shared registry of the plugin runtime objects.

The controls are created once a dedicated entry has registered both platform
callbacks, which may happen after the thermostat loads.
"""

from __future__ import annotations

from collections.abc import Mapping
from itertools import chain
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_ENTITY_IDS_ADOPTED,
    CONF_VTHERM_UNIQUE_ID,
    DATA_ADD_ENTITIES,
    DATA_CREATED,
    DATA_MANAGERS,
    DOMAIN,
    ENTITY_ENABLE_SUFFIX,
    ENTITY_STOP_MODE_SUFFIX,
    LEGACY_ENTITY_IDS,
    PLATFORM_SELECT,
    PLATFORM_SWITCH,
    VT_DOMAIN,
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
    hass: HomeAssistant, platform: str, unique_id: str, cb: AddEntitiesCallback
) -> None:
    """Store one add-entities callback for a thermostat."""
    _domain_data(hass).setdefault(DATA_ADD_ENTITIES, {}).setdefault(unique_id, {})[
        platform
    ] = cb


def unregister_callback(hass: HomeAssistant, platform: str, unique_id: str) -> None:
    """Forget one platform callback."""
    callbacks = _domain_data(hass).get(DATA_ADD_ENTITIES, {})
    platforms = callbacks.get(unique_id, {})
    platforms.pop(platform, None)
    if not platforms:
        callbacks.pop(unique_id, None)


def dedicated_entry(hass: HomeAssistant, unique_id: str):
    """Return the dedicated entry of a thermostat, including when disabled."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        values = entry_config(entry)
        if values.get(CONF_VTHERM_UNIQUE_ID) != unique_id:
            continue
        return entry
    return None


def _core_entry(hass: HomeAssistant, unique_id: str) -> ConfigEntry | None:
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("climate", VT_DOMAIN, unique_id)
    entity = registry.async_get(entity_id) if entity_id else None
    if entity is not None and entity.config_entry_id is not None:
        entry = hass.config_entries.async_get_entry(entity.config_entry_id)
        if entry is not None and entry.domain == VT_DOMAIN:
            return entry
    return next(
        (
            entry
            for entry in hass.config_entries.async_entries(VT_DOMAIN)
            if unique_id in (entry.unique_id, entry.entry_id)
        ),
        None,
    )


_CORE_SUFFIXES = {
    PLATFORM_SWITCH: "_enable_auto_start_stop",
    PLATFORM_SELECT: "_auto_start_stop_stop_mode",
}
_PLUGIN_SUFFIXES = {
    PLATFORM_SWITCH: ENTITY_ENABLE_SUFFIX,
    PLATFORM_SELECT: ENTITY_STOP_MODE_SUFFIX,
}


def _historical_ids(
    hass: HomeAssistant, core: ConfigEntry | None
) -> dict[str, str]:
    if core is None:
        return {}
    saved = core.data.get(LEGACY_ENTITY_IDS, {})
    if not isinstance(saved, Mapping) or any(
        domain not in _CORE_SUFFIXES
        or not isinstance(entity_id, str)
        or not entity_id.startswith(f"{domain}.")
        for domain, entity_id in saved.items()
    ):
        raise ConfigEntryError(f"Invalid {LEGACY_ENTITY_IDS} for {core.title}")
    result = dict(saved)
    registry = er.async_get(hass)
    for entity in chain(
        registry.entities.values(), registry.deleted_entities.values()
    ):
        suffix = _CORE_SUFFIXES.get(entity.domain)
        if (
            entity.platform == VT_DOMAIN
            and entity.config_entry_id == core.entry_id
            and suffix is not None
            and entity.unique_id.endswith(suffix)
        ):
            result.setdefault(entity.domain, entity.entity_id)
    return result


def prepare_entity_ids(
    hass: HomeAssistant, entry: ConfigEntry, unique_id: str
) -> bool:
    """Adopt exact historical IDs, or wait for legitimate core cleanup.

    Validate the whole pair before changing either registry entry. Never take
    another entity's ID or accept Home Assistant's automatic numeric suffix.
    """
    registry = er.async_get(hass)
    core = _core_entry(hass, unique_id)
    historical = _historical_ids(hass, core)
    adopted = entry.data.get(CONF_ENTITY_IDS_ADOPTED, False)
    planned: list[tuple[str, str, er.RegistryEntry | None]] = []
    waiting_for_core = False
    for domain, suffix in _PLUGIN_SUFFIXES.items():
        plugin_id = registry.async_get_entity_id(
            domain, DOMAIN, f"{unique_id}_{suffix}"
        )
        own = registry.async_get(plugin_id) if plugin_id else None
        if own is not None and own.config_entry_id != entry.entry_id:
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="entity_id_conflict",
                translation_placeholders={"entity_id": own.entity_id},
            )
        target = own.entity_id if adopted and own else historical.get(domain)
        if target is None:
            continue
        occupied = registry.async_get(target)
        if occupied is not None and occupied != own:
            if (
                core is not None
                and occupied.config_entry_id == core.entry_id
                and occupied.platform == VT_DOMAIN
                and occupied.domain == domain
                and occupied.unique_id.endswith(_CORE_SUFFIXES[domain])
            ):
                waiting_for_core = True
                continue
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="entity_id_conflict",
                translation_placeholders={"entity_id": target},
            )
        if occupied is None and hass.states.get(target) is not None:
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="entity_id_conflict",
                translation_placeholders={"entity_id": target},
            )
        planned.append((domain, target, own))

    if waiting_for_core:
        return False
    for domain, target, own in planned:
        if own is None:
            own = registry.async_get_or_create(
                domain,
                DOMAIN,
                f"{unique_id}_{_PLUGIN_SUFFIXES[domain]}",
                config_entry=entry,
                suggested_object_id=target.split(".", 1)[1],
            )
        if own.entity_id != target:
            registry.async_update_entity(own.entity_id, new_entity_id=target)
    if historical and not adopted:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_ENTITY_IDS_ADOPTED: True}
        )
    return True


def ensure_entities(hass: HomeAssistant, unique_id: str) -> None:
    """Create the two controls of a thermostat, once.

    Called on manager registration and on each refresh, so a plugin entry loaded
    after the thermostat still ends up creating its controls.
    """
    callbacks = _domain_data(hass).get(DATA_ADD_ENTITIES, {}).get(unique_id, {})
    switch_cb = callbacks.get(PLATFORM_SWITCH)
    select_cb = callbacks.get(PLATFORM_SELECT)
    if switch_cb is None or select_cb is None:
        return

    created = _domain_data(hass).setdefault(DATA_CREATED, {})
    if created.get(unique_id):
        return

    entry = dedicated_entry(hass, unique_id)
    if entry is None or not prepare_entity_ids(hass, entry, unique_id):
        return
    created[unique_id] = True

    # Imported here to avoid circular imports with the platforms, which import
    # this module to register their callbacks.
    from .select import AutoStartStopStopModeSelect
    from .switch import AutoStartStopEnableSwitch

    switch_cb([AutoStartStopEnableSwitch(hass, entry, unique_id)])
    select_cb([AutoStartStopStopModeSelect(hass, entry, unique_id)])


def reset_entities(hass: HomeAssistant, unique_id: str) -> None:
    """Forget that entities were created, so they can be recreated on reload."""
    data = _domain_data(hass)
    data.get(DATA_CREATED, {}).pop(unique_id, None)
