# Design

## Context

The core feature is one manager per thermostat, created from the thermostat entry, with the level stored in that entry. The plugin must reproduce its behavior while changing the configuration model, and it must plug into the existing external-manager mechanism rather than inventing one.

The external-manager mechanism already provides everything the runtime needs: a factory registered through the API, an instantiation loop per eligible thermostat, a refresh on each cycle, a merge of custom attributes into the thermostat state, and — after the delegation change — a substitutable access point that the arbitration reads. What the plugin must get right is the configuration layering, the eligibility predicate, the clock source, and the attribute compatibility.

Reference implementations exist in the organization: `vtherm_heating_failure_detection` provides the global-versus-targeted entry model with a `effective_config` cascade and a `supports()` returning `effective_config(...) is not None`; `vtherm_auto_fan_extended` provides the factory/manager/registry split; `vtherm_inhibition` provides the thermostat selector with `integration="versatile_thermostat"`.

## Goals / Non-Goals

**Goals**

- Behavioral parity with the core feature for phase 1.
- A configuration model that removes the level from the thermostat entry.
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

Resolution is a cascade: plugin defaults, then the global entry fields, then the dedicated entry fields. The cascade is implemented once, in `models.py`, and every consumer reads the result, so the order cannot diverge between the manager and the entities.

### D3 — Identity by `vtherm_unique_id`, not entity id

The dedicated entry keys on the thermostat's unique id rather than its entity id.

Rationale: entity id changes on rename; the unique id does not. Selecting on entity id would silently orphan the configuration on a rename, which is exactly the failure mode the core avoids.

### D4 — Eligibility predicate, evaluated twice

The predicate is: the thermostat is `over_climate` **and** is not valve-regulated. This is exactly the guard the core manager applies at `feature_auto_start_stop_manager.py:55` (`if not is_over_climate or have_valve_regulation: return`), so the plugin is functionally equivalent to the core feature on this point.

It is evaluated in two places, deliberately:

- **Config flow**: the thermostat selector filters on `integration="versatile_thermostat"`, then the selected thermostat is checked, and an ineligibility produces an explicit error field naming the reason (wrong type, or valve regulation). This is the phase-1 configuration improvement: the core flow simply hides the menu (`config_flow.py:657-662`) instead of explaining why.
- **`factory.supports(runtime)`**: the same predicate, recomputed on every load from the runtime facts. A thermostat reconfigured into an ineligible state after its entry was created must not be attached.

Rationale for keeping the valve exclusion rather than widening it: widening is technically safe (a stop at `off` closes the valve via `thermostat_climate_valve.py:356`), but it would be a functional extension, not a port. Keeping the predicate identical makes the later deletion of the core feature a pure removal with no behaviour change for any user, which is the whole point of the migration.

### D5 — Opt-out is an exclusion entry, not a neutral level

A thermostat opts out of the global instance by means of an **exclusion entry**: a dedicated entry with no parameter whose only effect is to mark the thermostat as not covered.

Rationale: the core offers opt-out by simply not enabling the feature, and the parity requirement is that an opted-out thermostat look like a thermostat the feature was never enabled for. A neutral level would not achieve that: the core distinguishes "not configured" from "configured at level none" (`_is_configured` is separate from the level, and `add_custom_attributes` publishes the section only `if self.is_configured`). Resolving an exclusion to *no effective configuration* reproduces the exact same observable state: no manager, no attribute section, nothing in the arbitration.

Alternative considered and rejected: a boolean `enabled` field on the dedicated entry, as `vtherm_heating_failure_detection` does. Rejected because "enabled: false" still yields an effective configuration, hence a manager and an attribute section, which is precisely what parity forbids.

Alternative considered and rejected: relying on the enable switch. Rejected because the switch only exists when a dedicated instance exists, so it cannot serve a thermostat configured through the global instance — the case that raises the question. It would also publish the attribute section with a disabled flag, which differs from "never enabled".

### D6 — Exclusions take precedence over every layer

The resolution order becomes: exclusion, then plugin defaults, then global instance, then dedicated instance — where the exclusion short-circuits to "no configuration".

Rationale: an exclusion that a deeper layer could override would be meaningless once a global instance exists. Short-circuiting also keeps `factory.supports()` a single predicate, `effective_config(...) is not None`, identical to the reference plugin's shape.

Trade-off: a thermostat cannot be excluded and configured at the same time, which is intentional — the user either configures it or opts out.

### D7 — `has_valve_regulation` is an eligibility fact, not a stop-mode input

Since eligibility is kept identical to the core (D4), a valve-regulated thermostat never gets a manager, so no stop mode ever needs to be resolved for one.

Consequence for the API contract: `has_valve_regulation` is consumed by `factory.supports()` as an eligibility gate, and `vtherm_hvac_modes` remains available to validate a configured stop mode on eligible thermostats. Neither is used to rewrite the configured mode.

### D8 — Migration and exclusion are independent

The core-side migration clears the legacy flag for every thermostat that had it enabled, whether or not the plugin excludes that thermostat.

Rationale: exclusion means "no auto-start/stop for this thermostat", so leaving the core feature enabled on it would contradict the user's choice. After migration, an excluded thermostat has the core flag cleared and no plugin manager — which is precisely the "feature never enabled" state D5 targets.

Consequence: excluding a thermostat that previously used the core feature is a deliberate removal of the feature for it, not a neutral toggle. The config flow states this when the exclusion is created.

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

Trade-off: such a thermostat cannot be toggled from the dashboard. Accepted for phase 1; a shared switch is a candidate for phase 2.

Terminology note: "global instance" is the single optional entry carrying installation-wide defaults (`unique_id` = domain). It has nothing to do with a Versatile Thermostat **central configuration** entry, which is not `over_climate` and is therefore ineligible.

## Risks / Trade-offs

- **Divergence from the core algorithm over time**: the ported algorithm is a copy. Mitigated by keeping the copy minimal and by the fact that the core implementation is scheduled for deletion.
- **Ineligible after reconfiguration**: the factory re-check drops the manager, so the feature stops silently. Mitigated by a log entry naming the reason.
- **Exclusion mistaken for a level**: a user might expect to tune an excluded thermostat instead of configuring it. Mitigated by the exclusion entry being a distinct flow branch with no level field, and by documentation.
- **Global instance deletion**: removing the global instance reverts every non-excluded thermostat without a dedicated instance to plugin defaults, which may mean "no configuration". Mitigated by resolving to defaults rather than to the previous global values, and by documenting the effect.
- **Two refresh paths**: if the core later changes how often it refreshes external managers, the transition-only refresh keeps behavior correct but may delay the effect by one cycle. Accepted.
- **Dependency sequencing**: the plugin cannot be released before both prerequisite changes are published.

## Migration Plan

1. Publish `thermostat-runtime-api` with the new members.
2. Publish the core delegation change with migration and entity cleanup.
3. Install the plugin; its first configuration reads the legacy level carried by the thermostat entry and seeds the dedicated instance.
4. The core flag is already cleared by the delegation change, so no duplicate configuration or duplicate entity exists at any point.
5. Phase 2 adds the `personnalise` mode inside `resolve_params`.
