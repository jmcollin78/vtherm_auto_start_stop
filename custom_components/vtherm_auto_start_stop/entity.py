"""Base entity shared by the plugin entities of one thermostat.

The plugin entities belong to a **dedicated** config entry and are shown on the
thermostat device, so the dashboard groups them with the thermostat they
configure. A thermostat configured only through the global instance owns no
entry at all, hence no entity: this is the phase-1 trade-off explained in the
design.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, SIGNAL_MANAGER_UPDATED, VT_DOMAIN

if TYPE_CHECKING:
    from .manager import AutoStartStopManager


def thermostat_device(
    hass: HomeAssistant, vtherm_unique_id: str
) -> dr.DeviceEntry | None:
    """Return the device of the targeted thermostat, found by its unique id.

    The entity id is only a lookup key: the stable reference is the thermostat
    unique id, so a rename is followed without touching the plugin entry.
    """
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("climate", VT_DOMAIN, vtherm_unique_id)
    entry = registry.async_get(entity_id) if entity_id else None
    if entry is None or not entry.device_id:
        return None
    return dr.async_get(hass).async_get(entry.device_id)


class AutoStartStopEntity(Entity):
    """An entity of a dedicated instance, attached to the thermostat device."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        hass: HomeAssistant,
        vtherm_unique_id: str,
        entry_id: str,
        title: str,
        key: str,
    ) -> None:
        self._vtherm_unique_id = vtherm_unique_id
        self._entry_id = entry_id
        self._attr_unique_id = f"{vtherm_unique_id}_{key}"
        self._attr_translation_key = key
        self._unsubscribers: list = []

        device = thermostat_device(hass, vtherm_unique_id)
        if device is not None:
            self.device_entry = device
        else:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, entry_id)}, name=title
            )

    @property
    def manager(self) -> "AutoStartStopManager | None":
        """Return the live manager, or ``None`` while the thermostat is not attached."""
        if self.hass is None:
            return None
        return (
            self.hass.data.get(DOMAIN, {})
            .get("managers", {})
            .get(self._vtherm_unique_id)
        )

    @property
    def available(self) -> bool:
        """An entity is available only while its manager is attached."""
        return self.manager is not None

    async def async_added_to_hass(self) -> None:
        """Follow the manager's decisions."""
        await super().async_added_to_hass()
        self._unsubscribers.append(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_MANAGER_UPDATED}_{self._vtherm_unique_id}",
                self._async_manager_updated,
            )
        )

    @callback
    def _async_manager_updated(self) -> None:
        """Republish when the manager's state changed."""
        if self.hass is not None and self.entity_id:
            self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Release the subscriptions."""
        while self._unsubscribers:
            self._unsubscribers.pop()()

    def _entry_values(self) -> dict:
        """Return the current values of the entry owning this entity."""
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        return dict(entry.options or entry.data) if entry else {}

    def _persist(self, key: str, value: object) -> None:
        """Store a value in the entry options so it survives a restart."""
        entry = self.hass.config_entries.async_get_entry(self._entry_id)
        if entry is None:
            return
        current = dict(entry.options or entry.data)
        if current.get(key) == value:
            return
        current[key] = value
        self.hass.config_entries.async_update_entry(entry, options=current)
