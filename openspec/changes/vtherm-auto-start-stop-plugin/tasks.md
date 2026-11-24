# Tasks

## 1. Integration skeleton

- [x] 1.1 Create the integration package with `manifest.json` declaring the `vtherm_api` dependency and version constraint, and verify the integration loads in a test instance
- [x] 1.2 Define the domain, the manager stable name `auto_start_stop`, the level vocabulary, the stop modes and the attribute keys in `const.py`, and verify each constant is referenced at least once
- [x] 1.3 Register the factory through the API in `__init__.py` and verify a log line confirms the factory is registered on setup

## 2. Configuration model

- [x] 2.1 Implement `models.py` with plugin defaults, the global entry shape, the dedicated entry shape, the exclusion short-circuit and the defaults-to-global-to-dedicated cascade, and verify the cascade with a table-driven test over the three layers plus an excluded thermostat
- [x] 2.2 Implement the config flow with the global branch (`unique_id` = domain), and verify a second global instance is refused
- [x] 2.3 Implement the dedicated branch (`unique_id` = domain plus the thermostat unique id) with a thermostat selector filtered on the Versatile Thermostat integration, and verify the entry stores the thermostat unique id
- [x] 2.4 Add the eligibility check producing explicit errors for a thermostat that is not `over_climate` and for a valve-regulated thermostat, and verify both error messages name their reason
- [x] 2.5 Implement the exclusion branch: a dedicated entry with no parameter that resolves to no effective configuration, and verify `factory.supports()` returns false for an excluded thermostat
- [x] 2.6 Verify an excluded thermostat publishes no auto-start/stop attribute section and exposes no entity, matching a thermostat that never had the core feature enabled
- [x] 2.7 Verify other eligible thermostats keep using the global instance while one thermostat is excluded
- [x] 2.8 Verify the exclusion short-circuits ahead of the three configuration layers, and that removing it restores the global instance on the next load

## 3. Algorithm port

- [x] 3.1 Port the detection algorithm reading the thermostat clock only, and verify with a test that two refreshes inside one cycle accumulate once
- [x] 3.2 Implement `resolve_params(level)` returning the minimum duration and the threshold per level, and verify a table-driven test over all named levels plus an unknown level
- [x] 3.3 Verify a full cycle accumulates the elapsed time once with a test driving two refreshes 120 seconds apart

## 4. Manager

- [x] 4.1 Implement the manager with the same stable name, the enable state, the stop mode and the detection flag, and verify `factory.supports()` returns false when there is no effective configuration
- [x] 4.2 Re-check eligibility from the runtime facts in `supports()` and verify an ineligible thermostat gets no manager with a log entry naming the reason
- [x] 4.3 Call the immediate refresh only when the detection flag changes, and verify with a test that a cycle without transition issues no refresh request
- [x] 4.4 Verify a detected stop applies the configured stop mode in the same cycle, and verify the reverse on release
- [x] 4.5 Reproduce the auto-start/stop attribute section and the core off-reason, and verify an existing card renders the section and the LLM attribute index lists it

## 5. Entities

- [x] 5.1 Create the enable switch and the stop-mode selector only for thermostats with a dedicated entry, and verify a thermostat configured only through the global instance owns no entity
- [x] 5.2 Verify the switch turned off stops accumulation and releases an applied stop
- [x] 5.3 Verify the selector changes the applied stop mode on the next detection

## 6. Migration from the core configuration

- [x] 6.1 Read the legacy level from the thermostat entry when creating a dedicated instance and seed the instance with it, and verify the seeded value with a test
- [x] 6.2 Verify an existing dedicated instance is not overwritten by the legacy level on a later configuration

## 7. Integration verification

- [ ] 7.1 Verify end-to-end on a test instance with the delegated core: a thermostat configured before the plugin keeps its level, stops via the plugin, and exposes no core auto-start/stop entity
  - This is the validation point of `core-auto-start-stop-delegation` task 5.3, which is blocked until this task runs. Report the outcome back there.
- [x] 7.2 Verify a thermostat reconfigured into an ineligible state loses its manager on reload and the installation keeps running
- [x] 7.3 Run the integration test suite and verify no test fails

## Workflow follow-up

- Release only after the API and core delegation releases are published.
- Write a user-oriented README (installation, global/dedicated configuration, per-thermostat exclusion, migration from the core) before releasing.
- Archive the change after end-to-end validation on a test instance.
