# Screenshots and photos to add

This is the checklist for images still needed in the documentation. Each link
opens the section with its marked insertion point. Replace that placeholder
with the image and a short caption when it's ready, then tick the item here.

For the other remaining documentation tasks, use
[the manual documentation checklist](DOCUMENTATION_TODO.md).

## Dashboard screenshots

- [ ] **[Monitor: find a reading](docs/FIRST_STEPS.md#1-find-a-reading).**
  Show the simulated starter dashboard with Compressed Air and pressure
  visible. Mark the setup heading, the reading, and where to click for history.
  Suggested filename: `docs/images/first-steps-monitor.png`.
- [ ] **[System Status: check the service](docs/FIRST_STEPS.md#2-check-the-service).**
  Show Compressed Air and Environment Sensor Hub reporting Working, with its
  latest readings. Mark the service name, status, and reading timestamps.
  Suggested filename: `docs/images/first-steps-system-status.png`.
- [ ] **[Alarm Setup: make a practice alarm](docs/FIRST_STEPS.md#3-make-a-practice-alarm).**
  Open Configure for Compressed Air, then Configure beside pressure. Show
  Alarm mode, Maximum threshold, Recovery deadband, Required danger,
  Observation window, and Required recovery. Use the practice settings in the
  walkthrough, with notifications muted.
  Suggested filename: `docs/images/first-steps-alarm-setup.png`.

## Hardware photos (optional)

These help readers recognise the main parts. Use real hardware and explain
what is shown; a complete wiring record isn't needed.

- [ ] **[Verified sensor hub](docs/HARDWARE.md#existing-hardware-assets)** —
  replace the “Photo to add: one verified sensor hub” block. Show the board,
  main parts, connectors, and USB connection. Name the firmware example it uses
  and any differences from its pin assignments.
  Suggested filename: `docs/images/hardware-sensor-hub.jpg`.
- [ ] **[Assembled installation](docs/MAIN_UNIT.md#finish-the-build-record)** —
  replace the “Photo to add: the assembled installation” block. Show the open
  main unit with its principal boards and connections. Add a closed-case view
  if useful. Identify any pictured prototype or planned part so readers know
  what they are looking at.
  Suggested filename: `docs/images/hardware-installation.jpg`.

## When adding an image

Use example data where possible. Check for phone numbers, account details,
private addresses, and other lab information before committing a capture.
Keep text large enough to read and crop out unrelated browser or desktop UI.

Store the image under `docs/images/`. In the guide, use a relative Markdown
image link with useful alternative text, followed by a short caption explaining
what to notice. For dashboard captures, record the LabPulse and Home Assistant
versions used so a future maintainer can tell when the image needs refreshing.

## Keep this list current

The [maintainer exercises](docs/MAINTAINER_EXAMPLES.md#change-a-dashboard-heading)
explain how to check a dashboard change before deciding which images need a
new capture. They currently add no separate screenshot slots.

Whenever documentation changes add, move, or remove an image insertion point,
update this checklist in the same change. Keep links pointing to the right
sections. Tick completed entries only once the actual image is in the guide;
if a later interface change makes it misleading, untick it and explain what
needs recapturing. Remove entries for sections that no longer need an image.

Run `python -m pytest testing/test_documentation.py -q` to check the links after
editing. This file tracks planned captures; don't add image links for files
that don't exist yet.
