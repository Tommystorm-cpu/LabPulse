# The Raspberry Pi main unit

The main unit is the computer at the centre of LabPulse. It runs the dashboard,
receives readings from the Arduino hubs, and uses a cellular modem to send SMS.
Its UPS (uninterruptible power supply) keeps the Pi running through a power
interruption and reports the battery and external-power state.

The reference main unit uses a Raspberry Pi 5, an X1200 UPS, and a 7-inch
Raspberry Pi Touch Display 2. As of 18 September 2026, the enclosure is printed
and assembly is awaiting parts. The SHT40 connections have not been installed.

For remote sensor hubs, see [Hardware](HARDWARE.md#sensor-hub-parts).
For software installation, use [Installation](INSTALLATION.md).
The [CAD files](#enclosure-files-and-build-status) are available for adapting
the enclosure to your own components.

## Parts in the main unit

The [purchasing workbook](LabPulse%20Purchasing.xlsx) lists supplier links,
quantities, historical prices, and replacement parts.

| Part | Role | Connection or assembly note |
|---|---|---|
| Raspberry Pi 5, 8 GB | Runs LabPulse, MQTT, and Home Assistant | Use the Pi 5 display adapter cable for the touchscreen. |
| Raspberry Pi 5 Active Cooler | Cools the Pi | Allow space for the cooler and airflow. |
| Geekworm/SupTronics X1200 UPS | Power backup and battery monitoring | Mounts beneath the Pi; see [power and GPIO](#power-and-shared-gpio-pins). |
| Waveshare SIM7600E-H 4G HAT | SMS modem | Connect over USB and mount on spacers. |
| Waveshare USB3.2 Gen1 HUB 2IN–4OUT | USB connections for Arduino hubs | Uses the external 12 V supply listed below. |
| DFRobot DFR0566 Gravity IO Expansion HAT | Accessible Pi GPIO and I2C connections | Connect through the [FPC GPIO extension](#gpio-extension-across-the-enclosure). |
| 40-pin FPC GPIO extension, 25 cm, with two header adapters | Connects the Gravity board to the Pi across the enclosure | Use the straight female adapter at the Pi and the right-angle male adapter at the expansion board. |
| Adafruit SHT40 STEMMA QT/Qwiic breakout | Temperature and humidity sensing | See [sensor connections](#gravity-board-and-room-sensor). |
| Raspberry Pi Touch Display 2, 7-inch | Local Pi access | This unit has had its standoffs removed; account for that when supporting the display. |
| M2.5 screws, spacers, and standoffs | Board mounting | Select lengths for the actual board stack and enclosure. |

A HAT is an add-on board shaped to mount on the Pi. It does not have to plug
directly into the Pi's header when the required connections are made separately.

## Additional parts requested

These accessories provide the display, hub power, and sensor connections.
They were requested for the build on 18 September 2026.

| Accessory | Use |
|---|---|
| [500 mm display adapter cable for Pi 5](https://thepihut.com/products/display-adapter-cable-for-raspberry-pi-5?variant=42531573891267) | Replace the short cable supplied with the display. The requested length is 500 mm. |
| [USB power breakout for Raspberry Pi Touch Display 2](https://thepihut.com/products/usb-power-breakout-for-raspberry-pi-touch-display-2) | Supply Touch Display 2 power from USB, avoiding a power lead to the GPIO connections outside the case. This is a power adapter; the display still needs its DSI connection. |
| [12 V, 2 A mains supply with 2.1 mm barrel plug](https://thepihut.com/products/12v-2a-power-supply-with-2-1mm-barrel-jack) | External power for the USB hub. See [power and shared GPIO pins](#power-and-shared-gpio-pins). |
| [STEMMA QT/Qwiic JST-SH to male headers cable](https://thepihut.com/products/stemma-qt-qwiic-jst-sh-4-pin-to-premium-male-headers-cable) | Connect an SHT40 to the compressed-air Arduino for main-lab temperature and humidity. |
| [300 mm STEMMA QT/Qwiic JST-SH cable](https://thepihut.com/products/stemma-qt-qwiic-jst-sh-4-pin-cable-300mm-long) | Pi-side SHT40 lead: retain the sensor-end JST-SH plug and terminate the other end in a single four-position female header for the Gravity board's I2C pins. |
| Four-position female header with solderable terminals | Terminate the modified SHT40 lead as one connector instead of four separate female jumper sockets. Match the board's pin spacing and use a header with solderable terminals. |

## How the connections fit together

Use the Pi's USB ports for internal connections and the powered hub for
removable Arduino leads. The diagram shows the connection layout.

```text
Raspberry Pi 5
  USB ---------------- SIM7600E-H modem (permanent connection)
  USB ---------------- Waveshare hub ----- Arduino sensor hubs
  40-pin FPC --------- Gravity board ----- room SHT40 connection
  DSI ---------------- Raspberry Pi Touch Display 2
  USB power breakout - Touch Display 2 power
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

The external 12 V supply has no battery backup. Test loss and restoration of
that supply with all intended USB devices connected: check whether each device
stays powered through the Pi or disconnects and recovers. Include this check
when commissioning the unit's UPS backup.

## GPIO extension across the enclosure

The Gravity GPIO expansion board connects to the Pi through a **25 cm FPC
(flexible printed circuit) cable** and two header adapters. This provides
the reach and flexibility needed to route the GPIO connection across the
case, replacing the earlier 150 mm GPIO ribbon selection.

Use one of each part:

| Part | Connection |
|---|---|
| [40-pin FPC to straight 2×20 IDC female socket adapter](https://thepihut.com/products/40-pin-fpc-to-straight-2x20-idc-female-socket-header) | Female socket fits onto the Pi's 40-pin male GPIO header. |
| [40-pin, 0.5 mm pitch FPC cable, A–B connections, 25 cm](https://thepihut.com/collections/adafruit-cables/products/40-pin-0-5mm-pitch-fpc-flex-cable-with-a-b-connections-25cm-long) | Joins the two adapters through their FPC connectors. |
| [40-pin FPC to right-angle 2×20 IDC male plug adapter](https://thepihut.com/products/40-pin-fpc-to-right-angle-2x20-idc-male-plug-header-adapter) | Male plug fits into the Gravity board's female GPIO connector. |

With power removed, align pin 1 at the Pi, both adapters, and the Gravity
board. Seat the cable in each FPC connector and secure its latch. Check
end-to-end pin mapping before powering the assembly, and route the cable
without sharp creases or tension at the connectors. The extension carries
the Pi's GPIO connections; it does not change their pin assignments.

## Gravity board and room sensor

The Gravity board provides accessible connections through the
[FPC GPIO extension](#gpio-extension-across-the-enclosure). Use the board's
labelled four-pin I2C group for the Pi-side SHT40.

The Qwiic-to-Gravity JST-SH-to-JST-PH cable is not the lead used here. For the
300 mm JST-SH cable, keep the sensor-end plug and solder the other end to a
single four-position female header. This keeps the four connections together
instead of using separate jumper sockets.

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
powered after its external supply is unplugged. Check the extension's pin-1
orientation at both ends. The [DFRobot pinout](https://wiki.dfrobot.com/dfr0566/)
and [Adafruit breakout pinout](https://learn.adafruit.com/adafruit-sht40-temperature-humidity-sensor/pinouts)
are the references for this mapping.

The SHT40 uses address `0x44`; the current Pi driver defaults to bus 1. It can
share that bus with the X1200 at `0x36`. The Gravity board's own controller is
at `0x10`. LabPulse has no dedicated DFR0566 analog/PWM driver: exposing those
connectors doesn't make their features available through `labpulse.gpio_input`
or `labpulse.gpio_output`. Those drivers operate Pi GPIO lines. See
[the included drivers](../src/labpulse/hardware/drivers/README.md).

The pressure-monitor Arduino example also supports an SHT40 on its I2C bus.
Use the JST-SH-to-male-header lead for that board and follow the
[firmware wiring guide](../firmware/README.md#pressure-monitor). This is a
separate sensor from the Pi-side room sensor.

## Enclosure files and build status

The touchscreen enclosure files are in
[`hardware/enclosure/`](../hardware/enclosure/README.md):

| File | What it provides |
|---|---|
| [Screen Enclosure.f3z](../hardware/enclosure/Screen%20Enclosure.f3z) | Autodesk Fusion assembly archive for continuing the design. It contains seven Fusion design documents. |
| [Screen Enclosure.step](../hardware/enclosure/Screen%20Enclosure.step) | Assembly geometry exported on 18 September 2026 for inspection in other CAD software; it does not retain the original Fusion editing history. |

The case is printed and assembly is awaiting parts. Before printing or
assembling your own unit, compare the CAD with the actual components, including
display supports, board clearances, plug bodies, and cable bends. Export the
individual parts from the assembly and choose print settings for your material.

The older STLs and their original design credits are now in
[`legacy/hardware/3d_parts/`](../legacy/hardware/3d_parts/). They are obsolete
and are not print exports of the touchscreen case. `Tall boi With hole!.stl`
contains only a newline, not a model; `RPi 4 cover holes.stl` is the other
historical mesh. Keep these separate from the current Fusion and STEP files.

## Display mounting

The display is a **7-inch Raspberry Pi Touch Display 2**. Its standoffs were
removed on this unit. That modification is not a required step for other
builds: choose supports that suit the display you are installing and check
the load-bearing surfaces before securing it.

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

> **Photo to add: the assembled installation (optional).** Show the main unit
> open with its principal boards and connections labelled. Show the FPC
> extension's route and its connections at the Pi and Gravity board. Add a closed-case
> view if useful, and identify the components shown. If the display is shown,
> identify the 7-inch Touch Display 2 with its removed
> standoffs and show how the case supports it. This capture is waiting for
> assembly; the current case is printed but key parts have not arrived. Record
> which CAD revision the photographed assembly uses.

The optional photo is tracked in [screenshot.md](../screenshot.md). A full lab
wiring inventory or commissioning report isn't needed to complete this guide.
