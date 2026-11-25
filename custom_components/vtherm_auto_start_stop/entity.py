"""Restorable per-thermostat controls, independent of parameter configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeGuard

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity
from vtherm_api.log_collector import get_vtherm_logger

from .const import (
    CONF_ENABLED,
    CONF_STOP_MODE,
    DATA_ENTRIES,
    DOMAIN,
    SIGNAL_MANAGER_UPDATED,
    STOP_MODE_OFF,
    STOP_MODES,
    VT_DOMAIN,
)
from .models import entry_config, initial_control_defaults
from .registry import (
    _core_entry,
    async_apply_controls,
    control_state,
    dedicated_entry,
    entity_owner,
    prepare_entity_ids,
)

if TYPE_CHECKING:
    from .manager import AutoStartStopManager

_LOGGER = get_vtherm_logger(__name__)
_STATE_VERSION_KEY = f"{DOMAIN}_state_version"


@dataclass
class ControlRestoreData(ExtraStoredData):
    """Distinguish persistent control choices from obsolete UI restore caches."""

    value: bool | str

    def as_dict(self) -> dict[str, bool | str | int]:
        return {_STATE_VERSION_KEY: 1, "value": self.value}


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


class AutoStartStopEntity(RestoreEntity):
    """A restorable control attached to its thermostat device."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _control_key: str

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
        self._value: bool | str | None = None

        device = thermostat_device(hass, vtherm_unique_id)
        if device is not None:
            self.device_entry = device
        else:
            core = _core_entry(hass, vtherm_unique_id)
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, vtherm_unique_id)},
                name=core.title if core else title,
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
        manager = self.manager
        return (
            manager is not None and manager.controls_ready and self._value is not None
        )

    async def async_added_to_hass(self) -> None:
        """Restore once, then attach the independent state to the live manager."""
        await super().async_added_to_hass()
        owner = entity_owner(self.hass, self._vtherm_unique_id)
        if owner is not None:
            prepare_entity_ids(self.hass, owner, self._vtherm_unique_id)
        state = control_state(self.hass, self._vtherm_unique_id)
        cached = state.enabled if self._control_key == CONF_ENABLED else state.stop_mode
        value = (
            cached if self._valid_value(cached) else await self._async_restore_value()
        )
        if self._control_key == CONF_STOP_MODE and self.manager is not None:
            if value not in self.manager.stop_modes:
                _LOGGER.warning(
                    "%s: restored stop mode %s is unsupported; using off",
                    self.entity_id,
                    value,
                )
                value = STOP_MODE_OFF
        self._value = value
        if self._control_key == CONF_ENABLED:
            state.enabled = bool(value)
        elif isinstance(value, str):
            state.stop_mode = value
        self._unsubscribers.append(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_MANAGER_UPDATED}_{self._vtherm_unique_id}",
                self._async_manager_updated,
            )
        )
        await async_apply_controls(self.hass, self._vtherm_unique_id)
        self.async_write_ha_state()

    @property
    def extra_restore_state_data(self) -> ExtraStoredData | None:
        if self._value is None:
            return None
        return ControlRestoreData(self._value)

    def _valid_value(self, value: object) -> TypeGuard[bool | str]:
        if self._control_key == CONF_ENABLED:
            return isinstance(value, bool)
        return isinstance(value, str) and value in STOP_MODES

    async def _async_restore_value(self) -> bool | str:
        extra = await self.async_get_last_extra_data()
        if extra is not None:
            saved = extra.as_dict()
            value = saved.get("value")
            if saved.get(_STATE_VERSION_KEY) == 1 and self._valid_value(value):
                return value
            if saved.get(_STATE_VERSION_KEY) == 1:
                _LOGGER.warning(
                    "%s: invalid saved control value %s", self.entity_id, value
                )
                if self._control_key == CONF_STOP_MODE:
                    return STOP_MODE_OFF
        legacy = dedicated_entry(self.hass, self._vtherm_unique_id)
        if legacy is not None:
            value = entry_config(legacy).get(self._control_key)
            if self._valid_value(value):
                return value
        last = await self.async_get_last_state()
        if last is not None:
            value = last.state
            if self._control_key == CONF_ENABLED:
                if value in ("on", "off"):
                    return value == "on"
            elif self._valid_value(value):
                return value
            if value not in ("unknown", "unavailable"):
                _LOGGER.warning(
                    "%s: cannot restore %s; using initialization default",
                    self.entity_id,
                    value,
                )
                if self._control_key == CONF_STOP_MODE:
                    return STOP_MODE_OFF
        defaults = initial_control_defaults(
            self.hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {})
        )
        value = defaults[self._control_key]
        if not self._valid_value(value):
            _LOGGER.warning(
                "%s: invalid initialization default %s", self.entity_id, value
            )
            return False if self._control_key == CONF_ENABLED else STOP_MODE_OFF
        return value

    @callback
    def _async_manager_updated(self) -> None:
        """Republish when the manager's state changed."""
        state = control_state(self.hass, self._vtherm_unique_id)
        value = state.enabled if self._control_key == CONF_ENABLED else state.stop_mode
        if self._valid_value(value):
            self._value = value
        if self.hass is not None and self.entity_id:
            self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Release the subscriptions."""
        while self._unsubscribers:
            self._unsubscribers.pop()()

    async def _async_set_value(self, value: bool | str) -> None:
        """Apply and remember a control action without changing configuration."""
        if (
            self.hass.config_entries.async_get_entry(self._entry_id) is None
            or entity_owner(self.hass, self._vtherm_unique_id) is None
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="missing_configuration",
            )
        state = control_state(self.hass, self._vtherm_unique_id)
        previous = (
            state.enabled if self._control_key == CONF_ENABLED else state.stop_mode
        )
        previous_value = self._value
        if self._control_key == CONF_ENABLED:
            state.enabled = bool(value)
        elif isinstance(value, str):
            state.stop_mode = value
        applied = False
        try:
            await async_apply_controls(self.hass, self._vtherm_unique_id)
            applied = True
        finally:
            if not applied:
                if self._control_key == CONF_ENABLED:
                    state.enabled = previous if isinstance(previous, bool) else None
                else:
                    state.stop_mode = previous if isinstance(previous, str) else None
                self._value = previous_value
                self.async_write_ha_state()
        self._value = value
        self.async_write_ha_state()
