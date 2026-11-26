"""Configuration model of the auto start/stop plugin.

One integration, two entry shapes:

* the **global instance** — no ``vtherm_unique_id``, covers every eligible
  thermostat;
* a **dedicated instance** — one per thermostat, keyed by its ``unique_id``.

Coverage is the only thing an entry grants at runtime: the detection parameters
live in the thermostat's own entities (``switch``, ``select``, ``number``). The
entry keeps its values as **seeds**, read once when an entity has no restored
state of its own.

Two pure helpers mirror each other and keep the direction explicit:

* :func:`derive_level` reads the two parameters and returns the preset label
  they match — ``personnalise`` when no named level matches;
* :func:`resolve_params` (in ``algorithm``) turns a preset label back into its
  two parameters. The tables stay in ``algorithm``, the single source of truth.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

from .algorithm import DT_MIN, ERROR_THRESHOLD, resolve_params
from .const import (
    CONF_ENABLED,
    CONF_ERROR_THRESHOLD,
    CONF_LEVEL,
    CONF_DT_MIN,
    CONF_STOP_MODE,
    CONF_VTHERM_UNIQUE_ID,
    DEFAULT_ENABLED,
    DEFAULT_LEVEL,
    DEFAULT_STOP_MODE,
    DEFAULT_DT_MIN,
    DEFAULT_ERROR_THRESHOLD,
    LEVEL_PERSONNALISE,
    LEVELS,
    LEGACY_LEVEL,
    STOP_MODES,
    TYPE_LEVEL,
)

#: Relative tolerance applied to the float comparison of a parameter pair. The
#: ``number`` entities render ``30`` as ``30.0``; the tolerance keeps such a
#: value recognised as the named level's ``30``.
PARAMETER_TOLERANCE = 1e-6

#: All keys an entry may seed into the thermostat's entities.
SEED_KEYS = (
    CONF_LEVEL,
    CONF_DT_MIN,
    CONF_ERROR_THRESHOLD,
    CONF_STOP_MODE,
    CONF_ENABLED,
)

#: The detection level entry key, kept for the dedicated-entry completeness
#: check used by the config flow. Detection parameters live in entities now, so
#: no other parameter key is required.
PARAMETER_KEYS = (CONF_LEVEL,)

#: Preset levels that carry a fixed parameter pair, in the stable order the
#: derivation walks. ``personnalise`` is excluded: it is the fallback, not a
#: pair.
NAMED_LEVELS = tuple(level for level in LEVELS if level != LEVEL_PERSONNALISE)


def entry_config(entry: ConfigEntry) -> dict[str, Any]:
    """Return entry data with options overriding individual fields."""
    return {**entry.data, **entry.options}


def default_config() -> dict[str, Any]:
    """Return the plugin defaults used as seeds when an entry defines nothing."""
    return {
        CONF_LEVEL: DEFAULT_LEVEL,
        CONF_STOP_MODE: DEFAULT_STOP_MODE,
        CONF_ENABLED: DEFAULT_ENABLED,
        CONF_DT_MIN: DEFAULT_DT_MIN,
        CONF_ERROR_THRESHOLD: DEFAULT_ERROR_THRESHOLD,
    }


def _matches(value: Any, expected: float) -> bool:
    """Compare a parameter to a table value with an explicit float tolerance."""
    try:
        return abs(float(value) - expected) <= PARAMETER_TOLERANCE
    except (TypeError, ValueError):
        return False


def derive_level(dt_min: Any, error_threshold: Any) -> TYPE_LEVEL:
    """Return the preset level matching a parameter pair.

    The table is injective, so at most one named level matches. The comparison
    tolerates the float rendering of the ``number`` entities (``30.0`` for
    ``30``). When no named level matches, the pair is ``personnalise``.
    """
    for level in NAMED_LEVELS:
        if _matches(dt_min, DT_MIN[level]) and _matches(
            error_threshold, ERROR_THRESHOLD[level]
        ):
            return level
    return LEVEL_PERSONNALISE


def is_covered(entries: dict[str, dict[str, Any]], vtherm_unique_id: str) -> bool:
    """Return whether a global or dedicated entry covers the thermostat.

    This replaces the coverage gate the layered resolution used to provide: it
    answers only "does an instance exist for this thermostat", never "with which
    parameters".
    """
    return any(
        entry.get(CONF_VTHERM_UNIQUE_ID) in (None, "", vtherm_unique_id)
        for entry in entries.values()
    )


def _seed_layer(
    entries: dict[str, dict[str, Any]], vtherm_unique_id: str | None
) -> dict[str, Any]:
    """Return the entry whose values seed the thermostat's controls.

    A dedicated entry wins; otherwise the global entry seeds. The iteration is
    ordered on the entry ids so the result is deterministic.
    """
    if vtherm_unique_id:
        dedicated = dedicated_entries(entries).get(vtherm_unique_id)
        if dedicated is not None:
            return dedicated
    global_layer: dict[str, Any] = {}
    for entry_id in sorted(entries):
        entry = entries[entry_id]
        if entry.get(CONF_VTHERM_UNIQUE_ID):
            continue
        for key in SEED_KEYS:
            if key in entry:
                global_layer.setdefault(key, entry[key])
    return global_layer


def _seed_parameters(values: dict[str, Any]) -> tuple[TYPE_LEVEL, float, float]:
    """Return a coherent ``(level, dt_min, error_threshold)`` triple.

    A named level seeds its table pair, so a stale custom key never contradicts
    the chosen preset. A custom (or absent) level seeds the stored custom pair,
    falling back to the defaults, and its label is the derived one.
    """
    level = values.get(CONF_LEVEL)
    if level in DT_MIN:
        params = resolve_params(level)
        return level, params.dt_min, params.error_threshold

    dt_min = _as_float(values.get(CONF_DT_MIN), DEFAULT_DT_MIN)
    threshold = _as_float(values.get(CONF_ERROR_THRESHOLD), DEFAULT_ERROR_THRESHOLD)
    return derive_level(dt_min, threshold), dt_min, threshold


def _as_float(value: Any, fallback: float) -> float:
    """Return a finite float, or the fallback for an unusable value."""
    try:
        result = float(value)
    except (TypeError, ValueError):
        return float(fallback)
    if result != result or result in (float("inf"), float("-inf")):
        return float(fallback)
    return result


def initial_control_defaults(
    entries: dict[str, dict[str, Any]], vtherm_unique_id: str | None = None
) -> dict[str, Any]:
    """Return the seed of each control, never overriding a saved entity state."""
    values = {**default_config(), **_seed_layer(entries, vtherm_unique_id)}
    level, dt_min, threshold = _seed_parameters(values)
    values[CONF_LEVEL] = level
    values[CONF_DT_MIN] = dt_min
    values[CONF_ERROR_THRESHOLD] = threshold
    return values


def dedicated_entries(
    entries: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Return the dedicated entries keyed by the thermostat they target."""
    result: dict[str, dict[str, Any]] = {}
    for entry in entries.values():
        target = entry.get(CONF_VTHERM_UNIQUE_ID)
        if target:
            result[target] = entry
    return result


def has_dedicated_instance(
    entries: dict[str, dict[str, Any]], vtherm_unique_id: str
) -> bool:
    """Return whether the thermostat owns a dedicated instance."""
    return vtherm_unique_id in dedicated_entries(entries)


def normalize_level(level: Any) -> TYPE_LEVEL:
    """Return a known level, falling back to the default on an unknown value.

    The refresh must never fail on a configuration carrying an unexpected
    level: a stale entry from a future version must not break the cycle.
    """
    return level if level in LEVELS else DEFAULT_LEVEL


def normalize_stop_mode(stop_mode: Any) -> str:
    """Return a known stop mode, falling back to ``off``."""
    return stop_mode if stop_mode in STOP_MODES else DEFAULT_STOP_MODE


def legacy_level(entry_infos: dict[str, Any] | None) -> str | None:
    """Return the level carried by a thermostat entry, if any.

    The core config flow keeps the configured level in the entry even after the
    delegation cleared the feature flag (it only resets the level on a save
    through its own flow). The plugin reads it when it creates a dedicated
    instance, so a migrated installation starts at the level the user had
    chosen rather than at the plugin default.
    """
    if not entry_infos:
        return None
    level = entry_infos.get(LEGACY_LEVEL)
    return level if level in LEVELS else None
