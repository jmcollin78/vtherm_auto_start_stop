"""Persistent stop-mode and level selectors of every covered thermostat.

Selecting a compatible stop mode does not change activation. The independent
enable switch controls whether detection runs.

The level selector is a **preset**: its option is the level derived from the two
parameters, and selecting a named level writes both parameters in one coherent
change. Selecting ``personnalise`` writes nothing — it is the state a custom pair
already produces.
"""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from vtherm_api.log_collector import get_vtherm_logger

from .const import (
    CONF_LEVEL,
    CONF_STOP_MODE,
    DOMAIN,
    ENTITY_LEVEL_SUFFIX,
    ENTITY_STOP_MODE_SUFFIX,
    LEVELS,
    LEVEL_PERSONNALISE,
    PLATFORM_SELECT,
    STOP_MODE_OFF,
    STOP_MODES,
)
from .entity import AutoStartStopEntity
from .registry import (
    ensure_all_entities,
    entity_owner,
    register_callback,
    unregister_callback,
)

_LOGGER = get_vtherm_logger(__name__)


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
    _control_key = "stop_mode"

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

    def _valid_value(self, value: object) -> bool:
        return isinstance(value, str) and value in STOP_MODES

    def _seed_key(self) -> str:
        """Return the entry key seeding this control."""
        return CONF_STOP_MODE

    def _fallback_value(self) -> str:
        return STOP_MODE_OFF

    def _normalize_restored(self, value):
        """Fall back to ``off`` when the restored mode is unsupported."""
        manager = self.manager
        if isinstance(value, str) and manager is not None:
            if value not in manager.stop_modes:
                _LOGGER.warning(
                    "%s: restored stop mode %s is unsupported; using off",
                    self.entity_id,
                    value,
                )
                return STOP_MODE_OFF
        return value

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


class AutoStartStopLevelSelect(AutoStartStopEntity, SelectEntity):
    """Read the derived detection level and select a named level as a preset.

    The level is never stored: :attr:`current_option` reads the pair of
    parameters through the manager. Selecting a named level calls the manager's
    single :meth:`apply_level` operation, which writes both parameters and
    publishes one update.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:tachometer"
    _control_key = "level"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, vtherm_unique_id: str
    ) -> None:
        super().__init__(
            hass,
            vtherm_unique_id,
            entry.entry_id,
            entry.title,
            ENTITY_LEVEL_SUFFIX,
        )

    def _valid_value(self, value: object) -> bool:
        return isinstance(value, str) and value in LEVELS

    def _seed_key(self) -> str:
        """Return the entry key seeding this control."""
        return CONF_LEVEL

    def _fallback_value(self) -> str:
        return LEVEL_PERSONNALISE

    @property
    def options(self) -> list[str]:
        """Return the named levels and the custom label."""
        return list(LEVELS)

    @property
    def current_option(self) -> str | None:
        """Return the derived level of the current parameter pair."""
        manager = self.manager
        if manager is not None and manager.controls_ready:
            return manager.level
        return self._value if isinstance(self._value, str) else None

    async def async_select_option(self, option: str) -> None:
        """Select a named level as a preset, or refuse a no-op custom selection."""
        if option not in LEVELS:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_auto_start_stop_option",
                translation_placeholders={"option": option},
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
        if option == LEVEL_PERSONNALISE:
            # ``personnalise`` is the label of a custom pair, not a value to
            # write. Refuse a selection that would change nothing, so the UI
            # never shows a choice the plugin did not honour.
            if manager.level != LEVEL_PERSONNALISE:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="level_already_named",
                    translation_placeholders={"level": manager.level},
                )
            return
        await manager.apply_level(option)
