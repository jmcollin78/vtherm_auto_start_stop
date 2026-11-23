# Proposal

## Why

Auto-start/stop is today a core feature: it is configured inside the thermostat entry, its entities are created by the thermostat platforms, and its manager is instantiated by the core. That makes it impossible to improve its configuration model (global defaults, per-thermostat instances) without changing the thermostat configuration flow, and it keeps a niche feature inside the core forever.

An external plugin can already host the feature: the core instantiates one feature manager per eligible thermostat from a registered factory, refreshes it each cycle, and merges its custom attributes. What the core still lacks is a way to hand over cleanly: a substitutable access point so the arbitration reads the external manager, an inert placeholder so the legacy manager stops competing, and an automatic migration so an existing installation is not left with duplicate entities or a silently disabled feature.

## What Changes

- **Config-driven hand-over**: when a thermostat configuration entry carries a migration marker, the core stops creating its own auto-start/stop entities and treats the external manager as the only owner.
- **Substitutable access point**: the thermostat property that the state manager reads to decide auto-stop becomes a resolution that prefers an external manager with the stable name `auto_start_stop`, falling back to the legacy core manager.
- **Inert legacy manager**: when an external manager with that stable name is present, the legacy core manager is instantiated but performs no work and publishes no competing state, so two managers never drive the same thermostat.
- **Automatic migration**: when the plugin is loaded and a thermostat is still flagged as using the core feature while an external manager is actually attached to it, the core writes `use_auto_start_stop_feature = False` and stamps a marker. The legacy level is left in the thermostat entry, where the plugin reads it when the user creates its own configuration.
- **Orphan entity cleanup**: when the core feature stops being enabled, the registry entries created for it are removed instead of being left orphaned.
- **No behavior change otherwise**: a thermostat with neither the plugin nor the migration marker behaves exactly as today, and the state manager's arbitration is untouched.

## Capabilities

### New Capabilities

- `auto-start-stop-delegation`: how the core hands the auto-start/stop decision over to an external manager, stays inert while it is delegated, migrates an existing installation without duplicate entities, and falls back to its own implementation when no external manager exists.

### Modified Capabilities

None.

## Impact

- `custom_components/versatile_thermostat/base_thermostat.py`: the substitutable access point, the inert legacy manager guard, the deferred migration step, and the registry cleanup helper.
- `custom_components/versatile_thermostat/feature_auto_start_stop_manager.py`: an inert mode that short-circuits the algorithm without removing the legacy implementation.
- `custom_components/versatile_thermostat/switch.py` and `select.py`: entity creation now depends on the migration marker as well as the configuration flag.
- `custom_components/versatile_thermostat/__init__.py`: the post-startup migration step.
- `custom_components/versatile_thermostat/manifest.json`: the raised `vtherm_api` minimum constraint.
- `state_manager.py` is explicitly **not** modified: it keeps reading the same attribute, which now resolves to whichever manager owns the decision.
- Depends on the `thermostat-runtime-api` change being published first, since the plugin needs the immediate-refresh request to make its decision effective in the same cycle.
