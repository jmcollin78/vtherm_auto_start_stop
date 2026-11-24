# vtherm_auto_start_stop
A plugin for Versatile Thermostat aiming to start and stop automatically your climate device

## Supported thermostats

Only `over_climate` thermostats without valve regulation are supported.
Dedicated configurations and exclusions accept the published `configuration.type`
value `over_climate` as well as the stored type `thermostat_over_climate`.
When state attributes are not yet available, eligibility is checked against the
thermostat's core configuration entry.
