# Proposal

## Why

An external feature manager can be refreshed on every control cycle, but it cannot ask the thermostat to recompute its state immediately. The core does it for its own managers (`requested_state.force_changed()` + `update_states(force=True)`), and a plugin that must make the thermostat stop or resume cannot reproduce that path. Moving auto-start/stop out of the core therefore needs a public way to request a state refresh, plus the two facts the feature needs to decide whether it applies at all.

## What Changes

- Add `async_request_state_refresh()` to the thermostat runtime contract exposed to plugins: it forces a change and recomputes the thermostat state, so a plugin decision becomes effective without waiting for the next cycle.
- Add two read-only runtime facts: `has_valve_regulation` (a thermostat regulated by a valve cannot host the feature, matching the core eligibility) and `vtherm_hvac_modes` (the HVAC modes the thermostat actually accepts, used to validate a stop mode).
- Document the rule that a manager reading the thermostat clock must use the runtime clock, never a local clock, so two refreshes in one cycle stay deduplicated.
- **BREAKING** for the API only: the version bump (`0.12.0` to `0.13.0`) is mandatory; the core must raise its minimum `vtherm_api` constraint in the same release train.
- No behavior change for existing plugins: the new members are additions to an existing protocol.

## Capabilities

### New Capabilities

- `thermostat-runtime-api`: the contract a plugin uses to observe and drive one thermostat, covering the state-refresh request and the eligibility facts a feature manager needs.

### Modified Capabilities

None. `vtherm_api` has no spec in this repository yet, so the whole contract is captured as one new capability.

## Impact

- `vtherm_api` (`src/vtherm_api/`): `interfaces.py` (two properties, one coroutine), `__init__.py` exports if any, version bump, tests.
- `versatile_thermostat`: implementation of the new members on the thermostat entity; `manifest.json` minimum version raised once the API release is published.
- `vtherm_auto_start_stop`: consumer of the new contract; no code in this change.
- Sequencing: this change must be released before `core-auto-start-stop-delegation` is testable outside a local dev container.
