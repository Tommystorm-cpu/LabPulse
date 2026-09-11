# Triton refrigerator setup

This is the complete commissioning guide for sending Oxford Instruments
Triton `.vcl` logfile readings from the refrigerator control PCs to LabPulse.
It covers the physical network, both TP-Link Archer D2 routers, Windows, the
LabPulse Pi, MQTT security, LabPulse configuration, the setup publisher, and
the unattended production publisher.

Follow the sections in order. Complete the whole process for Triton 2 first,
then repeat the control-PC and router steps for Triton 1. Keeping one known-good
fridge working makes the second installation much easier to diagnose.

## What this installation does

```text
Triton controller
    |
    | existing dedicated control connection -- do not change
    v
Triton Windows control PC
    |
    | second Ethernet adapter, monitoring data only
    v
Archer D2 LAN -> Archer firewall/NAT -> Archer WAN
                                         |
                                         v
                              isolated Ethernet switch
                                         |
                                         v
                            LabPulse Pi MQTT TLS port 8883
                                         |
                                         v
                         LabPulse measurements and Home Assistant
```

The Windows publisher only reads Triton logfiles and publishes MQTT messages.
It does not subscribe to commands and does not write to the Triton software.
The router treats the Pi as an untrusted WAN device: the control PC can start a
connection to the Pi, but the Pi cannot normally start a connection into the
control-PC LAN.

This is monitoring, not a safety interlock. Existing refrigerator protections
and operating procedures remain essential.

## Addresses and identities used here

Use these values consistently. Do not give both refrigerators the same MQTT
topic or username.

| Setting | Triton 1 | Triton 2 |
|---|---|---|
| Archer LAN address | `192.168.1.1/24` | `192.168.1.1/24` |
| Control-PC monitoring address | `192.168.1.101/24` | `192.168.1.101/24` |
| Archer WAN address | `10.50.1.2/30` | `10.50.2.2/30` |
| Pi address | `10.50.1.1/30` | `10.50.2.1/30` |
| MQTT username | `triton-01` | `triton-02` |
| MQTT topic | `labpulse/triton/triton-01/measurements` | `labpulse/triton/triton-02/measurements` |
| MQTT TLS port | `8883` | `8883` |

Both routers may use `192.168.1.1` because their LAN sides are separate. Never
connect the two routers' LAN ports together. Their WAN sides can share the
unmanaged switch because they use different `10.50.x.x/30` subnets.

## Equipment and files required

- One TP-Link Archer D2 router per refrigerator. The tested unit is Archer D2
  V1 EU with firmware `1.4.0 ... Build 160216`.
- One spare Ethernet adapter on each Triton control PC. Do not repurpose the
  adapter connected to the refrigerator controller.
- An Ethernet switch connecting the routers' WAN ports to the Pi's dedicated
  fridge-facing Ethernet interface.
- A current LabPulse installation that supports
  `mqtt.external_listener.bind_addresses`.
- Python 3.11 or newer on each control PC.
- These repository files:
  - `firmware/triton_logfile_publisher_setup.py`
  - `firmware/triton_logfile_publisher_production.py`
  - `firmware/run_triton_publisher.example.ps1`
- One CA certificate file, `labpulse-ca.crt`, created later in this guide.

The two Python publishers are deliberately independent, one-file programs.
Each contains its own `.vcl` decoder. Use the small setup version during
commissioning, then replace it with the production version without changing
the MQTT payload or LabPulse measurement mapping.

Install the normal LabPulse system first by following
[Installation](INSTALLATION.md). On an existing Pi, run `labpulse update`
before starting this guide so the installed package and container images agree.
Do not copy selected Python modules from a development checkout into a running
installation.

## 1. Cable one refrigerator

For the refrigerator currently being commissioned:

1. Leave the Triton controller-to-control-PC cable exactly as it is.
2. Connect the control PC's spare monitoring Ethernet adapter to an Archer LAN
   port, for example LAN 1.
3. If the nearby lab PC needs to reach the router UI, connect it to another
   Archer LAN port. Its university Ethernet remains its normal Internet path.
4. Configure LAN 4/WAN as the Archer's WAN port and connect it to the isolated
   switch.
5. Connect the Pi's fridge-facing Ethernet interface to the same switch.
6. Do not connect a router LAN port directly to the Pi-side switch.

The Archer may display **No Internet connection**. That is expected: its WAN
is an isolated route to LabPulse, not an Internet service.

## 2. Configure each Archer D2

Log in to `http://192.168.1.1` from a computer on that router's LAN. The tested
firmware has **Basic** and **Advanced** tabs across the top.

### 2.1 Select router mode

1. Open **Advanced**.
2. Select **Operation Mode**.
3. Choose **Wireless Router Mode**.
4. Save and allow the router to reboot.

Do not use Access Point mode. Router mode provides the WAN-to-LAN firewall/NAT
boundary that protects the control PC from the Pi-side network.

### 2.2 Configure the LAN

1. Open **Advanced > Network > LAN Settings**.
2. Set the router address to `192.168.1.1`.
3. Set the subnet mask to `255.255.255.0`.
4. Leave DHCP enabled for commissioning computers.
5. If using address reservation, reserve `192.168.1.101` for the control PC's
   monitoring-adapter MAC address. The later Windows static address makes the
   reservation optional, but keeping it prevents accidental duplication.
6. Save.

It is safe for the other refrigerator's separate Archer to use the same LAN
address. It is not safe to join the two LANs physically.

### 2.3 Configure the WAN

Open **Advanced > Network > Internet**, select **Static IP**, and enter the
values for this refrigerator.

| Field | Triton 1 | Triton 2 |
|---|---|---|
| IP address | `10.50.1.2` | `10.50.2.2` |
| Subnet mask | `255.255.255.252` | `255.255.255.252` |
| Default gateway | `10.50.1.1` | `10.50.2.1` |
| Primary DNS | `10.50.1.1` | `10.50.2.1` |
| Secondary DNS | leave blank | leave blank |
| IPv6 | disabled | disabled |

This Archer firmware rejects `0.0.0.0` as a gateway even though the WAN is not
being used for general Internet access. The Pi address is therefore entered as
both gateway and DNS. The control PC is prevented from using it as a general
gateway in the Windows configuration below.

### 2.4 Remove unwanted ways into the LAN

In **Advanced**, check all of the following. Menu labels can differ slightly
between firmware builds.

- **NAT Forwarding > Virtual Servers**: no rules.
- **NAT Forwarding > Port Triggering**: no rules.
- **NAT Forwarding > DMZ**: disabled.
- **NAT Forwarding > UPnP**: disabled.
- **Security/Remote Management**: disabled from the WAN.
- **CWMP/TR-069**: disabled.
- **SNMP**: disabled unless laboratory IT explicitly requires it.
- **IPv6** and **IPv6 Tunnel**: disabled on this isolated link.
- **Wireless** and **Guest Network**: disabled if they are not needed.

Do not create a port-forward for MQTT. The publisher makes an outbound
LAN-to-WAN connection, so no inbound rule is needed.

### 2.5 Optional lab-PC connection

The lab PC used during commissioning may have two network adapters:

- its university/laboratory adapter, which retains its normal address, DNS,
  default gateway, and Internet connection; and
- its Archer adapter, which can remain on DHCP and will normally receive an
  address such as `192.168.1.100`.

The Archer reporting no Internet does not mean the lab PC has no Internet. Run
`route print -4`: Windows normally prefers the university default route because
it has the lower metric. Do not remove or change that university route. Do not
enable Network Bridge or Internet Connection Sharing between the two adapters.
The lab PC is not part of the Triton publishing path once commissioning is
complete and may be disconnected from the Archer if it is no longer needed.

## 3. Configure the Windows control PC

The control PC normally has at least two adapters: the existing
refrigerator-control adapter, which must not be changed, and the new Archer
monitoring adapter.

Run `ipconfig /all` and identify them by description, MAC address, and cable
connection. On the commissioned Triton 2 PC, the Archer adapter was the Intel
I210 named `Ethernet 2`, with MAC address `00-01-29-9C-22-57`.

### 3.1 Give the monitoring adapter a static address

1. Press `Windows+R`, enter `ncpa.cpl`, and press Enter.
2. Right-click the Archer-facing adapter and select **Properties**.
3. Select **Internet Protocol Version 4 (TCP/IPv4)** and click **Properties**.
4. Select **Use the following IP address**.
5. Enter IP address `192.168.1.101` and subnet mask `255.255.255.0`.
6. Leave the default gateway blank.
7. Select **Use the following DNS server addresses** and leave both IPv4 DNS
   boxes blank.
8. Save the settings.

Windows may show `fec0:0:0:ffff::1`, `::2`, and `::3` in `ipconfig /all` as
IPv6 site-local DNS placeholders. They do not create an IPv4 default route and
are not the Archer/Pi DNS settings used by this installation.

If administering remotely, make absolutely sure the selected adapter is the
Archer adapter before changing it. Do not disable or reconfigure the adapter
carrying the remote session.

### 3.2 Add the one route the publisher needs

Open **Command Prompt as Administrator**. A normal prompt reports
`The requested operation requires elevation`.

For Triton 1:

```cmd
route -p add 10.50.1.1 mask 255.255.255.255 192.168.1.1 metric 5
```

For Triton 2:

```cmd
route -p add 10.50.2.1 mask 255.255.255.255 192.168.1.1 metric 5
```

The `/32` route permits only the Pi MQTT address. It does not install a default
route through the Pi. Verify it:

```cmd
route print -4
ipconfig /all
```

The monitoring adapter must have no IPv4 `0.0.0.0` route through
`192.168.1.1`, no default gateway, and no IPv4 DNS. The expected Triton 2 route
is:

```text
Network Destination  Netmask          Gateway      Interface
10.50.2.1             255.255.255.255  192.168.1.1  192.168.1.101
```

### 3.3 Check that Windows is not bridging the refrigerator

In `ncpa.cpl`:

1. Confirm there is no **Network Bridge** object.
2. Open each relevant adapter's **Properties > Sharing** tab.
3. Ensure **Allow other network users to connect through this computer's
   Internet connection** is not selected.

`ipconfig /all` should report `IP Routing Enabled: No`. These checks stop
Windows from routing Pi-side traffic towards the refrigerator controller.

## 4. Configure the Pi's isolated addresses

First inspect the fridge-facing interface and NetworkManager connection:

```bash
nmcli device status
nmcli -g GENERAL.CONNECTION device show eth0
ip -4 address show eth0
ip route
```

The commands below assume `eth0` is dedicated to the fridge network and its
connection is `Wired connection 1`. Substitute the name printed on the Pi. Do
not replace addresses on an interface carrying Pi management or Internet.

```bash
sudo nmcli connection modify "Wired connection 1" \
  ipv4.method manual \
  ipv4.addresses "10.50.1.1/30,10.50.2.1/30" \
  ipv4.gateway "" \
  ipv4.dns "" \
  ipv4.never-default yes \
  ipv6.method disabled
sudo nmcli connection up "Wired connection 1"
```

Verify:

```bash
ip -4 address show eth0
ip route
sysctl net.ipv4.ip_forward
```

Both Pi addresses must be present, neither link may supply the Pi default
route, and `net.ipv4.ip_forward` should be `0`. If NetworkManager does not own
the interface, stop and identify its network manager first. A temporary
`ip addr add` test does not survive reboot.

A ping initiated by the Pi towards `192.168.1.101` may fail because the Archer
blocks unsolicited WAN-to-LAN traffic. That is expected. Do not add a
port-forward to make reverse ping work.

## 5. Create the MQTT TLS certificates

The control PCs connect by IP address, so the server certificate must contain
both Pi IPs as Subject Alternative Names. Generate it on a trusted computer
with OpenSSL; the Pi can be used temporarily if necessary.

```bash
mkdir -p ~/labpulse-mqtt-ca
cd ~/labpulse-mqtt-ca
openssl genrsa -out labpulse-ca.key 4096
openssl req -x509 -new -key labpulse-ca.key -sha256 -days 3650 \
  -out labpulse-ca.crt -subj "/CN=LabPulse MQTT CA"
openssl genrsa -out server.key 3072
openssl req -new -key server.key -out server.csr \
  -subj "/CN=LabPulse MQTT"
nano server.ext
```

Put exactly this in `server.ext`:

```text
subjectAltName=IP:10.50.1.1,IP:10.50.2.1
extendedKeyUsage=serverAuth
keyUsage=digitalSignature,keyEncipherment
```

Sign and inspect it:

```bash
openssl x509 -req -in server.csr \
  -CA labpulse-ca.crt -CAkey labpulse-ca.key -CAcreateserial \
  -out server.crt -days 825 -sha256 -extfile server.ext
openssl x509 -in server.crt -noout -subject -dates -ext subjectAltName
```

The output must contain both Pi addresses. Install the server files:

```bash
mkdir -p ~/labpulse-live/mosquitto/config/certs
cp server.crt ~/labpulse-live/mosquitto/config/certs/server.crt
cp server.key ~/labpulse-live/mosquitto/config/certs/server.key
```

Copy only `labpulse-ca.crt` to the control PCs. Never copy `labpulse-ca.key` or
`server.key` to them. Store `labpulse-ca.key` offline because it can issue
certificates trusted by every Triton publisher.

## 6. Create MQTT accounts and access rules

Create the password database and first account on the Pi:

```bash
cd ~/labpulse-live
docker run --rm -it \
  -v "$PWD/mosquitto/config:/mosquitto/config" \
  eclipse-mosquitto:2 \
  mosquitto_passwd -c /mosquitto/config/external-passwords triton-01
```

Add Triton 2 without `-c`; using `-c` again would erase Triton 1:

```bash
docker run --rm -it \
  -v "$PWD/mosquitto/config:/mosquitto/config" \
  eclipse-mosquitto:2 \
  mosquitto_passwd /mosquitto/config/external-passwords triton-02
```

Create `~/labpulse-live/mosquitto/config/external-acl`:

```text
user triton-01
topic write labpulse/triton/triton-01/measurements

user triton-02
topic write labpulse/triton/triton-02/measurements
```

Each account can publish only its own topic and cannot subscribe. Set file
permissions:

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

To reset a password later, use `mosquitto_passwd` without `-c`, update that
PC's password file, and run `labpulse restart mosquitto`.

## 7. Enable the LabPulse listener

The real Pi configuration is `~/labpulse-live/config.yaml`. The repository
`config.yaml` is only the starter template.

Run `labpulse config` and edit the existing top-level `mqtt:` section:

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

Do not create a second `mqtt:` section. Saving validates the YAML, generates
Compose and Home Assistant files, checks them, and recreates the containers.
LabPulse refuses to enable the listener if a required security file is absent.

Check it:

```bash
labpulse ps
labpulse logs --tail 100 mosquitto
```

Internal containers use `mosquitto:1883`. Only the two specified Pi addresses
expose TLS port 8883.

On the control PC open **PowerShell**, not Command Prompt:

```powershell
Test-NetConnection 10.50.2.1 -Port 8883
```

Use `10.50.1.1` for Triton 1. `TcpTestSucceeded : True` proves the route,
router, Pi address, Docker binding, and TCP listener. The publisher tests TLS
and authentication next.

## 8. Install the Windows publishers

Create `C:\ProgramData\LabPulse\TritonPublisher` and copy into it:

- `triton_logfile_publisher_setup.py`
- `triton_logfile_publisher_production.py`
- `run_triton_publisher.example.ps1`, renamed to
  `run_triton_publisher.ps1`
- `labpulse-ca.crt`
- `mqtt-password.txt`, containing only this PC's MQTT password on one line

For the current two-account PCs, both `user` and `admin` may access the folder.
Open **Command Prompt as Administrator**:

```cmd
icacls "C:\ProgramData\LabPulse\TritonPublisher" /inheritance:e
icacls "C:\ProgramData\LabPulse\TritonPublisher" /grant "Users:(OI)(CI)(M)" "Administrators:(OI)(CI)(F)"
```

Python does not need administrator privileges. File access follows the Windows
account running Python.

### Install the Python dependency

In ordinary-user PowerShell:

```powershell
py -3 --version
py -3 -c "import sys; print(sys.executable)"
```

Record the full `python.exe` path. If the PC has package access:

```powershell
py -3 -m pip install "paho-mqtt>=2,<3"
```

If it has no Internet, download on an Internet-connected Windows PC:

```powershell
New-Item -ItemType Directory -Force -Path "C:\LabPulseTransfer\wheels"
py -3 -m pip download --dest "C:\LabPulseTransfer\wheels" "paho-mqtt>=2,<3"
```

Copy the wheel directory to the control PC and install offline:

```powershell
py -3 -m pip install --no-index --find-links "C:\LabPulseTransfer\wheels" "paho-mqtt>=2,<3"
```

Verify the package and password access without printing the password:

```powershell
py -3 -c "import paho.mqtt.client; print('Paho MQTT: OK')"
py -3 -c "from pathlib import Path; p=Path(r'C:\ProgramData\LabPulse\TritonPublisher\mqtt-password.txt'); print('Password readable:', p.is_file() and bool(p.read_text().strip()))"
```

### Find the real `.vcl` directory

```powershell
Get-ChildItem -Path "C:\Oxford Instruments","D:\Oxford Instruments" -Filter "*.vcl" -File -Recurse -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 10 FullName,LastWriteTime
```

If needed, search `C:\` and `D:\` instead. Use the directory containing the
newest file that continues changing while Triton runs.

Check the clocks because `Time(secs)` becomes the MQTT Unix timestamp:

```powershell
Get-Date
```

On the Pi compare it with `date` and `timedatectl`.

## 9. Run the commissioning publisher

On the Pi, wait for one Triton 2 payload:

```bash
docker exec labpulse-mqtt mosquitto_sub \
  -h 127.0.0.1 -p 1883 \
  -t 'labpulse/triton/triton-02/measurements' \
  -C 1 -v
```

Then run on the Triton 2 control PC:

```powershell
Set-Location "C:\ProgramData\LabPulse\TritonPublisher"
py -3 .\triton_logfile_publisher_setup.py `
  --directory "D:\Oxford Instruments\Triton\LogFiles" `
  --broker "10.50.2.1" `
  --port 8883 `
  --topic "labpulse/triton/triton-02/measurements" `
  --username "triton-02" `
  --password-file ".\mqtt-password.txt" `
  --ca-certificate ".\labpulse-ca.crt"
```

Replace the logfile directory with the discovered path. For Triton 1, use
`10.50.1.1`, `triton-01`, and its topic. Never use `--insecure`.

Expected output starts with:

```text
Connected to 10.50.2.1:8883; press Ctrl+C to stop.
Published record ... with ... fields.
```

The Pi prints a JSON object containing `protocol`, `version`, `recorded_at`,
and `measurements`. Copy the exact measurement names. Capitalization, spaces,
punctuation, and units are significant. Leave this small publisher running
while configuring LabPulse, then stop it with `Ctrl+C`.

## 10. Add each Triton service to LabPulse

Keep global notifications muted during commissioning. Run `labpulse config`
and add the service under the existing `services:` mapping. Use exact headers
from the captured JSON:

```yaml
services:
  triton_02:
    label: Triton 2 Fridge
    driver:
      type: labpulse.mqtt_json
      options:
        broker: mosquitto
        port: 1883
        topic: labpulse/triton/triton-02/measurements
        parameters:
          mixing_chamber_temperature: "Mixing Chamber T(K)"
          cold_plate_temperature: "Cold Plate T(K)"
          condense_pressure: "P2 Condense (Bar)"
        maximum_record_age_seconds: 120
    measurements:
      mixing_chamber_temperature:
        label: Mixing Chamber Temperature
        setups: [triton_2]
        availability: required
        alarmed: false
        unit: K
        device_class: temperature
      cold_plate_temperature:
        label: Cold Plate Temperature
        setups: [triton_2]
        availability: required
        alarmed: false
        unit: K
        device_class: temperature
      condense_pressure:
        label: Condense Pressure
        setups: [triton_2]
        availability: optional
        alarmed: false
        unit: bar
        device_class: pressure
    maximum_measurement_age_seconds: 180
```

Rules:

- Stable IDs use lowercase letters, numbers, and underscores.
- Every `parameters` key needs a matching `measurements` entry.
- Each quoted source header must match the JSON exactly.
- Use internal `mosquitto:1883`, not the external Pi address and port.
- Required readings create an incident when absent; optional readings remain
  visible but do not alert, make the service unhealthy, or block updates.
- Start with `alarmed: false` and enable thresholds only after commissioning.
- Increase the two age limits if Triton genuinely writes records more slowly.

Every measurement needs an existing setup. If necessary, add under the
existing top-level `setups:` mapping:

```yaml
setups:
  triton_2:
    label: Triton 2
    icon: mdi:snowflake-thermometer
    order: 50
```

Do not duplicate `services:` or `setups:`. Saving `labpulse config` validates,
regenerates, and starts the service. Inspect it:

```bash
labpulse ps
labpulse logs --tail 100 labpulse-triton-02
labpulse logs -f labpulse-triton-02
```

If readings remain unavailable, check the publisher, raw Pi subscriber, exact
header spelling, both clocks, record age, and the service log—in that order.
Repeat as `triton_01` for Triton 1.

## 11. Switch to the production publisher

Stop the setup publisher. Edit `run_triton_publisher.ps1`. For Triton 2 it
should use the real values below; substitute the exact Python and logfile paths:

```powershell
$ErrorActionPreference = "Stop"

$publisherDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExecutable = "C:\Users\user\AppData\Local\Programs\Python\Python311\python.exe"
$tritonLogDirectory = "D:\Oxford Instruments\Triton\LogFiles"
$brokerName = "10.50.2.1"
$mqttTopic = "labpulse/triton/triton-02/measurements"
$mqttUsername = "triton-02"
$passwordFile = Join-Path $publisherDirectory "mqtt-password.txt"
$caCertificate = Join-Path $publisherDirectory "labpulse-ca.crt"
$operationalLog = Join-Path $publisherDirectory "triton-publisher.log"

& $pythonExecutable (Join-Path $publisherDirectory "triton_logfile_publisher_production.py") `
    --directory $tritonLogDirectory `
    --broker $brokerName `
    --port 8883 `
    --topic $mqttTopic `
    --username $mqttUsername `
    --password-file $passwordFile `
    --ca-certificate $caCertificate `
    --log-file $operationalLog

if ($LASTEXITCODE -ne 0) {
    throw "Triton logfile publisher exited with code $LASTEXITCODE"
}
```

Run it manually as the ordinary user:

```powershell
powershell.exe -NoProfile -File "C:\ProgramData\LabPulse\TritonPublisher\run_triton_publisher.ps1"
```

In a second window:

```powershell
Get-Content "C:\ProgramData\LabPulse\TritonPublisher\triton-publisher.log" -Tail 50 -Wait
```

Confirm connection and publication, then stop the manual run. The production
publisher reconnects with backoff, uses acknowledged non-retained QoS 1
messages, validates data, and rotates its 5 MiB operational log with three
backups.

## 12. Configure Task Scheduler

Open Task Scheduler and choose **Create Task**, not **Create Basic Task**.

### General

1. Name it `LabPulse Triton Publisher`.
2. Select the ordinary account under which Python is installed.
3. Select **Run whether user is logged on or not**.
4. Do not select **Run with highest privileges**.

### Trigger

Create an **At startup** trigger delayed by 30 seconds.

### Action

| Field | Value |
|---|---|
| Program/script | `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe` |
| Arguments | `-NoProfile -File "C:\ProgramData\LabPulse\TritonPublisher\run_triton_publisher.ps1"` |
| Start in | `C:\ProgramData\LabPulse\TritonPublisher` |

### Conditions and settings

- Clear the AC-power-only condition if it would prevent the fixed PC running.
- Allow on-demand execution.
- Run as soon as possible after a missed start.
- Restart every minute after failure, with many attempts.
- Do not set a short maximum runtime.
- If already running, do not start another instance.

Save the task, provide the ordinary user's Windows password if requested,
right-click the task, and select **Run**. Inspect `triton-publisher.log`. Finally
reboot the control PC and verify that the task and fresh data return without
manual action.

## 13. Enable alarms after commissioning

Leave notifications muted while checking values, units, timestamps, and
availability policies. For readings needing thresholds:

1. Change `alarmed: false` to `alarmed: true` with `labpulse config`.
2. Configure sensible thresholds on the generated Home Assistant alarm page.
3. Test notification routing in test mode.
4. Test **Resend active alert** on a controlled active condition if required.
5. Unmute readings and then global notifications only when testing is complete.

Optional missing readings should show **Unavailable — optional** without an
incident. One complete MQTT failure should become one service-level incident,
not one notification for every reading.

## Final acceptance checklist

1. The original controller Ethernet configuration is unchanged.
2. The monitoring adapter has `192.168.1.101/24`, no gateway, and no IPv4 DNS.
3. Windows has only the persistent `/32` Pi route through the Archer.
4. Windows has no Network Bridge, Internet Connection Sharing, or IP routing.
5. The Archer has no forwarding, DMZ, UPnP, or WAN management rules.
6. The Archer's **No Internet** indication is accepted as normal.
7. Both Pi `/30` addresses survive reboot and the Pi does not forward IPv4.
8. `Test-NetConnection <Pi-address> -Port 8883` succeeds from the control PC.
9. Wrong MQTT credentials and untrusted certificates are rejected.
10. Each user can publish only to its own exact topic.
11. JSON timestamps are current and mapped headers match exactly.
12. Home Assistant displays plausible values, units, and availability policy.
13. Stopping the task produces one eventual input-service incident, not a
    per-reading notification flood.
14. Restarting the task restores the service and readings once.
15. Control PC, Pi, and router reboots need no manual publisher restart.

## Quick fault guide

### `Test-NetConnection` is false

Check the Windows `/32` route, Archer WAN address and cable, Pi address,
external-listener config, container state, and Mosquitto log. Run this command
in PowerShell, not Command Prompt.

### TCP succeeds but MQTT does not connect

The route works. Check the certificate IP SAN, CA file, username, password, ACL
topic, and Mosquitto log.

### MQTT connects but LabPulse receives nothing

Use the Pi `mosquitto_sub` command to verify the exact topic. Compare every
configured header with the raw JSON and inspect the relevant service log.

### LabPulse says records are stale or from the future

Compare Windows `Get-Date` with Pi `date`. Confirm `.vcl` `Time(secs)` is
current. Increase age limits only when the logfile genuinely updates slower.

### The task works manually but not at startup

Check that the task runs as the Python-owning user, the wrapper uses the full
`python.exe` path, **Start in** is correct, that account can read the Triton
logs and password, and Task Scheduler stored the account password.

### The Pi cannot ping the control PC

That is normally the Archer WAN firewall working correctly. The required path
is control PC to Pi TCP 8883. Do not add DMZ or forwarding rules for reverse
ping.
