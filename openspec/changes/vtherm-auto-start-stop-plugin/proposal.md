# Proposal

## Why

The core auto-start/stop feature is configured inside the thermostat entry: one level per thermostat, no way to define a default for the whole installation, no way to share a configuration between similar thermostats, and no place to add behaviour (per-thermostat tuning, custom thresholds) without changing the core configuration flow.

Moving the feature to a plugin removes that constraint. The thermostat already instantiates one external feature manager per eligible thermostat from a registered factory, refreshes it each cycle, merges its custom attributes, and now hands the auto-start/stop decision over to it. The plugin can therefore offer a global default plus per-thermostat overrides, and evolve independently.

## What Changes

- **Auto-start/stop leaves the thermostat configuration** for plugin users: the feature is configured in the plugin's own config flow.
- **Global instance**: one entry is sufficient while eligible thermostats share the same detection parameters. It provides those parameters to every `over_climate` thermostat without valve regulation, plus initial enable and stop-mode defaults for entities that have no saved state.
- **Optional dedicated instances**: entries are for per-thermostat detection-parameter overrides, resolving as `plugin defaults → global instance → dedicated instance`. They are never required or automatically created to change enable or stop mode. Explicit custom thresholds and durations remain a future extension; this revision does not add them.
- **Eligibility is enforced twice**: the config flow rejects a thermostat that is not `over_climate` or that is valve-regulated with an explicit error, and the factory re-checks the same predicate on every load so a later reconfiguration cannot leave an ineligible attachment. The predicate is identical to the core feature's, so no thermostat gains or loses support.
- **Independent persistent entity states**: each thermostat's switch and select remember its enable state and stop mode, including across restart. Switching Chambre on affects Chambre only and creates no configuration entry. Turning its switch off freezes detection and releases a detected stop while keeping its manager, attributes and both controls.
- **Initialization defaults only**: global enable and stop-mode defaults seed entities without saved state. Editing these defaults later never overwrites existing entity states. Detection-parameter changes continue to apply to thermostats inheriting those parameters. **BREAKING for test-version plugin configurations**: configuration fields no longer remain authoritative over saved entity states; migrate existing saved choices once rather than resetting them.
- **Simplified configuration flow**: the first entry configures global parameters and initial control defaults; further entries open the thermostat selector directly for optional parameter overrides, not activation or mode control. **BREAKING**: the configure-or-exclude menu and exclusion entry type are removed from the test-version UI. No exclusion entries have been created, so no exclusion-data migration or compatibility path is required.
- **Return to global parameters**: removing a dedicated instance restores inherited detection parameters, if a global entry exists, without changing either entity's saved state or identity.
- **Two core-compatible controls for every covered thermostat**: as soon as the global configuration exists, every eligible thermostat gets exactly one enable switch and one stop-mode select, even if the global enable default is false and no dedicated entry exists. The select offers `off` and supported `fan_only`/`dry`, with no `disabled` option or implicit activation. Valve-regulated thermostats get neither control.
- **Exact entity-id compatibility**: preserve the historical core switch and select entity IDs, including user-customized IDs, rather than deriving replacements from the thermostat name. Adopt them for global-only coverage as well as dedicated configurations. Adding or removing a dedicated parameter entry must not duplicate or rename the controls. Preserve subsequent user renames, never silently create an `_2` replacement, and leave other entries and integrations untouched.
- **Unmodified production card**: backward compatibility must be supplied by the plugin and coordinated core changes. Neither VTherm UI Card source nor existing dashboard bindings may require modification. Consulting the card code in read-only mode is allowed.
- **Upgrade of existing plugin entities**: retain or restore the switch and return the combined test-version select to a stop-mode-only control. Migrate saved enable/mode choices into persistent entity state without creating dedicated entries for globally covered thermostats or losing existing choices. Preserve existing plugin identities when no historical core identity must be adopted.
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
