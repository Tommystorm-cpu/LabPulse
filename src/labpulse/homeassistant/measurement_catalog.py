"""Canonical configured measurements and their logical/physical indexes."""

from collections.abc import Mapping
from dataclasses import dataclass

from labpulse.common.config import LabPulseConfig, MeasurementConfig, ServiceConfig
from labpulse.common.identity import stable_id


@dataclass(frozen=True)
class MeasurementKey:
    """Stable physical identity for one service-owned measurement."""

    service_name: str
    measurement_name: str

    @property
    def stable_id(self) -> str:
        """Return the shared Home Assistant/MQTT stable identifier."""

        return stable_id(self.service_name, self.measurement_name)


@dataclass(frozen=True)
class ConfiguredMeasurement:
    """One canonical measurement with its physical and logical relationships."""

    key: MeasurementKey
    service: ServiceConfig
    measurement: MeasurementConfig
    effective_setup_ids: tuple[str, ...]


@dataclass(frozen=True)
class MeasurementCatalog:
    """Canonical measurements plus setup-oriented and service-oriented projections."""

    measurements: tuple[ConfiguredMeasurement, ...]
    by_key: Mapping[MeasurementKey, ConfiguredMeasurement]
    by_setup: Mapping[str, tuple[ConfiguredMeasurement, ...]]
    by_service: Mapping[str, tuple[ConfiguredMeasurement, ...]]
    selected_shared_measurements: tuple[ConfiguredMeasurement, ...]


def build_measurement_catalog(config: LabPulseConfig) -> MeasurementCatalog:
    """Build the MeasurementCatalog class and fill it with all measurements organised by key, setup and service"""

    # Create a new tuple of setup_ids sorted by setup order
    setup_ids = tuple(
        setup_id
        for setup_id, _setup in sorted(
            config.setups.items(),
            key=lambda item: (item[1].order, item[0]),
        )
    )

    # Create a "setup_id: index" dictionary
    setup_order = {setup_id: index for index, setup_id in enumerate(setup_ids)}

    # Create an empty dictionary with lists of measurements organised by setup and service
    by_setup_lists: dict[str, list[ConfiguredMeasurement]] = {setup_id: [] for setup_id in setup_ids}
    by_service_lists: dict[str, list[ConfiguredMeasurement]] = {}

    measurements: list[ConfiguredMeasurement] = []
    selected_shared: list[ConfiguredMeasurement] = []

    # Loop through every service and measurement
    for service_name, service in config.services.items():

        if not service.enabled:
            continue

        service_measurements: list[ConfiguredMeasurement] = []

        for measurement in service.measurements:

            # Construct a tuple of the setups this measurement belongs to
            if measurement.setups is None:
                effective_setup_ids = ()
            else:
                effective_setup_ids = tuple(
                    sorted( # Sort the setups by order
                        measurement.setups.setup_ids,
                        key=lambda setup_id: setup_order[setup_id],
                    )
                )

            # Construct the configured measurement class
            item = ConfiguredMeasurement(
                key=MeasurementKey(service_name, measurement.name),
                service=service,
                measurement=measurement,
                effective_setup_ids=effective_setup_ids,
            )

            # Add it to the list of configured measurements and service measurements
            measurements.append(item)
            service_measurements.append(item)

            # Enter this measurement in each setup in by_setup_lists
            for setup_id in effective_setup_ids:
                by_setup_lists[setup_id].append(item)
            
            # If this measurement is shared between multiple setups
            if len(effective_setup_ids) > 1:
                selected_shared.append(item)
        
        by_service_lists[service_name] = service_measurements

    # Make it immutable
    canonical = tuple(measurements)

    # Construct and return the MeasurementCatalog
    return MeasurementCatalog(
        measurements=canonical,
        by_key={item.key: item for item in canonical},
        by_setup={key: tuple(value) for key, value in by_setup_lists.items()},
        by_service={key: tuple(value) for key, value in by_service_lists.items()},
        selected_shared_measurements=tuple(selected_shared),
    )
