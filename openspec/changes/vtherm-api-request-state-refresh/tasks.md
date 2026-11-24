# Tasks

## 1. Contract

- [x] 1.1 Add `async_request_state_refresh()` to `InterfaceThermostatRuntime` with a docstring stating the not-ready rule, and verify `python -m compileall src/vtherm_api` succeeds
- [x] 1.2 Add `has_valve_regulation` and `vtherm_hvac_modes` properties to `InterfaceThermostatRuntime`, and verify the protocol still passes the existing runtime-checkable tests
- [x] 1.3 Document the clock rule at the top of `interfaces.py`, next to the runtime protocol, and verify the design document and the module docstring agree

## 2. Tests

- [x] 2.1 Add an API test asserting `async_request_state_refresh()` is awaited and routed to the thermostat, using the fake thermostat fixture, and verify the new test passes
- [x] 2.2 Add API tests for `has_valve_regulation` and `vtherm_hvac_modes` covering both values, and verify they pass

## 3. Release

- [x] 3.1 Bump the package version from `0.12.0` to `0.13.0` as a minor release and verify the version is readable from `vtherm_api.__version__`
- [x] 3.2 Verify the full API test suite passes locally with the fake thermostat

## 4. Core implementation (`versatile_thermostat`)

- [x] 4.1 Implement `async_request_state_refresh()` on `BaseThermostat` — mark the requested state as changed, force `update_states`, and log a no-op when the thermostat is not ready — and verify the implementation mirrors the existing inline core path (`requested_state.force_changed()` + `update_states(force=True)`)
- [x] 4.2 Expose `has_valve_regulation` on `BaseThermostat` as a read-only alias of the existing `have_valve_regulation` fact, and verify the alias cannot diverge from the source property
- [x] 4.3 Add core unit tests for the refresh request (ready, unchanged effective state, not ready) and verify they pass
- [x] 4.4 Add core unit tests for the `has_valve_regulation` alias on a valve-regulated and on a non-valve thermostat, and verify they pass

## Workflow follow-up

- Publish the `vtherm_api` release before the core raises its minimum constraint.
- The core implementation can ship in the same release train as the raised `manifest.json` constraint; it does not require a second API release.
- Archive the change after the API release is published and the core change is unblocked.
