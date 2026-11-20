"""PROTOTYPE ONLY - round 3 A3: intent step. Prompt qi-v1 = qr-v1 (unchanged text plan: kind, phrases, keywords,
hypothetical captions) + an `intent` block of structured filters/boosts inferred from the user's words, applied to
the user's OWN interaction data (watch/like/playlist dates, watch counts, Watch later) and duration metadata.

  intent = {watched_after, watched_before: "YYYY-MM-DD"|null   window on the user's interaction dates
            require: subset of [liked, saved, watched]         item must have one of these
            exclude: subset of [liked, saved, watched]         item must have none ("never watched" -> watched)
            min_watch_count, max_watch_count: int|null         "rewatched a lot" -> min 2+; "watched briefly" -> max 1
            min_duration_s, max_duration_s: int|null
            shorts: "only" | "exclude" | null
            sort: relevance | most_watched | longest | shortest | newest | oldest
            topic_free: bool    the search names no topic; rank by the behaviour signal alone
            era_of_topic: bool  "that time when I was into X": a period of the user's life defined by the topic}

`python yt_intent.py --repeat N` -> $DIGESTER_DATA/runs/rewrites/qi-v1_gpt-5-nano_rN.json (same shape as qr-v1 +
"intent"). `apply()` is used by yt_search.py. The few-shot pairs are synthetic (not eval searches).
Prints aggregate stats only.
"""
import argparse
import copy
import datetime
import json
import os
import sys
import time
import urllib.error

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "lib"))
sys.path.insert(0, HERE)
import ai
import llm_rewrite as QR
from corpus import DATA, load_queries, rrf

PROMPT_VERSION = "qi-v1"  # qi-v2: same structure, tighter field rules (see INTENT_RULES_V2)
MODEL = "gpt-5-nano"
FLAGS = ["liked", "saved", "watched"]
SORTS = ["relevance", "most_watched", "longest", "shortest", "newest", "oldest"]

INTENT_RULES = """
- intent: what the person MEANS about their own history, beyond the topic words. Their library is their YouTube
  history: every video they watched (with dates, since about 2015), liked, or saved to a playlist (including
  Watch later), with each video's duration. Fill only what the words imply; otherwise null / [] / "relevance" /
  false.
  watched_after / watched_before: "YYYY-MM-DD" window on WHEN they watched, liked or saved it ("summer 2019",
    "last month"), worked out from today's date. Not for when a video was published.
  require: any of liked, saved, watched that the item must have ("I liked", "I saved / put in a playlist").
  exclude: any of liked, saved, watched the item must NOT have ("never got to watching" -> ["watched"]).
  min_watch_count / max_watch_count: watch-count bounds ("rewatched a lot" -> min 3; "only watched once" -> max 1).
  min_duration_s / max_duration_s: from words like long, short, quick, under 10 minutes (long -> min 1200).
  shorts: "only" for YouTube Shorts or very short clips, "exclude" if they want real videos, else null.
  sort: how to order matches if the words ask for it (most_watched, longest, shortest, newest, oldest).
  topic_free: true only if the search names no subject at all, just behaviour.
  era_of_topic: true if they mean a period of their life defined by a topic, without giving dates
    ("back when I was into chess")."""

INTENT_RULES_V2 = """
- intent: what the person MEANS about their own history, beyond the topic words. Their library is their YouTube
  history: every video they watched (with dates, since about 2015), liked, or saved to a playlist (including
  Watch later), with each video's duration. Most searches need NO intent: leave it empty (null / [] /
  "relevance" / false) unless the words clearly ask for it.
  watched_after / watched_before: "YYYY-MM-DD", only when the words name a time ("summer 2019", "last month",
    "in 2022"), worked out from today's date. Never guess dates for vague life periods (childhood, school days,
    "back then"). Not for when a video was published.
  require: only "liked" or "saved", and only when the words say so ("videos I liked", "my saved / playlist /
    watch later videos"). "I really liked that song" counts as liked. Never require both unless both are said.
  exclude: interactions the person says did NOT happen ("never got to watching" -> ["watched"], "that I didn't
    like" -> ["liked"]). Never use exclude for topics, channels or kinds of content to avoid.
  min_watch_count / max_watch_count: only for words about how often they watched ("rewatched a lot" -> min 3;
    "only watched once / briefly" -> max 1).
  min_duration_s / max_duration_s: only for words about length (long -> min 1200; short or quick -> max 300).
  shorts: "only" for YouTube Shorts, "exclude" if they say not Shorts, else null.
  sort: only if the words ask for an order (most_watched for "rewatched the most", longest, shortest, newest,
    oldest); else "relevance".
  topic_free: true only when the search is entirely about behaviour (how often, when, how long, saved or not)
    with no subject, mood or purpose. Mood or purpose words (cozy, to study, to fall asleep to) are NOT
    topic-free.
  era_of_topic: true only for "that time / phase when I was into X" without dates."""

SYSTEM = QR.SYSTEM.replace(
    "- filters: only what the query states explicitly. Otherwise use null / [].\n"
    "  before/after: \"YYYY-MM-DD\" dates, worked out from the date given and the query wording.\n"
    "  interactions: a subset of [\"save\", \"like\", \"collection\", \"share_self\", \"share_friend\"],\n"
    "  e.g. \"I sent to friends\" -> [\"share_friend\"].", INTENT_RULES.strip("\n"))
assert SYSTEM != QR.SYSTEM, "qr-v1 filters block not found"
SYSTEM_V2 = SYSTEM.replace(INTENT_RULES.strip("\n"), INTENT_RULES_V2.strip("\n"))
assert SYSTEM_V2 != SYSTEM

INTENT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["watched_after", "watched_before", "require", "exclude", "min_watch_count", "max_watch_count",
                 "min_duration_s", "max_duration_s", "shorts", "sort", "topic_free", "era_of_topic"],
    "properties": {
        "watched_after": {"type": ["string", "null"]}, "watched_before": {"type": ["string", "null"]},
        "require": {"type": "array", "items": {"type": "string", "enum": FLAGS}},
        "exclude": {"type": "array", "items": {"type": "string", "enum": FLAGS}},
        "min_watch_count": {"type": ["integer", "null"]}, "max_watch_count": {"type": ["integer", "null"]},
        "min_duration_s": {"type": ["integer", "null"]}, "max_duration_s": {"type": ["integer", "null"]},
        "shorts": {"type": ["string", "null"], "enum": ["only", "exclude", None]},
        "sort": {"type": "string", "enum": SORTS},
        "topic_free": {"type": "boolean"}, "era_of_topic": {"type": "boolean"}}}
SCHEMA = copy.deepcopy(QR.SCHEMA)
SCHEMA["required"] = [k for k in SCHEMA["required"] if k != "filters"] + ["intent"]
SCHEMA["properties"].pop("filters")
SCHEMA["properties"]["intent"] = INTENT_SCHEMA
RESPONSE_FORMAT = {"type": "json_schema", "json_schema": {"name": "query_plan", "strict": True, "schema": SCHEMA}}

NONE = {"watched_after": None, "watched_before": None, "require": [], "exclude": [], "min_watch_count": None,
        "max_watch_count": None, "min_duration_s": None, "max_duration_s": None, "shorts": None, "sort": "relevance",
        "topic_free": False, "era_of_topic": False}


def _shot(ans, intent):
    a = {k: v for k, v in ans.items() if k != "filters"}
    a["intent"] = {**NONE, **intent}
    return a


# qr-v1's two synthetic pairs (intent added) + one synthetic YouTube behaviour pair.
FEWSHOT = [
    (QR.FEWSHOT[0][0], _shot(QR.FEWSHOT[0][1], {})),
    (QR.FEWSHOT[1][0], _shot(QR.FEWSHOT[1][1], {"watched_after": "2026-03-20", "watched_before": "2026-06-21"})),
    ("quick woodworking clips I liked in early 2024",
     {"kind": ["topic", "time"],
      "phrases": ["short woodworking project clips", "quick wood joinery and carving demos",
                  "fast woodshop builds and hacks"],
      "keywords": ["woodworking", "joinery", "woodshop", "carving", "dovetail", "diy"],
      "hypothetical_captions": ["60 second dovetail joint 🪚 #woodworking #joinery #shorts",
                                "turning scrap wood into a coaster in one minute #woodshop #diy",
                                "spoon carving speedrun 🥄 #carving #woodworking"],
      "intent": {**NONE, "watched_after": "2024-01-01", "watched_before": "2024-05-01", "require": ["liked"],
                 "max_duration_s": 300}}),
]


def messages_for(query, system=None):
    msgs = [{"role": "system", "content": system or SYSTEM}]
    for q, ans in FEWSHOT:
        msgs.append({"role": "user", "content": QR.user_msg(q)})
        msgs.append({"role": "assistant", "content": json.dumps(ans, ensure_ascii=False)})
    msgs.append({"role": "user", "content": QR.user_msg(query)})
    return msgs


def valid_intent(i):
    i = {**NONE, **(i or {})}
    out = dict(NONE)
    for k in ("watched_after", "watched_before"):
        out[k] = QR.valid_date(i.get(k))
    for k in ("require", "exclude"):
        out[k] = sorted({x for x in i.get(k) or [] if x in FLAGS})
    for k in ("min_watch_count", "max_watch_count", "min_duration_s", "max_duration_s"):
        v = i.get(k)
        out[k] = int(v) if isinstance(v, (int, float)) and v >= 0 else None
    out["require"] = [x for x in out["require"] if x not in out["exclude"]]  # contradiction: exclude wins
    out["shorts"] = i.get("shorts") if i.get("shorts") in ("only", "exclude") else None
    out["sort"] = i.get("sort") if i.get("sort") in SORTS else "relevance"
    out["topic_free"] = bool(i.get("topic_free"))
    out["era_of_topic"] = bool(i.get("era_of_topic"))
    return out


def run_rewrite(repeat, version="qi-v1"):
    system = SYSTEM if version == "qi-v1" else SYSTEM_V2
    queries = [q for q in load_queries() if not q["examples"]]
    parses, per_q = {}, {}
    t0 = time.time()
    for q in queries:
        for att in range(4):
            t = time.time()
            try:
                raw, u = ai.openai_chat_json(MODEL, system, QR.user_msg(q["query"]), max_tokens=1400,
                                             purpose="query_rewrite_intent", prompt_version=version,
                                             reasoning_effort="minimal", response_format=RESPONSE_FORMAT,
                                             messages=messages_for(q["query"], system))
                break
            except urllib.error.HTTPError as e:
                if e.code < 500 and e.code != 429 or att == 3:
                    raise
                time.sleep(2 ** att)
        sec = time.time() - t
        p = QR.post_validate({**raw, "filters": {}})
        p.pop("filters")
        p["intent"] = valid_intent(raw.get("intent"))
        parses[q["id"]] = p
        per_q[q["id"]] = {"seconds": round(sec, 3), "cost_usd": QR.price(MODEL, u), "in_tokens": u["prompt_tokens"],
                          "out_tokens": u["completion_tokens"]}
    wall = time.time() - t0
    secs = [v["seconds"] for v in per_q.values()]
    meta = {"model": MODEL, "prompt_version": version, "reasoning_effort": "minimal", "repeat": repeat,
            "n": len(parses), "cost_usd": sum(v["cost_usd"] for v in per_q.values()),
            "rewrite_p50_s": round(float(np.median(secs)), 3), "rewrite_p95_s": round(float(np.percentile(secs, 95)), 3),
            "wall_s": round(wall, 1), "per_query": per_q}
    out = {"_note": f"{version} intent rewrite r{repeat} (yt_intent.py)", "_meta": meta, **parses}
    d = os.path.join(DATA, "runs", "rewrites")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{version}_{MODEL}_r{repeat}.json")
    json.dump(out, open(path, "w"), ensure_ascii=False, indent=1)
    active = sum(1 for p in parses.values() if p["intent"] != NONE)
    print(f"wrote {path}: {len(parses)} searches, {active} with a non-empty intent, cost ${meta['cost_usd']:.5f}, "
          f"p50 {meta['rewrite_p50_s']} s, p95 {meta['rewrite_p95_s']} s")


# ---------------- applying the intent ----------------
def describe(i):
    """Short label of the active intent fields (for the report table)."""
    out = []
    if i["watched_after"] or i["watched_before"]:
        out.append(f"window {i['watched_after'] or '…'}..{i['watched_before'] or '…'}")
    if i["require"]:
        out.append("require " + "+".join(i["require"]))
    if i["exclude"]:
        out.append("exclude " + "+".join(i["exclude"]))
    if i["min_watch_count"] is not None:
        out.append(f"watches>={i['min_watch_count']}")
    if i["max_watch_count"] is not None:
        out.append(f"watches<={i['max_watch_count']}")
    if i["min_duration_s"] is not None:
        out.append(f"dur>={i['min_duration_s']}s")
    if i["max_duration_s"] is not None:
        out.append(f"dur<={i['max_duration_s']}s")
    if i["shorts"]:
        out.append(f"shorts {i['shorts']}")
    if i["sort"] != "relevance":
        out.append(f"sort {i['sort']}")
    if i["topic_free"]:
        out.append("topic-free")
    if i["era_of_topic"]:
        out.append("era-of-topic")
    return "; ".join(out) or "none"


def _window_mask(D, after, before, kinds=None):
    lo, hi = after or "0000", before or "9999"
    return np.array([any(lo <= a < hi and (kinds is None or k in kinds) for k, a, _ in xs) for xs in D.inter])


def pool_mask(D, i):
    """Hard filter over all items from the intent. Returns (mask, active)."""
    m = np.ones(len(D.items), bool)
    act = False
    flag = {"liked": D.liked, "saved": D.saved, "watched": D.watched}
    if i["watched_after"] or i["watched_before"]:
        kinds = None
        if i["require"]:
            kinds = {"liked": "like", "saved": "playlist", "watched": "watch"}
            kinds = {kinds[x] for x in i["require"]}
        m &= _window_mask(D, i["watched_after"], i["watched_before"], kinds)
        act = True
    if i["require"]:
        m &= np.any([flag[x] for x in i["require"]], axis=0)
        act = True
    for x in i["exclude"]:
        m &= ~flag[x]
        act = True
    if i["min_watch_count"] is not None:
        m &= D.watch_count >= i["min_watch_count"]
        act = True
    if i["max_watch_count"] is not None:
        m &= D.watch_count <= i["max_watch_count"]
        act = True
    if i["min_duration_s"] is not None:
        m &= D.duration >= i["min_duration_s"]
        act = True
    if i["max_duration_s"] is not None:
        m &= (D.duration >= 0) & (D.duration <= i["max_duration_s"])
        act = True
    if i["shorts"] == "only":
        m &= D.short
        act = True
    elif i["shorts"] == "exclude":
        m &= ~D.short
        act = True
    return m, act


def behaviour_order(D, m, sort):
    idx = np.flatnonzero(m)
    w = 0.8 * D.saved[idx] + 0.3 * D.liked[idx] + 0.1 * np.minimum(D.watch_count[idx], 6)
    key = {"most_watched": (-D.watch_count[idx], -w), "longest": (-D.duration[idx], -w),
           "shortest": (np.where(D.duration[idx] < 0, 1 << 30, D.duration[idx]), -w),
           "newest": (np.array([-_ts(x) for x in D.last[idx]]), -w),
           "oldest": (np.array([_ts(x) for x in D.first[idx]]), -w),
           "relevance": (-w, np.array([-_ts(x) for x in D.last[idx]]))}[sort]
    order = np.lexsort(key[::-1])
    return [D.codes[n] for n in idx[order]]


def _ts(s):
    try:
        return datetime.datetime.fromisoformat(s[:19]).timestamp()
    except (ValueError, TypeError):
        return 0.0


MIN_POOL = 5


def apply(D, fused, i, depth=1000):
    """fused: ranked codes from the text stack. Returns (ranked codes, info dict)."""
    m, act = pool_mask(D, i)
    info = {"intent": describe(i), "pool": int(m.sum()) if act else None, "mode": "unchanged"}
    pos = D.pos
    if i["era_of_topic"]:
        top = [pos[c] for c in fused[:30] if c in pos]
        dates = sorted(a[:10] for n in top for _, a, _ in D.inter[n] if a)
        if len(dates) >= 5:
            lo, hi = dates[len(dates) // 10], dates[(9 * len(dates)) // 10]
            lo = (datetime.date.fromisoformat(lo) - datetime.timedelta(days=30)).isoformat()
            hi = (datetime.date.fromisoformat(hi) + datetime.timedelta(days=30)).isoformat()
            era = _window_mask(D, lo, hi)
            fused = rrf(fused, [c for c in fused if c in pos and era[pos[c]]])
            info.update({"mode": "era boost", "era_window_days": (datetime.date.fromisoformat(hi) -
                                                                  datetime.date.fromisoformat(lo)).days})
    if not act and i["sort"] == "relevance":
        return fused[:depth], info
    if act and m.sum() < MIN_POOL:  # the filter matched (almost) nothing: keep it soft
        keep = [c for c in fused if c in pos and m[pos[c]]]
        info["mode"] = "soft (pool < 5)"
        return (keep + [c for c in fused if c not in set(keep)])[:depth], info
    B = behaviour_order(D, m, i["sort"])
    inpool = [c for c in fused if c in pos and m[pos[c]]]
    if i["topic_free"]:
        info["mode"] = f"behaviour only ({i['sort']})"
        return B[:depth], info
    if i["sort"] != "relevance":
        out = rrf(inpool, B, depth=depth)
        info["mode"] = f"filter + rrf(text, {i['sort']})"
    else:
        out = inpool + [c for c in B if c not in set(inpool)]
        info["mode"] = "filter, text order, then pool by interaction weight"
    return out[:depth], info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, required=True)
    ap.add_argument("--version", default="qi-v1", choices=["qi-v1", "qi-v2"])
    a = ap.parse_args()
    run_rewrite(a.repeat, a.version)


if __name__ == "__main__":
    main()
