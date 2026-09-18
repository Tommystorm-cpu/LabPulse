# Touchscreen enclosure

This folder contains the touchscreen enclosure CAD supplied for the LabPulse
main unit. CAD is the editable three-dimensional design; it is separate from
the files and settings used to print individual parts.

| File | Use |
|---|---|
| [Screen Enclosure.f3z](Screen%20Enclosure.f3z) | Autodesk Fusion assembly archive containing the design documents. Start here when continuing the design in Fusion. |
| [Screen Enclosure.step](Screen%20Enclosure.step) | Geometry export for opening or inspecting the assembly in other CAD software. It does not provide the original Fusion editing history. |

The STEP header records an export on 18 September 2026.

## Assembly

The reference unit uses a **7-inch Raspberry Pi Touch Display 2**, with its
standoffs removed, and an X1200 UPS beneath the Pi. As of 18 September 2026,
the enclosure is printed and assembly is awaiting parts.

The Gravity GPIO expansion board connects across the case to the Pi using a
25 cm FPC cable and two header adapters. The [GPIO extension guide](../../docs/MAIN_UNIT.md#gpio-extension-across-the-enclosure)
lists the three parts and their connections.

Before reproducing the case, compare the design with the actual components,
including supports for the display and clearance for plugs and cables. Export
the individual print parts and record the material, settings, fasteners, and
assembly order alongside the revision you use.

See the [main-unit guide](../../docs/MAIN_UNIT.md#enclosure-files-and-build-status)
for parts and connections.

## Earlier models

The obsolete STLs and their original attribution notes are preserved under
[`legacy/hardware/3d_parts/`](../../legacy/hardware/3d_parts/). They are not
print files for this touchscreen enclosure. In particular,
`Tall boi With hole!.stl` contains only a newline and has no printable geometry.
