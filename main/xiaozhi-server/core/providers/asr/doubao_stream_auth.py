"""Eddie-fork helper: Volcengine streaming ASR auth + log redaction.

Upstream ``doubao_stream`` only sends old-console headers
``X-Api-App-Key`` / ``X-Api-Access-Key``. The new speech console issues a
single API Key that must be sent as ``X-Api-Key``.

When ``config.api_key`` is set (non-empty, not a ``你的…`` placeholder),
use the new header and omit the v1 ``app.appid`` / ``app.token`` payload
fields. Volcengine v3 bigmodel samples do not include an ``app`` section;
never send an empty or None appid.

Otherwise keep the upstream appid + access_token behaviour.

Do not put real keys in this module.
"""

from __future__ import annotations

import copy
from typing import Any, Mapping, Optional

# Config.yaml placeholders look like "你的火山引擎…"; never treat those as keys.
_PLACEHOLDER_MARK = "你的"

_SECRET_HEADER_NAMES = frozenset({"x-api-key", "x-api-access-key"})


def usable_api_key(config: Optional[Mapping[str, Any]]) -> Optional[str]:
    """Return a stripped API Key, or None when missing / placeholder."""
    if not config:
        return None
    raw = config.get("api_key")
    if raw is None:
        return None
    value = str(raw).strip()
    if not value or _PLACEHOLDER_MARK in value:
        return None
    return value


def use_api_key_auth(config: Optional[Mapping[str, Any]]) -> bool:
    return usable_api_key(config) is not None


def build_ws_auth_headers(
    config: Optional[Mapping[str, Any]],
    *,
    appid: Any,
    access_token: Any,
    resource_id: Any,
    connect_id: str,
) -> dict[str, Any]:
    """WebSocket handshake headers for Volcengine v3 sauc.

    New console: ``X-Api-Key`` + resource + connect id.
    Old console: ``X-Api-App-Key`` + ``X-Api-Access-Key`` + the same extras.
    """
    api_key = usable_api_key(config)
    if api_key is not None:
        return {
            "X-Api-Key": api_key,
            "X-Api-Resource-Id": resource_id,
            "X-Api-Connect-Id": connect_id,
        }
    return {
        "X-Api-App-Key": appid,
        "X-Api-Access-Key": access_token,
        "X-Api-Resource-Id": resource_id,
        "X-Api-Connect-Id": connect_id,
    }


def omit_app_section_if_api_key(
    request: dict, config: Optional[Mapping[str, Any]]
) -> dict:
    """Drop ``app`` (appid/token) when authenticating with ``X-Api-Key``."""
    if use_api_key_auth(config) and isinstance(request, dict):
        request.pop("app", None)
    return request


def mask_secret(value: Any, keep: int = 4) -> str:
    """First ``keep`` chars + ``***``; fully mask values that are too short."""
    if value is None:
        return "***"
    text = str(value)
    if len(text) <= keep:
        return "***"
    return f"{text[:keep]}***"


def redact_headers_for_log(headers: Any) -> Any:
    """Copy of headers with X-Api-Key / X-Api-Access-Key masked."""
    if not isinstance(headers, dict):
        return headers
    redacted = dict(headers)
    for key in list(redacted):
        if str(key).lower() in _SECRET_HEADER_NAMES:
            redacted[key] = mask_secret(redacted[key])
    return redacted


def redact_request_for_log(params: Any) -> Any:
    """Deep copy of the full-client-request JSON with ``app.token`` masked."""
    if not isinstance(params, dict):
        return params
    redacted = copy.deepcopy(params)
    app = redacted.get("app")
    if isinstance(app, dict) and "token" in app:
        app["token"] = mask_secret(app["token"])
    return redacted
