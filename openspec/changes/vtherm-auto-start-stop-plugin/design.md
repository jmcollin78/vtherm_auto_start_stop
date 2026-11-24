# Design

## Context

The core feature is one manager per thermostat, created from the thermostat entry, with the level stored in that entry. The plugin must reproduce its behavior while changing the configuration model, and it must plug into the existing external-manager mechanism rather than inventing one.

The external-manager mechanism already provides everything the runtime needs: a factory registered through the API, an instantiation loop per eligible thermostat, a refresh on each cycle, a merge of custom attributes into the thermostat state, and — after the delegation change — a substitutable access point that the arbitration reads. What the plugin must get right is the configuration layering, the eligibility predicate, the clock source, and the attribute compatibility.

Reference implementations exist in the organization: `vtherm_heating_failure_detection` provides the global-versus-targeted entry model with a `effective_config` cascade and a `supports()` returning `effective_config(...) is not None`; `vtherm_auto_fan_extended` provides the factory/manager/registry split; `vtherm_inhibition` provides the thermostat selector with `integration="versatile_thermostat"`.

## Goals / Non-Goals

**Goals**

- Behavioral parity with the core feature for phase 1.
- A configuration model that removes the level from the thermostat entry.
- One global configuration and optional dedicated overrides, using the same enable control to activate or deactivate the feature.
- Eligibility enforced before the user validates and again at every load.
- Exact attribute and off-reason compatibility.
- A single place to extend parameters in phase 2.

**Non-Goals**

- No new detection algorithm, no new level, no new stop mode in phase 1.
- No custom threshold editing in phase 1 (only the resolution step is prepared).
- No widening of eligibility: valve-regulated `over_climate` thermostats stay excluded, exactly as in the core.
- No per-thermostat entities for thermostats configured only through the global instance.
- No automatic re-enable of the core feature on uninstall (owned by the core change).

## Decisions

### D1 — Manager identity and stable name

The plugin manager registers under the stable name `auto_start_stop`, which is the name the core delegation resolves. This is what makes the property substitution work without the core knowing the plugin.

Consequence: the name must not collide with the legacy manager's name. It does not, because the core manager's `name` property returns the thermostat name.

### D2 — Configuration model: one global entry, N dedicated entries

`unique_id` is the domain alone for the global instance, and `DOMAIN-<vtherm_unique_id>` for a dedicated instance. This mirrors `vtherm_heating_failure_detection` and keeps a single integration with two entry shapes rather than two integrations.

Resolution is a cascade: plugin defaults, then the global entry fields, then the dedicated entry fields. This includes `enabled`: an explicit `false` overrides a global `true`, and a dedicated `true` overrides a global `false`. Only missing fields inherit from the preceding layer; false is never treated as missing. The cascade is implemented once, in `models.py`, and every consumer reads the result, so the order cannot diverge between the manager and the entities.

The global instance covers every eligible thermostat without a dedicated override. Removing a dedicated instance restores the global values on the next load, including the enable state. A dedicated instance can also operate without a global instance, inheriting missing fields from plugin defaults. Plugin defaults alone do not constitute an effective configuration.

### D3 — Identity by `vtherm_unique_id`, not entity id

The dedicated entry keys on the thermostat's unique id rather than its entity id.

Rationale: entity id changes on rename; the unique id does not. Selecting on entity id would silently orphan the configuration on a rename, which is exactly the failure mode the core avoids.

### D4 — Eligibility predicate, evaluated twice

The predicate is: the thermostat is `over_climate` **and** is not valve-regulated. This is exactly the guard the core manager applies at `feature_auto_start_stop_manager.py:55` (`if not is_over_climate or have_valve_regulation: return`), so the plugin is functionally equivalent to the core feature on this point.

It is evaluated in two places, deliberately:

- **Config flow**: the thermostat selector filters on `integration="versatile_thermostat"`, then the selected thermostat is checked, and an ineligibility produces an explicit error field naming the reason (wrong type, or valve regulation). This is the phase-1 configuration improvement: the core flow simply hides the menu (`config_flow.py:657-662`) instead of explaining why.
- **`factory.supports(runtime)`**: the same predicate, recomputed on every load from the runtime facts. A thermostat reconfigured into an ineligible state after its entry was created must not be attached.

Rationale for keeping the valve exclusion rather than widening it: widening is technically safe (a stop at `off` closes the valve via `thermostat_climate_valve.py:356`), but it would be a functional extension, not a port. Keeping the predicate identical makes the later deletion of the core feature a pure removal with no behaviour change for any user, which is the whole point of the migration.

### D5 — Disabled is a configured state, not an exclusion

There are only two entry shapes: global and dedicated. A thermostat disables the feature through `enabled: false`, either inherited from the global entry or set on its dedicated entry. The separate exclusion entry shape and `excluded` flag are removed.

An effective configuration remains non-null when disabled. After the eligibility check, `factory.supports()` tests for the existence of that configuration, not its enable state. The manager remains configured, publishes its attributes with `auto_start_stop_enable: false`, stops accumulating error and releases any detected stop. Dedicated entities remain available so the user can re-enable the same configuration. A frozen accumulated error need not be reset to zero.

Rationale: one enable control expresses the two user operations symmetrically: disable one thermostat when global defaults are enabled, or enable one thermostat when global defaults are disabled. Configuration presence and detection activity are distinct states.

Alternative rejected: retaining an exclusion entry that resolves to no configuration. Although it removes the manager and attribute section, this adds a second way to disable the feature and a confusing extra UI branch. Exact interface parity with a core feature that was never configured is no longer a requirement for a disabled plugin configuration.

### D6 — Dedicated configuration starts directly with thermostat selection

With no existing plugin entry, the user flow creates the global instance. Otherwise, it opens the thermostat selector directly, checks eligibility, and opens the dedicated settings. Both global and dedicated settings expose `enabled` alongside the level and stop mode.

The configure-or-exclude menu, exclusion step, exclusion-only options abort and associated translations are removed. Options editing uses the same settings for every dedicated entry. Existing unique ids and the one-global/one-dedicated-per-thermostat constraints remain unchanged.

Rationale: after the initial global configuration there is only one entry type to add, so an intent menu has no purpose. The UI follows the configuration model instead of introducing a separate opt-out concept.

### D7 — `has_valve_regulation` is an eligibility fact, not a stop-mode input

Since eligibility is kept identical to the core (D4), a valve-regulated thermostat never gets a manager, so no stop mode ever needs to be resolved for one.

Consequence for the API contract: `has_valve_regulation` is consumed by `factory.supports()` as an eligibility gate, and `vtherm_hvac_modes` remains available to validate a configured stop mode on eligible thermostats. Neither is used to rewrite the configured mode.

### D8 — Core migration is independent of the effective enable state

The core-side migration clears the legacy flag for every thermostat that had it enabled, whether the plugin's effective configuration is enabled or disabled.

Rationale: a disabled plugin configuration must not leave the core implementation running in its place. The plugin's configured manager can remain present but inactive; the legacy core flag remains cleared.

Creating a dedicated instance still seeds its level from the legacy core value when available. It inherits the global enable state unless the user changes it. Existing dedicated instances are not overwritten from legacy core values.

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

### D13 — Entities only for dedicated instances

The enable switch and the stop-mode selector are created only when a dedicated entry exists.

Rationale: an entity needs a stable owner, and an entity belongs to a config entry. A thermostat configured only through the **global instance** has no per-thermostat entry to own an entity, so its configuration is edited from the config flow instead.

The dedicated entry owns these entities even when its effective enable state is false. Registry lookup and platform setup no longer filter an exclusion flag. Disabling does not remove entities; deleting the dedicated instance does, and returns configuration resolution to the global instance if present.

Trade-off: such a thermostat cannot be toggled from the dashboard. Accepted for phase 1; a shared switch is a candidate for phase 2.

Terminology note: "global instance" is the single optional entry carrying installation-wide defaults (`unique_id` = domain). It has nothing to do with a Versatile Thermostat **central configuration** entry, which is not `over_climate` and is therefore ineligible.

## Risks / Trade-offs

- **Divergence from the core algorithm over time**: the ported algorithm is a copy. Mitigated by keeping the copy minimal and by the fact that the core implementation is scheduled for deletion.
- **Ineligible after reconfiguration**: the factory re-check drops the manager, so the feature stops silently. Mitigated by a log entry naming the reason.
- **Disabled mistaken for absent**: a disabled thermostat still exposes the attribute section and, for dedicated instances, controls. Mitigated by documenting the distinction and testing configured=true with enabled=false and no detection activity.
- **Dedicated instance deletion**: deleting a locally disabled instance can re-enable the feature if global defaults are enabled. Mitigated by documenting the return to global values and testing both global enable states.
- **Global instance deletion**: a thermostat without a dedicated instance has no effective configuration and loses its manager on the next load; a dedicated instance continues over plugin defaults. Mitigated by testing and documenting both cases rather than retaining stale global values.
- **Two refresh paths**: if the core later changes how often it refreshes external managers, the transition-only refresh keeps behavior correct but may delay the effect by one cycle. Accepted.
- **Dependency sequencing**: the plugin cannot be released before both prerequisite changes are published.

## Migration Plan

1. Publish `thermostat-runtime-api` with the new members.
2. Publish the core delegation change with migration and entity cleanup.
3. Install the plugin and configure global defaults. When creating a dedicated instance, read the legacy level carried by the thermostat entry and seed that instance.
4. The core flag is already cleared by the delegation change, so no duplicate configuration or duplicate entity exists at any point.
5. For this configuration simplification, remove exclusion handling from the model, config flow, constants, registry, entity platforms, fixtures and translations. No exclusion entries have been created in the test installation, so no migration, compatibility reader or automatic conversion is required. Existing global and ordinary dedicated entries retain their identities and values.
6. Phase 2 adds the `personnalise` mode inside `resolve_params`.
