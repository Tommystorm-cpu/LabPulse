"""Typed render data consumed by Home Assistant generators."""

from dataclasses import dataclass, field

from labpulse_common.mqtt_contracts import SMS_SEND_TOPIC


@dataclass(frozen=True)
class ThresholdModel:
    """Home Assistant threshold-editor bounds for one reading."""

    unit: str
    range_min: float | int
    range_max: float | int
    step: float | int


@dataclass(frozen=True)
class MqttEntity:
    """Deterministic MQTT discovery identity used by generated YAML."""

    unique_id: str
    entity_id: str


@dataclass
class ReadingModel:
    """Template data for one Home Assistant reading."""

    name: str
    label: str
    subcategory: str | None
    reading_id: str
    notification_context: str
    mqtt_entity: MqttEntity

    alarm_controls_expanded_entity: str
    alarm_state_entity: str
    alarm_mode_entity: str
    alarm_muted_entity: str
    minimum_threshold_entity: str
    maximum_threshold_entity: str
    recovery_deadband_entity: str
    required_danger_percent_entity: str
    observation_window_seconds_entity: str
    required_recovery_seconds_entity: str
    alarm_timing_initialized_entity: str
    setup_muted_entities: tuple[str, ...]

    danger_zone_unique_id: str
    danger_zone_entity: str
    recovery_zone_unique_id: str
    recovery_zone_entity: str
    sensor_fault_zone_unique_id: str
    sensor_fault_zone_entity: str
    observed_danger_percent_unique_id: str
    observed_danger_percent_entity: str

    threshold: ThresholdModel

    @property
    def mqtt_unique_id(self) -> str:
        """Return the MQTT unique ID retained for template compatibility."""

        return self.mqtt_entity.unique_id

    @property
    def expected_entity_id(self) -> str:
        """Return the deterministic MQTT entity ID used by generated files."""

        return self.mqtt_entity.entity_id

    @property
    def setup_notifications_unmuted_template(self) -> str:
        """Require every owning setup's independent notification gate to be open."""

        checks = " and ".join(
            f"is_state('{entity}', 'off')" for entity in self.setup_muted_entities
        )
        return "{{ " + (checks or "true") + " }}"


@dataclass
class PowerModel:
    """Dedicated direct-mains UPS lifecycle identities and timing settings."""

    source: str
    voltage: ReadingModel
    battery_level: ReadingModel
    mains_present: ReadingModel
    gpio_chip: str
    gpio_line: int
    mains_present_active_high: bool
    outage_confirm_seconds: int
    restore_confirm_seconds: int
    maximum_reading_age_seconds: int
    mains_present_unique_id: str
    mains_present_entity: str
    sensor_fault_unique_id: str
    sensor_fault_entity: str
    sensor_fault_confirmed_entity: str
    state_entity: str
    muted_entity: str
    outage_active_entity: str
    outage_started_entity: str
    last_outage_started_entity: str
    last_outage_duration_entity: str
    last_outage_started_sensor_unique_id: str
    last_outage_started_sensor_entity: str
    last_outage_duration_sensor_unique_id: str
    last_outage_duration_sensor_entity: str


@dataclass
class ServiceModel:
    """Template data for one enabled LabPulse service."""

    name: str
    service_id: str
    label: str
    status_entity: MqttEntity
    health_unhealthy_unique_id: str
    health_unhealthy_entity: str
    health_fault_active_entity: str
    health_fault_started_entity: str
    health_fault_confirm_seconds: int
    health_recovery_confirm_seconds: int
    sensor_fault_confirm_seconds: int
    readings: list[ReadingModel] = field(default_factory=list)
    power: PowerModel | None = None

    @property
    def status_unique_id(self) -> str:
        """Return the MQTT service-status unique ID."""

        return self.status_entity.unique_id

    @property
    def status_entity_id(self) -> str:
        """Return the deterministic MQTT service-status entity ID."""

        return self.status_entity.entity_id


@dataclass(frozen=True)
class BulkTimingTarget:
    """One logical bulk-timing target and its physical reading helpers."""

    option: str
    setup_id: str | None
    required_danger_percent_entities: tuple[str, ...]
    observation_window_seconds_entities: tuple[str, ...]
    required_recovery_seconds_entities: tuple[str, ...]


@dataclass(frozen=True)
class SetupAlarmModel:
    """Persistent notification-mute identity for one active logical setup."""

    setup_id: str
    label: str
    icon: str
    muted_entity: str
    shared_reading_labels: tuple[str, ...] = ()

    @property
    def muted_helper_id(self) -> str:
        """Return the helper key without its Home Assistant domain."""

        return self.muted_entity.split(".", 1)[1]

    @property
    def shared_reading_warning(self) -> str:
        """Explain the cross-setup consequence before enabling this mute."""

        labels = ", ".join(self.shared_reading_labels)
        return (
            f"{self.label} contains readings shared with other setups: {labels}. "
            "Muting this setup will suppress each reading's single alert in every "
            "setup where it appears. Continue?"
        )


@dataclass
class RenderModel:
    """All data needed to render Home Assistant templates."""

    services: list[ServiceModel]
    setups: tuple[SetupAlarmModel, ...] = ()
    sms_send_topic: str = SMS_SEND_TOPIC
    global_muted_entity: str = "input_boolean.labpulse_global_notifications_muted"
    test_mode_entity: str = "input_boolean.labpulse_notification_test_mode"
    phone_book_notification_script_entity: str = (
        "script.labpulse_send_phone_book_notification"
    )
    bulk_timing_target_entity: str = "input_select.labpulse_bulk_alarm_timing_target"
    bulk_required_danger_percent_entity: str = (
        "input_number.labpulse_bulk_required_danger_percent"
    )
    bulk_observation_window_seconds_entity: str = (
        "input_number.labpulse_bulk_observation_window_seconds"
    )
    bulk_required_recovery_seconds_entity: str = (
        "input_number.labpulse_bulk_required_recovery_seconds"
    )
    bulk_apply_timing_script_entity: str = "script.labpulse_apply_bulk_alarm_timing"
    bulk_timing_targets: tuple[BulkTimingTarget, ...] = ()

    @property
    def bulk_timing_target_options(self) -> list[str]:
        """Return generated select options for all valid bulk targets."""

        return [target.option for target in self.bulk_timing_targets]

    @property
    def readings(self) -> list[tuple[ServiceModel, ReadingModel]]:
        """Return all readings paired with their parent service."""

        return [
            (service, reading)
            for service in self.services
            for reading in service.readings
        ]

    @property
    def alarm_readings(self) -> list[tuple[ServiceModel, ReadingModel]]:
        """Return readings governed by the normal aggregate alarm machinery."""

        return [
            (service, reading)
            for service in self.services
            if service.power is None
            for reading in service.readings
        ]
