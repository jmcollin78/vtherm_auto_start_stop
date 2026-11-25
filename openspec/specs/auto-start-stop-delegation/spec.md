# auto-start-stop-delegation Specification

## Purpose

Defines how the thermostat hands its auto-start/stop decision over to an external feature manager, keeps its own implementation inert while the decision is delegated, migrates an installation that already used the core feature, and continues to work unchanged when no external manager is present.

## Requirements

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

### Requirement: Automatic migration when delegated

When the external plugin is loaded and an external `auto_start_stop` manager is attached to a thermostat still flagged as using the core feature, the core SHALL record a migration marker on that thermostat and clear the legacy flag. A thermostat to which no external manager is attached SHALL NOT be migrated.

#### Scenario: A delegated thermostat is migrated

- **WHEN** the plugin is loaded at startup and an external `auto_start_stop` manager is attached to a thermostat whose legacy flag is enabled and which carries no migration marker
- **THEN** the core records the marker and clears the legacy flag

#### Scenario: A thermostat the plugin does not cover keeps its feature

- **WHEN** a thermostat has the legacy flag enabled but no external `auto_start_stop` manager is attached
- **THEN** the core migrates nothing and the core feature keeps working normally

#### Scenario: Plugin removal does not restore the core feature

- **WHEN** the plugin is removed while thermostats carry the migration marker
- **THEN** the core does not re-enable its own feature and the legacy flag stays cleared, leaving the user to re-enable it deliberately

### Requirement: Legacy level left to the plugin

The core SHALL leave the auto-start/stop level untouched in the thermostat entry and SHALL NOT copy it into the plugin configuration, so that the plugin reads it when the user creates its own configuration.

#### Scenario: The migrated thermostat keeps its level

- **WHEN** the core migrates a thermostat whose entry carries an auto-start/stop level
- **THEN** the level is unchanged in the thermostat entry and no plugin configuration is written by the core

### Requirement: Deferred and non-blocking migration

The migration SHALL run only after the system has finished starting, SHALL be idempotent, and SHALL NOT block startup when it fails for one thermostat.

#### Scenario: Migration runs after startup

- **WHEN** the migration step executes
- **THEN** it runs after Home Assistant has finished starting, never during entity setup

#### Scenario: Migration is idempotent

- **WHEN** the migration runs on a thermostat that already carries the marker and has no missing historical identity metadata to recover
- **THEN** the core writes nothing and startup continues normally

#### Scenario: Migration does not block startup

- **WHEN** the migration fails for one thermostat
- **THEN** the failure is reported in the log and the remaining thermostats and the system startup are unaffected

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

### Requirement: Historical entity identities survive delegation

Before removing its auto-start/stop entities, the core SHALL persist their exact entity IDs in the thermostat entry under auto_start_stop_entity_ids. Identity collection and removal SHALL match the core integration, owning entry, domain and feature-specific unique-id suffix. Remembered IDs SHALL remain available for later dedicated plugin configuration.

#### Scenario: Renamed controls keep their historical references

- **WHEN** the core delegates a thermostat with user-renamed auto-start/stop controls
- **THEN** the exact switch and select entity IDs are saved before their registry rows are removed
- **AND** later loads retain those IDs without reconstructing them from a name

#### Scenario: Already-delegated test entries recover retained identities

- **WHEN** a delegated entry lacks historical identity metadata and matching deleted-registry rows are still retained
- **THEN** the core fills the missing IDs from those rows without changing the level or delegation state
- **AND** remembered IDs are not overwritten on later runs

#### Scenario: Unrelated identities remain untouched

- **WHEN** another platform or config entry has a similarly suffixed entity
- **THEN** its identity is neither adopted nor removed by this thermostat's migration
