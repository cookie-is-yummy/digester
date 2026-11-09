"""PROTOTYPE ONLY - Scroll Digest search demo: one command, a local web page, the round-8 search processor.

  python experiments/demo/app.py --library <folder> [--port 8765] [--no-browser]

<folder> is one library (a folder with corpus/items.jsonl) or a folder of libraries (e.g. the unzipped data pack,
which holds derrick/). New libraries made from uploaded exports are written next to the others.

The page is served on 127.0.0.1 only. API keys come from OPENAI_API_KEY / GEMINI_API_KEY or from the page's key
fields; the page's keys live in this process's memory (and the engine processes it starts) and are never written
or logged. Searches run in a separate engine process per library (engine.py), because the round-8 code reads its
data folder when imported. Uploaded exports stay on this computer: only item text (captions, titles, te inputs)
and the search text go to OpenAI / Gemini, for embeddings, the rewrite, the refine and the te pass.
"""
import argparse
import http.server
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ingest  # noqa: E402
import library as LIB  # noqa: E402

ENGINE = os.path.join(HERE, "engine.py")
PAGE = os.path.join(HERE, "static", "index.html")
VAR = {"openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY"}
PRIVACY = ("Everything stays on this computer: your exports, the library folders, the cost ledger and the cache of "
           "past searches. Only text is sent out: the search you type and item captions / titles go to OpenAI "
           "(embeddings, rewrite, refine) and, if you run the te pass, Instagram captions go to Gemini. "
           "Friends' posts are removed on import and never shown. DM message text is never read or stored.")


class Keys:
    def __init__(self):
        self.form = {"openai": None, "gemini": None}

    def get(self, prov):
        return self.form[prov] or os.environ.get(VAR[prov]) or None

    def child_env(self, extra=None):
        env = os.environ.copy()
        for prov, var in VAR.items():
            if self.form[prov]:
                env[var] = self.form[prov]
        env.update(extra or {})
        return env

    def status(self):
        return {p: ("this session" if self.form[p] else "environment" if os.environ.get(VAR[p]) else None)
                for p in VAR}


class Worker:
    """One engine.py serve process for one library; JSON lines over its stdin / stdout."""

    def __init__(self, lib, keys):
        self.lib = lib
        self.state, self.message, self.info = "loading", "", None
        self.t0 = time.time()
        self.cond = threading.Condition()
        self.replies = {}
        self.wlock = threading.Lock()
        self.next_id = 0
        self.proc = subprocess.Popen([sys.executable, ENGINE, "serve", lib], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, env=keys.child_env(), text=True, encoding="utf-8",
                                     bufsize=1)
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.proc.stdout:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            with self.cond:
                if "event" in msg:
                    ev = msg["event"]
                    if ev == "ready":
                        self.state, self.info = "ready", msg.get("info")
                        self.message = f"loaded in {time.time() - self.t0:.0f} s"
                    elif ev == "error":
                        self.state, self.message = "error", msg.get("message", "")
                else:
                    self.replies[msg.get("id")] = msg
                    if msg.get("info"):
                        self.info = msg["info"]
                self.cond.notify_all()
        with self.cond:
            if self.state != "error":
                self.state = "stopped"
                self.message = self.message or "the engine process ended"
            self.cond.notify_all()

    def _send(self, obj):
        with self.wlock:
            self.next_id += 1
            obj["id"] = self.next_id
            self.proc.stdin.write(json.dumps(obj) + "\n")
            self.proc.stdin.flush()
            return self.next_id

    def request(self, obj, timeout=600):
        rid = self._send(obj)
        end = time.time() + timeout
        with self.cond:
            while rid not in self.replies:
                if self.state in ("error", "stopped") or time.time() > end:
                    return {"ok": False, "error": self.message or "engine not available"}
                self.cond.wait(1.0)
            return self.replies.pop(rid)

    def send_nowait(self, obj):
        try:
            self._send(obj)
        except (OSError, ValueError):
            pass

    def stop(self):
        try:
            self.proc.terminate()
        except OSError:
            pass


class App:
    def __init__(self, path):
        self.root, _ = LIB.roots_and_libraries(path)
        self.path = os.path.abspath(path)
        os.makedirs(self.root, exist_ok=True)
        self.keys = Keys()
        self.worker = None
        self.lock = threading.RLock()
        self.uploads = {}
        self.jobs = {}
        self.prep = {}  # library path -> Popen
        self.search_lock = threading.Lock()

    def libraries(self):
        return LIB.roots_and_libraries(self.path)[1]

    def select(self, lib):
        lib = os.path.abspath(lib)
        if lib not in self.libraries():
            raise ValueError("unknown library")
        st = LIB.status(lib)
        if st["state"] != "ready":
            raise ValueError("this library is not prepared yet")
        with self.lock:
            if self.worker and self.worker.lib == lib and self.worker.state in ("loading", "ready"):
                return
            if self.worker:
                self.worker.stop()
            self.worker = Worker(lib, self.keys)

    def state(self):
        libs = []
        for lib in self.libraries():
            s = LIB.status(lib)
            s["active"] = bool(self.worker and self.worker.lib == lib)
            s["preparing_here"] = lib in self.prep and self.prep[lib].poll() is None
            libs.append(s)
        w = self.worker
        eng = {"state": "none"} if not w else {"state": w.state, "message": w.message, "info": w.info,
                                                "library": w.lib, "elapsed_s": round(time.time() - w.t0)}
        return {"libraries": libs, "engine": eng, "keys": self.keys.status(), "privacy": PRIVACY,
                "uploads": [{k: v for k, v in u.items() if k != "path"} for u in self.uploads.values()],
                "jobs": list(self.jobs.values()), "root": self.root}

    def set_keys(self, body):
        for prov in VAR:
            if prov in body:
                v = (body[prov] or "").strip()
                self.keys.form[prov] = v or None
        if self.worker:
            self.worker.send_nowait({"cmd": "keys", **{p: self.keys.get(p) for p in VAR}})

    def search(self, body):
        w = self.worker
        if not w or w.state != "ready":
            return 409, {"error": "The library is still loading." if w and w.state == "loading"
                         else "Choose a ready library first."}
        q = " ".join(str(body.get("query") or "").split())
        if not q:
            return 400, {"error": "Type a search."}
        procs = [p for p in body.get("processors") or ["q8"] if p in ("q8", "h0", "fm")][:2] or ["q8"]
        with self.search_lock:
            r = w.request({"cmd": "search", "query": q, "processors": procs})
        if not r.get("ok"):
            return 500, {"error": r.get("error") or "search failed"}
        return 200, r["result"]

    # ---------- uploads, import, prepare ----------
    def add_upload(self, kind, name, path, staged):
        if not zipfile.is_zipfile(path):
            if staged:
                os.remove(path)
            raise ValueError("That file is not a zip archive.")
        uid = secrets.token_hex(6)
        self.uploads[uid] = {"id": uid, "kind": kind, "name": os.path.basename(name), "path": path,
                             "bytes": os.path.getsize(path), "staged": staged}
        return self.uploads[uid]

    def drop_upload(self, uid):
        u = self.uploads.pop(uid, None)
        if u and u["staged"] and os.path.exists(u["path"]):
            os.remove(u["path"])

    def start_import(self, body):
        ids = [u for u in body.get("uploads") or [] if u in self.uploads]
        ig = [self.uploads[u]["path"] for u in ids if self.uploads[u]["kind"] == "ig"]
        yt = [self.uploads[u]["path"] for u in ids if self.uploads[u]["kind"] == "yt"]
        own = [x.strip() for x in str(body.get("own_names") or "").split(",") if x.strip()]
        name = str(body.get("name") or "").strip() or "My library"
        jid = secrets.token_hex(4)
        self.jobs[jid] = {"id": jid, "kind": "import", "state": "running", "name": name, "message": "importing…"}

        def run():
            try:
                lib = ingest.create_library(self.root, name, ig, yt, own, router_from=self.libraries())
                man = LIB.read_json(os.path.join(lib, "library.json"), {})
                self.jobs[jid].update(state="done", library=lib, counts=man.get("counts"),
                                      warnings=man.get("warnings"), message="imported; next: Prepare")
                for u in ids:
                    self.drop_upload(u)
            except Exception as e:  # noqa: BLE001 - shown to the user
                self.jobs[jid].update(state="error", message=str(e)[:300] if isinstance(e, ValueError)
                                      else f"import failed ({type(e).__name__})")
        threading.Thread(target=run, daemon=True).start()
        return self.jobs[jid]

    def estimate(self, lib):
        lib = self._lib(lib)
        r = subprocess.run([sys.executable, ENGINE, "estimate", lib], capture_output=True, text=True,
                           encoding="utf-8", env=self.keys.child_env(), timeout=600)
        if r.returncode:
            raise ValueError("could not estimate this library")
        out = json.loads(r.stdout.strip().splitlines()[-1])
        out["keys"] = {p: bool(self.keys.get(p)) for p in VAR}
        return out

    def prepare(self, body):
        lib = self._lib(body.get("path"))
        if lib in self.prep and self.prep[lib].poll() is None:
            raise ValueError("already preparing")
        if not self.keys.get("openai"):
            raise ValueError("Prepare needs an OpenAI key (embeddings). Add one above.")
        te = bool(body.get("te"))
        if te and not self.keys.get("gemini"):
            raise ValueError("The te pass needs a Gemini key. Add one, or choose 'skip te'.")
        cap = max(0.0, min(float(body.get("te_cap") or 1.0), 50.0))
        workers = max(1, min(int(body.get("workers") or 6), 16))
        est = body.get("estimate") or {}
        spent = est.get("spent_in_this_library") or {}
        extra = {"DIGESTER_GEMINI_BUDGET_USD": f"{(spent.get('gemini') or 0) + cap + 0.05:.4f}"}
        need = (spent.get("openai") or 0) + 1.5 * ((est.get("embed") or {}).get("cost_usd") or 0) + 0.5
        cur = float(os.environ.get("DIGESTER_OPENAI_BUDGET_USD", "4.00"))
        extra["DIGESTER_OPENAI_BUDGET_USD"] = f"{max(cur, need):.4f}"
        LIB.write_json(os.path.join(lib, "prepare_status.json"), {"state": "running", "step": "starting",
                                                                  "done": 0, "total": 0, "cost_usd": 0.0})
        self.prep[lib] = subprocess.Popen([sys.executable, ENGINE, "prepare", lib, "--te", "1" if te else "0",
                                           "--te-cap", str(cap), "--workers", str(workers)],
                                          env=self.keys.child_env(extra), stdout=subprocess.DEVNULL)
        threading.Thread(target=self._watch_prep, args=(lib,), daemon=True).start()
        return {"ok": True}

    def _watch_prep(self, lib):
        p = self.prep[lib]
        p.wait()
        st = LIB.read_json(os.path.join(lib, "prepare_status.json"), {}) or {}
        if st.get("state") == "running":  # killed or crashed before it could say so
            st.update(state="error", message="stopped" if p.returncode in (-15, 1, 15) else "prepare ended early")
            LIB.write_json(os.path.join(lib, "prepare_status.json"), st)

    def stop_prepare(self, lib):
        lib = self._lib(lib)
        p = self.prep.get(lib)
        if p and p.poll() is None:
            p.terminate()
        return {"ok": True}

    def _lib(self, lib):
        lib = os.path.abspath(str(lib or ""))
        if lib not in self.libraries():
            raise ValueError("unknown library")
        return lib


def make_handler(app, token, port):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class H(http.server.BaseHTTPRequestHandler):
        server_version = "ScrollDigestDemo/0.1"

        def log_message(self, *a):  # requests are not logged (search text travels in POST bodies)
            pass

        def _send(self, code, obj, ctype="application/json"):
            data = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def _ok_host(self):
            return self.headers.get("Host") in allowed_hosts

        def do_GET(self):
            if not self._ok_host():
                return self._send(403, {"error": "bad host"})
            path = urllib.parse.urlparse(self.path).path
            if path in ("/", "/index.html"):
                with open(PAGE, encoding="utf-8") as f:
                    html = f.read().replace("__DEMO_TOKEN__", token)
                return self._send(200, html.encode(), "text/html; charset=utf-8")
            if path == "/api/state":
                return self._send(200, app.state())
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self._ok_host() or self.headers.get("X-Demo-Token") != token:
                return self._send(403, {"error": "forbidden"})
            path = urllib.parse.urlparse(self.path).path
            try:
                if path == "/api/upload":
                    return self._upload()
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}") if n else {}
                if path == "/api/keys":
                    app.set_keys(body)
                    return self._send(200, {"keys": app.keys.status()})
                if path == "/api/select":
                    app.select(body.get("path"))
                    return self._send(200, {"ok": True})
                if path == "/api/search":
                    code, out = app.search(body)
                    return self._send(code, out)
                if path == "/api/upload_path":
                    p = os.path.abspath(os.path.expanduser(str(body.get("path") or "").strip().strip('"')))
                    if not os.path.isfile(p):
                        raise ValueError("No file at that path.")
                    return self._send(200, app.add_upload(body.get("kind"), p, p, staged=False))
                if path == "/api/discard_upload":
                    app.drop_upload(body.get("id"))
                    return self._send(200, {"ok": True})
                if path == "/api/import":
                    return self._send(200, app.start_import(body))
                if path == "/api/estimate":
                    return self._send(200, app.estimate(body.get("path")))
                if path == "/api/prepare":
                    return self._send(200, app.prepare(body))
                if path == "/api/prepare_stop":
                    return self._send(200, app.stop_prepare(body.get("path")))
                return self._send(404, {"error": "not found"})
            except ValueError as e:
                return self._send(400, {"error": str(e)})
            except Exception as e:  # noqa: BLE001
                return self._send(500, {"error": f"{type(e).__name__}"})

        def _upload(self):
            kind = self.headers.get("X-Kind")
            if kind not in ("ig", "yt"):
                raise ValueError("unknown upload kind")
            name = urllib.parse.unquote(self.headers.get("X-Filename") or "export.zip")
            n = int(self.headers.get("Content-Length") or 0)
            d = os.path.join(app.root, LIB.UPLOADS)
            os.makedirs(d, exist_ok=True)
            path = os.path.join(d, secrets.token_hex(8) + ".zip")
            left = n
            with open(path, "wb") as f:
                while left > 0:
                    chunk = self.rfile.read(min(left, 1 << 20))
                    if not chunk:
                        break
                    f.write(chunk)
                    left -= len(chunk)
            if left:
                os.remove(path)
                raise ValueError("upload interrupted")
            return self._send(200, app.add_upload(kind, name, path, staged=True))

    return H


def free_port(preferred):
    for p in [preferred] + list(range(preferred + 1, preferred + 50)):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise SystemExit("no free port")


def main():
    ap = argparse.ArgumentParser(description="Scroll Digest local search demo")
    ap.add_argument("--library", required=True, help="a library folder, or a folder of libraries")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    if not os.path.isdir(a.library):
        raise SystemExit(f"Not a folder: {a.library}")
    app = App(a.library)
    ready = [lib for lib in app.libraries() if LIB.status(lib)["state"] == "ready"]
    if ready:
        app.select(ready[0])
    port = free_port(a.port)
    token = secrets.token_urlsafe(24)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), make_handler(app, token, port))
    url = f"http://127.0.0.1:{port}/"
    print(f"Scroll Digest search demo: {url}  (libraries in {app.root}; Ctrl+C to stop)", flush=True)
    for prov in VAR:
        if not app.keys.get(prov):
            print(f"  no {VAR[prov]} set: you can paste one into the page (kept in memory only)", flush=True)
    if not a.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    def _term(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, _term)  # a plain kill also stops the engine and prepare processes
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if app.worker:
            app.worker.stop()
        for p in app.prep.values():
            if p.poll() is None:
                p.terminate()
        shutil.rmtree(os.path.join(app.root, LIB.UPLOADS), ignore_errors=True)


if __name__ == "__main__":
    main()
