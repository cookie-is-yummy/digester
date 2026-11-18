"""PROTOTYPE ONLY - the "virtual machine": a browser inside the bot's own machine that the person watches and takes over
on the test page (round 10, slice V5; DESIGN.md section 17.V; the addendum's section 1; amendment A-016, Proposed).

    MVP_BROWSER=vm   browser.make_host("vm") -> VmHost()

`VmHost` is the second implementation of browser_host's `Host` seam: a headless Chromium (it works in a container with
no screen), one browser process per run, a fresh context thrown away at the end. Its session streams the page as JPEG
frames over the DevTools protocol (`Page.startScreencast`); only the newest frame is held, in memory; none is written.

The take-over view is served by the web test page (channels/web.py calls `handle_get` / `handle_post`):

    GET  /vm?k=<key>                     the page: the live picture, "Take over", "I'm done", "Stop everything"
    GET  /api/vm/frame?k=<key>&after=N   the newest frame (204 when none is newer, 410 when the run has ended)
    POST /api/vm/input?k=<key>           {"type": click|text|key|scroll|take|handback|stop, ...}; always 204

`<key>` is a random key per run, made when the browser opens and dropped when it closes. The person's clicks and keys
are forwarded to the page only while they hold it (the session's `takeover`); while they hold it the bot presses
nothing. What they type is forwarded and never logged, stored, echoed, counted by content or put in an exception: the
handler keeps a count of inputs only. The bot never types and never solves a check: at any wall it stops and gives this
link.
"""
import hmac
import json
import secrets
import threading
from urllib.parse import parse_qs

from .browser_host import Host, Session

VIEW_INPUT_MAX = 4096        # bytes of one input event
TEXT_MAX = 200               # characters of one typed chunk (a paste is cut here)


class VmSession(Session):
    """A run's headless browser with the live picture on."""
    screencast = True


class VmHost(Host):
    kind = "vm"
    session_class = VmSession

    def available(self):
        try:
            import playwright  # noqa: F401
        except ImportError:
            return False, "no_playwright"
        return True, "ok"

    def start(self, domains, install=None, asset_hosts=(), on_end=None):
        return self.session_class(domains, headless=True, install=install, asset_hosts=asset_hosts, on_end=on_end)


# ---------- the views of this process: key -> the run they show ----------
_VIEWS = {}
_LOCK = threading.Lock()


def open_view(bot, handle, run_id, session):
    """A new key for this run's view; returns the link the bot sends ("<page>/vm?k=<key>")."""
    key = secrets.token_urlsafe(24)
    with _LOCK:
        for k in [k for k, v in _VIEWS.items() if v["handle"] == handle]:
            _VIEWS.pop(k, None)   # one view per person: an older run's key stops working
        _VIEWS[key] = {"bot": bot, "handle": handle, "run_id": run_id, "session": session, "inputs": 0}
    base = getattr(getattr(bot, "channel", None), "base_url", None) or ""
    return f"{base}/vm?k={key}"


def drop_views(run_id):
    with _LOCK:
        for k in [k for k, v in _VIEWS.items() if v["run_id"] == run_id]:
            _VIEWS.pop(k, None)


def view(key):
    if not key:
        return None
    with _LOCK:
        for k, v in _VIEWS.items():
            if hmac.compare_digest(k, key):
                return v
    return None


def open_views():
    with _LOCK:
        return len(_VIEWS)


# ---------- the web page's side (channels/web.py) ----------
PAGE = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Your browser</title><meta name=referrer content=no-referrer><style>
body{margin:0;font:15px system-ui,sans-serif;background:#111;color:#eee}
#bar{padding:8px 12px;display:flex;flex-wrap:wrap;gap:10px;align-items:center}
#v{max-width:100%;display:block;outline:none;cursor:pointer}button{font-size:15px;padding:6px 10px}
#who{font-weight:600}</style>
<div id=bar><span id=who>Connecting...</span>
<button id=take>Take over</button><button id=done>I'm done</button><button id=stop>Stop everything</button></div>
<img id=v tabindex=0 alt="the browser">
<script>
const K = new URLSearchParams(location.search).get('k') || ''; const v = document.getElementById('v');
const who = document.getElementById('who'); let n = 0, held = false;
function say(h){ held = h === 'person'; who.textContent = held ?
  'You have the browser. I press nothing and I don\\'t keep what you type. Tap "I\\'m done" when you are.' :
  'I have the browser. Tap "Take over" to use it yourself.'; }
async function loop(){ for(;;){ try{ const r = await fetch('/api/vm/frame?k='+encodeURIComponent(K)+'&after='+n);
  if(r.status===200){ n = +r.headers.get('X-Frame'); say(r.headers.get('X-Held')); const b = await r.blob();
   const u = URL.createObjectURL(b); const old = v.src; v.src = u; if(old) URL.revokeObjectURL(old); }
  else if(r.status===204){ say(r.headers.get('X-Held')); }
  else { who.textContent = 'The browser has closed.'; break; } }
  catch(e){ await new Promise(s=>setTimeout(s,500)); } } }
function send(o){ return fetch('/api/vm/input?k='+encodeURIComponent(K),{method:'POST',body:JSON.stringify(o)}); }
v.addEventListener('click', e => { if(!held) return; const r = v.getBoundingClientRect();
  send({type:'click', x:(e.clientX-r.left)*v.naturalWidth/r.width, y:(e.clientY-r.top)*v.naturalHeight/r.height});
  v.focus(); });
v.addEventListener('wheel', e => { if(!held) return; e.preventDefault(); send({type:'scroll', dy:e.deltaY}); },
  {passive:false});
v.addEventListener('keydown', e => { if(!held || e.ctrlKey || e.metaKey) return; e.preventDefault();
  if (e.key.length === 1) send({type:'text', text:e.key}); else send({type:'key', key:e.key}); });
v.addEventListener('paste', e => { if(!held) return; e.preventDefault();
  send({type:'text', text:(e.clipboardData||window.clipboardData).getData('text').slice(0,200)}); });
document.getElementById('take').onclick = () => { send({type:'take'}); say('person'); v.focus(); };
document.getElementById('done').onclick = () => { send({type:'handback'}); say('bot'); };
document.getElementById('stop').onclick = () => send({type:'stop'});
loop();
</script>"""

KEYS = ("Enter", "Backspace", "Tab", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Escape", "Delete", "Home",
        "End")


def _empty(req, code, headers=()):
    req.send_response(code)
    req.send_header("Content-Length", "0")
    req.send_header("Cache-Control", "no-store")
    for k, val in headers:
        req.send_header(k, val)
    req.end_headers()


def _key(query):
    return (parse_qs(query).get("k") or [""])[0]


def handle_get(req, path, query):
    """The web channel's GET for /vm and /api/vm/frame. True when it answered."""
    if path == "/vm":
        if view(_key(query)) is None:
            _empty(req, 404)
            return True
        body = PAGE.encode()
        req.send_response(200)
        req.send_header("Content-Type", "text/html; charset=utf-8")
        req.send_header("Cache-Control", "no-store")
        req.send_header("Referrer-Policy", "no-referrer")
        req.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' blob:; "
                                                   "script-src 'unsafe-inline'; style-src 'unsafe-inline'")
        req.send_header("Content-Length", str(len(body)))
        req.end_headers()
        req.wfile.write(body)
        return True
    if path == "/api/vm/frame":
        v = view(_key(query))
        if v is None or not v["session"].alive:
            _empty(req, 410)
            return True
        try:
            after = int((parse_qs(query).get("after") or ["0"])[0])
        except ValueError:
            after = 0
        s = v["session"]
        held = ("X-Held", "person" if s.takeover else "bot")
        no, data = s.latest_frame(after)
        if not data or no <= after:
            _empty(req, 204, (held,))
            return True
        req.send_response(200)
        req.send_header("Content-Type", "image/jpeg")
        req.send_header("X-Frame", str(no))
        req.send_header(*held)
        req.send_header("Cache-Control", "no-store")
        req.send_header("Content-Length", str(len(data)))
        req.end_headers()
        try:
            req.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass
        return True
    return False


def handle_post(req, path, query):
    """The web channel's POST for /api/vm/input. True when it answered. Always an empty reply: nothing typed is echoed,
    kept or logged; a bad body is dropped."""
    if path != "/api/vm/input":
        return False
    v = view(_key(query))
    n = int(req.headers.get("Content-Length") or 0)
    raw = req.rfile.read(min(n, VIEW_INPUT_MAX)) if n > 0 else b""
    if v is None or n > VIEW_INPUT_MAX:
        _empty(req, 403 if v is None else 413)
        return True
    try:
        o = json.loads(raw or b"{}")
        kind = o.get("type") if isinstance(o, dict) else None
    except ValueError:
        o, kind = None, None
    raw = None
    v["inputs"] += 1
    s = v["session"]
    try:
        if kind == "click":
            s.post("view_click", float(o.get("x", 0)), float(o.get("y", 0)))
        elif kind == "text":
            s.post("view_text", str(o.get("text", ""))[:TEXT_MAX])
        elif kind == "key" and str(o.get("key", "")) in KEYS:
            s.post("view_key", str(o.get("key")))
        elif kind == "scroll":
            s.post("view_scroll", float(o.get("dy", 0)))
        elif kind == "take":
            s.post("takeover", True)
        elif kind in ("handback", "stop"):
            o = None
            threading.Thread(target=_event, args=(v, kind), daemon=True, name="browser-view-event").start()
    except (TypeError, ValueError):
        pass
    o = None   # the typed text is dropped here; nothing else holds it
    _empty(req, 204)
    return True


def _event(v, kind):
    try:
        v["bot"].browser_view_event(v["handle"], v["run_id"], kind)
    except Exception:  # noqa: BLE001 - a button on the view never breaks the bot; nothing of the input is kept
        pass
