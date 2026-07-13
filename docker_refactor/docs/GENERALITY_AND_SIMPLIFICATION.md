# Generality and Simplification Review

## Purpose

The Docker refactor intentionally contains more structure than the original
`pi_scripts` implementation. It supports configuration-driven services,
reproducible deployments, hardware-free tests, stable MQTT and Home Assistant
identities, and separation between hardware, Home Assistant, and SMS.

That generality is useful, but speculative flexibility should not be retained
when it makes the current system harder to understand. This document records
the clearest opportunities to simplify the design without returning to
hard-coded, service-specific scripts.

## Strong Simplification Candidates

### Remove unimplemented I2C support

`ServiceConfig` currently accepts `driver: i2c`, and `build_driver()` contains
an I2C branch that only raises `NotImplementedError`. This expands the apparent
configuration surface without providing working functionality.

Remove the option until an actual I2C-backed service is implemented. Add it
back alongside its driver, configuration fields, and tests when required.

### Simplified driver construction

Driver construction now uses a module-level `build_driver(name, config)`
function instead of a stateful factory class. The function validates the
selected service and passes explicit typed arguments to each driver.

The previous untyped driver-configuration dictionaries and common
`driver.config` attribute have been removed. The shared driver lifecycle remains
because serial and DHT11 drivers genuinely use the same runner. Hardware-free
room readings now use the existing serial driver instead of a separate fake
DHT11 implementation.

### Compute Home Assistant entity IDs on demand

`ReadingModel` and `ServiceModel` store many entity IDs derived from the same
service and reading names. Examples include alarm-state, danger-zone,
recovery-zone, sensor-fault, and threshold-helper entity IDs.

These values could be computed properties instead of constructor fields. The
naming convention is already fixed, so storing every derived value adds
construction code and creates opportunities for inconsistent IDs without
providing meaningful flexibility.

### Describe serial formats rather than services

The legacy serial parser selects parser branches using service-oriented names
such as `pump_room` and `water`, although both currently use the same labelled
value parser.

Parser choices should describe actual wire formats, for example:

- a single pressure value;
- labelled values;
- pipe-delimited values, if a real device still requires them.

Once Arduino output is standardized, most of this legacy parser layer should be
removed rather than preserved as compatibility machinery.

### Publish MQTT discovery from configured readings at startup

The Home Assistant publisher dynamically tracks which readings have received
discovery messages. However, it also rejects readings not declared in
`config.yaml`, so the complete valid reading set is already known.

A simpler lifecycle would publish discovery for every configured reading when
the MQTT connection starts, then publish values only for those readings. This
would intentionally give up dynamically appearing, unconfigured readings, which
the current validation policy does not support anyway.

## Generality Worth Keeping

The following structure already provides practical value and should not be
removed merely to reduce line count:

- one validated, typed configuration model;
- stable shared MQTT topics and Home Assistant entity naming;
- config-driven services and readings;
- the common driver lifecycle used by the hardware runner;
- one fake serial simulator for all hardware-free sensor testing;
- separation between hardware, Home Assistant generation, and SMS delivery;
- one SMS sender with dry-run and `mmcli` delivery paths;
- tests for parsing, reconnection, MQTT contracts, and generated configuration.

The SMS sender can remain one concrete class. It does not need a protocol,
subclass hierarchy, or backend registration system while `mmcli` is the only
planned production delivery mechanism.

## Recommended Order

1. Remove the non-functional I2C configuration and factory branch.
2. Convert derived Home Assistant IDs into model properties.
3. Consolidate serial parser names around real input formats.
4. Reassess dynamic MQTT discovery after confirming Home Assistant startup and
   reconnect behaviour.

Each change should preserve the existing external behaviour and be covered by
the relevant lightweight tests. The goal is not minimum line count; it is to
remove flexibility that has no current user while retaining configurability,
testability, and safe operation.
