"""Build Home Assistant render models from validated LabPulse config."""

from typing import Any

from labpulse_common.config import LabPulseConfig, PowerDetectionConfig, ReadingConfig
from labpulse_common.identity import entity_id, slug, stable_id

from .inventory import InventoryReading, ReadingInventory, build_reading_inventory
from .models import (
    BulkTimingTarget,
    MqttEntity,
    PowerModel,
    ReadingModel,
    RenderModel,
    ServiceModel,
    SetupAlarmModel,
    ThresholdModel,
)


JsonDict = dict[str, Any]


THRESHOLD_EDITOR_RANGES: dict[str, JsonDict] = {
    "temp": {"unit": "\u00b0C", "range_min": -20, "range_max": 80, "step": 0.1},
    "hum": {"unit": "%", "range_min": 0, "range_max": 100, "step": 1},
    "flow": {"unit": "L/min", "range_min": 0, "range_max": 999, "step": 0.1},
    "pressure": {"unit": "bar", "range_min": 0, "range_max": 999, "step": 0.1},
    "generic": {"unit": "", "range_min": 0, "range_max": 999, "step": 1},
}


def threshold_editor_range(reading_name: str) -> JsonDict:
    """Infer threshold-editor bounds and step from a reading name."""

    name = slug(reading_name)
    if "temp" in name:
        return THRESHOLD_EDITOR_RANGES["temp"]
    if "hum" in name:
        return THRESHOLD_EDITOR_RANGES["hum"]
    if "flow" in name:
        return THRESHOLD_EDITOR_RANGES["flow"]
    if "press" in name or "pressure" in name:
        return THRESHOLD_EDITOR_RANGES["pressure"]
    return THRESHOLD_EDITOR_RANGES["generic"]


def build_render_model(
    config: LabPulseConfig,
    inventory: ReadingInventory | None = None,
) -> RenderModel:
    """Build the complete Home Assistant render model from validated config."""

    canonical_inventory = inventory or build_reading_inventory(config)
    services = []
    for service_name, service_config in config.services.items():
        if not service_config.enabled:
            continue

        service_id = slug(service_name)
        service = ServiceModel(
            name=str(service_name),
            service_id=service_id,
            label=service_config.device_name,
            status_entity=MqttEntity(
                unique_id=stable_id(service_name, "status"),
                entity_id=entity_id("sensor", service_name, "status"),
            ),
            health_unhealthy_unique_id=stable_id(service_name, "service_unhealthy"),
            health_unhealthy_entity=entity_id("binary_sensor", service_name, "service_unhealthy"),
            health_fault_active_entity=entity_id("input_boolean", service_name, "service_fault_active"),
            health_fault_started_entity=entity_id("input_datetime", service_name, "service_fault_started"),
            health_fault_confirm_seconds=config.service_health.fault_confirm_seconds,
            health_recovery_confirm_seconds=config.service_health.recovery_confirm_seconds,
            sensor_fault_confirm_seconds=min(
                15,
                service_config.maximum_reading_age_seconds,
            ),
        )

        for inventory_reading in canonical_inventory.by_service[service_name]:
            reading = inventory_reading.reading
            service.readings.append(
                build_reading_model(
                    service_name,
                    service_id,
                    reading,
                    notification_context(config, inventory_reading),
                    inventory_reading.effective_setup_ids,
                )
            )

        if service_config.power_detection is not None:
            service.power = build_power_model(
                service_name,
                service.readings,
                service_config.power_detection,
                service_config.maximum_reading_age_seconds,
            )
        services.append(service)

    model = RenderModel(
        services=services,
        setups=build_setup_alarm_models(config, canonical_inventory),
    )
    model.bulk_timing_targets = build_bulk_timing_targets(
        config, canonical_inventory, model
    )
    return model


def build_setup_alarm_models(
    config: LabPulseConfig, inventory: ReadingInventory
) -> tuple[SetupAlarmModel, ...]:
    """Build one independent mute helper for each setup containing readings."""

    return tuple(
        SetupAlarmModel(
            setup_id=setup_id,
            label=config.setups[setup_id].display_label(setup_id),
            icon=config.setups[setup_id].icon,
            muted_entity=setup_muted_entity(setup_id),
            shared_reading_labels=tuple(
                item.reading.display_label
                for item in readings
                if len(item.effective_setup_ids) > 1
            ),
        )
        for setup_id, readings in inventory.by_setup.items()
        if readings
    )


def setup_muted_entity(setup_id: str) -> str:
    """Return the stable Home Assistant mute helper for one logical setup."""

    return entity_id("input_boolean", "setup", setup_id, "notifications_muted")


def build_bulk_timing_targets(
    config: LabPulseConfig,
    inventory: ReadingInventory,
    model: RenderModel,
) -> tuple[BulkTimingTarget, ...]:
    """Build all-readings and setup-specific bulk timing projections."""

    models_by_key = {
        (service.name, reading.name): reading
        for service in model.services
        if service.power is None
        for reading in service.readings
    }

    def target(
        option: str,
        setup_id: str | None,
        items: tuple[InventoryReading, ...],
    ) -> BulkTimingTarget:
        """Map one logical inventory projection to per-reading helper IDs."""

        selected = tuple(
            models_by_key[(item.key.service_name, item.key.reading_name)]
            for item in items
            if (item.key.service_name, item.key.reading_name) in models_by_key
        )
        return BulkTimingTarget(
            option=option,
            setup_id=setup_id,
            required_danger_percent_entities=tuple(
                reading.required_danger_percent_entity for reading in selected
            ),
            observation_window_seconds_entities=tuple(
                reading.observation_window_seconds_entity for reading in selected
            ),
            required_recovery_seconds_entities=tuple(
                reading.required_recovery_seconds_entity for reading in selected
            ),
        )

    ordinary = tuple(
        item
        for item in inventory.readings
        if (item.key.service_name, item.key.reading_name) in models_by_key
    )
    targets = [target("All readings", None, ordinary)] if ordinary else []
    for setup_id, items in inventory.by_setup.items():
        selected = tuple(
            item
            for item in items
            if (item.key.service_name, item.key.reading_name) in models_by_key
        )
        if not selected:
            continue
        label = config.setups[setup_id].display_label(setup_id)
        targets.append(target(f"{label} ({setup_id})", setup_id, selected))
    return tuple(targets)


def build_power_model(
    service_name: str,
    readings: list[ReadingModel],
    config: PowerDetectionConfig,
    maximum_reading_age_seconds: int,
) -> PowerModel:
    """Build the dedicated power model from direct GPIO and UPS telemetry."""

    by_name = {reading.name: reading for reading in readings}
    prefix = (service_name, "power")
    return PowerModel(
        source=config.source,
        voltage=by_name["voltage"],
        battery_level=by_name["battery_level"],
        mains_present=by_name["mains_present"],
        gpio_chip=config.gpio_chip,
        gpio_line=config.gpio_line,
        mains_present_active_high=config.mains_present_active_high,
        outage_confirm_seconds=config.outage_confirm_seconds,
        restore_confirm_seconds=config.restore_confirm_seconds,
        maximum_reading_age_seconds=maximum_reading_age_seconds,
        mains_present_unique_id=stable_id(*prefix, "mains_present"),
        mains_present_entity=entity_id("binary_sensor", *prefix, "mains_present"),
        sensor_fault_unique_id=stable_id(*prefix, "sensor_fault"),
        sensor_fault_entity=entity_id("binary_sensor", *prefix, "sensor_fault"),
        sensor_fault_confirmed_entity=entity_id("input_boolean", *prefix, "sensor_fault_confirmed"),
        state_entity=entity_id("input_select", *prefix, "state"),
        muted_entity=entity_id("input_boolean", *prefix, "muted"),
        outage_active_entity=entity_id("input_boolean", *prefix, "outage_active"),
        outage_started_entity=entity_id("input_datetime", *prefix, "outage_started"),
        last_outage_started_entity=entity_id("input_datetime", *prefix, "last_outage_started"),
        last_outage_duration_entity=entity_id("input_number", *prefix, "last_outage_duration"),
        last_outage_started_sensor_unique_id=stable_id(*prefix, "last_outage_started"),
        last_outage_started_sensor_entity=entity_id("sensor", *prefix, "last_outage_started"),
        last_outage_duration_sensor_unique_id=stable_id(*prefix, "last_outage_duration"),
        last_outage_duration_sensor_entity=entity_id("sensor", *prefix, "last_outage_duration"),
    )


def build_reading_model(
    service_name: str,
    service_id: str,
    reading: ReadingConfig,
    setup_context: str,
    setup_ids: tuple[str, ...],
) -> ReadingModel:
    """Build template data for one configured reading."""

    reading_name = slug(reading.name)
    reading_id = f"{service_id}_{reading_name}"
    threshold = build_threshold(
        reading_name,
        reading,
    )
    return ReadingModel(
        name=reading_name,
        label=reading.display_label,
        subcategory=reading.subcategory,
        reading_id=reading_id,
        notification_context=setup_context,
        mqtt_entity=MqttEntity(
            unique_id=stable_id(service_name, reading_name),
            entity_id=entity_id("sensor", service_name, reading_name),
        ),
        alarm_controls_expanded_entity=entity_id("input_boolean", service_name, reading_name, "alarm_controls_expanded"),
        alarm_state_entity=entity_id("input_select", service_name, reading_name, "alarm_state"),
        alarm_mode_entity=entity_id("input_select", service_name, reading_name, "alarm_mode"),
        alarm_muted_entity=entity_id("input_boolean", service_name, reading_name, "alarm_muted"),
        minimum_threshold_entity=entity_id("input_number", service_name, reading_name, "minimum_threshold"),
        maximum_threshold_entity=entity_id("input_number", service_name, reading_name, "maximum_threshold"),
        recovery_deadband_entity=entity_id("input_number", service_name, reading_name, "recovery_deadband"),
        required_danger_percent_entity=entity_id(
            "input_number", service_name, reading_name, "required_danger_percent"
        ),
        observation_window_seconds_entity=entity_id(
            "input_number", service_name, reading_name, "observation_window_seconds"
        ),
        required_recovery_seconds_entity=entity_id(
            "input_number", service_name, reading_name, "required_recovery_seconds"
        ),
        alarm_timing_initialized_entity=entity_id(
            "input_boolean", service_name, reading_name, "alarm_timing_initialized"
        ),
        setup_muted_entities=tuple(
            setup_muted_entity(setup_id) for setup_id in setup_ids
        ),
        danger_zone_unique_id=stable_id(service_name, reading_name, "danger_zone"),
        danger_zone_entity=entity_id("binary_sensor", service_name, reading_name, "danger_zone"),
        recovery_zone_unique_id=stable_id(service_name, reading_name, "recovery_zone"),
        recovery_zone_entity=entity_id("binary_sensor", service_name, reading_name, "recovery_zone"),
        sensor_fault_zone_unique_id=stable_id(service_name, reading_name, "sensor_fault_zone"),
        sensor_fault_zone_entity=entity_id("binary_sensor", service_name, reading_name, "sensor_fault_zone"),
        observed_danger_percent_unique_id=stable_id(service_name, reading_name, "observed_danger_percent"),
        observed_danger_percent_entity=entity_id("sensor", service_name, reading_name, "observed_danger_percent"),
        threshold=threshold,
    )


def notification_context(config: LabPulseConfig, item: InventoryReading) -> str:
    """Describe logical setup impact without changing physical alarm identity."""

    scope = item.reading.setups
    if scope is None:
        return "Monitoring context: Dedicated power monitoring."
    labels = [
        config.setups[setup_id].display_label(setup_id)
        for setup_id in item.effective_setup_ids
    ]
    if len(labels) == 1:
        return f"Affected setup: {labels[0]}."
    return f"Affected setups: {', '.join(labels)}."


def build_threshold(
    reading_name: str,
    reading: ReadingConfig,
) -> ThresholdModel:
    """Return editable threshold bounds without assigning alarm values."""

    metadata = threshold_editor_range(reading_name)
    return ThresholdModel(
        unit=reading.unit or str(metadata["unit"]),
        range_min=metadata["range_min"],
        range_max=metadata["range_max"],
        step=metadata["step"],
    )
