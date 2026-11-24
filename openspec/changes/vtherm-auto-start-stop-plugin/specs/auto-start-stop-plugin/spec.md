# Spec Delta

## Purpose

Defines the auto-start/stop plugin: how its configuration is layered from a global default down to a per-thermostat instance, which thermostats it may attach to, and how the attached manager detects a prolonged deviation and asks the thermostat to stop.

## ADDED Requirements

### Requirement: Layered configuration resolution

The plugin SHALL apply the global configuration to every eligible thermostat without a dedicated override. Resolution SHALL use plugin defaults, then the global instance if present, then the dedicated instance if present. A layer SHALL only override the values it defines, including an explicit false enable state.

#### Scenario: Only defaults exist

- **WHEN** no global and no dedicated instance exist for a thermostat
- **THEN** the plugin has no configuration for it and attaches nothing

#### Scenario: Global instance applies

- **WHEN** a global instance exists and an eligible thermostat has no dedicated instance
- **THEN** the thermostat uses the global instance values over the plugin defaults

#### Scenario: Dedicated instance wins

- **WHEN** a thermostat has a dedicated instance and a global instance exists
- **THEN** the thermostat uses the dedicated instance values for the fields it defines and the global values for the others

#### Scenario: Dedicated instance works without a global instance

- **WHEN** an eligible thermostat has a dedicated instance and no global instance exists
- **THEN** the thermostat uses its dedicated values over the plugin defaults

#### Scenario: Removing a dedicated instance restores the global configuration

- **WHEN** a dedicated instance is removed and a global instance exists
- **THEN** the thermostat uses the global configuration, including its enable state, on the next load

#### Scenario: Removing the global instance leaves no implicit configuration

- **WHEN** the global instance is removed and an eligible thermostat has no dedicated instance
- **THEN** the plugin attaches no manager to that thermostat on the next load

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

### Requirement: Per-thermostat enable override

The plugin SHALL let a dedicated instance override the global enable state in either direction. A disabled effective configuration SHALL retain its manager and attributes, and any dedicated entities SHALL remain available. While disabled, detection SHALL not accumulate error or request an automatic stop.

#### Scenario: A dedicated instance disables a globally enabled feature

- **WHEN** the global instance is enabled and a thermostat's dedicated instance is disabled
- **THEN** auto-start/stop is disabled for that thermostat while other eligible thermostats without a dedicated override remain enabled

#### Scenario: A dedicated instance enables a globally disabled feature

- **WHEN** the global instance is disabled and a thermostat's dedicated instance is enabled
- **THEN** auto-start/stop is enabled for that thermostat while other eligible thermostats without a dedicated override remain disabled

#### Scenario: A globally disabled thermostat remains configured

- **WHEN** the global instance is disabled and an eligible thermostat has no dedicated instance
- **THEN** its manager remains attached, the configured flag is true, and its auto-start/stop attributes report an enable state of false
- **AND** its accumulated error stays unchanged and no automatic stop is requested

#### Scenario: A disabled dedicated instance retains its controls

- **WHEN** a thermostat has a disabled dedicated instance
- **THEN** its manager, auto-start/stop attribute section, enable switch and stop-mode selector remain present
- **AND** its configured flag is true, its enable state is false, and detection does not accumulate error or request an automatic stop

#### Scenario: Disabling releases a detected stop

- **WHEN** the effective enable state becomes false while an automatic stop is detected
- **THEN** the detection flag becomes false and the auto-start/stop stop request is released
- **AND** the thermostat resumes its requested operation subject to its other controls

### Requirement: Direct dedicated configuration flow

When no plugin entry exists, the config flow SHALL create the global defaults. Otherwise, adding an entry SHALL open the thermostat selector directly, followed by dedicated settings. Both global and dedicated settings SHALL expose an enable control. No exclusion entry type or configure-or-exclude menu SHALL be available.

#### Scenario: The first entry configures global defaults

- **WHEN** a user adds the integration and no plugin entry exists
- **THEN** the flow opens the global settings, including the enable control

#### Scenario: Adding a dedicated instance opens the thermostat selector directly

- **WHEN** a user adds another plugin entry
- **THEN** the flow opens the thermostat selector without an intent menu or exclusion choice
- **AND** after an eligible thermostat is selected, the flow opens its dedicated settings, including the enable control

#### Scenario: A dedicated instance can be edited in either direction

- **WHEN** a user changes the enable control in an existing dedicated instance
- **THEN** the saved value overrides the global enable state for that thermostat without requiring another entry type

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

The plugin SHALL create an enable switch and a stop-mode selector only for thermostats that have a dedicated instance.

#### Scenario: A dedicated instance has entities

- **WHEN** a thermostat has its own dedicated instance
- **THEN** the plugin creates an enable switch and a stop-mode selector for it

#### Scenario: A thermostat configured only through the global instance has no entity

- **WHEN** a thermostat is configured only through the global instance
- **THEN** the plugin creates no entity for it

#### Scenario: The enable switch suspends detection

- **WHEN** the enable switch is turned off
- **THEN** the manager stops accumulating and releases any stop it had applied

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
