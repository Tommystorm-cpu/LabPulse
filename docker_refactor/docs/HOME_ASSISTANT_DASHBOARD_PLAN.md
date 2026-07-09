# Home Assistant Dashboard And Automation Editing

This file is kept for compatibility with older links. The current, complete
guide is:

```text
HOME_ASSISTANT_DASHBOARDS_AND_AUTOMATIONS.md
```

In short:

- edit the running dashboard in the Home Assistant UI
- edit `labpulse_homeassistant/templates/dashboard_seed.yaml` to change the
  generated dashboard created by `--reset-dashboard`
- edit `labpulse_homeassistant/templates/alarm_logic.yaml` to change generated
  threshold helpers, alarm binary sensors, alert automations, and recovery
  automations
- keep threshold values in Home Assistant helpers, not in `config.yaml`
- run `./generate_homeassistant_config.sh` for normal generation
- run `./generate_homeassistant_config.sh --backup-dashboard --reset-dashboard`
  only when intentionally replacing the editable dashboard

See [HOME_ASSISTANT_DASHBOARDS_AND_AUTOMATIONS.md](HOME_ASSISTANT_DASHBOARDS_AND_AUTOMATIONS.md).
