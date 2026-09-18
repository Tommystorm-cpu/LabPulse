# Sensor-hub PCB revisions

These archives contain board-manufacturing artwork (Gerber files) and drill
files for sensor-hub prototypes. They are design references: the repository
does not yet establish which revision is fitted, electrically checked, or
recommended for a new build. A filename containing "Final" or "v6" is not
evidence of those checks.

## Revision index

| Archive | Recorded label | Contents inspected | Build status |
|---|---|---|---|
| [Prototype 1](Gerber_PCB_Arduino-Hat_prototype1.zip) | Arduino-Hat prototype1 | Copper, silkscreen, solder masks, board outline, drill files and ordering notes | Fitted revision and testing unconfirmed |
| [Prototype 2](Gerber_PCB_Arduino-Hat_prototype2_2025-11-14.zip) | Arduino-Hat prototype2; filename dated 2025-11-14 | Copper, silkscreen, solder masks, board outline, drill files, document layer and ordering notes | Fitted revision and testing unconfirmed |
| [Prototype 3](Gerber_PCB_Arduino-Hat_prototype3.zip) | Arduino-Hat prototype3 | Copper, silkscreen, solder masks, board outline, drill files, document layer and ordering notes | Fitted revision and testing unconfirmed |
| [Final prototype](Gerber_PCB_Arduino-Hat_Final_prototype.zip) | Arduino-Hat Final_prototype | Copper, silkscreen, solder masks, board outline, drill files, document layer and ordering notes | Fitted revision and testing unconfirmed |
| [PCBv6](PCBv6.zip) | PCBv6 | Copper, silkscreen, solder masks, solder paste, profile, drill and Gerber job files | Relationship to the Arduino-Hat series and testing unconfirmed |

All five archives are retained together until a maintainer identifies the
supported board. No revision is designated current merely because it sorts
last. The archive contents do not include editable schematic or board-layout
project files.

Before choosing a revision for manufacture, match its markings and connections
to the hardware, record the sensor and firmware pin assignments, and document
the electrical checks. Add source design files if available. Once a revision
is confirmed, identify it here and archive superseded revisions under
`legacy/hardware/pcbs/` with their history preserved.

See [Hardware](../../docs/HARDWARE.md#existing-hardware-assets) for the known
sensor parts and the optional photo needed to identify a verified hub.
