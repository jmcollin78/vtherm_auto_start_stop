"""Feature manager factory registered with ``vtherm_api``.

The factory is the single entry point the core uses to decide whether a
thermostat gets an auto-start/stop manager. It applies two gates, in this order:

1. **Eligibility** — the thermostat must be ``over_climate`` and must not be
   regulated by a valve. This is exactly the core feature's predicate, so no
   thermostat gains or loses support compared with the core.
2. **Effective configuration** — the layered resolution must return a
   configuration, including when its enable state is false.

The eligibility gate is recomputed on every load, so a thermostat reconfigured
into an ineligible state after its entry was created is not attached.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from vtherm_api.log_collector import get_vtherm_logger

from .const import (
    DATA_ENTRIES,
    DATA_FACTORY_REGISTERED,
    DOMAIN,
    MANAGER_NAME,
    THERMOSTAT_TYPE_CLIMATE,
)
from .manager import AutoStartStopManager
from .models import effective_config

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
    from vtherm_api.interfaces import (
        InterfaceFeatureManager,
        InterfaceThermostatRuntime,
    )

_LOGGER = get_vtherm_logger(__name__)


def thermostat_type(thermostat: "InterfaceThermostatRuntime") -> str | None:
    """Return the VTherm thermostat type, read from the runtime entry facts."""
    try:
        entry_infos = thermostat.entry_infos
    except Exception:  # pylint: disable=broad-except
        return None
    if not isinstance(entry_infos, dict):
        return None
    return entry_infos.get("thermostat_type")


def ineligibility_reason(thermostat: "InterfaceThermostatRuntime") -> str | None:
    """Return why a thermostat is ineligible, or ``None`` when it is eligible.

    The two rules are the ones the config flow reports to the user and the ones
    the factory re-checks on every load; sharing the function keeps them
    identical.
    """
    if thermostat_type(thermostat) != THERMOSTAT_TYPE_CLIMATE:
        return "not_over_climate"
    try:
        has_valve = bool(thermostat.has_valve_regulation)
    except Exception:  # pylint: disable=broad-except
        return "valve_regulation"
    if has_valve:
        return "valve_regulation"
    return None


class AutoStartStopManagerFactory:
    """Create one auto-start/stop manager per eligible thermostat."""

    def __init__(self, hass: "HomeAssistant") -> None:
        self._hass = hass

    @property
    def name(self) -> str:
        """Return the stable feature-manager identifier."""
        return MANAGER_NAME

    def supports(self, thermostat: "InterfaceThermostatRuntime") -> bool:
        """Return whether the plugin attaches to this thermostat."""
        reason = ineligibility_reason(thermostat)
        if reason is not None:
            _LOGGER.info(
                "%s - auto start/stop not attached: %s", thermostat.name, reason
            )
            return False

        entries = self._hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {})
        config = effective_config(entries, thermostat.unique_id)
        if config is None:
            _LOGGER.debug(
                "%s - auto start/stop not attached: no effective configuration",
                thermostat.name,
            )
            return False
        return True

    def create(
        self, thermostat: "InterfaceThermostatRuntime"
    ) -> "InterfaceFeatureManager":
        """Create a manager bound to the runtime thermostat."""
        return AutoStartStopManager(thermostat, self._hass)


def register_factory(
    hass: "HomeAssistant", factory: AutoStartStopManagerFactory
) -> None:
    """Register the factory once, idempotently."""
    data = hass.data.setdefault(DOMAIN, {})
    if data.get(DATA_FACTORY_REGISTERED):
        return

    from vtherm_api import VThermAPI

    api = VThermAPI.get_vtherm_api(hass)
    if api is None:
        _LOGGER.warning(
            "Auto start/stop factory not registered: the VTherm API is unavailable"
        )
        return

    if api.get_feature_manager(MANAGER_NAME) is None:
        api.register_feature_manager(factory)
    data[DATA_FACTORY_REGISTERED] = True
    _LOGGER.info(
        "Auto start/stop factory registered under the stable name '%s'", MANAGER_NAME
    )


def unregister_factory(hass: "HomeAssistant") -> None:
    """Remove the factory from the shared registry."""
    from vtherm_api import VThermAPI

    api = VThermAPI.get_vtherm_api(hass)
    if api is not None:
        api.unregister_feature_manager(MANAGER_NAME)
    hass.data.setdefault(DOMAIN, {})[DATA_FACTORY_REGISTERED] = False
