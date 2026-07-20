"""Canonical reading inventory and logical/physical dashboard projections."""

from collections.abc import Mapping
from dataclasses import dataclass

from labpulse_common.config import LabPulseConfig, ReadingConfig, ServiceConfig
from labpulse_common.identity import stable_id


@dataclass(frozen=True)
class ReadingKey:
    """Stable physical identity for one service-owned reading."""

    service_name: str
    reading_name: str

    @property
    def stable_id(self) -> str:
        """Return the shared Home Assistant/MQTT stable identifier."""

        return stable_id(self.service_name, self.reading_name)


@dataclass(frozen=True)
class InventoryReading:
    """One canonical reading with its physical and logical relationships."""

    key: ReadingKey
    service: ServiceConfig
    reading: ReadingConfig
    effective_setup_ids: tuple[str, ...]


@dataclass(frozen=True)
class ReadingInventory:
    """Canonical readings plus setup-oriented and service-oriented projections."""

    readings: tuple[InventoryReading, ...]
    by_key: Mapping[ReadingKey, InventoryReading]
    by_setup: Mapping[str, tuple[InventoryReading, ...]]
    by_service: Mapping[str, tuple[InventoryReading, ...]]
    selected_shared_readings: tuple[InventoryReading, ...]


def build_reading_inventory(config: LabPulseConfig) -> ReadingInventory:
    """Build one reading object per enabled service and all required projections."""

    setup_ids = tuple(
        setup_id
        for setup_id, _setup in sorted(
            config.setups.items(),
            key=lambda item: (item[1].order, item[0]),
        )
    )
    setup_order = {setup_id: index for index, setup_id in enumerate(setup_ids)}
    by_setup_lists: dict[str, list[InventoryReading]] = {
        setup_id: [] for setup_id in setup_ids
    }
    by_service_lists: dict[str, list[InventoryReading]] = {}
    readings: list[InventoryReading] = []
    selected_shared: list[InventoryReading] = []

    for service_name, service in config.services.items():
        if not service.enabled:
            continue
        service_readings: list[InventoryReading] = []
        for reading in service.readings:
            if reading.setups is None:
                effective_setup_ids = ()
            else:
                effective_setup_ids = tuple(
                    sorted(
                        reading.setups.setup_ids,
                        key=setup_order.__getitem__,
                    )
                )
            item = InventoryReading(
                key=ReadingKey(service_name, reading.name),
                service=service,
                reading=reading,
                effective_setup_ids=effective_setup_ids,
            )
            readings.append(item)
            service_readings.append(item)
            for setup_id in effective_setup_ids:
                by_setup_lists[setup_id].append(item)
            if len(effective_setup_ids) > 1:
                selected_shared.append(item)
        by_service_lists[service_name] = service_readings

    canonical = tuple(readings)
    return ReadingInventory(
        readings=canonical,
        by_key={item.key: item for item in canonical},
        by_setup={key: tuple(value) for key, value in by_setup_lists.items()},
        by_service={key: tuple(value) for key, value in by_service_lists.items()},
        selected_shared_readings=tuple(selected_shared),
    )
