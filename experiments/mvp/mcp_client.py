"""PROTOTYPE ONLY - the bot as an MCP client (round 10, slice C; DESIGN.md section 17.C; amendment A-015, Proposed).

Code picks the tool; the model never sees a tool, a description, a result or the server's `instructions`. A mapping
(mcp_mappings.py) may call only the tools pinned when the person connected: name plus a fingerprint of the name, input
schema, description and annotations. Before every call the tool list is read again; a tool that is gone or changed is
not called (`unpinned` / `changed`), and a tool the server adds later is never called (the mapping names its tools in
code). Arguments are built by code from the bot's own checked params and checked against the LIVE input schema before
they leave. Only the result fields a mapping names are read, and an id must look like an id. Errors keep a code only.

    transport.initialize()                    (not needed by the client: tools/list and tools/call are enough)
    transport.list_tools(cursor=None)         -> {"tools": [...], "nextCursor": str | None}
    transport.call_tool(name, arguments)      -> {"content": [...], "structuredContent"?, "isError"?, "resultType"?}
A transport raises an exception with `.status` (HTTP status or None), `.rpc_code` (JSON-RPC code or None) and
`.broken` (the stream broke after the server may have acted). tests/fakes/fake_mcp.FakeTransport is one; SdkTransport
below runs the real SDK (`mcp` 2.3.0) over Streamable HTTP with a Bearer header and is one too.

Error codes (McpError(code), a connectors.ConnectorError, so places.py's fallbacks and failure counts apply):
  refused        HTTP 401 after one refresh, or 403
  needs_signin   the sign-in cannot be renewed without the person (oauth.NeedsPerson), or 403 insufficient_scope
  timeout        no answer in time (a create that timed out may have arrived: never retried)
  server         HTTP 5xx, a broken stream (after a create: may have arrived), no network
  rate           HTTP 429
  protocol       a JSON-RPC error (-32602, -32601, -32022, ...)
  tool_error     a result with isError true
  changed        a pinned tool's fingerprint differs from the pin
  unpinned       the tool is gone, was never pinned, or is not safe to call (destructiveHint not false)
  bad_args       our arguments fail the live input schema (nothing is sent)
  bad_result     no id where the mapping expects one, or an "id" that is not an id
  input_required the server asks a question (never answered by the bot)
  partial        a batch failed and its cleanup failed too
  gone           the thing to delete is not there any more (counts as removed)

The daily discovery check, no token, no model call: `python -m mvp.mcp_client --discover` prints, for each server in
mcp_mappings.SERVERS, codes only (prm ok, as ok, s256 yes, ...) and whether the metadata's fingerprint changed since
the last check (kept in MVP_HOME/mcp_discovery.json).
"""
import asyncio
import hashlib
import json
import os
import re
import threading
import time

from .connectors import ConnectorError

CALL_TIMEOUT = 10.0      # seconds for one tools/call
LIST_TIMEOUT = 5.0       # seconds for one tools/list page
MAX_PAGES = 20           # a tool list longer than this many pages is refused (protocol)
ID_RX = re.compile(r"^[A-Za-z0-9_\-:.@/=+]{1,200}$")   # an id from a result; anything else is not an id
CODES = ("refused", "needs_signin", "timeout", "server", "rate", "protocol", "tool_error", "changed", "unpinned",
         "bad_args", "bad_result", "input_required", "partial", "gone")
TRANSPORT = None         # tests: a function (server_conf, access_token) -> transport; None: SdkTransport


def run_budget():
    """MVP_MCP_RUN_BUDGET_S (default 25): the most one action may spend on MCP calls in all (M-11)."""
    try:
        return max(1.0, float(os.environ.get("MVP_MCP_RUN_BUDGET_S") or 25))
    except ValueError:
        return 25.0


class McpError(ConnectorError):
    """A code only: never a URL, a token, an argument or any text a server sent. `made`: remote ids a failed batch
    made before it failed (ids only, for cleanup). `maybe_arrived`: a create whose answer was lost may have run."""

    def __init__(self, code, app=None, made=None, maybe_arrived=False):
        super().__init__(code, app)
        self.made = list(made or [])
        self.maybe_arrived = maybe_arrived


class TransportError(Exception):
    """What SdkTransport saw, shaped like the fake's WireError: a status or a JSON-RPC code, never any text."""

    def __init__(self, status=None, rpc_code=None, broken=False, www_authenticate=""):
        super().__init__(f"status={status} rpc={rpc_code} broken={broken}")
        self.status, self.rpc_code, self.broken, self.www_authenticate = status, rpc_code, broken, www_authenticate


def wire_code(e):
    """A transport exception -> one of CODES ('auth' for a 401, which the caller answers with one refresh)."""
    status, rpc, broken = getattr(e, "status", None), getattr(e, "rpc_code", None), getattr(e, "broken", False)
    if broken:
        return "server"
    if status == 401:
        return "auth"
    if status == 403:
        return "needs_signin" if "insufficient_scope" in str(getattr(e, "www_authenticate", "") or "") else "refused"
    if status == 429:
        return "rate"
    if isinstance(status, int) and status >= 500:
        return "server"
    if rpc is not None:
        return "protocol"
    if isinstance(e, (TimeoutError, asyncio.TimeoutError)):
        return "timeout"
    return "server"


def _as_error(e):
    """A transport exception as an McpError: the code only; a broken stream may have let the server act."""
    if isinstance(e, McpError):
        return e
    return McpError(wire_code(e), maybe_arrived=bool(getattr(e, "broken", False)))


def _run_with_timeout(fn, timeout):
    """fn() in a worker thread; McpError('timeout') when it has not answered in `timeout` seconds. Every other error
    keeps only its code (the exception is not chained, so no text a server sent travels with it)."""
    if timeout <= 0:
        raise McpError("timeout")
    box = {}

    def go():
        try:
            box["ok"] = fn()
        except BaseException as e:  # noqa: BLE001 - handed to the caller below, as a code
            box["err"] = e
    t = threading.Thread(target=go, daemon=True, name="mcp-call")
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise McpError("timeout")
    if "err" in box:
        err = box["err"]
        if isinstance(err, McpError):
            raise McpError(err.code, made=err.made, maybe_arrived=err.maybe_arrived) from None
        raise _as_error(err) from None
    return box["ok"]


# ---------- pins ----------
def fingerprint(tool):
    """sha256 of the tool's name, input schema, description and annotations (outputSchema left out: a server adding
    an output field must not void consent)."""
    body = {"name": tool.get("name"), "input": tool.get("inputSchema") or {}, "desc": tool.get("description") or "",
            "ann": tool.get("annotations") or {}}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def list_all(transport, deadline=None):
    """Every tool, over all pages: {name: tool}. Raises McpError."""
    tools, cursor = {}, None
    for _ in range(MAX_PAGES):
        page = _run_with_timeout(lambda c=cursor: transport.list_tools(c), _left(deadline, LIST_TIMEOUT))
        for t in (page or {}).get("tools") or []:
            if isinstance(t, dict) and isinstance(t.get("name"), str):
                tools.setdefault(t["name"], t)
        cursor = (page or {}).get("nextCursor")
        if not cursor:
            return tools
    raise McpError("protocol")


def destructive(tool):
    """Annotations are untrusted, so anything but an explicit destructiveHint false counts as destructive."""
    return (tool.get("annotations") or {}).get("destructiveHint") is not False


def pin(transport, mapping, deadline=None):
    """At the person's yes (connect, or "yes todoist" after a change): {tool: fingerprint} for every tool the mapping
    uses. A missing tool, or a create tool that says it may destroy things: McpError('unpinned')."""
    live = list_all(transport, deadline)
    pins = {}
    for name in mapping.tools():
        if name not in live or (name == mapping.tool and destructive(live[name])):
            raise McpError("unpinned")
        pins[name] = fingerprint(live[name])
    return pins


def changed_pins(transport, pins, deadline=None):
    """The pinned tools that are gone or changed now ([] when all are as pinned)."""
    live = list_all(transport, deadline)
    return sorted(n for n, fp in (pins or {}).items() if n not in live or fingerprint(live[n]) != fp)


def _check(live, pins, name):
    if name not in (pins or {}):
        raise McpError("unpinned")
    if name not in live:
        raise McpError("unpinned")
    if fingerprint(live[name]) != pins[name]:
        raise McpError("changed")
    return live[name]


def _left(deadline, cap):
    return cap if deadline is None else min(cap, deadline - time.monotonic())


def _call(transport, live, pins, name, args, deadline, may_destroy=False, creates=False):
    tool = _check(live, pins, name)
    if destructive(tool) and not may_destroy:
        raise McpError("unpinned")
    try:
        import jsonschema
        jsonschema.validate(args, tool.get("inputSchema") or {"type": "object"})
    except jsonschema.ValidationError:
        raise McpError("bad_args") from None
    except jsonschema.SchemaError:
        raise McpError("protocol") from None
    try:
        res = _run_with_timeout(lambda: transport.call_tool(name, args), _left(deadline, CALL_TIMEOUT))
    except McpError as e:
        # a create whose answer never came (time-out, broken stream) may have run: never retried, said so
        raise McpError(e.code, made=e.made, maybe_arrived=creates and (e.maybe_arrived or e.code == "timeout")) from None
    if not isinstance(res, dict):
        raise McpError("protocol")
    if res.get("resultType") == "input_required":
        raise McpError("input_required")    # never answered by the bot itself
    if res.get("isError"):
        raise McpError("gone" if (not creates and _says_not_found(res)) else "tool_error")
    return res


_NOT_FOUND = re.compile(r"\bnot\s+found\b|\bno\s+longer\s+exists\b|\bdoes\s?n[o']t\s+exist\b", re.IGNORECASE)


def _says_not_found(res):
    """Only for a delete that answered isError: the thing is already gone. The text is matched against this one fixed
    pattern and never kept, shown, logged or passed on."""
    for part in res.get("content") or []:
        if isinstance(part, dict) and part.get("type") == "text" and _NOT_FOUND.search(str(part.get("text") or "")[:200]):
            return True
    return False


# ---------- results are data ----------
def structured(res):
    """The result as data: structuredContent when it is an object; else the first text part that parses as a JSON
    object (prose parts, an injected line among them, are skipped and never read further)."""
    if isinstance(res.get("structuredContent"), dict):
        return res["structuredContent"]
    for part in res.get("content") or []:
        if not isinstance(part, dict) or part.get("type") != "text":
            continue
        try:
            v = json.loads(part.get("text") or "")
        except (TypeError, ValueError):
            continue
        if isinstance(v, dict):
            return v
    return {}


def an_id(v):
    if isinstance(v, bool) or not isinstance(v, (str, int)) or not ID_RX.match(str(v)):
        raise McpError("bad_result")
    return str(v)


# ---------- running a mapping ----------
def call_mapped(transport, pins, mapping, params, ctx, deadline=None):
    """Runs the mapping's creates; returns the remote ids made. All or nothing: when a later call fails, what the
    earlier calls made is deleted again with the mapping's undo tool; 'partial' when that cleanup fails too."""
    live = list_all(transport, deadline)
    made = []
    try:
        for args in mapping.build(params, ctx):
            res = _call(transport, live, pins, mapping.tool, args, deadline, creates=True)
            made += mapping.read(res)
    except McpError as e:
        made += e.made
        left = False
        for rid in made:
            try:
                _undo(transport, live, pins, mapping, rid, deadline)
            except McpError as d:
                left = left or d.code != "gone"
        raise McpError("partial" if left else e.code, maybe_arrived=e.maybe_arrived) from None
    return made


def _undo(transport, live, pins, mapping, remote_id, deadline):
    if not mapping.undo_tool:
        raise McpError("protocol")
    an_id(remote_id)
    _call(transport, live, pins, mapping.undo_tool, mapping.undo_args(remote_id), deadline, may_destroy=True)


def undo_ids(transport, pins, mapping, remote_ids, deadline=None):
    """Deletes things the bot made (ids from its own placements, never from text) with the mapping's undo tool.
    Returns {remote_id: "removed" | "gone" | <code>}."""
    live = list_all(transport, deadline)
    out = {}
    for rid in remote_ids:
        try:
            _undo(transport, live, pins, mapping, rid, deadline)
            out[rid] = "removed"
        except McpError as e:
            out[rid] = e.code
    return out


# ---------- the real transport: the SDK over Streamable HTTP, a Bearer header, one client per call ----------
class SdkTransport:
    """The official SDK as transport only (`mcp` 2.3.0). Each list or call opens one client in its own event loop in
    the calling thread and closes it. `target` is the server URL (or, in tests, an MCPServer for an in-process round
    trip); `http_client` (tests) replaces the httpx2 client the URL is reached with. The access token is only ever in
    the Authorization header. An HTTP status the server answered with is kept (an event hook), because the SDK turns
    a 401 into a JSON-RPC error without one."""

    def __init__(self, target, access_token=None, http_client=None, timeout=CALL_TIMEOUT):
        self.target, self._token, self._http, self.timeout = target, access_token, http_client, timeout
        self._status, self._www = None, ""

    async def _hook(self, response):
        if response.status_code >= 400:
            self._status = response.status_code
            self._www = response.headers.get("www-authenticate", "")

    def _client(self):
        from mcp import Client
        if not isinstance(self.target, str):
            return Client(self.target, read_timeout_seconds=self.timeout), None
        import httpx2
        from mcp.client.streamable_http import streamable_http_client
        http = self._http or httpx2.AsyncClient(
            headers={"Authorization": f"Bearer {self._token}"} if self._token else {},
            timeout=httpx2.Timeout(self.timeout))
        http.event_hooks.setdefault("response", []).append(self._hook)
        return Client(streamable_http_client(self.target, http_client=http),
                      read_timeout_seconds=self.timeout), http

    def _run(self, op):
        self._status, self._www = None, ""

        async def go():
            client, http = self._client()
            try:
                async with client as c:
                    return await asyncio.wait_for(op(c), self.timeout)
            finally:
                if http is not None and self._http is None:
                    await http.aclose()
        try:
            return asyncio.run(go())
        except (TimeoutError, asyncio.TimeoutError):
            raise McpError("timeout") from None
        except Exception as e:  # noqa: BLE001 - only a status or a code leaves; never the text
            from mcp.shared.exceptions import MCPError as SdkError
            rpc = e.code if isinstance(e, SdkError) else None
            if self._status:
                raise TransportError(status=self._status, www_authenticate=self._www) from None
            if rpc is not None:
                raise TransportError(rpc_code=rpc) from None
            raise TransportError(broken=True) from None

    def initialize(self):
        return {}

    def list_tools(self, cursor=None):
        async def op(c):
            r = await c.list_tools(cursor=cursor, cache_mode="bypass")
            return {"tools": [t.model_dump(mode="json", by_alias=True, exclude_none=True) for t in r.tools],
                    "nextCursor": getattr(r, "next_cursor", None) or getattr(r, "nextCursor", None)}
        return self._run(op)

    def call_tool(self, name, arguments):
        async def op(c):
            r = await c.call_tool(name, arguments)
            out = r.model_dump(mode="json", by_alias=True, exclude_none=True)
            if self._status:
                raise TransportError(status=self._status, www_authenticate=self._www)
            return out
        return self._run(op)


def transport_for(conf, access_token):
    if TRANSPORT is not None:
        return TRANSPORT(conf, access_token)
    if os.environ.get("PYTEST_CURRENT_TEST"):
        raise McpError("server")   # a test never reaches a real server, even by mistake
    return SdkTransport(conf["url"], access_token)


# ---------- the daily discovery check (no token, no model) ----------
def discover_all(out=print, now=None):
    """For each server in SERVERS: discovery without a token. Prints codes and fingerprint changes only; returns
    {key: {"code": ..., "changed": bool}}."""
    from . import config, oauth
    from .mcp_mappings import SERVERS
    path = os.path.join(config.HOME, "mcp_discovery.json")
    try:
        with open(path, encoding="utf-8") as f:
            before = json.load(f)
    except (OSError, ValueError):
        before = {}
    after, res = dict(before), {}
    for key, conf in SERVERS.items():
        try:
            meta = oauth.discover(conf)
        except oauth.OAuthError as e:
            res[key] = {"code": e.code, "changed": False}
            out(f"{key}: {e.code}")
            continue
        fp = meta.pop("fingerprint")
        changed = key in before and before[key] != fp
        after[key] = fp
        res[key] = {"code": "ok", "changed": changed}
        out(f"{key}: prm ok, as ok, s256 yes, cimd {'yes' if meta.get('cimd') else 'no'}, dcr "
            f"{'yes' if meta.get('registration_endpoint') else 'no'}, revoke "
            f"{'yes' if meta.get('revocation_endpoint') else 'no'}, "
            f"{'changed since the last check' if changed else 'same as the last check' if key in before else 'first check'}")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(after, f, indent=1)
    return res


if __name__ == "__main__":
    import sys
    if "--discover" in sys.argv[1:]:
        r = discover_all()
        sys.exit(0 if all(v["code"] == "ok" for v in r.values()) else 1)
    print("usage: python -m mvp.mcp_client --discover")
    sys.exit(2)
