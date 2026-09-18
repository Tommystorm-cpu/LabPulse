# Triton logfile publishers

These standalone programs run on the Windows Triton control PC. They are
separate from the Arduino firmware and the Pi's installed Python package.
Run the examples below from the directory containing the scripts on that PC.

Two publisher entry points are provided:

- `triton_logfile_publisher_setup.py` is the small foreground commissioning
  version. It connects once, prints each successful publish, and stops visibly
  on an unexpected error.
- `triton_logfile_publisher_production.py` is the production version for Task
  Scheduler. It adds validation, reconnect handling, configurable polling,
  acknowledged retries, stable identity, operational logging, log rotation,
  and independent script heartbeats.

Each file contains its own copy of the binary `.vcl` decoder and emits the exact
same JSON payload. Copy only the version you want to run. Switching versions
changes only the script file; the Pi topic and measurement mapping remain
unchanged. Both publishers send every field from each new complete record as
one named message.
LabPulse's `labpulse.mqtt_json` driver selects the useful fields by their exact
Triton header names, so different logfiles may contain different headers.

Install its MQTT dependency on the Windows Triton computer:

```powershell
py -m pip install "paho-mqtt>=2,<3"
```

During commissioning, run the smaller version directly in a visible terminal:

```powershell
py .\triton_logfile_publisher_setup.py `
  --directory "D:\Oxford Instruments\Triton\LogFiles" `
  --broker labpulse-pi.local `
  --port 8883 `
  --topic labpulse/triton/triton-01/measurements `
  --username triton-01 `
  --password-file C:\LabPulse\mqtt-password.txt `
  --ca-certificate C:\LabPulse\labpulse-ca.crt
```

It intentionally has no unattended recovery or file logging. Once the data is
correct in LabPulse, run the production version or supplied PowerShell wrapper:

```powershell
py .\triton_logfile_publisher_production.py `
  --directory "D:\Oxford Instruments\Triton\LogFiles" `
  --broker 192.0.2.10 `
  --port 8883 `
  --topic labpulse/triton/triton-01/measurements `
  --heartbeat-topic labpulse/triton/triton-01/heartbeat `
  --username triton-01 `
  --password-file C:\LabPulse\mqtt-password.txt `
  --ca-certificate C:\LabPulse\labpulse-ca.crt
```

The script keeps decoding while the broker is temporarily unavailable and
publishes the current record once the connection recovers. The password file's
first line is used, which keeps the secret out of command history and process
arguments. Plaintext operation requires an explicit `--insecure` flag and is
only for isolated development. See the complete Pi, certificate, Windows and
Task Scheduler procedure in [Triton control-PC publisher](../../docs/TRITON_PUBLISHER.md).
The production script's heartbeat defaults to every 15 seconds, independently
of logfile polling; it also publishes retained `online`/`offline` availability
and configures an `offline` MQTT Last Will. The setup script does not send
heartbeats.


## Repository files

- [Commissioning publisher](triton_logfile_publisher_setup.py)
- [Production publisher](triton_logfile_publisher_production.py)
- [Task Scheduler launcher example](run_triton_publisher.example.ps1)

Copy the launcher beside the production script and configure its placeholders
before use. Moving these source files does not change existing Windows
installation paths or require an installed publisher to be relocated.
