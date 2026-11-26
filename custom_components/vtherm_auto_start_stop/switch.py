"""Persistent enable control for every covered thermostat."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_ENABLED,
    ENTITY_ENABLE_SUFFIX,
    PLATFORM_SWITCH,
)
from .entity import AutoStartStopEntity
from .registry import ensure_all_entities, register_callback, unregister_callback


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Register the enable-switch platform of a covering entry."""
    register_callback(hass, PLATFORM_SWITCH, entry.entry_id, async_add_entities)
    entry.async_on_unload(
        lambda: unregister_callback(hass, PLATFORM_SWITCH, entry.entry_id)
    )
    ensure_all_entities(hass)


class AutoStartStopEnableSwitch(AutoStartStopEntity, SwitchEntity):
    """Control detection without changing the saved automatic stop mode."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:power-sleep"
    _control_key = "enabled"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, vtherm_unique_id: str
    ) -> None:
        super().__init__(
            hass, vtherm_unique_id, entry.entry_id, entry.title, ENTITY_ENABLE_SUFFIX
        )

    @property
    def is_on(self) -> bool:
        """Return the effective activation state."""
        return bool(self._value)

    def _valid_value(self, value: object) -> bool:
        return isinstance(value, bool)

    def _decode_last_state(self, raw: str) -> bool | None:
        if raw in ("on", "off"):
            return raw == "on"
        return None

    def _fallback_value(self) -> bool:
        return False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable detection using the saved stop mode."""
        await self._async_set_value(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Suspend detection and release an automatic stop."""
        await self._async_set_value(False)
