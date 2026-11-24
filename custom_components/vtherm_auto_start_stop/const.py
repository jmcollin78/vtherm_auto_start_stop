"""Constants for the VTherm auto start/stop plugin.

The plugin mirrors the core vocabulary instead of importing the core, so it
stays decoupled from ``versatile_thermostat`` internals. Every literal below is
part of the public contract with the core:

* the stable feature-manager name the delegation resolves;
* the level values stored by the core configuration and carried over by the
  migration;
* the stop-mode values the arbitration compares against the accepted HVAC
  modes;
* the attribute keys the existing card and the LLM attribute index read.
"""

from __future__ import annotations

from typing import Literal

# ---------------------------------------------------------------------------
# Integration identity
# ---------------------------------------------------------------------------

DOMAIN = "vtherm_auto_start_stop"

VT_DOMAIN = "versatile_thermostat"

#: Stable name under which the plugin registers its feature manager. The core
#: resolves this name through ``auto_start_stop_manager`` so the arbitration
#: follows the actual decision owner.
MANAGER_NAME = "auto_start_stop"

#: Top-level attribute section published on the thermostat state. Reproduced
#: verbatim so the existing card keeps rendering it.
MANAGER_ATTRIBUTES_KEY = "auto_start_stop_manager"

#: Boolean sibling attribute telling whether the feature is configured. The core
#: publishes it next to the section and cards read it.
ATTR_IS_CONFIGURED = "is_auto_start_stop_configured"

# ---------------------------------------------------------------------------
# Config entry keys
# ---------------------------------------------------------------------------

#: Unique id of the targeted thermostat on a dedicated entry.
CONF_VTHERM_UNIQUE_ID = "vtherm_unique_id"

#: Configured auto-start/stop level.
CONF_LEVEL = "auto_start_stop_level"

#: HVAC mode applied when a stop is detected.
CONF_STOP_MODE = "auto_start_stop_stop_mode"

#: Persisted enable state of a global or dedicated instance.
CONF_ENABLED = "enabled"

#: Thermodtat selection key used by the config flow.
CONF_TARGET_ENTITY = "target_entity"

# ---------------------------------------------------------------------------
# Level vocabulary (verbatim core values)
# ---------------------------------------------------------------------------

LEVEL_NONE = "auto_start_stop_none"
LEVEL_VERY_SLOW = "auto_start_stop_very_slow"
LEVEL_SLOW = "auto_start_stop_slow"
LEVEL_MEDIUM = "auto_start_stop_medium"
LEVEL_FAST = "auto_start_stop_fast"

LEVELS = [LEVEL_NONE, LEVEL_VERY_SLOW, LEVEL_SLOW, LEVEL_MEDIUM, LEVEL_FAST]

TYPE_LEVEL = Literal[
    "auto_start_stop_none",
    "auto_start_stop_very_slow",
    "auto_start_stop_slow",
    "auto_start_stop_medium",
    "auto_start_stop_fast",
]

DEFAULT_LEVEL = LEVEL_SLOW

# ---------------------------------------------------------------------------
# Stop modes (verbatim core values)
# ---------------------------------------------------------------------------

STOP_MODE_OFF = "off"
STOP_MODE_FAN_ONLY = "fan_only"
STOP_MODE_DRY = "dry"

STOP_MODES = [STOP_MODE_OFF, STOP_MODE_FAN_ONLY, STOP_MODE_DRY]

DEFAULT_STOP_MODE = STOP_MODE_OFF

#: A newly created instance is enabled: the user asked for the feature by
#: creating the entry, so it must not silently stay idle.
DEFAULT_ENABLED = True

# ---------------------------------------------------------------------------
# Legacy core configuration (read by the migration, never written)
# ---------------------------------------------------------------------------

LEGACY_LEVEL = "auto_start_stop_level"
LEGACY_THERMOSTAT_TYPE = "thermostat_type"
LEGACY_REGULATION_MODE = "auto_regulation_mode"
LEGACY_REGULATION_VALVE = "auto_regulation_valve"

#: Value of ``thermostat_type`` for an ``over_climate`` thermostat.
THERMOSTAT_TYPE_CLIMATE = "thermostat_over_climate"

#: Off reason set by the core arbitration when the plugin asks for a stop.
HVAC_OFF_REASON_AUTO_START_STOP = "hvac_off_auto_start_stop"

# ---------------------------------------------------------------------------
# Attributes published inside the section (verbatim core keys)
# ---------------------------------------------------------------------------

ATTR_ENABLE = "auto_start_stop_enable"
ATTR_LEVEL = "auto_start_stop_level"
ATTR_DTMIN = "auto_start_stop_dtmin"
ATTR_ACCUMULATED_ERROR = "auto_start_stop_accumulated_error"
ATTR_ACCUMULATED_ERROR_THRESHOLD = "auto_start_stop_accumulated_error_threshold"
ATTR_LAST_SWITCH_DATE = "auto_start_stop_last_switch_date"
ATTR_IS_STOP_DETECTED = "is_auto_stop_detected"
ATTR_STOP_MODE = "auto_start_stop_stop_mode"

# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------

PLATFORMS = ["switch", "select"]

#: Platform sub-keys used inside the add-entities registry.
PLATFORM_SWITCH = "switch"
PLATFORM_SELECT = "select"

#: Entity unique-id suffix (appended to the thermostat unique id).
ENTITY_ENABLE_SUFFIX = "auto_start_stop_enable"
ENTITY_STOP_MODE_SUFFIX = "auto_start_stop_stop_mode"

# ---------------------------------------------------------------------------
# Internal data keys (``hass.data[DOMAIN]``)
# ---------------------------------------------------------------------------

DATA_ENTRIES = "entries"
DATA_FACTORY_REGISTERED = "factory_registered"
DATA_MANAGERS = "managers"
DATA_ADD_ENTITIES = "add_entities"
DATA_CREATED = "created"

#: Dispatcher signal sent when a manager is registered, refreshed with a changed
#: decision, or reconfigured through one of its entities.
SIGNAL_MANAGER_UPDATED = f"{DOMAIN}_manager_updated"
