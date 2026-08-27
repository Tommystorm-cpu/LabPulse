"""Read temperature and humidity from a Raspberry Pi DHT11 sensor."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from labpulse.hardware.driver import (
    ContainerRequirements,
    ConnectionLost,
    DriverDefinition,
    DriverUnavailable,
    HardwareDriver,
    HardwareReadings,
    TransientReadError,
)


# Driver configuration
class Dht11Config(BaseModel):
    """GPIO configuration for one DHT11 sensor."""

    model_config = ConfigDict(extra="forbid", strict=True)

    pin: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")


# Optional hardware dependencies
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
            "DHT11 dependencies are missing. Install the LabPulse gpio extra "
            "or install adafruit-circuitpython-dht, adafruit-blinka, and lgpio "
            "in the container."
        )
    return adafruit_dht, board


# Required driver lifecycle
class Dht11Driver(HardwareDriver):
    """Read temperature and humidity from an Adafruit-compatible DHT11 sensor."""

    def __init__(self, service_name: str, config: Dht11Config) -> None:
        """Create a DHT11 driver for one named GPIO pin."""

        super().__init__(service_name)
        self.pin_name = config.pin
        self._device: Any | None = None

    def connect(self) -> None:
        """Initialize the DHT11 device or report it as unavailable."""

        dht_module, board_module = _load_gpio_dependencies()

        try:
            pin = getattr(board_module, self.pin_name)
        except AttributeError as error:
            raise DriverUnavailable(
                f"unknown board pin for DHT11 service {self.service_name}: "
                f"{self.pin_name}"
            ) from error

        try:
            self._device = dht_module.DHT11(pin, use_pulseio=True)
        except Exception as error:
            self._device = None
            raise DriverUnavailable(f"failed to initialize DHT11 on {self.pin_name}: {error}") from error

        self.logger.info("DHT11 initialized on %s", self.pin_name)

    def read(self) -> HardwareReadings:
        """Return temperature and humidity or classify the failed sample."""

        if self._device is None:
            raise ConnectionLost("DHT11 device is not initialized")

        try:
            temperature = self._device.temperature
            humidity = self._device.humidity
        except RuntimeError as error:
            raise TransientReadError(f"DHT11 timing/read error: {error}") from error
        except Exception as error:
            raise ConnectionLost(f"DHT11 read failed: {error}") from error

        if temperature is None or humidity is None:
            raise TransientReadError("DHT11 returned an incomplete sample")

        return HardwareReadings({
            "temperature": round(float(temperature), 1),
            "humidity": round(float(humidity), 1),
        })

    def close(self) -> None:
        """Release the DHT11 device safely and idempotently."""

        if self._device is not None:
            try:
                self._device.exit()
            except AttributeError:
                pass
            except Exception as error:
                self.logger.warning("DHT11 cleanup failed: %s", error)

        self._device = None


# Container access and driver registration
def container_requirements(_config: Dht11Config, _force_simulated: bool) -> ContainerRequirements:
    """Give the DHT11 container access to Raspberry Pi GPIO devices."""

    return ContainerRequirements(mounts=("/dev:/dev",), privileged=True)


DRIVER_DEFINITION = DriverDefinition(
    driver_id="labpulse.dht11",
    config_model=Dht11Config,
    driver_class=Dht11Driver,
    container_requirements=container_requirements,
    default_read_interval_seconds=2.0,
)
