# The Raspberry Pi main unit

The main unit is the computer at the centre of LabPulse. It runs the dashboard,
receives readings from the Arduino hubs, and uses a cellular modem to send SMS.
Its UPS (uninterruptible power supply) keeps the Pi running through a power
interruption and reports the battery and external-power state.

This page was checked against the repository, CAD chats, and manufacturer
references on 17 September 2026. It records the known parts and the latest
enclosure direction from the July–August 2026 discussions, so the next person
doesn't have to reconstruct those chats. The wall-mounted touchscreen case
was still being designed; this isn't a claim that it has been built and tested.

For the remote sensor hubs, see [Hardware](HARDWARE.md#sensor-hub-parts).
For the software installation, use [Installation](INSTALLATION.md).

If you're identifying an existing unit, start with [the parts list](#parts-in-the-main-unit)
and [connections](#how-the-connections-fit-together). If you're continuing the
case design, read [the enclosure history](#enclosure-history) before importing
models. The [build notes](#finish-the-build-record) explain what to include if
you share a finished version of the case.

## Parts in the main unit

“Purchased” below comes from [the original purchase workbook](Internship%20purchased%20items.xlsx),
Sheet1. “Later list” means [Mini Shopping List](Mini%20Shopping%20List.xlsx),
Sheet1. The [enclosure history](#enclosure-history) identifies the supporting chats.

| Part | Role | What the records establish |
|---|---|---|
| Raspberry Pi 5, 8 GB | Runs LabPulse, MQTT, and Home Assistant | Purchased, row 2. The July acceptance record identifies the tested Pi as Model B Rev 1.1. |
| Raspberry Pi 5 Active Cooler | Cools the Pi | Purchased, row 13; included in the CAD component list. |
| Geekworm/SupTronics X1200 UPS | Pi power backup and battery monitoring | Replacement named in purchase-workbook E12 and the sensor inventory. This is the UPS supported by `labpulse.x1200`. |
| Two 18650 cells for the X1200 | Stored energy for the UPS | The board has two cell holders. The fitted cell manufacturer, capacity, and age aren't recorded in these lists; use the X1200 instructions when choosing replacements. |
| Waveshare SIM7600E-H 4G HAT | SMS modem | Purchased, row 11. Record the PCB revision as well as the modem name. |
| Waveshare USB3.2 Gen1 HUB 2IN–4OUT | Accessible USB connections for Arduino hubs | Explicitly identified as already owned in the August CAD chat. The design keeps its metal casing. |
| DFRobot DFR0566 Gravity IO Expansion HAT | Accessible Pi GPIO and I2C connections | Later list, row 4; the August chat reports the bought board's cable mismatch. |
| 40-pin male-to-female GPIO ribbon, 150 mm (Gertboard type) | Lets the Gravity board sit away from the Pi stack | Later list, row 6; used in the enclosure plan. |
| Adafruit Sensirion SHT40 STEMMA QT/Qwiic breakout | Room temperature and humidity | Later list, row 3. The starter `room_environment` service uses the Pi SHT40 driver. |
| 7-inch touchscreen | Local Pi access | Explored in the August redesign. The later CAD work used the Waveshare **7inch DSI LCD (H)** as its reference; no purchase or finished fit is established here. |
| M2.5 screws, spacers, and standoffs | Board mounting | Original list includes Wurth 971160151 male–female 16 mm standoffs, a nylon assortment, and a GPIO riser. The July chat separately identifies Wurth 970160155 female–female 16 mm standoffs as being used. They aren't interchangeable in every mounting position. |

A HAT is an add-on board shaped to mount on the Pi. The name doesn't mean every
HAT in this enclosure has to plug into the Pi's 40-pin header.

The original list's **Waveshare UPS HAT (A)** is marked “DON'T USE THIS ONE”.
It was superseded by the X1200. It also lists three Gembird UHB-U2P4-04 USB hubs;
these belong to the earlier purchases, not the later Waveshare enclosure plan.
The [July acceptance record](../ROADMAP.md#real-hardware-reliability) reports a
faulty external hub, but doesn't identify its model.

## How the connections fit together

The intended arrangement keeps permanent internal connections on the Pi and
puts the removable Arduino connections on the powered hub. This is a
connection overview, not a circuit or a drawing of the finished case.

```text
Raspberry Pi 5
  USB ---------------- SIM7600E-H modem (permanent connection)
  USB ---------------- Waveshare hub ----- Arduino sensor hubs
  40-pin GPIO ribbon - Gravity board ----- room SHT40 over I2C
  DSI ---------------- proposed touchscreen
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

There is one unresolved power detail worth keeping visible: the Waveshare
hub's **external power terminal is specified for 7–36 V**, while the X1200
provides about 5 V. Don't connect that terminal straight to a 5 V UPS output.
The hub's supply, and whether it stays powered during a mains outage, need to
be recorded as part of the finished build. A running Pi doesn't guarantee
that independently powered USB sensors are still running.
[Waveshare power specifications](https://www.waveshare.com/usb3.2-gen1-hub-2in-4out.htm).

## Gravity board and room sensor

The Gravity board moves the connections somewhere accessible instead of making
the Pi stack taller. In the later enclosure plan it sits above the screen,
connected to the Pi by the 150 mm GPIO ribbon.

The shopping-list **Qwiic-to-Gravity JST-SH-to-JST-PH cable did not fit this
board**. That was the starting point of the August chat. Don't repeat the
purchase assuming that “Gravity” guarantees matching connectors. The proposed
replacement was a STEMMA QT/Qwiic JST-SH lead with female jumper sockets at
the other end; its final installation wasn't recorded in that discussion.

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
It doesn't replace or share the physical room sensor attached to the Pi.

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
That is useful prototype feedback, not evidence that the later touchscreen
case was printed successfully.

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

The screen discussion moved from Raspberry Pi Touch Display 2 to Waveshare
7inch DSI LCD (H). Some early claims about removable display bosses were
retracted. Likewise, the **41.34 mm Pi-plus-UPS figure was a sum of separate
CAD envelopes**, not a measured assembled height. Don't use those old answers
as manufacturing dimensions. Check the complete stack, cooler, display bosses,
plug bodies, and cable bends in the actual assembly.

The current [3D-parts folder](../hardware/3d_parts/) contains only the older
STLs marked obsolete by its README. It doesn't contain the touchscreen case's
editable Fusion assembly or a verified printable release. Keep those distinct
when bringing the finished CAD back into the repository.

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
| Proposed display | [Waveshare 7inch DSI LCD (H) documentation](https://www.waveshare.com/wiki/7inch_DSI_LCD_%28H%29) |

## Finish the build record

This enclosure is an optional example. Other labs can use a different case
and arrange their own sensors without reproducing this installation.

If you share the finished case, add the editable CAD and print files, identify
the parts they fit, and give a short assembly order with the required fasteners.
Include any non-obvious details, such as a tight cable bend, a changed connector,
or a power arrangement that someone copying the case needs to understand.
Keep unfinished ideas labelled as proposals.

> **Photo to add: the assembled installation (optional).** Show the main unit
> open with its principal boards and connections labelled. Add a closed-case
> view if useful, and identify any pictured prototype or planned part.

The optional photo is tracked in [screenshot.md](../screenshot.md). A full lab
wiring inventory or commissioning report isn't needed to complete this guide.
