# Spec Delta

## Purpose

Defines the auto-start/stop plugin: how its configuration is layered from a global default down to a per-thermostat instance, which thermostats it may attach to, and how the attached manager detects a prolonged deviation and asks the thermostat to stop.

## ADDED Requirements

### Requirement: Layered configuration resolution

The plugin SHALL resolve the effective configuration of a thermostat as defaults, then the global instance if one exists, then the thermostat's dedicated instance if one exists. A layer SHALL only override the values it defines.

#### Scenario: Only defaults exist

- **WHEN** no global and no dedicated instance exist for a thermostat
- **THEN** the plugin has no configuration for it and attaches nothing

#### Scenario: Global instance applies

- **WHEN** a global instance exists and the thermostat has no dedicated instance
- **THEN** the thermostat uses the global instance values over the plugin defaults

#### Scenario: Dedicated instance wins

- **WHEN** a thermostat has a dedicated instance and a global instance exists
- **THEN** the thermostat uses the dedicated instance values for the fields it defines and the global values for the others

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

### Requirement: Per-thermostat exclusion from the global configuration

The plugin SHALL let a thermostat opt out of a global instance without defining any parameter for it. An excluded thermostat SHALL be treated exactly as a thermostat for which the feature was never enabled in the core: no manager is attached, no detection runs, and no attribute section is published.

#### Scenario: A thermostat opted out of the global instance gets nothing

- **WHEN** a thermostat has an exclusion entry and a global instance exists
- **THEN** the plugin attaches no manager to it and detects nothing for it

#### Scenario: Other thermostats are unaffected by an exclusion

- **WHEN** one thermostat has an exclusion entry and other eligible thermostats have none
- **THEN** the other thermostats keep using the global instance normally

#### Scenario: An exclusion is not a level

- **WHEN** a thermostat is excluded
- **THEN** its effective configuration is absent rather than set to a neutral level, so it is indistinguishable from a thermostat the feature was never enabled for

#### Scenario: Removing the exclusion restores the global configuration

- **WHEN** an exclusion entry is removed for a thermostat that is otherwise eligible
- **THEN** the global instance applies to it again on the next load

### Requirement: Behavioural parity with the core opt-out

A thermostat that opts out of the plugin SHALL be indistinguishable at the interface level from a thermostat that never had the core feature enabled.

#### Scenario: No auto-start/stop entity exists for an opted-out thermostat

- **WHEN** a thermostat is excluded
- **THEN** no enable switch and no stop-mode selector are created for it

#### Scenario: No auto-start/stop attribute section is published

- **WHEN** a thermostat is excluded and the thermostat exposes its custom attributes
- **THEN** the `auto_start_stop_manager` section is absent and the configured flag reports false, exactly as when the core feature is disabled

#### Scenario: The arbitration ignores an opted-out thermostat

- **WHEN** the state arbitration evaluates an excluded thermostat
- **THEN** it finds no detected stop, so the thermostat keeps its requested mode and no auto-start/stop off-reason is set

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
