"""PROTOTYPE ONLY - signing in to an MCP server for one person, and keeping that sign-in fresh (round 10, slice C;
DESIGN.md section 17.C; amendment A-015, Proposed). The operator only this round (verdict M-3): the link opens a
page on the computer the bot runs on, and the server sends the person back to a small page on that same computer.

Our own OAuth 2.1 client, the SDK only as transport (research_mcp 3.3: the SDK forgets a token's expiry and its token
endpoint after a restart, so a 9 am rule would ask for a new sign-in). Each step as the MCP spec asks:
  discover   the server's Protected Resource Metadata (RFC 9728; its `resource` must be the server's own address),
             then its authorization server's metadata (RFC 8414 / OpenID); the `issuer` must be the one in
             mcp_mappings.SERVERS and the one asked; S256 must be offered; every endpoint is https on the issuer's host
  register   a Client ID Metadata Document when MVP_CIMD_URL is set and the server takes one, else Dynamic Client
             Registration as a native app (token_endpoint_auth_method none)
  start      PKCE S256, `state` (one use, 10 minutes, bound to the person), `resource`, the loopback redirect
             http://127.0.0.1:<MVP_CONNECT_PORT>/callback (default 8799; 8765 and 8791 are refused). The verifier and
             the state live in this process's memory only; the store keeps `oauthpending:<handle>` (when, which app)
  finish     the state checked, `iss` checked (RFC 9207) when sent or promised, the code exchanged; the tokens sealed
             by tokens.py with the absolute expiry, the token and revocation endpoints and the client id
  access_token  the sealed access token; less than 60 s left (or refused by the server): one refresh under
             tokens.lock, the new refresh token written BEFORE the new access token is used (rotation); a second
             caller waiting on the lock finds the fresh token and makes no request. No refresh token, `invalid_grant`,
             or no key to open the file: NeedsPerson (code needs_signin). Nothing here ever opens a browser or sends
             a link: a rule run gets NeedsPerson and falls back.
  revoke     RFC 7009, one request with the refresh token (else the access token)

Tests set OPENER: opener(method, url, headers, body_bytes, timeout) -> (status, headers, body_bytes). No token, code,
verifier or URL with a code in it is ever logged, stored in the store's tables, shown, or put in an error.
"""
import base64
import contextlib
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import tokens
from .mcp_client import McpError

TIMEOUT = 10
PENDING_LIFE = 10 * 60          # seconds a sign-in link works
REFRESH_EARLY = 60              # refresh when less than this many seconds are left
DEFAULT_PORT = 8799
FORBIDDEN_PORTS = (8765, 8791)  # the test page and the fake services of earlier rounds
CLIENT_NAME = "Digest assistant (test)"
OPENER = None
_PENDING = {}                   # state -> what finish needs; memory only (the verifier never leaves this process)
_PLOCK = threading.Lock()


def _now():
    return time.time()


class OAuthError(Exception):
    """A step of the sign-in failed. A code only: unreachable | no_prm | resource | issuer | no_s256 | endpoint |
    no_registration | registration | state | expired | iss | denied | exchange | port | key."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


class NeedsPerson(McpError):
    """Only the person can fix this (sign in again). A rule run falls back; nothing is opened or sent."""

    def __init__(self, app=None):
        super().__init__("needs_signin", app)


# ---------- HTTP ----------
def _urllib(method, url, headers, body, timeout):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=timeout) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, e.read() if e.fp else b""


def _http(method, url, form=None, body_json=None, accept="application/json"):
    """(status, headers, parsed JSON or {}). Raises OAuthError('unreachable') on no answer. https only."""
    if urllib.parse.urlsplit(url).scheme != "https":
        raise OAuthError("endpoint")
    headers = {"Accept": accept, "User-Agent": "digest-prototype/0.10"}
    data = None
    if form is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        data = urllib.parse.urlencode(form).encode()
    elif body_json is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body_json).encode()
    if OPENER is None and os.environ.get("PYTEST_CURRENT_TEST"):
        raise OAuthError("unreachable")   # a test never reaches a real server, even by mistake
    try:
        status, hdrs, raw = (OPENER or _urllib)(method, url, headers, data, TIMEOUT)
    except Exception:  # noqa: BLE001 - no network, a time-out: a code only
        raise OAuthError("unreachable") from None
    hdrs = {str(k).lower(): v for k, v in (hdrs or {}).items()}
    try:
        parsed = json.loads(raw.decode("utf-8")) if raw else {}
    except (ValueError, UnicodeDecodeError):
        parsed = {}
    return status, hdrs, parsed if isinstance(parsed, dict) else {}


def _norm(url):
    return (url or "").rstrip("/")


def _host(url):
    return (urllib.parse.urlsplit(url or "").hostname or "").lower()


def _origin_path(url):
    s = urllib.parse.urlsplit(url)
    return f"{s.scheme}://{s.netloc}", s.path.rstrip("/")


# ---------- discovery ----------
def _resource_metadata_url(www):
    import re
    m = re.search(r'resource_metadata="([^"]+)"', www or "")
    return m.group(1) if m else None


def discover(conf):
    """The server's sign-in facts, checked. Returns {resource, issuer, authorization_endpoint, token_endpoint,
    registration_endpoint, revocation_endpoint, cimd, iss_param, scopes, fingerprint}. Raises OAuthError."""
    url = conf["url"]
    origin, path = _origin_path(url)
    tries = []
    st, hdrs, _ = _http("GET", url, accept="application/json, text/event-stream")
    hinted = _resource_metadata_url(hdrs.get("www-authenticate")) if st == 401 else None
    if hinted and _host(hinted) == _host(url):
        tries.append(hinted)
    tries += [f"{origin}/.well-known/oauth-protected-resource{path}", f"{origin}/.well-known/oauth-protected-resource"]
    prm = None
    for u in dict.fromkeys(tries):
        st, _, doc = _http("GET", u)
        if st == 200 and doc.get("authorization_servers"):
            prm = doc
            break
    if prm is None:
        raise OAuthError("no_prm")
    if _norm(prm.get("resource")) != _norm(url):
        raise OAuthError("resource")
    as_url = _norm(str((prm.get("authorization_servers") or [""])[0]))
    if urllib.parse.urlsplit(as_url).scheme != "https" or (conf.get("issuer") and as_url != _norm(conf["issuer"])):
        raise OAuthError("issuer")
    a_origin, a_path = _origin_path(as_url)
    meta = None
    for u in (f"{a_origin}/.well-known/oauth-authorization-server{a_path}",
              f"{a_origin}/.well-known/openid-configuration{a_path}", f"{as_url}/.well-known/openid-configuration"):
        st, _, doc = _http("GET", u)
        if st == 200 and doc.get("issuer"):
            meta = doc
            break
    if meta is None:
        raise OAuthError("no_prm")
    if _norm(meta.get("issuer")) != as_url:
        raise OAuthError("issuer")
    if "S256" not in (meta.get("code_challenge_methods_supported") or []):
        raise OAuthError("no_s256")
    host = _host(as_url)
    for k in ("authorization_endpoint", "token_endpoint", "registration_endpoint", "revocation_endpoint"):
        v = meta.get(k)
        if v and (urllib.parse.urlsplit(v).scheme != "https" or _host(v) != host):
            raise OAuthError("endpoint")
    if not meta.get("authorization_endpoint") or not meta.get("token_endpoint"):
        raise OAuthError("endpoint")
    out = {"resource": _norm(url), "issuer": as_url, "authorization_endpoint": meta["authorization_endpoint"],
           "token_endpoint": meta["token_endpoint"], "registration_endpoint": meta.get("registration_endpoint"),
           "revocation_endpoint": meta.get("revocation_endpoint"),
           "cimd": bool(meta.get("client_id_metadata_document_supported")),
           "iss_param": bool(meta.get("authorization_response_iss_parameter_supported")),
           "scopes": prm.get("scopes_supported") or []}
    out["fingerprint"] = hashlib.sha256(json.dumps(out, sort_keys=True).encode()).hexdigest()
    return out


def register(meta, conf, redirect_uri):
    """Our client id at this server: our CIMD address (MVP_CIMD_URL) when the server takes one, else a native app by
    Dynamic Client Registration."""
    cimd = (os.environ.get("MVP_CIMD_URL") or "").strip()
    if cimd and meta.get("cimd") and cimd.startswith("https://"):
        return cimd
    if not meta.get("registration_endpoint"):
        raise OAuthError("no_registration")
    st, _, doc = _http("POST", meta["registration_endpoint"], body_json={
        "client_name": CLIENT_NAME, "redirect_uris": [redirect_uri], "application_type": "native",
        "token_endpoint_auth_method": "none", "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"], "scope": conf.get("scope") or ""})
    cid = doc.get("client_id")
    if st not in (200, 201) or not isinstance(cid, str) or not 0 < len(cid) <= 300:
        raise OAuthError("registration")
    return cid


# ---------- the sign-in link and its return ----------
def connect_port():
    """MVP_CONNECT_PORT (default 8799). 8765 and 8791 are never used. 0 (tests) takes any free port."""
    try:
        port = int(os.environ.get("MVP_CONNECT_PORT") or DEFAULT_PORT)
    except ValueError:
        raise OAuthError("port") from None
    if port in FORBIDDEN_PORTS or not 0 <= port <= 65535:
        raise OAuthError("port")
    return port


def redirect_uri(port):
    return f"http://127.0.0.1:{port}/callback"


def _challenge(verifier):
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


def start(handle, key, port):
    """Discovers, registers and returns the link the person opens. Raises OAuthError."""
    from .mcp_mappings import SERVERS
    conf = SERVERS[key]
    meta = discover(conf)
    back = redirect_uri(port)
    client_id = register(meta, conf, back)
    verifier, state = secrets.token_urlsafe(48), secrets.token_urlsafe(24)
    with _PLOCK:
        for s in [s for s, p in _PENDING.items() if p["handle"] == handle or _now() - p["at"] > PENDING_LIFE]:
            del _PENDING[s]   # one link at a time per person; old ones die
        _PENDING[state] = {"handle": handle, "key": key, "verifier": verifier, "client_id": client_id,
                           "meta": {k: v for k, v in meta.items() if k != "fingerprint"}, "redirect_uri": back,
                           "at": _now()}
    q = {"response_type": "code", "client_id": client_id, "redirect_uri": back, "code_challenge": _challenge(verifier),
         "code_challenge_method": "S256", "state": state, "resource": meta["resource"]}
    if conf.get("scope"):
        q["scope"] = conf["scope"]
    return meta["authorization_endpoint"] + ("&" if "?" in meta["authorization_endpoint"] else "?") + \
        urllib.parse.urlencode(q)


def pending(handle):
    """True while a sign-in link of this person still works."""
    with _PLOCK:
        return any(p["handle"] == handle and _now() - p["at"] <= PENDING_LIFE for p in _PENDING.values())


def drop_pending(handle):
    with _PLOCK:
        for s in [s for s, p in _PENDING.items() if p["handle"] == handle]:
            del _PENDING[s]


def _take(state):
    """The pending sign-in this state belongs to (one use: it is gone after this), or OAuthError('state')."""
    with _PLOCK:
        for s in list(_PENDING):
            if isinstance(state, str) and hmac.compare_digest(s.encode(), state.encode()):
                return _PENDING.pop(s)
    raise OAuthError("state")


def finish(state, code, iss=None, error=None):
    """The person came back to the loopback page. Returns (handle, key) with the tokens sealed. Raises OAuthError
    (the pending sign-in is used up either way)."""
    p = _take(state)
    try:
        if _now() - p["at"] > PENDING_LIFE:
            raise OAuthError("expired")
        if error or not code:
            raise OAuthError("denied")
        meta = p["meta"]
        if (iss is not None or meta.get("iss_param")) and _norm(iss) != meta["issuer"]:
            raise OAuthError("iss")
        st, _, tok = _http("POST", meta["token_endpoint"], form={
            "grant_type": "authorization_code", "code": code, "redirect_uri": p["redirect_uri"],
            "client_id": p["client_id"], "code_verifier": p["verifier"], "resource": meta["resource"]})
        if st != 200 or not isinstance(tok.get("access_token"), str) or \
                str(tok.get("token_type", "bearer")).lower() != "bearer":
            raise OAuthError("exchange")
        _seal(p["handle"], p["key"], meta, p["client_id"], tok, None)
    except OAuthError as e:
        e.pending = {"handle": p["handle"], "key": p["key"]}   # who to tell; never the verifier or the code
        raise
    return p["handle"], p["key"]


def _seal(handle, key, meta, client_id, tok, old):
    try:
        expires_in = int(tok.get("expires_in") or 3600)
    except (TypeError, ValueError):
        expires_in = 3600
    data = {"issuer": meta["issuer"], "resource": meta["resource"], "client_id": client_id,
            "access_token": tok["access_token"],
            "refresh_token": tok.get("refresh_token") or (old or {}).get("refresh_token"),
            "expires_at": _now() + max(1, expires_in), "token_endpoint": meta["token_endpoint"],
            "revocation_endpoint": meta.get("revocation_endpoint"), "scope": tok.get("scope") or (old or {}).get("scope")}
    try:
        tokens.save(handle, key, data, issuer=meta["issuer"])
    except tokens.TokenKeyMissing:
        raise OAuthError("key") from None
    return data


# ---------- a fresh access token, and revoking ----------
def _load(handle, key):
    try:
        return tokens.load(handle, key)
    except tokens.TokenError:   # nothing sealed, no key, a copied or changed file: only a new sign-in fixes it
        raise NeedsPerson() from None


def access_token(handle, key, refused=None):
    """A usable access token for this person and app. `refused`: the token the server just refused (401), which
    forces one refresh unless another caller already made a new one. Raises NeedsPerson or McpError."""
    saved = _load(handle, key)
    if refused is None and saved.get("expires_at", 0) - REFRESH_EARLY > _now():
        return saved["access_token"]
    with tokens.lock(handle, key):
        saved = _load(handle, key)   # another caller may have refreshed while this one waited
        fresh = saved.get("expires_at", 0) - REFRESH_EARLY > _now()
        if fresh and (refused is None or not hmac.compare_digest(str(saved["access_token"]), str(refused))):
            return saved["access_token"]
        if not saved.get("refresh_token"):
            raise NeedsPerson()
        st, _, tok = _http("POST", saved["token_endpoint"], form={
            "grant_type": "refresh_token", "refresh_token": saved["refresh_token"], "client_id": saved["client_id"],
            "resource": saved["resource"]})
        if st in (400, 401) or (st == 200 and not isinstance(tok.get("access_token"), str)):
            raise NeedsPerson()       # invalid_grant: consent withdrawn, or the refresh token died
        if st == 429:
            raise McpError("rate")
        if st != 200:
            raise McpError("server")
        meta = {"issuer": saved["issuer"], "resource": saved["resource"], "token_endpoint": saved["token_endpoint"],
                "revocation_endpoint": saved.get("revocation_endpoint")}
        new = _seal(handle, key, meta, saved["client_id"], tok, saved)   # written before it is used (rotation)
        return new["access_token"]


def connected(handle, key):
    """A sign-in is sealed for this person and app (it may still need renewing)."""
    try:
        return tokens.exists(handle, key)
    except tokens.TokenError:
        return False


def revoke(handle, key):
    """RFC 7009: one request. True when the server said yes; False when it could not be reached, said no, or there
    was nothing to revoke. The sealed file is left for the caller to delete."""
    try:
        saved = tokens.load(handle, key)
    except tokens.TokenError:
        return False
    url = saved.get("revocation_endpoint")
    tok = saved.get("refresh_token") or saved.get("access_token")
    if not url or not tok:
        return False
    try:
        st, _, _ = _http("POST", url, form={"token": tok, "token_type_hint": "refresh_token" if saved.get(
            "refresh_token") else "access_token", "client_id": saved.get("client_id") or ""})
    except OAuthError:
        return False
    return st == 200


# ---------- the loopback page ----------
_PAGE = ("<!doctype html><meta charset=utf-8><title>{t}</title><body style=\"font-family:sans-serif;margin:3em\">"
         "<p>{t}</p></body>")


class Listener:
    """A tiny page on 127.0.0.1 that catches the server's redirect. It stops after PENDING_LIFE. `on_code(state,
    code, iss, error) -> bool` does the rest (in the bot). Request lines are never logged (they hold the code)."""

    def __init__(self, port, on_code):
        self.on_code = on_code
        listener = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):   # never: the query holds the code
                return

            def do_GET(self):
                u = urllib.parse.urlsplit(self.path)
                if u.path != "/callback":
                    self.send_response(404)
                    self.end_headers()
                    return
                q = dict(urllib.parse.parse_qsl(u.query))
                try:
                    ok = bool(listener.on_code(q.get("state"), q.get("code"), q.get("iss"), q.get("error")))
                except Exception:  # noqa: BLE001 - the page never shows why
                    ok = False
                body = _PAGE.format(t="Done. You can close this tab and go back to the chat." if ok else
                                    "That didn't work. Ask for a new link in the chat.").encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                self.wfile.write(body)
        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True, name="oauth-loopback")
        self.timer = threading.Timer(PENDING_LIFE + 5, self.stop)
        self.timer.daemon = True

    def start(self):
        self.thread.start()
        self.timer.start()
        return self

    def stop(self):
        self.timer.cancel()
        with contextlib.suppress(Exception):   # stopping twice, or a socket already closed
            self.server.shutdown()
            self.server.server_close()

    @property
    def alive(self):
        return self.thread.is_alive()


_LISTENER = {"it": None}
_LLOCK = threading.Lock()


def ensure_listener(on_code, port):
    """The loopback page on `port`, started once (a new one when the old one stopped). Raises OAuthError('port')."""
    with _LLOCK:
        cur = _LISTENER["it"]
        if cur is not None and cur.alive:
            cur.on_code = on_code
            cur.timer.cancel()
            cur.timer = threading.Timer(PENDING_LIFE + 5, cur.stop)
            cur.timer.daemon = True
            cur.timer.start()
            return cur
        try:
            _LISTENER["it"] = Listener(port, on_code).start()
        except OSError:
            raise OAuthError("port") from None
        return _LISTENER["it"]


def stop_listener():
    with _LLOCK:
        if _LISTENER["it"] is not None:
            _LISTENER["it"].stop()
            _LISTENER["it"] = None
