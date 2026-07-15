"""DHT11 GPIO driver for Raspberry Pi environment readings."""

from typing import Any, Optional
import time

from labpulse_hardware.drivers.base import BaseSensorDriver

try:
    import adafruit_dht
    import board
except ImportError:
    adafruit_dht = None
    board = None


class Driver(BaseSensorDriver):
    """Read temperature and humidity from an Adafruit-compatible DHT11 sensor."""

    def __init__(
        self,
        name: str,
        pin_name: str,
        read_interval_seconds: float,
    ) -> None:
        """Create a DHT11 driver from GPIO pin and timing configuration."""

        super().__init__(name)
        self.pin_name = pin_name
        self.read_interval_seconds = read_interval_seconds
        self.device: Any | None = None
        self.last_read_at = 0.0

    def setup(self) -> bool:
        """Initialize the DHT11 device on the configured Raspberry Pi GPIO pin."""

        if adafruit_dht is None or board is None:
            self.status = "disconnected"
            self.connected = False
            self.logger.error(
                "DHT11 dependencies are missing. Install adafruit-circuitpython-dht, "
                "adafruit-blinka, and lgpio in the container."
            )
            return False

        try:
            pin = getattr(board, self.pin_name)
        except AttributeError:
            self.status = "disconnected"
            self.connected = False
            self.logger.error("Unknown board pin for DHT11 service %s: %s", self.name, self.pin_name)
            return False

        try:
            self.device = self._create_device(pin)
        except Exception as error:
            self.status = "disconnected"
            self.connected = False
            self.logger.error("Failed to initialize DHT11 on %s: %s", self.pin_name, error)
            return False

        self.connected = True
        self.status = "online"
        self.logger.info("DHT11 initialized on %s", self.pin_name)
        return True

    def read(self) -> Optional[dict[str, float]]:
        """Return temperature and humidity readings, or None when unavailable."""

        if not self.connected or self.device is None:
            return None

        now = time.monotonic()
        if now - self.last_read_at < self.read_interval_seconds:
            return None

        self.last_read_at = now

        try:
            temperature = self.device.temperature
            humidity = self.device.humidity
        except RuntimeError as error:
            # DHT sensors commonly miss individual samples. Keep the service
            # online and let Home Assistant stale detection catch sustained loss.
            self.logger.warning("DHT11 timing/read error: %s", error)
            return None
        except Exception as error:
            self.logger.error("DHT11 read failed: %s", error)
            self.disconnect()
            return None

        if temperature is None or humidity is None:
            self.logger.warning("DHT11 returned an incomplete sample")
            return None

        self.status = "online"
        return {
            "temperature": round(float(temperature), 1),
            "humidity": round(float(humidity), 1),
        }

    def disconnect(self) -> None:
        """Release the DHT11 device object."""

        if self.device is not None:
            try:
                self.device.exit()
            except AttributeError:
                pass
            except Exception as error:
                self.logger.warning("DHT11 cleanup failed: %s", error)

        self.device = None
        self.connected = False
        self.status = "disconnected"

    @staticmethod
    def _create_device(pin: object) -> object:
        """Create the Adafruit DHT11 object, preferring Raspberry Pi-safe pulse IO."""

        try:
            return adafruit_dht.DHT11(pin, use_pulseio=True)
        except TypeError:
            return adafruit_dht.DHT11(pin)
