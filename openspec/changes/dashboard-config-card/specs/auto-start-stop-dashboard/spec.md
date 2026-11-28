# Spec Delta

## Purpose

Defines how the auto-start-stop plugin presents itself inside VTherm Dashboard: the conditions under which it registers a configuration card and a summary widget, how it keeps working when the dashboard is absent, when its contributions are shown, and how the card edits the five per-thermostat controls while the widget reports the derived level read-only.

## ADDED Requirements

### Requirement: Plugin works without VTherm Dashboard

The plugin SHALL remain fully functional when VTherm Dashboard is not installed. VTherm Dashboard SHALL be declared as an optional startup-order dependency, never as a required dependency, and its absence SHALL NOT raise an error, log a warning, or prevent any entity from being created.

#### Scenario: Dashboard absent at startup

- **WHEN** the plugin starts up while VTherm Dashboard is not installed
- **THEN** the plugin loads successfully and publishes its five thermostat controls as usual

#### Scenario: No failure surfaces from the missing dashboard

- **WHEN** VTherm Dashboard is absent and the user inspects the plugin's log
- **THEN** no error or warning about the missing dashboard is recorded

#### Scenario: Dashboard installed after the plugin

- **WHEN** VTherm Dashboard is installed while the plugin is already loaded
- **THEN** the plugin contributes no card and no widget until it is reloaded, and its entities keep working

### Requirement: UI plugin registration is conditional

The plugin SHALL register its JavaScript module with the dashboard API only when VTherm Dashboard is present in the running Home Assistant instance. The registration SHALL declare a supported dashboard version range and SHALL serve the module from a local static path owned by the plugin.

#### Scenario: Registration happens when the dashboard is loaded

- **WHEN** the plugin starts up and VTherm Dashboard is loaded
- **THEN** the plugin registers its UI module with a dashboard version constraint and exposes the module at a local static path

#### Scenario: Registration is skipped when the dashboard is absent

- **WHEN** the plugin starts up and VTherm Dashboard is not loaded
- **THEN** the plugin performs no UI registration and no static path is required

### Requirement: Contributions are visible when the thermostat is covered

The plugin's card and widget SHALL be shown for a thermostat exactly when that thermostat is covered by the plugin, which is observable as the presence of the plugin's five control entities on the thermostat's device. Coverage SHALL NOT depend on the user having changed any value, so a thermostat covered only by default configuration still shows both contributions.

#### Scenario: Covered thermostat shows the card

- **WHEN** a thermostat is covered by the plugin and the user opens its configuration menu in the dashboard
- **THEN** the plugin's card is listed and selectable

#### Scenario: Uncovered thermostat shows nothing

- **WHEN** a thermostat is not covered by the plugin
- **THEN** neither the card nor the widget is listed for that thermostat

#### Scenario: Default configuration is enough

- **WHEN** a thermostat is covered through the default configuration and the user has never edited any control
- **THEN** the card and the widget are shown all the same

### Requirement: Section status reports configuration completeness

The card SHALL expose a status used by the dashboard menu. The status SHALL be `off` when the enable switch is off, `complete` when the enable switch is on and both custom parameters hold a readable value, and `incomplete` carrying the count of missing parameters otherwise. The plugin SHALL NOT report an inherited status.

#### Scenario: Feature disabled

- **WHEN** the thermostat's enable control is off
- **THEN** the card reports the `off` status

#### Scenario: Fully configured

- **WHEN** the enable control is on and both the minimum duration and the error threshold are readable
- **THEN** the card reports the `complete` status

#### Scenario: Parameters missing

- **WHEN** the enable control is on but one of the two numeric controls has no readable value
- **THEN** the card reports the `incomplete` status carrying the number of missing parameters

### Requirement: Card edits controls immediately

Each control of the card SHALL write its value to the matching entity as soon as the user changes it, without any save step and without a draft. The card SHALL NOT rely on the dashboard to persist values, and SHALL display the error returned by a rejected write.

#### Scenario: Changing a control writes at once

- **WHEN** the user changes the stop mode in the card
- **THEN** the corresponding Home Assistant service call is issued immediately and the entity state reflects the new value

#### Scenario: A rejected write is reported in the card

- **WHEN** the user picks a value the plugin refuses
- **THEN** the card shows the returned message next to the control and the entity keeps its previous value

#### Scenario: Card declares no dashboard save action

- **WHEN** the dashboard renders the card
- **THEN** no dashboard save or discard footer is shown for it, because the card manages its own writes

### Requirement: Custom level selection leaves a named level unchanged

The level control SHALL offer all five level values. Selecting the custom level while the current level is a named level SHALL NOT modify any parameter, and the control SHALL display the unchanged derived level afterwards.

#### Scenario: Selecting custom on a named level

- **WHEN** the current level is a named level and the user selects the custom level
- **THEN** both custom parameters keep their values and the control shows the same named level as before

#### Scenario: Custom selected when already custom

- **WHEN** the current level is already the custom level and the user selects it again
- **THEN** nothing changes and no error is displayed

### Requirement: Widget reports the derived level read-only

The plugin SHALL provide a summary widget showing the detection state, the accumulated error against its threshold, the age of the last switch, and the derived level. The widget SHALL read only attributes published by the covered thermostat and SHALL NOT call any service.

#### Scenario: Widget shows the summary

- **WHEN** a covered thermostat has detection data available and the dashboard displays the widget
- **THEN** the widget shows the detection state, the accumulated error and threshold, the last switch age, and the derived level

#### Scenario: Feature disabled hides the widget

- **WHEN** the thermostat's enable control is off
- **THEN** the widget is not shown

#### Scenario: No source entity hides the widget

- **WHEN** the covered thermostat publishes no detection data
- **THEN** the widget is not shown rather than displaying invented values

### Requirement: Contribution text comes from the plugin

Every user-facing text of the card and the widget SHALL be provided by the plugin, with an English catalog as the mandatory base and a French catalog alongside it. The language SHALL follow the one selected in the dashboard.

#### Scenario: French dashboard

- **WHEN** the dashboard runs in French
- **THEN** the card and the widget render their labels and messages from the French catalog

#### Scenario: Unknown language falls back to English

- **WHEN** the dashboard language has no matching plugin catalog
- **THEN** the card and the widget render their text from the English catalog
