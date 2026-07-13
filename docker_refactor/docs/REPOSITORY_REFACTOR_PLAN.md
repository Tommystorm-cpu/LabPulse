# Repository Refactor Plan

Status: implemented on 10 July 2026. The package layout, shared contracts,
module entry points, tests, deployment generators, and documentation described
below are now the current repository structure.

## Objective

Reorganise `docker_refactor/` around three clear responsibilities without
changing LabPulse's externally visible behaviour:

- **hardware** reads physical devices, normalises readings, and publishes them
  to MQTT/Home Assistant discovery;
- **homeassistant** generates Home Assistant configuration, dashboards, and
  alarm/automation logic from the LabPulse configuration;
- **sms** subscribes to Home Assistant alert requests over MQTT and delivers
  SMS messages.

The refactor is structural. It must not add new hardware drivers, redesign
alarm behaviour, or change Arduino serial formats.

## Ownership

```text
hardware source -> driver -> normalised readings -> MQTT publisher

config.yaml -> Home Assistant render model -> dashboards, helpers, alarms

Home Assistant alert automation -> MQTT SMS request -> SMS sender backend
```

The MQTT publisher belongs to the hardware runtime. It is the final stage that
hands physical readings to Home Assistant; it is not part of Home Assistant
dashboard or automation generation.

Legacy Arduino parsers are temporary implementation details of serial drivers.
They must be isolated so future standardised Arduino output can replace them
without changing the driver contract, MQTT publisher, Home Assistant generator,
or SMS service.

## Target Layout

```text
docker_refactor/
  labpulse_common/
    config.py                 validated shared configuration models/loading
    identity.py               stable IDs, slugs, expected entity IDs
    logging_config.py         Docker-friendly logging
    mqtt_contracts.py         shared MQTT topic and alert-payload contracts

  labpulse_hardware/
    __main__.py               executable package adapter
    cli.py                    one configured hardware service process
    drivers/
      base.py
      factory.py
      serial_driver.py
    legacy_parsing/
      serial_parser.py        temporary Arduino text compatibility layer
    homeassistant_publisher.py

  labpulse_homeassistant/
    __main__.py
    cli.py
    data_models.py            Home Assistant-specific render model
    alarm.py
    dashboard.py
    write_yaml.py
    template_utils.py
    templates/

  labpulse_sms/
    __main__.py
    cli.py
    sms_subscriber.py
    sender.py

  testing/
  docs/
  setup_container_fs.sh
  generate_compose.sh
  generate_homeassistant_config.sh
```

Use `python -m labpulse_hardware --service <service>` as the hardware
container command. Update the Dockerfile, Compose generator, setup script, and
tests accordingly; do not retain the old top-level `main.py` solely for
compatibility.

## Shared Components

### Validated configuration

`labpulse_common.config` is the single reader and validator of `config.yaml`.
Hardware, Home Assistant generation, and SMS must all consume its typed
`LabPulseConfig` model. Remove Home Assistant's independent raw YAML loading.

Home Assistant render-model construction may transform the validated model into
Home Assistant-specific data, but must not independently interpret missing
services, readings, labels, or display metadata.

### Stable identity

Move slugging and stable ID/entity-ID derivation into
`labpulse_common.identity`. Hardware MQTT discovery and Home Assistant
generation must use the same helpers to derive:

- MQTT `unique_id` and `object_id`;
- default Home Assistant entity ID;
- generated alarm entity IDs;
- generated threshold/helper IDs.

Labels remain user-facing metadata and must not affect stable IDs.

### MQTT contracts

Keep Home Assistant discovery/state publishing in
`labpulse_hardware.homeassistant_publisher`. Keep shared topic constants and
cross-service message contracts in `labpulse_common.mqtt_contracts`.

The Home Assistant alarm templates and SMS subscriber must share the SMS topic
and documented alert JSON schema. The payload continues to carry the current
event, service, reading, entity ID, title, message, current value, and
threshold context.

### Runtime logging

Keep logging configuration shared and neutral. Hardware and SMS runtime
entrypoints configure it; the Home Assistant generator may remain a short-lived
command-line renderer unless structured logging is useful there.

## Hardware Contract

Every driver presents the same interface to `labpulse_hardware/cli.py`:

```text
setup() -> bool
read() -> dict[str, float]
get_status() -> str
disconnect() -> None
```

The runner owns the loop, service status publishing, and calls to the Home
Assistant MQTT publisher. Drivers never import Home Assistant or SMS code.

`legacy_parsing.serial_parser` is used only by legacy serial drivers. A future
driver for standardised Arduino output may decode readings directly and return
the same mapping.

## Behaviour That Must Be Preserved

- The live Pi configuration remains `~/labpulse-ha/config.yaml`.
- Existing `config.yaml` keys and defaults remain valid.
- Existing Docker Compose service/container names remain unchanged.
- MQTT discovery topics, state topics, retained discovery behaviour, payload
  keys, stable IDs, and Home Assistant entity IDs remain unchanged.
- Home Assistant generated dashboard, helper, alarm, and automation behaviour
  remains unchanged.
- SMS continues to subscribe to the same alert topic and accept the same JSON
  request payload.
- The setup script still refreshes copied Python packages without overwriting a
  live user-edited config or Home Assistant dashboard.

## Implementation Sequence

1. Add shared identity and MQTT-contract modules with tests proving they
   reproduce the current IDs, topics, and alert payload contract.
2. Convert Home Assistant generation to receive validated `LabPulseConfig` and
   remove its duplicate YAML interpretation.
3. Move the hardware runner, drivers, factory, and legacy parser into
   `labpulse_hardware`; move the MQTT discovery/state publisher with them.
4. Update imports, Docker commands, Compose generation, setup copying, and all
   test paths for the new layout.
5. Update the SMS service to consume the shared MQTT contract where applicable.
6. Update architecture, setup, runtime, and code-reading documentation.
7. Remove obsolete files and imports once no code, script, test, or document
   references them.

## Verification

Before completing the refactor:

1. Run the existing parser, sensor-factory, serial-driver, MQTT publisher,
   Home Assistant generator/entity, and SMS tests.
2. Add or update tests that compare representative discovery payloads, entity
   IDs, generated alarm references, and SMS topic/payloads before and after the
   move.
3. Run `docker compose config` against generated Compose output.
4. Run the fake-USB happy path and confirm readings, Home Assistant discovery,
   generated alarms, and SMS test-backend messages still work.
5. Confirm `setup_container_fs.sh` refreshes runtime code while preserving an
   existing live config and dashboard.

## Acceptance Criteria

The refactor is complete when folder ownership matches the target layout,
there is one validated configuration path and one stable-identity path, legacy
parsing is isolated behind the driver contract, and all existing external
runtime behaviour and tests are preserved.
