"""Eddie-fork helper: optional OTA device allowlist.

Upstream single-server OTA (core/api/ota_handler.py) signs a websocket HMAC
token for any device that speaks the protocol when server.auth.enabled is
true. WebSocket then accepts that token; server.auth.allowed_devices only
skips token checks for listed devices, it does not deny everyone else.

When server.auth.restrict_ota_to_allowed_devices is true, OTA refuses to
issue websocket / MQTT credentials (and firmware metadata on that same
POST) to devices not listed in allowed_devices.

Absent or false = upstream behaviour. Do not put secrets in this module.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _as_device_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [raw] if raw else []
    if isinstance(raw, (list, tuple, set)):
        return [str(item) for item in raw if item is not None and str(item) != ""]
    return []


def restrict_ota_to_allowed_devices_enabled(auth_config: Optional[dict]) -> bool:
    if not auth_config:
        return False
    return _as_bool(auth_config.get("restrict_ota_to_allowed_devices", False))


def is_device_on_allowlist(device_id: str, allowed_devices: Iterable[Any]) -> bool:
    if not device_id:
        return False
    return device_id in set(_as_device_list(allowed_devices))


def should_refuse_unknown_ota_device(
    auth_config: Optional[dict], device_id: str
) -> bool:
    """Return True when OTA must not hand out credentials for this device."""
    if not restrict_ota_to_allowed_devices_enabled(auth_config):
        return False
    allowed = (auth_config or {}).get("allowed_devices")
    return not is_device_on_allowlist(device_id, allowed)


def unknown_device_ota_payload(device_id: str) -> tuple[int, dict, str]:
    """HTTP status, JSON body, and log line for a refused OTA POST."""
    return (
        403,
        {"success": False, "message": "device not allowed"},
        (
            f"OTA拒绝未授权设备 {device_id}：不在 server.auth.allowed_devices 中"
            "（restrict_ota_to_allowed_devices=true）"
        ),
    )
