"""PROTOTYPE ONLY - builds and checks evalset/brain_fresh.jsonl, the fresh eval set of the chat core (scratchpad brief
of mvp22, "The fresh eval set"). Offline: no model call, no network, no money.

    python3 -m mvp.eval.build_brain_fresh [--write] [--report OUT.json]      (from experiments/)

What it does, per plan-tier message of brain_fresh_a.py and brain_fresh_b.py:
1. every reading is replayed through brain.tools.call on the made-up library of tests/brain_library.py (built in a
   temporary folder with eval_brain.Harness.scratch, as the other offline evals build it), one fresh Turn per reading
   with the message's own text (so the unlock, the notes and the digit rule are the message's). A follow-up runs with
   the window and window words of the preferred reading of the message before it, as a screen would hold them. A
   reading with an error result fails the build. The window kept is each result's sheet window (start, end).
2. the window I read from their words (R(win=...)) is set against the tool's: a difference is a finding.
3. every fact is recounted by Recount below, which reads only tests/brain_library.py rows() (no facts, history,
   insight or eval_claims code). Where a fact names a tool path, the tool's figure is read too; a difference is kept
   as a finding (my count stays in the file).
4. every call the message's tools must refuse (X) is run and must come back as an error.
5. the set's checks: counts, halves (half A when int(sha1(id), 16) % 2 == 0), no message equal to or close to one of
   evalset/brain_plans.jsonl (normalised text, and difflib's ratio below CLOSE), tags known.

The report names half B messages by id only (half B is locked: evalset/README_brain_fresh.md).
"""
import argparse
import difflib
import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import date, datetime
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
MVP = os.path.dirname(HERE)
OUT = os.path.join(MVP, "evalset", "brain_fresh.jsonl")
PLANS = os.path.join(MVP, "evalset", "brain_plans.jsonl")
NY = ZoneInfo("America/New_York")
CLOSE = 0.8          # a message this close (difflib ratio of normalised text) to an old one is refused
MIN_CONVS, MIN_PLAN, MIN_FOLLOW = 70, 100, 30
TAGS = {"follow_up", "correction", "scoped", "private", "locked", "unlocked", "friends", "saved", "liked", "instagram",
        "shorts", "compare", "first_last", "timeline", "items", "wide", "no_answer_in_data", "part_of_period",
        "sloppy", "lately", "changes", "channels", "themes", "time_of_day", "weekday", "search", "after_end",
        "planted", "exact", "tool_gap"}


def half_of(cid):
    return "A" if int(hashlib.sha1(cid.encode()).hexdigest(), 16) % 2 == 0 else "B"


# ================================================================ my own recount of the made-up rows
THEME_NAME = {"mc": "Minecraft builds", "sr": "Speedruns", "cl": "Gaming clips", "wc": "Watercolor painting",
              "dd": "Digital drawing", "ca": "Calculus lessons", "np": "Number puzzles", "co": "Home cooking",
              "da": "Dating advice"}
AREA = {"mc": "gaming", "sr": "gaming", "cl": "gaming", "wc": "art and design", "dd": "art and design",
        "ca": "math", "np": "math", "co": "food and cooking", "da": "relationships"}
PRIVATE = {"da"}
OPENED, SAVED = ("watch", "view"), ("save", "playlist", "collection", "share_self")
KINDS = {"opened": OPENED, "saved": SAVED, "liked": ("like",), "any": OPENED + SAVED + ("like",)}
ENDS = {"youtube": date(2026, 10, 30), "instagram": date(2026, 10, 15)}
NEWEST = max(ENDS.values())


def d(s):
    return date.fromisoformat(s)


class Recount:
    """The rows of tests/brain_library.py read by plain rules, said here once:
    - a row's day and hour are its event's instant in New York;
    - opened = watch or view events; saved = save, playlist, collection or share_self; there are no like events;
    - a friend's row (friend: True) is never counted, only counted apart (friends());
    - private = the "da" rows (Heart Notes, dating advice): left out unless private=True;
    - length: a YouTube row is a Short when its known length is 60 s or less, long when over 60 s, unknown when it has
      no length; an Instagram reel (media missing or "reel") is short; an Instagram post is neither;
    - an item counts once in a window when at least one of its events of the kind asked falls in the window.
    """

    def __init__(self, rows):
        self.rows = []
        for r in rows:
            evs = []
            for k, at in r["events"]:
                t = datetime.fromisoformat(at).astimezone(NY)
                evs.append((t, k))
            if r["platform"] == "youtube":
                ln = r.get("length")
                length = "unknown" if ln is None else "short" if ln <= 60 else "long"
                channel = r["channel"]
            else:
                length = "short" if (r.get("media") or "reel") == "reel" else "unknown"
                channel = "@" + r["handle"]
            self.rows.append({"id": r["id"], "platform": r["platform"], "channel": channel, "key": r["theme"],
                              "theme": THEME_NAME[r["theme"]], "area": AREA[r["theme"]], "title": r["caption"],
                              "length": length, "length_s": r.get("length"), "friend": bool(r.get("friend")), "private": r["theme"] in PRIVATE,
                              "events": evs})

    # ---- selection
    def _ok(self, r, f):
        if r["friend"]:
            return False
        if r["private"] and not f.get("private"):
            return False
        for k in ("area", "theme", "channel", "platform", "key"):
            v = f.get(k)
            if v is not None and (r[k] not in v if isinstance(v, (set, list, tuple)) else r[k] != v):
                return False
        for k, field in (("not_area", "area"), ("not_theme", "theme"), ("not_channel", "channel")):
            v = f.get(k)
            if v is not None and r[field] in (v if isinstance(v, (set, list, tuple)) else {v}):
                return False
        if f.get("length") and r["length"] != f["length"]:
            return False
        if f.get("words") and not _holds(r["title"], f["words"]):
            return False
        if f.get("not_words") and _holds(r["title"], f["not_words"]):
            return False
        return True

    def sel(self, win=None, how="opened", **f):
        """[(row, its first event of the kind in the window)] of the items counted."""
        kinds = KINDS[how]
        out = []
        for r in self.rows:
            if not self._ok(r, f):
                continue
            evs = [(t, k) for t, k in r["events"] if k in kinds and _in(t.date(), win)
                   and (f.get("weekday") is None or t.weekday() == f["weekday"])
                   and (f.get("hours") is None or t.hour in f["hours"])]
            if evs:
                out.append((r, min(evs)[0]))
        return out

    def n(self, win=None, **f):
        return len(self.sel(win, **f))

    def share(self, part, win=None, **base):
        """part: extra filters over base; a fraction to 4 places."""
        b = self.n(win, **base)
        p = self.n(win, **dict(base, **part))
        return round(p / b, 4) if b else 0.0

    def by(self, key, win=None, **f):
        """[[label, count], ...] most first, ties by label."""
        c = Counter()
        for r, t in self.sel(win, **f):
            c[_key(key, r, t)] += 1
        return [[k, v] for k, v in sorted(c.items(), key=lambda kv: (-kv[1], str(kv[0])))]

    def top(self, key, win=None, **f):
        rows = self.by(key, win, **f)
        return rows[0][0] if rows else None

    def top_n(self, key, win=None, **f):
        rows = self.by(key, win, **f)
        return rows[0][1] if rows else 0

    def least(self, key, win=None, **f):
        rows = self.by(key, win, **f)
        return min(rows, key=lambda kv: (kv[1], str(kv[0])))[0] if rows else None

    def edge(self, which, win=None, **f):
        """The first or last event of the scope: {day, time, title, channel}."""
        kinds = KINDS[f.get("how", "opened")]
        evs = sorted((t, r["id"], r) for r, _t in self.sel(win, **f) for t, k in r["events"]
                     if k in kinds and _in(t.date(), win))
        if not evs:
            return None
        t, _i, r = evs[0] if which == "first" else evs[-1]
        return {"day": t.date().isoformat(), "time": t.strftime("%H:%M"), "title": r["title"], "channel": r["channel"]}

    def titles(self, win=None, order="newest", k=5, **f):
        got = sorted(self.sel(win, **f), key=lambda x: (x[1], x[0]["id"]), reverse=(order == "newest"))
        return [r["title"] for r, _t in got[:k]]

    def median_long_min(self):
        """The middle length, in whole minutes, of the long YouTube rows (private left out)."""
        ls = sorted(r["length_s"] for r, _t in self.sel(None, length="long"))
        return ls[len(ls) // 2] // 60 if ls else None

    def last_day(self, platform=None):
        return max(t.date() for r in self.rows if platform in (None, r["platform"])
                   for t, _k in r["events"]).isoformat()

    def kinds(self):
        return sorted({k for r in self.rows for _t, k in r["events"]})

    def events_of(self, kind):
        return sum(1 for r in self.rows for _t, k in r["events"] if k == kind)

    def max_opens(self, win=None):
        return max((sum(1 for t, k in r["events"] if k in OPENED and _in(t.date(), win)) for r, _t in self.sel(win)),
                   default=0)

    def hidden(self, win=None, how="opened"):
        """Private items left out of a window."""
        return self.n(win, how=how, private=True) - self.n(win, how=how)

    def friends(self, win=None, how="saved"):
        """Friends' items of the kind in the window (counted only, never shown)."""
        kinds = KINDS[how]
        return sum(1 for r in self.rows if r["friend"] and any(k in kinds and _in(t.date(), win)
                                                                for t, k in r["events"]))


def _holds(text, words):
    low = set(re.findall(r"[a-z0-9]+", (text or "").lower()))
    return all(w in low or w.rstrip("s") in low or (w + "s") in low for w in words.lower().split())


def _in(day, win):
    return win is None or (d(win[0]) <= day <= d(win[1]))


def _key(key, r, t):
    if key in ("area", "theme", "channel", "platform", "length"):
        return r[key]
    if key == "year":
        return t.year
    if key == "month":
        return t.strftime("%Y-%m")
    if key == "weekday":
        return t.strftime("%A")
    if key == "hour":
        return t.hour
    if key == "daypart":
        h = t.hour
        return "morning (5 to 11)" if 5 <= h < 12 else "afternoon (12 to 16)" if 12 <= h < 17 else \
            "evening (17 to 21)" if 17 <= h < 22 else "night (22 to 4)"
    raise KeyError(key)


# ================================================================ the tool side
def get_path(results, path):
    """A path into a reading's results: r1.totals.items, r1.channels[0].name, r1.themes[name=Home cooking].items,
    r1.meta.hidden.sensitive, r1.error. Missing -> the string "(missing)"."""
    segs = re.findall(r"[^.\[\]]+|\[[^\]]*\]", path)
    env = results.get(segs[0])
    if env is None:
        return "(missing)"
    cur = env if segs[1:2] in (["meta"], ["error"], ["options"]) else env.get("sheet")
    for s in segs[1:]:
        if s.startswith("["):
            inner = s[1:-1]
            if not isinstance(cur, list):
                return "(missing)"
            if "=" in inner:
                k, v = inner.split("=", 1)
                cur = next((x for x in cur if isinstance(x, dict) and str(x.get(k)) == v), None)
            else:
                i = int(inner)
                cur = cur[i] if -len(cur) <= i < len(cur) else None
        else:
            cur = cur.get(s) if isinstance(cur, dict) else None
        if cur is None:
            return "(missing)"
    return cur


def yes_no(v):
    """A fact's value is a number or a string: a yes/no question is said "yes" or "no"."""
    return ("yes" if v else "no") if isinstance(v, bool) else v


def same(a, b):
    if isinstance(a, float) or isinstance(b, float):
        try:
            return abs(float(a) - float(b)) < 0.0015
        except (TypeError, ValueError):
            return False
    if isinstance(a, str) and isinstance(b, str) and re.fullmatch(r"\d{4}-\d\d-\d\d", a) and b.startswith(a + " "):
        return True     # a day against a "when" that also gives the time of day
    return a == b or (isinstance(a, str) and isinstance(b, str) and a.lower() == b.lower())


def sheet_window(env, turn=None):
    """A result's window: its sheet's (start, end); a search result has no sheet window, so its window is the one
    the tools resolved for it (history.resolve over the record's ends, as run_search does)."""
    w = ((env or {}).get("sheet") or {}).get("window")
    if isinstance(w, dict) and w.get("start"):
        return [w["start"], w["end"]]
    if turn is not None and env and env.get("tool") == "search" and env.get("rid") in turn.windows:
        from mvp import history as Hm
        rec = turn.lib.rec
        s, e = Hm.resolve(turn.windows[env["rid"]], rec, sorted(rec.ends), turn.today)
        if s is not None:
            return [s.isoformat(), e.isoformat()]
    return None


def run_reading(h, text, rounds, screen, last):
    from mvp.brain import tools as TL
    from mvp.tests.fakes.fake_brain import FakeEngine, fake_learned
    t = h.turn(text, screen=screen, last_window=last, search=FakeEngine(), learned=fake_learned)
    results, errors = {}, []
    for rnd in rounds:
        for c in rnd:
            r = TL.call(t, c["tool"], c["args"])
            if r.get("is_error"):
                errors.append(f"{c['tool']}: {r.get('error')}")
            elif r.get("error"):
                errors.append(f"{c['tool']}: {r.get('error')} ({r.get('name')})")
                results[r["rid"]] = r
            else:
                results[r["rid"]] = r
    return t, results, errors


def replay(h, conv):
    """Every reading and every refused call of one conversation of the written file, run as the build ran them (the
    screen and the last window carried from the preferred reading of the message before) -> a list of problems."""
    out, screen, last = [], "", None
    for m in conv["messages"]:
        if m["tier"] != "plan":
            continue
        pref = None
        for k, rd in enumerate(m["readings"]):
            t, results, errors = run_reading(h, m["text"], rd["rounds"], screen, last)
            out += [f"{conv['id']}.{m['n']} reading {k}: {e}" for e in errors]
            if k == 0:
                pref = (t, results)
        for x in m.get("refuses") or []:
            _t, _r, err = run_reading(h, m["text"], [[{"tool": x["tool"], "args": x["args"]}]], screen, last)
            if not err:
                out.append(f"{conv['id']}.{m['n']}: {x['tool']} was not refused")
        if pref:
            t, results = pref
            last = t.windows.get("r1") or last
            screen = ((results.get("r1") or {}).get("meta") or {}).get("window_said") or screen
    return out


def valid_args(c):
    """The tool's own params model accepts the arguments (no run)."""
    from mvp.brain import tools as TL
    TL.REGISTRY[c["tool"]].params(**c["args"])
    return True


# ================================================================ build
def load_specs():
    from mvp.eval import brain_fresh_a as A
    from mvp.eval import brain_fresh_b as B
    return [(c, "A") for c in A.CONVS] + [(c, "B") for c in B.CONVS]


def old_texts():
    out = []
    with open(PLANS, encoding="utf-8") as f:
        for line in f:
            o = json.loads(line)
            if o.get("before"):
                out.append(o["before"]["message"])
            out += [m["text"] for m in o["messages"]]
    return sorted(set(out))


def norm(s):
    return " ".join(re.findall(r"[a-z0-9]+", s.lower()))


def build(h=None, log=print):
    from mvp import eval_brain as E
    from mvp.tests import brain_library as BL
    rec = Recount(BL.rows())
    h = h or E.Harness.scratch()
    problems, findings, convs = [], [], []
    for spec, half in load_specs():
        cid = spec["id"]
        if half_of(cid) != half:
            problems.append(f"{cid}: in the half-{half} file but its sha1 puts it in half {half_of(cid)}")
        def label(n, s="", cid=cid, half=half):
            return f"{cid}.{n}" + (f" {s}" if half == "A" and s else "")
        msgs, screen, last = [], "", None
        for n, m in enumerate(spec["msgs"]):
            bad_tags = set(m["tags"]) - TAGS
            if bad_tags:
                problems.append(f"{cid}.{n}: unknown tags {sorted(bad_tags)}")
            if m["tier"] != "plan":
                msgs.append({"n": n, "text": m["text"], "tier": m["tier"], "tags": m["tags"], "why": m["why"]})
                continue
            if not 1 <= len(m["readings"]) <= 3:
                problems.append(f"{cid}.{n}: {len(m['readings'])} readings (1 to 3)")
            out_r, pref, others = [], None, []
            for k, rd in enumerate(m["readings"]):
                for rnd in rd["rounds"]:
                    for c in rnd:
                        try:
                            valid_args(c)
                        except Exception as e:  # noqa: BLE001
                            problems.append(f"{cid}.{n} reading {k}: {c['tool']} args refused: {str(e)[:200]}")
                t, results, errors = run_reading(h, m["text"], rd["rounds"], screen, last)
                for e in errors:
                    problems.append(f"{cid}.{n} reading {k}: {e}")
                wins = {rid: sheet_window(env, t) for rid, env in results.items() if sheet_window(env, t)}
                if rd["win"] is not None or "r1" in wins:
                    got = wins.get("r1")
                    if got != rd["win"]:
                        findings.append({"kind": "window", "where": label(n, m["text"]), "reading": k,
                                         "mine": rd["win"], "tool": got,
                                         "said": ((results.get("r1") or {}).get("meta") or {}).get("window_said")})
                out_r.append({"rounds": rd["rounds"], "window": wins, "note": rd["note"]})
                if k == 0:
                    pref = (t, results)
                else:
                    if rd.get("check"):
                        others.append((k, results, wins.get("r1")))
            facts = []
            pref_win = sheet_window((pref[1] if pref else {}).get("r1"), pref[0] if pref else None)
            for fct in m["facts"]:
                v = yes_no(fct["fn"](rec))
                facts.append({"say": fct["say"], "value": v, "how": fct["how"]})
                if not (fct["tool"] and pref):
                    continue
                # the preferred reading always; another reading only over the same window and when the path is
                # there (its figures rest on the same rows)
                checks = [(0, pref[1])] + [(k, res) for k, res, w in others if w == pref_win
                                           and get_path(res, fct["tool"]) != "(missing)"]
                for k, res in checks:
                    tv = yes_no(get_path(res, fct["tool"]))
                    if not same(v, tv):
                        kind = "count"
                        if isinstance(v, str) and isinstance(tv, str) and re.sub(r"\s*#\d+$", "", v) == tv:
                            kind = "title tail"     # the tool's title drops a trailing " #N" (its title cleaning)
                        findings.append({"kind": kind, "where": label(n, m["text"]), "reading": k,
                                         "say": fct["say"], "mine": v, "tool": tv, "path": fct["tool"],
                                         "call": res.get(fct["tool"].split(".")[0], {}).get("tool")})
            refuses = []
            for x in m["refuses"]:
                _t2, _res2, err2 = run_reading(h, m["text"], [[x]], screen, last)
                if not err2:
                    problems.append(f"{cid}.{n}: a call that must be refused was not: {x['tool']}")
                refuses.append({"tool": x["tool"], "args": x["args"], "error": err2[0] if err2 else None})
            msg = {"n": n, "text": m["text"], "tier": "plan", "tags": m["tags"], "readings": out_r, "facts": facts,
                   "good": {"means": m["means"], "offer": m["offer"]}}
            if refuses:
                msg["refuses"] = refuses
            if not m["means"] or not m["offer"] or not facts:
                problems.append(f"{cid}.{n}: needs facts, means and offer")
            msgs.append(msg)
            if pref:
                t, results = pref
                w = t.windows.get("r1")
                if w is not None:
                    last = w
                said = ((results.get("r1") or {}).get("meta") or {}).get("window_said")
                if said:
                    screen = said
        convs.append({"id": cid, "half": half, "messages": msgs})
    return convs, problems, findings


def check_set(convs):
    """Counts, tags, halves and the nearness to the old set."""
    problems = []
    plan = [m for c in convs for m in c["messages"] if m["tier"] == "plan"]
    follow = [m for m in plan if {"follow_up", "correction"} & set(m["tags"])]
    if len(convs) < MIN_CONVS:
        problems.append(f"{len(convs)} conversations (at least {MIN_CONVS})")
    if len(plan) < MIN_PLAN:
        problems.append(f"{len(plan)} plan messages (at least {MIN_PLAN})")
    if len(follow) < MIN_FOLLOW:
        problems.append(f"{len(follow)} follow-ups or corrections (at least {MIN_FOLLOW})")
    ids = [c["id"] for c in convs]
    if len(set(ids)) != len(ids) or not all(re.fullmatch(r"N\d{3}", i) for i in ids):
        problems.append("ids repeat or are not N + 3 digits")
    olds = old_texts()
    near = []
    seen = {}
    for c in convs:
        for m in c["messages"]:
            nm = norm(m["text"])
            if nm in seen:
                problems.append(f"{c['id']}.{m['n']}: repeats {seen[nm]} inside the set")
            seen[nm] = f"{c['id']}.{m['n']}"
            for o in olds:
                r = difflib.SequenceMatcher(None, nm, norm(o)).ratio()
                near.append((round(r, 3), c["id"], m["n"], c["half"], m["text"], o))
                if nm == norm(o):
                    problems.append(f"{c['id']}.{m['n']}: equal to an old message")
                elif r >= CLOSE:
                    problems.append(f"{c['id']}.{m['n']}: {r:.2f} close to an old message")
    near.sort(key=lambda x: -x[0])
    return problems, near


def counts(convs):
    by_tag, by_half = Counter(), Counter()
    for c in convs:
        by_half[c["half"] + " conversations"] += 1
        for m in c["messages"]:
            by_half[c["half"] + " " + m["tier"]] += 1
            if m["tier"] == "plan":
                for t in m["tags"]:
                    by_tag[t] += 1
                    by_half[c["half"] + " " + t] += 1
                if {"follow_up", "correction"} & set(m["tags"]):
                    by_half[c["half"] + " follow_up or correction"] += 1
    return dict(sorted(by_tag.items())), dict(sorted(by_half.items()))


def lines(convs):
    return [json.dumps(c, ensure_ascii=False, sort_keys=False) for c in convs]


def half_b_sha(text_lines):
    """sha256 of half B's lines, in file order, each with its newline (the raw bytes of those lines)."""
    hb = [ln for ln in text_lines if half_of(json.loads(ln)["id"]) == "B"]
    return hashlib.sha256("".join(ln + "\n" for ln in hb).encode("utf-8")).hexdigest()


def stored_lines():
    """{id: line} of the written file, or {} when there is none."""
    if not os.path.exists(OUT):
        return {}
    with open(OUT, encoding="utf-8") as f:
        return {json.loads(x)["id"]: x.rstrip("\n") for x in f if x.strip()}


def keep_half_b(ls, stored):
    """Half B is locked: once the file exists its half B lines are kept byte for byte, whatever the tools now give.
    -> (the lines to write, the ids of half B whose rebuilt line differs from the stored one)."""
    out, differ = [], []
    for ln in ls:
        cid = json.loads(ln)["id"]
        if half_of(cid) == "B" and cid in stored:
            if stored[cid] != ln:
                differ.append(cid)
            out.append(stored[cid])
        else:
            out.append(ln)
    missing = sorted({i for i in stored if half_of(i) == "B"} - {json.loads(x)["id"] for x in ls})
    return out, differ + [f"{i} (gone from the source)" for i in missing]


def redact(row):
    """A finding of half B as the report keeps it: id, kind, reading, call and path only (half B is locked)."""
    cid = row["where"].split(".")[0]
    if half_of(cid) == "A":
        return row
    return {k: row.get(k) for k in ("kind", "where", "reading", "call", "path") if k in row}


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--write", action="store_true", help="write evalset/brain_fresh.jsonl (half B kept as stored)")
    p.add_argument("--rewrite-half-b", action="store_true",
                   help="rebuild half B too: only for the first write of a new set, never after the lock")
    p.add_argument("--report", help="write the report (counts, findings, problems, nearest pairs) as JSON here")
    a = p.parse_args(argv)
    convs, problems, findings = build()
    p2, near = check_set(convs)
    problems += p2
    by_tag, by_half = counts(convs)
    ls = lines(convs)
    stored = {} if a.rewrite_half_b else stored_lines()
    ls, b_differs = keep_half_b(ls, stored)
    findings = [redact(x) for x in findings]
    hide = lambda x: x if x[3] == "A" else (x[0], x[1], x[2], "B", "(half B)", x[5])
    rep = {"problems": problems, "findings": findings, "by_tag": by_tag, "by_half": by_half,
           "half_b_rebuilt_differs": b_differs,
           "nearest": [hide(x) for x in near[:10]], "half_b_sha256": half_b_sha(ls),
           "conversations": len(convs),
           "plan_messages": sum(1 for c in convs for m in c["messages"] if m["tier"] == "plan")}
    print(json.dumps({k: rep[k] for k in ("conversations", "plan_messages", "half_b_sha256")}))
    print(f"problems: {len(problems)}")
    for x in problems:
        print("  ", x)
    print(f"findings: {len(findings)}")
    for x in findings:
        print("  ", json.dumps(x, default=str)[:400])
    print("nearest:", json.dumps(rep["nearest"][:3]))
    if b_differs:
        print(f"half B kept as stored; rebuilt differs for: {', '.join(b_differs)}")
    if a.report:
        with open(a.report, "w", encoding="utf-8") as f:
            json.dump(rep, f, indent=1, default=str)
    if a.write:
        if problems:
            print("not written: fix the problems first")
            return 1
        with open(OUT, "w", encoding="utf-8") as f:
            f.write("".join(ln + "\n" for ln in ls))
        print(f"wrote {OUT}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(MVP))
    sys.exit(main())
