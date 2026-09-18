# Working on LabPulse

Read the repository's [LabPulse project skill](.codex/skills/labpulse-project/SKILL.md)
before changing code, deployment, firmware, hardware records, or documentation.
It is the shared project guide even when your agent cannot discover skills
automatically. Read only the task-relevant references it links to.

## Core rules

- LabPulse has live installations and published releases. Preserve user-owned
  state and assess changes to public commands, configuration, IDs, and protocols
  against the supported release behaviour. `legacy/` is historical reference,
  not a second maintained implementation.
- The repository's `config.yaml` is a starter. Installed users edit
  `~/labpulse-live/config.yaml` and referenced `config.d/` files. Change generators
  rather than treating generated Compose or Home Assistant YAML as source.
- Keep work on a test installation separate from the live monitor. A different
  `--live-dir` does not isolate Docker container names or host ports. Repository
  work does not itself authorise changes to a running Pi or delivery of real SMS.
- Run the relevant hardware-free tests for code changes; report skipped or
  unperformed Linux, Home Assistant, firmware, and physical-hardware checks.
  Use [testing/README.md](testing/README.md) to select the relevant suite.
- Keep this file short. Put project-specific working guidance in the skill and
  detailed procedures in the maintained docs; update their links when moving files.

## Documentation maintenance

When editing documentation, keep the root `screenshot.md` checklist in sync
with screenshot and photo insertion points. Add entries for new capture needs,
update links when sections move, and remove obsolete entries. Mark an entry
complete only when the real image has been added to the guide. If documented
UI changes make an existing image inaccurate, mark it as needing a refresh.

Use clearly labelled insertion points when a real capture isn't available.
Do not present a diagram or mockup as a screenshot. Write user documentation
in approachable, plain language and explain unfamiliar terms where needed.
