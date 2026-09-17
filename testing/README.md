# Tests

Ordinary pytest tests in this directory are hardware-free and run on developer
machines and CI. `real_hardware/` contains deliberate Raspberry Pi acceptance
procedures.

New maintainers should read [what the tests prove](../docs/MAINTAINING.md#5-know-what-your-tests-prove)
before interpreting a green run. It explains fakes, platform skips, and which
changes still need a running Home Assistant or real-device check.

```bash
python -m pip install --editable ".[dev]"
python -m pytest
```

| Area | Tests |
|---|---|
| Configuration/contracts | `test_config_pipeline.py`, `test_common_contracts.py`, `test_custom_measurements.py` |
| Drivers/runner/MQTT | `test_hardware_factory.py`, `test_hardware_runner.py`, `test_*_driver.py`, `test_homeassistant_publisher.py` |
| Home Assistant/alarms | `test_homeassistant_entities.py`, `test_homeassistant_generator.py`, `test_yaml_dashboard.py`, `test_setup_grouping.py`, `test_notification_context.py`, `test_power_monitor.py` |
| Outputs/SMS | `test_output_mqtt_service.py`, `test_sms_container.py` |
| Deployment/operations | `test_deployment_generation.py`, `test_unified_generation.py`, `test_control_cli.py`, `test_doctor.py`, `test_backup_restore.py` |
| Packaging/release | `test_packaging.py`, `test_container_release.py` |
| Simulation/USB | `test_fake_hardware.py`, `test_simulate_serial.py`, `test_usb_setup.py` |
| Firmware/external input | `test_firmware_layout.py`, `test_triton_logfile_decoder.py`, `test_mqtt_json_driver.py` |
| Documentation | `test_documentation.py` |

`conftest.py` supplies repository and disposable workspace fixtures.
`ups_test_pi_config.yaml` is a real-Pi acceptance configuration, not a starter.
`testing/tmp/` is generated and disposable.

Tests inject fake clocks, MQTT, serial, buses, GPIO and modem calls. A green
suite proves software contracts, not wiring, calibration or real delivery.
Expected failure tests may log warnings. Test the owning boundary and normal,
invalid, failure and recovery paths without `sys.path` mutation or module-level
runners. See [Development](../docs/DEVELOPMENT.md) and
[real-hardware acceptance](real_hardware/README.md).
