"""Writable detection parameters of every covered thermostat.

Two numbers carry the detection criteria: the minimum duration before a stop is
allowed, and the accumulated-error threshold that triggers a decision. They are
``RestoreNumber`` entities: a user's value survives reloads and restarts, and the
configuration entry only seeds them when no restored state exists.

An out-of-range write is refused with an explicit validation error, leaving the
previous value and the accumulated deviation untouched. ``available`` is never
overloaded to express a refusal: Home Assistant silently filters a service call
that targets an unavailable entity, so a refusal must be a raised error.
"""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode, RestoreNumber
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_DT_MIN,
    CONF_ERROR_THRESHOLD,
    DOMAIN,
    DT_MIN_MAX_VALUE,
    DT_MIN_MIN_VALUE,
    ENTITY_DT_MIN_SUFFIX,
    ENTITY_ERROR_THRESHOLD_SUFFIX,
    ERROR_THRESHOLD_MAX_VALUE,
    ERROR_THRESHOLD_MIN_VALUE,
    ERROR_THRESHOLD_STEP,
    PLATFORM_NUMBER,
)
from .entity import AutoStartStopEntity
from .registry import (
    ensure_all_entities,
    entity_owner,
    register_callback,
    unregister_callback,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Register the number callback of a covering entry."""
    register_callback(hass, PLATFORM_NUMBER, entry.entry_id, async_add_entities)
    entry.async_on_unload(
        lambda: unregister_callback(hass, PLATFORM_NUMBER, entry.entry_id)
    )
    ensure_all_entities(hass)


class _AutoStartStopParameterNumber(AutoStartStopEntity, RestoreNumber):
    """Base of the two parameter numbers: bounds, refuse, apply to the manager."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX

    def _valid_value(self, value: object) -> bool:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and self.native_min_value <= value <= self.native_max_value
        )

    def _decode_last_state(self, raw: str) -> float | None:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        return value if self._valid_value(value) else None

    @property
    def native_value(self) -> float | None:
        """Return the restored or written value, as a number."""
        return float(self._value) if self._value is not None else None

    async def async_set_native_value(self, value: float) -> None:
        """Refuse an out-of-range value explicitly, then apply both parameters."""
        if not self._valid_value(value):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_auto_start_stop_bound",
                translation_placeholders={
                    "entity_id": self.entity_id or self.unique_id,
                    "min": str(self.native_min_value),
                    "max": str(self.native_max_value),
                    "value": str(value),
                },
            )
        if (
            self.hass.config_entries.async_get_entry(self._entry_id) is None
            or entity_owner(self.hass, self._vtherm_unique_id) is None
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="missing_configuration",
            )
        manager = self.manager
        if manager is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="missing_configuration",
            )
        if self._control_key == "dt_min":
            await manager.apply_parameters(float(value), manager.error_threshold)
        else:
            await manager.apply_parameters(manager.dt_min, float(value))
        # Reflect the write immediately: the dispatcher notification is
        # asynchronous, and a refused write must never reach this point.
        self._value = float(value)
        self.async_write_ha_state()

    def _seed_key(self) -> str:
        """Return the entry key seeding this control."""
        return self._control_key


class AutoStartStopDtMinNumber(_AutoStartStopParameterNumber):
    """Minimum duration before a stop, in minutes."""

    _attr_native_min_value = DT_MIN_MIN_VALUE
    _attr_native_max_value = DT_MIN_MAX_VALUE
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_icon = "mdi:timer-sand"
    _control_key = "dt_min"

    def _seed_key(self) -> str:
        """Return the entry key seeding this control."""
        return CONF_DT_MIN

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, vtherm_unique_id: str
    ) -> None:
        super().__init__(
            hass, vtherm_unique_id, entry.entry_id, entry.title, ENTITY_DT_MIN_SUFFIX
        )

    def _fallback_value(self) -> float:
        return float(DT_MIN_MIN_VALUE)


class AutoStartStopErrorThresholdNumber(_AutoStartStopParameterNumber):
    """Accumulated-error threshold that triggers a stop."""

    _attr_native_min_value = ERROR_THRESHOLD_MIN_VALUE
    _attr_native_max_value = ERROR_THRESHOLD_MAX_VALUE
    _attr_native_step = ERROR_THRESHOLD_STEP
    _attr_icon = "mdi:chart-bell-curve-cumulative"
    _control_key = "error_threshold"

    def _seed_key(self) -> str:
        """Return the entry key seeding this control."""
        return CONF_ERROR_THRESHOLD

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, vtherm_unique_id: str
    ) -> None:
        super().__init__(
            hass,
            vtherm_unique_id,
            entry.entry_id,
            entry.title,
            ENTITY_ERROR_THRESHOLD_SUFFIX,
        )

    def _fallback_value(self) -> float:
        return float(ERROR_THRESHOLD_MIN_VALUE)
