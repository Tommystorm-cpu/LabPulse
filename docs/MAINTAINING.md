# Your first day maintaining LabPulse

You don't need to understand the whole project before making a useful change.
Start by running the tests and generating a small dashboard, then follow one
reading through the code. This guide assumes you know a little Python and Git
but haven't worked on LabPulse before.

If the product itself is new to you, read
[What you're installing](FIRST_STEPS.md#what-youre-installing) first. Keep the
[Development guide](DEVELOPMENT.md) nearby as a reference; you don't need to
read it all before starting.

By the end of this guide, you should have a working checkout, a generated
dashboard you can inspect, and one small change whose route through the code
you understand. The first three sections run on your own computer. The live
debugging recipes in section 4 need a separate Linux development installation.

## 1. Get a working checkout

For this first session you need Git and Python 3.11 or 3.12. You don't need a
Pi, Docker, sensors, or a modem. Work on your own computer, not in a running
lab's installation directory.

Clone the repository with its history so the version can be calculated from
Git tags:

```bash
git clone https://github.com/lairdgrouplancaster/LabPulse.git
cd LabPulse
git switch -c codex/first-maintainer-change
```

Create a Python virtual environment. It keeps this checkout's dependencies
separate from other projects. **On Linux or macOS**:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

**In Windows PowerShell**:

```powershell
py -3.12 -m venv .venv
.venv/Scripts/Activate.ps1
```

Use 3.11 instead if that's the supported version you have installed. If
PowerShell blocks activation, you can use `.venv/Scripts/python.exe` in place
of `python` in the commands below without activating it.

Then, on either platform:

```bash
python -m pip install --editable ".[dev]"
python -m labpulse.control --help
python -m pytest -q
```

An **editable install** uses the Python files in your checkout. A source edit
is picked up the next time you run that code. Reinstall after changing
dependencies, entry points, or packaging settings in `pyproject.toml`.

You should get the command's help text and a passing test run. Read any skip
reasons in the test summary; a skipped test hasn't checked anything. The
[testing section below](#5-know-what-your-tests-prove) explains the limits.

### Generate something you can inspect

From the repository root, run this as one line in either shell:

```bash
python -m labpulse.deployment --config docs/examples/minimal-serial.yaml --project-dir testing/tmp/maintainer-demo --output testing/tmp/maintainer-demo/compose.yaml --ha-config-dir testing/tmp/maintainer-demo/homeassistant/config --fake-hardware
```

This writes files under the ignored `testing/tmp/` directory. It doesn't start
Docker, connect to hardware, or change an installed system. The example's
placeholder serial path is fine because this uses simulation.

Open these files in your editor:

| Generated file under `testing/tmp/maintainer-demo/` | What to look for |
|---|---|
| `compose.yaml` | Home Assistant, Mosquitto, SMS, and the pressure worker |
| `config.fake.yaml` | The resolved configuration selected for simulation |
| `homeassistant/config/labpulse-dashboard.yaml` | The Compressed Air setup and pressure card |
| `homeassistant/config/packages/labpulse_generated.yaml` | Alarm helpers, derived sensors, and automations |

The command prints the Compose path and selected image. That image needn't
exist just to generate files. Don't edit the generated YAML as your fix: the
next generation replaces it. Use it to see what your source change produces.

For a running dashboard later, follow
[the development-image workflow](DEVELOPMENT.md#host-code-and-runtime-images).
That part needs Linux and Docker on a development host.

## 2. Follow one pressure reading

Use the service `pressure_monitor` and measurement `pressure` from the small
example. A serial line arrives as:

```text
pressure:1.2
```

Here's where it goes. Follow these links in order rather than reading whole
packages at once.

For each step, the [package guides](ARCHITECTURE.md#package-guides) give a
function reading order, the data passed between calls and the failure path.
Use them beside the source; the short docstrings are reminders of each
function's job rather than a second copy of the walkthrough.

| Step | Code to open | What happens to the example |
|---|---|---|
| Load the settings | [`load_config`](../src/labpulse/common/config.py), then [`ServiceConfig`](../src/labpulse/common/service_config.py) | Validate the service, measurement, and serial options |
| Choose the driver | [Hardware entry point](../src/labpulse/hardware/__main__.py) and [registry](../src/labpulse/hardware/registry.py) | Select `labpulse.serial_pipe` and construct its driver |
| Parse the sample | [`parse_serial_line` and `SerialPipeDriver.read`](../src/labpulse/hardware/drivers/serial_pipe.py) | Turn the line into `{"pressure": 1.2}`, wrapped in `HardwareReadings` |
| Handle timing and health | [`HardwareServiceRunner`](../src/labpulse/hardware/runner.py) | Publish the reading, track success, and handle failures or reconnects |
| Send it to Home Assistant | [`HomeAssistantMqttPublisher`](../src/labpulse/hardware/homeassistant_publisher.py) | Publish discovery, numeric state, and service status through MQTT |
| Decide whether it is dangerous | [Derived entities](../src/labpulse/homeassistant/templates/alarm/derived_entities.yaml.j2) and [measurement automations](../src/labpulse/homeassistant/templates/alarm/automations/measurement_state.yaml.j2) | Home Assistant compares the reading with thresholds and confirmation timing |
| Notify someone | [Incident scripts](../src/labpulse/homeassistant/templates/alarm/scripts.yaml.j2) and [SMS subscriber](../src/labpulse/sms/subscriber.py) | Apply notification rules, then process an eligible SMS request |

For this reading, the MQTT state topic is
`home/sensor/pressure_monitor/pressure/state`. Discovery uses
`homeassistant/sensor/pressure_monitor_pressure/config`. A fresh installation
uses the entity ID `sensor.labpulse_pressure_monitor_pressure`. Shared
[topic functions](../src/labpulse/common/mqtt_contracts.py) and
[identity functions](../src/labpulse/common/identity.py) define these names;
don't invent another naming scheme inside a new feature.

Discovery tells Home Assistant what the sensor is. State messages carry its
value. Numeric state isn't retained by the broker, so you need to wait for a
new sample when listening to it. Discovery and service status are retained.

There are two different times when code runs: LabPulse generates Home Assistant
YAML during setup or a configuration change; Home Assistant runs the resulting
alarms later. Editing a template won't change an already running dashboard
until you regenerate and apply it.

The real serial driver isn't used in complete simulation mode. The entry point
substitutes an in-memory driver, then uses the same runner and publisher. A
successful demo therefore doesn't prove a change to the serial parser works.

Try `python -m pytest testing/test_serial_parser.py -q`, then read one test in
that file. Continue with `test_hardware_runner.py` and
`test_homeassistant_publisher.py` when you reach those steps in the flow.

## 3. Make a small change

Start with [the worked changes](MAINTAINER_EXAMPLES.md). They cover:

1. changing a heading on System Status and inspecting the generated result;
2. adding a serial timeout option, from validation to the actual connection;
3. adding a small counter driver to learn registration, lifecycle, and tests.

These are exercises on your branch, not proposed product changes. Keep or
discard each one deliberately before preparing a pull request. For a real
change, describe the behaviour you want first: what the user does, what happens
now, and what should happen afterward.

## 4. Find where a problem starts

Use these recipes on a dedicated development installation. The examples use
`~/labpulse-dev-live` from the development-image workflow. Run commands on that
Linux host. They don't require changing alarm settings on a live lab system.

### The driver has a value, but the dashboard doesn't

Start with the service and Home Assistant logs:

```bash
labpulse --live-dir ~/labpulse-dev-live ps --all
labpulse --live-dir ~/labpulse-dev-live logs --tail 100 labpulse-pressure-monitor
labpulse --live-dir ~/labpulse-dev-live logs --tail 100 homeassistant
```

Check the startup line for the selected driver and configuration. A
`simulated(...)` driver means you're checking simulated data. Confirm that
`pressure` is actually declared under this service's measurements; the
publisher ignores unexpected keys returned by a driver.

Listen to this reading at the broker:

```bash
sudo docker compose -f ~/labpulse-dev-live/compose.yaml exec mosquitto mosquitto_sub -h 127.0.0.1 -t home/sensor/pressure_monitor/pressure/state -v
```

You should see a topic and numeric value on each new publication. Press
**Ctrl+C** to stop listening. If there are no messages, stay with the driver,
runner, and publisher. If messages arrive, inspect discovery:

```bash
sudo docker compose -f ~/labpulse-dev-live/compose.yaml exec mosquitto mosquitto_sub -h 127.0.0.1 -t homeassistant/sensor/pressure_monitor_pressure/config -v -C 1
```

The retained JSON should identify the state topic and expiry time. If no
discovery arrives, check the publisher's connection and discovery code. If it
does arrive, check Home Assistant's MQTT integration, entity state, and logs.
If the entity is current but its card is missing, check setup membership and
the generated dashboard. Each check narrows the problem by one step.

### My Python change isn't running

Check where the host imports it from:

```bash
python -c "import labpulse; print(labpulse.__file__)"
```

That should point into your checkout. Then check the running pressure worker:

```bash
sudo docker compose -f ~/labpulse-dev-live/compose.yaml images
sudo docker compose -f ~/labpulse-dev-live/compose.yaml exec labpulse-pressure-monitor python -c "import labpulse; print(labpulse.__file__)"
```

The container has its own installed copy. For runtime Python changes, rebuild
the wheel and image and recreate the container, using the
[development-image commands](DEVELOPMENT.md#host-code-and-runtime-images).
Restarting an old container doesn't install your new code. For generated YAML,
rerun generation/setup and apply the result instead.

### The alarm changed, but no SMS arrived

First check global, setup, and measurement mutes, Test mode, and the intended
recipient list. Test mode changes recipients; dry-run prevents modem delivery.
Complete simulation forces dry-run regardless of the source SMS setting.

Then inspect the sender:

```bash
labpulse --live-dir ~/labpulse-dev-live logs --tail 100 labpulse-sms
```

For a deliberate test with example recipients, start a broker listener before
triggering the test:

```bash
sudo docker compose -f ~/labpulse-dev-live/compose.yaml exec mosquitto mosquitto_sub -h 127.0.0.1 -t labpulse/sms/send -t 'labpulse/sms/result/#' -v
```

A new request should have a `request_id`; use it to match the result and log
entries. No request points back to Home Assistant's notification gates. A
request without successful processing points to the subscriber or sender.
A dry-run result is expected in simulation. A modem accepting a message still
doesn't prove a phone received it. Avoid sharing raw message payloads or logs
containing real contact details.

## 5. Know what your tests prove

A **fake** is a small stand-in for something outside the code, such as a serial
port or clock. It lets a test simulate a timeout or unplugged device without
waiting or touching hardware. A **fixture** supplies repeatable test data or
setup; shared fixtures live in [`testing/conftest.py`](../testing/conftest.py).

| Check | What it establishes | What it doesn't establish |
|---|---|---|
| Parser and driver tests | Expected values, errors, and cleanup with controlled inputs | Electrical behaviour or a vendor library working on the Pi |
| Runner and publisher tests | Retry, health, publication, and discovery decisions with fakes | A real broker connection or Home Assistant discovering the entity |
| Configuration and generation tests | Accepted settings and the shape/content of generated YAML | That every automation behaves correctly inside Home Assistant |
| Dashboard tests | Expected cards and references in parsed YAML | Layout, readability, or clicking the controls in a browser |
| Packaging tests | Required metadata, files, and workflow declarations | Successful publication or operation on both CPU architectures |
| Running-stack checks | Real containers, broker, discovery, and Home Assistant together | Real sensor wiring or SMS delivery when using simulation |
| Real-device checks | Behaviour on the recorded hardware and software versions | Behaviour on every other device or indefinite reliability |

Start with the tests closest to your change, then run `python -m pytest` before
submitting it. The [test map](../testing/README.md) helps find the relevant
modules. Use `python -m pytest -ra` to see skip reasons: editor integration tests
skip without Bash, and a symlink test can skip when the environment can't
create symlinks. Having Bash on Windows isn't proof that Linux deployment
workflows will run correctly; use Linux CI or a development Pi for those.

Ordinary CI runs on Ubuntu with Python 3.11 and 3.12. A passing local run on a
different platform is useful, but isn't a substitute for that matrix. Tests
which exercise failure handling may emit warnings deliberately; use the test
result and traceback to distinguish expected failures from broken tests.

For a driver change, record actual-device connection, readings, failure, and
recovery. For an alarm change, test timing, missing input, recovery, mutes, and
restart behaviour in Home Assistant. For a dashboard change, open it at desktop
and phone widths. Record what you haven't checked instead of implying the
unit tests cover it.

## 6. Prepare a change for others to use

Before opening a pull request, read `git diff` and check that it contains only
the intended changes. Include the problem, new behaviour, tests run, and any
remaining real-device checks. Update the relevant guide and the
[screenshot checklist](../screenshot.md) if the interface has changed.

For implemented behaviour, read the [User Guide](USER_GUIDE.md) and the guide
for the feature you're changing. Remaining documentation checks are in the
[documentation checklist](../DOCUMENTATION_TODO.md); proposed changes belong in
[GitHub issues](https://github.com/lairdgrouplancaster/LabPulse/issues).
The [July hardware acceptance record](../testing/real_hardware/ACCEPTANCE_2026-07-27.md)
applies to its recorded revision and equipment, not your current checkout.
For a Triton installation, record the
[site acceptance checks](TRITON_PUBLISHER.md#final-acceptance-checklist) separately.

Publishing is a separate step, normally done by a maintainer with release
access. Start with the [GitHub release and Pi update quick guide](RELEASING.md#quick-guide-github-release-to-updated-pi).
Follow the rest of [Releasing LabPulse](RELEASING.md) for versioning, artifact
checks, publication, and recovery from a partial release. You don't need to
publish anything to validate your first contribution.

You're ready to hand the change over when you can explain which source files
you changed, show the resulting behaviour, and say what the tests checked.
Include any remaining Pi or browser checks in the pull request so the next
person knows exactly where to continue.
