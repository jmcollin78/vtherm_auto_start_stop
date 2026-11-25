# Spec Delta

## Purpose

Defines the auto-start/stop plugin: how its configuration is layered from a global default down to a per-thermostat instance, which thermostats it may attach to, and how the attached manager detects a prolonged deviation and asks the thermostat to stop.

## ADDED Requirements

### Requirement: Layered configuration resolution

The plugin SHALL resolve detection parameters from plugin defaults, then the global instance if present, then dedicated parameter overrides if present. Individual enable and stop-mode states SHALL belong to the thermostat's entities, not require a dedicated configuration, and remain independent of parameter inheritance.

#### Scenario: Only defaults exist

- **WHEN** no global and no dedicated instance exist for a thermostat
- **THEN** the plugin has no configuration for it and attaches nothing

#### Scenario: Global instance applies

- **WHEN** a global instance exists and an eligible thermostat has no dedicated instance
- **THEN** the thermostat uses the global detection parameters over the plugin defaults and receives its two controls

#### Scenario: Dedicated instance wins

- **WHEN** a thermostat has a dedicated instance and a global instance exists
- **THEN** dedicated detection parameters override global parameters for the fields they define
- **AND** neither entity's enable or stop-mode state is overwritten

#### Scenario: Dedicated instance works without a global instance

- **WHEN** an eligible thermostat has a dedicated instance and no global instance exists
- **THEN** the thermostat uses its dedicated detection parameters over the plugin defaults and receives its two controls

#### Scenario: Removing a dedicated instance restores the global configuration

- **WHEN** a dedicated instance is removed and a global instance exists
- **THEN** the thermostat uses the global detection parameters on the next load
- **AND** its two controls retain their identities, enable state and stop mode

#### Scenario: Removing the global instance leaves no implicit configuration

- **WHEN** the global instance is removed and an eligible thermostat has no dedicated instance
- **THEN** the plugin attaches no manager and exposes no plugin controls for that thermostat on the next load

### Requirement: Thermostat eligibility

The plugin SHALL only attach to a thermostat that is `over_climate` **and** not regulated by a valve, which is exactly the eligibility of the core feature. Ineligibility SHALL be detected both when the configuration is entered, with an explicit error naming the reason, and again when managers are resolved on every load.

#### Scenario: A non over_climate thermostat is refused

- **WHEN** a user tries to configure a dedicated instance for a thermostat that is not `over_climate`
- **THEN** the configuration is refused with an error naming the thermostat type

#### Scenario: A central configuration thermostat is refused

- **WHEN** a user tries to configure a dedicated instance for a Versatile Thermostat central configuration entry
- **THEN** the configuration is refused because it is not an `over_climate` thermostat

#### Scenario: A valve-regulated over_climate thermostat is refused

- **WHEN** a user tries to configure a dedicated instance for an `over_climate` thermostat whose regulation is done by a valve
- **THEN** the configuration is refused with an error naming the valve regulation, matching the eligibility of the core feature

#### Scenario: A thermostat reclassified later is not attached

- **WHEN** a thermostat that had a dedicated instance is reconfigured into an ineligible state, either a different type or a valve regulation
- **THEN** the plugin attaches no manager to it on the next load and the installation keeps working

#### Scenario: An eligible thermostat gets a manager

- **WHEN** a thermostat is `over_climate`, is not valve-regulated, and has an effective configuration
- **THEN** the plugin attaches one manager to it

#### Scenario: Global defaults never include valve-regulated thermostats

- **WHEN** a global instance exists and an `over_climate` thermostat is valve-regulated
- **THEN** the plugin attaches no manager to that thermostat, regardless of the global enable state

### Requirement: Persistent per-thermostat control states

Each thermostat's enable switch and stop-mode select SHALL persist their own states across reloads and restarts. Their commands SHALL affect that thermostat only, without modifying global defaults or creating or requiring a dedicated entry. A disabled thermostat SHALL retain its manager, attributes and both controls, without accumulating error or requesting an automatic stop.

#### Scenario: Chambre is enabled without a dedicated configuration

- **WHEN** only the global configuration exists and the user turns Chambre's enable switch on
- **THEN** only Chambre is enabled and the choice survives restart
- **AND** no dedicated configuration entry is created and other thermostats' states are unchanged

#### Scenario: A thermostat is disabled independently

- **WHEN** the user turns one thermostat's enable switch off
- **THEN** only that thermostat is disabled and the choice survives restart
- **AND** global defaults and other thermostats' states are unchanged

#### Scenario: A mode is memorized without a dedicated configuration

- **WHEN** only the global configuration exists and the user selects a supported stop mode for one thermostat
- **THEN** only that select's mode changes and the choice survives restart
- **AND** no configuration entry is created and no enable state is changed

#### Scenario: A disabled thermostat retains its controls

- **WHEN** a covered thermostat's enable switch is off, with or without a dedicated parameter entry
- **THEN** its manager, auto-start/stop attribute section, enable switch and stop-mode select remain present
- **AND** the switch is off and the select displays the retained stop mode
- **AND** its configured flag is true, its enable state is false, and detection does not accumulate error or request an automatic stop

#### Scenario: Disabling releases a detected stop

- **WHEN** the effective enable state becomes false while an automatic stop is detected
- **THEN** the detection flag becomes false and the auto-start/stop stop request is released
- **AND** the thermostat resumes its requested operation subject to its other controls

### Requirement: Enable and stop-mode defaults initialize entities only

The global enable and stop-mode defaults SHALL initialize entities without saved state. Later changes to those defaults SHALL NOT overwrite existing entity states. Detection-parameter changes SHALL still apply to thermostats inheriting those parameters. Dedicated entries SHALL NOT be necessary for preserving individual control states.

#### Scenario: New controls use current initialization defaults

- **WHEN** an eligible thermostat has no saved control states and is first covered by the global configuration
- **THEN** its switch and select start with the current initialization defaults, restricted to supported stop modes

#### Scenario: Changed defaults do not reset existing controls

- **WHEN** existing switches and selects have saved states and the global enable or stop-mode defaults are changed
- **THEN** existing entity states are retained, including after reload and restart
- **AND** eligible thermostats added later without saved states use the new defaults

#### Scenario: Detection parameters still apply globally

- **WHEN** a global detection parameter changes and a thermostat has no dedicated override for that parameter
- **THEN** the thermostat uses the new detection parameter without resetting its switch or select

### Requirement: Direct dedicated configuration flow

When no plugin entry exists, the config flow SHALL create global detection parameters and explicitly labelled initial control defaults. Further entries SHALL open the thermostat selector directly for optional dedicated detection parameters. Individual enable/mode actions SHALL NOT enter this flow. No exclusion entry type or configure-or-exclude menu SHALL be available.

#### Scenario: The first entry configures global defaults

- **WHEN** a user adds the integration and no plugin entry exists
- **THEN** the flow opens the global settings, including enable and stop-mode defaults clearly labelled as initialization-only

#### Scenario: Adding a dedicated instance opens the thermostat selector directly

- **WHEN** a user adds another plugin entry
- **THEN** the flow opens the thermostat selector without an intent menu or exclusion choice
- **AND** after an eligible thermostat is selected, the flow opens its dedicated detection-parameter settings

#### Scenario: Control state is not a dedicated configuration setting

- **WHEN** a user wants to change an individual thermostat's enable state or stop mode
- **THEN** its existing switch or select is sufficient and no configuration creation or editing is required

#### Scenario: Custom thresholds and durations are not introduced prematurely

- **WHEN** a user configures this phase-1 implementation
- **THEN** explicit custom thresholds and durations are not offered
- **AND** a later specification may add them as dedicated detection-parameter overrides without changing the two-control interface

### Requirement: Detection and stop request

The attached manager SHALL accumulate the deviation between the current temperature and the target over time, and SHALL request that the thermostat stop when the deviation stays beyond the configured threshold for longer than the configured minimum duration.

#### Scenario: A sustained deviation triggers a stop

- **WHEN** the deviation stays beyond the threshold for longer than the minimum duration while the thermostat is heating
- **THEN** the manager flags the stop and the thermostat applies the configured stop mode

#### Scenario: A short deviation does not trigger a stop

- **WHEN** the deviation exceeds the threshold for less than the minimum duration
- **THEN** the manager does not flag a stop and the thermostat keeps its mode

#### Scenario: The deviation returns within tolerance

- **WHEN** the deviation comes back within tolerance before the minimum duration elapses
- **THEN** the accumulated deviation is cleared and no stop is requested

#### Scenario: The stop is reversed on its own

- **WHEN** the thermostat has been stopped by the plugin and the deviation comes back within tolerance for long enough
- **THEN** the manager releases the stop and the thermostat resumes its requested mode

### Requirement: Elapsed time from the thermostat clock

The manager SHALL measure elapsed time using the thermostat clock, so that two refreshes within the same control cycle count as simultaneous and cannot double the accumulated deviation.

#### Scenario: Two refreshes in one cycle accumulate once

- **WHEN** the manager is refreshed twice during one control cycle
- **THEN** the accumulated deviation grows as if it had been refreshed once

#### Scenario: A normal cycle accumulates normally

- **WHEN** the manager is refreshed after a full control cycle
- **THEN** the accumulated deviation grows by the elapsed time since the previous refresh

### Requirement: Immediate effect of the decision

When the manager changes its detection state, it SHALL request an immediate state refresh from the thermostat so the new effective mode is applied in the same cycle rather than at the next one.

#### Scenario: A detected stop is applied immediately

- **WHEN** the manager flags a stop during a refresh
- **THEN** it requests an immediate state refresh and the thermostat publishes the stopped mode before the cycle ends

#### Scenario: A released stop is applied immediately

- **WHEN** the manager releases a stop during a refresh
- **THEN** it requests an immediate state refresh and the thermostat republishes its requested mode before the cycle ends

#### Scenario: No change requests nothing

- **WHEN** the manager's detection state is unchanged by a refresh
- **THEN** it does not request a state refresh

### Requirement: Published attributes and off-reason

The plugin SHALL publish the same auto-start/stop attribute section as the core feature and SHALL use the same off-reason vocabulary, so existing cards and summaries keep working.

#### Scenario: The attribute section is present

- **WHEN** a thermostat managed by the plugin exposes its custom attributes
- **THEN** the auto-start/stop section contains the detection flag, the level, the minimum duration, the accumulated deviation, its threshold, the last switch date, the stop mode and the enable state

#### Scenario: The off-reason is unchanged

- **WHEN** the thermostat is stopped by the plugin
- **THEN** its off-reason is the auto-start/stop reason already used by the core feature

### Requirement: Plugin entities

The plugin SHALL create exactly one enable switch and one stop-mode select for each eligible thermostat covered by a global or dedicated configuration. A global configuration alone SHALL suffice for every eligible thermostat, even with its enable default false. The select SHALL offer off and supported fan_only/dry, never disabled or heat/cool/auto. The select's options SHALL reflect the modes the thermostat currently accepts.

#### Scenario: Global configuration alone creates two controls per thermostat

- **WHEN** only the global configuration exists and several non-valve-regulated over_climate thermostats are present
- **THEN** every such thermostat has exactly one enable switch and one stop-mode select
- **AND** no dedicated configuration is required or automatically created

#### Scenario: Disabled initialization defaults do not suppress entities

- **WHEN** only the global configuration exists, its enable default is false and eligible thermostats have no saved states
- **THEN** every eligible thermostat has an off enable switch and a select showing its supported initial stop mode
- **AND** their managers and attributes remain configured

#### Scenario: A dedicated instance has two controls

- **WHEN** an eligible thermostat has its own dedicated parameter instance, with or without a global instance
- **THEN** it has one enable switch and one stop-mode select, never a second pair

#### Scenario: Options only contain compatible stop modes

- **WHEN** a thermostat supports off, heat and fan_only but not dry
- **THEN** the select options are off and fan_only in that order
- **AND** disabled, heat and dry are not offered

#### Scenario: Stop-mode options update once the accepted hvac modes settle

- **WHEN** a manager was registered before the underlying climate of an over_climate attached, so the select initially exposes only the fallback options
- **AND** the underlying later attaches and exposes more accepted hvac modes such as fan_only or dry
- **THEN** the plugin re-publishes the select state so it gains the newly supported stop modes
- **AND** the user does not need to restart or interact with the control to see the updated options

#### Scenario: Controls and stop modes are localized

- **WHEN** the controls are displayed with French or English translations
- **THEN** the switch, select and supported stop-mode labels use the selected language

#### Scenario: An eligible thermostat is added after the global configuration

- **WHEN** another eligible thermostat is added while the global configuration exists
- **THEN** the plugin creates its own switch/select pair without requiring a dedicated configuration

#### Scenario: Ineligible thermostats have no controls

- **WHEN** a thermostat is not over_climate or is valve-regulated
- **THEN** the plugin creates neither control for it, regardless of the global defaults

#### Scenario: No configuration means no controls

- **WHEN** neither a global configuration nor a dedicated parameter configuration covers a thermostat
- **THEN** no plugin manager or plugin control is exposed for it

### Requirement: Independent activation and stop-mode controls

The switch SHALL reflect and control its thermostat's enable state without changing its saved stop mode. The select SHALL reflect and control its stop mode without changing the enable state. Valid persisted entity states SHALL take precedence over initialization defaults after reloads, restarts and parameter edits.

#### Scenario: Turning the switch off releases a stop and preserves the mode

- **WHEN** the user turns the switch off while an automatic stop is detected
- **THEN** the feature is disabled, accumulation stops and the stop request is released
- **AND** the select still displays the last configured stop mode

#### Scenario: Turning the switch on uses the saved mode

- **WHEN** the user turns the switch on
- **THEN** detection is enabled without changing the saved stop mode

#### Scenario: A mode change does not enable a disabled feature

- **WHEN** the user selects a supported stop mode while the switch is off
- **THEN** that mode is saved and the switch remains off

#### Scenario: Off is an automatic stop mode

- **WHEN** the user selects off while the switch is on
- **THEN** the feature remains enabled and subsequent automatic stops request the off HVAC mode

#### Scenario: Unsupported modes are refused

- **WHEN** a user attempts to select a mode not offered for that thermostat
- **THEN** the selection is refused explicitly and neither the enable state nor the saved stop mode changes

#### Scenario: Parameter edits and restart preserve entity states

- **WHEN** detection parameters change or the integration restarts
- **THEN** each switch and select retains its own saved state rather than being reset from configuration defaults

#### Scenario: Restoration does not briefly enable detection with the wrong mode

- **WHEN** the controls and manager are being restored or reattached
- **THEN** the saved stop mode is applied before the saved enable state becomes active
- **AND** detection does not run with an uninitialized or stale control state

### Requirement: Controls survive parameter-configuration changes

Adding or removing a dedicated parameter configuration SHALL NOT duplicate, rename or reset an existing switch/select pair while a global configuration still covers the thermostat. Removing global coverage SHALL retain controls for thermostats still covered by dedicated parameter entries.

#### Scenario: A dedicated parameter entry is added

- **WHEN** a globally covered thermostat already has its two controls and a dedicated parameter entry is added
- **THEN** the same two entities retain their IDs and saved states while the new detection parameters apply

#### Scenario: A dedicated parameter entry is removed

- **WHEN** a dedicated parameter entry is removed while global coverage remains
- **THEN** the same controls retain their IDs and states while detection parameters revert to the global values

#### Scenario: The global configuration is removed

- **WHEN** the global configuration is removed
- **THEN** thermostats with dedicated parameter entries retain their controls and saved states
- **AND** thermostats without remaining coverage expose neither plugin manager nor plugin controls

### Requirement: Historical entity-id compatibility

Historical core switch and select entity IDs SHALL be reused exactly for globally or individually covered thermostats, including custom IDs, when available. Later user renames SHALL be retained. Unrelated entries SHALL NOT be overwritten, and a conflict SHALL produce an explicit error rather than a silently suffixed replacement.

#### Scenario: Existing core references remain valid

- **WHEN** a thermostat used switch.thermostat_chambre_enable_auto_start_stop and select.chambre_thermostat_chambre_auto_start_stop_stop_mode before delegation
- **THEN** its plugin controls reuse those exact entity IDs even when only the global configuration exists
- **AND** existing card settings and automation targets require no edits

#### Scenario: Global-only delegation adopts the remembered identities

- **WHEN** core delegation removes the old controls and only the global configuration exists
- **THEN** their plugin replacements reuse the identities remembered by the core migration without waiting for a dedicated entry

#### Scenario: A user renames a plugin control

- **WHEN** a migrated plugin control is renamed and the entry reloads
- **THEN** the new user-selected entity ID is retained

#### Scenario: A historical identity belongs to an unrelated entity

- **WHEN** an unrelated entity already owns the historical entity ID
- **THEN** setup reports an explicit identity conflict without modifying that entity
- **AND** it does not silently create an entity with a suffixed ID

### Requirement: Unmodified VTherm UI Card compatibility

Compatibility SHALL be implemented in the plugin and coordinated core, without requiring changes to VTherm UI Card source or existing dashboard bindings. Read-only inspection of the card source is permitted. Existing switch/select service calls, options and attribute consumers SHALL continue to work under global-only coverage as well as dedicated parameter configurations.

#### Scenario: Existing card controls a globally covered thermostat

- **WHEN** only the global configuration exists and the unchanged production card targets the historical switch/select IDs
- **THEN** activation, deactivation and mode selection work for that thermostat with no card or dashboard edits
- **AND** individual choices survive restart without creating configuration entries

#### Scenario: Card source is consulted during development

- **WHEN** card behavior is investigated to verify compatibility
- **THEN** its source may be read but neither its code nor existing dashboard bindings are modified to make the plugin work

### Requirement: Upgrade from the combined test-version select

Upgrade SHALL preserve existing control choices, restore any missing enable switch and expose stop-mode-only selects. Prior plugin configuration-backed control choices SHALL migrate once into persistent entity state, without subsequent configuration reapplication. Global-only thermostats SHALL gain their pair without dedicated entries. Repeated setup SHALL preserve identities and avoid duplicates.

#### Scenario: A disabled entry retains its settings

- **WHEN** an existing combined-select entry has enabled=false and stop mode dry
- **THEN** upgrade creates an off enable switch and the select displays dry
- **AND** the entry retains enabled=false and stop mode dry

#### Scenario: Old configuration-backed choices are migrated only once

- **WHEN** an older plugin configuration explicitly saved disabled and dry but obsolete restored UI state disagrees
- **THEN** upgrade initializes the new persistent controls as disabled and dry
- **AND** later switch/select changes survive restart instead of being reset from those legacy fields

#### Scenario: An earlier plugin switch still exists

- **WHEN** an entry still has its switch from the earlier two-control plugin version
- **THEN** upgrade reuses it instead of deleting it or creating a duplicate

#### Scenario: Upgrade is idempotent

- **WHEN** the same global or dedicated configuration is loaded repeatedly
- **THEN** every covered eligible thermostat still has one switch and one select with stable identities

### Requirement: Migration from the core configuration

When the plugin is configured for a thermostat that was using the core feature, the plugin SHALL adopt the core level as its own starting value and push it into the dedicated instance being created.

#### Scenario: The core level is adopted

- **WHEN** a thermostat entry carries a legacy auto-start/stop level and the plugin creates its dedicated instance
- **THEN** the plugin's instance starts at that level instead of the plugin default

#### Scenario: The legacy level is not reused twice

- **WHEN** the plugin instance already exists
- **THEN** a subsequent configuration does not overwrite its level from the legacy value

### Requirement: Phase-2 parameter readiness

The plugin SHALL resolve algorithm parameters through a single resolution step keyed on the configured level, so a future custom mode can supply explicit thresholds without changing detection call sites.

#### Scenario: A known level resolves to its parameters

- **WHEN** the configured level is one of the named levels
- **THEN** the resolution step returns that level's minimum duration and threshold

#### Scenario: An unknown or custom level is handled

- **WHEN** the configured level is not one of the named levels
- **THEN** the resolution step returns the default parameters without failing the refresh
