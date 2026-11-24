"""Persistent stop-mode selector of every covered thermostat.

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
    DOMAIN,
    ENTITY_STOP_MODE_SUFFIX,
    PLATFORM_SELECT,
    STOP_MODES,
)
from .entity import AutoStartStopEntity
from .registry import ensure_all_entities, register_callback, unregister_callback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Register the select callback of a covering entry."""
    register_callback(hass, PLATFORM_SELECT, entry.entry_id, async_add_entities)
    entry.async_on_unload(
        lambda: unregister_callback(hass, PLATFORM_SELECT, entry.entry_id)
    )
    ensure_all_entities(hass)


class AutoStartStopStopModeSelect(AutoStartStopEntity, SelectEntity):
    """Choose the HVAC mode applied on an automatic stop."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:hvac"
    _control_key = CONF_STOP_MODE

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
        return self._value if isinstance(self._value, str) else None

    async def async_select_option(self, option: str) -> None:
        """Save and apply the mode without changing activation."""
        if option not in self.options:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_auto_start_stop_option",
                translation_placeholders={"option": option},
            )
        await self._async_set_value(option)
