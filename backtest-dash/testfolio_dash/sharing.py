from __future__ import annotations

import base64
import json
import zlib
from collections.abc import Mapping
from typing import Any

ANALYSIS_SCHEMA_VERSION = 1


def encode_analysis_state(state: Mapping[str, Any]) -> str:
    payload = json.dumps(
        {"version": ANALYSIS_SCHEMA_VERSION, "state": state}, separators=(",", ":"), sort_keys=True
    ).encode()
    return base64.urlsafe_b64encode(zlib.compress(payload, 9)).decode().rstrip("=")


def decode_analysis_state(token: str) -> dict[str, Any]:
    if len(token) > 100_000:
        raise ValueError("Analysis state is too large.")
    padding = "=" * (-len(token) % 4)
    try:
        payload = zlib.decompress(base64.urlsafe_b64decode(token + padding))
        if len(payload) > 1_000_000:
            raise ValueError("Analysis state is too large.")
        data = json.loads(payload)
    except (ValueError, TypeError, json.JSONDecodeError, zlib.error) as error:
        raise ValueError("Invalid analysis state.") from error
    if (
        not isinstance(data, dict)
        or data.get("version") != ANALYSIS_SCHEMA_VERSION
        or not isinstance(data.get("state"), dict)
    ):
        raise ValueError("Unsupported analysis state version.")
    return data["state"]
