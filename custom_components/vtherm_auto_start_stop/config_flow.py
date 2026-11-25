"""Config flow of the auto start/stop plugin.

Two branches share one integration:

* the **global** branch — created when no entry exists yet; its ``unique_id`` is
  the domain, so a second global instance is refused;
* the **dedicated** branch — one per thermostat, its ``unique_id`` being
  ``<domain>-<thermostat unique id>``.

The dedicated branch checks eligibility before the user validates and returns an
explicit error naming the reason, which is the phase-1 improvement over the core
flow (the core simply hides the menu).
"""

from __future__ import annotations

from typing import Any
import voluptuous as vol
from homeassistant.components.climate.const import DOMAIN as CLIMATE_DOMAIN
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import selector
from vtherm_api.log_collector import get_vtherm_logger

from .const import (
    CONF_DT_MIN,
    CONF_ENABLED,
    CONF_ERROR_THRESHOLD,
    CONF_LEVEL,
    CONF_STOP_MODE,
    CONF_TARGET_ENTITY,
    CONF_VTHERM_UNIQUE_ID,
    DEFAULT_ERROR_THRESHOLD,
    DEFAULT_DT_MIN,
    DOMAIN,
    LEGACY_REGULATION_MODE,
    LEGACY_REGULATION_VALVE,
    LEGACY_THERMOSTAT_TYPE,
    LEVELS,
    STOP_MODES,
    THERMOSTAT_TYPE_CLIMATE,
    VT_DOMAIN,
)
from .models import default_config, entry_config, legacy_level

_LOGGER = get_vtherm_logger(__name__)

ERROR_NOT_OVER_CLIMATE = "not_over_climate"
ERROR_VALVE_REGULATION = "valve_regulation"
ERROR_INVALID_ENTITY = "invalid_entity"


def _options_schema(
    defaults: dict[str, Any], *, parameters_only: bool = False
) -> vol.Schema:
    """Schema of the configuration values of a global or dedicated entry."""
    fields = {
        vol.Optional(CONF_LEVEL, default=defaults[CONF_LEVEL]): (
            selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=LEVELS,
                    translation_key="auto_start_stop_level",
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
        ),
        vol.Optional(CONF_STOP_MODE, default=defaults[CONF_STOP_MODE]): (
            selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=STOP_MODES,
                    translation_key="auto_start_stop_stop_mode",
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
        ),
        vol.Optional(CONF_ENABLED, default=defaults[CONF_ENABLED]): (
            selector.BooleanSelector()
        ),
        vol.Optional(CONF_DT_MIN, default=defaults.get(CONF_DT_MIN, DEFAULT_DT_MIN)): (
            selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=5,
                    max=120,
                    unit_of_measurement="min",
                    mode=selector.NumberSelectorMode.BOX,
                )
            )
        ),
        vol.Optional(
            CONF_ERROR_THRESHOLD,
            default=defaults.get(CONF_ERROR_THRESHOLD, DEFAULT_ERROR_THRESHOLD),
        ): (
            selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=50,
                    step=0.5,
                    mode=selector.NumberSelectorMode.BOX,
                )
            )
        ),
    }
    if parameters_only:
        detection_keys = (CONF_LEVEL, CONF_DT_MIN, CONF_ERROR_THRESHOLD)
        fields = {
            key: value for key, value in fields.items() if key.schema in detection_keys
        }
    return vol.Schema(fields)


def _is_number(value: Any) -> bool:
    """Return whether a value is a real number (bool is excluded on purpose)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _clamp_numbers(user_input: dict[str, Any]) -> None:
    """Defensively clamp the custom parameters to the selector bounds.

    The UI (selector.NumberSelector) already refuses out-of-range values; this
    is a last-line guard for programmatic submits so a bad value is corrected
    instead of silently accepted.
    """
    dt_min = user_input.get(CONF_DT_MIN)
    if _is_number(dt_min):
        user_input[CONF_DT_MIN] = max(5, min(120, int(dt_min)))
    threshold = user_input.get(CONF_ERROR_THRESHOLD)
    if _is_number(threshold):
        user_input[CONF_ERROR_THRESHOLD] = max(1.0, min(50.0, float(threshold)))


def _target_schema() -> vol.Schema:
    """Schema selecting the thermostat, filtered on the VTherm integration."""
    return vol.Schema(
        {
            vol.Required(CONF_TARGET_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=CLIMATE_DOMAIN,
                    integration=VT_DOMAIN,
                )
            )
        }
    )


def _global_defaults(hass) -> dict[str, Any]:
    """Return the global entry values, completed by the plugin defaults."""
    defaults = default_config()
    for entry in hass.config_entries.async_entries(DOMAIN):
        config = entry_config(entry)
        if not config.get(CONF_VTHERM_UNIQUE_ID):
            defaults.update({key: config[key] for key in defaults if key in config})
    return defaults


class AutoStartStopConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure the global defaults or one thermostat."""

    VERSION = 1

    def __init__(self) -> None:
        super().__init__()
        self._target_entity_id = ""
        self._target_unique_id = ""

    def is_matching(self, other_flow: ConfigFlow) -> bool:
        """Return whether another flow targets the same entry.

        Home Assistant calls this to merge flows started from different sources
        for the same unique id.
        """
        return other_flow.unique_id == self.unique_id

    # -- entry point --------------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create global defaults first, then configure thermostats directly."""
        if not self._async_current_entries():
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return await self.async_step_global(user_input)
        return await self.async_step_thermostat(user_input)

    # -- global branch ------------------------------------------------------

    async def async_step_global(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the single global instance."""
        if user_input is not None:
            _clamp_numbers(user_input)
            return self.async_create_entry(
                title="Auto start/stop defaults", data=user_input
            )
        return self.async_show_form(
            step_id="global", data_schema=_options_schema(_global_defaults(self.hass))
        )

    # -- dedicated branch ---------------------------------------------------

    async def async_step_thermostat(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select the thermostat of a dedicated instance."""
        errors: dict[str, str] = {}
        if user_input is not None:
            entity_id = user_input[CONF_TARGET_ENTITY]
            registry_entry = er.async_get(self.hass).async_get(entity_id)
            if registry_entry is None:
                errors[CONF_TARGET_ENTITY] = ERROR_INVALID_ENTITY
            else:
                error = self._eligibility_error(entity_id)
                if error is not None:
                    errors[CONF_TARGET_ENTITY] = error
                else:
                    self._target_entity_id = entity_id
                    self._target_unique_id = registry_entry.unique_id
                    await self.async_set_unique_id(f"{DOMAIN}-{self._target_unique_id}")
                    self._abort_if_unique_id_configured()
                    return await self.async_step_thermostat_options()

        return self.async_show_form(
            step_id="thermostat",
            data_schema=_target_schema(),
            errors=errors,
        )

    async def async_step_thermostat_options(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set the values of a dedicated instance, seeded from the legacy level."""
        defaults = _global_defaults(self.hass)
        # Adopt the level the thermostat carried before the migration, unless
        # the thermostat already has a dedicated instance (the cascade is not
        # used here: this is the creation of the dedicated instance itself).
        seeded = legacy_level(self._core_entry_infos())
        if seeded is not None:
            defaults[CONF_LEVEL] = seeded
            _LOGGER.info(
                "%s - dedicated auto start/stop instance seeded with the legacy "
                "level '%s'",
                self._target_unique_id,
                seeded,
            )

        if user_input is not None:
            data = dict(user_input)
            _clamp_numbers(data)
            data[CONF_VTHERM_UNIQUE_ID] = self._target_unique_id
            return self.async_create_entry(title=self._target_title(), data=data)

        return self.async_show_form(
            step_id="thermostat_options",
            data_schema=_options_schema(defaults, parameters_only=True),
        )

    # -- helpers ------------------------------------------------------------

    def _core_entry_infos(self) -> dict[str, Any]:
        """Return the data of the thermostat's core config entry."""
        registry_entry = er.async_get(self.hass).async_get(self._target_entity_id)
        if registry_entry is None or registry_entry.config_entry_id is None:
            return {}
        core_entry = self.hass.config_entries.async_get_entry(
            registry_entry.config_entry_id
        )
        if core_entry is None:
            return {}
        return {**core_entry.data, **core_entry.options}

    def _eligibility_error(self, entity_id: str) -> str | None:
        """Return the eligibility error for a thermostat entity, if any."""
        state = self.hass.states.get(entity_id)
        attributes = state.attributes if state is not None else {}

        thermostat_type = attributes.get("configuration", {}).get("type") or (
            attributes.get("thermostat_type")
        )
        has_valve = attributes.get("configuration", {}).get(
            "have_valve_regulation", False
        )

        # Published types omit the "thermostat_" prefix used in config entries.
        if thermostat_type is not None and thermostat_type not in (
            "over_climate",
            THERMOSTAT_TYPE_CLIMATE,
        ):
            return ERROR_NOT_OVER_CLIMATE
        if has_valve:
            return ERROR_VALVE_REGULATION
        if thermostat_type is None:
            # Fall back to the config entry when the state attributes are not
            # published yet (right after a restart).
            infos = self._entry_infos_for(entity_id)
            if infos.get(LEGACY_THERMOSTAT_TYPE) != THERMOSTAT_TYPE_CLIMATE:
                return ERROR_NOT_OVER_CLIMATE
            if infos.get(LEGACY_REGULATION_MODE) == LEGACY_REGULATION_VALVE:
                return ERROR_VALVE_REGULATION
        return None

    def _entry_infos_for(self, entity_id: str) -> dict[str, Any]:
        """Return the core entry data of an entity."""
        registry_entry = er.async_get(self.hass).async_get(entity_id)
        if registry_entry is None or registry_entry.config_entry_id is None:
            return {}
        entry = self.hass.config_entries.async_get_entry(registry_entry.config_entry_id)
        if entry is None:
            return {}
        return {**entry.data, **entry.options}

    def _target_title(self) -> str:
        """Return the title of a dedicated entry."""
        state = self.hass.states.get(self._target_entity_id)
        return state.name if state else self._target_entity_id

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow of an entry."""
        return AutoStartStopOptionsFlow(config_entry)


class AutoStartStopOptionsFlow(OptionsFlow):
    """Edit an existing entry in place."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the global or dedicated settings."""
        current = entry_config(self._config_entry)

        if user_input is not None:
            _clamp_numbers(user_input)
            return self.async_create_entry(title="", data=user_input)

        defaults = _global_defaults(self.hass)
        defaults.update({key: current[key] for key in defaults if key in current})
        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(
                defaults, parameters_only=bool(current.get(CONF_VTHERM_UNIQUE_ID))
            ),
        )
