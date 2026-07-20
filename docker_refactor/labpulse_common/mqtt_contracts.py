"""MQTT topics and cross-service payload contracts used by LabPulse."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

HOME_ASSISTANT_DISCOVERY_PREFIX = "homeassistant"
SENSOR_STATE_TOPIC_PREFIX = "home/sensor"
SMS_SEND_TOPIC = "labpulse/sms/send"
SMS_SUBSCRIPTION_TOPIC = SMS_SEND_TOPIC
SMS_STATUS_TOPIC = "labpulse/sms/status"
SMS_RESULT_TOPIC_PREFIX = "labpulse/sms/result"
SMS_STATUS_DISCOVERY_TOPIC = "homeassistant/sensor/labpulse_sms_status/config"


class SmsRequest(BaseModel):
    """One validated request published by Home Assistant for SMS delivery."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    request_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:-]+$")
    event: Literal["sensor_fault", "warning", "recovery", "notification", "test"]
    service: str = Field(min_length=1, max_length=80)
    measurement: str = Field(min_length=1, max_length=80)
    state: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=500)
    test_mode: bool = Field(default=False, strict=True)
    service_label: str | None = Field(default=None, max_length=120)
    measurement_label: str | None = Field(default=None, max_length=120)
    current_measurement: str | None = Field(default=None, max_length=80)


SMS_ALERT_PAYLOAD_FIELDS = frozenset(SmsRequest.model_fields)


def sms_result_topic(request_id: str) -> str:
    """Return the per-request topic used for SMS delivery results."""

    return f"{SMS_RESULT_TOPIC_PREFIX}/{request_id}"


def sensor_state_topic(service_name: str, measurement_name: str) -> str:
    """Return the MQTT state topic for one hardware measurement."""

    return f"{SENSOR_STATE_TOPIC_PREFIX}/{service_name}/{measurement_name}/state"


def service_status_topic(service_name: str) -> str:
    """Return the MQTT state topic for one hardware service status."""

    return f"{SENSOR_STATE_TOPIC_PREFIX}/{service_name}/status"


def sensor_discovery_topic(service_name: str, measurement_name: str) -> str:
    """Return the Home Assistant discovery topic for one sensor measurement."""

    return (
        f"{HOME_ASSISTANT_DISCOVERY_PREFIX}/sensor/"
        f"{service_name}_{measurement_name}/config"
    )


def status_discovery_topic(service_name: str) -> str:
    """Return the Home Assistant discovery topic for one service status."""

    return (
        f"{HOME_ASSISTANT_DISCOVERY_PREFIX}/sensor/"
        f"{service_name}_status/config"
    )
