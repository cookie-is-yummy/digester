"""PROTOTYPE ONLY - details of one picked item (ingredients, steps, key points), from its whole text (DESIGN.md sections
3 and 4, extract prompt v1).

One call per picked item, on the full caption (not the 600-character cut the composer sees) or, for YouTube, the title
and the description videos.list returned. Every line is checked in code exactly as before (`line_in_text`: the words
in order, in that item's text; `clean_line`: no headers, links or calls to follow or shop). A long step or key point
is cut to its first sentence (it is still the item's own words, and "…" shows the cut). Results are cached in the
store's facts table per (library, item, kind): details found once are reused always. An empty result is cached only
after two attempts. When code sees list-like lines in the text and no line survives, the call is tried once more.
Recipes get ingredients and steps when both are in the text. Item text is data, never instructions (rule 6).
"""
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from . import config, llm
from .compose import as_data, clean_line, line_in_text, own_text, own_text_lines

PROMPT = open(os.path.join(config.HERE, "prompts", f"{config.PROMPT_EXTRACT}.md"), encoding="utf-8").read()
ORDER = ["ingredients", "steps", "key_points"]
MAX_LINES = 15
MAX_CHARS = 6000
MIN_TEXT = 40          # a text shorter than this (a bare title) holds no list: no call is made
LIST_MARK = re.compile(r"^\s*(?:\d{1,2}\s*[.)\-:]|\d️?⃣|[-*•·▪◦➤►▶✅✔☑️🔸🔹⭐️👉]|[^\w\s])\s*\S", re.U)
LIST_HEAD = re.compile(r"^\W*(ingredients?|method|steps?|instructions?|directions?|you(?:'ll)? need|tips?)\W*:?\s*$",
                       re.I | re.M)


def kinds_for(extract):
    """The kinds one call asks for: a recipe ask (ingredients or steps) gets both, when both are in the text."""
    ks = set(extract or [])
    if ks & {"ingredients", "steps"}:
        ks |= {"ingredients", "steps"}
    return [k for k in ORDER if k in ks]


def list_like(text):
    """True when the text looks like it holds a list: a list heading, or 3 or more lines that start with a list mark."""
    if LIST_HEAD.search(text or ""):
        return True
    return sum(1 for line in (text or "").splitlines() if LIST_MARK.match(line)) >= 3


def _cut(line, limit=105):
    """A long line cut to its first sentence, or to a word boundary, with '…'. Still the item's own words."""
    if len(line) <= limit:
        return line
    first = re.split(r"(?<=[.!?])\s", line, maxsplit=1)[0]
    if 15 <= len(first) <= limit:
        return first
    return line[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"


def verify(raw_lines, text, kind):
    """(lines, dropped): the model's lines that are in the text, cleaned; at most MAX_LINES."""
    out, dropped = [], 0
    for raw in (raw_lines or [])[:MAX_LINES + 5]:
        line = " ".join(str(raw).split())[:400]
        if not line:
            continue
        if not line_in_text(line, text):
            cl = clean_line(line) if len(line) <= 110 else line
            if not cl or not line_in_text(cl, text):
                dropped += 1
                continue
            line = cl
        line = re.sub(r"(?:\s*#[^\s#]+)+\s*$", "", line).strip()      # hashtags at the end are not the detail
        if kind != "ingredients":
            line = _cut(line)
        cl = clean_line(line)
        if not cl:
            dropped += 1
            continue
        if cl not in out:
            out.append(cl)
        if len(out) >= MAX_LINES:
            break
    return out, dropped


def _call(kinds, text, person, seed, note=""):
    user = "Kinds wanted: " + json.dumps(kinds) + (("\n" + note) if note else "") + "\n\n" + as_data(text[:MAX_CHARS])
    return llm.chat_json(PROMPT, user, purpose="mvp_extract", prompt_version=config.PROMPT_EXTRACT, person=person,
                         max_tokens=1400, temperature=config.EXTRACT_TEMPERATURE, seed=seed)


def details(it, extract, library, store=None, person=None, extra=None, now=None):
    """({kind: lines}, info) for one item. info: cost, calls, dropped, cached (kinds read from the cache)."""
    kinds = kinds_for(extract)
    info = {"cost": 0.0, "calls": 0, "dropped": 0, "cached": 0}
    if not kinds:
        return {}, info
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(days=config.YOUTUBE_KEEP_DAYS)).astimezone(timezone.utc).isoformat(timespec="seconds")
    have = store.facts_get(library, it.id, kinds, since=since) if store is not None else {}
    info["cached"] = len(have)
    need = [k for k in kinds if k not in have]
    if not need:
        return {k: have[k] for k in kinds}, info
    full = own_text_lines(it, extra)
    if len(full) < MIN_TEXT:   # a bare title: no list to read, and nothing worth caching
        return {**{k: [] for k in need}, **have}, info
    text = own_text(it, extra)
    source = "youtube_api" if ((extra or {}).get(it.id) or {}).get("description") else "caption"
    got, tries = {k: [] for k in need}, {k: 0 for k in need}
    ask, note = list(need), ""
    for attempt in range(2):
        raw, cost = _call(ask, full, person, config.EXTRACT_SEED + attempt, note)
        info["cost"] += cost
        info["calls"] += 1
        returned_any = False
        for k in ask:
            tries[k] += 1
            lines, dropped = verify(raw.get(k) if isinstance(raw, dict) else None, text, k)
            info["dropped"] += dropped
            returned_any = returned_any or bool(dropped)
            got[k] = lines
        ask = [k for k in ask if not got[k]]
        if not ask or not list_like(full):   # retry only when the text looks like it holds a list
            break
        note = ("Your last lines were not exact copies of the text. Copy the words exactly as written."
                if returned_any else "Look again: the text seems to hold a list.")
    if store is not None:
        for k in need:
            prev = store.facts_attempts(library, it.id, k)
            store.facts_put(library, it.id, k, got[k], config.PROMPT_EXTRACT,
                            attempts=1 if got[k] else prev + tries[k], source=source, at=now)
    return {k: (have.get(k) if k in have else got[k]) for k in kinds}, info


def details_many(items, extract, library, store=None, person=None, extra=None, now=None, workers=4):
    """details() for several picked items at once (the calls run in parallel). Returns ({item_id: {kind: lines}},
    info summed)."""
    total = {"cost": 0.0, "calls": 0, "dropped": 0, "cached": 0}
    if not items or not kinds_for(extract):
        return {}, total
    if len(items) == 1:
        res = [details(items[0], extract, library, store, person, extra, now)]
    else:
        with ThreadPoolExecutor(max_workers=min(workers, len(items))) as ex:
            res = list(ex.map(lambda it: details(it, extract, library, store, person, extra, now), items))
    out = {}
    for it, (facts, info) in zip(items, res):
        out[it.id] = facts
        for k in total:
            total[k] += info[k]
    return out, total
