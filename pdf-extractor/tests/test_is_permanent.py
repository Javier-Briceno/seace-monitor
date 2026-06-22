"""
Unit tests for utils._is_permanent().

No Celery, OCR, or AI dependencies needed — imports only utils.py.
"""
import json
from unittest.mock import MagicMock

import httpx
import pytest

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils import _is_permanent


# ─── Permanent errors ─────────────────────────────────────────────────────────

def test_value_error_is_permanent():
    assert _is_permanent(ValueError("bad value")) is True


def test_type_error_is_permanent():
    assert _is_permanent(TypeError("wrong type")) is True


def test_unicode_decode_error_is_permanent():
    exc = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid byte")
    assert _is_permanent(exc) is True


def test_http_400_is_permanent():
    response = MagicMock()
    response.status_code = 400
    assert _is_permanent(httpx.HTTPStatusError("Bad Request", request=MagicMock(), response=response)) is True


def test_http_401_is_permanent():
    response = MagicMock()
    response.status_code = 401
    assert _is_permanent(httpx.HTTPStatusError("Unauthorized", request=MagicMock(), response=response)) is True


def test_http_403_is_permanent():
    response = MagicMock()
    response.status_code = 403
    assert _is_permanent(httpx.HTTPStatusError("Forbidden", request=MagicMock(), response=response)) is True


def test_http_404_is_permanent():
    response = MagicMock()
    response.status_code = 404
    assert _is_permanent(httpx.HTTPStatusError("Not Found", request=MagicMock(), response=response)) is True


def test_http_422_is_permanent():
    response = MagicMock()
    response.status_code = 422
    assert _is_permanent(httpx.HTTPStatusError("Unprocessable Entity", request=MagicMock(), response=response)) is True


# ─── Transient errors ─────────────────────────────────────────────────────────

def test_http_500_is_transient():
    response = MagicMock()
    response.status_code = 500
    assert _is_permanent(httpx.HTTPStatusError("Internal Server Error", request=MagicMock(), response=response)) is False


def test_http_429_is_transient():
    response = MagicMock()
    response.status_code = 429
    assert _is_permanent(httpx.HTTPStatusError("Too Many Requests", request=MagicMock(), response=response)) is False


def test_http_503_is_transient():
    response = MagicMock()
    response.status_code = 503
    assert _is_permanent(httpx.HTTPStatusError("Service Unavailable", request=MagicMock(), response=response)) is False


def test_runtime_error_is_transient():
    assert _is_permanent(RuntimeError("connection reset")) is False


def test_os_error_is_transient():
    assert _is_permanent(OSError("disk full")) is False


# ─── json.JSONDecodeError (subclass of ValueError) ────────────────────────────

def test_json_decode_error_is_permanent_via_valueerror():
    # json.JSONDecodeError IS-A ValueError, so it is classified as permanent.
    # Haiku JSON-parse errors are caught in extract_semantic_fields() before
    # reaching this function, so any JSONDecodeError here indicates corrupt
    # file data rather than a transient model fluke.
    exc = json.JSONDecodeError("Expecting value", "", 0)
    assert isinstance(exc, ValueError)   # confirm the inheritance
    assert _is_permanent(exc) is True
