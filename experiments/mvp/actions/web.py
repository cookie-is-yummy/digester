"""PROTOTYPE ONLY - the one HTTP helper the token connectors use (round 9, E; DESIGN.md section 16.E).

One JSON request with a 10-second timeout and no redirect to another host. Errors keep only a code, never the URL,
a header, the token or the body (they can hold secrets or titles):
  refused  401 or 403 (the token was refused, or the address no longer takes requests)
  rate     429 (asked to slow down)
  gone     404 or 410
  server   500 and up
  timeout  no answer in 10 seconds
  failed   anything else (another status, a redirect to another host, no network, a body that is not JSON)

Tests set OPENER to a fake: opener(method, url, headers, body_bytes, timeout) -> (status, body_bytes). No test opens
a network connection.
"""
import json
import socket
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from ..connectors import ConnectorError

TIMEOUT = 10
OPENER = None


class _SameHostOnly(urllib.request.HTTPRedirectHandler):
    """A redirect is followed only to the same host (an API never needs more); else the 3xx is the answer."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).hostname != urlsplit(req.full_url).hostname or urlsplit(newurl).scheme != "https":
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _urllib(method, url, headers, body, timeout):
    opener = urllib.request.build_opener(_SameHostOnly)
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with opener.open(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except urllib.error.URLError as e:
        if isinstance(getattr(e, "reason", None), (socket.timeout, TimeoutError)):
            raise TimeoutError() from None
        raise ConnectionError() from None


def call(method, url, token=None, body=None, app=None):
    """Sends one request; returns the parsed JSON answer ({} when there is none). Raises ConnectorError(code, app)."""
    if urlsplit(url).scheme != "https":
        raise ConnectorError("failed", app)
    headers = {"Accept": "application/json", "User-Agent": "digest-prototype/0.9"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        status, raw = (OPENER or _urllib)(method, url, headers, data, TIMEOUT)
    except (socket.timeout, TimeoutError):
        raise ConnectorError("timeout", app) from None
    except ConnectorError as e:
        raise ConnectorError(e.code, app) from None
    except Exception:  # noqa: BLE001 - no network, a bad answer: only a code leaves this function
        raise ConnectorError("failed", app) from None
    if status in (401, 403):
        raise ConnectorError("refused", app)
    if status == 429:
        raise ConnectorError("rate", app)
    if status in (404, 410):
        raise ConnectorError("gone", app)
    if status >= 500:
        raise ConnectorError("server", app)
    if not 200 <= status < 300:
        raise ConnectorError("failed", app)
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError:
        return {}
