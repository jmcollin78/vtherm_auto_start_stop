# Tasks

## 1. Substitutable access point

- [x] 1.1 Turn the `auto_start_stop_manager` property into a resolution that prefers `get_feature_manager("auto_start_stop")` and falls back to the legacy instance, and verify `state_manager.py` is byte-for-byte unchanged
- [x] 1.2 Add a unit test where a fake external manager is attached under the stable name and the property returns it, and verify the test passes
- [x] 1.3 Add a unit test where no external manager is attached and the property returns the legacy instance, and verify the test passes

## 2. Inert legacy manager

- [x] 2.1 Add an inert mode to the core manager that skips time accumulation, detection update and state publication, and verify `refresh_and_update_if_changed()` leaves `is_auto_stop_detected` and the accumulated error untouched while inert
- [x] 2.2 Enable the inert mode from the thermostat when an external manager with stable name `auto_start_stop` is present, and verify with a log trace that the core manager is refreshed but performs no work
- [x] 2.3 Add a test where the external manager is removed and a reload restores the core manager's normal behavior, and verify the test passes

## 3. Migration

- [x] 3.1 Add the migration marker constant and an eligibility predicate (flag `True` and marker absent), and verify the predicate with a table-driven test over the four flag/marker combinations
- [x] 3.2 Implement the migration write (flag clear plus marker) deferred to `EVENT_HOMEASSISTANT_STARTED`, gated on an attached external manager, leaving the legacy level untouched, and verify with a test that the level is preserved
- [x] 3.3 Add a test that a second migration run on a marked entry writes nothing, and verify the test passes
- [x] 3.4 Add a test where the migration raises for one thermostat and verify the remaining thermostats still migrate and startup completes
- [x] 3.5 Verify `async_remove_entry` leaves the thermostat flag untouched by reading the entry data after a simulated uninstall
- [x] 3.6 Persist exact switch/select entity IDs under auto_start_stop_entity_ids in the same migration write before registry cleanup, sharing its strict ownership predicate; verify user-renamed IDs, save-before-removal ordering and that unrelated platforms or entries are neither adopted nor removed
- [x] 3.7 Recover missing identity metadata for already-delegated test entries from retained deleted-registry rows; verify complete metadata is idempotent, remembered IDs are never overwritten and level/delegation state are unchanged

## 4. Entity lifecycle

- [x] 4.1 Make the switch and selector platforms skip entity creation when the entry carries the migration marker, and verify a migrated thermostat exposes no auto-start/stop entity
- [x] 4.2 Implement the registry cleanup filtered by `config_entry_id` and `unique_id` suffix, and verify a renamed thermostat still has its entities removed
- [x] 4.3 Add a test that the cleanup leaves other thermostats' entities untouched, and verify the test passes
- [x] 4.4 Add a test that the cleanup on a thermostat without the feature removes nothing and logs no error, and verify the test passes

## 5. Dependency and integration

- [x] 5.1 Raise the `vtherm_api` minimum constraint in `manifest.json` to `0.13.0`, and verify the integration loads with the pinned version installed
- [x] 5.2 Run the full integration test suite and verify no existing auto-start/stop test regresses
- [x] 5.3 Verify end-to-end on a test instance: install the plugin, confirm the flag is cleared, the level and historical entity IDs preserved, core-owned entities removed, dedicated plugin controls using the same IDs, and the external manager driving the stop decision
  - Verified on a production delegated instance on 2026-11-25 (see `vtherm-auto-start-stop-plugin` task 7.1): flag cleared, historical entity IDs preserved, core-owned entities removed, dedicated plugin controls active and driving the stop decision

## Workflow follow-up

- Publish the core release only after the `vtherm_api` release is available.
- Do not archive this change while 5.3 is blocked: the end-to-end delegation check is the last gate. It is validated by `vtherm-auto-start-stop-plugin` task 7.1, then reported back here.
- Archive the change after the plugin change has been validated against it.
