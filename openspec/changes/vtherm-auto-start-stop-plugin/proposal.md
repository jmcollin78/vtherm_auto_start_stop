# Proposal

## Why

The core auto-start/stop feature is configured inside the thermostat entry: one level per thermostat, no way to define a default for the whole installation, no way to share a configuration between similar thermostats, and no place to add behaviour (per-thermostat tuning, custom thresholds) without changing the core configuration flow.

Moving the feature to a plugin removes that constraint. The thermostat already instantiates one external feature manager per eligible thermostat from a registered factory, refreshes it each cycle, merges its custom attributes, and now hands the auto-start/stop decision over to it. The plugin can therefore offer a global default plus per-thermostat overrides, and evolve independently.

## What Changes

- **Auto-start/stop leaves the thermostat configuration** for plugin users: the feature is configured in the plugin's own config flow.
- **Global instance**: one optional entry providing the defaults, including the enable state, for every `over_climate` thermostat without valve regulation that has no dedicated override.
- **Dedicated instances**: one entry per thermostat that needs its own parameters, resolving as `plugin defaults → global instance → dedicated instance`. A dedicated instance can disable a globally enabled feature or enable a globally disabled feature.
- **Eligibility is enforced twice**: the config flow rejects a thermostat that is not `over_climate` or that is valve-regulated with an explicit error, and the factory re-checks the same predicate on every load so a later reconfiguration cannot leave an ineligible attachment. The predicate is identical to the core feature's, so no thermostat gains or loses support.
- **One way to disable the feature**: set `enabled: false` on the global or dedicated configuration. A disabled configuration remains configured and keeps its manager, attributes and, for dedicated instances, entities; it runs no detection and requests no automatic stop.
- **Simplified configuration flow**: the first entry configures the global defaults; further entries open the thermostat selector directly, followed by its settings. **BREAKING**: the configure-or-exclude menu and exclusion entry type are removed from the test-version UI. No exclusion entries have been created, so no exclusion-data migration or compatibility path is required.
- **Return to global defaults**: removing a dedicated instance makes that thermostat use the global configuration again, if one exists, without affecting other thermostats.
- **Core-compatible controls per dedicated instance**: restore one enable switch and one stop-mode select. The switch controls activation without changing the saved stop mode. The select offers `off` and `fan_only`/`dry` only when supported; choosing a mode does not enable the feature. There is no `disabled` select option. Thermostats using only global defaults still have no dedicated entity.
- **Exact entity-id compatibility**: preserve the historical core switch and select entity IDs, including user-customized IDs, rather than deriving replacements from the current thermostat name. Coordinate with core delegation to remember those IDs before cleanup, and reuse them when a dedicated entry is created. Preserve subsequent user renames, never silently create an `_2` replacement, and leave other entries and integrations untouched.
- **Upgrade of existing plugin entities**: stop deleting the plugin enable switch, restore it when absent, and return the combined test-version select to a stop-mode-only control. Retain the configured enable state and stop mode. Existing plugin controls retain their identities when no historical core identity must be adopted.
- **Functional parity in phase 1**: the five levels (`very_slow` to `fast`, plus `none`), the stop modes (`off`, `fan_only`, `dry`), the same eligibility (including the exclusion of valve-regulated thermostats), the same algorithm, the same custom attributes and the same off-reason are preserved. No user gains or loses a supported thermostat compared with the core feature.
- **Room for phase 2**: parameters are resolved through a single `resolve_params(level)` function so a `personnalise` mode can later supply explicit thresholds without changing call sites.

## Capabilities

### New Capabilities

- `auto-start-stop-plugin`: the plugin's configuration model (global default and per-thermostat instances, resolution order, eligibility rules), its runtime behavior (delegated manager, cycle refresh, immediate state refresh, published attributes, entities), and its migration from the core configuration.

### Modified Capabilities

None.

## Impact

- New integration `custom_components/vtherm_auto_start_stop/`: `__init__.py`, `config_flow.py`, `const.py`, `models.py`, `factory.py`, `manager.py`, `registry.py`, `switch.py`, `select.py`, `manifest.json`, translations.
- Ported algorithm module, rewritten to read the runtime clock and to expose `resolve_params(level)`.
- Consumes `thermostat-runtime-api` (immediate refresh request, valve-regulation fact, accepted HVAC modes) and `auto-start-stop-delegation` (stable name `auto_start_stop`, marker `auto_start_stop_migrated_by`, persistent historical entity IDs).
- Depends on both changes being released first.
