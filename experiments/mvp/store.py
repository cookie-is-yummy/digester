"""PROTOTYPE ONLY - the MVP's own records, in one SQLite file under MVP_HOME (outside git).

Kept: people (handle, library folder, timezone, consent), their rules (their request text and the spec), runs (counts,
fit scores, cost; no captions), deliveries (item IDs), feedback, pending confirmations, the last answer's item IDs
(for follow-ups and "👎 2"), the channel IDs of sent messages (for tapbacks), and requests the bot could not do.
"""
import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS people (handle TEXT PRIMARY KEY, name TEXT, library TEXT NOT NULL, timezone TEXT NOT NULL,
  consent_version TEXT, consent_at TEXT, paused INTEGER DEFAULT 0, created_at TEXT);
CREATE TABLE IF NOT EXISTS rules (id INTEGER PRIMARY KEY AUTOINCREMENT, handle TEXT NOT NULL, text TEXT, spec TEXT NOT NULL,
  status TEXT NOT NULL, created_at TEXT, next_run_at TEXT, last_run_at TEXT);
CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY AUTOINCREMENT, handle TEXT, rule_id INTEGER, kind TEXT, at TEXT,
  n_candidates INTEGER, n_picks INTEGER, n_dropped INTEGER, fits TEXT, cost_usd REAL, status TEXT, error TEXT,
  prompt_version TEXT, seconds REAL);
CREATE TABLE IF NOT EXISTS deliveries (id INTEGER PRIMARY KEY AUTOINCREMENT, handle TEXT, rule_id INTEGER, run_id INTEGER,
  item_id TEXT, pick_number INTEGER, at TEXT);
CREATE TABLE IF NOT EXISTS feedback (id INTEGER PRIMARY KEY AUTOINCREMENT, handle TEXT, item_id TEXT, rule_id INTEGER,
  kind TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS pending (handle TEXT PRIMARY KEY, kind TEXT, payload TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS last_answer (handle TEXT PRIMARY KEY, run_id INTEGER, rule_id INTEGER, items TEXT,
  goal TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS sent (channel_ref TEXT PRIMARY KEY, handle TEXT, run_id INTEGER, at TEXT);
CREATE TABLE IF NOT EXISTS requests (id INTEGER PRIMARY KEY AUTOINCREMENT, handle TEXT, text TEXT, intent TEXT, at TEXT);
CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT);
"""


def now_iso(dt=None):
    return (dt or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.db.executescript(SCHEMA)
            self.db.commit()

    def x(self, sql, args=()):
        with self.lock:
            cur = self.db.execute(sql, args)
            self.db.commit()
            return cur

    def q(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        rows = self.q(sql, args)
        return rows[0] if rows else None

    # people
    def upsert_person(self, handle, name, library, tz):
        self.x("INSERT INTO people(handle,name,library,timezone,created_at) VALUES(?,?,?,?,?) "
               "ON CONFLICT(handle) DO UPDATE SET name=excluded.name, library=excluded.library, "
               "timezone=excluded.timezone", (handle, name, library, tz, now_iso()))

    def person(self, handle):
        return self.one("SELECT * FROM people WHERE handle=?", (handle,))

    def set_consent(self, handle, version):
        self.x("UPDATE people SET consent_version=?, consent_at=? WHERE handle=?", (version, now_iso(), handle))

    def set_timezone(self, handle, tz):
        self.x("UPDATE people SET timezone=? WHERE handle=?", (tz, handle))

    # rules
    def add_rule(self, handle, text, spec, status, next_run_at):
        cur = self.x("INSERT INTO rules(handle,text,spec,status,created_at,next_run_at) VALUES(?,?,?,?,?,?)",
                     (handle, text, json.dumps(spec), status, now_iso(), next_run_at))
        return cur.lastrowid

    def rules(self, handle, statuses=("active", "paused")):
        marks = ",".join("?" * len(statuses))
        rows = self.q(f"SELECT * FROM rules WHERE handle=? AND status IN ({marks}) ORDER BY id", (handle, *statuses))
        for r in rows:
            r["spec"] = json.loads(r["spec"])
        return rows

    def rule(self, rule_id):
        r = self.one("SELECT * FROM rules WHERE id=?", (rule_id,))
        if r:
            r["spec"] = json.loads(r["spec"])
        return r

    def update_rule(self, rule_id, **fields):
        if "spec" in fields:
            fields["spec"] = json.dumps(fields["spec"])
        sets = ", ".join(f"{k}=?" for k in fields)
        self.x(f"UPDATE rules SET {sets} WHERE id=?", (*fields.values(), rule_id))

    def due_rules(self, now):
        rows = self.q("SELECT * FROM rules WHERE status='active' AND next_run_at IS NOT NULL AND next_run_at<=? "
                      "ORDER BY next_run_at", (now_iso(now),))
        for r in rows:
            r["spec"] = json.loads(r["spec"])
        return rows

    # runs and deliveries
    def add_run(self, **f):
        f.setdefault("at", now_iso())
        keys = ",".join(f)
        cur = self.x(f"INSERT INTO runs({keys}) VALUES({','.join('?' * len(f))})", tuple(
            json.dumps(v) if isinstance(v, (list, dict)) else v for v in f.values()))
        return cur.lastrowid

    def add_delivery(self, handle, rule_id, run_id, item_id, pick_number, at=None):
        self.x("INSERT INTO deliveries(handle,rule_id,run_id,item_id,pick_number,at) VALUES(?,?,?,?,?,?)",
               (handle, rule_id, run_id, item_id, pick_number, now_iso(at)))

    def delivered(self, rule_id):
        return {r["item_id"] for r in self.q("SELECT item_id FROM deliveries WHERE rule_id=?", (rule_id,))}

    def scheduled_today(self, handle, day_start_utc):
        r = self.one("SELECT COUNT(*) n FROM runs WHERE handle=? AND kind='scheduled' AND status='sent' AND at>=?",
                     (handle, now_iso(day_start_utc)))
        return r["n"] if r else 0

    # feedback
    def add_feedback(self, handle, item_id, rule_id, kind):
        self.x("INSERT INTO feedback(handle,item_id,rule_id,kind,at) VALUES(?,?,?,?,?)",
               (handle, item_id, rule_id, kind, now_iso()))

    def disliked(self, handle):
        return {r["item_id"] for r in self.q("SELECT item_id FROM feedback WHERE handle=? AND kind='down'", (handle,))}

    def feedback_for_rule(self, rule_id):
        return self.q("SELECT item_id, kind FROM feedback WHERE rule_id=? ORDER BY id", (rule_id,))

    # conversation state
    def set_pending(self, handle, kind, payload):
        self.x("INSERT INTO pending(handle,kind,payload,at) VALUES(?,?,?,?) ON CONFLICT(handle) DO UPDATE SET "
               "kind=excluded.kind, payload=excluded.payload, at=excluded.at", (handle, kind, json.dumps(payload), now_iso()))

    def pending(self, handle):
        r = self.one("SELECT * FROM pending WHERE handle=?", (handle,))
        if r:
            r["payload"] = json.loads(r["payload"])
        return r

    def clear_pending(self, handle):
        self.x("DELETE FROM pending WHERE handle=?", (handle,))

    def set_last_answer(self, handle, run_id, rule_id, items, goal):
        self.x("INSERT INTO last_answer(handle,run_id,rule_id,items,goal,at) VALUES(?,?,?,?,?,?) ON CONFLICT(handle) "
               "DO UPDATE SET run_id=excluded.run_id, rule_id=excluded.rule_id, items=excluded.items, "
               "goal=excluded.goal, at=excluded.at", (handle, run_id, rule_id, json.dumps(items), goal, now_iso()))

    def last_answer(self, handle):
        r = self.one("SELECT * FROM last_answer WHERE handle=?", (handle,))
        if r:
            r["items"] = json.loads(r["items"])
        return r

    def record_sent(self, channel_ref, handle, run_id):
        if channel_ref:
            self.x("INSERT OR REPLACE INTO sent(channel_ref,handle,run_id,at) VALUES(?,?,?,?)",
                   (str(channel_ref), handle, run_id, now_iso()))

    def run_for_ref(self, channel_ref):
        r = self.one("SELECT run_id FROM sent WHERE channel_ref=?", (str(channel_ref),))
        return r["run_id"] if r else None

    def items_of_run(self, run_id):
        return self.q("SELECT item_id, rule_id, pick_number FROM deliveries WHERE run_id=? ORDER BY pick_number", (run_id,))

    def log_request(self, handle, text, intent):
        self.x("INSERT INTO requests(handle,text,intent,at) VALUES(?,?,?,?)", (handle, text[:500], intent, now_iso()))

    def get_state(self, key, default=None):
        r = self.one("SELECT value FROM state WHERE key=?", (key,))
        return json.loads(r["value"]) if r else default

    def set_state(self, key, value):
        self.x("INSERT OR REPLACE INTO state(key,value) VALUES(?,?)", (key, json.dumps(value)))

    def delete_person_data(self, handle):
        """'delete my data': everything the MVP holds about the person except a deletion marker."""
        with self.lock:
            for t in ("rules", "runs", "deliveries", "feedback", "pending", "last_answer", "sent", "requests"):
                self.db.execute(f"DELETE FROM {t} WHERE handle=?", (handle,))
            self.db.execute("DELETE FROM people WHERE handle=?", (handle,))
            self.db.commit()


def ts():
    return time.time()
