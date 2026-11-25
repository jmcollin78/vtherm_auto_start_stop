# Tasks

## 1. Integration skeleton

- [x] 1.1 Create the integration package with `manifest.json` declaring the `vtherm_api` dependency and version constraint, and verify the integration loads in a test instance
- [x] 1.2 Define the domain, the manager stable name `auto_start_stop`, the level vocabulary, the stop modes and the attribute keys in `const.py`, and verify each constant is referenced at least once
- [x] 1.3 Register the factory through the API in `__init__.py` and verify a log line confirms the factory is registered on setup

## 2. Configuration model

Reopened tasks separate detection parameters from persistent per-thermostat entity states. One global configuration must suffice for shared parameters; individual control actions never create or require dedicated configurations. No exclusion entries exist, so no exclusion-data migration is planned.

- [x] 2.1 Separate detection-parameter resolution and initialization-only control defaults from live entity states; verify parameter inheritance, missing fields, dedicated parameter coverage without a global entry, and no coverage when neither exists
- [x] 2.2 Keep the single global flow and explicitly label enable/mode fields as defaults for entities without saved states; verify duplicate-global rejection and that later default edits do not reset existing entities but do initialize new ones
- [x] 2.3 Keep direct thermostat selection for optional dedicated detection-parameter entries, not individual enable/mode settings; verify stable thermostat identity, duplicate rejection and that switch/select actions never invoke configuration creation
- [x] 2.4 Add the eligibility check producing explicit errors for a thermostat that is not `over_climate` and for a valve-regulated thermostat, and verify both error messages name their reason
- [x] 2.5 Remove the exclusion flow, schema, flag, helpers, options abort and obsolete module descriptions, fixtures and tests; remove the configure-or-exclude menu and exclusion labels from strings and both translations, and verify obsolete identifiers and user-facing choices are absent without adding a migration or compatibility branch
- [x] 2.6 Verify global-only thermostats initialized as disabled still have managers, configured=true attributes and both controls; verify switching a thermostat off retains them, freezes accumulated error and requests no automatic stop
- [x] 2.7 Verify multiple globally covered thermostats can retain different enable/mode states across restart without adding entries or modifying global defaults; verify later initialization-default edits leave all existing states intact while inherited detection-parameter changes still apply, and valves remain excluded
- [x] 2.8 Verify adding/removing dedicated parameter entries preserves existing control IDs and states while changing parameter inheritance; verify global removal preserves dedicated coverage but removes controls and managers from otherwise uncovered thermostats
- [x] 2.9 Update the README for global-only two-control coverage, persistent individual states, initialization-only defaults, optional parameter configurations, lifecycle behavior and the unchanged valve restriction; verify the examples and unchanged-card service calls against the revised tests

## 3. Algorithm port

- [x] 3.1 Port the detection algorithm reading the thermostat clock only, and verify with a test that two refreshes inside one cycle accumulate once
- [x] 3.2 Implement `resolve_params(level)` returning the minimum duration and the threshold per level, and verify a table-driven test over all named levels plus an unknown level
- [x] 3.3 Verify a full cycle accumulates the elapsed time once with a test driving two refreshes 120 seconds apart

## 4. Manager

- [x] 4.1 Reconcile the manager with entity-owned control states while retaining its stable name and coverage-based support check; verify startup waits for restored mode then enable, parameter edits and manager replacement do not reset states, and no coverage still means no attachment
- [x] 4.2 Re-check eligibility from the runtime facts in `supports()` and verify an ineligible thermostat gets no manager with a log entry naming the reason
- [x] 4.3 Call the immediate refresh only when the detection flag changes, and verify with a test that a cycle without transition issues no refresh request
- [x] 4.4 Verify a detected stop applies the configured stop mode in the same cycle, and verify the reverse on release
- [x] 4.5 Reproduce the auto-start/stop attribute section and the core off-reason, and verify an existing card renders the section and the LLM attribute index lists it

## 5. Entities

The former dedicated-only, configuration-authoritative implementation is superseded. These tasks must implement two persistent controls for every covered eligible thermostat, including global-only coverage. VTherm UI Card and existing dashboard bindings must remain unmodified; source inspection is read-only.

- [x] 5.1 Create exactly one switch/select pair per covered eligible thermostat from the global platforms, including false enable defaults and later thermostat discovery; verify N eligible thermostats yield 2N controls without dedicated entries, while valve-regulated, other-type and uncovered thermostats receive none
- [x] 5.2 Persist enable state in each switch without updating configuration entries or the saved mode; verify local-only actions, restart persistence, frozen accumulation and stop release when off, and saved-mode-before-enable startup
- [x] 5.3 Persist stop mode in each select without updating configuration entries or activation; verify off/supported fan_only/dry filtering, no disabled option, state retention across restart, explicit invalid-service rejection and reported safe reconciliation of invalid restored modes
- [x] 5.4 Adopt exact historical IDs for global-only as well as dedicated coverage, reuse proven-owned plugin rows and migrate adoption metadata per entity; verify production/custom IDs, later renames, former dedicated markers, core cleanup ordering, idempotency and conflicts without suffixes or changes to unrelated owners
- [x] 5.5 Verify production-compatible English/French control names, option values, attributes and unchanged card calls under both coverage shapes; card code and dashboard bindings must remain untouched, and read-only source inspection must not become a required adapter or card change
- [x] 5.6 Implement global/dedicated control ownership handover and coverage cleanup through official Home Assistant APIs; verify parameter-entry additions/removals, global removal with surviving dedicated entries, reloads and eligibility changes preserve valid control identities/states without duplicate or orphaned pairs
- [x] 5.7 Implement native versioned entity restoration and one-time migration of older configuration-backed choices; verify explicit false/dry beats obsolete UI state during migration only, later actions beat legacy fields, partial saved states are retained, and no dedicated entry or global override dictionary is created for control persistence

## 6. Migration from the core configuration

- [x] 6.1 Read the legacy level from the thermostat entry when creating a dedicated instance and seed the instance with it, and verify the seeded value with a test
- [x] 6.2 Verify an existing dedicated instance is not overwritten by the legacy level on a later configuration
- [x] 6.3 Coordinate core delegation to persist exact switch/select IDs under auto_start_stop_entity_ids before cleanup and recover missing metadata for already-delegated test entries from retained deleted-registry rows when available; verify ownership filtering, save-before-removal ordering, idempotency, no overwrite of remembered identities and unchanged core migration behavior

## 7. Integration verification

- [x] 7.1 Verify end-to-end on a delegated-core test instance with only the global configuration: every eligible thermostat has its exact historical switch/select IDs even with false initialization defaults, unchanged cards control thermostats independently and choices survive restart without new entries; then verify legacy-level seeding for optional dedicated parameters, parameter-only inheritance changes, stable controls on dedicated removal, initialization-only default edits and no core-owned duplicates
  - Verified on a production delegated instance on 2026-11-25: global configuration only, historical IDs preserved, stop detection (slow level, preset change reset included) driven by the plugin, no core-owned duplicates. Reported back to `core-auto-start-stop-delegation` task 5.3.
- [x] 7.2 Verify a thermostat reconfigured into an ineligible state loses its manager and active plugin controls on reload while unrelated thermostats keep working
- [x] 7.3 Re-run the plugin suite and affected core regressions after implementing global coverage and entity-owned persistence; verify entry counts, initialization-only defaults, ownership handover, exact IDs, unchanged card interactions, migration and valve exclusions
  - Previous baseline: 217 plugin and 50 core tests passed before this planning revision. Those results do not establish the newly specified global-only entities or entity-state persistence and must be rerun after implementation.
  - Revised implementation verification: 249 plugin tests and 50 affected core tests passed. Both changes pass strict OpenSpec validation; actual-instance verification remains tracked separately in 7.1.

## Workflow follow-up

- Release only after the API and core delegation releases are published.
- Complete the user-oriented README with installation and migration-from-core guidance before releasing; task 2.9 covers the revised global/dedicated configuration model.
- Archive the change after end-to-end validation on a test instance.
