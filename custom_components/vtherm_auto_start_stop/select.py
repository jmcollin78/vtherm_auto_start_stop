"""Stop-mode selector of a thermostat's dedicated auto-start/stop instance.

Selecting a compatible stop mode does not change activation. The independent
enable switch controls whether detection runs.
"""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_STOP_MODE,
    CONF_VTHERM_UNIQUE_ID,
    DOMAIN,
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


class AutoStartStopStopModeSelect(AutoStartStopEntity, SelectEntity):
    """Choose the HVAC mode applied on an automatic stop."""

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
        """Return compatible stop modes, independently of activation."""
        manager = self.manager
        if manager is not None:
            return manager.stop_modes
        return list(STOP_MODES)

    @property
    def current_option(self) -> str | None:
        """Return the saved stop mode even when detection is disabled."""
        manager = self.manager
        if manager is not None:
            return manager.stop_mode
        return self._entry_values().get(CONF_STOP_MODE)

    async def async_added_to_hass(self) -> None:
        """Apply persisted configuration, never a stale restored UI state."""
        await super().async_added_to_hass()
        manager = self.manager
        if manager is not None:
            values = self._entry_values()
            await manager.async_set_stop_mode(
                values.get(CONF_STOP_MODE, manager.stop_mode)
            )
        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Save and apply the mode without changing activation."""
        if option not in self.options:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_auto_start_stop_option",
                translation_placeholders={"option": option},
            )
        self._persist({CONF_STOP_MODE: option})
        manager = self.manager
        if manager is not None:
            await manager.async_set_stop_mode(option)
        self.async_write_ha_state()
