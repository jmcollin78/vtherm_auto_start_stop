# Spec Delta

## Purpose

Defines how the thermostat hands its auto-start/stop decision over to an external feature manager, keeps its own implementation inert while the decision is delegated, migrates an installation that already used the core feature, and continues to work unchanged when no external manager is present.

## ADDED Requirements

### Requirement: Delegated decision owner

The thermostat SHALL resolve the auto-start/stop decision owner dynamically, preferring an external feature manager registered under the stable name `auto_start_stop`, and falling back to the core implementation when no such manager exists. Every consumer of that decision, including the state arbitration, SHALL read through this resolution rather than a fixed reference.

#### Scenario: An external manager owns the decision

- **WHEN** an external feature manager with the stable name `auto_start_stop` is attached to the thermostat
- **THEN** the thermostat's auto-start/stop decision, its stop mode, and its detection flag all come from that external manager

#### Scenario: The core implementation owns the decision

- **WHEN** no external feature manager with the stable name `auto_start_stop` is attached
- **THEN** the thermostat's auto-start/stop decision comes from the core implementation, exactly as before

#### Scenario: The arbitration follows the resolution

- **WHEN** the state arbitration evaluates whether the thermostat must be stopped for auto-start/stop
- **THEN** it reads the resolved owner's detection flag and stop mode, so the effective mode and the published off-reason reflect the actual owner

### Requirement: Inert legacy manager under delegation

When an external manager owns the decision, the core implementation SHALL exist but SHALL perform no time accumulation, no detection, and no state publication, so that two owners never drive one thermostat.

#### Scenario: The legacy manager does not compete

- **WHEN** an external manager is attached and the core manager is refreshed
- **THEN** the core manager leaves its detection flag and its accumulated error untouched and does not request a state change

#### Scenario: The legacy implementation remains available

- **WHEN** the external manager is removed and the thermostat is reloaded
- **THEN** the core manager resumes its normal behavior without any other change

### Requirement: Configuration-driven hand-over

The core SHALL stop creating its auto-start/stop entities for a thermostat whose configuration entry carries the migration marker identifying the external plugin, independently of the legacy configuration flag.

#### Scenario: Migrated thermostat has no core entities

- **WHEN** a thermostat entry carries the migration marker
- **THEN** the core creates neither the enable switch nor the stop-mode selector for auto-start/stop

#### Scenario: Non-migrated thermostat keeps its entities

- **WHEN** a thermostat entry has the legacy configuration flag enabled and carries no migration marker
- **THEN** the core creates the enable switch and the stop-mode selector as before

### Requirement: Automatic migration at plugin registration

When the external plugin registers and a thermostat is still flagged as using the core feature, the core SHALL mark that thermostat as migrated and clear the legacy flag, after the current level has been made available to the plugin. The migration SHALL NOT block startup and SHALL NOT run before the system has finished starting.

#### Scenario: An existing installation is migrated

- **WHEN** the plugin registers while a thermostat has the legacy flag enabled and no migration marker
- **THEN** the core records the marker, makes the thermostat's current level available to the plugin, and then clears the legacy flag

#### Scenario: Migration is idempotent

- **WHEN** the migration runs on a thermostat that already carries the marker
- **THEN** the core writes nothing and startup continues normally

#### Scenario: Migration does not block startup

- **WHEN** the migration fails for one thermostat
- **THEN** the failure is reported in the log and the remaining thermostats and the system startup are unaffected

#### Scenario: Plugin removal does not restore the core feature

- **WHEN** the plugin is removed while thermostats carry the migration marker
- **THEN** the core does not re-enable its own feature and the legacy flag stays cleared, leaving the user to re-enable it deliberately

### Requirement: Orphan entity cleanup

When the core auto-start/stop feature stops being active for a thermostat, the core SHALL remove the registry entries it created for that feature, so that no unavailable or orphaned entity is left behind.

#### Scenario: Entities are removed with the feature

- **WHEN** the core feature becomes inactive for a thermostat that had its auto-start/stop entities created
- **THEN** the enable switch and the stop-mode selector are removed from the entity registry

#### Scenario: Cleanup is scoped to one thermostat

- **WHEN** the cleanup runs for one thermostat
- **THEN** the entities of every other thermostat are left untouched

#### Scenario: Cleanup is harmless when nothing was created

- **WHEN** the cleanup runs for a thermostat that never had the feature enabled
- **THEN** nothing is removed and no error is reported
