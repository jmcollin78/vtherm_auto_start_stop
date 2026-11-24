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

1. The first entry configures the **global defaults**: level, stop mode and
   **Enabled**. They apply to every eligible thermostat without its own override.
2. To configure one thermostat differently, add another entry for this
   integration. The thermostat selector opens directly, followed by its settings.
3. Use **Enabled** to enable or disable that thermostat independently of the
   global defaults. You can edit the same entry later; no other entry type is
   needed.

Without a dedicated entry, a thermostat follows the global enable state.
With a dedicated entry, its explicit enable state takes precedence:

| Global Enabled | Dedicated Enabled | Effective state |
|---|---|---|
| On | On | On |
| On | Off | Off |
| Off | On | On |
| Off | Off | Off |

For example, leave the global defaults disabled and create an enabled dedicated
entry to test the feature on just one thermostat. Conversely, with global defaults
enabled, create a disabled dedicated entry to stop using it on one thermostat.

The dedicated form starts from the global settings, except that an available
legacy core level is used to seed its level. Saved dedicated values take priority
over global values; any missing fields inherit from the global configuration,
then from the plugin defaults.

## Disabled does not mean unconfigured

A disabled configuration keeps its manager and its `auto_start_stop_manager`
attributes. It reports `is_auto_start_stop_configured: true` and
`auto_start_stop_enable: false`, does not accumulate error, and requests no
automatic stop. A previously accumulated error can remain visible, frozen at its
last value. Disabling releases a detected stop, subject to the thermostat's other
controls.

Only dedicated entries create the two production-compatible controls:

- An **Enable auto start/stop** switch, which enables or disables detection
  without changing the saved stop mode.
- An independent **Auto start/stop stop mode** select:

| Option (service value) | Behavior |
|---|---|
| Off (`off`) | Use HVAC `off` for automatic stops |
| Fan only (`fan_only`) | Use ventilation for automatic stops |
| Dry (`dry`) | Use dehumidification for automatic stops |

`fan_only` and `dry` are offered only when supported by the thermostat. `heat`,
`cool` and `auto` are not stop modes. **Off does not disable auto start/stop.**
Selecting a stop mode never enables or disables detection. Use `switch.turn_on`
or `switch.turn_off` to change activation.

Both controls remain available when the dedicated configuration is disabled.
Saved configuration takes precedence over previously restored entity state
after a restart. Thermostats using only the global defaults have no dedicated
plugin controls; configure them through the global entry or create a dedicated
entry.

## Preserving existing controls and dashboards

Install the coordinated compatible core and plugin versions, then restart Home
Assistant. Before removing its old controls, the core saves their exact entity
IDs. A dedicated plugin entry reuses those IDs, including custom user names,
without changing the card or dashboard configuration. This also works when the
dedicated entry is created later, after global-only delegation. Legitimate core
controls must finish unloading before the plugin creates their replacements.

Existing plugin controls are reused rather than deleted. Later user renames are
preserved. An unrelated entity occupying a historical ID causes an explicit
configuration error: the plugin never takes it over or silently creates an `_2`
replacement. Resolve the conflict, then reload the dedicated configuration.

Upgrading from the experimental combined selector restores the switch and removes
the select's `disabled` option. Saved activation and stop mode are unchanged:
a disabled entry with `dry` saved stays disabled and retains `dry`. Automations
written specifically for that experimental option must use the switch instead.
Already-delegated test installations can recover old core IDs from retained
registry deletion history. A custom historical ID cannot be reconstructed if
neither that history nor the core's saved metadata remains available.

## Removing entries

- Removing a dedicated entry removes its switch and select and restores the global
  configuration on the next thermostat load. **This can re-enable the feature
  if the global defaults are enabled.**
- Removing the global entry leaves thermostats without dedicated entries
  unconfigured. Dedicated entries continue to work, using plugin defaults for
  any missing fields.
- With neither a global nor a dedicated entry, no plugin manager is attached.

## Migration from the core feature

The compatible Versatile Thermostat core delegates auto-start/stop to the plugin
and clears the legacy core feature flag. This also applies when the plugin
configuration is disabled, so the core feature does not run in its place.

When creating a dedicated entry, its level is seeded from the legacy thermostat
configuration if available. An existing dedicated entry is not overwritten.
Choose its enable state explicitly before saving. Removing the plugin does not
automatically re-enable the old core feature.
