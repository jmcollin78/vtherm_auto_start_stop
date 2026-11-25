# Spec Delta

## MODIFIED Requirements

### Requirement: Phase-2 parameter readiness

The plugin SHALL resolve algorithm parameters through a single resolution step keyed on the configured level. When the level is `personnalise`, the step SHALL read the explicit minimum duration and error threshold from the effective configuration, falling back to the named level's values when a custom value is absent. An unknown level SHALL resolve to the default parameters without failing the refresh.

#### Scenario: A known level resolves to its parameters

- **WHEN** the configured level is one of the named levels
- **THEN** the resolution step returns that level's minimum duration and threshold
- **AND** when the level is `personnalise` and the effective configuration carries explicit custom values, the step returns those exact values instead of a named level's pair

#### Scenario: An unknown or custom level is handled

- **WHEN** the configured level is not one of the named levels and is not `personnalise`
- **THEN** the resolution step returns the default parameters without failing the refresh

#### Scenario: The personnalise level falls back on absent custom values

- **WHEN** the resolved level is `personnalise` and the effective configuration does not carry one of the two custom values
- **THEN** that value resolves to the named level that preceded the switch to `personnalise`, without failing the refresh

#### Scenario: The personnalise level reads from the effective configuration

- **WHEN** the resolved level is `personnalise` and the layered resolution has merged custom values from a global and a dedicated instance
- **THEN** the resolution step returns the merged minimum duration and error threshold of the effective configuration

### Requirement: Direct dedicated configuration flow

When no plugin entry exists, the config flow SHALL create global detection parameters and explicitly labelled initial control defaults. Further entries SHALL open the thermostat selector directly for optional dedicated detection parameters. Individual enable/mode actions SHALL NOT enter this flow. No exclusion entry type or configure-or-exclude menu SHALL be available. The flow SHALL expose explicit minimum duration and error threshold fields when the level is `personnalise`.

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

- **WHEN** a user configures this phase-1 implementation with a named level
- **THEN** explicit custom thresholds and durations are not required for that named level
- **AND** when the user selects the `personnalise` level, the explicit minimum duration and error threshold fields are presented, pre-filled from the named level the user was selecting before the switch
- **AND** saving these values makes them the detection parameters for that thermostat until the level is switched away

## ADDED Requirements

### Requirement: Personnalise level parameter bounds

The `personnalise` level SHALL accept a minimum duration between 5 and 120 minutes and an error threshold between 1 and 50. Values outside these bounds SHALL be refused or clamped with an explicit validation error.

#### Scenario: Out-of-range values are refused or clamped

- **WHEN** a user submits a minimum duration below 5 minutes or above 120 minutes
- **THEN** the flow rejects the value or clamps it to the valid bounds and displays an explicit validation error
- **AND** the same applies to an error threshold below 1 or above 50

### Requirement: Custom value persistence across level switches

Custom minimum duration and error threshold values SHALL persist in the configuration entry when the user switches away from `personnalise`, so that switching back to `personnalise` later re-presents the previously saved values without re-entering them.

#### Scenario: Leaving personnalise retains the custom values

- **WHEN** a thermostat is configured at `personnalise` with custom minimum duration and error threshold values, and the user switches its level to a named level
- **THEN** the thermostat resolves with the named level's parameters
- **AND** the custom values persist in the configuration entry
- **AND** switching back to `personnalise` later re-presents the persisted values as pre-filled values in the flow

### Requirement: Removal of the none level

The configuration vocabulary SHALL NOT offer a `none` auto-start/stop level, because the feature's enable switch already controls activation. Configuration entries storing the historical `none` value SHALL resolve to the default parameters without any migration of the stored value.

#### Scenario: The none level is not offered

- **WHEN** a user configures or edits a global or dedicated instance
- **THEN** the level selector offers only the named detection levels and `personnalise`, never a `none` level

#### Scenario: An existing none entry resolves to the default parameters

- **WHEN** an existing configuration entry stores the historical `none` level value
- **THEN** the plugin resolves the default parameters for it without failing the refresh
- **AND** the stored value is not rewritten and no entry migration runs
