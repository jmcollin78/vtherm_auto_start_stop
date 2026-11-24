"""Configuration model of the auto start/stop plugin.

One integration, two entry shapes:

* the **global instance** — no ``vtherm_unique_id``, holds the defaults for the
  whole installation;
* a **dedicated instance** — one per thermostat, keyed by its ``unique_id``.

Dedicated entries override detection parameters. Enable and stop-mode defaults
initialize entity states; they are not live operational configuration.

The resolution is implemented once, here, and every consumer reads its result so
the order cannot diverge between the manager and the entities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

from .const import (
    CONF_ENABLED,
    CONF_LEVEL,
    CONF_STOP_MODE,
    CONF_VTHERM_UNIQUE_ID,
    DEFAULT_ENABLED,
    DEFAULT_LEVEL,
    DEFAULT_STOP_MODE,
    LEVELS,
    LEGACY_LEVEL,
    STOP_MODES,
    TYPE_LEVEL,
)

#: Configuration values, distinct from the target entry metadata.
CONFIG_KEYS = (CONF_LEVEL, CONF_STOP_MODE, CONF_ENABLED)
PARAMETER_KEYS = (CONF_LEVEL,)


def entry_config(entry: ConfigEntry) -> dict[str, Any]:
    """Return entry data with options overriding individual fields."""
    return {**entry.data, **entry.options}


def default_config() -> dict[str, Any]:
    """Return the plugin defaults, the first layer of the cascade.

    These values exist on their own but do not constitute an effective
    configuration: without a global or dedicated instance the plugin attaches
    nothing (see :func:`effective_config`).
    """
    return {
        CONF_LEVEL: DEFAULT_LEVEL,
        CONF_STOP_MODE: DEFAULT_STOP_MODE,
        CONF_ENABLED: DEFAULT_ENABLED,
    }


def _layers(
    entries: dict[str, dict[str, Any]], vtherm_unique_id: str
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return the global and dedicated layers, or None for absent entries."""
    global_layer: dict[str, Any] | None = None
    dedicated_layer: dict[str, Any] | None = None

    for entry in entries.values():
        target = entry.get(CONF_VTHERM_UNIQUE_ID)
        if target == vtherm_unique_id:
            if dedicated_layer is None:
                dedicated_layer = {}
            dedicated_layer.update(
                {key: entry[key] for key in PARAMETER_KEYS if key in entry}
            )
        elif not target:
            if global_layer is None:
                global_layer = {}
            global_layer.update(
                {key: entry[key] for key in CONFIG_KEYS if key in entry}
            )

    return global_layer, dedicated_layer


def effective_config(
    entries: dict[str, dict[str, Any]],
    vtherm_unique_id: str,
) -> dict[str, Any] | None:
    """Resolve the effective configuration of one thermostat.

    Order: plugin defaults, global instance, dedicated instance.
    A layer only overrides the values it defines.

    Returns ``None`` only when no global or dedicated instance exists.
    Disabled configurations remain present so the manager keeps its controls.
    """
    global_layer, dedicated_layer = _layers(entries, vtherm_unique_id)

    if global_layer is None and dedicated_layer is None:
        return None

    config = {CONF_LEVEL: DEFAULT_LEVEL}
    if global_layer is not None:
        config.update(
            {key: global_layer[key] for key in PARAMETER_KEYS if key in global_layer}
        )
    if dedicated_layer is not None:
        config.update(dedicated_layer)
    return config


def initial_control_defaults(entries: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Return initialization defaults, never overriding saved entity states."""
    result = {CONF_ENABLED: DEFAULT_ENABLED, CONF_STOP_MODE: DEFAULT_STOP_MODE}
    for values in entries.values():
        if not values.get(CONF_VTHERM_UNIQUE_ID):
            result.update({key: values[key] for key in result if key in values})
    return result


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
    level: phase 2 will add a ``personnalise`` mode, and a stale entry from a
    future version must not break the cycle.
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
