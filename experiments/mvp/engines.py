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
    def __init__(self, lib):
        self.lib = lib
        self.state, self.message = "loading", ""
        self.cond = threading.Condition()
        self.replies = {}
        self.wlock = threading.Lock()
        self.next_id = 0
        self.last_used = time.time()
        env = os.environ.copy()
        env.pop("DIGESTER_DATA", None)  # the engine points the round-8 code at the library itself
        # The library's ledger may already hold research spend; the engine may spend up to HEADROOM more on searches.
        env["DIGESTER_OPENAI_BUDGET_USD"] = f"{_library_spent(lib) + ENGINE_HEADROOM_USD:.4f}"
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
                else:
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

    def request(self, obj, timeout=300):
        with self.wlock:
            self.next_id += 1
            rid = obj["id"] = self.next_id
            self.proc.stdin.write(json.dumps(obj) + "\n")
            self.proc.stdin.flush()
        self.last_used = time.time()
        end = time.time() + timeout
        with self.cond:
            while rid not in self.replies:
                if self.state in ("error", "stopped") or time.time() > end:
                    return {"ok": False, "error": self.message or "engine not available"}
                self.cond.wait(1.0)
            return self.replies.pop(rid)

    def stop(self):
        try:
            self.proc.terminate()
        except OSError:
            pass


class EnginePool:
    def __init__(self, max_resident=MAX_RESIDENT):
        self.max_resident = max_resident
        self.engines = {}
        self.lock = threading.Lock()

    def get(self, lib):
        lib = os.path.abspath(lib)
        with self.lock:
            eng = self.engines.get(lib)
            if eng is None or eng.state in ("error", "stopped"):
                while len(self.engines) >= self.max_resident:
                    oldest = min(self.engines.values(), key=lambda e: e.last_used)
                    oldest.stop()
                    self.engines.pop(oldest.lib)
                eng = self.engines[lib] = EngineProcess(lib)
        if not eng.wait_ready():
            raise RuntimeError(f"search engine not available: {eng.message or eng.state}")
        return eng

    def warm(self, lib):
        """Start a library's engine without waiting (before a scheduled rule is due)."""
        threading.Thread(target=lambda: self.get(lib), daemon=True).start()

    def search(self, lib, query, depth=config.SEARCH_DEPTH):
        r = self.get(lib).request({"cmd": "search", "query": query, "processors": ["q8"], "depth": depth})
        if not r.get("ok"):
            raise RuntimeError(r.get("error") or "search failed")
        q8 = r["result"]["q8"]
        return {"ids": q8.get("ids") or [row["id"] for row in q8["results"]], "mode": q8["why"].get("mode"),
                "cost_usd": q8["why"].get("cost", {}).get("usd", 0.0)}

    def stop_all(self):
        with self.lock:
            for e in self.engines.values():
                e.stop()
            self.engines.clear()
