# Design

## Context

The core feature is one manager per thermostat, created from the thermostat entry, with the level stored in that entry. The plugin must reproduce its behavior while changing the configuration model, and it must plug into the existing external-manager mechanism rather than inventing one.

The external-manager mechanism already provides everything the runtime needs: a factory registered through the API, an instantiation loop per eligible thermostat, a refresh on each cycle, a merge of custom attributes into the thermostat state, and — after the delegation change — a substitutable access point that the arbitration reads. What the plugin must get right is the configuration layering, the eligibility predicate, the clock source, and the attribute compatibility.

Reference implementations exist in the organization: `vtherm_heating_failure_detection` provides the global-versus-targeted entry model with a `effective_config` cascade and a `supports()` returning `effective_config(...) is not None`; `vtherm_auto_fan_extended` provides the factory/manager/registry split; `vtherm_inhibition` provides the thermostat selector with `integration="versatile_thermostat"`.

## Goals / Non-Goals

**Goals**

- Behavioral parity with the core feature for phase 1.
- A configuration model that removes the level from the thermostat entry.
- One global configuration sufficient for shared detection parameters, with optional dedicated parameter overrides.
- One persistent enable switch and independent stop-mode select for every covered eligible thermostat, including global-only coverage.
- No configuration creation or editing for individual enable or stop-mode changes.
- Backward compatibility with the production card without modifying its code or existing dashboard bindings; read-only source inspection is allowed.
- Eligibility enforced before the user validates and again at every load.
- Exact attribute and off-reason compatibility.
- A single place to extend parameters in phase 2.

**Non-Goals**

- No new detection algorithm, no new level, no new stop mode in phase 1.
- No custom threshold editing in phase 1 (only the resolution step is prepared).
- No widening of eligibility: valve-regulated `over_climate` thermostats stay excluded, exactly as in the core.
- No automatic dedicated entry or hidden configuration override map for switch/select changes; their states belong to the entities.
- No automatic re-enable of the core feature on uninstall (owned by the core change).

## Decisions

### D1 — Manager identity and stable name

The plugin manager registers under the stable name `auto_start_stop`, which is the name the core delegation resolves. This is what makes the property substitution work without the core knowing the plugin.

Consequence: the name must not collide with the legacy manager's name. It does not, because the core manager's `name` property returns the thermostat name.

### D2 — Configuration model: one global entry, N dedicated entries

`unique_id` is the domain alone for the global instance, and `DOMAIN-<vtherm_unique_id>` for a dedicated instance. This mirrors `vtherm_heating_failure_detection` and keeps a single integration with two entry shapes rather than two integrations.

Detection-parameter resolution is a cascade: plugin defaults, then global parameters, then dedicated parameter overrides. Only missing parameter fields inherit from the preceding layer. The cascade is implemented once in `models.py`. Named levels remain the phase-1 parameterization; explicit custom thresholds and durations require a later specification.

The global instance covers every eligible thermostat without requiring dedicated entries. Removing a dedicated parameter instance restores inherited detection parameters, not enable/mode states. A dedicated instance can operate without a global instance, inheriting missing parameters from plugin defaults. Plugin defaults alone do not constitute effective coverage.

Separate live entity state from configuration. `enabled` and `auto_start_stop_stop_mode` on the global configuration are explicitly labelled initialization defaults, used only when a control has no saved state. Their later edits do not reset existing entities, including entities never manually changed. Parameter edits still propagate to inheriting thermostats. Existing configuration-backed individual choices migrate once as described in D15; they are not an ongoing override layer.

### D3 — Identity by `vtherm_unique_id`, not entity id

Dedicated parameter entries and each thermostat's control pair key on the thermostat's unique id rather than its climate entity id. Global coverage must use the same per-thermostat entity unique IDs as dedicated coverage.

Rationale: entity id changes on rename; the unique id does not. Selecting on entity id would silently orphan the configuration on a rename, which is exactly the failure mode the core avoids.

### D4 — Eligibility predicate, evaluated twice

The predicate is: the thermostat is `over_climate` **and** is not valve-regulated. This is exactly the guard the core manager applies at `feature_auto_start_stop_manager.py:55` (`if not is_over_climate or have_valve_regulation: return`), so the plugin is functionally equivalent to the core feature on this point.

It is evaluated in two places, deliberately:

- **Config flow**: the thermostat selector filters on `integration="versatile_thermostat"`, then the selected thermostat is checked, and an ineligibility produces an explicit error field naming the reason (wrong type, or valve regulation). This is the phase-1 configuration improvement: the core flow simply hides the menu (`config_flow.py:657-662`) instead of explaining why.
- **`factory.supports(runtime)`**: the same predicate, recomputed on every load from the runtime facts. A thermostat reconfigured into an ineligible state after its entry was created must not be attached.

Rationale for keeping the valve exclusion rather than widening it: widening is technically safe (a stop at `off` closes the valve via `thermostat_climate_valve.py:356`), but it would be a functional extension, not a port. Keeping the predicate identical makes the later deletion of the core feature a pure removal with no behaviour change for any user, which is the whole point of the migration.

### D5 — Disabled is a persistent entity state, not an exclusion

There are only two entry shapes: global and optional dedicated parameter configurations. A thermostat disables detection through its enable switch, without creating or changing a configuration entry. Global `enabled: false` initializes previously uninitialized switches as off; it does not suppress entities or reset saved switches. The exclusion entry shape and `excluded` flag are removed.

An effective configuration remains non-null while the switch is off. After eligibility checking, `factory.supports()` tests for coverage, not switch state. The manager remains configured, publishes `auto_start_stop_enable: false`, freezes accumulated error and releases any detected stop. Both controls remain available; the select retains its saved stop mode. A frozen accumulated error need not be reset to zero.

Rationale: activation is local operational state, whereas configurations carry feature parameters. Turning Chambre on must affect Chambre only, survive restart and never add a visible or hidden dedicated configuration.

Alternative rejected: retaining an exclusion entry that resolves to no configuration. Although it removes the manager and attribute section, this adds a second way to disable the feature and a confusing extra UI branch. Exact interface parity with a core feature that was never configured is no longer a requirement for a disabled plugin configuration.

### D6 — Dedicated configuration starts directly with thermostat selection

With no existing plugin entry, the user flow creates global detection parameters and initialization-only enable/mode defaults. Otherwise, it opens the thermostat selector directly, checks eligibility, and opens optional dedicated parameter settings. Dedicated forms do not manage runtime enable or stop mode; the existing entities do that. Legacy dedicated fields are handled by migration rather than reintroduced as authoritative controls.

The configure-or-exclude menu, exclusion step, exclusion-only options abort and associated translations are removed. Options editing uses the same settings for every dedicated entry. Existing unique ids and the one-global/one-dedicated-per-thermostat constraints remain unchanged.

Rationale: after the initial global configuration there is only one entry type to add, so an intent menu has no purpose. The UI follows the configuration model instead of introducing a separate opt-out concept.

### D7 — `has_valve_regulation` is an eligibility fact, not a stop-mode input

Since eligibility is kept identical to the core (D4), a valve-regulated thermostat never gets a manager, so no stop mode ever needs to be resolved for one.

Consequence for the API contract: `has_valve_regulation` is consumed by `factory.supports()` as an eligibility gate, and `vtherm_hvac_modes` remains available to validate a configured stop mode on eligible thermostats. Neither is used to rewrite the configured mode.

### D8 — Core migration is independent of the effective enable state

The core-side migration clears the legacy flag for every thermostat that had it enabled, whether the plugin's effective configuration is enabled or disabled.

Rationale: a disabled plugin configuration must not leave the core implementation running in its place. The plugin's configured manager can remain present but inactive; the legacy core flag remains cleared.

Creating an optional dedicated parameter instance still seeds its level from the legacy core value when available. Existing dedicated parameters are not overwritten from legacy core values. Creating or editing that entry does not reset existing switch/select states.

### D9 — Runtime clock only

The manager reads `runtime.now` and never `datetime.now()`.

Rationale: the thermostat is refreshed twice per cycle (climate control path plus generic external-manager loop). The algorithm's `dtmin <= 0.2` guard collapses the second refresh to a no-op only when both refreshes observe the same clock. Using a local clock would double the accumulated deviation and halve the effective detection time. This is asserted by a dedicated test.

### D10 — Immediate refresh only on transition

`async_request_state_refresh()` is called only when the detection flag changes.

Rationale: the call forces a full recalculation. Calling it every cycle would add a recalculation per cycle per thermostat for no benefit; the generic external-manager loop already tolerates a changed flag being applied at the next cycle, but the climate control path returns early after refreshing its managers, so a flag set during that path would otherwise be ignored for the whole cycle. Restricting the call to transitions keeps the cost at two calls at most per stop and per resume.

### D11 — Attribute section reproduced verbatim

The manager publishes the same keys as the core feature: detection flag, level, minimum duration, accumulated deviation, deviation threshold, last switch date, stop mode, enable state. The thermostat merges manager custom attributes into the existing section, so the core's attribute section becomes the plugin's.

Rationale: the existing UI card and the LLM attribute index read that section by name. Changing the shape would break them silently.

### D12 — Phase-2 readiness through a single resolution function

`resolve_params(level)` returns the minimum duration and the threshold for a level. The detection code only consumes its output.

Rationale: phase 2 adds a `personnalise` mode with explicit values. With this indirection, that mode is one new branch in one function; without it, every call site would need a conditional and the level vocabulary would leak into the algorithm.

### D13 — Independent switch and select for every covered eligible thermostat

Forward both platforms for global and dedicated parameter entries. A global configuration alone creates exactly one enable switch and one stop-mode select for every eligible thermostat, including when its enable default is false. No dedicated entry is created automatically. New eligible thermostats receive their pair when discovered; ineligible and uncovered thermostats expose no active plugin controls.

An integration config entry can own many per-thermostat entities. While a global entry exists, it owns the control pairs, even for thermostats with dedicated parameter overrides. Without a global entry, a dedicated parameter entry owns its thermostat's pair. Ownership and parameter source are separate concerns. Key creation and initialization by thermostat unique ID, wait for both platform callbacks and legitimate core cleanup, and create each pair once.

The select exposes the manager's existing stop-mode list: `off` is always available, and `fan_only` and `dry` are included only when supported. It contains neither `disabled` nor regulation modes such as heat, cool or auto. Both controls and stop-mode labels are translated.

The persistent operational values remain `enabled` and `auto_start_stop_stop_mode`, but their source of truth is the entities, not configuration fields:

- The switch reflects and persists its thermostat's enable state. Turning it off releases a detected stop without forgetting the mode.
- Turning the switch on enables detection with the saved stop mode.
- Selecting a supported stop mode persists only that field. In particular, changing the mode while disabled does not enable detection.
- An unsupported selection raises an explicit validation error before any persistence or manager mutation.

Commands change only that thermostat's entity state and live manager. They never update global defaults or create a dedicated entry. Existing card calls remain `switch.turn_on`, `switch.turn_off` and `select.select_option`; attribute names, option values and historical entity IDs remain compatible.

Adding or removing dedicated parameter entries leaves the same controls, IDs and saved states intact. When coverage ownership must move between global and dedicated entries, coordinate platform teardown and registry reassignment through official Home Assistant APIs before entry removal can delete the rows. Preserve registry identities, restoration data and subsequent user renames; never briefly create a second pair as a handover mechanism.

Removing the global entry removes controls only for thermostats without remaining dedicated coverage. Both controls remain available while their thermostat's switch is off. Manager reattachment and parameter edits synchronize with the saved operational states described in D15.

Terminology note: "global instance" is the single optional entry carrying installation-wide defaults (`unique_id` = domain). It has nothing to do with a Versatile Thermostat **central configuration** entry, which is not `over_climate` and is therefore ineligible.

### D14 — Preserve historical entity IDs independently of configuration scope

The core delegation migration records the exact historical core switch and select entity IDs in the thermostat entry under `auto_start_stop_entity_ids`, keyed by `switch` and `select`, before clearing the feature flag and removing its entities. Registry matches require the core platform, owning core entry, domain and feature-specific unique-id suffix. Persisted identities are not recomputed from a thermostat name. Already-delegated test installations can recover missing identities from Home Assistant's retained deleted-registry entries when available.

The plugin reads this metadata when creating controls under global-only or dedicated coverage. It does not wait for a dedicated entry. While the core still owns a target ID, pair creation waits for registry removal and retries; a different owner is an explicit conflict, not a reason to append `_2` or remove that owner's entity.

Reuse existing plugin registry entries and stable plugin unique IDs. Track historical-ID adoption per entity using plugin registry metadata, not one boolean shared by a global config entry. Migrate the former dedicated-entry adoption flag so later user renames are not undone during the ownership transition. Preserve this metadata when ownership changes. If no historical core identity is available, retain existing plugin IDs; new controls use core-compatible names, not hardcoded examples. Do not delete the former plugin switch; recreate it only when absent.

Global-only controls adopt historical IDs immediately after legitimate core cleanup. Adding or removing a dedicated parameter entry neither changes those IDs nor creates another pair.

Resolve the thermostat through its climate registry owner or the core entry identity. The core publishes its config-entry ID as the climate unique ID; targeted reloads and global-override filtering must recognize that ID, not only the optional config-entry `unique_id`, so dedicated setup actually triggers core delegation and releases its controls.

Rationale: recreating an English-looking default name does not preserve renamed entities or guarantee exact IDs. Remembering the registry identity before cleanup preserves dashboard and automation references without coupling the plugin to the card. Persistent adoption state prevents a later thermostat reload from undoing a user's rename.

### D15 — Native persistent entity state, with initialization-only defaults

Use Home Assistant's entity restoration mechanism for each switch and select, with versioned extra restore data where needed to distinguish completed migration from obsolete test-version state. Do not introduce a per-thermostat configuration entry or a global configuration override dictionary for ordinary control actions, and do not edit `.storage` directly.

Bootstrap each control from its valid persistent plugin entity state. For an older plugin installation that has not completed this migration, preserve explicitly saved per-thermostat configuration-backed choices once, even if an obsolete UI restore cache disagrees. Otherwise retain valid historical core entity states when available. Only a genuinely missing state uses current initialization defaults. Migrating one control must not overwrite the other control's already valid state.

After bootstrap, configuration fields are never reapplied as operational state. A later default edit affects newly initialized entities only; a parameter edit reconfigures detection without resetting controls. Existing legacy fields may remain as migration input but must not repeatedly override later entity actions.

On startup or manager replacement, hold detection inactive until control restoration is resolved, apply the selected stop mode first, then the saved enable state. Existing entities reapply their states to a new manager without requiring another configuration entry. Unsupported restored modes are reported and reconciled to a supported safe mode without implicitly enabling detection; unsupported service selections fail before mutation.

Rationale: this is the production-style separation requested by the user: one shared parameter configuration, N independent persistent control pairs. Dedicated configurations are needed only for differing feature parameters, not to remember that Chambre is enabled or uses a particular stop mode.

### D16 — The production card is a read-only compatibility reference

Inspecting VTherm UI Card source is allowed to verify entity IDs, option consumption, attributes and service calls. Do not modify its source or dashboard bindings, introduce a required card adapter, or make users replace configured entity targets. Implement any necessary compatibility in the plugin and coordinated core. Verify unchanged card interactions against both global-only and dedicated-parameter coverage.

## Risks / Trade-offs

- **Divergence from the core algorithm over time**: the ported algorithm is a copy. Mitigated by keeping the copy minimal and by the fact that the core implementation is scheduled for deletion.
- **Ineligible after reconfiguration**: the factory re-check drops the manager, so the feature stops silently. Mitigated by a log entry naming the reason.
- **Disabled mistaken for absent**: every covered thermostat retains its attributes and both controls while switched off. Mitigated by global-only tests with false initialization defaults and no detection activity.
- **Defaults mistaken for live controls**: later enable/mode default edits intentionally do not reset existing entities. Mitigated by initialization-only form labels, documentation and restart tests; detection-parameter inheritance remains live.
- **Restoration or migration resets user choices**: migrate legacy individual choices once, retain versioned entity state thereafter, and block detection until mode and enable restoration are reconciled.
- **Configuration ownership changes duplicate or remove controls**: distinguish entity identity from parameter source, transfer only proven-owned rows through official APIs, and test global/dedicated additions, removals and restarts.
- **Off mistaken for disabled**: `off` selects the HVAC mode used on an automatic stop; the switch alone controls activation. Mitigated by independent controls, documentation and tests with the switch both on and off.
- **Historical IDs lost during delegation**: generating replacement names can break dashboards and automations. Mitigated by core-side persistence before cleanup and exact-ID assertions under global-only coverage as well as dedicated configurations.
- **Already-deleted test-version identities**: deleted-registry metadata may no longer be retained. Recover it when available; do not claim a missing customized historical name can be reconstructed from a display name.
- **Identity conflict or setup ordering**: another owner can occupy a historical ID, or core cleanup can still be pending. Wait only for legitimate core cleanup, report other conflicts explicitly, and test that unrelated entities are never modified.
- **Dedicated instance deletion**: only detection parameters return to global values; local activation and stop mode must not reset. Mitigated by entity-state and identity preservation tests.
- **Global instance deletion**: a thermostat without a dedicated instance has no effective configuration and loses its manager on the next load; a dedicated instance continues over plugin defaults. Mitigated by testing and documenting both cases rather than retaining stale global values.
- **Two refresh paths**: if the core later changes how often it refreshes external managers, the transition-only refresh keeps behavior correct but may delay the effect by one cycle. Accepted.
- **Dependency sequencing**: the plugin cannot be released before both prerequisite changes are published.

## Migration Plan

1. Publish `thermostat-runtime-api` with the new members.
2. Publish the core delegation change with durable historical entity-ID capture before entity cleanup.
3. Install the plugin and configure global detection parameters and initial control defaults. Every eligible thermostat receives its two controls; no dedicated entry is needed. Optional dedicated parameter configurations may still seed their level from the legacy core value.
4. The core flag is already cleared by the delegation change, so no duplicate configuration or duplicate entity exists at any point.
5. For this configuration simplification, remove exclusion handling from the model, config flow, constants, registry, entity platforms, fixtures and translations. No exclusion entries have been created in the test installation, so no migration, compatibility reader or automatic conversion is required. Existing global and ordinary dedicated entries retain their identities and values.
6. Restore or retain one switch and one stop-mode-only select per covered thermostat. Migrate existing individual control choices into persistent entity states, adopt historical IDs and per-entity adoption metadata, and preserve later user renames. Replace the former dedicated-only creation rule and configuration-authoritative restoration logic; the previous automated results do not prove this revised behavior. Restart after deploying the coordinated core/plugin updates; no card or dashboard changes are required.
7. Phase 2 adds the `personnalise` mode inside `resolve_params`.
