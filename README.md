# vtherm_auto_start_stop
A plugin for Versatile Thermostat aiming to start and stop automatically your climate device

## Installation

Use Home Assistant 2026.10 or later and a Versatile Thermostat version that
supports external auto-start/stop delegation. The plugin declares
`vtherm_api>=0.13.1` as a Python dependency.

Install this repository as a custom integration through HACS, or copy
`custom_components/vtherm_auto_start_stop` into Home Assistant's
`config/custom_components` directory. Restart Home Assistant, then add
**VTherm Auto Start/Stop** from **Settings > Devices & services**.

## Supported thermostats

Only `over_climate` thermostats without valve regulation are supported.
This restriction applies both to global defaults and dedicated configurations:
valve-regulated thermostats cannot use this plugin.

The configuration flow accepts the published `configuration.type` value
`over_climate` as well as the stored type `thermostat_over_climate`.
When state attributes are not yet available, eligibility is checked against the
thermostat's core configuration entry.

## Global defaults and dedicated configurations

1. The first entry configures the shared **detection level**, plus initial
   enable and stop-mode defaults. Every eligible thermostat receives its own
   switch and select, even if the initialization default is disabled.
2. Use each thermostat's switch and select, including through the unchanged
   VTherm UI Card, to change its activation and stop mode independently. These
   states survive reloads and restarts through Home Assistant entity restoration.
   Actions never create a configuration entry or modify global defaults.
3. Optional dedicated entries change **detection parameters only**. Add another
   entry, select the thermostat, then choose its level. No dedicated entry is
   needed merely to enable a thermostat or remember its stop mode.

Initialization defaults apply only when an entity has no saved state. Editing
them later does not reset any existing entity, even one never manually changed.
Detection-level edits still propagate to thermostats inheriting that parameter.

For example, leave initial activation disabled, then enable only Chambre using
its switch or the card. Salon stays disabled, and both choices survive restart
with just the single global configuration.

The dedicated form starts from the global level, except that an available legacy
core level seeds its level. Dedicated parameters override global parameters;
missing parameters inherit global values, then plugin defaults. Without global
coverage, a dedicated entry still supplies its thermostat's two controls.

## Detection levels

The plugin detects an automatic stop after an accumulated deviation exceeds the
`error_threshold`, for at least `dt_min` minutes. The named levels fix both
values:

| Level     | `dt_min` | `error_threshold` |
| --------- | -------- | ----------------- |
| Very slow | 60       | 20                |
| Slow      | 30       | 10                |
| Medium    | 15       | 5                 |
| Fast      | 7        | 2                 |

The **Custom** level lets you set both values per thermostat:

- `dt_min` in minutes, between **5** and **120**.
- `error_threshold` in °C, between **1** and **50** (step 0.5).

Both fields are **always visible** in the configuration form — whether the level
is named or Custom. They are pre-filled from the current entry, or from the
Slow values (30 / 10) when the entry does not yet carry custom values.

- When the level is **Custom**, the submitted values are applied.
- When the level is a named one, the algorithm ignores them and uses the static
  table for that level; the values are still persisted in the entry so the user
  does not have to re-enter them on a later switch back to Custom.
- Out-of-bounds values are rejected by the form.

The previous **None** level was removed: it duplicated the Slow behavior, and
any stored legacy value now resolves to Slow (30 / 10).

## Disabled does not mean unconfigured

A disabled configuration keeps its manager and its `auto_start_stop_manager`
attributes. It reports `is_auto_start_stop_configured: true` and
`auto_start_stop_enable: false`, does not accumulate error, and requests no
automatic stop. A previously accumulated error can remain visible, frozen at its
last value. Disabling releases a detected stop, subject to the thermostat's other
controls.

Every covered eligible thermostat has exactly two production-compatible controls:

- An **Enable auto start/stop** switch, which enables or disables detection
  without changing the saved stop mode.
- An independent **Auto start/stop stop mode** select:

| Option (service value) | Behavior                                 |
| ---------------------- | ---------------------------------------- |
| Off (`off`)            | Use HVAC `off` for automatic stops       |
| Fan only (`fan_only`)  | Use ventilation for automatic stops      |
| Dry (`dry`)            | Use dehumidification for automatic stops |

`fan_only` and `dry` are offered only when supported by the thermostat. `heat`,
`cool` and `auto` are not stop modes. **Off does not disable auto start/stop.**
Selecting a stop mode never enables or disables detection. Use `switch.turn_on`
or `switch.turn_off` to change activation.

Both controls remain present when detection is disabled. A saved stop mode is
restored before activation; detection waits until both states are initialized.
An unsupported restored mode is logged and safely reconciled to `off` without
enabling the feature.

## Preserving existing controls and dashboards

Install the coordinated compatible core and plugin versions, then restart Home
Assistant. Before removing its old controls, the core saves their exact entity
IDs. The plugin reuses those IDs under global-only or dedicated coverage,
including custom user names, without changing the card or dashboard configuration.
Adding a dedicated parameter entry later does not replace the controls. Legitimate core
controls must finish unloading before the plugin creates their replacements.

Existing plugin controls are reused rather than deleted. Later user renames are
preserved. An unrelated entity occupying a historical ID causes an explicit
configuration error: the plugin never takes it over or silently creates an `_2`
replacement. Resolve the conflict, then reload the owning plugin configuration.

Upgrading from the experimental combined selector restores the switch and removes
the select's `disabled` option. Saved activation and stop mode are unchanged:
a disabled thermostat with `dry` saved stays disabled and retains `dry`. Older
configuration-backed individual choices migrate once; later entity actions take
precedence over those legacy fields. Automations
written specifically for that experimental option must use the switch instead.
Already-delegated test installations can recover old core IDs from retained
registry deletion history. A custom historical ID cannot be reconstructed if
neither that history nor the core's saved metadata remains available.

## Removing entries

- Adding or removing a dedicated parameter entry preserves existing control IDs,
  activation and mode while changing only parameter inheritance.
- Removing the global entry leaves thermostats without dedicated entries
  unconfigured and removes their plugin controls. Dedicated entries retain their
  controls, IDs and saved states, using plugin defaults for missing parameters.
- With neither a global nor a dedicated entry, no plugin manager is attached.

## Migration from the core feature

The compatible Versatile Thermostat core delegates auto-start/stop to the plugin
and clears the legacy core feature flag. This also applies when the plugin
configuration is disabled, so the core feature does not run in its place.

When creating a dedicated entry, its level is seeded from the legacy thermostat
configuration if available. An existing dedicated entry is not overwritten.
Activation and stop mode remain controlled by its entities. Removing the plugin does not
automatically re-enable the old core feature.
