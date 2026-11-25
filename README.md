<p align="left">
  <img src="custom_components/vtherm_auto_start_stop/brand/icon.png" alt="VTherm Auto Start/Stop" width="256" height="256">
</p>

# VTherm Auto Start/Stop

**[English](README.md) · [Français](README-fr.md)** · [Contributors (EN)](CONTRIBUTING.md) · [Contributeurs (FR)](CONTRIBUTING-fr.md)

A plugin for [Versatile Thermostat](https://github.com/jmcollin78/versatile_thermostat)
that automatically stops your climate device once the room has reached its target
temperature, and lets Versatile Thermostat resume it normally when the temperature
drifts away again.

## 🎯 What is it for?

Your climate device (heat pump, heater, cooling system…) keeps running until the
Versatile Thermostat logic decides otherwise — even when the room is already at the
setpoint. This plugin watches the temperature and **stops the device when it has
arrived**, then lets Versatile Thermostat bring it back up normally when the room
drifts from the target again.

- **Saves energy** — every automatic stop avoids useless minutes of compressor or
  boiler work.
- **Fully automatic** — no button to press: the plugin requests the stop itself.
- **You stay in control** — each thermostat gets an *Enable auto start/stop* switch
  and a *Stop mode* select, right in the dashboard. The unchanged VTherm UI card
  operates them exactly as before.
- **One global configuration** covers all of your thermostats; per-thermostat
  parameter overrides are optional and never needed merely to enable a room.
- **Standalone** — auto start/stop runs entirely as this plugin, with the
  Versatile Thermostat logic left untouched.

## 🔍 How does the detection work? (in plain words)

Regularly, the plugin takes a measurement and asks one question:
**"How far is the room from the target, and for how long has it stayed there?"**

1. **The deviation** — the current temperature is compared to the target. If the
   room is still 2 °C below the target, the deviation is 2 °C.
2. **The score** — since the last measurement, that deviation is multiplied by the
   elapsed time and added to a running **score** (the *accumulated error*). A
   deviation that persists builds up the score; one that disappears does not
   grow it.
3. **The verdict** — the device is asked to stop when the score exceeds a
   **threshold** *and* the temperature, projected with its current trend
   (plus a 0.5 °C safety margin), has already crossed the target.
4. **Releasing the stop** — when the error changes sign (the room starts moving
   the other way), the score is halved rather than reset, so a short wobble does
   not restart the whole detection.
5. **Your commands win** — changing the preset or the target temperature resets
   the score immediately: you explicitly asked for something new, so a leftover
   detection can never hold the previous decision.

How fast a stop is detected is set by the **level**: a level fixes the
**minimum duration** (`dt_min`, how long the deviation must persist before any
verdict) and the **score threshold** it must cross.

| Level          | `dt_min` (minutes) | Score threshold | Character          |
| -------------- | ------------------ | --------------- | ------------------ |
| Very slow      | 60                 | 20              | Stops rarely, late |
| Slow (default) | 30                 | 10              | Balanced           |
| Medium         | 15                 | 5               | Moderate           |
| Fast           | 7                  | 2               | Stops quickly      |
| Custom         | 5 → 120            | 1 → 50          | You choose both    |

The default level is **Slow (30 / 10)**, the behaviour the core feature had.

> With the **Custom** level you set both values yourself: a minimum duration
> between **5 and 120 minutes** and a threshold between **1 and 50** (step 0.5).
> The two fields are always shown in the configuration form, whatever the
> current level. They are only applied when the level is *Custom* — with a named
> level the static table is used instead — and the values are saved in the entry
> so you do not have to re-enter them when you switch back to *Custom*.

## 📋 Supported thermostats

- Only **`over_climate`** thermostats (a Versatile Thermostat driving a
  climate device) are eligible.
- **Valve-regulated thermostats are not supported** — the same restriction the
  core feature had, kept on purpose so the migration is a pure handover.

## 📦 Installation

**Prerequisites**

- Home Assistant **2026.10** or later.
- Versatile Thermostat **11.x or later**, with **external auto start/stop
  delegation** support.

**Option A — HACS**

1. In HACS, add this repository as a custom integration (via the *Marketplace* or
   a manual download of the repository).
2. Restart Home Assistant.
3. Go to **Settings → Devices & services** and add **VTherm Auto Start/Stop**.

**Option B — Manual**

1. Copy the `custom_components/vtherm_auto_start_stop` folder into your
   Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.
3. Go to **Settings → Devices & services** and add **VTherm Auto Start/Stop**.

## ⚙️ Configuration

### 🌍 The global configuration (the only mandatory one)

The first time you add the integration, you configure the **global settings**:

- **Level** — the detection level applied to every thermostat (table above).
- **Initial enable** and **initial stop mode** — defaults used **only** while a
  thermostat's controls have no saved state yet (a brand-new thermostat). Once a
  control has a saved state, editing these defaults never resets it, even if you
  never touched it by hand.

Every eligible thermostat automatically receives its own pair of controls:

- **Enable auto start/stop** (switch) — turns detection on or off for that
  thermostat only, without touching its saved stop mode.
- **Stop mode** (select) — which HVAC mode to apply when the plugin requests a
  stop:

| Option    | Behaviour on an automatic stop     | Availability |
| --------- | ---------------------------------- | ------------ |
| Off `off` | The device is switched off         | Always       |
| Fan only  | The device switches to ventilation | If supported |
| Dry       | The device switches to dehumidify  | If supported |

> **`Off` is a stop mode, not a way to disable the feature.** Disabling or
> enabling detection is the switch's only job; choosing `Off` only says *how*
> the device is stopped. Selecting a stop mode never enables or disables
> detection.

All of these states survive reloads and restarts. Changing a control never
creates a configuration entry and never modifies the global settings.

### 🎛️ Per-thermostat parameters (optional dedicated entries)

If one thermostat needs different **detection parameters** — say a slow room
that should not stop quickly — add another configuration entry:

1. Add **VTherm Auto Start/Stop** again from *Devices & services*.
2. Select the thermostat.
3. Choose its level (and its Custom values, if needed).

Dedicated entries change **parameters only**: activation and stop mode always
stay on the entity controls (no dedicated entry is ever needed for those).
Parameters you do not set in the dedicated entry inherit from the global entry,
then from the plugin defaults.

### 🗑️ Removing entries

- Removing a **dedicated** entry restores parameter inheritance; the
  thermostat's controls, activation and stop mode are untouched.
- Removing the **global** entry removes the controls of every thermostat that
  has no dedicated entry of its own; thermostats that do keep working, with
  missing parameters falling back to the plugin defaults.

## 🔄 Migrating from the core feature

If your thermostats already used the built-in auto start/stop:

- With the coordinated core and plugin versions installed, a reload hands the
  feature over to the plugin: the core clears its legacy feature flag, removes
  the old switch and select, and the plugin recreates the controls **under their
  exact previous entity IDs** — dashboards, cards and automations keep working
  unchanged.
- When you create a dedicated entry, its level is **seeded from the legacy core
  level** when available; an existing dedicated entry is never overwritten.
- Removing the plugin does **not** silently re-enable the old core feature —
  re-enable it through Versatile Thermostat if you want it back.

## ❓ Frequently asked questions

**I disabled the feature on a thermostat — why do the controls and attributes
still show up?**
Disabling is a saved state, not an uninstall: the thermostat keeps its (frozen)
accumulated score, its stop mode and both controls, so re-enabling is immediate.
While disabled, detection does not accumulate and requests no stop.

**Can I enable the feature for only one thermostat?**
Yes — configure the global settings with *initial enable* off, then flip the
switch only on the thermostat(s) you want. No extra configuration entry is
created.

**My valve-regulated thermostat is not offered in the selector.**
That is intentional: valve-regulated `over_climate` thermostats stay excluded,
exactly as with the core feature.

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) / [CONTRIBUTING-fr.md](CONTRIBUTING-fr.md)
for the design, the mandatory OpenSpec workflow and the interactions with the
Versatile Thermostat core.

> **Note:** This plugin replaces the equivalent auto start/stop feature of the
> Versatile Thermostat core, which will be **completely removed in 2027**.
