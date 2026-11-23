# Tasks

## 1. Contract

- [ ] 1.1 Add `async_request_state_refresh()` to `InterfaceThermostatRuntime` with a docstring stating the not-ready rule, and verify `python -m compileall src/vtherm_api` succeeds
- [ ] 1.2 Add `has_valve_regulation` and `vtherm_hvac_modes` properties to `InterfaceThermostatRuntime`, and verify the protocol still passes the existing runtime-checkable tests
- [ ] 1.3 Document the clock rule at the top of `interfaces.py`, next to the runtime protocol, and verify the design document and the module docstring agree

## 2. Tests

- [ ] 2.1 Add an API test asserting `async_request_state_refresh()` is awaited and routed to the thermostat, using the fake thermostat fixture, and verify the new test passes
- [ ] 2.2 Add API tests for `has_valve_regulation` and `vtherm_hvac_modes` covering both values, and verify they pass

## 3. Release

- [ ] 3.1 Bump the package version from `0.12.0` to `0.13.0` as a minor release and verify the version is readable from `vtherm_api.__version__`
- [ ] 3.2 Verify the full API test suite passes locally with the fake thermostat

## Workflow follow-up

- Publish the `vtherm_api` release before the core raises its minimum constraint.
- Archive the change after the API release is published and the core change is unblocked.
