# Triton control-PC publisher

The Windows publishers in `firmware/` are the supported bridge from a Triton
`.vcl` logfile to LabPulse. They read the newest complete record, preserve every
Triton column name, and publish the final `labpulse.measurements` version 1 JSON
format. The Pi's `labpulse.mqtt_json` driver selects configured columns by their
exact header names.

There are two entry points:

| Version | File | Intended use |
|---|---|---|
| Setup | `triton_logfile_publisher_setup.py` | Visible foreground commissioning; deliberately small and stops on errors |
| Production | `triton_logfile_publisher_production.py` | Task Scheduler; reconnects, validates, retries and writes rotating operational logs |

Each publisher is one self-contained file with its own copy of the `.vcl`
decoder. Copy only the version being used. They accept the same shared settings
and emit the same payload. Promotion to production does not change the broker,
topic, credentials, Pi configuration, or measurement mapping.

The repository supplies all application code. Three site-specific tasks cannot
be automated safely: issuing a certificate for the Pi's real network name,
choosing which control-PC addresses may reach it, and entering credentials on
each computer. Complete those tasks before enabling the external listener.

## Data path

```text
Triton .vcl logfile on Windows
  -> setup or production Triton publisher
  -> authenticated MQTT over TLS
  -> Mosquitto on the LabPulse Pi
  -> labpulse.mqtt_json service
  -> normal LabPulse measurements, availability, alarms and dashboards
```

`Time(secs)` in the inspected Triton files is a Unix timestamp. It becomes
`recorded_at`, allowing the Pi to reject old data and enforce freshness. A
publish is not marked complete until the broker acknowledges it, so the latest
record is retried after a temporary network outage.

## 1. Choose identities and topics

Give every control PC a unique MQTT username and topic. For example:

| Computer | Username | Topic |
|---|---|---|
| Triton 1 | `triton-01` | `labpulse/triton/triton-01/measurements` |
| Triton 2 | `triton-02` | `labpulse/triton/triton-02/measurements` |

Do not point two independent refrigerators at the same topic: the Pi would
combine their snapshots into one input stream. The publisher's MQTT client ID
contains the Windows computer name by default. Use `--client-id` only if cloned
computers share a name.

## 2. Create the Pi server certificate

Use the Pi's stable DNS name in both the certificate and the publisher's
`--broker` value. The following OpenSSL commands are an example; replace the
name and address with the real values:

```bash
mkdir labpulse-mqtt-ca
cd labpulse-mqtt-ca
openssl genrsa -out labpulse-ca.key 4096
openssl req -x509 -new -key labpulse-ca.key -sha256 -days 3650 \
  -out labpulse-ca.crt -subj "/CN=LabPulse MQTT CA"
openssl genrsa -out server.key 3072
openssl req -new -key server.key -out server.csr \
  -subj "/CN=labpulse-pi.local"
cat > server.ext <<'EOF'
subjectAltName=DNS:labpulse-pi.local,IP:192.168.10.20
extendedKeyUsage=serverAuth
keyUsage=digitalSignature,keyEncipherment
EOF
openssl x509 -req -in server.csr -CA labpulse-ca.crt -CAkey labpulse-ca.key \
  -CAcreateserial -out server.crt -days 825 -sha256 -extfile server.ext
```

Keep `labpulse-ca.key` offline; it is not installed on the Pi or control PCs.
Copy `server.crt` and `server.key` to the Pi, and copy only
`labpulse-ca.crt` to every control PC.

On the Pi:

```bash
mkdir -p ~/labpulse-live/mosquitto/config/certs
cp server.crt ~/labpulse-live/mosquitto/config/certs/server.crt
cp server.key ~/labpulse-live/mosquitto/config/certs/server.key
```

## 3. Create broker users and access rules

Create one password entry per control PC. The Mosquitto image already contains
`mosquitto_passwd`; this command prompts without putting the password in shell
history:

```bash
cd ~/labpulse-live
docker run --rm -it \
  -v "$PWD/mosquitto/config:/mosquitto/config" \
  eclipse-mosquitto:2 \
  mosquitto_passwd -c /mosquitto/config/external-passwords triton-01
```

For later users, omit `-c` so the existing password file is not replaced:

```bash
docker run --rm -it \
  -v "$PWD/mosquitto/config:/mosquitto/config" \
  eclipse-mosquitto:2 \
  mosquitto_passwd /mosquitto/config/external-passwords triton-02
```

Create `~/labpulse-live/mosquitto/config/external-acl` with one exact write
permission per user:

```text
user triton-01
topic write labpulse/triton/triton-01/measurements

user triton-02
topic write labpulse/triton/triton-02/measurements
```

Make the private files readable by the Mosquitto container and not by other
host users:

```bash
sudo chown 1883:1883 \
  ~/labpulse-live/mosquitto/config/certs/server.key \
  ~/labpulse-live/mosquitto/config/external-passwords
sudo chmod 600 \
  ~/labpulse-live/mosquitto/config/certs/server.key \
  ~/labpulse-live/mosquitto/config/external-passwords
chmod 644 \
  ~/labpulse-live/mosquitto/config/certs/server.crt \
  ~/labpulse-live/mosquitto/config/external-acl
```

## 4. Enable the external listener

Edit the real Pi configuration with `labpulse config`:

```yaml
mqtt:
  broker: mosquitto
  port: 1883
  external_listener:
    enabled: true
    bind_addresses:
      - 10.50.1.1
      - 10.50.2.1
    port: 8883
```

These are the Pi addresses on the isolated Triton 1 and Triton 2 `/30` links.
LabPulse publishes MQTT on both addresses but not on the Pi's other interfaces.
`0.0.0.0` is supported for other installations, but listens everywhere and
cannot be combined with specific addresses. LabPulse refuses to generate an
enabled listener unless the certificate, key, password database and ACL all
exist.

Apply and inspect the deployment:

```bash
labpulse config
labpulse up
labpulse ps
labpulse logs mosquitto
```

The existing anonymous port 1883 remains bound to Pi loopback for Home
Assistant and the trusted local containers. Only the new port 8883 is exposed,
and it requires TLS, a username/password and an ACL match.

Restrict TCP 8883 at the laboratory firewall to the known control-PC addresses.
Do not expose it to the public internet. Docker-published ports can interact
with host firewall front ends in surprising ways, so verify the effective rule
from both an allowed computer and an unrelated LAN computer.

## 5. Configure LabPulse's input service

Add or update one service in `~/labpulse-live/config.yaml` for each topic. Map
measurement names to the exact Triton logfile headers:

```yaml
services:
  triton_01:
    label: Triton 1
    driver:
      type: labpulse.mqtt_json
      options:
        topic: labpulse/triton/triton-01/measurements
        maximum_record_age_seconds: 120
        parameters:
          cold_plate_temperature: "Cold Plate T(K)"
          mixing_chamber_temperature: "Mixing Chamber T(K)"
    measurements:
      cold_plate_temperature:
        label: Cold Plate Temperature
        unit: K
        setups: [triton_1]
      mixing_chamber_temperature:
        label: Mixing Chamber Temperature
        unit: K
        setups: [triton_1]
    maximum_measurement_age_seconds: 120
```

Use actual headers from the current `.vcl` file. A missing mapped field is an
unavailable LabPulse reading; an old `recorded_at` value is rejected rather than
being presented as current telemetry. The service-level
`maximum_measurement_age_seconds` setting may also be increased when Triton
records are normally written less frequently than the default.

## 6. Install the publisher on Windows

Install a current Python 3 release and Paho MQTT:

```powershell
py -3 -m pip install "paho-mqtt>=2,<3"
```

Create `C:\ProgramData\LabPulse\TritonPublisher`, then copy these files into it:

- `firmware/triton_logfile_publisher_setup.py`;
- `firmware/triton_logfile_publisher_production.py`;
- `firmware/run_triton_publisher.example.ps1`, renamed to
  `run_triton_publisher.ps1`;
- `labpulse-ca.crt`;
- `mqtt-password.txt`, containing only this PC's broker password.

Edit every `CHANGE_ME` value in the PowerShell file. Ensure the Windows account
that will run the task can read both the Triton logfile directory and these
files. Use Windows file Security properties to remove general-user access from
`mqtt-password.txt`; grant read access only to the task account and SYSTEM.

Test connectivity and first run the setup publisher in a console:

```powershell
Test-NetConnection labpulse-pi.local -Port 8883
cd C:\ProgramData\LabPulse\TritonPublisher
py -3 .\triton_logfile_publisher_setup.py `
  --directory "C:\CHANGE_ME\Triton\LogFiles" `
  --broker labpulse-pi.local `
  --topic labpulse/triton/triton-01/measurements `
  --username triton-01 `
  --password-file .\mqtt-password.txt `
  --ca-certificate .\labpulse-ca.crt
```

The console should say that MQTT connected and that a complete record was
published. Leave it running long enough to see the configured LabPulse
measurements become available. This commissioning version intentionally exits
on a logfile, certificate, authentication, or connection error so the problem
is obvious.

After commissioning, stop it and run the production wrapper:

```powershell
powershell.exe -NoProfile -File C:\ProgramData\LabPulse\TritonPublisher\run_triton_publisher.ps1
```

Confirm that `triton-publisher.log` records a connection and publish before
creating the scheduled task.

## 7. Run it automatically

In Windows Task Scheduler, create a task with:

- trigger: **At startup**, delayed by 30 seconds;
- account: a dedicated local account that can read the Triton logs;
- **Run whether user is logged on or not**;
- program: `powershell.exe`;
- arguments: `-NoProfile -File "C:\ProgramData\LabPulse\TritonPublisher\run_triton_publisher.ps1"`;
- start in: `C:\ProgramData\LabPulse\TritonPublisher`;
- restart on failure every minute, with many retry attempts;
- no short execution time limit.

Start the task manually once and inspect
`C:\ProgramData\LabPulse\TritonPublisher\triton-publisher.log`. Reboot the PC
as the final acceptance check.

## Acceptance checklist

1. An unrelated LAN computer cannot connect to Pi TCP 8883.
2. The allowed control PC rejects a wrong password and an untrusted server
   certificate.
3. Each control PC publishes only to its ACL-approved topic.
4. LabPulse shows mapped readings with realistic values and units.
5. Stop the Windows task: the service becomes unhealthy only after configured
   freshness and confirmation delays.
6. Restart the task: readings and service health recover once without duplicate
   alerts.
7. Reboot the control PC and Pi independently and repeat the checks.
8. Confirm Windows and Pi clocks are synchronized; stale-data protection relies
   on correct time.

The publisher transports monitoring data only. It is not a safety interlock,
and deployment still requires physical validation against the real Triton
software, log rotation behaviour and laboratory network policy.
