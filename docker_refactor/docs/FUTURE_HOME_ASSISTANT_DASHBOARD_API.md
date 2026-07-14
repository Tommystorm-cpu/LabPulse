# Future Home Assistant Dashboard API Design

Status: proposed; not implemented.

This document records the intended replacement for direct Home Assistant
`.storage` dashboard writes. It should be implemented after the live-Pi sensor
path has been proven. Until then, the current generator resolves the active
Overview storage file and reports a one-file ownership remedy when necessary.

## Why change the current approach?

`generate_homeassistant_config.sh --reset-dashboard` currently renders JSON
directly into Home Assistant's private `.storage` directory. That works, but it
couples LabPulse to internal filenames and filesystem ownership.

The test installation exposed both problems:

1. Home Assistant migrated the legacy `.storage/lovelace` dashboard into a
   registered dashboard with a store such as `.storage/lovelace.lovelace`.
2. Home Assistant runs as `root` in its container and created `.storage` files
   that the `labpulse` host user could not replace.

Home Assistant already owns dashboard registration, persistence, migration,
cache invalidation, and update events. LabPulse should ask Home Assistant to
save dashboard configuration through its WebSocket API instead of modifying
Home Assistant's implementation files.

Official references:

- <https://developers.home-assistant.io/docs/api/websocket/>
- <https://github.com/home-assistant/core/blob/dev/homeassistant/components/lovelace/websocket.py>
- <https://github.com/home-assistant/core/blob/dev/homeassistant/components/lovelace/dashboard.py>

## Design decision

LabPulse should own a dedicated storage-mode dashboard rather than replace the
user's general Overview dashboard.

Proposed identity:

```text
title: LabPulse
url_path: labpulse-monitor
mode: storage
show_in_sidebar: true
icon: mdi:flask-outline
```

This separates responsibilities:

| State | Owner |
| --- | --- |
| LabPulse dashboard seed and generated structure | LabPulse repository |
| Live LabPulse dashboard | Home Assistant storage/API |
| General Overview and unrelated dashboards | Home Assistant user |
| Sensor inventory and presentation labels | `~/labpulse-ha/config.yaml` |
| Alarm helper values and UI edits | Home Assistant |

Normal generation must preserve the live dashboard. Only explicit reset,
restore, or entity-synchronization commands may change it.

## WebSocket protocol

The client connects to:

```text
ws://127.0.0.1:8123/api/websocket
```

Use `wss://` when communicating through an HTTPS endpoint. The normal local Pi
deployment should use loopback so the token and dashboard data do not leave the
host.

The connection sequence is:

1. Receive `auth_required`.
2. Send `{"type": "auth", "access_token": "..."}`.
3. Require `auth_ok`; treat `auth_invalid` as fatal.
4. Send commands with monotonically increasing integer IDs.
5. Require a matching successful `result` for every command.

Relevant Home Assistant commands are:

```json
{"id": 1, "type": "lovelace/dashboards/list"}
```

```json
{
  "id": 2,
  "type": "lovelace/config",
  "url_path": "labpulse-monitor",
  "force": true
}
```

```json
{
  "id": 3,
  "type": "lovelace/config/save",
  "url_path": "labpulse-monitor",
  "config": {"views": []}
}
```

Dashboard creation should use the dashboard collection's create command when
`labpulse-monitor` does not exist. The implementation must confirm the exact
create schema against the Home Assistant version under test rather than
depending on undocumented fields.

`lovelace/config/save` requires an administrator. Home Assistant persists the
configuration and emits its normal Lovelace-updated event; no container restart
should be required.

## Authentication and secret storage

Use a Home Assistant long-lived access token belonging to a dedicated LabPulse
automation account. Because dashboard saving requires administrator access,
the token is sensitive and broadly privileged.

Preferred token path:

```text
~/labpulse-ha/secrets/homeassistant_token
```

Required properties:

- mode `0600`
- owned by the account running the generator
- excluded from Git and setup backups intended for sharing
- never stored in `config.yaml`, Compose YAML, command-line arguments, or logs
- token contents never included in exceptions

Allow `LABPULSE_HA_TOKEN` as a temporary environment override for development,
but prefer the file for normal Pi operation. Continue to support
`LABPULSE_HA_URL`, defaulting to `http://127.0.0.1:8123` and deriving the
corresponding WebSocket URL.

If a token is missing:

- ordinary YAML generation should still work;
- dashboard-preserving runs should still work without contacting Home
  Assistant;
- any command that mutates or validates live Home Assistant state should stop
  with concise token-setup instructions.

## Proposed Python structure

Add a small client under `labpulse_homeassistant`:

```text
labpulse_homeassistant/
  homeassistant_api.py     authenticated WebSocket transport and commands
  dashboard.py             pure dashboard rendering and entity replacement
  dashboard_service.py     backup/reset/restore orchestration
```

Suggested interfaces:

```python
class HomeAssistantApi:
    def connect(self) -> None: ...
    def list_dashboards(self) -> list[dict[str, object]]: ...
    def create_dashboard(self, metadata: dict[str, object]) -> None: ...
    def load_dashboard(self, url_path: str) -> dict[str, object]: ...
    def save_dashboard(self, url_path: str, config: dict[str, object]) -> None: ...
    def close(self) -> None: ...
```

The transport should have explicit connection, authentication, request, and
read timeouts. It must validate message IDs and convert Home Assistant error
results into typed, readable exceptions.

Keep `dashboard.py` pure: it should produce the dashboard's `config` object,
not Home Assistant's private storage wrapper containing `version`, `key`, and
`data`. Those wrapper fields belong to Home Assistant.

The project already uses WebSocket access for optional entity-registry
resolution. Reuse one transport and authentication implementation rather than
maintaining separate WebSocket clients.

## Command behaviour

### Normal generation

```bash
./generate_homeassistant_config.sh
```

- Generate `configuration.yaml`, the LabPulse package, and entity map.
- Do not connect to Home Assistant unless another requested operation needs it.
- Do not read or save the dashboard.

### Reset dashboard

```bash
./generate_homeassistant_config.sh --reset-dashboard
```

1. Require Home Assistant to be running and authenticate.
2. Find `labpulse-monitor`; create it if absent.
3. Read its current config when one exists.
4. Save a timestamped API-level backup.
5. Render the new dashboard from live `~/labpulse-ha/config.yaml`.
6. Save through `lovelace/config/save`.
7. Read the dashboard back with `force: true`.
8. Compare canonical JSON and fail if verification differs.

Reset should always back up an existing dashboard. The separate
`--backup-dashboard` flag may remain for an explicit backup without mutation.

### Backup dashboard

Backups should contain metadata plus the portable Lovelace config, not a copy
of a private `.storage` file:

```json
{
  "format": "labpulse-lovelace-backup-v1",
  "created_at": "2026-07-14T12:00:00Z",
  "home_assistant_url_path": "labpulse-monitor",
  "config": {"views": []}
}
```

Continue using timestamped and `dashboard-latest` locations, but give backup
files a `.json` extension and write them atomically.

### Restore dashboard

```bash
./generate_homeassistant_config.sh --load-dashboard
```

1. Parse and validate the selected LabPulse backup format.
2. Back up the current remote dashboard before changing it.
3. Save the backup's `config` through the API.
4. Read it back and verify canonical equality.

### Synchronize entity IDs

The existing surgical replacement behaviour should operate on the dashboard
returned by `lovelace/config`, then save only if at least one exact entity ID
changed. Always back up before saving. Preserve all unrelated dashboard keys
and ordering.

## Installation lifecycle

Home Assistant authentication does not exist until onboarding is complete, so
installation becomes deliberately two-stage:

1. `setup_container_fs.sh` creates the live project, generated YAML, Compose,
   and service code without mutating a Lovelace dashboard.
2. Start Home Assistant and complete onboarding.
3. Create the dedicated LabPulse automation account and token.
4. Store the token with mode `0600`.
5. Run `generate_homeassistant_config.sh --reset-dashboard` to create the
   LabPulse dashboard through the API.

The setup script should print these next steps. It must not manufacture Home
Assistant users, scrape authentication storage, or request an administrator
password.

## Failure and rollback rules

- Network, authentication, schema, or save errors must return non-zero.
- Never delete or truncate the current dashboard before a successful save.
- Never log the token or the WebSocket authentication frame.
- If post-save verification fails, attempt to restore the just-created backup
  and report whether rollback succeeded.
- If Home Assistant is unavailable, generated YAML may still be written, but
  explicitly requested dashboard mutation must fail.
- Do not fall back silently to direct `.storage` writes.
- A concurrent UI edit remains a last-writer-wins risk because the API does not
  expose a compare-and-swap revision. Minimize the interval between backup and
  save and clearly log the operation time.

## Testing strategy

No test should require a real Home Assistant instance by default.

Unit tests should cover:

- authentication success, invalid token, and timeout;
- request/response ID matching;
- dashboard present and absent;
- backup before reset or restore;
- successful save and read-back verification;
- failed verification with successful and failed rollback;
- exact entity-ID synchronization preserving unrelated JSON;
- token redaction in errors and logs;
- no API connection during ordinary generation.

Use a deterministic fake WebSocket server or scripted transport. Add a
separate opt-in integration test against the test Pi's Home Assistant to prove
the real command schemas and immediate UI update.

## Migration plan

1. Implement and test the shared Home Assistant WebSocket client.
2. Move existing entity-registry resolution onto that client.
3. Add API backup and read-only dashboard inspection.
4. Add creation of the dedicated `labpulse-monitor` dashboard.
5. Add reset, restore, verification, and rollback.
6. Change setup into the two-stage onboarding flow.
7. Remove all direct Lovelace `.storage` write, ownership, and restart logic.
8. Keep one documented manual recovery procedure for importing the latest
   portable backup through the Home Assistant UI.

Do not maintain API and filesystem dashboard mutation as two permanent modes.
Once the API path is proven, remove the filesystem path to avoid divergent
behaviour.

## Acceptance criteria

The design is complete when:

- a clean Pi can reach the onboarding stage without a Home Assistant token;
- post-onboarding finalisation creates a sidebar LabPulse dashboard;
- reset, backup, restore, and entity synchronization never touch `.storage`;
- no Home Assistant restart is required after dashboard changes;
- UI dashboard edits survive ordinary LabPulse regeneration;
- explicit reset replaces only the LabPulse dashboard;
- permission and storage-key migrations do not affect LabPulse;
- invalid credentials and unavailable Home Assistant produce actionable errors;
- a failed verified save can restore the previous dashboard;
- all normal tests run without Home Assistant or physical sensors.

