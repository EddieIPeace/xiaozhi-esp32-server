"""Focused tests for Eddie-fork doubao_stream API Key auth + log redaction.

These tests stay dependency-light (no aiohttp / torch / websockets) so CI
can run them without installing the full server requirements.

Run with ``pytest --noconftest tests/test_doubao_stream_auth.py`` to skip
the heavy tests/conftest.py import chain.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVER_ROOT))

from core.providers.asr.doubao_stream_auth import (
    build_ws_auth_headers,
    mask_secret,
    omit_app_section_if_api_key,
    redact_headers_for_log,
    redact_request_for_log,
    use_api_key_auth,
    usable_api_key,
)

RESOURCE = "volc.seedasr.sauc.duration"
CONNECT_ID = "11111111-2222-3333-4444-555555555555"
LEGACY_APPID = "app-123456"
LEGACY_TOKEN = "tok-LEGACY-SECRET-VALUE-999"
NEW_API_KEY = "sk-NEW-CONSOLE-API-KEY-SECRET-aaa"


def _legacy_config(**extra):
    cfg = {
        "appid": LEGACY_APPID,
        "access_token": LEGACY_TOKEN,
        "resource_id": RESOURCE,
    }
    cfg.update(extra)
    return cfg


def test_legacy_headers_when_api_key_absent():
    headers = build_ws_auth_headers(
        _legacy_config(),
        appid=LEGACY_APPID,
        access_token=LEGACY_TOKEN,
        resource_id=RESOURCE,
        connect_id=CONNECT_ID,
    )
    assert headers == {
        "X-Api-App-Key": LEGACY_APPID,
        "X-Api-Access-Key": LEGACY_TOKEN,
        "X-Api-Resource-Id": RESOURCE,
        "X-Api-Connect-Id": CONNECT_ID,
    }
    assert "X-Api-Key" not in headers


def test_api_key_headers_replace_app_and_access_key():
    headers = build_ws_auth_headers(
        _legacy_config(api_key=NEW_API_KEY),
        appid=LEGACY_APPID,
        access_token=LEGACY_TOKEN,
        resource_id=RESOURCE,
        connect_id=CONNECT_ID,
    )
    assert headers == {
        "X-Api-Key": NEW_API_KEY,
        "X-Api-Resource-Id": RESOURCE,
        "X-Api-Connect-Id": CONNECT_ID,
    }
    assert "X-Api-App-Key" not in headers
    assert "X-Api-Access-Key" not in headers


def test_placeholder_or_empty_api_key_keeps_legacy():
    for raw in (None, "", "   ", "你的火山引擎新控制台API Key"):
        config = _legacy_config()
        if raw is not None:
            config["api_key"] = raw
        assert use_api_key_auth(config) is False
        assert usable_api_key(config) is None
        headers = build_ws_auth_headers(
            config,
            appid=LEGACY_APPID,
            access_token=LEGACY_TOKEN,
            resource_id=RESOURCE,
            connect_id=CONNECT_ID,
        )
        assert headers["X-Api-App-Key"] == LEGACY_APPID
        assert headers["X-Api-Access-Key"] == LEGACY_TOKEN
        assert "X-Api-Key" not in headers


def test_api_key_is_stripped():
    headers = build_ws_auth_headers(
        {"api_key": f"  {NEW_API_KEY}  "},
        appid=LEGACY_APPID,
        access_token=LEGACY_TOKEN,
        resource_id=RESOURCE,
        connect_id=CONNECT_ID,
    )
    assert headers["X-Api-Key"] == NEW_API_KEY


def test_omit_app_section_only_for_api_key():
    legacy_req = {
        "app": {"appid": LEGACY_APPID, "token": LEGACY_TOKEN},
        "user": {"uid": "streaming_asr_service"},
    }
    omit_app_section_if_api_key(legacy_req, _legacy_config())
    assert legacy_req["app"]["appid"] == LEGACY_APPID
    assert legacy_req["app"]["token"] == LEGACY_TOKEN

    key_req = {
        "app": {"appid": "None", "token": None},
        "user": {"uid": "streaming_asr_service"},
    }
    omit_app_section_if_api_key(key_req, {"api_key": NEW_API_KEY})
    assert "app" not in key_req
    assert key_req["user"]["uid"] == "streaming_asr_service"


def test_mask_secret_keeps_prefix_or_fully_hides_short_values():
    assert mask_secret(NEW_API_KEY) == "sk-N***"
    assert mask_secret("abcd") == "***"
    assert mask_secret("abc") == "***"
    assert mask_secret(None) == "***"


def test_redact_headers_never_contains_secret():
    headers = {
        "X-Api-Key": NEW_API_KEY,
        "X-Api-Access-Key": LEGACY_TOKEN,
        "X-Api-Resource-Id": RESOURCE,
        "X-Api-Connect-Id": CONNECT_ID,
    }
    redacted = redact_headers_for_log(headers)
    rendered = f"正在连接ASR服务，headers: {redacted}"
    assert NEW_API_KEY not in rendered
    assert LEGACY_TOKEN not in str(redacted)
    assert redacted["X-Api-Key"] == "sk-N***"
    assert redacted["X-Api-Access-Key"] == "tok-***"
    assert redacted["X-Api-Resource-Id"] == RESOURCE
    # original must stay intact so we never send the masked value
    assert headers["X-Api-Key"] == NEW_API_KEY
    assert headers["X-Api-Access-Key"] == LEGACY_TOKEN


def test_redact_request_never_contains_token():
    params = {
        "app": {"appid": LEGACY_APPID, "token": LEGACY_TOKEN},
        "user": {"uid": "u"},
    }
    redacted = redact_request_for_log(params)
    rendered = f"发送初始化请求: {redacted}"
    assert LEGACY_TOKEN not in rendered
    assert LEGACY_TOKEN not in str(redacted)
    assert redacted["app"]["token"] == "tok-***"
    assert redacted["app"]["appid"] == LEGACY_APPID
    assert params["app"]["token"] == LEGACY_TOKEN


def test_redact_headers_passthrough_for_none():
    assert redact_headers_for_log(None) is None


def test_config_yaml_documents_empty_api_key_on_v2():
    text = (_SERVER_ROOT / "config.yaml").read_text(encoding="utf-8")
    start = text.index("  DoubaoStreamASRV2:")
    end = text.index("  TencentASR:")
    section = text[start:end]
    assert "api_key:" in section
    assert 'api_key: ""' in section
    assert "新版语音控制台" in section
    assert "旧版控制台" in section


def test_provider_wires_helper_and_does_not_log_raw_secrets():
    src = (
        _SERVER_ROOT / "core" / "providers" / "asr" / "doubao_stream.py"
    ).read_text(encoding="utf-8")
    assert "build_ws_auth_headers" in src
    assert "omit_app_section_if_api_key" in src
    assert "redact_headers_for_log" in src
    assert "redact_request_for_log" in src
    assert "headers: {headers}" not in src
    assert "发送初始化请求: {request_params}" not in src
    assert "json.dumps(req," not in src
