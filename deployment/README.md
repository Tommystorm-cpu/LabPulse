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
src/labpulse/homeassistant/generator.py  HA command and core/dashboard generation
src/labpulse/homeassistant/alarm.py      alarm context/package generation
```

Setup and guarded editing use the unified deployment generator. It resolves the
operator-owned `config.yaml` and referenced `config.d` measurement fragments
into a standalone `config.resolved.yaml`, validates it independently, and then
builds Compose and Home Assistant output from that document before managed live
files are replaced. Fake mode preserves the complete resolved document in
`config.fake.yaml`; Compose selects safe in-memory workers at runtime.

The scripts accept live paths and version/image selections from the operator
command; they do not own the configuration schema. A failed validation or
generation step must leave operator-owned configuration and the last installed
managed files intact. Host permission, missing-command, and generator failures
are reported to the calling command with a non-zero exit status.

Coverage is primarily in `testing/test_control_cli.py`,
`testing/test_deployment_generation.py`, and
`testing/test_unified_generation.py`. See [Installation](../docs/INSTALLATION.md)
for the deployed workflow and [Development](../docs/DEVELOPMENT.md) before
running these Linux-oriented scripts directly.
