"""Stop-mode selector of a thermostat's dedicated auto start/stop instance.

The select exists only for a thermostat owning a dedicated instance. Its options
are the stop modes the thermostat accepts, so ``fan_only`` and ``dry`` are only
offered when the thermostat supports them, while ``off`` is always available.
"""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_STOP_MODE,
    CONF_VTHERM_UNIQUE_ID,
    ENTITY_STOP_MODE_SUFFIX,
    PLATFORM_SELECT,
    STOP_MODES,
)
from .entity import AutoStartStopEntity
from .models import entry_config
from .registry import ensure_entities, register_callback, unregister_callback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Register the select callback of a dedicated entry."""
    values = entry_config(entry)
    unique_id = values.get(CONF_VTHERM_UNIQUE_ID)
    if not unique_id:
        return

    register_callback(hass, PLATFORM_SELECT, unique_id, async_add_entities)
    entry.async_on_unload(lambda: unregister_callback(hass, PLATFORM_SELECT, unique_id))
    ensure_entities(hass, unique_id)


class AutoStartStopStopModeSelect(AutoStartStopEntity, SelectEntity, RestoreEntity):
    """Choose the HVAC mode applied when a stop is detected."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:hvac"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, vtherm_unique_id: str
    ) -> None:
        super().__init__(
            hass,
            vtherm_unique_id,
            entry.entry_id,
            entry.title,
            ENTITY_STOP_MODE_SUFFIX,
        )

    @property
    def options(self) -> list[str]:
        """Return the stop modes accepted by the thermostat."""
        manager = self.manager
        if manager is not None:
            return manager.stop_modes
        return list(STOP_MODES)

    @property
    def current_option(self) -> str | None:
        """Return the configured stop mode."""
        manager = self.manager
        if manager is not None:
            return manager.stop_mode
        return self._entry_values().get(CONF_STOP_MODE)

    async def async_added_to_hass(self) -> None:
        """Apply configured values before considering a restored option."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        option = self._entry_values().get(CONF_STOP_MODE, self.current_option)
        if option not in self.options:
            option = last.state if last is not None else None
        manager = self.manager
        if manager is not None and option in self.options:
            manager.restore_entity_state(manager.enabled, option)
        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Apply a new stop mode on the next detection."""
        self._persist(CONF_STOP_MODE, option)
        manager = self.manager
        if manager is not None:
            await manager.async_set_stop_mode(option)
        self.async_write_ha_state()
