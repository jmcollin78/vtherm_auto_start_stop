"""Configuration model of the auto start/stop plugin.

One integration, two entry shapes:

* the **global instance** — no ``vtherm_unique_id``, holds the defaults for the
  whole installation;
* a **dedicated instance** — one per thermostat, keyed by its ``unique_id``.

A dedicated entry may also be an **exclusion**: it carries no parameter and only
marks the thermostat as opting out of the global instance. An exclusion resolves
to *no effective configuration*, which is what makes an opted-out thermostat
indistinguishable from a thermostat the core feature was never enabled on.

The resolution is implemented once, here, and every consumer reads its result so
the order cannot diverge between the manager and the entities.
"""

from __future__ import annotations

from typing import Any

from .const import (
    CONF_ENABLED,
    CONF_EXCLUDED,
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

#: Keys a configuration entry may carry. Entry metadata (``vtherm_unique_id``,
#: ``excluded``) is deliberately excluded: it belongs to the entry, not to the
#: configuration it holds.
CONFIG_KEYS = (CONF_LEVEL, CONF_STOP_MODE, CONF_ENABLED)


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


def is_exclusion(entry: dict[str, Any]) -> bool:
    """Return whether an entry is an exclusion (no parameter, opt-out only)."""
    return bool(entry.get(CONF_EXCLUDED))


def _layers(
    entries: dict[str, dict[str, Any]], vtherm_unique_id: str
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    """Return the global layer, the dedicated layer and the exclusion flag.

    The dedicated layer is the first entry targeting this thermostat. An
    exclusion is reported separately so the caller can short-circuit before
    merging anything.
    """
    global_layer: dict[str, Any] = {}
    dedicated_layer: dict[str, Any] = {}
    excluded = False

    for entry in entries.values():
        target = entry.get(CONF_VTHERM_UNIQUE_ID)
        if target == vtherm_unique_id:
            if is_exclusion(entry):
                excluded = True
                continue
            dedicated_layer.update(
                {key: entry[key] for key in CONFIG_KEYS if key in entry}
            )
        elif not target:
            global_layer.update(
                {key: entry[key] for key in CONFIG_KEYS if key in entry}
            )

    return global_layer, dedicated_layer, excluded


def effective_config(
    entries: dict[str, dict[str, Any]],
    vtherm_unique_id: str,
) -> dict[str, Any] | None:
    """Resolve the effective configuration of one thermostat.

    Order: exclusion (short-circuit), plugin defaults, global instance,
    dedicated instance. A layer only overrides the values it defines.

    Returns ``None`` when the thermostat has no effective configuration: no
    global instance and no dedicated instance, or an exclusion entry. ``None``
    is the single predicate of ``factory.supports()``.
    """
    global_layer, dedicated_layer, excluded = _layers(entries, vtherm_unique_id)

    if excluded:
        return None
    if not global_layer and not dedicated_layer:
        return None

    config = default_config()
    config.update(global_layer)
    config.update(dedicated_layer)
    return config


def dedicated_entries(
    entries: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Return the dedicated entries keyed by the thermostat they target.

    Exclusion entries are returned too: the entity platforms need to know a
    thermostat owns an entry, and the exclusion case is filtered there.
    """
    result: dict[str, dict[str, Any]] = {}
    for entry in entries.values():
        target = entry.get(CONF_VTHERM_UNIQUE_ID)
        if target:
            result[target] = entry
    return result


def has_dedicated_instance(
    entries: dict[str, dict[str, Any]], vtherm_unique_id: str
) -> bool:
    """Return whether the thermostat owns a configurable dedicated instance.

    An exclusion is not a configurable instance: it owns no entity.
    """
    entry = dedicated_entries(entries).get(vtherm_unique_id)
    return entry is not None and not is_exclusion(entry)


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
