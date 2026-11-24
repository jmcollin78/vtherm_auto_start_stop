"""Config flow of the auto start/stop plugin.

Three branches share one integration:

* the **global** branch — created when no entry exists yet; its ``unique_id`` is
  the domain, so a second global instance is refused;
* the **dedicated** branch — one per thermostat, its ``unique_id`` being
  ``<domain>-<thermostat unique id>``;
* the **exclusion** branch — a dedicated entry with no parameter, telling the
  plugin the thermostat opts out of the global configuration.

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
    CONF_ENABLED,
    CONF_EXCLUDED,
    CONF_LEVEL,
    CONF_STOP_MODE,
    CONF_TARGET_ENTITY,
    CONF_VTHERM_UNIQUE_ID,
    DOMAIN,
    LEGACY_REGULATION_MODE,
    LEGACY_REGULATION_VALVE,
    LEGACY_THERMOSTAT_TYPE,
    LEVELS,
    STOP_MODES,
    THERMOSTAT_TYPE_CLIMATE,
    VT_DOMAIN,
)
from .models import default_config, legacy_level

_LOGGER = get_vtherm_logger(__name__)

ERROR_NOT_OVER_CLIMATE = "not_over_climate"
ERROR_VALVE_REGULATION = "valve_regulation"
ERROR_INVALID_ENTITY = "invalid_entity"


def _options_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Schema of the configuration values of a global or dedicated entry."""
    return vol.Schema(
        {
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
        }
    )


def _target_schema(exclude: list[str] | None = None) -> vol.Schema:
    """Schema selecting the thermostat, filtered on the VTherm integration."""
    return vol.Schema(
        {
            vol.Required(CONF_TARGET_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=CLIMATE_DOMAIN,
                    integration=VT_DOMAIN,
                    exclude_entities=exclude or [],
                )
            )
        }
    )


def _exclusion_schema() -> vol.Schema:
    """Schema of the exclusion branch: only the thermostat, no parameter."""
    return _target_schema()


def _global_defaults(hass) -> dict[str, Any]:
    """Return the global entry values, completed by the plugin defaults."""
    defaults = default_config()
    for entry in hass.config_entries.async_entries(DOMAIN):
        config = dict(entry.options or entry.data)
        if not config.get(CONF_VTHERM_UNIQUE_ID):
            defaults.update({key: config[key] for key in defaults if key in config})
    return defaults


class AutoStartStopConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure the global defaults, a thermostat or an exclusion."""

    VERSION = 1

    def __init__(self) -> None:
        super().__init__()
        self._target_entity_id = ""
        self._target_unique_id = ""
        self._exclude = False

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
        """Route to the global branch when no entry exists, else ask the intent."""
        if not self._async_current_entries():
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return await self.async_step_global(user_input)
        return await self.async_step_menu(user_input)

    async def async_step_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user choose a thermostat entry or an exclusion.

        ``user_input`` is unused: a menu step only renders the choices, and the
        selected option starts the matching step.
        """
        del user_input
        return self.async_show_menu(
            step_id="menu",
            menu_options=["thermostat", "exclusion"],
        )

    # -- global branch ------------------------------------------------------

    async def async_step_global(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the single global instance."""
        if user_input is not None:
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
                    self._exclude = False
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
        if user_input is not None:
            data = dict(user_input)
            data[CONF_VTHERM_UNIQUE_ID] = self._target_unique_id
            data.pop(CONF_EXCLUDED, None)
            return self.async_create_entry(title=self._target_title(), data=data)

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

        return self.async_show_form(
            step_id="thermostat_options", data_schema=_options_schema(defaults)
        )

    # -- exclusion branch ---------------------------------------------------

    async def async_step_exclusion(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create an exclusion entry for a thermostat."""
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
                    return self.async_create_entry(
                        title=f"{self._target_title()} (excluded)",
                        data={
                            CONF_VTHERM_UNIQUE_ID: self._target_unique_id,
                            CONF_EXCLUDED: True,
                        },
                    )

        return self.async_show_form(
            step_id="exclusion",
            data_schema=_exclusion_schema(),
            errors=errors,
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

        if thermostat_type is not None and thermostat_type != THERMOSTAT_TYPE_CLIMATE:
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
        """Edit the values of the entry; an exclusion has none."""
        current = dict(self._config_entry.options or self._config_entry.data)

        if current.get(CONF_EXCLUDED):
            return self.async_abort(reason="exclusion_not_configurable")

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        defaults = _global_defaults(self.hass)
        defaults.update({key: current[key] for key in defaults if key in current})
        return self.async_show_form(
            step_id="init", data_schema=_options_schema(defaults)
        )
