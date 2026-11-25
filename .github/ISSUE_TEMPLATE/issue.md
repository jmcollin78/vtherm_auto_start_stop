---
name: Issue
about: Create a report to help us improve
---

# Read this carefully

I read carefully these instructions and filled this form before writing an issue. This will help the reader to help me.

<!-- If you choose to not follow this template, you accept to have no answer from the author. The tag 'Template not respected' on the issue means you don't respect this template. Potentially, you will not have a relevant answer.

This template will allow the maintainer to be efficient and post the most accurate response as possible. There are many types / modes / configurations possible, so the analysis can be very tricky. If you don't follow this template, your issue could be rejected without any message. Please help me to help you. -->

<!-- Before you open a new issue, search through the existing issues to see if others have had the same problem.

If you have a simple question or you are not sure this is an issue, don't open an issue but open a new discussion instead.

Check also the Troubleshooting section of the README if the answer is not already given.

Issues not containing the minimum requirements will be closed:

- Issues without a description (using the header is not good enough) will be closed.
- Issues that don't follow this template could be closed.
-->

## Version of the custom_component
<!-- If you are not using the newest version, download and try that before opening an issue.
If you are unsure about the version, open HACS, find the VTherm Auto Start/Stop integration and copy/paste the release.
-->

<!-- If it was working with a previous release -->
The issue was not present in previous release: <!-- give it if you know it -->

## Configuration

<!-- This project is a plugin for Versatile Thermostat. Copy / paste the attributes of the VTherm here. You can go to Development Tools / States, find and select your VTherm and copy/paste the attributes. Surround these attributes by a yaml formatting: ```yaml <put the attributes> .... ```
Without these attributes support is impossible due to the number of configuration attributes the VTherm has (more than 60). -->

<!-- Also paste the configuration of the VTherm Auto Start/Stop plugin (config entry / select entities), if relevant. -->

<!-- replace with yours -->
My VTherm attributes are the following:
```yaml
hvac_modes:
  - heat
  - 'off'
min_temp: 7
max_temp: 35
preset_modes:
  - none
  - eco
  - comfort
  - boost
  - activity
current_temperature: 18.9
temperature: 22
hvac_action: 'off'
preset_mode: security
hvac_mode: 'off'
type: null
eco_temp: 17
boost_temp: 20
comfort_temp: 19
eco_away_temp: 16.1
boost_away_temp: 16.3
comfort_away_temp: 16.2
power_temp: 13
ext_current_temperature: 11.6
ac_mode: false
current_power: 450
current_power_max: 910
saved_preset_mode: none
saved_target_temp: 22
window_state: 'on'
motion_state: 'off'
overpowering_state: false
presence_state: 'on'
window_auto_state: false
is_window_bypass: false
safety_delay_min: 2
safety_min_on_percent: 0.5
```

## Expected behavior / observed behavior

<!-- Describe what was expected and what actually happened. Include, if available, the related logs (Development Tools / Logs) with the VTherm Auto Start/Stop entities. -->
