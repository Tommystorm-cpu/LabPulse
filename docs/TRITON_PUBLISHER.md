# Triton refrigerator setup

This guide connects two Oxford Instruments Triton control PCs to LabPulse so
their `.vcl` logfile readings appear on the dashboard. It describes the lab's
specific two-fridge arrangement, including its TP-Link Archer D2 routers and
network addresses. Check that your installation matches before following it;
another lab needs a network plan for its own equipment.

You'll first run a publisher by hand to check the readings, then arrange for
Windows to run the production publisher automatically. A publisher is the
small program that reads the logfile and sends its values to LabPulse.

Follow the sections in order. Instructions marked **repeat for each fridge**
are performed once for Triton 1 and once for Triton 2. Instructions marked
**once** configure both refrigerators together and must not be repeated.

> [!CAUTION]
> Do not change the LAN address, subnet mask, default gateway, DNS, DHCP, or
> cabling already used by a Triton control PC, workstation, magnet supply, or
> other laboratory device. This installation reuses each refrigerator's
> existing isolated LAN and changes only the Archer WAN settings plus one
> Windows host route. Perform the first router and route changes locally, not
> through Remote Desktop, and verify remote access afterwards.

## What this installation does

```text
Existing Triton LAN -- unchanged
  |-- Triton Windows control PC
  |-- Triton workstation and laboratory devices
  `-- Archer D2 LAN -> Archer firewall/NAT -> Archer WAN
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
The router treats the Pi as an untrusted WAN device: it permits return traffic
for a connection started by the control PC but must block every new connection
started from the Pi side towards the control-PC LAN.

### Security boundary and threat model

The **LAN** is each fridge's private network. The router's **WAN** port faces
the separate Pi-side network. These must stay on the correct sides of the
router. The **security boundary** is the equipment and configuration that
prevent the Pi from starting connections into a fridge's private network.

Assume that the Pi, its operating system, every container, and every device on
the Pi-side switch are hostile. No Pi setting is a security control. In
particular, Pi firewall rules, Docker rules, routes, and
`net.ipv4.ip_forward` must not be used to protect a Triton LAN.

Each Archer and the physical WAN/LAN separation are the security boundary. A
compromised Pi may send arbitrary packets, ignore its configured routes, proxy
traffic in user space, or report false test results. It must still be unable to
initiate a connection through either Archer into a Triton LAN. If laboratory IT
does not accept the Archer model and firmware as that boundary, replace it with
an approved externally managed firewall before connecting the Pi.

TLS encrypts MQTT connections, certificates identify the server, and an ACL
(access-control list) says which topics each account may use.
MQTT TLS, passwords, ACLs, and topic restrictions remain useful for normal
operation, but they are implemented by or terminate on the Pi. They cannot
constrain a compromised Pi and are not part of the Triton network boundary.

This is monitoring, not a safety interlock. Existing refrigerator protections
and operating procedures remain essential.

## Implementation sequence

| Phase | Where | Frequency | Work |
|---|---|---|---|
| A | Each Archer and control PC | Repeat for Triton 1 and Triton 2 | Sections 1–3: cabling, router WAN, boundary test, and Windows host route |
| B | Trusted admin computer and LabPulse Pi, with a check from each control PC | Once for both fridges | Sections 4–7: both Pi addresses, both link checks, one certificate set, both MQTT accounts, ACL, and listener |
| C | Each control PC, with checks on the Pi | Repeat for Triton 1 and Triton 2 | Sections 8–9: install and commission each publisher |
| D | LabPulse Pi | Once for both fridges | Section 10: add both services to the live LabPulse configuration |
| E | Each control PC | Repeat for Triton 1 and Triton 2 | Sections 11–12: production publisher and Task Scheduler |
| F | LabPulse Pi and Home Assistant | Once after both fridges work | Section 13: enable and test alarms |

Complete both copies of a repeatable phase before moving to the next phase.
Use the Triton-specific values in the address table throughout.

## Addresses and identities used here

Use these values consistently. Do not give both refrigerators the same MQTT
topic or username.

| Setting | Triton 1 | Triton 2 |
|---|---|---|
| Existing Archer LAN address | `192.168.1.1/24` | `192.168.1.1/24` |
| Existing workstation address | `192.168.1.100/24` | `192.168.1.100/24` |
| Existing Triton control-PC address | `192.168.1.102/24` | `192.168.1.101/24` |
| Existing vector-magnet supply | `192.168.1.103/24` | not listed |
| Archer WAN address | `10.50.1.2/30` | `10.50.2.2/30` |
| Pi address | `10.50.1.1/30` | `10.50.2.1/30` |
| MQTT username | `triton-01` | `triton-02` |
| MQTT topic | `labpulse/triton/triton-01/measurements` | `labpulse/triton/triton-02/measurements` |
| Heartbeat topic | `labpulse/triton/triton-01/heartbeat` | `labpulse/triton/triton-02/heartbeat` |
| Availability topic | `labpulse/triton/triton-01/availability` | `labpulse/triton/triton-02/availability` |
| MQTT TLS port | `8883` | `8883` |

Treat the live `ipconfig /all`, route table, and laboratory network register as
the authority if they differ from this inventory. Do not “correct” an existing
adapter to match this table without checking locally.

Both Archers can keep `192.168.1.1/24` because their LAN sides are physically
separate. Never connect the two routers' LAN ports together. Their WAN sides
can share the unmanaged switch because they use different `10.50.x.x/30`
subnets.

This layout preserves the working laboratory LANs. The Windows steps add a
host route but do not change an adapter address or its existing configuration.

## Equipment and files required

- One TP-Link Archer D2 router per refrigerator. The tested unit is Archer D2
  V1 EU with firmware `1.4.0 ... Build 160216`.
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

## Phase A — repeat for each fridge

Complete sections 1–3 for one refrigerator, then perform them again for the
other. Keep the Pi disconnected from the WAN-side switch until both Archers
have passed the independent boundary test.

## 1. Cable one refrigerator — repeat for each fridge

For the refrigerator currently being commissioned:

1. Leave all existing Archer LAN, Triton control-PC, workstation, controller,
   magnet-supply, and remote-access cables exactly as they are.
2. Confirm that the Archer WAN port is currently unused and that no Internet,
   university-network, VPN, or remote-access path depends on it. Stop if it is
   already connected or configured for another purpose; do not repurpose it.
3. Configure LAN 4/WAN as the Archer's WAN port and connect it to the isolated
   switch.
4. Keep the Pi's fridge-facing Ethernet cable disconnected until both Archers
   pass the independent boundary test in section 2.5.
5. Never connect a router LAN port directly to the Pi-side switch.

The Archer may display **No Internet connection**. That is expected: its WAN
is an isolated route to LabPulse, not an Internet service.

## 2. Configure the Archer D2 — repeat for each fridge

Log in to the existing Archer at `http://192.168.1.1` from its Triton
workstation. The tested firmware has **Basic** and **Advanced** tabs across the
top. Export or photograph the existing router settings before making changes.

### 2.1 Select router mode

1. Open **Advanced**.
2. Select **Operation Mode**.
3. Verify that **Wireless Router Mode** is already selected.

Do not change the mode during commissioning. If the router is not already in
Wireless Router Mode, stop and assess the existing laboratory network before
continuing. Router mode provides the WAN-to-LAN firewall/NAT boundary that
protects the control PC from the Pi-side network.

### 2.2 Verify the LAN without changing it

1. Open **Advanced > Network > LAN Settings**.
2. Confirm the existing router address is `192.168.1.1`.
3. Confirm the existing subnet mask is `255.255.255.0`.
4. Record the DHCP and address-reservation settings without altering them.

Do not save changes on this page. Both Archers may use the same LAN settings
because the two LANs are physically isolated; it is not safe to join them
together.

### 2.3 Configure the WAN

Open **Advanced > Network > Internet**, select **Static IP**, and enter the
values for this refrigerator.

Only continue if the preflight check confirmed that this WAN configuration is
unused. Photograph or export its current settings first so the change can be
reversed locally if an unexpected dependency appears.

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

Do not rely on this configuration review alone. Prove the boundary from an
independent device using the test below before reconnecting the Pi.

### 2.5 Test the boundary without trusting the Pi

Perform this test separately for each Archer. Use a dedicated, approved test
laptop with no other active network connection:

1. Disconnect the Pi's fridge-facing Ethernet cable from the Pi-side switch.
   Leave the Archer WAN cable connected. If the Pi is not yet connected, leave
   it disconnected.
2. Connect the test laptop to that switch and temporarily give it the Pi
   address for the Archer under test: `10.50.1.1/30` or `10.50.2.1/30`. Do not
   configure a default gateway or DNS server.
3. Add a temporary route for `192.168.1.0/24` through that Archer's WAN address:
   `10.50.1.2` or `10.50.2.2`. This deliberately gives the test device the route
   a hostile Pi would use to attack the Triton LAN.
4. Confirm at layer 2, for example from the laptop's ARP or neighbour table,
   that the Archer WAN address resolves. This distinguishes a working cable
   from a firewall test that only appears to pass because nothing is connected.
5. With an approved network scanner, test all TCP ports on the Archer WAN
   address and on the known Triton LAN addresses, including `192.168.1.1`, the
   control PC, workstation, and any listed laboratory devices. Test known UDP
   services as required by laboratory IT. A failed ping alone is not evidence
   of isolation.
6. Treat any reachable WAN administration service or any response establishing
   connectivity to a Triton LAN device as a failed boundary test. Stop, remove
   the test connection, and have laboratory IT correct or replace the Archer.
7. Remove the temporary route and address from the test laptop, disconnect the
   laptop, and leave the Pi disconnected. Test the other Archer when repeating
   this phase for the other refrigerator.

Record the test device, date, targets, scanner settings, and results. The test
must be performed again after an Archer reset, firmware change, replacement, or
security-related configuration change.

### 2.6 Preserve the workstation connection

Leave the Triton workstation's existing `192.168.1.100` address, gateway, DNS,
and cabling unchanged. If it also has a university or laboratory-network
adapter, do not remove or change that adapter's route. Do not enable Network
Bridge or Internet Connection Sharing between adapters.

## 3. Configure the Windows control PC — repeat for each fridge

The publisher uses the control PC's existing connection to its Archer LAN. No
new adapter or Windows IP address is required. Before adding the host route,
work locally at the control PC and save the existing configuration:

```powershell
ipconfig /all | Out-File "$env:USERPROFILE\Desktop\network-before-labpulse.txt"
route print -4 | Out-File -Append "$env:USERPROFILE\Desktop\network-before-labpulse.txt"
Get-NetAdapter | Format-Table -Auto Name,InterfaceDescription,Status,MacAddress,ifIndex
```

Identify the adapter carrying the existing Triton LAN address and record its
`ifIndex`:

- Triton 1 is expected to use `192.168.1.102`.
- Triton 2 is expected to use `192.168.1.101`.

Do not open that adapter's IPv4 properties and do not change its address,
subnet mask, gateway, DNS, metric, or DHCP setting. Confirm Triton operation
and remote access remain available before continuing.

### 3.1 Add the one route the publisher needs

Open **Command Prompt as Administrator**. A normal prompt reports
`The requested operation requires elevation`.

For Triton 1:

```cmd
route -p add 10.50.1.1 mask 255.255.255.255 192.168.1.1 metric 5 if 12
```

For Triton 2:

```cmd
route -p add 10.50.2.1 mask 255.255.255.255 192.168.1.1 metric 5 if 12
```

These examples use interface index `12`. Replace `12` with the actual `ifIndex`
of the existing Triton LAN adapter shown by `Get-NetAdapter`. Specifying it
prevents Windows from attaching the route to another adapter.

The `/32` route sends only the Pi MQTT address through the existing Archer. It
does not change the PC's address, gateway, DNS, or default route. Verify it:

```cmd
route print -4
ipconfig /all
```

The expected Triton 2 route is:

```text
Network Destination  Netmask          Gateway      Interface
10.50.2.1             255.255.255.255  192.168.1.1  192.168.1.101
```

### 3.2 Check that Windows is not bridging the refrigerator

In `ncpa.cpl`:

1. Confirm there is no **Network Bridge** object.
2. Open each relevant adapter's **Properties > Sharing** tab.
3. Ensure **Allow other network users to connect through this computer's
   Internet connection** is not selected.

`ipconfig /all` should report `IP Routing Enabled: No`. These checks stop
Windows from routing Pi-side traffic towards the refrigerator controller.

After both copies of Phase A are complete and both Archers have passed the
boundary test, connect the Pi's fridge-facing Ethernet interface to the
WAN-side switch.

## Phase B — configure shared infrastructure once

Complete sections 4–7 once. Section 5 starts on a trusted admin computer and
installs the resulting server files on the Pi. All other configuration in this
phase is performed on the Pi, with connectivity checks from both control PCs.

## 4. Configure both Pi-side addresses — Pi, once

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
```

Both Pi addresses must be present, neither link may supply the Pi default
route. If NetworkManager does not own the interface, stop and identify its
network manager first. A temporary `ip addr add` test does not survive reboot.

Docker may enable `net.ipv4.ip_forward=1` for container networking. Do not
change it as an isolation measure: a hostile Pi can forward or proxy traffic
regardless of that value, and disabling it may break Docker port publishing.
The independent Archer boundary test in section 2.5 is the security check.

### 4.1 Check connectivity in both directions

These quick checks give useful confirmation that the addresses, Windows host
routes, cables, and Archer directionality are working as intended. They do not
replace the independent boundary test in section 2.5 because the Pi is not a
trusted test device.

Run only the matching checks for the refrigerator currently being
commissioned, then repeat this section when commissioning the other one.

On the Triton 1 control PC, run in PowerShell:

```powershell
Test-NetConnection 10.50.1.1 -InformationLevel Detailed
```

On the Triton 2 control PC, use its Pi address instead:

```powershell
Test-NetConnection 10.50.2.1 -InformationLevel Detailed
```

`PingSucceeded` must be `True`. This confirms that the control PC's `/32` route
passes through its Archer to the correct Pi address. It does not test MQTT yet;
the TLS listener is enabled later in this guide.

For the reverse check, first add the matching explicit temporary route on the
Pi. It is required because both Triton LANs use `192.168.1.0/24`; without it, a
failed ping could have left through the wrong interface and would prove
nothing.

For Triton 1:

```bash
sudo ip route add 192.168.1.102/32 via 10.50.1.2 dev eth0
ip route get 192.168.1.102
ping -c 4 -W 2 192.168.1.102
sudo ip route del 192.168.1.102/32 via 10.50.1.2 dev eth0
```

For Triton 2:

```bash
sudo ip route add 192.168.1.101/32 via 10.50.2.2 dev eth0
ip route get 192.168.1.101
ping -c 4 -W 2 192.168.1.101
sudo ip route del 192.168.1.101/32 via 10.50.2.2 dev eth0
```

The `ip route get` result must show the intended Archer gateway and
fridge-facing interface. The ping must receive no replies; its summary should
report `0 received` and `100% packet loss`. A reply from the control PC is a
failed Archer boundary check: disconnect the Pi-side link and follow the fault
guidance at the end of this document. The final command removes the temporary
route; run it manually if the sequence is interrupted.

## 5. Create one MQTT TLS certificate set — trusted computer and Pi, once

The control PCs connect by IP address, so the server certificate must contain
both Pi IPs as Subject Alternative Names. Generate it on a trusted computer
with OpenSSL. Do not create or store the CA private key on the Pi.

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

The output must contain both Pi addresses. Transfer only `server.crt` and
`server.key` from the trusted computer to a temporary directory on the Pi. From
that directory on the Pi, install the server files:

```bash
mkdir -p ~/labpulse-live/mosquitto/config/certs
cp server.crt ~/labpulse-live/mosquitto/config/certs/server.crt
cp server.key ~/labpulse-live/mosquitto/config/certs/server.key
```

Copy only `labpulse-ca.crt` to the control PCs. Never copy `labpulse-ca.key` to
the Pi or a control PC. Store it offline because it can issue certificates
trusted by every Triton publisher. The server key is necessarily present on the
Pi and therefore cannot remain secret if the Pi is compromised.

## 6. Create both MQTT accounts and access rules — Pi, once

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
topic write labpulse/triton/triton-01/heartbeat
topic write labpulse/triton/triton-01/availability

user triton-02
topic write labpulse/triton/triton-02/measurements
topic write labpulse/triton/triton-02/heartbeat
topic write labpulse/triton/triton-02/availability
```

Each account can publish only its own three topics and cannot subscribe. Set file
permissions:

```bash
sudo chown 1883:1883 \
  ~/labpulse-live/mosquitto/config/certs/server.key \
  ~/labpulse-live/mosquitto/config/external-passwords
sudo chmod 600 \
  ~/labpulse-live/mosquitto/config/certs/server.key \
  ~/labpulse-live/mosquitto/config/external-passwords
sudo chmod 644 \
  ~/labpulse-live/mosquitto/config/certs/server.crt \
  ~/labpulse-live/mosquitto/config/external-acl
```

Use unique MQTT passwords created only for this deployment; never reuse a
Windows, laboratory, or other service credential. The broker receives these
credentials, so a hostile Pi may capture them. TLS protects them from other
devices observing the link, but it does not make the Pi trustworthy.

To reset a password later, use `mosquitto_passwd` without `-c`, update that
PC's password file, and run `labpulse restart mosquitto`.

## 7. Enable the listener for both Pi addresses — Pi, once

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

Run the matching command on each control PC in **PowerShell**, not Command
Prompt.

Triton 1:

```powershell
Test-NetConnection 10.50.1.1 -Port 8883
```

Triton 2:

```powershell
Test-NetConnection 10.50.2.1 -Port 8883
```

`TcpTestSucceeded : True` on both PCs proves each route, router, Pi address,
Docker binding, and TCP listener. The publishers test TLS and authentication
next.

## Phase C — commission both Windows publishers

Complete sections 8–9 on one control PC and then on the other. The Pi-side
subscriber command in section 9 is a test command, not another Pi
configuration step.

## 8. Install the publisher — repeat on each control PC

Create `C:\ProgramData\LabPulse\TritonPublisher` and copy into it:

- `triton_logfile_publisher_setup.py`
- `triton_logfile_publisher_production.py`
- `run_triton_publisher.example.ps1`, renamed to
  `run_triton_publisher.ps1`
- `labpulse-ca.crt`
- `mqtt-password.txt`, containing only this PC's MQTT password on one line

On each control PC, both `user` and `admin` may access the folder. Open
**Command Prompt as Administrator**:

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

## 9. Run the commissioning publisher — repeat for each fridge

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
punctuation, and units are significant. Leave both commissioning publishers
running until section 10 is complete, then stop each one with `Ctrl+C`.

## Phase D — add both services to LabPulse once

After both commissioning publishers have produced a payload, complete section
10 in one `labpulse config` session on the Pi.

## 10. Add both Triton services — Pi, once

Keep global notifications muted during commissioning. Run `labpulse config`
once and add one service under the existing `services:` mapping for each
fridge. Use these identities and the exact headers captured from each
publisher:

| Field | Triton 1 | Triton 2 |
|---|---|---|
| Service key | `triton_01` | `triton_02` |
| Setup key | `triton_1` | `triton_2` |
| MQTT topic | `labpulse/triton/triton-01/measurements` | `labpulse/triton/triton-02/measurements` |
| Service log | `labpulse-triton-01` | `labpulse-triton-02` |

Add both setups and both services in the same edit. The source names below are
examples; use each fridge's exact captured headers if they differ:

```yaml
setups:
  triton_1:
    label: Triton 1
    icon: mdi:snowflake-thermometer
    order: 50
  triton_2:
    label: Triton 2
    icon: mdi:snowflake-thermometer
    order: 51

services:
  triton_01:
    label: Triton 1 Fridge
    service_health:
      offline_confirm_seconds: 120
    driver:
      type: labpulse.mqtt_json
      options:
        topic: labpulse/triton/triton-01/measurements
        heartbeat_topic: labpulse/triton/triton-01/heartbeat
        heartbeat_timeout_seconds: 60
        maximum_record_age_seconds: 120
    measurement_defaults:
      setups: [triton_1]
      alarmed: false
    measurements_file: config.d/triton-01-measurements.yaml
    maximum_measurement_age_seconds: 180

  triton_02:
    label: Triton 2 Fridge
    service_health:
      offline_confirm_seconds: 120
    driver:
      type: labpulse.mqtt_json
      options:
        topic: labpulse/triton/triton-02/measurements
        heartbeat_topic: labpulse/triton/triton-02/heartbeat
        heartbeat_timeout_seconds: 60
        maximum_record_age_seconds: 120
    measurement_defaults:
      setups: [triton_2]
      alarmed: false
    measurements_file: config.d/triton-02-measurements.yaml
    maximum_measurement_age_seconds: 180
```

Open the master and both fragments together so they are validated and applied
as one candidate bundle:

```bash
labpulse config config.yaml \
  config.d/triton-01-measurements.yaml \
  config.d/triton-02-measurements.yaml
```

Put only the mapping below in each fridge's fragment. Use the exact captured
headers for that fridge; do not add a surrounding `measurements:` key:

```yaml
mixing_chamber_temperature:
  source: "Mixing Chamber T(K)"
  unit: K
  device_class: temperature
cold_plate_temperature:
  source: "Cold Plate T(K)"
  unit: K
  device_class: temperature
condense_pressure:
  source: "P2 Condense (Bar)"
  unit: bar
  device_class: pressure
  required: false
```

Rules:

- Stable IDs use lowercase letters, numbers, and underscores.
- Every MQTT JSON measurement needs one unique `source` header matching the
  captured JSON exactly, including capitalization, spaces, punctuation, and
  units.
- Use internal `mosquitto:1883`, not the external Pi address and port.
- Required readings create an incident when absent; optional readings remain
  visible without a missing-reading incident. Missing mapped fields still cause
  an MQTT JSON driver fault and **Needs attention**, while valid fields continue
  updating. Optional readings can still produce numeric threshold alarms.
- Start with `alarmed: false` and enable thresholds only after commissioning.
- Increase the two age limits if Triton genuinely writes records more slowly.
- The foreground setup publisher does not send heartbeats. With the heartbeat
  fields above, each service will show Offline until its production publisher
  starts in section 11; leave notifications muted through that switch.

Do not duplicate `services:` or `setups:`. Saving `labpulse config` validates
the complete source bundle, writes the standalone `config.resolved.yaml`,
regenerates, and starts both services. Inspect them:

```bash
labpulse ps
labpulse logs --tail 100 labpulse-triton-01
labpulse logs --tail 100 labpulse-triton-02
```

If readings remain unavailable, check the publisher, raw Pi subscriber, exact
header spelling, both clocks, record age, and the service log—in that order.

## Phase E — make both publishers permanent

Complete sections 11–12 on one control PC and then repeat them on the other.

## 11. Switch to the production publisher — repeat on each control PC

Stop the setup publisher. Edit `run_triton_publisher.ps1`. For Triton 2 it
should use the real values below; substitute the exact Python and logfile paths:

```powershell
$ErrorActionPreference = "Stop"

$publisherDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonExecutable = "C:\Users\user\AppData\Local\Programs\Python\Python311\python.exe"
$tritonLogDirectory = "D:\Oxford Instruments\Triton\LogFiles"
$brokerName = "10.50.2.1"
$mqttTopic = "labpulse/triton/triton-02/measurements"
$heartbeatTopic = "labpulse/triton/triton-02/heartbeat"
$mqttUsername = "triton-02"
$passwordFile = Join-Path $publisherDirectory "mqtt-password.txt"
$caCertificate = Join-Path $publisherDirectory "labpulse-ca.crt"
$operationalLog = Join-Path $publisherDirectory "triton-publisher.log"

& $pythonExecutable (Join-Path $publisherDirectory "triton_logfile_publisher_production.py") `
    --directory $tritonLogDirectory `
    --broker $brokerName `
    --port 8883 `
    --topic $mqttTopic `
    --heartbeat-topic $heartbeatTopic `
    --username $mqttUsername `
    --password-file $passwordFile `
    --ca-certificate $caCertificate `
    --log-file $operationalLog

if ($LASTEXITCODE -ne 0) {
    throw "Triton logfile publisher exited with code $LASTEXITCODE"
}
```

On Triton 1, set `$brokerName` to `10.50.1.1`, `$mqttTopic` to
`labpulse/triton/triton-01/measurements`, `$heartbeatTopic` to
`labpulse/triton/triton-01/heartbeat`, and `$mqttUsername` to `triton-01`.
Keep the Triton 2 values shown above on its control PC.

Run it manually as the ordinary user:

```powershell
powershell.exe -NoProfile -File "C:\ProgramData\LabPulse\TritonPublisher\run_triton_publisher.ps1"
```

In a second window:

```powershell
Get-Content "C:\ProgramData\LabPulse\TritonPublisher\triton-publisher.log" -Tail 50 -Wait
```

Confirm connection, publication, and a heartbeat, then stop the manual run.
The production publisher reconnects with backoff, uses acknowledged
non-retained QoS 1 measurement and heartbeat messages, publishes retained
availability with a Last Will, validates data, and rotates its 5 MiB
operational log with three backups. A quiet or unreadable logfile does not
stop heartbeats; it does stop fresh measurement publication.
After a Pi subscriber or broker restart, the fridge service shows Needs
attention while awaiting its first new heartbeat rather than claiming the
publisher is healthy from an old retained message.

## 12. Configure Task Scheduler — repeat on each control PC

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

## Phase F — finish on the Pi once

Complete section 13 after both scheduled publishers and both LabPulse services
have passed commissioning.

## 13. Enable alarms after commissioning — Pi, once

Leave notifications muted while checking values, units, timestamps, and
availability policies. For readings needing thresholds:

1. Change `alarmed: false` to `alarmed: true` with `labpulse config`.
2. Configure sensible thresholds on the generated Home Assistant alarm page.
3. Test notification routing in test mode.
4. Test **Resend active alert** on a controlled active condition if required.
5. Unmute readings and then global notifications only when testing is complete.

Optional missing readings should show **No recent data — optional** without a
missing-reading incident; their driver fault can still affect service health.
One complete MQTT failure should become one service-level incident,
not one notification for every reading.

## Final acceptance checklist

### Complete for each fridge

1. The original Archer LAN, control PC, workstation, controller, magnet-supply,
   gateway, DNS, DHCP, and remote-access settings are unchanged.
2. The Archer WAN has the matching `/30` address from the address table.
3. The only new Windows network setting is the persistent `/32` Pi route
   through the existing Archer and correct existing LAN interface.
4. Windows has no Network Bridge, Internet Connection Sharing, or IP routing.
5. The Archer has no forwarding, DMZ, UPnP, or WAN-management rules.
6. The independent WAN-side boundary test cannot reach WAN administration or
   any device on the Triton LAN, and its method and results are recorded.
7. The production publisher runs from Task Scheduler and returns automatically
   after a control-PC or router reboot.

### Complete once on the Pi

1. Both Pi `/30` addresses survive reboot and neither supplies a default route.
2. The certificate contains both Pi addresses, and its CA private key is stored
   offline rather than on the Pi or either control PC.
3. Both MQTT users exist, and the ACL restricts each user to its own write-only
   topic.
4. The TLS listener is bound only to `10.50.1.1:8883` and
   `10.50.2.1:8883`.
5. Both `triton_01` and `triton_02` services are present in the live LabPulse
   configuration and survive a Pi reboot.

### Check end to end for both fridges

1. Each control PC can ping its Pi `/30` address, while correctly routed
   Pi-to-control-PC probes receive no replies.
2. `Test-NetConnection <Pi-address> -Port 8883` succeeds on both control PCs.
3. Wrong MQTT credentials and untrusted certificates are rejected.
4. JSON timestamps are current and mapped headers match exactly.
5. Home Assistant displays plausible values, units, and availability policy.
6. Stopping one scheduled publisher produces one eventual service incident,
   and starting it restores that service once. Readings recover when Triton
   supplies a fresh record; the heartbeat does not refresh old readings.

## Upgrade an existing two-fridge installation

Use a released LabPulse version containing this feature on the Pi. Keep global
notifications muted until both control PCs have been upgraded and verified.
Do not change the original Triton LAN, host routes, certificates, or passwords.

On the Pi, record the installed version and back up the two files you will edit:

```bash
labpulse version
cp -p ~/labpulse-live/config.yaml ~/labpulse-live/config.yaml.pre-heartbeat
cp -p ~/labpulse-live/mosquitto/config/external-acl \
  ~/labpulse-live/mosquitto/config/external-acl.pre-heartbeat
labpulse update VERSION_WITH_HEARTBEAT
```

Replace `VERSION_WITH_HEARTBEAT` with the published release version. Edit the
ACL with `nano ~/labpulse-live/mosquitto/config/external-acl` so each account
can write only its own `measurements`, `heartbeat`, and `availability` topics,
as shown in section 6. Reload it and inspect the broker:

```bash
labpulse restart mosquitto
labpulse logs --tail 100 mosquitto
```

On each Windows control PC, use PowerShell as the account that owns the
scheduled task. Replace `C:\CHANGE_ME\LabPulse\firmware` with the directory
containing the new release files:

```powershell
$publisherDirectory = 'C:\ProgramData\LabPulse\TritonPublisher'
$releaseFirmwareDirectory = 'C:\CHANGE_ME\LabPulse\firmware'
Stop-ScheduledTask -TaskName 'LabPulse Triton Publisher'
Copy-Item -LiteralPath (Join-Path $publisherDirectory 'triton_logfile_publisher_production.py') `
  -Destination (Join-Path $publisherDirectory 'triton_logfile_publisher_production.py.pre-heartbeat')
Copy-Item -LiteralPath (Join-Path $publisherDirectory 'run_triton_publisher.ps1') `
  -Destination (Join-Path $publisherDirectory 'run_triton_publisher.ps1.pre-heartbeat')
Copy-Item -LiteralPath (Join-Path $releaseFirmwareDirectory 'triton_logfile_publisher_production.py') `
  -Destination (Join-Path $publisherDirectory 'triton_logfile_publisher_production.py') -Force
```

Edit the existing `run_triton_publisher.ps1`: retain its real Python executable,
log directory, broker address, MQTT account, password file, CA certificate,
and measurement topic. Add `$heartbeatTopic` beside `$mqttTopic` and pass
`--heartbeat-topic $heartbeatTopic` beside `--topic $mqttTopic`, as in section
11. Use `triton-01` on the first PC and `triton-02` on the second. The heartbeat
interval defaults to 15 seconds; do not make it longer than the Pi timeout.
Run once in the foreground, then restart the scheduled task:

```powershell
powershell.exe -NoProfile -File 'C:\ProgramData\LabPulse\TritonPublisher\run_triton_publisher.ps1'
Get-Content 'C:\ProgramData\LabPulse\TritonPublisher\triton-publisher.log' -Tail 50
Start-ScheduledTask -TaskName 'LabPulse Triton Publisher'
Get-ScheduledTaskInfo -TaskName 'LabPulse Triton Publisher'
```

Stop the foreground run with Ctrl+C before starting the task. On the Pi, verify
a new heartbeat and retained online availability for each fridge:

```bash
docker exec labpulse-mqtt mosquitto_sub -h 127.0.0.1 -p 1883 \
  -t 'labpulse/triton/triton-01/heartbeat' -C 1 -v
docker exec labpulse-mqtt mosquitto_sub -h 127.0.0.1 -p 1883 \
  -t 'labpulse/triton/triton-02/heartbeat' -C 1 -v
docker exec labpulse-mqtt mosquitto_sub -h 127.0.0.1 -p 1883 \
  -t 'labpulse/triton/triton-01/availability' -C 1 -v
docker exec labpulse-mqtt mosquitto_sub -h 127.0.0.1 -p 1883 \
  -t 'labpulse/triton/triton-02/availability' -C 1 -v
```

Now run `labpulse config` on the Pi and add each service's exact
`heartbeat_topic` and `heartbeat_timeout_seconds: 60` from section 10. Set
`notify_on_service_failure: false` only on hubs whose service outage should
remain visible without Home Assistant/SMS delivery; it defaults to true. Check:

```bash
labpulse ps
labpulse logs --tail 100 labpulse-triton-01
labpulse logs --tail 100 labpulse-triton-02
```

With test-mode recipients and global notifications still controlled, stop one
Windows scheduled task. Its own service should become Offline and open one
incident after the Last Will plus the 120-second service confirmation, or after
the 60-second heartbeat timeout followed by that confirmation. The other fridge
should stay unaffected. Start
the task and verify a single recovery after the 15-second recovery confirmation.
Repeat for the other fridge. A quiet logfile with continuing heartbeats should
leave the publisher online while old readings expire; required missing-reading
alerts are governed separately. Unmute only after these checks pass.

### Roll back the heartbeat deployment

Keep notifications muted during rollback. On each Windows PC, stop the task,
restore its backed-up script and wrapper, then restart it:

```powershell
$publisherDirectory = 'C:\ProgramData\LabPulse\TritonPublisher'
Stop-ScheduledTask -TaskName 'LabPulse Triton Publisher'
Copy-Item -LiteralPath (Join-Path $publisherDirectory 'triton_logfile_publisher_production.py.pre-heartbeat') `
  -Destination (Join-Path $publisherDirectory 'triton_logfile_publisher_production.py') -Force
Copy-Item -LiteralPath (Join-Path $publisherDirectory 'run_triton_publisher.ps1.pre-heartbeat') `
  -Destination (Join-Path $publisherDirectory 'run_triton_publisher.ps1') -Force
Start-ScheduledTask -TaskName 'LabPulse Triton Publisher'
```

On the Pi, restore the saved live config and ACL, regenerate, and reload the
broker. This disables heartbeat monitoring while leaving the newer LabPulse
package installed. If a complete package rollback is necessary, use
`labpulse update PREVIOUS_VERSION` with the version recorded before upgrading.
If either live file has been edited since its backup, remove only the new
heartbeat fields or ACL topic lines in `labpulse config` or `nano` instead of
overwriting those later changes with the snapshot.

```bash
cp -p ~/labpulse-live/config.yaml.pre-heartbeat ~/labpulse-live/config.yaml
cp -p ~/labpulse-live/mosquitto/config/external-acl.pre-heartbeat \
  ~/labpulse-live/mosquitto/config/external-acl
labpulse config
labpulse restart mosquitto
labpulse ps
```

## Quick fault guide

### `Test-NetConnection` reports `PingSucceeded: False`

Do not continue to MQTT setup. Check the control PC's persistent `/32` route,
the Archer WAN address, the Pi `/30` address, and the WAN-side cabling. Repeat
the test until the control PC can ping its corresponding Pi address.

### `Test-NetConnection -Port 8883` is false

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

### A reverse ping succeeds or the independent test reaches a protected device

The Archer boundary has failed. Disconnect the Pi-side switch from that Archer
and do not reconnect the Pi. Recheck that the cable uses the Archer WAN port,
the Archer is in router mode, and port forwarding, DMZ, UPnP, WAN management,
CWMP, and SNMP are disabled. If any protected LAN address remains reachable,
have laboratory IT replace or reconfigure the boundary device. Do not use a Pi
firewall rule or `net.ipv4.ip_forward` change as the fix.
