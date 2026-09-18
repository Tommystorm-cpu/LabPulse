# Contributing to LabPulse

Thank you for helping improve LabPulse. Changes to public commands,
configuration or extension interfaces need migration notes and normal semantic
versioning so existing installations are not surprised.

Adding support for a sensor? Follow [Contributing sensors](#contributing-sensors),
then [the GitHub workflow](#making-a-change-through-github) to send your work
for review. Firmware, reusable configuration examples, calibration notes, and
tests are useful contributions too; a new sensor doesn't always need a new
Python driver.

## Before starting

If you're new to the project, start with
[Your first day maintaining LabPulse](docs/MAINTAINING.md). It takes you from
a fresh checkout to a tested change, with no hardware needed for the first steps.

For a small correction, open a focused pull request. For a new feature,
configuration change, public interface, or hardware driver, open an issue first
so the intended behavior and test boundary can be agreed.

Read:

1. [User guide and safety boundary](docs/USER_GUIDE.md)
2. [Architecture](docs/ARCHITECTURE.md)
3. [Development](docs/DEVELOPMENT.md)
4. [Hardware driver package guide](src/labpulse/hardware/drivers/README.md)
   when adding direct hardware support
5. [Firmware guide](firmware/README.md) when changing Arduino firmware or
   serial output

## Development principles

- Preserve `~/labpulse-live/config.yaml` as the installed source of truth.
- Keep sensor acquisition in Python and alarm decisions in Home Assistant.
- Keep equipment control and safety functions outside the measurement driver
  contract; discuss any actuation proposal before implementation.
- Prefer the standard serial protocol when firmware can normalize a device.
- Keep optional hardware libraries lazy so unrelated drivers and host-side
  generation do not require them.
- Make important behavior testable without Raspberry Pi hardware.
- Add compatibility or migration logic only for a concrete published-release
  requirement.
- Do not commit phone numbers, credentials, Home Assistant state, logs, or
  locally generated deployment files.

## Making a change through GitHub

You can contribute without write access to LabPulse. A **fork** is your copy
of the repository on GitHub; a **clone** is a working copy on your computer.
A **branch** keeps one change together, a **commit** records a set of edits,
and a **pull request (PR)** asks the maintainers to review and merge those
commits into LabPulse.

### 1. Fork and clone the repository

You need a GitHub account and Git installed on your computer. For first-time
Git setup and authentication, follow [GitHub's setup guide](https://docs.github.com/en/get-started/git-basics/set-up-git).

Open [lairdgrouplancaster/LabPulse](https://github.com/lairdgrouplancaster/LabPulse),
choose **Fork**, select your account as owner, and choose **Create fork**.
Keeping just the default branch is enough. See [GitHub's fork guide](https://docs.github.com/en/pull-requests/how-tos/work-with-forks/fork-a-repo)
for the current screen instructions.

In a terminal on your development computer, run the following. Replace
`YOUR-USERNAME` with your GitHub username; these commands assume you kept the
fork's name as `LabPulse`.

```bash
git clone https://github.com/YOUR-USERNAME/LabPulse.git
cd LabPulse
git remote add upstream https://github.com/lairdgrouplancaster/LabPulse.git
git remote -v
```

The last command should show `origin` pointing to your fork and `upstream`
pointing to `lairdgrouplancaster/LabPulse`. These are saved names for the two
repositories: you push contributions to `origin` and fetch project updates
from `upstream`. If you already have a checkout, inspect its remotes first;
don't repeat the clone or add an already-existing remote.

### 2. Make a branch and prepare Python

Start with a clean checkout (`git status` should report no uncommitted changes):

```bash
git fetch upstream
git switch -c add-my-sensor upstream/main
```

Use a descriptive branch name, such as `add-water-temperature-sensor`.
Use that same name in the push command below. Fetching downloads the current
project history; the new branch starts from the project's `main` branch.

Use Python 3.11 or 3.12 and create a virtual environment, a separate place for
this checkout's Python packages:

```bash
python -m venv .venv
```

Activate it using the command for your terminal:

| Terminal | Command |
|---|---|
| Linux/macOS Bash | `source .venv/bin/activate` |
| Windows PowerShell | `.venv/Scripts/Activate.ps1` |

Then install LabPulse and its test tools from the repository root:

```bash
python -m pip install --editable ".[dev]"
python -m pytest
```

An editable install uses the source files you're changing. The normal tests
need no Pi or sensors. If environment setup fails, use
[the first maintainer session](docs/MAINTAINING.md#1-get-a-working-checkout).
Continue in this fork's checkout rather than cloning the project again.

### 3. Make and test your contribution

Follow [the sensor steps below](#contributing-sensors). Keep the change focused,
update its documentation, and run relevant tests while developing. Before
submitting a code change, run `python -m pytest` for the complete hardware-free
suite. For documentation-only changes, run
`python -m pytest testing/test_documentation.py -q`.

Review what will be published:

```bash
git status
git diff
```

Stage only the files belonging to this contribution. For example, if your
change updates an existing configuration example and the hardware guide:

```bash
git add docs/examples/minimal-serial.yaml docs/HARDWARE.md
git diff --cached
git commit -m "Document configuration and wiring for the new sensor"
git push -u origin add-my-sensor
```

Replace the paths, message, and branch name with your actual change.
`git diff --cached` shows exactly what the commit will contain; check new files
there too. Keep real credentials, phone numbers, logs, local environments,
and generated deployment files out of the commit. If GitHub asks you to sign
in when pushing, use your configured GitHub authentication; an account password
isn't a Git HTTPS credential.

### 4. Open a pull request into LabPulse

On the upstream LabPulse repository, open **Pull requests**, choose
**New pull request**, then **compare across forks**. Set:

| Selector | Value |
|---|---|
| Base repository (where the change should go) | `lairdgrouplancaster/LabPulse` |
| Base branch | `main` |
| Head repository (where your work is) | `YOUR-USERNAME/LabPulse` |
| Compare branch | Your contribution branch, such as `add-my-sensor` |

Check the displayed file changes, then choose **Create pull request**. Give it
a clear title and use [the PR checklist below](#pull-requests) for the
description. Link the issue you discussed, for example `Related to #123`.
Choose a **draft pull request** if you want feedback while work or hardware
testing is still incomplete. [GitHub's PR-from-a-fork guide](https://docs.github.com/en/pull-requests/how-tos/create-pull-requests/creating-a-pull-request-from-a-fork)
explains the interface in more detail.

> **Screenshot to add: contributing from a fork.** Capture the comparison
> selectors with `lairdgrouplancaster/LabPulse` and `main` as the base, and a
> contributor's fork and sensor branch as the head. Use a real contribution
> with permission to show the account name; crop out unrelated account details.

### 5. Respond to review

The PR shows automated checks and reviewer comments. LabPulse's Python checks
run the hardware-free suite on Python 3.11 and 3.12. A maintainer may need to
approve a first-time contributor's workflow run. Passing these checks doesn't
demonstrate that a physical sensor is wired or calibrated correctly.

Make requested edits on the same local branch, rerun the relevant tests, then
stage, commit, and `git push` again. The existing PR updates automatically;
reply to comments explaining the changes. The maintainers decide when to merge.

If the branch needs current project changes, commit your work first, then run
`git fetch upstream` and `git merge upstream/main` while on your contribution
branch. Resolve any reported conflicts, review the combined result, rerun tests,
and push it. After a merge, start your next contribution on a new branch from
a freshly fetched `upstream/main`.

By submitting a contribution, you agree that it may be distributed under the
[MIT License](LICENSE) used by this project.

Do not hand-edit generated `compose.yaml`,
`homeassistant/config/packages/labpulse_generated.yaml`, or
`homeassistant/config/labpulse-dashboard.yaml` as source changes. Update their
generators, models, templates, or source configuration.

## Pull requests

A pull request should explain:

- the problem and intended behavior;
- the components changed;
- automated tests run;
- real hardware tested, if any;
- configuration or generated-output changes;
- documentation updated;
- remaining risks or follow-up work.

For a sensor, also give the model and interface, measurement names and units,
a sample reading, and a link to the example configuration. Record the board,
firmware revision, calibration/reference check, and disconnect/recovery results
when hardware was tested. Say explicitly which checks haven't been performed;
an honest draft is useful before hardware validation is complete.

Keep unrelated formatting and refactors out of functional changes. Preserve
user changes already present in the branch.

## Hardware contributions

For sensor contributions, follow the walkthrough below. Equipment-control
contributions need a separate design discussion because they can change the
state of attached equipment.

## Contributing sensors

### 1. Describe the sensor and choose a route

Search [the existing issues](https://github.com/lairdgrouplancaster/LabPulse/issues)
and [supported drivers](src/labpulse/hardware/drivers/README.md) first. For new
support, open an issue with the manufacturer/model, a datasheet link, connection
type, measured quantities, units, expected sampling rate, and hardware available
for testing. Include a short example of what the device sends, if applicable.

| What you have | Contribution route |
|---|---|
| A sensor already supported by a driver or firmware example | Add a reusable configuration example, wiring/calibration notes, and missing tests. |
| An Arduino or other board whose firmware you can change | Send the standard serial format and reuse `labpulse.serial_pipe`. |
| A separate computer or instrument publisher | Check whether it can send the existing `labpulse.mqtt_json` contract; MQTT carries messages between processes. |
| A device needing Python to access its bus or decode a different protocol | Add a direct input driver with the lifecycle described below. |

Prefer serial when firmware can normalize the sensor data. An extra temperature
probe on an Arduino usually needs firmware and measurement configuration,
rather than another Python driver. Read the existing
[one-sensor walkthrough](docs/FIRST_SENSOR.md) to see how readings reach the
dashboard; see [MQTT input configuration](docs/CONFIGURATION.md#named-json-over-mqtt)
for the network route.

### 2. Define the readings and configuration

Choose stable measurement keys, such as `water_temperature`, and document each
key's meaning, unit, valid range, and conversion/calibration. The driver's
returned keys or parsed serial labels must match the configured measurement
keys. A display label can be friendlier. For MQTT, use the documented source
mapping when the external publisher uses different names.

`unit` in YAML labels a reading; it doesn't convert it. Publish finite numeric
values in the stated units, preserve genuine zero readings, and report missing
or faulty readings as unavailable rather than inventing a zero.

Add a small, complete example under `docs/examples/`, using
[minimal-serial.yaml](docs/examples/minimal-serial.yaml) or
[mqtt-input.yaml](docs/examples/mqtt-input.yaml) as a starting point. Explain
which port, bus address, or topic the user must replace, and how measurements
join a setup on the dashboard. Use stable `/dev/serial/by-id/` paths for USB
hardware. Keep lab-specific choices out of the shared starter configuration.

These are repository examples. On an installed Pi, users edit
`~/labpulse-live/config.yaml` and its referenced measurement files through
`labpulse config`. Update source configuration, generators, or templates when
needed; generated Compose and Home Assistant files aren't contribution sources.

### 3. Implement the acquisition

**For serial firmware**, start with the [firmware library and examples](firmware/README.md).
Send one newline-terminated sample using unit-free `name:value` fields separated
by `|`, for example:

```text
water_temperature: 21.4 | flow_rate: 0.8
```

Those illustrative numbers have meaning only with documented units. Use `null`
for an unavailable channel, and match the firmware baud rate to configuration
(the default is 9600). Reuse the shared firmware components where appropriate;
document the board, pins, required libraries, conversion formula, and upload
steps. Keep the single Python serial parser; a new sensor label doesn't require
a device-specific parser. Add representative samples to the relevant tests and
update simulation coverage if the change affects it.

**For a direct Python driver**, work through
[the hardware-free driver example](docs/MAINTAINER_EXAMPLES.md#add-a-driver-without-hardware),
then adapt [the driver template](docs/examples/driver_template.py). Put the
implementation in `src/labpulse/hardware/drivers/` with:

- A strict options model for device-specific settings, used beneath
  `driver.options`; don't add them to the shared service model.
- A named driver class with the `(service_name, config)` constructor.
  `connect()` opens the device, `read()` returns `HardwareReadings` or `None`
  when no sample is ready, and `close()` releases resources safely even after
  a partly failed connection or a previous close.
- Classified failures: `DriverUnavailable` for a failed connection,
  `ConnectionLost` when the connection needs reopening, and
  `TransientReadError` when a read can be retried on the same connection.
  Use `HardwareIssue` alongside usable values for a partial-channel fault.
- A container-requirements function declaring the devices and mounts Docker
  needs, or an empty `ContainerRequirements()` if none are needed.
- One `DRIVER_DEFINITION` with a stable ID, options model, driver class,
  default read interval, and container-requirements function. Public driver
  modules are discovered automatically; no registry selection branch is needed.

Import optional hardware libraries inside `connect()` so desktop configuration
and tests can load the module. Add dependencies to the appropriate extra in
[pyproject.toml](pyproject.toml), and check that the [runtime image](Dockerfile)
installs them. Leave retries and reading freshness to the runner, LabPulse MQTT
publication to the shared publisher, and alarm thresholds to Home Assistant.
See [the driver package guide](src/labpulse/hardware/drivers/README.md) for the
current contracts and implementations.

### 4. Test without hardware, then record a physical check

Use fake device interfaces in tests so another contributor can reproduce
normal readings, invalid configuration/data, missing channels, connection
failure, disconnect/reconnect, and repeated cleanup without owning your sensor.
For a new driver, also cover registry discovery and generated container resources.
For a complete YAML example, add its filename to `DOCUMENTATION_EXAMPLES` in
[the documentation tests](testing/test_documentation.py) so validation and
generation are checked automatically.

Useful focused checks, run from the repository root:

```bash
python -m pytest testing/test_serial_parser.py testing/test_serial_driver.py testing/test_firmware_layout.py -q
python -m pytest testing/test_hardware_factory.py testing/test_deployment_generation.py -q
python -m pytest testing/test_documentation.py -q
```

Choose the checks relevant to your route and run your new driver tests too.
Before submitting code, run the full `python -m pytest` suite. Firmware layout
tests don't compile or run Arduino code: compile changed examples for the
intended board and record the board/core/library versions and result.

For physical checks, follow [the development image workflow](docs/DEVELOPMENT.md#host-code-and-runtime-images)
on a dedicated development Pi. Editing host Python alone doesn't update code
inside a running container. Complete fake-hardware mode substitutes simulated
readings, so it doesn't exercise your real driver or prove calibration.

Record a real-device smoke test (a short end-to-end check) before release:
confirm a reading reaches Home Assistant in the right units, compare it with a
suitable reference, then safely disconnect and reconnect the practice sensor
and check fault reporting and recovery. Keep notifications muted during checks.
If you don't have the device, say so in the PR and list the physical checks
still needed; maintainers can review the software separately.

### 5. Leave enough information for the next lab

Update [Hardware](docs/HARDWARE.md) for part numbers, wiring and calibration,
[Configuration](docs/CONFIGURATION.md) for new settings, and the firmware or
driver package README for implementation details. Explain electrical limits
and pin numbering using the device documentation, and distinguish verified
hardware from untested proposals. Include any relevant release notes.

If a real wiring photo or screenshot isn't available, add a clearly labelled
insertion point and a matching entry in [screenshot.md](screenshot.md). A diagram
can explain connections, but label it as a diagram. Then use
[the GitHub steps above](#making-a-change-through-github) to submit the sensor,
tests, example, and documentation together.

## Documentation style

Write current facts rather than implementation history. Put operator tasks in
operator guides, cross-component contracts in architecture references, and
code-local details in docstrings. Avoid creating one-off implementation-plan
documents for completed features.

Use relative links inside the repository. Examples must distinguish the
repository starter `config.yaml` from the installed
`~/labpulse-live/config.yaml`.

Keep the [screenshot checklist](screenshot.md) in sync when adding, moving, or
removing image insertion points. If a UI change makes a screenshot out of date,
mark it for a new capture. Use plain language and explain unfamiliar terms;
write as though you're helping a colleague who hasn't used LabPulse before.

## Participation

Be respectful, constructive, and professional when opening issues, reviewing
changes, or discussing the project. Do not publish credentials, phone numbers,
private network details, or other sensitive information in issues or pull
requests.
