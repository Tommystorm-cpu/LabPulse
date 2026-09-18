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
src/labpulse/deployment/generate.py      staged rendering and per-file installation
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
command; they do not own the configuration schema. Validation/render failures
leave managed live output untouched. Installation replaces files individually;
a filesystem failure during replacement can leave mixed output. Host permission,
missing-command, and generator failures return a non-zero exit status.

## Follow the host-to-Python boundary

[`installer.main()`](../src/labpulse/installer.py) locates the packaged assets
and starts [`setup_container_fs.sh`](setup_container_fs.sh). Read that script's
main sequence to see directory creation, managed host environment setup,
generation and permission handling. The generator runs as a separate Python
process; its exit status tells the shell whether to continue.

For a config change, [`control.run_config_editor()`](../src/labpulse/control.py)
starts [`edit_config.sh`](edit_config.sh). The editor works on a disposable copy
of the master and fragments, generates candidate output and checks it before
installing the edited bundle. Its shell traps handle temporary files and rollback
work; follow those alongside the successful path when changing error handling.
Continue in the [deployment package README](../src/labpulse/deployment/README.md)
for the Python function sequence and data structures.

Coverage is primarily in `testing/test_control_cli.py`,
`testing/test_deployment_generation.py`, and
`testing/test_unified_generation.py`. See [Installation](../docs/INSTALLATION.md)
for the deployed workflow and [Development](../docs/DEVELOPMENT.md) before
running these Linux-oriented scripts directly.
