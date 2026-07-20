"""DHT11 GPIO driver for Raspberry Pi environment measurements."""

from collections.abc import Callable
from typing import Any, Optional
import time

from labpulse_hardware.drivers.base import BaseSensorDriver


FAILURE_LOG_INTERVAL_SECONDS = 60.0

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
        reconnect_interval_seconds: float,
        maximum_measurement_age_seconds: float,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        """Create a DHT11 driver from GPIO pin and timing configuration."""

        super().__init__(name)
        self.pin_name = pin_name
        self.read_interval_seconds = read_interval_seconds
        self.reconnect_interval_seconds = reconnect_interval_seconds
        self.maximum_measurement_age_seconds = maximum_measurement_age_seconds
        self._monotonic = monotonic
        self.device: Any | None = None
        self.last_read_at = 0.0
        self.last_success_at: float | None = None
        self.monitoring_started_at = self._monotonic()
        self.last_reconnect_attempt = -reconnect_interval_seconds
        self.last_failure_log_at = -FAILURE_LOG_INTERVAL_SECONDS
        self.sample_failure_active = False

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
        """Return temperature and humidity measurements, or None when unavailable."""

        if not self.connected or self.device is None:
            self._try_reconnect()
            return None

        now = self._monotonic()
        if now - self.last_read_at < self.read_interval_seconds:
            return None

        self.last_read_at = now

        try:
            temperature = self.device.temperature
            humidity = self.device.humidity
        except RuntimeError as error:
            # DHT sensors commonly miss individual samples. Keep the service
            # connected, but report an error after the configured freshness
            # interval so service health cannot remain misleadingly online.
            self._record_failed_sample(now, f"DHT11 timing/read error: {error}")
            return None
        except Exception as error:
            self.logger.error("DHT11 read failed: %s", error)
            self.disconnect()
            self.last_reconnect_attempt = now
            return None

        if temperature is None or humidity is None:
            self._record_failed_sample(now, "DHT11 returned an incomplete sample")
            return None

        if self.sample_failure_active:
            self.logger.info("DHT11 measurements recovered")
        self.sample_failure_active = False
        self.last_success_at = now
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

    def _record_failed_sample(self, now: float, message: str) -> None:
        """Mark sustained missing samples as an explicit service error."""

        if (
            not self.sample_failure_active
            or now - self.last_failure_log_at >= FAILURE_LOG_INTERVAL_SECONDS
        ):
            self.logger.warning(message)
            self.last_failure_log_at = now
        self.sample_failure_active = True

        freshness_reference = (
            self.last_success_at
            if self.last_success_at is not None
            else self.monitoring_started_at
        )
        missing_seconds = now - freshness_reference
        if (
            missing_seconds >= self.maximum_measurement_age_seconds
            and self.status != "error"
        ):
            self.status = "error"
            self.logger.error(
                "DHT11 has produced no valid sample for %.1f seconds",
                missing_seconds,
            )

    def _try_reconnect(self) -> bool:
        """Retry GPIO device initialization at the configured interval."""

        now = self._monotonic()
        if now - self.last_reconnect_attempt < self.reconnect_interval_seconds:
            return False

        self.last_reconnect_attempt = now
        self.status = "reconnecting"
        reconnected = self.setup()
        if not reconnected:
            self.status = "reconnecting"
        return reconnected

    @staticmethod
    def _create_device(pin: object) -> object:
        """Create the Adafruit DHT11 object, preferring Raspberry Pi-safe pulse IO."""

        try:
            return adafruit_dht.DHT11(pin, use_pulseio=True)
        except TypeError:
            return adafruit_dht.DHT11(pin)
