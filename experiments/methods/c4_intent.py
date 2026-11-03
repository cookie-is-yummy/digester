"""PROTOTYPE ONLY - round 4.1 C3: intent step qi-v3 over both platforms, used as filters only on C0.

qi-v3 = round 3's qi-v2 (yt_intent.py) with four changes (LOG.md Y4.1-C3):
  (a) no era_of_topic and no date window for vague life periods: a window only when the words name a calendar time;
  (b) the intent rules carry no example search phrases (qi-v2's quoted examples are removed); the few-shot pairs are
      qr-v1's two synthetic pairs plus one new synthetic pair written for this prompt, not from any eval search;
  (c) `platform` (instagram | youtube | null), set only when the person names the platform; a hard filter;
  (d) behaviour flags over both platforms' own interactions: liked (like), saved (Instagram save / collection,
      YouTube playlist incl. Watch later), shared (Instagram share_self / share_friend), watched (watch);
      watch counts, duration and Shorts exist for YouTube only (duration from API metadata: filter/display only).
The text fields (kind, phrases, keywords, captions) are still requested, as in qi-v1/v2, but C3 uses only `intent`
on C0's unchanged fused list (the qr-v1 parses). apply() keeps round 3's rules: hard pool filter; soft if the pool
has < 5 items; topic_free -> behaviour order; sort != relevance -> RRF(text order in pool, behaviour order);
otherwise text order in the pool, then the rest of the pool by interaction weight.

`python c4_intent.py --repeat N` -> $DIGESTER_DATA/runs/rewrites/qi-v3_gpt-5-nano_rN.json. Prints aggregates only.
"""
import argparse
import copy
import datetime
import json
import os
import re
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

PROMPT_VERSION = "qi-v3"
MODEL = "gpt-5-nano"
FLAGS = ["liked", "saved", "shared", "watched"]
SORTS = ["relevance", "most_watched", "longest", "shortest", "newest", "oldest"]
PLATFORMS = ["instagram", "youtube"]

INTENT_RULES_V3 = """
- intent: what the person MEANS about their own history, beyond the topic words. The library has two sources:
  Instagram posts and reels they saved, put in a collection, liked or shared (with dates), and YouTube videos
  they watched (since about 2015, with dates and watch counts), liked, or saved to a playlist (including Watch
  later), with each video's duration. Most searches need NO intent: leave every field empty (null / [] /
  "relevance" / false) unless the words clearly ask for it.
  platform: "instagram" or "youtube" only when the person names that app or service; otherwise null.
  after / before: "YYYY-MM-DD", only when the words name a calendar time (a date, month, season with a year,
    year, or a time relative to today), worked out from today's date. Never set dates for a life period or
    phase that has no calendar time. This is when they interacted with it, not when it was published.
  require: only interactions the words say the person had (liked, saved, shared, watched). Never add one that
    is not said; never require two unless both are said.
  exclude: only interactions the person says did NOT happen. Never use exclude for topics, creators, channels
    or kinds of content to avoid.
  min_watch_count / max_watch_count: only for words about how many times they watched something.
  min_duration_s / max_duration_s: only for words about length (long -> min 1200; short or quick -> max 300).
  shorts: "only" for YouTube Shorts, "exclude" if they say not Shorts, else null.
  sort: only if the words ask for an order (most_watched, longest, shortest, newest, oldest); else "relevance".
  topic_free: true only when the search is entirely about behaviour (when, how often, how long, saved or not)
    with no subject, mood or purpose. A mood or purpose is not topic-free."""

_FILTERS_BLOCK = ("- filters: only what the query states explicitly. Otherwise use null / [].\n"
                  "  before/after: \"YYYY-MM-DD\" dates, worked out from the date given and the query wording.\n"
                  "  interactions: a subset of [\"save\", \"like\", \"collection\", \"share_self\", \"share_friend\"],\n"
                  "  e.g. \"I sent to friends\" -> [\"share_friend\"].")
SYSTEM = QR.SYSTEM.replace(_FILTERS_BLOCK, INTENT_RULES_V3.strip("\n")).replace(
    "The items are Instagram reels and posts (later also YouTube videos, articles, podcasts). Each item is\n"
    "indexed only by its caption, its hashtags and the creator's handle and name.",
    "The items are Instagram reels and posts and YouTube videos. Each item is indexed only by its caption or\n"
    "title, its hashtags and the creator's or channel's name.")
assert SYSTEM != QR.SYSTEM and "YouTube videos. Each item" in SYSTEM and "- filters:" not in SYSTEM

INTENT_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["platform", "after", "before", "require", "exclude", "min_watch_count", "max_watch_count",
                 "min_duration_s", "max_duration_s", "shorts", "sort", "topic_free"],
    "properties": {
        "platform": {"type": ["string", "null"], "enum": PLATFORMS + [None]},
        "after": {"type": ["string", "null"]}, "before": {"type": ["string", "null"]},
        "require": {"type": "array", "items": {"type": "string", "enum": FLAGS}},
        "exclude": {"type": "array", "items": {"type": "string", "enum": FLAGS}},
        "min_watch_count": {"type": ["integer", "null"]}, "max_watch_count": {"type": ["integer", "null"]},
        "min_duration_s": {"type": ["integer", "null"]}, "max_duration_s": {"type": ["integer", "null"]},
        "shorts": {"type": ["string", "null"], "enum": ["only", "exclude", None]},
        "sort": {"type": "string", "enum": SORTS},
        "topic_free": {"type": "boolean"}}}
SCHEMA = copy.deepcopy(QR.SCHEMA)
SCHEMA["required"] = [k for k in SCHEMA["required"] if k != "filters"] + ["intent"]
SCHEMA["properties"].pop("filters")
SCHEMA["properties"]["intent"] = INTENT_SCHEMA
RESPONSE_FORMAT = {"type": "json_schema", "json_schema": {"name": "query_plan", "strict": True, "schema": SCHEMA}}

NONE = {"platform": None, "after": None, "before": None, "require": [], "exclude": [], "min_watch_count": None,
        "max_watch_count": None, "min_duration_s": None, "max_duration_s": None, "shorts": None, "sort": "relevance",
        "topic_free": False}


def _shot(ans, intent):
    a = {k: v for k, v in ans.items() if k != "filters"}
    a["intent"] = {**NONE, **intent}
    return a


# qr-v1's two synthetic pairs (intent added) + one new synthetic pair (not an eval search).
FEWSHOT = [
    (QR.FEWSHOT[0][0], _shot(QR.FEWSHOT[0][1], {})),
    (QR.FEWSHOT[1][0], _shot(QR.FEWSHOT[1][1], {"after": "2026-03-20", "before": "2026-06-21",
                                                  "require": ["shared"]})),
    ("lentil soup recipes I liked on instagram in february",
     {"kind": ["topic", "task"],
      "phrases": ["easy lentil soup recipe", "red lentil and vegetable soup cooking",
                  "one pot lentil stew for weeknights"],
      "keywords": ["lentil", "lentilsoup", "soup", "dal", "redlentils", "onepot", "vegan"],
      "hypothetical_captions": ["30 minute red lentil soup 🍲 cozy + cheap #lentilsoup #vegan #onepot",
                                "my grandma's lentil soup with lemon and cumin #soup #comfortfood #lentils",
                                "meal prep lentil stew for the week 🥄 #mealprep #redlentils #dal"],
      "intent": {**NONE, "platform": "instagram", "after": "2026-02-01", "before": "2026-03-01",
                 "require": ["liked"]}}),
]


def messages_for(query):
    msgs = [{"role": "system", "content": SYSTEM}]
    for q, ans in FEWSHOT:
        msgs.append({"role": "user", "content": QR.user_msg(q)})
        msgs.append({"role": "assistant", "content": json.dumps(ans, ensure_ascii=False)})
    msgs.append({"role": "user", "content": QR.user_msg(query)})
    return msgs


def valid_intent(i):
    i = {**NONE, **(i or {})}
    out = dict(NONE)
    out["platform"] = i.get("platform") if i.get("platform") in PLATFORMS else None
    for k in ("after", "before"):
        out[k] = QR.valid_date(i.get(k))
    for k in ("require", "exclude"):
        out[k] = sorted({x for x in i.get(k) or [] if x in FLAGS})
    for k in ("min_watch_count", "max_watch_count", "min_duration_s", "max_duration_s"):
        v = i.get(k)
        out[k] = int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0 else None
    out["require"] = [x for x in out["require"] if x not in out["exclude"]]  # contradiction: exclude wins
    out["shorts"] = i.get("shorts") if i.get("shorts") in ("only", "exclude") else None
    out["sort"] = i.get("sort") if i.get("sort") in SORTS else "relevance"
    out["topic_free"] = bool(i.get("topic_free"))
    return out


_NAMES = {"instagram": re.compile(r"\b(instagram|insta|ig)\b", re.IGNORECASE), "youtube": re.compile(r"\b(youtube|yt)\b", re.IGNORECASE)}


def guard_platform(intent, query):
    """Post-validation of the preregistered rule "platform only when the user names it": keep the model's platform
    only if the search text names exactly that platform (instagram / insta / ig; youtube / yt). Added after the
    first qi-v3 outputs set it in 4 searches per repeat where 1-2 name a platform (no labels seen)."""
    p = intent.get("platform")
    named = [k for k, rx in _NAMES.items() if rx.search(query or "")]
    if p and named != [p]:
        intent = {**intent, "platform": None}
    return intent


def run_rewrite(repeat):
    queries = [q for q in load_queries() if not q["examples"]]
    parses, per_q = {}, {}
    t0 = time.time()
    for q in queries:
        for att in range(4):
            t = time.time()
            try:
                raw, u = ai.openai_chat_json(MODEL, SYSTEM, QR.user_msg(q["query"]), max_tokens=1400,
                                             purpose="query_rewrite_intent", prompt_version=PROMPT_VERSION,
                                             reasoning_effort="minimal", response_format=RESPONSE_FORMAT,
                                             messages=messages_for(q["query"]))
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
    meta = {"model": MODEL, "prompt_version": PROMPT_VERSION, "reasoning_effort": "minimal", "repeat": repeat,
            "n": len(parses), "cost_usd": sum(v["cost_usd"] for v in per_q.values()),
            "rewrite_p50_s": round(float(np.median(secs)), 3), "rewrite_p95_s": round(float(np.percentile(secs, 95)), 3),
            "wall_s": round(wall, 1), "per_query": per_q}
    out = {"_note": f"{PROMPT_VERSION} intent rewrite r{repeat} (c4_intent.py)", "_meta": meta, **parses}
    d = os.path.join(DATA, "runs", "rewrites")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{PROMPT_VERSION}_{MODEL}_r{repeat}.json")
    json.dump(out, open(path, "w"), ensure_ascii=False, indent=1)
    active = sum(1 for p in parses.values() if p["intent"] != NONE)
    print(f"wrote {os.path.basename(path)}: {len(parses)} searches, {active} with a non-empty intent, "
          f"cost ${meta['cost_usd']:.5f}, p50 {meta['rewrite_p50_s']} s, p95 {meta['rewrite_p95_s']} s")


# ---------------- applying the intent on the combined index ----------------
KIND_FLAG = {"like": "liked", "save": "saved", "collection": "saved", "playlist": "saved", "share_self": "shared",
             "share_friend": "shared", "watch": "watched"}


def prepare(S):
    """Per-item behaviour arrays on a c4_lib.Combined index (its own items only)."""
    N = len(S.items)
    S.inter = [[] for _ in range(N)]  # (flag, at)
    for line in open(os.path.join(DATA, "corpus", "interactions.jsonl")):
        r = json.loads(line)
        n = S.id_pos.get(r["item_id"])
        f = KIND_FLAG.get(r["kind"])
        if n is not None and f:
            S.inter[n].append((f, r.get("at") or ""))
    S.flag = {f: np.array([any(g == f for g, _ in xs) for xs in S.inter]) for f in FLAGS}
    pd = [it["platform_data"] for it in S.items]
    S.watch_count = np.array([p.get("watch_count") or 0 for p in pd])
    S.duration = np.array([p.get("duration_s") if p.get("duration_s") is not None else -1 for p in pd])
    low = [(it.get("caption") or "").lower() for it in S.items]
    d = S.duration
    S.short = (d >= 0) & ((d <= 60) | ((d <= 180) & np.array(["#short" in t for t in low])))
    S.plat = np.array([it["platform"] for it in S.items])
    S.last = np.array([max([a for _, a in xs] or [""]) for xs in S.inter])
    S.firsti = np.array([min([a for _, a in xs if a] or ["9999"]) for xs in S.inter])


def describe(i):
    out = []
    if i["platform"]:
        out.append(f"platform {i['platform']}")
    if i["after"] or i["before"]:
        out.append(f"window {i['after'] or '…'}..{i['before'] or '…'}")
    for k in ("require", "exclude"):
        if i[k]:
            out.append(f"{k} " + "+".join(i[k]))
    for k, lab in (("min_watch_count", "watches>="), ("max_watch_count", "watches<="), ("min_duration_s", "dur>="),
                   ("max_duration_s", "dur<=")):
        if i[k] is not None:
            out.append(f"{lab}{i[k]}")
    if i["shorts"]:
        out.append(f"shorts {i['shorts']}")
    if i["sort"] != "relevance":
        out.append(f"sort {i['sort']}")
    if i["topic_free"]:
        out.append("topic-free")
    return "; ".join(out) or "none"


def pool_mask(S, i):
    m = np.ones(len(S.items), bool)
    act = False
    if i["platform"]:
        m &= S.plat == i["platform"]
        act = True
    if i["after"] or i["before"]:
        lo, hi = i["after"] or "0000", i["before"] or "9999"
        want = set(i["require"]) or None
        m &= np.array([any(lo <= a < hi and (want is None or f in want) for f, a in xs) for xs in S.inter])
        act = True
    if i["require"]:
        m &= np.any([S.flag[x] for x in i["require"]], axis=0)
        act = True
    for x in i["exclude"]:
        m &= ~S.flag[x]
        act = True
    if i["min_watch_count"] is not None:
        m &= S.watch_count >= i["min_watch_count"]
        act = True
    if i["max_watch_count"] is not None:
        m &= S.watch_count <= i["max_watch_count"]
        act = True
    if i["min_duration_s"] is not None:
        m &= S.duration >= i["min_duration_s"]
        act = True
    if i["max_duration_s"] is not None:
        m &= (S.duration >= 0) & (S.duration <= i["max_duration_s"])
        act = True
    if i["shorts"] == "only":
        m &= S.short
        act = True
    elif i["shorts"] == "exclude":
        m &= ~S.short
        act = True
    return m, act


def _ts(s):
    try:
        return datetime.datetime.fromisoformat(s[:19]).timestamp()
    except (ValueError, TypeError):
        return 0.0


def behaviour_order(S, m, sort):
    idx = np.flatnonzero(m)
    w = (0.8 * S.flag["saved"][idx] + 0.3 * S.flag["liked"][idx] + 0.6 * S.flag["shared"][idx]
         + 0.1 * np.minimum(S.watch_count[idx], 6))
    key = {"most_watched": (-S.watch_count[idx], -w), "longest": (-S.duration[idx], -w),
           "shortest": (np.where(S.duration[idx] < 0, 1 << 30, S.duration[idx]), -w),
           "newest": (np.array([-_ts(x) for x in S.last[idx]]), -w),
           "oldest": (np.array([_ts(x) for x in S.firsti[idx]]), -w),
           "relevance": (-w, np.array([-_ts(x) for x in S.last[idx]]))}[sort]
    order = np.lexsort(key[::-1])
    return [S.codes[n] for n in idx[order]]


MIN_POOL = 5


def apply(S, fused, i, depth=1000):
    m, act = pool_mask(S, i)
    info = {"intent": describe(i), "pool": int(m.sum()) if act else None, "mode": "unchanged"}
    if not act and i["sort"] == "relevance":
        return fused[:depth], info
    pos = S.pos
    if act and m.sum() < MIN_POOL:
        keep = [c for c in fused if c in pos and m[pos[c]]]
        ks = set(keep)
        info["mode"] = "soft (pool < 5)"
        return (keep + [c for c in fused if c not in ks])[:depth], info
    B = behaviour_order(S, m, i["sort"])
    inpool = [c for c in fused if c in pos and m[pos[c]]]
    if i["topic_free"]:
        info["mode"] = f"behaviour only ({i['sort']})"
        return B[:depth], info
    if i["sort"] != "relevance":
        out = rrf(inpool, B, depth=depth)
        info["mode"] = f"filter + rrf(text, {i['sort']})"
    else:
        ip = set(inpool)
        out = inpool + [c for c in B if c not in ip]
        info["mode"] = "filter, text order, then pool by interaction weight"
    return out[:depth], info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, required=True)
    a = ap.parse_args()
    run_rewrite(a.repeat)


if __name__ == "__main__":
    main()
