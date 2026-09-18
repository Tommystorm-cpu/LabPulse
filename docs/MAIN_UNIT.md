# The Raspberry Pi main unit

The main unit is the computer at the centre of LabPulse. It runs the dashboard,
receives readings from the Arduino hubs, and uses a cellular modem to send SMS.
Its UPS (uninterruptible power supply) keeps the Pi running through a power
interruption and reports the battery and external-power state.

This page combines the repository, July–August 2026 CAD discussions, and a
maintainer update on 18 September 2026. The update confirms the X1200 UPS and
the planned hub power supply, and records a shopping email for further parts.
The SHT40 connections are not installed yet. The current case has been printed
but is awaiting key parts before assembly. It uses a 7-inch Raspberry Pi Touch
Display 2; the earlier CAD discussions below remain design history.

For the remote sensor hubs, see [Hardware](HARDWARE.md#sensor-hub-parts).
For the software installation, use [Installation](INSTALLATION.md).

If you're identifying an existing unit, start with [the parts list](#parts-in-the-main-unit)
and [connections](#how-the-connections-fit-together). If you're continuing the
case design, start with [the CAD files and build status](#enclosure-files-and-build-status),
then read [the enclosure history](#enclosure-history). The [build notes](#finish-the-build-record) explain what to include if
you share a finished version of the case.

## Parts in the main unit

The current consolidated [purchasing workbook](LabPulse%20Purchasing.xlsx)
includes supplier links, requested additions, and separately labelled earlier
choices. Prices retained from the old lists are historical, not current quotes.

“Purchased” below comes from [the archived purchase workbook](../legacy/Documentation/purchasing-2026-09-18/Internship%20purchased%20items.xlsx),
Sheet1. “Later list” means [Mini Shopping List](../legacy/Documentation/purchasing-2026-09-18/Mini%20Shopping%20List.xlsx),
Sheet1. The [enclosure history](#enclosure-history) identifies the supporting chats.

| Part | Role | What the records establish |
|---|---|---|
| Raspberry Pi 5, 8 GB | Runs LabPulse, MQTT, and Home Assistant | Purchased, row 2. The July acceptance record identifies the tested Pi as Model B Rev 1.1. |
| Raspberry Pi 5 Active Cooler | Cools the Pi | Purchased, row 13; included in the CAD component list. |
| Geekworm/SupTronics X1200 UPS | Pi power backup and battery monitoring | Confirmed by the maintainer on 18 September 2026. This is the UPS supported by `labpulse.x1200`. |
| Two 18650 cells for the X1200 | Stored energy for the UPS | The board has two cell holders. The fitted cell manufacturer, capacity, and age aren't recorded in these lists; use the X1200 instructions when choosing replacements. |
| Waveshare SIM7600E-H 4G HAT | SMS modem | Purchased, row 11. Record the PCB revision as well as the modem name. |
| Waveshare USB3.2 Gen1 HUB 2IN–4OUT | Accessible USB connections for Arduino hubs | Explicitly identified as already owned in the August CAD chat. The design keeps its metal casing. |
| DFRobot DFR0566 Gravity IO Expansion HAT | Accessible Pi GPIO and I2C connections | Later list, row 4; the August chat reports the bought board's cable mismatch. |
| 40-pin male-to-female GPIO ribbon, 150 mm (Gertboard type) | Lets the Gravity board sit away from the Pi stack | Later list, row 6; used in the enclosure plan. |
| Adafruit Sensirion SHT40 STEMMA QT/Qwiic breakout | Room temperature and humidity | Not connected yet, as reported on 18 September 2026. The starter `room_environment` service uses the Pi SHT40 driver. Planned cables are listed below. |
| Raspberry Pi Touch Display 2, 7-inch | Local Pi access | Confirmed by the maintainer on 18 September 2026, superseding the Waveshare CAD reference. The standoffs on this unit were removed by wiggling them off with pliers; see the enclosure notes below. |
| M2.5 screws, spacers, and standoffs | Board mounting | Original list includes Wurth 971160151 male–female 16 mm standoffs, a nylon assortment, and a GPIO riser. The July chat separately identifies Wurth 970160155 female–female 16 mm standoffs as being used. They aren't interchangeable in every mounting position. |

A HAT is an add-on board shaped to mount on the Pi. The name doesn't mean every
HAT in this enclosure has to plug into the Pi's 40-pin header.

The original list's **Waveshare UPS HAT (A)** is marked “DON'T USE THIS ONE”.
It was superseded by the X1200. It also lists three Gembird UHB-U2P4-04 USB hubs;
these belong to the earlier purchases, not the later Waveshare enclosure plan.
The [July acceptance record](../testing/real_hardware/ACCEPTANCE_2026-07-27.md) reports a
faulty external hub, but doesn't identify its model.

## Additional parts requested

The maintainer supplied these shopping-email links on 18 September 2026 for
parts awaiting arrival or documentation. This records the selected parts and
their intended jobs; it does not establish that each has arrived or been fitted.

| Requested part | Intended use |
|---|---|
| [500 mm display adapter cable for Pi 5](https://thepihut.com/products/display-adapter-cable-for-raspberry-pi-5?variant=42531573891267) | Replace the short cable supplied with the display. The requested length is 500 mm. |
| [USB power breakout for Raspberry Pi Touch Display 2](https://thepihut.com/products/usb-power-breakout-for-raspberry-pi-touch-display-2) | Supply Touch Display 2 power from USB, avoiding a power lead to the GPIO connections outside the case. This is a power adapter; the display still needs its DSI connection. |
| [12 V, 2 A mains supply with 2.1 mm barrel plug](https://thepihut.com/products/12v-2a-power-supply-with-2-1mm-barrel-jack) | External power for the USB hub. See the outage plan below. |
| [STEMMA QT/Qwiic JST-SH to male headers cable](https://thepihut.com/products/stemma-qt-qwiic-jst-sh-4-pin-to-premium-male-headers-cable) | Connect an SHT40 to the compressed-air Arduino for main-lab temperature and humidity. |
| [300 mm STEMMA QT/Qwiic JST-SH cable](https://thepihut.com/products/stemma-qt-qwiic-jst-sh-4-pin-cable-300mm-long) | Planned Pi-side SHT40 lead: retain the sensor-end JST-SH plug, cut off the other plug, and solder the four wires to a single four-position female header for the Gravity board's I2C pins. Not yet assembled. |
| Four-position female header from the requested header pack; exact product unspecified | Terminate the modified SHT40 lead as one connector instead of four separate female jumper sockets. Match the board's pin spacing and use a header with solderable terminals. |

## How the connections fit together

The intended arrangement keeps permanent internal connections on the Pi and
puts the removable Arduino connections on the powered hub. This is a
connection overview, not a circuit or a drawing of the finished case.

```text
Raspberry Pi 5
  USB ---------------- SIM7600E-H modem (permanent connection)
  USB ---------------- Waveshare hub ----- Arduino sensor hubs
  40-pin GPIO ribbon - Gravity board ----- planned room SHT40 connection
  DSI ---------------- Raspberry Pi Touch Display 2
  USB power breakout - Touch Display 2 power (planned)
  underside contacts - X1200 UPS and its battery monitor
```

DSI is the Pi's display connection. A display also needs its specified power
connection; the diagram doesn't imply that the DSI cable supplies everything.

Label the hub's selected upstream connection (the connection back to the Pi)
and each downstream Arduino lead. This hub can switch between two hosts, so
switching away from the Pi would disconnect its sensors from LabPulse. Use the
manufacturer-specified host cable and leave the selection on the Pi.
[Waveshare hub reference](https://www.waveshare.com/usb3.2-gen1-hub-2in-4out.htm).

On the Pi, identify Arduino hubs by `/dev/serial/by-id/...`, not by whichever
`ttyACM` or `ttyUSB` number they happen to receive. The [first-sensor guide](FIRST_SENSOR.md)
walks through assigning those paths. SMS uses the host's ModemManager service;
see [SMS delivery](USER_GUIDE.md#sms-delivery-details) for the software boundary.

## Power and shared GPIO pins

The X1200 mounts **underneath** the Pi and connects through spring-loaded
contacts, often called pogo pins. It leaves the top header physically available,
but still uses some of its signals. Follow the [X1200 installation instructions](https://wiki.geekworm.com/X1200)
for its supply and cells: power enters the X1200's USB-C socket, and the vendor
says not to power the Pi through its own USB-C socket in this arrangement.

The [X1200 pin allocation](https://wiki.geekworm.com/X1200_Hardware) is:

| Signal | BCM GPIO | Physical header pin | LabPulse use |
|---|---:|---:|---|
| I2C data, SDA | 2 | 3 | Battery gauge; also shared with the room SHT40 |
| I2C clock, SCL | 3 | 5 | Clock for those I2C devices |
| External-power detection | 6 | 31 | High means external power present; low means it has failed |
| Charging control | 16 | 36 | Used by the UPS hardware; the LabPulse X1200 driver does not control charging |

Reserve GPIO6 and GPIO16 when adding other connections. The [driver](../src/labpulse/hardware/drivers/x1200.py)
defaults to I2C bus 1, gauge address `0x36`, and GPIO6 with high meaning power
present. Its settings and required measurement names are in
[Configuration](CONFIGURATION.md#geekworm-x1200-ups).

The modem can communicate over USB. In this layout it should be mechanically
mounted on spacers without electrically stacking its GPIO header onto the Pi
or Gravity board. The modem's optional `PWR–D6` control would compete with the
UPS's GPIO6 use. Newer SIM7600 HATs have a `PWR–3V3` automatic-start option;
check the actual board revision and jumper positions before relying on it.
[Waveshare modem reference](https://www.waveshare.com/wiki/SIM7600E-H_4G_HAT).

The hub power arrangement is decided: use the **12 V, 2 A mains supply** in the
[additional parts list](#additional-parts-requested) for normal operation.
Waveshare specifies 7–36 V for the hub's external power input and 5 V for its
USB host inputs. The X1200's approximately 5 V output is not a supply for that
7–36 V input. [Waveshare power specifications](https://www.waveshare.com/usb3.2-gen1-hub-2in-4out.htm).

During a mains outage, the intended fallback is for the X1200 to keep the Pi
running and for the Pi to supply the hub and Arduino sensors through USB.
The external 12 V supply has no battery backup. This fallback is the design
intent, not yet a recorded test of uninterrupted operation with all sensors
connected. Check whether devices remain powered or disconnect and recover when
external power is lost and restored before describing it as seamless backup.

## Gravity board and room sensor

The Gravity board moves the connections somewhere accessible instead of making
the Pi stack taller. In the later enclosure plan it sits above the screen,
connected to the Pi by the 150 mm GPIO ribbon.

The shopping-list **Qwiic-to-Gravity JST-SH-to-JST-PH cable did not fit this
board**. That was the starting point of the August chat. Don't repeat the
purchase assuming that “Gravity” guarantees matching connectors.

The selected approach is to modify the requested 300 mm JST-SH cable: keep
the plug at the SHT40 end, cut off the other plug, and solder the four wires
to the terminals of a single four-position female header. That header will
plug onto the Gravity board's four-pin I2C group. This keeps the connections
together instead of using four individual female jumper sockets. The cable
has not been modified or connected yet.

Choose a header with the correct pin spacing and solderable terminals; solder
to its tails, not inside the mating sockets. Insulate each joint and secure
the cable so a pull or repeated bend does not load the solder joints (strain
relief). A single housing keeps the wires in order but does not make an
unlatched header locking or prevent reversal. Mark its orientation and check
each connection with a continuity meter, including for shorts between adjacent
contacts, before powering it. The table below gives signal mapping, not the
physical left-to-right order of the pins.

For the Adafruit breakout, the required signal mapping is:

| Gravity I2C group | SHT40 connection | Pi signal |
|---|---|---|
| `+` | VIN/power | 3.3 V |
| `-` | GND | Ground |
| `D` | SDA | GPIO2, I2C data |
| `C` | SCL | GPIO3, I2C clock |

Use the labels and the actual cable pinout, rather than relying on wire colour.
Make connections with power removed, remembering that the UPS can keep the Pi
powered after its external supply is unplugged. Check the ribbon's pin-1
orientation at both ends. The [DFRobot pinout](https://wiki.dfrobot.com/dfr0566/)
and [Adafruit breakout pinout](https://learn.adafruit.com/adafruit-sht40-temperature-humidity-sensor/pinouts)
are the references for this mapping.

The SHT40 uses address `0x44`; the current Pi driver defaults to bus 1. It can
share that bus with the X1200 at `0x36`. The Gravity board's own controller is
at `0x10`. LabPulse has no dedicated DFR0566 analog/PWM driver: exposing those
connectors doesn't make their features available through `labpulse.gpio_input`
or `labpulse.gpio_output`. Those drivers operate Pi GPIO lines. See
[the included drivers](../src/labpulse/hardware/drivers/README.md).

The pressure-monitor Arduino now also has SHT40 firmware support. That is a
separate sensor connection, described in [the firmware guide](../firmware/README.md#pressure-monitor).
The shopping email requests a JST-SH-to-male-header lead for that sensor, to
measure main-lab temperature and humidity at the compressed-air hub. It is
separate from the planned Pi room sensor; firmware support does not establish
that either sensor has been connected and checked.

## Enclosure files and build status

The touchscreen enclosure files are in
[`hardware/enclosure/`](../hardware/enclosure/README.md):

| File | What it provides |
|---|---|
| [Screen Enclosure.f3z](../hardware/enclosure/Screen%20Enclosure.f3z) | Autodesk Fusion assembly archive for continuing the design. It contains seven Fusion design documents. |
| [Screen Enclosure.step](../hardware/enclosure/Screen%20Enclosure.step) | Assembly geometry exported on 18 September 2026 for inspection in other CAD software; it does not retain the original Fusion editing history. |

The CAD is available. The maintainer reports that the current case is printed,
but assembly is waiting for parts. The repository does not yet identify the
CAD revision used for that print or contain its exported print parts and
settings. Final component fit, display retention, cable routing, and assembly
remain to be checked against the actual hardware.

The older STLs and their original design credits are now in
[`legacy/hardware/3d_parts/`](../legacy/hardware/3d_parts/). They are obsolete
and are not print exports of the touchscreen case. `Tall boi With hole!.stl`
contains only a newline, not a model; `RPi 4 cover holes.stl` is the other
historical mesh. Keep these separate from the current Fusion and STEP files.

## Enclosure history

Two Codex tasks contain the useful design context:

- **Find Gravity HAT mounting clearance**, 30 July–3 August 2026
  (`019fb249-8b04-7021-b281-c240d249e170`): the earlier Pi-stack case, adjacent
  Gravity-board housing, ribbon opening, and print feedback.
- **Resolve Gravity IO cable mismatch**, 4–5 August 2026
  (`019fcbf2-effe-7bc3-9b20-082d3526ec20`): the connector problem followed by the
  wall-mounted touchscreen redesign and its component layout.

The earlier case was printed. The reported result was a snug locating lip,
but a thin clip snapped and parts of the lip were also close to breaking.
That is feedback on the earlier prototype. On 18 September the maintainer
confirmed that the current touchscreen case is also printed, but has not been
assembled because key parts have not arrived. Fit and final assembly remain
unchecked.

The later discussion established these preferences:

- a wall-mounted enclosure with as little depth as practical;
- a small local screen mainly for accessing the Pi; normal LabPulse use would
  be through the app or remote access on a larger display;
- the Gravity board above the screen, with the modem potentially behind it;
- the powered hub inside the enclosure, retaining its metal case;
- permanent modem USB wiring kept inside and removable Arduino leads on the hub;
- USB sockets exiting through the **top** of the enclosure, superseding the
  earlier front-facing proposal;
- simple, consistent screw and standoff fixings where practical.

The working proposal put the electronics on a removable front assembly and
left a passive wall plate behind it. This addresses the problem raised in the
chat: if the Pi and hub are mounted on opposite halves, their short USB cables
make the case awkward to open. Screen-retaining bars were explored and liked;
their material, fasteners, and final load path still need documenting.

The August screen discussion moved from Raspberry Pi Touch Display 2 to
Waveshare 7inch DSI LCD (H), but the maintainer confirmed on 18 September that
the actual unit is a **7-inch Raspberry Pi Touch Display 2**. Its standoffs were
removed by wiggling them off with pliers. This records a modification to that
particular unit, not a manufacturer-specified removal procedure or a requirement
for other builds. The final enclosure must support the modified display;
check it against the physical part rather than the superseded Waveshare model.
The final retention arrangement remains to be recorded when assembled.

Some early chat claims about removable display bosses were retracted.
Likewise, the **41.34 mm Pi-plus-UPS figure was a sum of separate
CAD envelopes**, not a measured assembled height. Don't use those old answers
as manufacturing dimensions. Check the complete stack, cooler, display bosses,
plug bodies, and cable bends in the actual assembly.

## References for continuing the CAD

Start with the manufacturers' drawings, then compare them with the physical
parts. Record the board revision beside each imported model; a bare-PCB model
isn't enough to represent the USB hub with its metal case fitted.

| Component | Design reference |
|---|---|
| Pi 5 | [Official mechanical drawing](https://pip.raspberrypi.com/documents/RP-008347-DS) and [STEP model](https://pip.raspberrypi.com/documents/RP-010083-CA) |
| Active Cooler | [Raspberry Pi product and documentation](https://www.raspberrypi.com/products/active-cooler/) |
| X1200 | [Geekworm documentation, installation, and outline DXF](https://wiki.geekworm.com/X1200) |
| SIM7600E-H | [Waveshare board drawings and revision notes](https://www.waveshare.com/wiki/SIM7600E-H_4G_HAT) |
| USB hub | [Waveshare casing dimensions and mounting holes](https://www.waveshare.com/usb3.2-gen1-hub-2in-4out.htm) |
| DFR0566 | [DFRobot Dimension, Layout, SVG, and pinout](https://wiki.dfrobot.com/dfr0566/) |
| 7-inch display; account for the removed standoffs | [Raspberry Pi Touch Display 2 product and documentation](https://www.raspberrypi.com/products/touch-display-2/) |

## Finish the build record

This enclosure is an optional example. Other labs can use a different case
and arrange their own sensors without reproducing this installation.

The [editable assembly and STEP export](#enclosure-files-and-build-status) are
already included. To make the case reproducible, identify the CAD revision used
for the print, add the individual print files and settings, identify the parts
they fit, and give a short assembly order with the required fasteners.
Include any non-obvious details, such as a tight cable bend, a changed connector,
or a power arrangement that someone copying the case needs to understand.
Keep unfinished ideas labelled as proposals.

> **Photo to add: the assembled installation (optional).** Show the main unit
> open with its principal boards and connections labelled. Add a closed-case
> view if useful, and identify any pictured prototype or planned part. If the
> display is shown, identify the 7-inch Touch Display 2 with its removed
> standoffs and show how the case supports it. This capture is waiting for
> assembly; the current case is printed but key parts have not arrived. Record
> which CAD revision the photographed assembly uses.

The optional photo is tracked in [screenshot.md](../screenshot.md). A full lab
wiring inventory or commissioning report isn't needed to complete this guide.
