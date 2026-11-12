"""PROTOTYPE ONLY - the MVP's own records, in one SQLite file under MVP_HOME (outside git).

Kept: people (handle, library folder, timezone, consent), their rules (their request text and the spec), runs (counts,
fit scores, cost; no captions), deliveries (item IDs), feedback, pending confirmations, the last answer's item IDs
(for follow-ups and "👎 2"), the channel IDs of sent messages (for tapbacks), and requests the bot could not do.
"""
import json
import os
import sqlite3
import threading
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
CREATE TABLE IF NOT EXISTS inbound (id INTEGER PRIMARY KEY AUTOINCREMENT, channel TEXT, ref TEXT, handle TEXT, text TEXT,
  tapback TEXT, tapback_ref TEXT, received_at TEXT, status TEXT, intent TEXT, run_id INTEGER, reply_ref TEXT,
  error TEXT, seconds REAL);
CREATE UNIQUE INDEX IF NOT EXISTS inbound_ref ON inbound(channel, ref) WHERE ref IS NOT NULL;
CREATE TABLE IF NOT EXISTS todos (id INTEGER PRIMARY KEY AUTOINCREMENT, handle TEXT NOT NULL, text TEXT NOT NULL,
  item_id TEXT, url TEXT, due_at TEXT, reminded_at TEXT, done_at TEXT, created_at TEXT, list TEXT DEFAULT 'todo',
  removed_at TEXT);
CREATE TABLE IF NOT EXISTS profile_notes (id INTEGER PRIMARY KEY AUTOINCREMENT, handle TEXT NOT NULL, text TEXT NOT NULL,
  at TEXT);
CREATE TABLE IF NOT EXISTS interp_cache (key TEXT PRIMARY KEY, handle TEXT, raw TEXT, at TEXT);
"""


# Columns added after the first build, each with a guarded ALTER TABLE so older stores still load.
ADDED_COLUMNS = [
    ("rules", "slot_at TEXT"),           # the time of the slot a rule is due for (next_run_at also holds retries and holds)
    ("rules", "paused_until TEXT"),      # a paused rule resumes at this UTC time ("pause it until Monday")
    ("rules", "skip_count INTEGER DEFAULT 0"),   # "skip the next two": the next N due sends are skipped and recorded
    ("rules", "skip_dates TEXT"),        # JSON list of local dates whose sends are skipped ("not on the 26th")
    ("people", "quiet TEXT"),            # JSON list of up to 4 quiet blocks; NULL = the default 22:00 to 08:00
    ("people", "snooze_until TEXT"),     # timed sends before this UTC time are skipped and recorded as 'snoozed'
    ("people", "tz_revert_to TEXT"),     # a temporary time zone: switch back to this zone ...
    ("people", "tz_revert_at TEXT"),     # ... at this UTC time
    ("runs", "lang TEXT"),               # the language the person wrote in, when it was not English (section 11)
]


def now_iso(dt=None):
    return (dt or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path):
        self.path = os.path.abspath(path)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.db.executescript(SCHEMA)
            for table, column in ADDED_COLUMNS:  # stores made by earlier builds gain these columns
                try:
                    self.db.execute(f"ALTER TABLE {table} ADD COLUMN {column}")
                except sqlite3.OperationalError:
                    pass  # already there
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
               "ON CONFLICT(handle) DO UPDATE SET name=excluded.name, library=excluded.library",
               (handle, name, library, tz, now_iso()))  # the time zone is set once: after that the person changes it by text

    def person(self, handle):
        return self.one("SELECT * FROM people WHERE handle=?", (handle,))

    def set_consent(self, handle, version):
        self.x("UPDATE people SET consent_version=?, consent_at=? WHERE handle=?", (version, now_iso(), handle))

    def set_timezone(self, handle, tz, revert_to=None, revert_at=None):
        """A plain change clears any planned switch back; with revert_to and revert_at (UTC) the change is temporary."""
        self.x("UPDATE people SET timezone=?, tz_revert_to=?, tz_revert_at=? WHERE handle=?",
               (tz, revert_to, now_iso(revert_at) if revert_at else None, handle))

    def timezone_reverts_due(self, now):
        return self.q("SELECT * FROM people WHERE tz_revert_at IS NOT NULL AND tz_revert_at<=?", (now_iso(now),))

    def quiet(self, handle):
        """The person's quiet blocks as dicts ({start, end, days}); the default when none are set."""
        from .schema import quiet_blocks
        r = self.one("SELECT quiet FROM people WHERE handle=?", (handle,))
        raw = json.loads(r["quiet"]) if r and r["quiet"] else None
        return [b.model_dump(exclude_defaults=True) for b in quiet_blocks(raw)]

    def set_quiet(self, handle, blocks):
        """Up to 4 blocks, validated; None restores the default."""
        from .schema import quiet_blocks
        value = None if blocks is None else json.dumps([b.model_dump(exclude_defaults=True) for b in quiet_blocks(blocks)])
        self.x("UPDATE people SET quiet=? WHERE handle=?", (value, handle))

    def set_snooze(self, handle, until=None):
        """'I'm away until the 20th': timed sends before `until` (aware datetime) are skipped. None clears it."""
        self.x("UPDATE people SET snooze_until=? WHERE handle=?", (now_iso(until) if until else None, handle))

    # rules
    def add_rule(self, handle, text, spec, status, next_run_at, created_at=None):
        cur = self.x("INSERT INTO rules(handle,text,spec,status,created_at,next_run_at,slot_at) VALUES(?,?,?,?,?,?,?)",
                     (handle, text, json.dumps(spec), status, created_at or now_iso(), next_run_at, next_run_at))
        return cur.lastrowid

    @staticmethod
    def _rule_row(r):
        r["spec"] = json.loads(r["spec"])
        r["skip_dates"] = json.loads(r.get("skip_dates") or "[]")
        r["skip_count"] = r.get("skip_count") or 0
        return r

    def rules(self, handle, statuses=("active", "paused")):
        marks = ",".join("?" * len(statuses))
        rows = self.q(f"SELECT * FROM rules WHERE handle=? AND status IN ({marks}) ORDER BY id", (handle, *statuses))
        return [self._rule_row(r) for r in rows]

    def rule(self, rule_id):
        r = self.one("SELECT * FROM rules WHERE id=?", (rule_id,))
        return self._rule_row(r) if r else None

    def update_rule(self, rule_id, **fields):
        if "spec" in fields:
            fields["spec"] = json.dumps(fields["spec"])
        sets = ", ".join(f"{k}=?" for k in fields)
        self.x(f"UPDATE rules SET {sets} WHERE id=?", (*fields.values(), rule_id))

    def set_slot(self, rule_id, next_run_at, status):
        """A rule's next real send time (or None). Retries and holds change next_run_at only, through update_rule."""
        self.x("UPDATE rules SET next_run_at=?, slot_at=?, status=? WHERE id=?", (next_run_at, next_run_at, status, rule_id))

    def due_rules(self, now):
        rows = self.q("SELECT * FROM rules WHERE status='active' AND next_run_at IS NOT NULL AND next_run_at<=? "
                      "ORDER BY next_run_at", (now_iso(now),))
        return [self._rule_row(r) for r in rows]

    def pause_rule(self, rule_id, until=None):
        """Paused; with `until` (aware datetime) the scheduler resumes it then."""
        self.x("UPDATE rules SET status='paused', paused_until=? WHERE id=?", (now_iso(until) if until else None, rule_id))

    def rules_to_resume(self, now):
        rows = self.q("SELECT * FROM rules WHERE status='paused' AND paused_until IS NOT NULL AND paused_until<=? "
                      "ORDER BY id", (now_iso(now),))
        return [self._rule_row(r) for r in rows]

    def skip(self, rule_id, count=0, dates=()):
        """'Skip the next two' adds to the count; 'not on the 26th' adds local dates. The scheduler consumes them."""
        with self.lock:
            r = self.rule(rule_id)
            if not r:
                return
            kept = sorted(set(r["skip_dates"]) | set(dates))
            self.x("UPDATE rules SET skip_count=?, skip_dates=? WHERE id=?",
                   ((r["skip_count"] or 0) + count, json.dumps(kept) if kept else None, rule_id))

    def consume_skip(self, rule_id, local_date):
        """At a due send: 'date' if its local date (YYYY-MM-DD) is skipped, else 'count' if a counted skip is left,
        else None. A skipped date covers every send on that day ("not on the 26th" with a rule that sends twice a
        day), so it is kept until the day has passed; a counted skip is used up."""
        with self.lock:
            r = self.rule(rule_id)
            if not r:
                return None
            dates = [d for d in r["skip_dates"] if d >= local_date]
            reason = None
            if local_date in dates:
                reason = "date"
            count = r["skip_count"]
            if reason is None and count > 0:
                count, reason = count - 1, "count"
            self.x("UPDATE rules SET skip_count=?, skip_dates=? WHERE id=?",
                   (count, json.dumps(dates) if dates else None, rule_id))
            return reason

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
        r = self.one("SELECT COUNT(*) n FROM runs WHERE handle=? AND kind IN ('scheduled','todo') AND status IN "
                     "('sent','none_sent','sending','unknown') AND at>=?",
                     (handle, now_iso(day_start_utc)))
        return r["n"] if r else 0

    # feedback
    def add_feedback(self, handle, item_id, rule_id, kind):
        self.x("INSERT INTO feedback(handle,item_id,rule_id,kind,at) VALUES(?,?,?,?,?)",
               (handle, item_id, rule_id, kind, now_iso()))

    def disliked(self, handle):
        """Items never to be sent again: 👎 and 'hide'."""
        return {r["item_id"] for r in self.q("SELECT item_id FROM feedback WHERE handle=? AND kind IN ('down','hide')",
                                             (handle,))}

    def feedback_for_rule(self, rule_id):
        return self.q("SELECT item_id, kind FROM feedback WHERE rule_id=? ORDER BY id", (rule_id,))

    # conversation state
    def set_pending(self, handle, kind, payload, at=None):
        self.x("INSERT INTO pending(handle,kind,payload,at) VALUES(?,?,?,?) ON CONFLICT(handle) DO UPDATE SET "
               "kind=excluded.kind, payload=excluded.payload, at=excluded.at",
               (handle, kind, json.dumps(payload), now_iso(at)))

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

    # to-dos (DESIGN.md sections 2 and 11)
    def add_todo(self, handle, text, list_name="todo", item_id=None, url=None, due_at=None, at=None):
        cur = self.x("INSERT INTO todos(handle,text,item_id,url,due_at,created_at,list) VALUES(?,?,?,?,?,?,?)",
                     (handle, text[:200], item_id, url, now_iso(due_at) if due_at else None, now_iso(at), list_name or "todo"))
        return cur.lastrowid

    def todos(self, handle):
        """Open to-dos in the order they are numbered to the person: the default list first, then the others by name,
        oldest first within a list. One numbering across all lists, so "done 3" always means the same to-do."""
        return self.q("SELECT * FROM todos WHERE handle=? AND done_at IS NULL AND removed_at IS NULL "
                      "ORDER BY CASE WHEN COALESCE(list,'todo')='todo' THEN 0 ELSE 1 END, list, id", (handle,))

    def todo(self, todo_id):
        return self.one("SELECT * FROM todos WHERE id=?", (todo_id,))

    def update_todo(self, todo_id, **fields):
        sets = ", ".join(f"{k}=?" for k in fields)
        self.x(f"UPDATE todos SET {sets} WHERE id=?", (*fields.values(), todo_id))

    def due_todos(self, now):
        return self.q("SELECT * FROM todos WHERE due_at IS NOT NULL AND due_at<=? AND reminded_at IS NULL "
                      "AND done_at IS NULL AND removed_at IS NULL ORDER BY due_at", (now_iso(now),))

    # what the person said about themselves, kept for the profile (DESIGN.md sections 5 and 11)
    def add_profile_note(self, handle, text, at=None):
        self.x("INSERT INTO profile_notes(handle,text,at) VALUES(?,?,?)", (handle, text[:300], now_iso(at)))

    def profile_notes(self, handle, limit=10):
        rows = self.q("SELECT text FROM profile_notes WHERE handle=? ORDER BY id DESC LIMIT ?", (handle, limit))
        return [r["text"] for r in reversed(rows)]

    def log_request(self, handle, text, intent):
        self.x("INSERT INTO requests(handle,text,intent,at) VALUES(?,?,?,?)", (handle, text[:500], intent, now_iso()))

    # the inbound journal: one row per message received, with no text once it has been handled
    def inbound_add(self, channel, msg, at=None):
        """Returns the row id, or None when this channel reference was already received (a webhook retry, a restart)."""
        try:
            cur = self.x("INSERT INTO inbound(channel,ref,handle,text,tapback,tapback_ref,received_at,status) "
                         "VALUES(?,?,?,?,?,?,?,'received')",
                         (channel, msg.ref, msg.handle, msg.text or None, msg.tapback, msg.tapback_ref, now_iso(at)))
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def inbound_done(self, inbound_id, status, intent=None, run_id=None, reply_ref=None, error=None, seconds=None):
        self.x("UPDATE inbound SET status=?, intent=?, run_id=?, reply_ref=?, error=?, seconds=?, text=NULL WHERE id=?",
               (status, intent, run_id, str(reply_ref) if reply_ref else None, error, seconds, inbound_id))

    def inbound_unfinished(self):
        return self.q("SELECT * FROM inbound WHERE status='received' ORDER BY id")

    def get_state(self, key, default=None):
        r = self.one("SELECT value FROM state WHERE key=?", (key,))
        return json.loads(r["value"]) if r else default

    def set_state(self, key, value):
        self.x("INSERT OR REPLACE INTO state(key,value) VALUES(?,?)", (key, json.dumps(value)))

    def delete_person_data(self, handle):
        """'delete my data': everything the MVP holds about the person except a deletion marker."""
        with self.lock:
            for t in ("rules", "runs", "deliveries", "feedback", "pending", "last_answer", "sent", "requests", "inbound",
                      "todos", "profile_notes", "interp_cache"):
                self.db.execute(f"DELETE FROM {t} WHERE handle=?", (handle,))
            self.db.execute("DELETE FROM people WHERE handle=?", (handle,))
            for key in (f"lines:{handle}", f"lastspec:{handle}", f"last_in:{handle}", f"cap_notice:{handle}", f"unknown:{handle}",
                        f"lastwrite:{handle}"):
                self.db.execute("DELETE FROM state WHERE key=?", (key,))
            self.db.commit()

