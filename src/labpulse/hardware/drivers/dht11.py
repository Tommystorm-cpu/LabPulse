"""Typed configuration and implementation for Raspberry Pi DHT11 sensors."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from labpulse.hardware.api import (
    BaseSensorDriver,
    ContainerRequirements,
    ConnectionLost,
    DriverDefinition,
    DriverUnavailable,
    ReadingBatch,
    TransientReadError,
)


class Dht11Options(BaseModel):
    """Normalized configuration for one DHT11 sensor."""

    model_config = ConfigDict(extra="forbid", strict=True)

    pin: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")


# These libraries can initialize GPIO during import. Delay that work until this
# driver is selected, while leaving the globals patchable in hardware-free tests.
_UNLOADED = object()
adafruit_dht: Any = _UNLOADED
board: Any = _UNLOADED


def _load_gpio_dependencies() -> tuple[Any, Any]:
    """Load Blinka and Adafruit DHT lazily for the selected worker only."""

    global adafruit_dht, board
    if adafruit_dht is _UNLOADED or board is _UNLOADED:
        try:
            import adafruit_dht as adafruit_dht_module
            import board as board_module
        except ImportError:
            adafruit_dht = None
            board = None
        else:
            adafruit_dht = adafruit_dht_module
            board = board_module
    if adafruit_dht is None or board is None:
        raise DriverUnavailable(
            "DHT11 dependencies are missing. Install adafruit-circuitpython-dht, "
            "adafruit-blinka, and lgpio in the container."
        )
    return adafruit_dht, board


class Driver(BaseSensorDriver):
    """Read temperature and humidity from an Adafruit-compatible DHT11 sensor."""

    def __init__(
        self,
        name: str,
        pin_name: str,
    ) -> None:
        """Create a DHT11 driver for one named GPIO pin."""

        super().__init__(name)
        self.pin_name = pin_name
        self.device: Any | None = None

    def connect(self) -> None:
        """Initialize the DHT11 device or report it as unavailable."""

        _, board_module = _load_gpio_dependencies()

        try:
            pin = getattr(board_module, self.pin_name)
        except AttributeError as error:
            raise DriverUnavailable(
                f"unknown board pin for DHT11 service {self.name}: {self.pin_name}"
            ) from error

        try:
            self.device = self._create_device(pin)
        except Exception as error:
            self.device = None
            raise DriverUnavailable(
                f"failed to initialize DHT11 on {self.pin_name}: {error}"
            ) from error

        self.logger.info("DHT11 initialized on %s", self.pin_name)

    def read(self) -> ReadingBatch:
        """Return temperature and humidity or classify the failed sample."""

        if self.device is None:
            raise ConnectionLost("DHT11 device is not initialized")

        try:
            temperature = self.device.temperature
            humidity = self.device.humidity
        except RuntimeError as error:
            raise TransientReadError(f"DHT11 timing/read error: {error}") from error
        except Exception as error:
            raise ConnectionLost(f"DHT11 read failed: {error}") from error

        if temperature is None or humidity is None:
            raise TransientReadError("DHT11 returned an incomplete sample")

        return ReadingBatch(
            {
                "temperature": round(float(temperature), 1),
                "humidity": round(float(humidity), 1),
            }
        )

    def close(self) -> None:
        """Release the DHT11 device safely and idempotently."""

        if self.device is not None:
            try:
                self.device.exit()
            except AttributeError:
                pass
            except Exception as error:
                self.logger.warning("DHT11 cleanup failed: %s", error)

        self.device = None

    @staticmethod
    def _create_device(pin: object) -> object:
        """Create the Adafruit DHT11 object, preferring Raspberry Pi-safe pulse IO."""

        dht_module, _ = _load_gpio_dependencies()
        try:
            return dht_module.DHT11(pin, use_pulseio=True)
        except TypeError:
            return dht_module.DHT11(pin)


def build_driver(
    service_name: str,
    raw_options: BaseModel,
) -> BaseSensorDriver:
    """Construct one DHT11 driver from registry-validated options."""

    if not isinstance(raw_options, Dht11Options):
        raise TypeError(
            "DHT11 driver expected Dht11Options, "
            f"got {type(raw_options).__name__}"
        )
    return Driver(name=service_name, pin_name=raw_options.pin)


def resources(
    raw_options: BaseModel,
    _force_simulated: bool,
) -> ContainerRequirements:
    """Expose the current Raspberry Pi GPIO devices to the DHT worker."""

    if not isinstance(raw_options, Dht11Options):
        raise TypeError("DHT11 resources require Dht11Options")
    return ContainerRequirements(mounts=("/dev:/dev",), privileged=True)


DRIVER = DriverDefinition(
    driver_id="labpulse.dht11",
    options_model=Dht11Options,
    build=build_driver,
    resources=resources,
    default_read_interval_seconds=2.0,
)
