"""Self-building aggregate render models for Home Assistant generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from labpulse.common.config import LabPulseConfig, PowerDetectionConfig
from labpulse.common.identity import entity_id, slug, stable_id
from labpulse.common.mqtt_contracts import SMS_SEND_TOPIC

from .measurement_catalog import (
    ConfiguredMeasurement,
    MeasurementCatalog,
    MeasurementKey,
    build_measurement_catalog,
)
from .measurement_model import EntityMap, MeasurementModel, MqttEntity


# Define the shared Home Assistant entities used by every generated setup.
DEFAULT_RENDER_ENTITIES = {
    "global_muted": "input_boolean.labpulse_global_notifications_muted",
    "test_mode": "input_boolean.labpulse_notification_test_mode",
    "phone_book_notification_script": "script.labpulse_send_phone_book_notification",
    "bulk_timing_target": "input_select.labpulse_bulk_alarm_timing_target",
    "bulk_required_danger_percent": "input_number.labpulse_bulk_required_danger_percent",
    "bulk_observation_window_seconds": "input_number.labpulse_bulk_observation_window_seconds",
    "bulk_required_recovery_seconds": "input_number.labpulse_bulk_required_recovery_seconds",
    "bulk_apply_required_danger_percent": "input_boolean.labpulse_bulk_apply_required_danger_percent",
    "bulk_apply_observation_window_seconds": "input_boolean.labpulse_bulk_apply_observation_window_seconds",
    "bulk_apply_required_recovery_seconds": "input_boolean.labpulse_bulk_apply_required_recovery_seconds",
    "bulk_editor_expanded": "input_boolean.labpulse_bulk_alarm_editor_expanded",
    "bulk_changes_selected": "binary_sensor.labpulse_bulk_alarm_changes_selected",
    "bulk_target_count": "sensor.labpulse_bulk_alarm_target_count",
    "bulk_clear_selection_script": "script.labpulse_clear_bulk_alarm_selection",
    "bulk_apply_settings_script": "script.labpulse_apply_bulk_alarm_settings",
}


@dataclass(frozen=True)
class PowerModel:
    """Dedicated direct-mains UPS lifecycle configuration and identities."""

    # Map each power entity role to its Home Assistant domain and ID suffix.
    ENTITY_SPECS: ClassVar[dict[str, tuple[str, str]]] = {
        "mains_present": ("binary_sensor", "mains_present"),
        "sensor_fault": ("binary_sensor", "sensor_fault"),
        "sensor_fault_confirmed": ("input_boolean", "sensor_fault_confirmed"),
        "state": ("input_select", "state"),
        "muted": ("input_boolean", "muted"),
        "outage_active": ("input_boolean", "outage_active"),
        "outage_started": ("input_datetime", "outage_started"),
        "last_outage_started": ("input_datetime", "last_outage_started"),
        "last_outage_duration": ("input_number", "last_outage_duration"),
        "last_outage_started_sensor": ("sensor", "last_outage_started"),
        "last_outage_duration_sensor": ("sensor", "last_outage_duration"),
    }

    # List the power template entities that also need stable unique IDs.
    UNIQUE_ID_NAMES: ClassVar[tuple[str, ...]] = (
        "mains_present",
        "sensor_fault",
        "last_outage_started",
        "last_outage_duration",
    )

    voltage: MeasurementModel
    battery_level: MeasurementModel
    mains_present: MeasurementModel
    config: PowerDetectionConfig
    maximum_measurement_age_seconds: int
    entities: EntityMap
    unique_ids: EntityMap

    @classmethod
    def from_config(
        cls: type[PowerModel],
        service_name: str,
        measurements: list[MeasurementModel],
        config: PowerDetectionConfig,
        maximum_measurement_age_seconds: int,
    ) -> PowerModel:
        """Build a complete power lifecycle model for one service."""

        # Create a "measurement name: model" dictionary for the power readings.
        by_name = {measurement.name: measurement for measurement in measurements}

        # Create the shared identity prefix for every power lifecycle entity.
        prefix = (service_name, "power")

        # Create a "role: entity_id" dictionary for the power lifecycle.
        entities = {
            role: entity_id(domain, *prefix, suffix)
            for role, (domain, suffix) in cls.ENTITY_SPECS.items()
        }

        # Create a "role: unique_id" dictionary for the power template entities.
        unique_ids = {
            role: stable_id(*prefix, role) for role in cls.UNIQUE_ID_NAMES
        }

        # Construct the complete power render model.
        return cls(
            voltage=by_name["voltage"],
            battery_level=by_name["battery_level"],
            mains_present=by_name["mains_present"],
            config=config,
            maximum_measurement_age_seconds=maximum_measurement_age_seconds,
            entities=entities,
            unique_ids=unique_ids,
        )


@dataclass
class ServiceModel:
    """Template data and derived identities for one enabled sensor service."""

    name: str
    label: str
    status_entity: MqttEntity
    entities: EntityMap
    unique_ids: EntityMap
    health_fault_confirm_seconds: int
    health_recovery_confirm_seconds: int
    sensor_fault_confirm_seconds: int
    measurements: list[MeasurementModel]
    power: PowerModel | None = None

    @property
    def service_id(self) -> str:
        """Return the normalized service identifier."""

        return slug(self.name)

    @classmethod
    def from_config(
        cls: type[ServiceModel],
        service_name: str,
        config: LabPulseConfig,
        items: tuple[ConfiguredMeasurement, ...],
    ) -> ServiceModel:
        """Build one service and all of its configured measurements."""

        # Get the validated configuration for this service.
        service_config = config.services[service_name]

        # Construct a render model for every measurement owned by this service.
        measurements = [
            MeasurementModel.from_config(
                service_name,
                item.measurement,
                cls._notification_context(config, item),
                item.effective_setup_ids,
            )
            for item in items
        ]

        # Construct the service health and measurement render model.
        model = cls(
            name=service_name,
            label=service_config.device_name,
            status_entity=MqttEntity(
                unique_id=stable_id(service_name, "status"),
                entity_id=entity_id("sensor", service_name, "status"),
            ),
            entities={
                "health_unhealthy": entity_id(
                    "binary_sensor", service_name, "service_unhealthy"
                ),
                "health_fault_active": entity_id(
                    "input_boolean", service_name, "service_fault_active"
                ),
                "health_fault_started": entity_id(
                    "input_datetime", service_name, "service_fault_started"
                ),
            },
            unique_ids={
                "health_unhealthy": stable_id(service_name, "service_unhealthy")
            },
            health_fault_confirm_seconds=config.service_health.fault_confirm_seconds,
            health_recovery_confirm_seconds=(
                config.service_health.recovery_confirm_seconds
            ),
            sensor_fault_confirm_seconds=min(
                15, service_config.maximum_measurement_age_seconds
            ),
            measurements=measurements,
        )

        # Add the dedicated power lifecycle when power detection is configured.
        if service_config.power_detection is not None:
            model.power = PowerModel.from_config(
                service_name,
                measurements,
                service_config.power_detection,
                service_config.maximum_measurement_age_seconds,
            )
        return model

    @staticmethod
    def _notification_context(
        config: LabPulseConfig, item: ConfiguredMeasurement
    ) -> str:
        """Describe setup impact without changing physical alarm identity."""

        # Use dedicated wording for measurements outside the setup system.
        if item.measurement.setups is None:
            return "Monitoring context: Dedicated power monitoring."

        # Collect the display label for every setup using this measurement.
        labels = [
            config.setups[setup_id].display_label(setup_id)
            for setup_id in item.effective_setup_ids
        ]

        # Select singular or plural wording from the number of affected setups.
        prefix = "Affected setup" if len(labels) == 1 else "Affected setups"

        # Construct the context sentence added to Home Assistant and SMS alerts.
        return f"{prefix}: {', '.join(labels)}."


@dataclass(frozen=True)
class DeadbandGroupKey:
    """Compatibility identity for measurements allowed to share a deadband."""

    device_class: str
    unit: str


@dataclass(frozen=True)
class BulkDeadbandGroup:
    """One compatible deadband update group within a selected bulk target."""

    key: DeadbandGroupKey
    label: str
    helper_slug: str
    unit: str
    measurement_keys: tuple[MeasurementKey, ...]
    recovery_deadband_entities: tuple[str, ...]
    value_entity: str
    apply_entity: str
    range_min: float | int
    range_max: float | int
    step: float | int


@dataclass(frozen=True)
class BulkAlarmTarget:
    """One canonical bulk target with common and typed helper projections."""

    target_id: str
    option: str
    measurement_keys: tuple[MeasurementKey, ...]
    required_danger_percent_entities: tuple[str, ...]
    observation_window_seconds_entities: tuple[str, ...]
    required_recovery_seconds_entities: tuple[str, ...]
    deadband_groups: tuple[BulkDeadbandGroup, ...]

    @classmethod
    def from_measurements(
        cls: type[BulkAlarmTarget],
        target_id: str,
        option: str,
        measurements: tuple[tuple[MeasurementKey, MeasurementModel], ...],
    ) -> BulkAlarmTarget:
        """Collect common helpers and safe deadband groups for one target."""

        def entities(name: str) -> tuple[str, ...]:
            """Return one helper entity from every selected measurement."""

            return tuple(model.entities[name] for _key, model in measurements)

        # Group deadbands only when device class and exact unit are compatible.
        grouped: dict[DeadbandGroupKey, list[tuple[MeasurementKey, MeasurementModel]]] = {}
        for key, model in measurements:
            device_class = model.device_class or f"measurement:{key.stable_id}"
            group_key = DeadbandGroupKey(device_class, model.threshold.unit)
            grouped.setdefault(group_key, []).append((key, model))

        # Project each compatibility group into stable helper and entity metadata.
        deadband_groups: list[BulkDeadbandGroup] = []
        for key, members in grouped.items():
            if key.device_class.startswith("measurement:"):
                helper_slug = slug(members[0][0].stable_id)
                label = members[0][1].label
            else:
                helper_slug = slug(f"{key.device_class}_{key.unit or 'unitless'}")
                label = key.device_class.replace("_", " ").title()
            range_min = max(0, *(model.threshold.range_min for _item, model in members))
            range_max = min(model.threshold.range_max for _item, model in members)
            if range_min > range_max:
                raise ValueError(
                    f"empty deadband range for {key.device_class} ({key.unit})"
                )
            deadband_groups.append(
                BulkDeadbandGroup(
                    key=key,
                    label=label,
                    helper_slug=helper_slug,
                    unit=key.unit,
                    measurement_keys=tuple(item for item, _model in members),
                    recovery_deadband_entities=tuple(
                        model.entities["recovery_deadband"] for _item, model in members
                    ),
                    value_entity=entity_id(
                        "input_number", "bulk", "deadband", helper_slug
                    ),
                    apply_entity=entity_id(
                        "input_boolean", "bulk", "apply", "deadband", helper_slug
                    ),
                    range_min=range_min,
                    range_max=range_max,
                    step=max(model.threshold.step for _item, model in members),
                )
            )

        # Construct the three groups of timing helpers for this bulk target.
        return cls(
            target_id,
            option,
            tuple(key for key, _model in measurements),
            entities("required_danger_percent"),
            entities("observation_window_seconds"),
            entities("required_recovery_seconds"),
            tuple(deadband_groups),
        )


@dataclass(frozen=True)
class SetupAlarmModel:
    """Persistent notification-mute identity for one active logical setup."""

    setup_id: str
    label: str
    icon: str
    muted_entity: str
    measurement_count: int
    shared_measurement_labels: tuple[str, ...] = ()

    @property
    def muted_helper_id(self) -> str:
        """Return the helper key without its Home Assistant domain."""

        return self.muted_entity.split(".", 1)[1]

    @property
    def shared_measurement_warning(self) -> str:
        """Explain the cross-setup consequence before enabling this mute."""

        labels = ", ".join(self.shared_measurement_labels)
        return (
            f"{self.label} contains measurements shared with other setups: {labels}. "
            "These measurements will remain unmuted while another setup using them "
            "remains unmuted. Continue?"
        )


@dataclass
class RenderModel:
    """Complete self-building model consumed by all Home Assistant writers."""

    services: list[ServiceModel]
    setups: tuple[SetupAlarmModel, ...] = ()
    # Copy the shared entity dictionary so each render model owns its values.
    entities: EntityMap = field(default_factory=lambda: dict(DEFAULT_RENDER_ENTITIES))
    sms_send_topic: str = SMS_SEND_TOPIC
    bulk_alarm_targets: tuple[BulkAlarmTarget, ...] = ()

    @property
    def bulk_alarm_target_options(self) -> list[str]:
        """Return select options for every generated bulk alarm target."""

        # Extract the label shown for each bulk alarm target.
        return [target.option for target in self.bulk_alarm_targets]

    @property
    def bulk_deadband_groups(self) -> tuple[BulkDeadbandGroup, ...]:
        """Return every distinct deadband helper group in deterministic order."""

        if not self.bulk_alarm_targets:
            return ()
        return self.bulk_alarm_targets[0].deadband_groups

    @property
    def bulk_apply_entities(self) -> tuple[str, ...]:
        """Return every apply flag cleared together after a target or update."""

        return (
            self.entities["bulk_apply_required_danger_percent"],
            self.entities["bulk_apply_observation_window_seconds"],
            self.entities["bulk_apply_required_recovery_seconds"],
            *(group.apply_entity for group in self.bulk_deadband_groups),
        )

    @property
    def alarm_measurements(self) -> list[tuple[ServiceModel, MeasurementModel]]:
        """Return measurements governed by the ordinary alarm machinery."""

        # Pair each ordinary measurement with the service that owns it.
        alarm_measurements: list[tuple[ServiceModel, MeasurementModel]] = []
        for service in self.services:
            if service.power is not None:
                continue
            for measurement in service.measurements:
                alarm_measurements.append((service, measurement))
        return alarm_measurements

    @classmethod
    def from_config(
        cls: type[RenderModel],
        config: LabPulseConfig,
        catalog: MeasurementCatalog | None = None,
    ) -> RenderModel:
        """Build the complete render model from validated configuration."""

        # Build the measurement catalogue unless the caller already supplied one.
        catalog = catalog or build_measurement_catalog(config)

        # Construct a render model for every enabled physical service.
        services = [
            ServiceModel.from_config(service_name, config, catalog.by_service[service_name])
            for service_name, service in config.services.items()
            if service.enabled
        ]

        # Construct an alarm model for every setup containing measurements.
        setups_list: list[SetupAlarmModel] = []
        for setup_id, items in catalog.by_setup.items():
            if not items:
                continue

            # Collect labels for measurements shared with another setup.
            shared_measurement_labels = tuple(
                item.measurement.display_label
                for item in items
                if len(item.effective_setup_ids) > 1
            )

            # Add this setup's notification mute identity and warning context.
            setups_list.append(
                SetupAlarmModel(
                setup_id=setup_id,
                label=config.setups[setup_id].display_label(setup_id),
                icon=config.setups[setup_id].icon,
                    muted_entity=entity_id(
                        "input_boolean", "setup", setup_id, "notifications_muted"
                    ),
                    measurement_count=len(items),
                    shared_measurement_labels=shared_measurement_labels,
                )
            )

        # Construct the aggregate model from the service and setup models.
        model = cls(services=services, setups=tuple(setups_list))

        # Add the bulk alarm targets after the ordinary measurement models exist.
        model.bulk_alarm_targets = model._bulk_alarm_targets(config, catalog)
        return model

    def _bulk_alarm_targets(
        self, config: LabPulseConfig, catalog: MeasurementCatalog
    ) -> tuple[BulkAlarmTarget, ...]:
        """Build all-measurements and setup-specific selective projections."""

        # Index each ordinary measurement model by its physical identity.
        models_by_key = {
            (service.name, measurement.name): measurement
            for service in self.services
            if service.power is None
            for measurement in service.measurements
        }

        def select(
            items: tuple[ConfiguredMeasurement, ...],
        ) -> tuple[tuple[MeasurementKey, MeasurementModel], ...]:
            """Resolve catalogue records that participate in ordinary alarms."""

            # Match catalogue measurements to their ordinary alarm models.
            selected: list[tuple[MeasurementKey, MeasurementModel]] = []
            for item in items:
                key = (item.key.service_name, item.key.measurement_name)
                if key in models_by_key:
                    selected.append((item.key, models_by_key[key]))
            return tuple(selected)

        # Start with one target covering every ordinary measurement.
        projections: list[
            tuple[str, str, tuple[ConfiguredMeasurement, ...]]
        ] = [("all", "All measurements", catalog.measurements)]

        # Add one target for the measurements belonging to each setup.
        for setup_id, items in catalog.by_setup.items():
            projections.append(
                (
                    setup_id,
                    f"{config.setups[setup_id].display_label(setup_id)} ({setup_id})",
                    items,
                )
            )

        # Construct a bulk target for every projection containing measurements.
        targets: list[BulkAlarmTarget] = []
        for target_id, option, items in projections:
            selected = select(items)
            if selected:
                targets.append(
                    BulkAlarmTarget.from_measurements(target_id, option, selected)
                )
        return tuple(targets)
