"""Auto start/stop detection algorithm, ported from the core feature.

The algorithm accumulates the error ``target - current`` over time, weighted by
the elapsed time since the previous measurement, and asks for a stop when the
accumulated error crosses the level's threshold while the projected temperature
already overshoots the target.

Two properties matter for the port:

* **Clock** — the algorithm only reads ``now``, supplied by the caller. The
  caller passes ``thermostat.now``, the shared cycle clock. Two refreshes inside
  one control cycle then observe the same value and the elapsed computation
  collapses to a no-op, so the error is not accumulated twice. Using a local
  wall clock would turn the same two refreshes into a real interval and halve
  the effective detection time.
* **Parameters** — ``resolve_params(level)`` is the single place that maps a
  level to its minimum duration and threshold. Phase 2 adds a ``personnalise``
  mode by adding one branch there, without touching the detection code.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from vtherm_api.log_collector import get_vtherm_logger

from .const import (
    CONF_ERROR_THRESHOLD,
    CONF_DT_MIN,
    DEFAULT_ERROR_THRESHOLD,
    DEFAULT_DT_MIN,
    DEFAULT_LEVEL,
    LEVEL_FAST,
    LEVEL_MEDIUM,
    LEVEL_PERSONNALISE,
    LEVEL_SLOW,
    LEVEL_VERY_SLOW,
)

_LOGGER = get_vtherm_logger(__name__)

#: The control cycle used to normalize the elapsed time. Two measurements taken
#: less than ``MIN_CYCLE_RATIO`` cycles apart are treated as the same cycle.
CYCLE_SEC = 120
MIN_CYCLE_RATIO = 0.2

#: Temperature hysteresis applied to the projected temperature to avoid rapid
#: off/on toggling.
TEMP_HYSTERESIS = 0.5

#: Minimum duration in minutes, per level.
DT_MIN: dict[str, float] = {
    LEVEL_VERY_SLOW: 60,
    LEVEL_SLOW: 30,
    LEVEL_MEDIUM: 15,
    LEVEL_FAST: 7,
}

#: Accumulated error threshold, per level.
ERROR_THRESHOLD: dict[str, float] = {
    LEVEL_VERY_SLOW: 20,
    LEVEL_SLOW: 10,
    LEVEL_MEDIUM: 5,
    LEVEL_FAST: 2,
}


#: Parameters returned for a level. A single shape keeps the detection code
#: independent of how a level is defined.
@dataclass(frozen=True, slots=True)
class LevelParams:
    """The two parameters the detection consumes for a configured level."""

    dt_min: float
    """Minimum duration in minutes before a stop (or a release) is allowed."""

    error_threshold: float
    """Accumulated-error magnitude that triggers a decision."""


#: Relative tolerance applied to the float comparison of a parameter pair, so the
#: ``number`` entities' ``30.0`` still matches a table value of ``30``.
PARAMETER_TOLERANCE = 1e-6


def _derive_level(dt_min: float, error_threshold: float) -> str:
    """Return the named level matching a pair, or ``personnalise``.

    The tables here are injective, so at most one named level matches. Kept in
    this module (rather than importing ``models.derive_level``) to avoid a
    circular import; ``models.derive_level`` is the public entry point and uses
    the same tables and tolerance.
    """
    for level, level_dt_min in DT_MIN.items():
        if (
            abs(float(dt_min) - level_dt_min) <= PARAMETER_TOLERANCE
            and abs(float(error_threshold) - ERROR_THRESHOLD[level])
            <= PARAMETER_TOLERANCE
        ):
            return level
    return LEVEL_PERSONNALISE


def _clamp_custom_key(
    config: dict[str, Any] | None, key: str, fallback: float
) -> float:
    """Read a custom parameter from ``config``, clamped to a sane range.

    Absent, non-numeric or out-of-range values fall back to the SLOW-derived
    default rather than failing the refresh: a bad value must never break the
    control cycle. ``dt_min`` is the minimum duration (minutes); the threshold
    is always a magnitude.
    """
    raw = config.get(key) if config else None
    if raw is None:
        return fallback
    try:
        result = float(raw)
    except (TypeError, ValueError):
        return fallback
    if result != result or result in (float("inf"), float("-inf")):
        return fallback
    return result


def resolve_params(level: str, config: dict[str, Any] | None = None) -> LevelParams:
    """Return the parameters of a level.

    ``personnalise`` reads the per-instance custom values from ``config`` and
    clamps them; a missing or invalid value falls back to the SLOW-derived
    default. An unknown level (a stale or future value) resolves to the default
    parameters rather than failing the refresh: a configuration must never break
    the control cycle of the thermostat.
    """
    if level in DT_MIN:
        return LevelParams(DT_MIN[level], ERROR_THRESHOLD[level])
    if level == LEVEL_PERSONNALISE:
        dt_min = _clamp_custom_key(config, CONF_DT_MIN, DEFAULT_DT_MIN)
        threshold = _clamp_custom_key(
            config, CONF_ERROR_THRESHOLD, DEFAULT_ERROR_THRESHOLD
        )
        return LevelParams(dt_min, threshold)
    _LOGGER.debug(
        "Auto start/stop: unknown level '%s', falling back to the default", level
    )
    return LevelParams(DT_MIN[LEVEL_SLOW], ERROR_THRESHOLD[LEVEL_SLOW])


class AutoStartStopDetectionAlgorithm:
    """Accumulate the error over time and decide whether the thermostat stops."""

    def __init__(self, level: str, vtherm_name: str) -> None:
        self._vtherm_name = vtherm_name
        self._level = DEFAULT_LEVEL
        self._params = resolve_params(DEFAULT_LEVEL)
        self._accumulated_error = 0.0
        self._last_calculation_date: datetime | None = None
        self._last_switch_date: datetime | None = None
        self._last_should_be_off = False
        self.set_params(level, None)

    # -- configuration ------------------------------------------------------

    def set_params(self, level: str, config: dict[str, Any] | None) -> None:
        """Set the level and its parameters without touching the accumulation.

        ``config`` carries the detection parameters; only ``personnalise`` reads
        it (the custom ``dt_min`` and threshold). The accumulated deviation is an
        observed physical measurement, and the parameters are reading criteria
        applied to it: changing a criterion must not discard the measurement, so
        this method never resets ``_accumulated_error`` nor ``_last_switch_date``.
        The accumulation stays bounded to the *new* threshold on the next cycle
        (see :meth:`should_be_turned_off`), which is what makes a faster level
        able to detect on the very next cycle while a slower one cannot.
        """
        self._level = level
        self._params = resolve_params(level, config)

    def set_level(self, level: str) -> None:
        """Set a new level; the accumulation is preserved (see :meth:`set_params`)."""
        self.set_params(level, None)

    def set_parameters(
        self, dt_min: float, error_threshold: float, level: str | None = None
    ) -> None:
        """Set a custom pair directly, preserving the accumulation.

        Used by the parameters path. When ``level`` is omitted, the level is
        derived from the pair with the same injective table the model uses, so
        the algorithm never claims ``personnalise`` for a pair that matches a
        named level. The accumulation is preserved for the same reason as
        :meth:`set_params`.
        """
        self._level = level or _derive_level(dt_min, error_threshold)
        self._params = LevelParams(float(dt_min), float(error_threshold))

    def reset_switch_delay(self) -> None:
        """Allow an immediate start/stop after a deliberate user change.

        Called when the preset or the target temperature changes: the user
        explicitly asked for something else, so neither the switch delay nor the
        "too near" guard may hold the previous decision.
        """
        self._last_switch_date = None
        self._last_calculation_date = None
        self._last_should_be_off = False

    # -- detection ----------------------------------------------------------

    def should_be_turned_off(
        self,
        requested_hvac_mode: object | None,
        target_temp: float | None,
        current_temp: float | None,
        slope_min: float | None,
        now: datetime,
    ) -> bool:
        """Return whether the thermostat should be stopped.

        ``requested_hvac_mode`` is the mode the thermostat asks for, before any
        feature override. ``slope_min`` is the temperature slope in °C per
        minute, used to project the temperature ``dt_min`` ahead.
        """
        mode = None if requested_hvac_mode is None else str(requested_hvac_mode)

        if mode is None or target_temp is None or current_temp is None:
            _LOGGER.debug(
                "%s - mandatory parameters missing, auto start/stop stays idle",
                self,
            )
            self._last_should_be_off = False
            return self._last_should_be_off

        error = target_temp - current_temp

        if self._last_calculation_date is not None:
            dt_cycles = (now - self._last_calculation_date).total_seconds() / (
                CYCLE_SEC
            )
            if dt_cycles <= MIN_CYCLE_RATIO:
                _LOGGER.debug(
                    "%s - measurement too close to the previous one (%s vs %s), "
                    "keeping the last decision",
                    self,
                    now,
                    self._last_calculation_date,
                )
                return self._last_should_be_off
            error *= dt_cycles

        # When the error changes sign, halve the accumulation instead of
        # cancelling it, so a heating then cooling sequence does not restart
        # from zero.
        if error * self._accumulated_error < 0:
            self._accumulated_error /= 2.0

        self._accumulated_error += error
        self._accumulated_error = min(
            self._params.error_threshold,
            max(-self._params.error_threshold, self._accumulated_error),
        )
        self._last_calculation_date = now

        projected_temp = current_temp + (slope_min or 0.0) * self._params.dt_min

        minutes_since_switch = 999
        if self._last_switch_date is not None:
            minutes_since_switch = (now - self._last_switch_date).total_seconds() / 60

        previous_decision = self._last_should_be_off
        dt_min = self._params.dt_min
        threshold = self._params.error_threshold

        if mode == "heat":
            if (
                self._accumulated_error <= -threshold
                and projected_temp >= target_temp + TEMP_HYSTERESIS
                and minutes_since_switch >= dt_min
            ):
                _LOGGER.info(
                    "%s - auto-start/stop: stop, heating is not needed for a "
                    "long time",
                    self,
                )
                self._last_should_be_off = True
            elif (
                projected_temp <= target_temp - TEMP_HYSTERESIS
                and minutes_since_switch >= dt_min
            ):
                _LOGGER.info("%s - auto-start/stop: start heating", self)
                self._last_should_be_off = False
        elif mode == "cool":
            if (
                self._accumulated_error >= threshold
                and projected_temp <= target_temp - TEMP_HYSTERESIS
                and minutes_since_switch >= dt_min
            ):
                _LOGGER.info(
                    "%s - auto-start/stop: stop, cooling is not needed for a "
                    "long time",
                    self,
                )
                self._last_should_be_off = True
            elif (
                projected_temp >= target_temp + TEMP_HYSTERESIS
                and minutes_since_switch >= dt_min
            ):
                _LOGGER.info("%s - auto-start/stop: start cooling", self)
                self._last_should_be_off = False

        if previous_decision != self._last_should_be_off:
            self._last_switch_date = now

        return self._last_should_be_off

    # -- published state ----------------------------------------------------

    @property
    def level(self) -> str:
        """Return the configured level."""
        return self._level

    @property
    def dt_min(self) -> float:
        """Return the minimum duration of the configured level, in minutes."""
        return self._params.dt_min

    @property
    def accumulated_error(self) -> float:
        """Return the accumulated error."""
        return self._accumulated_error

    @property
    def accumulated_error_threshold(self) -> float:
        """Return the accumulated-error threshold of the configured level."""
        return self._params.error_threshold

    @property
    def last_switch_date(self) -> datetime | None:
        """Return the date of the last decision change."""
        return self._last_switch_date

    # -- restore ------------------------------------------------------------

    def restore(
        self,
        accumulated_error: float | None,
        last_switch_date: datetime | None,
    ) -> None:
        """Restore the algorithm state after a Home Assistant restart."""
        if accumulated_error is not None:
            self._accumulated_error = float(accumulated_error)
        self._last_switch_date = last_switch_date

    def __str__(self) -> str:
        return f"AutoStartStopAlgorithm-{self._vtherm_name}"
