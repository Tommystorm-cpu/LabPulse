"""MQTT topics and cross-service payload contracts used by LabPulse."""

HOME_ASSISTANT_DISCOVERY_PREFIX = "homeassistant"
SENSOR_STATE_TOPIC_PREFIX = "home/sensor"
SMS_SEND_TOPIC = "labpulse/sms/send"
SMS_SUBSCRIPTION_TOPIC = "labpulse/sms/#"

SMS_ALERT_PAYLOAD_FIELDS = frozenset(
    {
        "event",
        "service",
        "service_label",
        "reading",
        "reading_label",
        "entity_id",
        "title",
        "message",
        "current",
        "minimum_threshold",
        "maximum_threshold",
    }
)


def sensor_state_topic(service_name: str, reading_name: str) -> str:
    """Return the MQTT state topic for one hardware reading."""

    return f"{SENSOR_STATE_TOPIC_PREFIX}/{service_name}/{reading_name}/state"


def service_status_topic(service_name: str) -> str:
    """Return the MQTT state topic for one hardware service status."""

    return f"{SENSOR_STATE_TOPIC_PREFIX}/{service_name}/status"


def sensor_discovery_topic(service_name: str, reading_name: str) -> str:
    """Return the Home Assistant discovery topic for one sensor reading."""

    return (
        f"{HOME_ASSISTANT_DISCOVERY_PREFIX}/sensor/"
        f"{service_name}_{reading_name}/config"
    )


def status_discovery_topic(service_name: str) -> str:
    """Return the Home Assistant discovery topic for one service status."""

    return (
        f"{HOME_ASSISTANT_DISCOVERY_PREFIX}/sensor/"
        f"{service_name}_status/config"
    )
