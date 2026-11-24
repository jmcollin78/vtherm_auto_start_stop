"""Shared registry of the plugin runtime objects.

Control identity is independent of the configuration supplying parameters.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
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
    DATA_CONTROLS,
    DATA_ENTITIES,
    DATA_ENTRIES,
    DATA_INELIGIBLE,
    DATA_MANAGERS,
    DATA_UNLOADING,
    DOMAIN,
    ENTITY_ENABLE_SUFFIX,
    ENTITY_STOP_MODE_SUFFIX,
    LEGACY_ENTITY_IDS,
    LEGACY_REGULATION_MODE,
    LEGACY_REGULATION_VALVE,
    LEGACY_THERMOSTAT_TYPE,
    PLATFORM_SELECT,
    PLATFORM_SWITCH,
    THERMOSTAT_TYPE_CLIMATE,
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


def get_manager(
    hass: HomeAssistant, vtherm_unique_id: str
) -> AutoStartStopManager | None:
    """Return the live manager of a thermostat, if attached."""
    return managers(hass).get(vtherm_unique_id)


@dataclass
class ControlState:
    """In-memory bridge between restored entities and replacement managers."""

    enabled: bool | None = None
    stop_mode: str | None = None


def control_state(hass: HomeAssistant, unique_id: str) -> ControlState:
    return _domain_data(hass).setdefault(DATA_CONTROLS, {}).setdefault(
        unique_id, ControlState()
    )


async def async_apply_controls(hass: HomeAssistant, unique_id: str) -> None:
    state = control_state(hass, unique_id)
    manager = get_manager(hass, unique_id)
    if manager is not None and state.enabled is not None and state.stop_mode is not None:
        await manager.async_initialize_controls(state.enabled, state.stop_mode)


def register_callback(
    hass: HomeAssistant, platform: str, entry_id: str, cb: AddEntitiesCallback
) -> None:
    """Store one platform callback for a loaded covering entry."""
    _domain_data(hass).setdefault(DATA_ADD_ENTITIES, {}).setdefault(entry_id, {})[
        platform
    ] = cb


def unregister_callback(hass: HomeAssistant, platform: str, entry_id: str) -> None:
    """Forget one platform callback."""
    callbacks = hass.data.get(DOMAIN, {}).get(DATA_ADD_ENTITIES, {})
    platforms = callbacks.get(entry_id, {})
    platforms.pop(platform, None)
    if not platforms:
        callbacks.pop(entry_id, None)


def dedicated_entry(hass: HomeAssistant, unique_id: str):
    """Return the dedicated entry of a thermostat, including when disabled."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        values = entry_config(entry)
        if values.get(CONF_VTHERM_UNIQUE_ID) != unique_id:
            continue
        return entry
    return None


def entity_owner(hass: HomeAssistant, unique_id: str) -> ConfigEntry | None:
    """Prefer the loaded global entry; otherwise use dedicated coverage."""
    data = _domain_data(hass)
    loaded = data.get(DATA_ENTRIES, {})
    unloading = data.get(DATA_UNLOADING, set())
    dedicated = None
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.entry_id not in loaded or entry.entry_id in unloading:
            continue
        target = entry_config(entry).get(CONF_VTHERM_UNIQUE_ID)
        if not target:
            return entry
        if target == unique_id:
            dedicated = entry
    return dedicated


def covered_thermostats(hass: HomeAssistant) -> set[str]:
    result = set(managers(hass))
    for entry in hass.config_entries.async_entries(VT_DOMAIN):
        values = {**entry.data, **entry.options}
        if (
            values.get(LEGACY_THERMOSTAT_TYPE) == THERMOSTAT_TYPE_CLIMATE
            and values.get(LEGACY_REGULATION_MODE) != LEGACY_REGULATION_VALVE
        ):
            registry = er.async_get(hass)
            climates = [
                entity
                for entity in er.async_entries_for_config_entry(registry, entry.entry_id)
                if entity.platform == VT_DOMAIN and entity.domain == "climate"
            ]
            result.add(
                climates[0].unique_id if climates else entry.unique_id or entry.entry_id
            )
    result.difference_update(_domain_data(hass).get(DATA_INELIGIBLE, set()))
    return {unique_id for unique_id in result if entity_owner(hass, unique_id) is not None}


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
    planned: list[tuple[str, str | None, er.RegistryEntry | None, bool]] = []
    waiting_for_core = False
    for domain, suffix in _PLUGIN_SUFFIXES.items():
        plugin_id = registry.async_get_entity_id(
            domain, DOMAIN, f"{unique_id}_{suffix}"
        )
        own = registry.async_get(plugin_id) if plugin_id else None
        old_owner = (
            hass.config_entries.async_get_entry(own.config_entry_id)
            if own is not None and own.config_entry_id is not None
            else None
        )
        if own is not None and own.config_entry_id != entry.entry_id and (
            old_owner is None
            or old_owner.domain != DOMAIN
            or entry_config(old_owner).get(CONF_VTHERM_UNIQUE_ID) not in (None, unique_id)
        ):
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="entity_id_conflict",
                translation_placeholders={"entity_id": own.entity_id},
            )
        adopted = own is not None and (
            own.options.get(DOMAIN, {}).get(CONF_ENTITY_IDS_ADOPTED, False)
            or (
                old_owner is not None
                and entry_config(old_owner).get(CONF_VTHERM_UNIQUE_ID) == unique_id
                and old_owner.data.get(CONF_ENTITY_IDS_ADOPTED, False)
            )
        )
        target = own.entity_id if adopted and own else historical.get(domain)
        occupied = registry.async_get(target) if target else None
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
        if target is not None and occupied is None and hass.states.get(target) is not None:
            raise ConfigEntryError(
                translation_domain=DOMAIN,
                translation_key="entity_id_conflict",
                translation_placeholders={"entity_id": target},
            )
        planned.append((domain, target, own, adopted))

    if waiting_for_core:
        return False
    for domain, target, own, adopted in planned:
        if own is None and target is not None:
            own = registry.async_get_or_create(
                domain,
                DOMAIN,
                f"{unique_id}_{_PLUGIN_SUFFIXES[domain]}",
                config_entry=entry,
                suggested_object_id=target.split(".", 1)[1],
            )
        if own is None:
            continue
        changes = {}
        if target is not None and own.entity_id != target:
            changes["new_entity_id"] = target
        if own.config_entry_id != entry.entry_id:
            changes["config_entry_id"] = entry.entry_id
        if changes:
            own = registry.async_update_entity(own.entity_id, **changes)
        if not own.options.get(DOMAIN, {}).get(CONF_ENTITY_IDS_ADOPTED, False):
            registry.async_update_entity_options(
                own.entity_id,
                DOMAIN,
                {**own.options.get(DOMAIN, {}), CONF_ENTITY_IDS_ADOPTED: True},
            )
    return True


def ensure_entities(hass: HomeAssistant, unique_id: str) -> None:
    """Create the two controls of a thermostat, once.

    Called on manager registration and on each refresh, so a plugin entry loaded
    after the thermostat still ends up creating its controls.
    """
    entry = entity_owner(hass, unique_id)
    if entry is None or unique_id in _domain_data(hass).get(DATA_INELIGIBLE, set()):
        return
    callbacks = _domain_data(hass).get(DATA_ADD_ENTITIES, {}).get(entry.entry_id, {})
    switch_cb = callbacks.get(PLATFORM_SWITCH)
    select_cb = callbacks.get(PLATFORM_SELECT)
    if switch_cb is None or select_cb is None:
        return

    created = _domain_data(hass).setdefault(DATA_CREATED, {})
    if created.get(unique_id):
        return

    if not prepare_entity_ids(hass, entry, unique_id):
        return
    created[unique_id] = entry.entry_id

    # Imported here to avoid circular imports with the platforms, which import
    # this module to register their callbacks.
    from .select import AutoStartStopStopModeSelect
    from .switch import AutoStartStopEnableSwitch

    switch = AutoStartStopEnableSwitch(hass, entry, unique_id)
    select = AutoStartStopStopModeSelect(hass, entry, unique_id)
    _domain_data(hass).setdefault(DATA_ENTITIES, {})[unique_id] = [switch, select]
    switch_cb([switch])
    select_cb([select])


def ensure_all_entities(hass: HomeAssistant) -> None:
    if not hass.data.get(DOMAIN, {}).get(DATA_ENTRIES):
        return
    for unique_id in covered_thermostats(hass):
        ensure_entities(hass, unique_id)


async def async_remove_controls(
    hass: HomeAssistant, unique_id: str, *, remove_registry: bool = False
) -> None:
    data = _domain_data(hass)
    for entity in data.get(DATA_ENTITIES, {}).pop(unique_id, []):
        if entity.hass is not None:
            await entity.async_remove(force_remove=True)
    reset_entities(hass, unique_id)
    if remove_registry:
        registry = er.async_get(hass)
        for domain, suffix in _PLUGIN_SUFFIXES.items():
            entity_id = registry.async_get_entity_id(domain, DOMAIN, f"{unique_id}_{suffix}")
            if entity_id is not None:
                registry.async_remove(entity_id)
        data.get(DATA_CONTROLS, {}).pop(unique_id, None)


async def async_reconcile_entities(
    hass: HomeAssistant, *, remove_registry: bool = True
) -> None:
    """Move proven-owned controls before HA deletes their previous owner."""
    covered = covered_thermostats(hass)
    for unique_id, owner_id in list(_domain_data(hass).get(DATA_CREATED, {}).items()):
        owner = entity_owner(hass, unique_id)
        if unique_id not in covered:
            manager = get_manager(hass, unique_id)
            if manager is not None:
                manager.stop_listening()
            await async_remove_controls(hass, unique_id, remove_registry=remove_registry)
        elif owner is not None and owner.entry_id != owner_id:
            await async_remove_controls(hass, unique_id)
            prepare_entity_ids(hass, owner, unique_id)
    ensure_all_entities(hass)


def reset_entities(hass: HomeAssistant, unique_id: str) -> None:
    """Forget that entities were created, so they can be recreated on reload."""
    data = _domain_data(hass)
    data.get(DATA_CREATED, {}).pop(unique_id, None)
