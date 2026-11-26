<p align="center">
  <img src="custom_components/vtherm_auto_start_stop/brand/icon.png" alt="VTherm Auto Start/Stop" width="256" height="256">
</p>

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)
[![HACS][hacs_badge]][hacs]
[![BuyMeCoffee][buymecoffeebadge]][buymecoffee]

# 🌡️ VTherm Auto Start/Stop

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
- **You stay in control** — each thermostat gets an *auto-start/stop enable*
  switch, an *auto-start/stop stop mode* select, an *auto-start/stop detection
  level* select and two parameter numbers, right in the dashboard. The unchanged
  VTherm UI card operates them exactly as before.
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

> The level is a **preset label derived from the two values**, not a stored
> setting. Two entities per thermostat carry the parameters: **auto-start/stop
> minimum duration before stop** (5 → 120 minutes) and **auto-start/stop
> threshold** (1 → 50, step 0.5).
> Selecting a named level writes both values in one go; writing one value
> yourself reclassifies the level as *Custom* when it no longer matches a named
> pair. The level select simply reflects that pair — it never holds the truth.

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

- **Initial enable** and **initial stop mode** — seeds used
  **only** while a thermostat's controls have no saved state yet (a brand-new
  thermostat). Once a control has a saved state, editing these seeds never
  resets it, even if you never touched it by hand.

The detection level is not part of that form: it is derived from the two
parameter entities. A brand-new thermostat starts at the default level and,
when migrating, is seeded once from the legacy core level.

Every eligible thermostat automatically receives its own set of controls, all
prefixed with **auto-start/stop** so they are grouped and sorted together in the
interface:

- **auto-start/stop enable** (switch) — turns detection on or off for that
  thermostat only, without touching its saved stop mode.
- **auto-start/stop stop mode** (select) — which HVAC mode to apply when the
  plugin requests a stop.
- **auto-start/stop detection level** (select) — a *preset* that reads the level
  derived from the two parameter entities; selecting a named level writes both
  parameters at once.
- **auto-start/stop minimum duration before stop** and **auto-start/stop
  threshold** (numbers) — the two detection parameters themselves, editable
  directly and per thermostat.

| Stop mode | Behaviour on an automatic stop     | Availability |
| --------- | ---------------------------------- | ------------ |
| Off `off` | The device is switched off         | Always       |
| Fan only  | The device switches to ventilation | If supported |
| Dry       | The device switches to dehumidify  | If supported |

> **`Off` is a stop mode, not a way to disable the feature.** Disabling or
> enabling detection is the switch's only job; choosing `Off` only says *how*
> the device is stopped. Selecting a stop mode never enables or disables
> detection.

All of these states survive reloads and restarts, independently of any
configuration entry. Writing a parameter never creates a configuration entry,
never writes the global settings, and **never reloads a thermostat**: the
attached manager picks the new value up immediately. Changing a parameter also
leaves the accumulated score intact — the score measures an observed gap, while
the parameters are the criteria applied to it.

### 🎛️ Per-thermostat parameters (optional dedicated entries)

Detection parameters are already per-thermostat: every covered thermostat has its
own **auto-start/stop minimum duration before stop**, **auto-start/stop
threshold** and **auto-start/stop detection level** entities. A
dedicated configuration entry is therefore optional; it only changes the
**coverage** and the **initial seeds** of a single thermostat — it is never
required to enable a room or to adjust a parameter.

### 🗑️ Removing entries

- Removing a **dedicated** entry only drops its coverage and its seeds; the
  thermostat's controls and their saved states are untouched while the global
  entry still covers it.
- Removing the **global** entry removes the controls of every thermostat that
  has no dedicated entry of its own; thermostats with a dedicated entry keep
  their controls.

## 🔄 Migrating from the core feature

If your thermostats already used the built-in auto start/stop:

- With the coordinated core and plugin versions installed, a reload hands the
  feature over to the plugin: the core clears its legacy feature flag, removes
  the old switch and select, and the plugin recreates the controls **under their
  exact previous entity IDs** — dashboards, cards and automations keep working
  unchanged.
- When a thermostat becomes covered, its level is **seeded from the legacy core
  level** when available; an existing restored parameter state is never
  overwritten. The seed is read once, when a control has no saved state.
- Removing the plugin does **not** silently re-enable the old core feature —
  re-enable it through Versatile Thermostat if you want it back.

## ❓ Frequently asked questions

**I disabled the feature on a thermostat — why do the controls and attributes
still show up?**
Disabling is a saved state, not an uninstall: the thermostat keeps its (frozen)
accumulated score, its stop mode, its level and its two parameters, so
re-enabling is immediate. While disabled, detection does not accumulate and
requests no stop.

**Why did my custom values disappear when I picked a named level?**
A named level is a preset: choosing it writes both parameters to that level's
pair. Going back to *Custom* does not restore the previous values — there is no
hidden copy of them. Set the two numbers again to get your values back.

**I edited the stop mode in the configuration entry — why did the thermostat not
change?**
The entry only supplies a **seed**, read when a control has no saved state. A
covered thermostat keeps its own control entities; edit that thermostat's
**auto-start/stop stop mode** select (or call the numbers through a service) to
change a running thermostat.

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

[commits]: https://github.com/jmcollin78/vtherm_auto_start_stop/commits/main
[commits-shield]: https://img.shields.io/github/commit-activity/m/jmcollin78/vtherm_auto_start_stop.svg?style=flat-square
[releases]: https://github.com/jmcollin78/vtherm_auto_start_stop/releases
[releases-shield]: https://img.shields.io/github/release/jmcollin78/vtherm_auto_start_stop.svg?style=flat-square
[license-shield]: https://img.shields.io/github/license/jmcollin78/vtherm_auto_start_stop.svg?style=flat-square
[hacs]: https://hacs.xyz/
[hacs_badge]: https://img.shields.io/badge/HACS-Default-orange.svg?style=flat-square
[buymecoffee]: https://www.buymeacoffee.com/jmcollin78
[buymecoffeebadge]: https://img.shields.io/badge/Buy%20Me%20A%20Coffee-FFDD00?style=flat-square&logo=buy-me-a-coffee&logoColor=black
