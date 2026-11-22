# Spec Delta

## Purpose

Defines the contract a plugin-provided feature manager uses to observe one thermostat and to make its own decision effective on it, including the ability to request an immediate state recalculation instead of waiting for the next control cycle.

## ADDED Requirements

### Requirement: Immediate state refresh request

A feature manager SHALL be able to request that the thermostat recompute and publish its state immediately, without waiting for the next control cycle. The request SHALL mark the requested state as changed and SHALL trigger a forced recalculation of the current state, so that any arbitration the thermostat performs between constraints is applied at once.

#### Scenario: A manager decision is applied without waiting for a cycle

- **WHEN** a feature manager requests an immediate state refresh while the thermostat is ready
- **THEN** the thermostat marks its requested state as changed, recomputes its current state, and publishes the result before the request returns

#### Scenario: The refresh request is harmless when nothing changed

- **WHEN** a feature manager requests an immediate state refresh and the recomputed current state is identical to the previous one
- **THEN** the thermostat completes the request without error and its published effective state is unchanged

#### Scenario: A refresh request from an unavailable thermostat does not fail the caller

- **WHEN** a feature manager requests an immediate state refresh on a thermostat that is not ready
- **THEN** the request completes without raising, and the thermostat's published state is left as it was

### Requirement: Valve regulation fact

The runtime contract SHALL expose whether the thermostat is regulated by a valve, so that a manager can decide whether its feature is applicable, without reading thermostat configuration keys.

#### Scenario: A valve-regulated thermostat is identifiable

- **WHEN** a feature manager reads the valve regulation fact of a thermostat whose regulation is done by valve
- **THEN** the fact reports that the thermostat is regulated by a valve

#### Scenario: A thermostat without valve regulation is identifiable

- **WHEN** a feature manager reads the valve regulation fact of a thermostat whose regulation is not done by valve
- **THEN** the fact reports that the thermostat is not regulated by a valve

### Requirement: Accepted HVAC modes fact

The runtime contract SHALL expose the HVAC modes the thermostat actually accepts, so that a manager can offer and validate modes that the thermostat will not silently replace.

#### Scenario: A manager validates a mode against the thermostat

- **WHEN** a feature manager reads the accepted HVAC modes of a thermostat
- **THEN** it receives the modes the thermostat can currently apply, excluding modes the thermostat has disabled for itself

#### Scenario: A mode the thermostat does not accept is detectable

- **WHEN** a feature manager compares a candidate mode against the accepted HVAC modes
- **THEN** it can determine whether the thermostat would apply that mode or substitute another

### Requirement: Single clock source for managers

A feature manager that keeps time-based state SHALL read the thermostat clock rather than a local wall clock, so that two refreshes of the manager within the same control cycle are recognised as simultaneous and cannot double-accumulate its state.

#### Scenario: Two refreshes in the same cycle do not double-count

- **WHEN** a feature manager is refreshed twice during one control cycle and both refreshes read the thermostat clock
- **THEN** the second refresh observes no elapsed time since the first and leaves the time-based state unchanged

#### Scenario: A manager reading a local clock is not protected

- **WHEN** a feature manager reads a local wall clock instead of the thermostat clock
- **THEN** the contract offers no protection against double accumulation, and the manager is responsible for its own deduplication
