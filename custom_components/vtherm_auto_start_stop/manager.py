"""Auto start/stop feature manager bound to one thermostat.

The manager implements the external feature-manager contract exposed by
``vtherm_api``. The core instantiates it from the registered factory, refreshes
it on every cycle, merges its custom attributes into the thermostat state, and —
after the delegation change — resolves it as the auto-start/stop decision owner.

Two behaviours are specific to this plugin:

* it reads the *runtime clock* (``thermostat.now``) and never a local clock, so
  the two refreshes of one cycle cannot accumulate twice;
* it asks for an immediate state refresh only when its detection flag changes,
  so a detected stop is applied in the same cycle while an unchanged cycle costs
  nothing.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.util import dt as dt_util
from vtherm_api.const import EventType
from vtherm_api.log_collector import get_vtherm_logger, write_event_log

from .algorithm import AutoStartStopDetectionAlgorithm
from .const import (
    ATTR_ACCUMULATED_ERROR,
    ATTR_ACCUMULATED_ERROR_THRESHOLD,
    ATTR_DTMIN,
    ATTR_ENABLE,
    ATTR_IS_CONFIGURED,
    ATTR_IS_STOP_DETECTED,
    ATTR_LAST_SWITCH_DATE,
    ATTR_LEVEL,
    ATTR_STOP_MODE,
    CONF_LEVEL,
    DATA_MANAGERS,
    DOMAIN,
    HVAC_OFF_REASON_AUTO_START_STOP,
    MANAGER_ATTRIBUTES_KEY,
    MANAGER_NAME,
    SIGNAL_MANAGER_UPDATED,
    STOP_MODE_DRY,
    STOP_MODE_FAN_ONLY,
    STOP_MODE_OFF,
)
from .models import effective_config, normalize_level, normalize_stop_mode
from .registry import control_state, ensure_entities

_LOGGER = get_vtherm_logger(__name__)


class AutoStartStopManager:
    """The auto start/stop feature manager of one thermostat."""

    def __init__(self, thermostat: Any, hass: HomeAssistant) -> None:
        self._thermostat = thermostat
        self._hass = hass
        self._configured = False
        self._enabled = False
        self._controls_ready = False
        self._stop_mode = STOP_MODE_OFF
        self._is_stop_detected = False
        self._algorithm = AutoStartStopDetectionAlgorithm(
            normalize_level(None), str(thermostat)
        )
        # Capture the clock of the last refresh, so a transition can be
        # detected even when the flag is restored from a previous state.
        self._last_refresh: datetime | None = None
        self._stop_modes_cache: list[str] | None = None

    # ------------------------------------------------------------------
    # InterfaceFeatureManager
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        """Return the stable name the delegation resolves."""
        return MANAGER_NAME

    @property
    def hass(self) -> HomeAssistant:
        """Return the Home Assistant instance."""
        return self._hass

    @property
    def is_configured(self) -> bool:
        """Return whether the manager has an effective configuration."""
        return self._configured

    @property
    def is_detected(self) -> bool:
        """Return whether a stop is currently detected."""
        return self.enabled and self._is_stop_detected

    # The core state arbitration and the core entities read the auto-start/stop
    # manager through the core names, not the generic interface names. The core
    # resolves ``vtherm.auto_start_stop_manager`` to *this* manager once the
    # feature is delegated, so these aliases are part of the delegation contract
    # and not a convenience: without them the arbitration would raise.
    @property
    def is_auto_stop_detected(self) -> bool:
        """Return the detection flag under the name the core arbitration reads."""
        return self.is_detected

    @property
    def auto_start_stop_enable(self) -> bool:
        """Return the enable state under the name the core entities read."""
        return self.enabled

    async def set_auto_start_stop_enable(self, enabled: bool) -> None:
        """Apply an enable change coming from the core entity."""
        await self.async_set_enabled(enabled)

    async def set_auto_start_stop_stop_mode(self, stop_mode: str) -> None:
        """Apply a stop-mode change coming from the core entity."""
        await self.async_set_stop_mode(stop_mode)

    def reset_switch_delay(self) -> None:
        """Allow an immediate decision after a deliberate user change.

        Called by the core when the preset or the target temperature changes
        significantly: the user explicitly asked for something else, so the
        switch delay must not hold the previous decision.
        """
        self._algorithm.reset_switch_delay()

    def post_init(self, entry_infos: dict[str, Any]) -> None:
        """Resolve the configuration and register the live manager.

        ``entry_infos`` is the thermostat configuration the core passes to every
        manager. The plugin ignores it: its own configuration lives in its
        config entries, and the legacy level is read when a dedicated entry is
        created (see the config flow), not from the merged thermostat data.
        """
        del entry_infos
        entries = self._hass.data.get(DOMAIN, {}).get("entries", {})
        config = effective_config(entries, self._thermostat.unique_id)
        if config is None:
            self._dispose("no effective configuration")
            return

        self._configured = True
        state = control_state(self._hass, self._thermostat.unique_id)
        if state.enabled is not None and state.stop_mode is not None:
            self.restore_entity_state(state.enabled, state.stop_mode)
        level = normalize_level(config.get(CONF_LEVEL))
        self._algorithm.set_params(level, config)
        self._algorithm.reset_switch_delay()

        self._hass.data.setdefault(DOMAIN, {}).setdefault(DATA_MANAGERS, {})[
            self._thermostat.unique_id
        ] = self
        _LOGGER.info(
            "%s - auto start/stop registered (level=%s, stop_mode=%s, enabled=%s)",
            self,
            level,
            self._stop_mode,
            self._enabled,
        )
        ensure_entities(self._hass, self._thermostat.unique_id)
        # Seed the stop-mode cache with the value resolved at registration so
        # the first refresh does not publish merely to populate it. The list
        # can later grow once the underlyings are attached (see refresh_state).
        self._stop_modes_cache = self.stop_modes
        async_dispatcher_send(
            self._hass,
            f"{SIGNAL_MANAGER_UPDATED}_{self._thermostat.unique_id}",
        )

    async def start_listening(self, force: bool = False) -> None:
        """No listeners are required: the core drives the refresh."""
        del force

    def stop_listening(self) -> None:
        """Release the live manager registration."""
        self._dispose("thermostat unloaded")

    async def refresh_state(self) -> bool:
        """Run one detection cycle and return whether a stop is detected."""
        if not self._configured or not self._controls_ready:
            return False

        # Republish when the accepted stop modes change (e.g. the underlyings
        # finish initialising and their HVAC modes become available). This
        # mirrors the core's ``async_my_climate_changed`` callback: the list
        # can only grow (modes added), never shrink, so a single re-publish
        # after the underlying is ready is sufficient.
        current_modes = self.stop_modes
        if current_modes != self._stop_modes_cache:
            self._stop_modes_cache = current_modes
            self._publish_update()

        if not self._enabled:
            # Disabled: stop accumulating and release any applied stop.
            if self._is_stop_detected:
                self._is_stop_detected = False
                self._algorithm.reset_switch_delay()
            return False

        now = self._thermostat.now
        self._last_refresh = now

        detected = self._algorithm.should_be_turned_off(
            self._thermostat.requested_hvac_mode,
            self._thermostat.target_temperature,
            self._thermostat.current_temperature,
            (self._thermostat.last_temperature_slope or 0.0) / 60,
            now,
        )
        changed = detected != self._is_stop_detected
        self._is_stop_detected = detected

        if changed:
            write_event_log(
                _LOGGER,
                self._thermostat,
                f"Auto start/stop state changed to {detected}",
            )
            self._send_event(detected)
            self._publish_update()
            await self._thermostat.async_request_state_refresh()

        return detected

    async def refresh_and_update_if_changed(self) -> bool:
        """Refresh and report whether the decision changed.

        The core calls this on the state-change paths. The immediate refresh is
        requested inside :meth:`refresh_state` and only on a transition, so a
        cycle with no decision costs no recalculation while a decision taken on a
        state-change path is still applied within the same cycle.
        """
        before = self._is_stop_detected
        await self.refresh_state()
        return self._is_stop_detected != before

    def restore_state(self, old_state: Any) -> None:
        """Restore the detection flag and the algorithm state after a restart."""
        if old_state is None:
            return

        section = (old_state.attributes or {}).get(MANAGER_ATTRIBUTES_KEY)
        if not section:
            return

        if not self._configured:
            return

        self._is_stop_detected = self.enabled and bool(
            section.get(ATTR_IS_STOP_DETECTED, False)
        )
        last_switch: datetime | None = None
        raw = section.get(ATTR_LAST_SWITCH_DATE)
        if isinstance(raw, str):
            last_switch = dt_util.parse_datetime(raw)
        elif isinstance(raw, datetime):
            last_switch = raw

        accumulated = section.get(ATTR_ACCUMULATED_ERROR)
        self._algorithm.restore(
            float(accumulated) if accumulated is not None else None,
            last_switch,
        )

    def add_listener(self, func) -> None:
        """Register a callback; unused by this manager."""

    def add_custom_attributes(self, attributes: dict[str, Any]) -> None:
        """Publish the auto-start/stop attribute section.

        The section and its keys are reproduced verbatim from the core feature
        so the existing card and the LLM attribute index keep working.
        """
        attributes[ATTR_IS_CONFIGURED] = self._configured
        if not self._configured:
            return

        attributes[MANAGER_ATTRIBUTES_KEY] = {
            ATTR_ENABLE: self.enabled,
            ATTR_LEVEL: self._algorithm.level,
            ATTR_DTMIN: self._algorithm.dt_min,
            ATTR_ACCUMULATED_ERROR: self._algorithm.accumulated_error,
            ATTR_ACCUMULATED_ERROR_THRESHOLD: (
                self._algorithm.accumulated_error_threshold
            ),
            ATTR_LAST_SWITCH_DATE: self._algorithm.last_switch_date,
            ATTR_IS_STOP_DETECTED: self.is_detected,
            ATTR_STOP_MODE: self._stop_mode,
        }

    # ------------------------------------------------------------------
    # Entities
    # ------------------------------------------------------------------

    @property
    def vtherm_unique_id(self) -> str:
        """Return the unique id of the bound thermostat."""
        return self._thermostat.unique_id

    @property
    def device_entry(self) -> Any:
        """Return the thermostat device, so entities attach to it."""
        from homeassistant.helpers import device_registry as dr
        from homeassistant.helpers import entity_registry as er

        registry = er.async_get(self._hass)
        entry = registry.async_get(self._thermostat.entity_id)
        if entry is None or entry.device_id is None:
            return None
        return dr.async_get(self._hass).async_get(entry.device_id)

    @property
    def enabled(self) -> bool:
        """Return the persisted enable state."""
        return self._controls_ready and self._enabled

    @property
    def controls_ready(self) -> bool:
        return self._controls_ready

    @property
    def stop_mode(self) -> str:
        """Return the configured stop mode.

        Returned as the plain string the core arbitration compares against its
        own HVAC modes: the core wraps the value back into a ``VThermHvacMode``,
        which accepts a ``str`` as well as its own instances.
        """
        return self._stop_mode

    @property
    def stop_modes(self) -> list[str]:
        """Return the stop modes accepted by the thermostat.

        ``fan_only`` and ``dry`` are only offered when the thermostat accepts
        them; ``off`` is always available.
        """
        accepted = {str(mode) for mode in (self._thermostat.vtherm_hvac_modes or [])}
        options = [STOP_MODE_OFF]
        if STOP_MODE_FAN_ONLY in accepted:
            options.append(STOP_MODE_FAN_ONLY)
        if STOP_MODE_DRY in accepted:
            options.append(STOP_MODE_DRY)
        return options

    @property
    def is_auto_stopped(self) -> bool:
        """Return whether the thermostat is currently stopped by this feature.

        Mirrors the core predicate: the thermostat is off *and* its off reason is
        the auto-start/stop one. The reason is set by the core arbitration when it
        applies the stop this manager asks for, so reading it is how the plugin
        knows its decision actually took effect rather than being overridden by
        an inhibition, a window detection or a central mode.
        """
        return (
            str(self._thermostat.hvac_mode) == STOP_MODE_OFF
            and getattr(self._thermostat, "hvac_off_reason", None)
            == HVAC_OFF_REASON_AUTO_START_STOP
        )

    async def async_set_enabled(self, enabled: bool) -> None:
        """Apply a new enable state; its switch owns persistence."""
        if self._enabled == enabled:
            return
        self._enabled = enabled
        write_event_log(
            _LOGGER,
            self._thermostat,
            f"Auto start/stop enable changed to {enabled}",
        )
        await self.refresh_state()
        await self._thermostat.async_request_state_refresh()
        self._thermostat.update_custom_attributes()

    async def async_set_stop_mode(self, stop_mode: str) -> None:
        """Apply a new stop mode; its select owns persistence."""
        stop_mode = normalize_stop_mode(stop_mode)
        if self._stop_mode == stop_mode:
            return
        write_event_log(
            _LOGGER,
            self._thermostat,
            f"Auto start/stop stop mode changed to {stop_mode}",
        )
        self._stop_mode = stop_mode
        if self.is_detected:
            await self._thermostat.async_request_state_refresh()
        self._thermostat.update_custom_attributes()

    def restore_entity_state(self, enabled: bool, stop_mode: str) -> None:
        """Reconcile the manager with a supplied enable state and stop mode."""
        if stop_mode not in self.stop_modes:
            _LOGGER.warning(
                "%s - restored stop mode %s is unsupported; using off", self, stop_mode
            )
            stop_mode = STOP_MODE_OFF
        self._enabled = enabled
        if not enabled:
            self._is_stop_detected = False
        self._stop_mode = normalize_stop_mode(stop_mode)
        self._controls_ready = True
        state = control_state(self._hass, self._thermostat.unique_id)
        state.enabled, state.stop_mode = enabled, self._stop_mode

    async def async_initialize_controls(self, enabled: bool, stop_mode: str) -> None:
        """Apply a complete restored pair before enabling detection."""
        if stop_mode not in self.stop_modes:
            _LOGGER.warning(
                "%s - restored stop mode %s is unsupported; using off", self, stop_mode
            )
            stop_mode = STOP_MODE_OFF
            control_state(self._hass, self._thermostat.unique_id).stop_mode = stop_mode
        ready = self._controls_ready
        if not ready:
            self._enabled = False
        await self.async_set_stop_mode(stop_mode)
        self._controls_ready = True
        if not ready or self._enabled != enabled:
            await self.async_set_enabled(enabled)
        self._publish_update()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _dispose(self, reason: str) -> None:
        """Drop the configuration and unregister the manager."""
        if self._configured:
            _LOGGER.info("%s - auto start/stop disabled: %s", self, reason)
        self._configured = False
        self._controls_ready = False
        self._enabled = False
        self._is_stop_detected = False
        managers = self._hass.data.get(DOMAIN, {}).get(DATA_MANAGERS, {})
        if managers.get(self._thermostat.unique_id) is self:
            managers.pop(self._thermostat.unique_id, None)

    def _publish_update(self) -> None:
        """Republish the thermostat attributes and notify the entity listeners."""
        try:
            self._thermostat.update_custom_attributes()
            self._thermostat.async_write_ha_state()
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.warning("%s - could not publish the state: %s", self, exc)
        async_dispatcher_send(
            self._hass,
            f"{SIGNAL_MANAGER_UPDATED}_{self._thermostat.unique_id}",
        )

    def _send_event(self, stopped: bool) -> None:
        """Send the same event the core feature sends on a transition."""
        try:
            self._thermostat.send_event(
                EventType.AUTO_START_STOP_EVENT,
                {
                    "type": "stop" if stopped else "start",
                    "name": self.name,
                    "cause": (
                        "Auto stop conditions reached"
                        if stopped
                        else "Auto start conditions reached"
                    ),
                    "hvac_mode": (
                        self._stop_mode
                        if stopped
                        else str(self._thermostat.requested_hvac_mode)
                    ),
                    "saved_hvac_mode": str(self._thermostat.requested_hvac_mode),
                    "target_temperature": self._thermostat.target_temperature,
                    "current_temperature": self._thermostat.current_temperature,
                    "temperature_slope": round(
                        (self._thermostat.last_temperature_slope or 0.0) / 60, 3
                    ),
                    "accumulated_error": self._algorithm.accumulated_error,
                    "accumulated_error_threshold": (
                        self._algorithm.accumulated_error_threshold
                    ),
                },
            )
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.warning(
                "%s - could not send the auto start/stop event: %s", self, exc
            )

    def __str__(self) -> str:
        return f"AutoStartStopManager-{self._thermostat.name}"
