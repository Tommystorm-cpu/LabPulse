# Documentation still to finish

The remaining work is small. These guides should help another lab install
LabPulse and connect its own sensors; they don't need a complete record of
how our lab is wired.

## Main tasks

- [ ] **Add the three dashboard screenshots.** Follow [screenshot.md](screenshot.md)
  for the Monitor, System Status, and Alarm Setup captures. Replace the
  placeholders and tick the entries there.
- [ ] **Check the hardware details that affect someone else's choices.**
  In [Hardware](docs/HARDWARE.md) and [Main unit](docs/MAIN_UNIT.md), correct any
  part names or compatibility details you know are wrong. Concentrate on useful
  gotchas such as the Gravity cable mismatch, UPS/GPIO conflicts, and hub power.
  Leave unknown models labelled unknown; no need to audit every installed sensor.
- [ ] **Give the Arduino instructions a quick sanity check.** Read the
  [firmware guide](firmware/README.md) and [first-sensor walkthrough](docs/FIRST_SENSOR.md).
  Add anything a reader couldn't infer from the pin assignments and examples,
  especially sensor-specific conversion values. Full circuit drawings aren't
  required for straightforward wiring.
- [ ] **Read through the beginner instructions once.** Check
  [Installation](docs/INSTALLATION.md) and [First steps](docs/FIRST_STEPS.md)
  against how you actually use LabPulse. Fix missing steps or misleading
  wording you notice. This doesn't need a formal test report.

## Optional extras

- Add a clear photo of a sensor hub and the main unit if it helps readers
  understand the hardware. The optional capture slots are in
  [screenshot.md](screenshot.md).
- If you want others to print your enclosure, add the current editable CAD
  and print files, plus a short note on parts, fasteners, and assembly.
  Link them from [Main unit](docs/MAIN_UNIT.md). Otherwise leave the case as
  a design example.
- If someone new tries the user or maintainer guides, use their questions to
  improve the wording. A formal handover exercise isn't a requirement.

Lab-specific plumbing, cable inventories, battery replacement histories,
commissioning reports, and a full record of the installed wiring are outside
this documentation checklist. Each lab will make its own installation choices.

After editing, run this from the repository root:

```bash
python -m pytest testing/test_documentation.py -q
```

Keep this list short. Add an item only when it fills a useful gap for a user
or maintainer, and keep image tasks in sync with [screenshot.md](screenshot.md).
