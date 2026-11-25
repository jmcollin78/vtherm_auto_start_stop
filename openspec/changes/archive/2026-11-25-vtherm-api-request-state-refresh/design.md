# Design

## Context

`vtherm_api` exposes `InterfaceThermostatRuntime`, the read-mostly view of one thermostat available to an external feature manager. Two gaps block moving auto-start/stop out of the core:

1. A plugin manager can be refreshed each cycle, but cannot ask the thermostat to recompute its state. The core does it inline for its own managers, then returns early from the control cycle.
2. The feature needs two facts the runtime does not expose: whether the thermostat is valve-regulated (an eligibility fact, matching the core rule), and which HVAC modes it accepts (to validate a stop mode against the thermostat).

A third, non-API issue matters for the port: an external manager is refreshed twice per cycle (once by the climate-specific control path, once by the generic external-manager loop), so its time-based state must be protected by the thermostat clock.

## Goals / Non-Goals

**Goals**

- A public, minimal way for a plugin manager to make a decision effective immediately.
- The two eligibility facts, so the plugin does not parse thermostat configuration keys.
- No behavior change for existing plugins.

**Non-Goals**

- No generic "HVAC mode override" mechanism. The core keeps its arbitration; the plugin feeds the facts the arbitration consumes.
- No exposure of underlying entities, requested state objects, or the state manager.
- No change to the core auto-start/stop feature in this change.
- The core implementation of the two new members is in scope (it is what makes the contract testable end to end); it ships in the same release train as the raised `manifest.json` constraint.

## Decisions

### D1 — One coroutine instead of an override primitive

Add `async_request_state_refresh()` rather than a mode/reason override API.

Rationale: the arbitration chain in the state manager already knows how to turn "auto-stop detected" plus "stop mode" into an effective mode and a published reason. A plugin that feeds those two facts gets the arbitration, the reason vocabulary, the UI rendering and the LLM summary for free, with zero change to the state manager. An override API would duplicate the arbitration and re-open the priority question for every future plugin.

### D2 — Refresh means what the core does inline

Implementation of the request mirrors the existing core path exactly: mark the requested state as changed, then force a recalculation of the current state. This keeps one semantics in the codebase and avoids a second, subtly different refresh path.

Trade-off: the call performs a full recalculation, which is heavier than a targeted update. Accepted, because it is called on a state transition, not per cycle.

### D3 — Not ready is not an error

The core already tolerates a not-ready thermostat in the control path. The request therefore logs and returns instead of raising, so a plugin does not need to reproduce the readiness rule. A plugin that wants to retry after startup keeps its own retry logic, which it needs anyway for the first call after a restart.

### D4 — Two read-only facts, not configuration exposure

`has_valve_regulation` and `vtherm_hvac_modes` are exposed as facts rather than letting the plugin read `entry_infos`.

Rationale: `entry_infos` is the merged configuration, including central configuration overrides. A plugin that recomputes the regulation mode from it will drift from the core. The facts are computed by the thermostat, so they stay correct when the core changes how it derives them.

`has_valve_regulation` is an eligibility fact: a valve-regulated `over_climate` thermostat cannot host the feature, which mirrors the core manager's own guard. `vtherm_hvac_modes` answers the separate question of whether a configured stop mode is one the thermostat will actually apply.

### D5 — Clock rule documented, not enforced

The API cannot forbid `datetime.now()`. The contract states the rule, the plugin follows it, and its own tests assert the deduplication. Enforcing it would need a clock injection mechanism whose cost outweighs the benefit.

## Risks / Trade-offs

- **Version sequencing**: the core cannot raise its minimum `vtherm_api` constraint before the API release is published, or the dependency resolution breaks. The release must precede the core change.
- **Recalculation cost**: a plugin could call the refresh from a hot path. Mitigation is documentation plus the fact that a well-behaved manager only calls it on a transition.
- **Silent divergence**: a plugin reading the clock wrongly loses the double-refresh protection with no error. Mitigated by a spec requirement and a dedicated test in the plugin change.
- **Eligibility drift**: if the core later adds another ineligibility rule, the two facts may become insufficient. Accepted; additional facts can be added without breaking the contract.

## Migration Plan

1. Add the three members to the contract, implement them on the thermostat, ship as a minor version.
2. Publish the API version.
3. Raise the minimum constraint in the core in the change that consumes the members.
4. No plugin can be released in between, since nothing consumes the new members yet.

## Open Questions

None.
