"""Enable switch of a thermostat's dedicated auto start/stop instance.

The switch exists only for a thermostat owning a dedicated instance. It
suspends the accumulation when turned off, and releases an applied stop so the
thermostat resumes its requested mode immediately.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_ENABLED,
    CONF_EXCLUDED,
    CONF_VTHERM_UNIQUE_ID,
    DEFAULT_ENABLED,
    ENTITY_ENABLE_SUFFIX,
    PLATFORM_SWITCH,
)
from .entity import AutoStartStopEntity
from .registry import ensure_entities, register_callback, unregister_callback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Register the switch callback of a dedicated entry."""
    values = dict(entry.options or entry.data)
    unique_id = values.get(CONF_VTHERM_UNIQUE_ID)
    if not unique_id or values.get(CONF_EXCLUDED):
        return

    register_callback(hass, PLATFORM_SWITCH, unique_id, async_add_entities)
    entry.async_on_unload(lambda: unregister_callback(hass, PLATFORM_SWITCH, unique_id))
    ensure_entities(hass, unique_id)


class AutoStartStopEnableSwitch(AutoStartStopEntity, SwitchEntity, RestoreEntity):
    """Turn the auto-start/stop detection of one thermostat on or off."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:power-sleep"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, vtherm_unique_id: str
    ) -> None:
        super().__init__(
            hass,
            vtherm_unique_id,
            entry.entry_id,
            entry.title,
            ENTITY_ENABLE_SUFFIX,
        )

    async def async_added_to_hass(self) -> None:
        """Restore the last state and push it into the manager."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            enabled = last.state == "on"
        else:
            enabled = bool(self._entry_values().get(CONF_ENABLED, DEFAULT_ENABLED))

        manager = self.manager
        if manager is not None:
            await manager.async_set_enabled(enabled)
        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return whether detection is enabled."""
        manager = self.manager
        if manager is not None:
            return manager.enabled
        return bool(self._entry_values().get(CONF_ENABLED, DEFAULT_ENABLED))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable detection."""
        await self._async_apply(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable detection and release an applied stop."""
        await self._async_apply(False)

    async def _async_apply(self, enabled: bool) -> None:
        self._persist(CONF_ENABLED, enabled)
        manager = self.manager
        if manager is not None:
            await manager.async_set_enabled(enabled)
        self.async_write_ha_state()
