"""PROTOTYPE ONLY - one demo engine process per library (the engine allows one library per process).

Speaks the demo engine's JSON-lines protocol (`engine.py serve LIB`). Up to MAX_RESIDENT engines stay loaded; the least
recently used one is stopped when another is needed. Search text travels in the process pipe only.
"""
import json
import os
import subprocess
import sys
import threading
import time

from . import config

MAX_RESIDENT = int(os.environ.get("MVP_MAX_ENGINES", "4"))
ENGINE_HEADROOM_USD = float(os.environ.get("MVP_ENGINE_HEADROOM_USD", "2.00"))


def _library_spent(lib):
    path = os.path.join(lib, "ai_runs.jsonl")
    if not os.path.exists(path):
        return 0.0
    with open(path) as f:
        return sum(json.loads(l).get("cost_usd", 0) for l in f if l.strip())


class EngineProcess:
    def __init__(self, lib, budget_usd):
        self.lib = lib
        self.state, self.message = "loading", ""
        self.cond = threading.Condition()
        self.replies = {}
        self.waiting = set()   # review fix X12: ids still waited for; a reply that comes after its time-out is dropped
        self.wlock = threading.Lock()
        self.next_id = 0
        self.busy = 0   # requests in flight: an engine that is answering is never stopped to make room
        self.last_used = time.time()
        env = os.environ.copy()
        env.pop("DIGESTER_DATA", None)  # the engine points the round-8 code at the library itself
        # The library's ledger may already hold research spend; the engine may spend up to HEADROOM more on searches.
        env["DIGESTER_OPENAI_BUDGET_USD"] = f"{budget_usd:.4f}"
        self.proc = subprocess.Popen([sys.executable, config.ENGINE, "serve", lib], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1, env=env)
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.proc.stdout:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            with self.cond:
                if "event" in msg:
                    if msg["event"] == "ready":
                        self.state = "ready"
                    elif msg["event"] == "error":
                        self.state, self.message = "error", msg.get("message", "")
                elif msg.get("id") in self.waiting:
                    self.replies[msg.get("id")] = msg
                self.cond.notify_all()
        with self.cond:
            if self.state != "error":
                self.state, self.message = "stopped", self.message or "the engine process ended"
            self.cond.notify_all()

    def wait_ready(self, timeout=600):
        end = time.time() + timeout
        with self.cond:
            while self.state == "loading" and time.time() < end:
                self.cond.wait(1.0)
            return self.state == "ready"

    def request(self, obj, timeout=90):
        with self.wlock:
            self.next_id += 1
            rid = obj["id"] = self.next_id
            self.busy += 1
            with self.cond:
                self.waiting.add(rid)
            self.proc.stdin.write(json.dumps(obj) + "\n")
            self.proc.stdin.flush()
        self.last_used = time.time()
        end = time.time() + timeout
        try:
            with self.cond:
                while rid not in self.replies:
                    if self.state in ("error", "stopped") or time.time() > end:
                        return {"ok": False, "error": self.message or "engine not available"}
                    self.cond.wait(1.0)
                return self.replies.pop(rid)
        finally:
            with self.cond:
                self.waiting.discard(rid)
                self.replies.pop(rid, None)
            with self.wlock:
                self.busy -= 1

    def stop(self):
        try:
            self.proc.terminate()
        except OSError:
            pass


class EnginePool:
    def __init__(self, max_resident=MAX_RESIDENT):
        self.max_resident = max_resident
        self.engines = {}
        self.budgets = {}  # fixed once per library per process, so restarts do not grant more headroom
        self.lock = threading.Lock()
        self.failed_at = {}   # review fix X12: when a library's engine last failed to load (no restart before RETRY_S)

    RETRY_S = 300

    def get(self, lib):
        lib = os.path.abspath(lib)
        with self.lock:
            eng = self.engines.get(lib)
            if eng is None or eng.state in ("error", "stopped"):
                if time.time() - self.failed_at.get(lib, 0) < self.RETRY_S and eng is not None:
                    # a multi-GB load that just failed is not started again by every message and warm-up tick
                    raise RuntimeError(f"search engine not available: {eng.message or eng.state}")
                while len(self.engines) >= self.max_resident:
                    idle = [e for e in self.engines.values() if e.busy == 0 and e.state != "loading"]
                    if not idle:
                        break  # every engine is answering or loading: go over the limit rather than cut one off
                    oldest = min(idle, key=lambda e: e.last_used)
                    oldest.stop()
                    self.engines.pop(oldest.lib)
                if lib not in self.budgets:
                    self.budgets[lib] = _library_spent(lib) + ENGINE_HEADROOM_USD
                eng = self.engines[lib] = EngineProcess(lib, self.budgets[lib])
        if not eng.wait_ready():
            if eng.state in ("error", "stopped"):
                self.failed_at[lib] = time.time()
            raise RuntimeError(f"search engine not available: {eng.message or eng.state}")
        return eng

    def is_ready(self, lib):
        eng = self.engines.get(os.path.abspath(lib))
        return bool(eng and eng.state == "ready")

    def warm(self, lib):
        """Start a library's engine without waiting (before a scheduled rule is due)."""
        threading.Thread(target=lambda: self.get(lib), daemon=True).start()

    def search(self, lib, query, depth=config.SEARCH_DEPTH):
        r = self.get(lib).request({"cmd": "search", "query": query, "processors": ["q8"], "depth": depth})
        if not r.get("ok"):
            raise RuntimeError(r.get("error") or "search failed")
        q8 = r["result"]["q8"]
        rw = q8["why"].get("rewrite") or {}
        # review fix X5: a search whose rewrite call failed used the raw query only; the engine still says "normal"
        degraded = q8["why"].get("path") == "rewrite" and not rw.get("used", True)
        return {"ids": q8.get("ids") or [row["id"] for row in q8["results"]], "mode": q8["why"].get("mode"),
                "cost_usd": q8["why"].get("cost", {}).get("usd", 0.0), "degraded": degraded}

    def stop_all(self):
        with self.lock:
            for e in self.engines.values():
                e.stop()
            self.engines.clear()
