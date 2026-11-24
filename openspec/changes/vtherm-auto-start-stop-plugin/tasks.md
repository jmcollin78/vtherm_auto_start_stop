# Tasks

## 1. Integration skeleton

- [x] 1.1 Create the integration package with `manifest.json` declaring the `vtherm_api` dependency and version constraint, and verify the integration loads in a test instance
- [x] 1.2 Define the domain, the manager stable name `auto_start_stop`, the level vocabulary, the stop modes and the attribute keys in `const.py`, and verify each constant is referenced at least once
- [x] 1.3 Register the factory through the API in `__init__.py` and verify a log line confirms the factory is registered on setup

## 2. Configuration model

Tasks reopened below describe the approved simplification; their earlier exclusion-based implementation is not completion of the revised behavior. No exclusion entries exist in the test installation, so no migration or compatibility implementation is planned.

- [x] 2.1 Simplify `models.py` to global and dedicated entries only, removing the exclusion short-circuit while preserving the defaults-to-global-to-dedicated cascade; verify all four global/dedicated enable-state combinations, missing-field inheritance, a dedicated instance without a global instance, and no effective configuration when neither exists
- [x] 2.2 Implement the config flow with the global branch (`unique_id` = domain), and verify a second global instance is refused
- [x] 2.3 Route every addition after the first entry directly to the thermostat selector and then dedicated settings, without the intent menu; verify the first entry still configures global defaults, both settings forms expose enabled, duplicate dedicated entries are refused, and the dedicated entry stores the thermostat unique id rather than its entity id
- [x] 2.4 Add the eligibility check producing explicit errors for a thermostat that is not `over_climate` and for a valve-regulated thermostat, and verify both error messages name their reason
- [x] 2.5 Remove the exclusion flow, schema, flag, helpers, options abort and obsolete module descriptions, fixtures and tests; remove the configure-or-exclude menu and exclusion labels from strings and both translations, and verify obsolete identifiers and user-facing choices are absent without adding a migration or compatibility branch
- [x] 2.6 Verify disabled global and dedicated configurations remain effective configurations with an attached manager, configured=true and enabled=false attributes, frozen accumulated error, and no automatic stop; replace the former exclusion-detachment assertions with these regression tests
- [x] 2.7 Verify with multiple thermostats that a dedicated disabled configuration overrides global enabled defaults and a dedicated enabled configuration overrides global disabled defaults, that unrelated eligible thermostats keep following global changes, and that valve-regulated thermostats never receive a manager in either global state
- [x] 2.8 Verify deleting a dedicated instance restores the global values on the next load for both global enable states, and deleting the global instance leaves dedicated instances operational over plugin defaults while thermostats without a dedicated instance lose their configuration
- [x] 2.9 Update the user README with the direct configuration flow, the global/dedicated enable-state matrix, return to global values after deletion, disabled-but-configured attributes and the unchanged valve-regulation restriction; verify all examples match the configuration-flow and resolution tests

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

- [x] 5.1 Forward only the select platform, remove the switch implementation and simplify the registry to one callback; verify each eligible dedicated instance owns exactly one select with the existing unique id even when disabled, global-only thermostats own no entity, and delete/recreate does not duplicate or lose the select
- [x] 5.2 Project enabled=false as the disabled select option and implement selecting disabled without changing the saved stop mode; verify accumulated error stays frozen, a detected stop is released, and configuration edits and restart override stale restored entity state
- [x] 5.3 Implement selecting a compatible stop mode as one persisted update setting that mode and enabled=true, applying the runtime mode before enabling detection; verify off enables rather than disables, fan_only/dry are filtered by capabilities, and unsupported choices raise an explicit error without changing configuration or runtime state
- [x] 5.4 Remove each dedicated entry's former plugin enable switch from the entity registry during setup, preserving its configuration and existing select identity; verify disabled entries remain disabled, cleanup is idempotent and entities belonging to another integration or config entry are untouched
- [x] 5.5 Translate the combined select name and all options in strings and English/French resources, and update the README with disabled-versus-off behavior and upgrade guidance for old switch automations; verify localized option keys match the entity options and documented examples match the selection and upgrade tests

## 6. Migration from the core configuration

- [x] 6.1 Read the legacy level from the thermostat entry when creating a dedicated instance and seed the instance with it, and verify the seeded value with a test
- [x] 6.2 Verify an existing dedicated instance is not overwritten by the legacy level on a later configuration

## 7. Integration verification

- [ ] 7.1 Verify end-to-end on a test instance with the delegated core: a thermostat configured before the plugin keeps its level, stops via the plugin, and exposes no core auto-start/stop entity; then verify the direct dedicated flow, global enabled/local disabled and global disabled/local enabled cases, the single select including disabled/off and old-switch removal after upgrade, and return to global values after removing the dedicated entry
  - This is the validation point of `core-auto-start-stop-delegation` task 5.3, which is blocked until this task runs. Report the outcome back there.
  - Automated regressions cover the revised configuration flow, overrides, controls and entry removal. They do not replace this check against the actual delegated core; no deployment or on-instance validation was performed during this apply.
- [x] 7.2 Verify a thermostat reconfigured into an ineligible state loses its manager on reload and the installation keeps running
- [x] 7.3 Re-run the integration test suite after the combined-select change and verify no test fails, including direct-flow, disabled-configuration, atomic selection, entity-upgrade and unchanged eligibility regressions

## Workflow follow-up

- Release only after the API and core delegation releases are published.
- Complete the user-oriented README with installation and migration-from-core guidance before releasing; task 2.9 covers the revised global/dedicated configuration model.
- Archive the change after end-to-end validation on a test instance.
