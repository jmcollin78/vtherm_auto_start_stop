"""Enable control for a thermostat's dedicated auto-start/stop configuration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ENABLED,
    CONF_STOP_MODE,
    CONF_VTHERM_UNIQUE_ID,
    DEFAULT_ENABLED,
    ENTITY_ENABLE_SUFFIX,
    PLATFORM_SWITCH,
)
from .entity import AutoStartStopEntity
from .models import entry_config
from .registry import ensure_entities, register_callback, unregister_callback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Register the enable-switch platform of a dedicated entry."""
    unique_id = entry_config(entry).get(CONF_VTHERM_UNIQUE_ID)
    if not unique_id:
        return
    register_callback(hass, PLATFORM_SWITCH, unique_id, async_add_entities)
    entry.async_on_unload(lambda: unregister_callback(hass, PLATFORM_SWITCH, unique_id))
    ensure_entities(hass, unique_id)


class AutoStartStopEnableSwitch(AutoStartStopEntity, SwitchEntity):
    """Control detection without changing the saved automatic stop mode."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:power-sleep"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, vtherm_unique_id: str
    ) -> None:
        super().__init__(
            hass, vtherm_unique_id, entry.entry_id, entry.title, ENTITY_ENABLE_SUFFIX
        )

    @property
    def is_on(self) -> bool:
        """Return the effective activation state."""
        manager = self.manager
        if manager is not None:
            return manager.enabled
        return bool(self._entry_values().get(CONF_ENABLED, DEFAULT_ENABLED))

    async def async_added_to_hass(self) -> None:
        """Use persisted settings, not a stale restored switch state."""
        await super().async_added_to_hass()
        manager = self.manager
        if manager is not None:
            values = self._entry_values()
            await manager.async_set_stop_mode(
                values.get(CONF_STOP_MODE, manager.stop_mode)
            )
            await manager.async_set_enabled(values.get(CONF_ENABLED, manager.enabled))
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable detection using the saved stop mode."""
        await self._async_apply(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Suspend detection and release an automatic stop."""
        await self._async_apply(False)

    async def _async_apply(self, enabled: bool) -> None:
        self._persist({CONF_ENABLED: enabled})
        manager = self.manager
        if manager is not None:
            if enabled:
                await manager.async_set_stop_mode(
                    self._entry_values().get(CONF_STOP_MODE, manager.stop_mode)
                )
            await manager.async_set_enabled(enabled)
        self.async_write_ha_state()
