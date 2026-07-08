# Home Assistant Threshold YAML

This folder contains a first YAML-based Home Assistant threshold setup for the
LabPulse air pressure sensor.

It creates:

- a dashboard-editable pressure threshold
- a dashboard-editable alert delay
- a dashboard-editable recovery delay
- an alert-state toggle
- one alert automation
- one recovery automation
- a dashboard card snippet

## Files

- `input_numbers.yaml`: threshold and delay helpers
- `input_booleans.yaml`: alert-state helper
- `automations.yaml`: alert and recovery automations
- `dashboard_card.yaml`: optional dashboard card snippet
- `configuration_includes.yaml`: the include lines for `configuration.yaml`

## Install On The Raspberry Pi

Home Assistant is mounted at:

```text
~/labpulse-ha/homeassistant/config
```

Copy these files into that folder:

```text
input_numbers.yaml
input_booleans.yaml
automations.yaml
```

Then edit:

```text
~/labpulse-ha/homeassistant/config/configuration.yaml
```

Add these lines if they are not already present:

```yaml
input_number: !include input_numbers.yaml
input_boolean: !include input_booleans.yaml
automation: !include automations.yaml
```

If `configuration.yaml` already has `automation: !include automations.yaml`, do
not add a second `automation:` line. Append the contents of this folder's
`automations.yaml` to the existing Home Assistant `automations.yaml` instead.

## Dashboard

To add the controls to a dashboard:

1. Open the dashboard.
2. Choose edit mode.
3. Add a manual card.
4. Paste the contents of `dashboard_card.yaml`.

## Reload

After copying the YAML:

1. In Home Assistant, go to **Developer Tools -> YAML**.
2. Run **Check configuration**.
3. Restart Home Assistant so the new helpers are loaded.

Automation-only changes can usually be reloaded without a full restart, but new
`input_number` and `input_boolean` helpers normally need a restart.
