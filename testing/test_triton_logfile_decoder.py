"""Tests for the JSON added around the existing Triton logfile decoder."""

import json
import math
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from firmware.triton_logfile_publisher_production import (
    create_mqtt_client,
    default_client_id,
    parse_args,
    record_to_json,
)
from firmware.triton_logfile_publisher_setup import (
    parse_args as parse_setup_args,
    record_to_json as setup_record_to_json,
)


def test_record_to_json_publishes_every_named_value() -> None:
    """Keep changing Triton headers and represent unavailable values as null."""

    payload = json.loads(record_to_json({
        "Time(secs)": 1_700_000_000.0,
        "Cold Plate T(K)": 0.0857,
        "header only in this logfile": 42.0,
        "disconnected channel": math.nan,
    }))

    assert payload == {
        "protocol": "labpulse.measurements",
        "version": 1,
        "recorded_at": 1_700_000_000.0,
        "measurements": {
            "Time(secs)": 1_700_000_000.0,
            "Cold Plate T(K)": 0.0857,
            "header only in this logfile": 42.0,
            "disconnected channel": None,
        },
    }
    assert json.loads(setup_record_to_json({
        "Time(secs)": 1_700_000_000.0,
        "Cold Plate T(K)": 0.0857,
        "header only in this logfile": 42.0,
        "disconnected channel": math.nan,
    })) == payload


def test_record_to_json_rejects_an_invalid_record_time() -> None:
    """Do not publish a snapshot that cannot participate in freshness checks."""

    try:
        record_to_json({"Time(secs)": math.inf})
    except ValueError as error:
        assert "Invalid Triton record time" in str(error)
    else:
        raise AssertionError("infinite record time was accepted")


def test_default_client_id_is_stable_and_computer_specific() -> None:
    """Control PCs must not disconnect one another by sharing a client ID."""

    with patch(
        "firmware.triton_logfile_publisher_production.socket.gethostname",
        return_value="Triton PC 01.lab",
    ):
        assert default_client_id() == "Triton-logfile-publisher-Triton-PC-01-lab"


def test_secure_publisher_arguments_are_the_default() -> None:
    """Production invocation requires broker verification and credentials."""

    args = parse_args(
        [
            "--directory", "D:/Triton/logs",
            "--broker", "labpulse-pi.local",
            "--username", "triton-01",
            "--password-file", "C:/LabPulse/password.txt",
            "--ca-certificate", "C:/LabPulse/ca.crt",
        ]
    )

    assert args.port == 8883
    assert args.topic == "labpulse/triton/measurements"
    assert args.insecure is False


def test_setup_publisher_uses_the_same_connection_contract() -> None:
    """Commissioning needs only settings that remain valid in production."""

    args = parse_setup_args(
        [
            "--directory", "D:/Triton/logs",
            "--broker", "labpulse-pi.local",
            "--topic", "labpulse/triton/triton-01/measurements",
            "--username", "triton-01",
            "--password-file", "C:/LabPulse/password.txt",
            "--ca-certificate", "C:/LabPulse/ca.crt",
        ]
    )

    assert args.port == 8883
    assert args.topic == "labpulse/triton/triton-01/measurements"


@pytest.mark.parametrize(
    "arguments",
    [
        ["--directory", "D:/logs", "--broker", "pi"],
        [
            "--directory", "D:/logs", "--broker", "pi", "--ca-certificate", "ca.crt"
        ],
        [
            "--directory", "D:/logs", "--broker", "pi", "--insecure",
            "--ca-certificate", "ca.crt",
        ],
        ["--directory", "D:/logs", "--broker", "pi", "--insecure", "--topic", "bad/#"],
    ],
)
def test_publisher_rejects_ambiguous_or_incomplete_security(
    arguments: list[str],
) -> None:
    """There must be no accidental plaintext or half-configured TLS mode."""

    with pytest.raises(SystemExit):
        parse_args(arguments)


def test_mqtt_client_applies_tls_authentication_and_identity(
    workspace_tmp_path: Path,
) -> None:
    """The validated CLI settings must reach Paho without exposing the password."""

    password_file = workspace_tmp_path / "password.txt"
    password_file.write_text("secret-value\n", encoding="utf-8")
    ca_file = workspace_tmp_path / "ca.crt"
    ca_file.write_text("test certificate", encoding="utf-8")
    args = parse_args(
        [
            "--directory", str(workspace_tmp_path),
            "--broker", "labpulse-pi.local",
            "--client-id", "Triton-fridge-01",
            "--username", "triton-01",
            "--password-file", str(password_file),
            "--ca-certificate", str(ca_file),
        ]
    )
    client = Mock()

    with patch(
        "firmware.triton_logfile_publisher_production.mqtt.Client",
        return_value=client,
    ) as factory:
        assert create_mqtt_client(args) is client

    assert factory.call_args.kwargs["client_id"] == "Triton-fridge-01"
    client.username_pw_set.assert_called_once_with("triton-01", "secret-value")
    client.tls_set.assert_called_once_with(ca_certs=str(ca_file))
    client.connect_async.assert_called_once_with("labpulse-pi.local", 8883, keepalive=60)
    client.loop_start.assert_called_once_with()
