# Design

## Context

The core auto-start/stop feature is wired into the thermostat at four places:

| Anchor             | Location                                           | Role today                                               |
| ------------------ | -------------------------------------------------- | -------------------------------------------------------- |
| Manager creation   | `thermostat_climate.py:98-102`                     | instantiates the core manager                            |
| Access point       | `base_thermostat.py:1295-1297`                     | property read by the state manager                       |
| State arbitration  | `state_manager.py:151-157`                         | reads `is_auto_stop_detected` + `stop_mode`              |
| Entities           | `switch.py:35-43,49-92`, `select.py:61-64,140-229` | created when the config flag is true                     |
| External refresh   | `base_thermostat.py:2017-2028`                     | loops over external managers, ignores their return value |
| Attributes         | `base_thermostat.py:2342-2348`                     | defensive merge of manager custom attributes             |
| Switch-delay reset | `base_thermostat.py:1920-1930`                     | calls the manager to reset its delay                     |

`state_manager.py` is the strict constraint: it must not be touched, and it reaches the decision through a single attribute read. This is what makes delegation possible with one substitution point.

Two additional facts shape the design:

- The core already gives an external manager precedence over a legacy one with the same stable name, and there is an existing comment stating that intent at `base_thermostat.py:2051`. The delegation follows that precedent instead of inventing a new mechanism.
- A thermostat is refreshed twice per cycle: once by the climate-specific control path (`thermostat_climate.py:1249`) and once by the generic external-manager loop (`base_thermostat.py:2017`). The auto-start/stop algorithm guards against double accumulation with a `dtmin <= 0.2` check based on the runtime clock, so the guard only holds if the manager reads the runtime clock.

## Goals / Non-Goals

**Goals**

- One substituted access point, zero change in the arbitration.
- No duplicate entities on an installation that already used the core feature.
- No startup failure and no manual step when the plugin is installed.
- The legacy path stays fully functional when the plugin is absent.

**Non-Goals**

- Removing the core implementation. Deletion is a later change, once the plugin has proven itself.
- Restoring the core feature automatically when the plugin is uninstalled.
- Changing the algorithm, the levels or the stop modes.

## Decisions

### D1 — Substitution at the property, not in the state manager

`auto_start_stop_manager` becomes a resolution: return the external manager registered under the stable name `auto_start_stop` if there is one, otherwise the legacy instance. The state manager is untouched.

Rationale: the state manager reads exactly one attribute (`is_auto_stop_detected`) plus `stop_mode`; both are part of the manager contract. Substituting the object is a one-line change with a blast radius of one file. Alternative (adding a delegation check inside the state manager) would put plugin knowledge in the arbitration and need a second change when the arbitration evolves.

Rejected alternative: a generic HVAC-mode override API with priorities. It duplicates the arbitration, re-opens the priority question for every future plugin, and the auto-start/stop reason vocabulary would have to be rebuilt on the plugin side.

### D2 — Inert legacy manager, mirroring the existing precedence comment

When the property resolves to an external manager, the legacy manager is still instantiated (so the attribute exists and any residual reader keeps working) but its refresh becomes a no-op: no time accumulation, no detection update, no forced state publication.

Rationale: this reproduces exactly the intent already expressed for other features — keep the legacy manager until existing entries have migrated, but let an external manager with the same stable name take precedence. Making the legacy manager inert rather than absent also avoids `None` handling in the residual readers (`reset_switch_delay`, the defensive attribute merge, the LLM allow-list).

Trade-off: an inert object is slightly less obvious than a removed one. Accepted, because it is temporary and commented.

### D3 — Migration is a two-step write, ordered

1. Copy the current level into the plugin's entry (the plugin reads it as its legacy seed).
2. Write `use_auto_start_stop_feature = False` **and** the marker in the thermostat entry, in one `async_update_entry`.

Order matters: the thermostat configuration flow resets the level to `none` whenever the flag is false (`config_flow.py:1322`). Copying first guarantees the value survives.

The write happens only when the flag is `True` and the marker is absent, so the operation is idempotent. It is deferred until `EVENT_HOMEASSISTANT_STARTED`, so a failure cannot slow or block the initial startup.

### D4 — Marker on the thermostat entry, not on the plugin entry

`auto_start_stop_migrated_by = "vtherm_auto_start_stop"` lives in the thermostat entry data.

Rationale: the decision "do not create my entities" is taken by the thermostat platform while building entities, from its own entry data. Reading the plugin entry from there would add a cross-integration lookup on the entity-creation path. A marker in the thermostat entry is local, readable synchronously, and survives a plugin uninstall, which is what makes D6 possible.

### D5 — Explicit registry removal, targeted by entry and unique-id suffix

Disabling the flag only prevents future entity additions; the existing registry rows stay and surface as unavailable entities. The migration therefore removes them explicitly, filtered by `config_entry_id` and by a `unique_id` suffix, computed from the platform attribute names.

Rationale: `unique_id` is built on the device name, which changes when a thermostat is renamed, so filtering on the full `unique_id` would miss renamed thermostats. Filtering on the suffix plus the config entry is stable.

### D6 — No automatic restore on plugin removal

`async_remove_entry` does not touch the thermostat flag. The user re-enables the core feature deliberately if they want it back.

Rationale: automatic restore would require the core to know which thermostats the plugin had migrated, to re-derive the level from the plugin entry, and to re-create entities — for a feature that is slated for deletion. Explicit is cheaper and safer.

### D7 — Three independent protection levels

1. **Config data** — the migration clears the flag, so the core stops creating entities even if the plugin is later missing.
2. **Access point** — the property prefers the external manager, so the arbitration follows the owner.
3. **Registry** — the orphan cleanup removes stale rows.

Rationale: each level alone is insufficient (config alone leaves the legacy manager driving if the plugin is loaded; the access point alone leaves duplicate entities; the registry alone leaves the core manager competing). Together they make the hand-over correct regardless of ordering.

## Double-refresh analysis

A thermostat is refreshed twice per cycle through two independent paths:

1. `thermostat_climate.py:1249` — the climate control path, on the stop transition.
2. `base_thermostat.py:2017-2028` — the generic external-manager loop, whose return value is ignored.

The auto-start/stop algorithm accumulates error over elapsed time (`accumulated_error += k * dt`). Running it twice per cycle with two distinct clock readings doubles the accumulated error and makes the detection threshold arrive twice as fast.

The algorithm already protects against this: it computes `dt` from the runtime clock and, when `dtmin <= 0.2`, treats the call as a duplicate and skips accumulation entirely (`CYCLE_SEC = 120`, so a genuine cycle never yields `dt` that small).

Consequence for the delegation: the guard holds **only if** the external manager reads `runtime.now`. A manager calling `datetime.now()` would measure a real double interval and defeat the guard. This is the reason the API change adds a spec requirement on the clock source, and the reason the plugin change has a dedicated test asserting no double accumulation.

No change is required on the core side for this: the double refresh is already the norm for every external manager, and `refresh_and_update_if_changed()` (`force_changed()` + forced `update_states`) is idempotent when the computed state does not change.

## Risks / Trade-offs

- **Migration write while the entry is reloading**: writing entry data triggers a reload. Deferring to `EVENT_HOMEASSISTANT_STARTED` and writing once per thermostat limits it to one reload per thermostat, on the first start after installation.
- **Level loss if the copy step is skipped**: guarded by ordering (D3) and by copying before writing the flag.
- **Inert manager hiding a real bug**: if the external manager fails to attach after the flag is cleared, the thermostat silently has no auto-start/stop. Mitigated by the plugin's `supports()` contract and by the fact that the marker is only written when the plugin actually registered.
- **Rename breaking the cleanup filter**: mitigated by the suffix-based match (D5).
- **Dependency on the API change**: the core cannot raise its `vtherm_api` constraint to `0.13.0` before that API release exists. Sequencing is a hard prerequisite, not a preference.

## Migration Plan

1. Ship the substitutable property and the inert manager guard (no behavior change for anyone).
2. Ship the migration and the registry cleanup together, in the same release, so no release ships a cleared flag without the cleanup.
3. The plugin registers, triggers the migration, and owns the decision.
4. A later change deletes the core implementation once the plugin is adopted.
