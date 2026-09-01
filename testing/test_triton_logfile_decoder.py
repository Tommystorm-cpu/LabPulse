"""Tests for the JSON added around the existing Triton logfile decoder."""

import json
import math

from firmware.triton_logfile_decoder import record_to_json


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


def test_record_to_json_rejects_an_invalid_record_time() -> None:
    """Do not publish a snapshot that cannot participate in freshness checks."""

    try:
        record_to_json({"Time(secs)": math.inf})
    except ValueError as error:
        assert "Invalid Triton record time" in str(error)
    else:
        raise AssertionError("infinite record time was accepted")

