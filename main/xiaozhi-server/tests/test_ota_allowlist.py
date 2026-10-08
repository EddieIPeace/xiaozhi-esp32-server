"""Focused tests for the Eddie-fork OTA allowlist helper.

These tests stay dependency-light (no aiohttp / torch) so CI can run them
without installing the full server requirements.

Run with ``pytest --noconftest tests/test_ota_allowlist.py`` to skip the
heavy tests/conftest.py import chain.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVER_ROOT))

from core.api.ota_allowlist import (
    is_device_on_allowlist,
    restrict_ota_to_allowed_devices_enabled,
    should_refuse_unknown_ota_device,
    unknown_device_ota_payload,
)

ALLOWED = "aa:bb:cc:dd:ee:ff"
STRANGER = "11:22:33:44:55:00"


def test_flag_absent_is_upstream_off():
    assert restrict_ota_to_allowed_devices_enabled({}) is False
    assert restrict_ota_to_allowed_devices_enabled(None) is False
    assert restrict_ota_to_allowed_devices_enabled({"enabled": True}) is False


def test_flag_false_is_off():
    assert (
        restrict_ota_to_allowed_devices_enabled(
            {"restrict_ota_to_allowed_devices": False}
        )
        is False
    )


def test_flag_true_and_yaml_string_true():
    assert (
        restrict_ota_to_allowed_devices_enabled(
            {"restrict_ota_to_allowed_devices": True}
        )
        is True
    )
    assert (
        restrict_ota_to_allowed_devices_enabled(
            {"restrict_ota_to_allowed_devices": "true"}
        )
        is True
    )
    assert (
        restrict_ota_to_allowed_devices_enabled(
            {"restrict_ota_to_allowed_devices": "false"}
        )
        is False
    )


def test_allowlist_match_is_exact():
    assert is_device_on_allowlist(ALLOWED, [ALLOWED]) is True
    assert is_device_on_allowlist(ALLOWED.upper(), [ALLOWED]) is False
    assert is_device_on_allowlist(STRANGER, [ALLOWED]) is False
    assert is_device_on_allowlist("", [ALLOWED]) is False


def test_allowlist_accepts_single_string():
    assert is_device_on_allowlist(ALLOWED, ALLOWED) is True


def test_refuse_when_flag_on_and_device_unknown():
    auth = {
        "restrict_ota_to_allowed_devices": True,
        "allowed_devices": [ALLOWED],
    }
    assert should_refuse_unknown_ota_device(auth, STRANGER) is True
    assert should_refuse_unknown_ota_device(auth, ALLOWED) is False


def test_refuse_everyone_when_flag_on_and_list_empty():
    auth = {"restrict_ota_to_allowed_devices": True, "allowed_devices": []}
    assert should_refuse_unknown_ota_device(auth, ALLOWED) is True


def test_never_refuse_when_flag_absent_or_false():
    with_list = {"enabled": True, "allowed_devices": [ALLOWED]}
    assert should_refuse_unknown_ota_device(with_list, STRANGER) is False
    assert (
        should_refuse_unknown_ota_device(
            {"restrict_ota_to_allowed_devices": False, "allowed_devices": [ALLOWED]},
            STRANGER,
        )
        is False
    )


def test_config_yaml_documents_restrict_flag_default_false():
    text = (_SERVER_ROOT / "config.yaml").read_text(
        encoding="utf-8"
    )
    assert "restrict_ota_to_allowed_devices:" in text
    assert "restrict_ota_to_allowed_devices: false" in text


def test_ota_handler_wires_allowlist_before_issuing_credentials():
    src = (
        _SERVER_ROOT / "core" / "api" / "ota_handler.py"
    ).read_text(encoding="utf-8")
    assert "should_refuse_unknown_ota_device" in src
    assert "unknown_device_ota_payload" in src
    refuse_at = src.index("should_refuse_unknown_ota_device")
    token_at = src.index("self.auth.generate_token")
    mqtt_at = src.index('return_json["mqtt"]')
    assert refuse_at < token_at
    assert refuse_at < mqtt_at


def test_unknown_device_payload_is_403_without_credentials():
    status, body, log_msg = unknown_device_ota_payload(STRANGER)
    assert status == 403
    assert body == {"success": False, "message": "device not allowed"}
    assert "websocket" not in body
    assert "mqtt" not in body
    assert "token" not in body
    assert STRANGER in log_msg
    assert "restrict_ota_to_allowed_devices" in log_msg
