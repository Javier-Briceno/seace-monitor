"""
Shared utilities with no heavy dependencies (no Celery, no OCR, no AI).

Kept separate so tests can import these without loading the full task stack.
"""
import httpx

# HTTP 4xx codes that signal a permanent caller/config error and must not be retried.
# 5xx codes (server errors, overload) are transient and should be retried.
_PERMANENT_HTTP_CODES = frozenset({400, 401, 403, 404, 422})


def _is_permanent(exc: Exception) -> bool:
    """Return True for errors that retrying cannot fix.

    json.JSONDecodeError is a subclass of ValueError, so it is treated as
    permanent here. In practice Haiku JSON-parse errors are caught inside
    extract_semantic_fields() before they reach this path; any JSONDecodeError
    that does propagate is likely from corrupt file data, not a transient glitch.
    """
    if isinstance(exc, (ValueError, TypeError, UnicodeDecodeError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _PERMANENT_HTTP_CODES
    return False
