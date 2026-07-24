# Home Assistant and alarms

LabPulse generates a native YAML-mode Home Assistant dashboard and alarm
package. No HACS cards, custom frontend resources, JavaScript, card-mod, or
private `.storage` mutation are required.

Home Assistant alarm states and notifications are best-effort monitoring aids.
Their absence does not establish that conditions are safe, and they must not
replace independent protective alarms or interlocks. See
[Product scope and safety boundary](PRODUCT_SCOPE.md).

## First connection

Open:

```text
http://<pi-address>:8123
```

Create the first Home Assistant account and add the MQTT integration:

```text
Settings → Devices & services → Add integration → MQTT
Broker: 127.0.0.1
Port: 1883
```

Home Assistant uses host networking. LabPulse sensor and SMS containers use
`mosquitto:1883` on the Compose network.

## Generated files

LabPulse owns:

```text
homeassistant/config/configuration.yaml
homeassistant/config/packages/labpulse_generated.yaml
homeassistant/config/labpulse-dashboard.yaml
```

Generation also creates empty `automations.yaml`, `scripts.yaml`, and
`scenes.yaml` when they do not exist.

Do not make permanent UI edits to the LabPulse YAML dashboard and do not
hand-edit the generated package. Change:

- sensors, setups, labels, subcategories, units, and icons in live
  `config.yaml`;
- dashboard layout rules in `src/labpulse/homeassistant/dashboard/`;
- alarm-generation behavior in the Home Assistant generator and templates.

Apply ordinary changes with:

```bash
labpulse config
```

## Dashboard views

### Monitor

Monitor is the main operator view. It projects measurements into logical
setups, shows alarm state, and includes prominent banners when global
notifications are muted or Test mode is active.

A measurement assigned to more than one setup appears in each relevant
presentation group but remains one physical MQTT entity and one alarm.

Dedicated power monitoring is displayed separately from experimental setup
membership.

### Alarm Setup

Alarm Setup provides:

- global notification mute;
- Test mode;
- a phone-book notification test;
- links and mute state for each logical setup;
- selective bulk alarm timing and deadband editing;
- per-measurement alarm modes, thresholds, timing, deadband, and mute controls;
- dedicated power alarm controls.

### Diagnostics

Diagnostics is organized by physical sensor service. It shows service status
and the measurements produced by that hub, which helps distinguish a complete
device failure from an individual measurement alarm.

## Measurement discovery and identity

Hardware services publish retained MQTT discovery and service health. A
measurement is discovered after its first valid sample.

Stable identity comes from:

```text
service key + measurement name
```

Changing a label is safe. Renaming a service key or measurement creates a new
entity, alarm-helper set, topic, and history.

LabPulse publishes the exact configured unit and an explicit icon but does not
publish Home Assistant's convertible sensor `device_class`. Home Assistant
therefore leaves Celsius, Fahrenheit, bar, psi, and other units unchanged.

## Measurement alarm model

Each ordinary measurement has a persistent state:

- `Normal`
- `Danger`
- `Sensor Fault`

The alarm mode controls threshold interpretation:

- `Disabled`
- `Low Only`
- `High Only`
- `Range`

Alarm calculation uses:

- minimum and/or maximum threshold;
- observation-window duration;
- required percentage of that window spent in danger;
- required continuous recovery duration;
- recovery deadband.

Default timing for a newly initialized measurement is:

```text
Required danger:     70%
Observation window:  120 seconds
Required recovery:   120 seconds
```

Threshold defaults and ranges are derived from measurement metadata. Review all
thresholds before unmuting a new installation.

### Entering Danger

The current value first enters the configured danger zone. Home Assistant's
`history_stats` sensor then measures the percentage of the observation window
spent in that zone. The alarm becomes `Danger` only when it reaches the
required percentage.

### Recovering

Recovery requires the value to remain inside a safer recovery boundary for the
configured recovery duration. The deadband moves that boundary away from the
alarm threshold to prevent repeated transitions caused by noisy values.

### Sensor Fault

MQTT discovery uses `expire_after` based on
`maximum_measurement_age_seconds`. A repeatedly published unchanged value stays
healthy; a value becomes unavailable only when valid samples stop.

An unavailable or non-numeric individual value can become Sensor Fault. When
the complete service is unhealthy, Home Assistant uses the hub-level
service-fault lifecycle instead of sending one stale warning for every
measurement.

## Service health

Hardware services publish states such as:

```text
online
disconnected
reconnecting
error
offline
```

Home Assistant confirms whole-service failure and recovery using
`service_health.fault_confirm_seconds` and
`service_health.recovery_confirm_seconds`.

A confirmed failure creates one hub-level notification and SMS request. On
recovery, Home Assistant reports restored communication and downtime.

## Notification safety

Alarm state and notification delivery are deliberately separate. Muting never
stops measurements or alarm calculation.

Delivery can be suppressed at three levels:

1. global mute;
2. logical setup mute;
3. individual measurement mute.

Power alerts have their own mute control. Setup mute does not apply to
dedicated power monitoring.

On the first installation, global notifications start muted. Home Assistant
then restores the operator's global mute choice across ordinary restarts.

Test mode starts enabled after every Home Assistant startup. Test notifications
are prefixed `[TEST]` and route only to `sms.test_recipients`. Operators must
deliberately turn Test mode off before normal recipients can receive alerts.

Turning global mute on or off does not overwrite setup or measurement mute
choices.

## Power alarm model

A configured power service has states:

- `Normal`
- `On Battery`
- `Sensor Fault`

The X1200 driver publishes battery voltage, battery level, and direct
external-power GPIO state. Battery values are context; the GPIO state is the
outage signal.

Home Assistant:

- confirms loss for `outage_confirm_seconds`;
- records outage start and active state;
- confirms restoration for `restore_confirm_seconds`;
- records the last outage duration;
- restores the persistent lifecycle across restarts;
- treats an unreadable power GPIO as Sensor Fault, not as an outage.

Whole-hub failure still uses the service-health lifecycle.

## Regeneration and restarts

`labpulse config` performs generation and Home Assistant's configuration check
before recreating services.

After direct generator use:

```bash
cd ~/labpulse-live
./generate_homeassistant_config.sh
labpulse restart homeassistant
```

Refresh the browser after Home Assistant has restarted.

## Backups

The generated dashboard and package can be recreated from current code and
configuration. Home Assistant accounts, integrations, recorder history, and
private state cannot. Back up the complete
`~/labpulse-live/homeassistant/config/` directory according to the deployment's
recovery policy.
