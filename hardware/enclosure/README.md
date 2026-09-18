# Touchscreen enclosure

This folder contains the touchscreen enclosure CAD supplied for the LabPulse
main unit. CAD is the editable three-dimensional design; it is separate from
the files and settings used to print individual parts.

| File | Use |
|---|---|
| [Screen Enclosure.f3z](Screen%20Enclosure.f3z) | Autodesk Fusion assembly archive containing the design documents. Start here when continuing the design in Fusion. |
| [Screen Enclosure.step](Screen%20Enclosure.step) | Geometry export for opening or inspecting the assembly in other CAD software. It does not provide the original Fusion editing history. |

The STEP header records an export on 18 September 2026. The Fusion archive
contains seven `.f3d` design documents and its archive integrity check passed;
that check does not establish dimensions, component fit, or printability.

## Build status

On 18 September 2026 the maintainer reported that the current case was
printed but not assembled because key parts had not arrived. The actual
display is a **7-inch Raspberry Pi Touch Display 2**, with its standoffs
removed. The unit also uses an X1200 UPS beneath the Pi.

The repository does not yet identify which CAD revision produced that print,
include a set of exported print parts, or record a completed fit check. Before
reproducing the case, compare the design with the actual components and record
the print revision, material, settings, fasteners, and assembly order. Do not
assume imported component models establish clearance for plugs and cables.

See the [main-unit guide](../../docs/MAIN_UNIT.md#enclosure-files-and-build-status)
for the selected parts, pending assembly checks, design history, and planned
photo of the completed installation.

## Earlier models

The obsolete STLs and their original attribution notes are preserved under
[`legacy/hardware/3d_parts/`](../../legacy/hardware/3d_parts/). They are not
print files for this touchscreen enclosure. In particular,
`Tall boi With hole!.stl` contains only a newline and has no printable geometry.
