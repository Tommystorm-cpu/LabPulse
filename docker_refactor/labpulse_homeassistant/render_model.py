"""Self-building aggregate render models for Home Assistant generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar

from labpulse_common.config import LabPulseConfig, PowerDetectionConfig
from labpulse_common.identity import entity_id, slug, stable_id
from labpulse_common.mqtt_contracts import SMS_SEND_TOPIC

from .measurement_catalog import (
    ConfiguredMeasurement,
    MeasurementCatalog,
    build_measurement_catalog,
)
from .measurement_model import EntityMap, MeasurementModel, MqttEntity


DEFAULT_RENDER_ENTITIES = {
    "global_muted": "input_boolean.labpulse_global_notifications_muted",
    "test_mode": "input_boolean.labpulse_notification_test_mode",
    "phone_book_notification_script": "script.labpulse_send_phone_book_notification",
    "bulk_timing_target": "input_select.labpulse_bulk_alarm_timing_target",
    "bulk_required_danger_percent": "input_number.labpulse_bulk_required_danger_percent",
    "bulk_observation_window_seconds": "input_number.labpulse_bulk_observation_window_seconds",
    "bulk_required_recovery_seconds": "input_number.labpulse_bulk_required_recovery_seconds",
    "bulk_apply_timing_script": "script.labpulse_apply_bulk_alarm_timing",
}


@dataclass(frozen=True)
class PowerModel:
    """Dedicated direct-mains UPS lifecycle configuration and identities."""

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

        by_name = {measurement.name: measurement for measurement in measurements}
        prefix = (service_name, "power")
        return cls(
            voltage=by_name["voltage"],
            battery_level=by_name["battery_level"],
            mains_present=by_name["mains_present"],
            config=config,
            maximum_measurement_age_seconds=maximum_measurement_age_seconds,
            entities={
                key: entity_id(domain, *prefix, suffix)
                for key, (domain, suffix) in cls.ENTITY_SPECS.items()
            },
            unique_ids={
                key: stable_id(*prefix, key) for key in cls.UNIQUE_ID_NAMES
            },
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

        service_config = config.services[service_name]
        measurements = [
            MeasurementModel.from_config(
                service_name,
                item.measurement,
                cls._notification_context(config, item),
                item.effective_setup_ids,
            )
            for item in items
        ]
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

        if item.measurement.setups is None:
            return "Monitoring context: Dedicated power monitoring."
        labels = [
            config.setups[setup_id].display_label(setup_id)
            for setup_id in item.effective_setup_ids
        ]
        prefix = "Affected setup" if len(labels) == 1 else "Affected setups"
        return f"{prefix}: {', '.join(labels)}."


@dataclass(frozen=True)
class BulkTimingTarget:
    """One logical bulk-timing target and its measurement helper entities."""

    option: str
    setup_id: str | None
    required_danger_percent_entities: tuple[str, ...]
    observation_window_seconds_entities: tuple[str, ...]
    required_recovery_seconds_entities: tuple[str, ...]

    @classmethod
    def from_measurements(
        cls: type[BulkTimingTarget],
        option: str,
        setup_id: str | None,
        measurements: tuple[MeasurementModel, ...],
    ) -> BulkTimingTarget:
        """Collect the three timing-helper groups for selected measurements."""

        def entities(name: str) -> tuple[str, ...]:
            """Return one helper entity from every selected measurement."""

            return tuple(measurement.entities[name] for measurement in measurements)

        return cls(
            option,
            setup_id,
            entities("required_danger_percent"),
            entities("observation_window_seconds"),
            entities("required_recovery_seconds"),
        )


@dataclass(frozen=True)
class SetupAlarmModel:
    """Persistent notification-mute identity for one active logical setup."""

    setup_id: str
    label: str
    icon: str
    muted_entity: str
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
            "Muting this setup will suppress each measurement's single alert in every "
            "setup where it appears. Continue?"
        )

@dataclass
class RenderModel:
    """Complete self-building model consumed by all Home Assistant writers."""

    services: list[ServiceModel]
    setups: tuple[SetupAlarmModel, ...] = ()
    entities: EntityMap = field(default_factory=lambda: dict(DEFAULT_RENDER_ENTITIES))
    sms_send_topic: str = SMS_SEND_TOPIC
    bulk_timing_targets: tuple[BulkTimingTarget, ...] = ()

    @property
    def bulk_timing_target_options(self) -> list[str]:
        """Return select options for every generated bulk target."""

        return [target.option for target in self.bulk_timing_targets]

    @property
    def alarm_measurements(self) -> list[tuple[ServiceModel, MeasurementModel]]:
        """Return measurements governed by the ordinary alarm machinery."""

        return [
            (service, measurement)
            for service in self.services
            if service.power is None
            for measurement in service.measurements
        ]

    @classmethod
    def from_config(
        cls: type[RenderModel],
        config: LabPulseConfig,
        catalog: MeasurementCatalog | None = None,
    ) -> RenderModel:
        """Build the complete render model from validated configuration."""

        catalog = catalog or build_measurement_catalog(config)
        services = [
            ServiceModel.from_config(service_name, config, catalog.by_service[service_name])
            for service_name, service in config.services.items()
            if service.enabled
        ]
        setups = tuple(
            SetupAlarmModel(
                setup_id=setup_id,
                label=config.setups[setup_id].display_label(setup_id),
                icon=config.setups[setup_id].icon,
                muted_entity=entity_id(
                    "input_boolean", "setup", setup_id, "notifications_muted"
                ),
                shared_measurement_labels=tuple(
                    item.measurement.display_label
                    for item in items
                    if len(item.effective_setup_ids) > 1
                ),
            )
            for setup_id, items in catalog.by_setup.items()
            if items
        )
        model = cls(services=services, setups=setups)
        model.bulk_timing_targets = model._bulk_timing_targets(config, catalog)
        return model

    def _bulk_timing_targets(
        self, config: LabPulseConfig, catalog: MeasurementCatalog
    ) -> tuple[BulkTimingTarget, ...]:
        """Build all-measurements and setup-specific bulk timing projections."""

        models_by_key = {
            (service.name, measurement.name): measurement
            for service in self.services
            if service.power is None
            for measurement in service.measurements
        }

        def select(items: tuple[ConfiguredMeasurement, ...]) -> tuple[MeasurementModel, ...]:
            """Resolve catalogue records that participate in ordinary alarms."""

            return tuple(
                models_by_key[key]
                for item in items
                if (key := (item.key.service_name, item.key.measurement_name))
                in models_by_key
            )

        projections = [("All measurements", None, catalog.measurements)]
        projections.extend(
            (
                f"{config.setups[setup_id].display_label(setup_id)} ({setup_id})",
                setup_id,
                items,
            )
            for setup_id, items in catalog.by_setup.items()
        )
        return tuple(
            BulkTimingTarget.from_measurements(option, setup_id, selected)
            for option, setup_id, items in projections
            if (selected := select(items))
        )
