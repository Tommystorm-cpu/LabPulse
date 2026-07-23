# Deployment scripts

These Linux shell scripts are source assets for the pipx-installed LabPulse
package. Operators normally use `labpulse setup` and `labpulse config` rather
than invoking files in this directory directly.

During setup, the required operational wrappers are copied into
`~/labpulse-live/` with their existing flat names. Keeping the source scripts
here makes the repository root easier to navigate without changing the live
Raspberry Pi layout.

- `setup_container_fs.sh` creates or refreshes the live deployment.
- `edit_config.sh` implements the guarded workflow behind `labpulse config`.
- `generate_compose.sh` generates the live Compose file.
- `generate_homeassistant_config.sh` invokes the packaged Home Assistant
  generator with live paths and permissions.

Change these source files rather than copies under `~/labpulse-live`; rerun
`labpulse setup` to deploy the changes.
