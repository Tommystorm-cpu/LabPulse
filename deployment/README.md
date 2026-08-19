# Deployment scripts

These Linux shell scripts are packaged workflow assets. They own live-directory
scaffolding, editor sequencing, permission checks, and calls into the installed
Python package. Configuration validation and document rendering remain in
`src/labpulse/`.

During setup, the required operational wrappers are copied into
`~/labpulse-live/` with their existing flat names. Keeping the source scripts
here makes the repository root easier to navigate without changing the live
Raspberry Pi layout.

- `setup_container_fs.sh` creates or refreshes the live deployment.
- `edit_config.sh` implements the guarded workflow behind `labpulse config`.
- `generate_compose.sh` launches `python -m labpulse.deployment` for Compose
  generation using live paths.
- `generate_homeassistant_config.sh` launches
  `python -m labpulse.homeassistant` with live paths and permission checks.

Change these source files rather than copies under `~/labpulse-live`; rerun
`labpulse setup` to deploy the changes.

The current sources of generation behavior are:

```text
src/labpulse/deployment/compose.py       Compose rendering
src/labpulse/deployment/generate.py      unified staging/install transaction
src/labpulse/homeassistant/cli.py        standalone HA command boundary
src/labpulse/homeassistant/generator.py  core/dashboard file generation
src/labpulse/homeassistant/alarm.py      alarm context/package generation
```

Setup and guarded editing use the unified deployment generator so Compose and
Home Assistant output are built from one validated document before managed
live files are replaced.
