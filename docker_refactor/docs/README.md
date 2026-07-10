# LabPulse Docker Refactor Documentation

This documentation explains the `docker_refactor/` system from operator setup
through code changes. It is written for someone who needs to understand how the
system works, how to safely change it, and especially how to edit Home Assistant
dashboard and automation layouts.

## Reading Path

If you are new to this folder, read in this order:

1. [HAPPY_PATH_SETUP.md](HAPPY_PATH_SETUP.md) - the normal Raspberry Pi setup and update loop.
2. [ARCHITECTURE.md](ARCHITECTURE.md) - how containers, MQTT, Python services, Home Assistant, and SMS fit together.
3. [CONFIGURATION.md](CONFIGURATION.md) - every important `config.yaml` field and what it controls.
4. [HOME_ASSISTANT_DASHBOARDS_AND_AUTOMATIONS.md](HOME_ASSISTANT_DASHBOARDS_AND_AUTOMATIONS.md) - how dashboard layout and alarm automations are generated and edited.
5. [CODE_READING_GUIDE.md](CODE_READING_GUIDE.md) - code-level guide to every module and execution path.

The implemented package-boundary design and acceptance criteria are recorded
in [REPOSITORY_REFACTOR_PLAN.md](REPOSITORY_REFACTOR_PLAN.md).

## Task Guides

- [CONTAINER_SETUP.md](CONTAINER_SETUP.md) explains the generated `~/labpulse-ha/` filesystem and Docker Compose project.
- [RUNTIME_AND_MQTT.md](RUNTIME_AND_MQTT.md) explains serial reading, parsing, MQTT discovery, state topics, and entity IDs.
- [HOME_ASSISTANT_BACKUP_RESTORE.md](HOME_ASSISTANT_BACKUP_RESTORE.md) explains dashboard backup, restore, reset, and preservation behavior.
- [SMS_SETUP.md](SMS_SETUP.md) explains log-mode SMS testing and real `mmcli` modem delivery.
- [HARDWARE_AND_SERIAL.md](HARDWARE_AND_SERIAL.md) explains Arduino serial formats, parser compatibility, and stable USB paths.
- [FUTURE_HARDWARE_USB_SETUP.md](FUTURE_HARDWARE_USB_SETUP.md) preserves the future USB detection plan.
- [TESTING_AND_TROUBLESHOOTING.md](TESTING_AND_TROUBLESHOOTING.md) gives tests, debug commands, and failure isolation.

## Historical Notes Rewritten As Current Guides

These files are kept because existing links may point at them, but they now
describe the current implementation rather than old plans:

- [HOME_ASSISTANT_DASHBOARD_PLAN.md](HOME_ASSISTANT_DASHBOARD_PLAN.md)
- [HOME_ASSISTANT_REWRITE_BRIEF.md](HOME_ASSISTANT_REWRITE_BRIEF.md)
- [CPP_REVIEW_NOTES.md](CPP_REVIEW_NOTES.md)

## Source Of Truth

On a running Raspberry Pi:

```text
~/labpulse-ha/config.yaml
```

In the repository:

```text
docker_refactor/config.yaml
```

The repository file is a starter template. The live Pi file is the one users
edit for enabled services, serial paths, labels, display sections, and SMS
recipients.

Generated files such as `compose.yaml`, `labpulse_generated.yaml`, and
`labpulse_entity_map.yaml` should not be hand-edited. Change the generator,
template, or live config, then regenerate.
