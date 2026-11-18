"""PROTOTYPE ONLY - round 10, slice S (DESIGN.md section 17.S): "the caption may not match the video".

Meme pages paste long text that has nothing to do with the clip (a chatbot recipe, a spec sheet, a course ad). The bot
only reads text, so such a reel can come back as a recipe. This module marks those items from text alone (no model, no
embeddings, no network), learns from what the person says ("that reel had nothing to do with it"), and gives the code
that ranks, orders and words an answer the mark to use.

- The mark is DERIVED data (AGENTS rules 2 and 10): `<library>/marks/caption_marks-cm-v1.json`, keyed by the library's
  build stamp; a new SIGNAL_VERSION writes a new file beside the old one. Built after an import (`refresh`) and by a
  background thread at bot start; until the file exists no item is marked (today's behaviour).
- What the person says is CORE data (`caption_feedback` table): never regenerated; the effective level is worked out
  around it (`effective`).
- Captions are third-party text: they are only matched by fixed patterns here; no caption word ever reaches a reply,
  a prompt or a reason (the reasons are fixed codes, worded by code).
- English patterns only: a caption in another language is missed, never a false alarm.
"""
import hashlib
import json
import os
import re
import time
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone

STUB = False
SIGNAL_VERSION = "cm-v1"
REASONS = ("says_unrelated", "chatbot_text", "pasted_elsewhere", "same_caption_repeated", "account_memes",
           "joke_over_block", "account_mostly_chatbot")
FP_MIN = 60          # a fingerprint only for a body this long (a short caption like "so good" is under many accounts)

# ---------- the text signals (ported rule of the diagnosis's v3; not its file, not its counts) ----------
HASH = re.compile(r"#\w+", re.U)
HANDLE = re.compile(r"@[\w.]+")
URL = re.compile(r"https?://\S+|www\.\S+")


def body(caption):
    """The caption's words, lowercased, without tags, handles and links (what a copy under another account shares)."""
    c = URL.sub(" ", HANDLE.sub(" ", HASH.sub(" ", caption or "")))
    c = unicodedata.normalize("NFKC", c).lower()
    return " ".join(re.findall(r"[^\W_]+", c))


def fingerprint(caption):
    """sha256 of the normalised body, first 16 hex characters; None when the body is short."""
    b = body(caption)
    return hashlib.sha256(b.encode()).hexdigest()[:16] if len(b) >= FP_MIN else None


UNIT = re.compile(r"\b\d+(?:[./]\d+)?\s*(?:g|kg|ml|l|cups?|tbsp|tsp|tablespoons?|teaspoons?|oz|lbs?|grams?|cloves?|"
                  r"pinch)\b", re.I)
HDR = re.compile(r"^\W*(#+\s*)?\**\s*(ingredients?|instructions?|method|directions?|steps?|recipe|how to make|"
                 r"you(?:'|’)ll need|what you need)\b", re.I | re.M)
LISTLINE = re.compile(r"^\s*(?:[-*•▪✅🔸🔹🔶▫️]|\d+[.)])\s*\S+\s+\S+\s+\S+", re.M)


def howto(c):
    """A recipe, steps or tips block: a header, 3 or more amounts, or 5 or more list lines of 3 words or more."""
    c = c or ""
    return bool(HDR.search(c)) or len(UNIT.findall(c)) >= 3 or len(LISTLINE.findall(c)) >= 5


def recipe(c):
    c = c or ""
    return bool(re.search(r"\bingredients?\b", c, re.I)) or len(UNIT.findall(c)) >= 3


# B: text pasted from a chatbot: markdown Instagram never shows, or an assistant's opener
OPENER = re.compile(
    r"(^\s*(?:here(?:'|’)s|here is)\s+(?:a|an|the|your|some)\b[^\n]{0,60}?\b(?:recipe|guide|list|tips|steps|breakdown|"
    r"overview|rundown|version|explanation|information|info)\b"
    r"|^\s*(?:no problem|certainly|sure|absolutely|of course)[!,.]"
    r"|\benjoy your (?:delicious|creamy|homemade|tasty|flavorful|flavourful)\b"
    r"|\bhow about (?:a|an) recipe\b"
    r"|\bhere(?:'|’)s the information (?:about|on)\b)", re.I | re.M)
MARKUP = re.compile(r"(\*\*[^*\n]{2,60}\*\*|^\s*#{2,4}\s+\w)", re.M)
# the assistant's own words, which alone make a strong mark (the narrow echo list of the diagnosis's v3): a creator's
# "Here's the full breakdown" of their own tutorial is chatbot-like evidence (above), never enough on its own
ECHO = re.compile(
    r"(^\s*here(?:'|’)s\s+(?:a|an)\s+(?:[\w-]+\s+(?:and\s+)?){0,3}recipe\s+for\b"
    r"|^\s*(?:no problem|certainly|sure|absolutely|of course)[!,.]\s*(?:here|below)\b"
    r"|\benjoy your (?:delicious|creamy|homemade|tasty|flavorful|flavourful)\b"
    r"|\bhow about (?:a|an) recipe\b"
    r"|\bhere(?:'|’)s the information (?:about|on)\b)", re.I | re.M)

# C: a meme account by its handle or display name (whole words)
MEMEW = re.compile(r"(?:^|[^a-z])(memes?|memez|funny|funnies|lol|lmao|humou?r|comedy|jokes?|shitpost\w*|dank|fails|"
                   r"viral|clips?z?|repost\w*|cursed|brainrot|goofy|satire|parody|unhinged|reels?|vids|laughs?)"
                   r"(?:[^a-z]|$)", re.I)
# C2: captions that read like a meme page's
PAGE = re.compile(r"(follow (?:\(us\) )?@[\w.]+ (?:for|or)|#(?:memes?|dankmemes|funnymemes|memesdaily|comedy|funny)\b|"
                  r"^\W*(?:ain.?t no way|bro\b|nah\b|pov\b|💀|😭|😂|🤣|☠️))", re.I | re.M)
# E: a joke first line over a how-to block
CUES = re.compile(r"(\bpov\b|\bme when\b|\bwhen (?:you|u|your|ur)\b|\bbro\b|\blol\b|\blmao\b|\bnah\b|💀|😭|😂|🤣|😹|"
                  r"\bfr\b|\bngl\b|\bwait for it\b|\bain.?t no way\b)", re.I)
# G: the caption says it is unrelated
DISCLAIM = re.compile(r"(caption (?:is |for )?(?:for )?(?:the )?algo|for the algo(?:rithm)?\b|"
                      r"ignore (?:the |my |this )?(?:caption|tags|hashtags|text)|random caption|"
                      r"caption (?:has )?nothing to do|unrelated caption|(?:don'?t|dont) mind (?:the|this) "
                      r"(?:caption|post)|caption (?:is )?unrelated|algorithm (?:purposes|reasons)|"
                      r"(?:recipe|caption) (?:in|for) (?:the )?(?:algo|engagement))", re.I)
# the creator's own voice in the first lines: never a strong mark
VOICE = re.compile(r"\b(i|my|me|we|our)\b", re.I)
FOLLOW_LINE = re.compile(r"^\W*(follow|like and follow|follow us|follow me)\b", re.I)


def chatbot(c):
    return bool(OPENER.search(c or "") or MARKUP.search(c or ""))


def first_line(c):
    return next((ln.strip() for ln in (c or "").splitlines() if ln.strip()), "")


def joke_over_block(c):
    if not howto(c):
        return False
    fl = first_line(c)
    if not CUES.search(fl):
        return False
    lines = (c or "").splitlines()
    k = next((i for i, ln in enumerate(lines) if ln.strip()), 0)
    rest = set(body("\n".join(lines[k + 1:])).split())
    return not any(w in rest for w in body(fl).split() if len(w) >= 4)


def own_voice(c):
    """First person in either of the first two lines that are not "follow" lines: the creator speaking."""
    lines = [ln for ln in (c or "").splitlines() if ln.strip() and not FOLLOW_LINE.search(ln)][:2]
    return any(VOICE.search(ln) for ln in lines)


def opener_line(line):
    """A line that starts like an assistant's reply ("Here's a delicious recipe for ..."): never a card title."""
    return bool(OPENER.search(line or ""))


# ---------- the build (pure Python over raw rows) ----------
def _creator(row):
    pd = row.get("platform_data") or {}
    return (pd.get("owner_handle") or pd.get("owner_name") or "").lower().strip().lstrip("@") or None


def _shingles(b, n=6):
    w = b.split()
    return {hashlib.md5(" ".join(w[i:i + n]).encode()).hexdigest()[:12] for i in range(max(0, len(w) - n + 1))}


def build_rows(rows):
    """{item_id: [level, reasons, fp]} for the Instagram rows given (friends' rows must already be left out), only the
    marked ones. Level "strong" (the v3 rule) or "weak" (the broad rule, minus strong)."""
    ig = [r for r in rows if r.get("platform") == "instagram"]
    cap = {r["id"]: r.get("caption") or "" for r in ig}
    cr = {r["id"]: _creator(r) for r in ig}
    bodies = {i: body(c) for i, c in cap.items()}
    # A: the same body (60+ chars) under 2+ accounts, or 6-word shingles with Jaccard >= 0.5 between accounts
    by_body = defaultdict(set)
    for i, b in bodies.items():
        if len(b) >= 60:
            by_body[b].add(cr[i])
    pasted = {i for i, b in bodies.items() if len(b) >= 60 and len(by_body[b] - {None}) >= 2}
    sh = {i: _shingles(b) for i, b in bodies.items() if len(b.split()) >= 15}
    inv = defaultdict(list)
    for i, s in sh.items():
        for x in s:
            inv[x].append(i)
    checked = set()
    for lst in inv.values():
        if len(lst) < 2 or len(lst) > 40:
            continue
        for a_ in range(len(lst)):
            for b_ in range(a_ + 1, len(lst)):
                a, b = lst[a_], lst[b_]
                if cr[a] == cr[b] or (a, b) in checked:
                    continue
                checked.add((a, b))
                if len(sh[a] & sh[b]) / len(sh[a] | sh[b]) >= 0.5:
                    pasted.update((a, b))
    # account-level: K (mostly chatbot), C2 (meme-page captions), A2 (one long body repeated 3+ times)
    by_cr = defaultdict(list)
    for r in ig:
        by_cr[cr[r["id"]]].append(r["id"])
    mostly_chatbot, page_like = set(), set()
    for c, ids in by_cr.items():
        if c and len(ids) >= 3:
            if sum(chatbot(cap[i]) for i in ids) / len(ids) >= 0.5:
                mostly_chatbot.add(c)
            if sum(bool(PAGE.search(cap[i])) for i in ids) / len(ids) >= 0.3:
                page_like.add(c)
    same = defaultdict(list)
    for i, b in bodies.items():
        if len(b) >= 80 and cr[i]:
            same[(cr[i], b)].append(i)
    repeated = {i for ids in same.values() if len(ids) >= 3 for i in ids}
    out = {}
    for r in ig:
        i, c = r["id"], cap[r["id"]]
        pd = r.get("platform_data") or {}
        name = f"{pd.get('owner_handle') or ''} {pd.get('owner_name') or ''}".replace("_", " ").replace(".", " ")
        ev = {"chatbot_text": chatbot(c), "pasted_elsewhere": i in pasted, "same_caption_repeated": i in repeated,
              "account_memes": bool(MEMEW.search(name)) or cr[i] in page_like, "joke_over_block": joke_over_block(c),
              "account_mostly_chatbot": cr[i] in mostly_chatbot}
        h, long_ = howto(c), len(c) >= 300
        says = bool(DISCLAIM.search(c))
        reasons = [k for k in REASONS[1:] if ev[k]]
        level = None
        if says:
            level, reasons = "strong", ["says_unrelated"] + reasons
        elif (h or long_) and not own_voice(c) and (ECHO.search(c) or len(reasons) >= 2):
            level = "strong"
        else:
            filler = any(ev[k] for k in ("chatbot_text", "pasted_elsewhere", "same_caption_repeated",
                                         "joke_over_block", "account_mostly_chatbot"))
            if (filler and (h or long_)) or (h and ev["account_memes"]):
                level = "weak"
        if level:
            out[i] = [level, reasons, fingerprint(c)]
    return out


def marks_path(lib, version=None):
    return os.path.join(lib, "marks", f"caption_marks-{version or SIGNAL_VERSION}.json")


def _rows(lib):
    """The library's own rows, friends' posts left out (rule 5), as LibraryView reads them."""
    from .libview import LIB
    path = LIB.p(lib, "corpus", "items.jsonl")
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                raw = json.loads(line)
                if not LIB.is_friend(raw):
                    out.append(raw)
    return out


def build_file(lib):
    """Builds the marks of one library and writes them beside its derived files (atomic), with a line in
    `marks/build_log.jsonl` (items, marked, items per second, wall time: AGENTS rule 11). Returns the file's dict."""
    from .retrieve import _library_stamp
    lib = os.path.abspath(lib)
    t0 = time.time()
    stamp = _library_stamp(lib)
    rows = _rows(lib)
    items = build_rows(rows)
    wall = time.time() - t0
    counts = {"items": len(rows), "instagram": sum(1 for r in rows if r.get("platform") == "instagram"),
              "strong": sum(1 for v in items.values() if v[0] == "strong"),
              "weak": sum(1 for v in items.values() if v[0] == "weak")}
    data = {"version": SIGNAL_VERSION, "stamp": stamp, "built_at": datetime.now(timezone.utc).isoformat(
        timespec="seconds"), "counts": counts, "items": items}
    path = marks_path(lib)
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    tmp = path + f".tmp{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)
    with open(os.path.join(d, "build_log.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"at": data["built_at"], "version": SIGNAL_VERSION, "items": counts["items"],
                            "marked_strong": counts["strong"], "marked_weak": counts["weak"],
                            "items_per_s": round(counts["items"] / max(wall, 1e-9)), "wall_s": round(wall, 3)}) + "\n")
    return data


def load_into(view):
    """Puts the marks of the file that matches this library build and SIGNAL_VERSION on the view's items. False when
    there is no such file (then no item is marked: today's behaviour)."""
    from .retrieve import _library_stamp
    try:
        with open(marks_path(view.lib), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return False
    if data.get("version") != SIGNAL_VERSION or data.get("stamp") != _library_stamp(view.lib):
        return False
    for iid, (level, reasons, fp) in (data.get("items") or {}).items():
        it = view.items.get(iid)
        if it is not None and level in ("strong", "weak"):
            it.caption_mark, it.caption_reasons, it.caption_fp = level, tuple(reasons or ()), fp
    view.cm_loaded = SIGNAL_VERSION
    return True


def ensure(view):
    """The marks on the view, built first when missing (bot start, in a background thread; after an import)."""
    if getattr(view, "cm_loaded", None) == SIGNAL_VERSION or load_into(view):
        return True
    build_file(view.lib)
    return load_into(view)


def ensure_lib(lib):
    """After an import: the new library's marks are written before the person is switched to it, so the first answer
    from it never waits for them and never goes unmarked."""
    from .retrieve import _library_stamp
    try:
        with open(marks_path(lib), encoding="utf-8") as f:
            data = json.load(f)
        if data.get("version") == SIGNAL_VERSION and data.get("stamp") == _library_stamp(os.path.abspath(lib)):
            return data
    except (OSError, ValueError):
        pass
    return build_file(lib)


# ---------- per item ----------
def mark(it):
    """'strong', 'weak' or None: the library's mark, before what the person said."""
    return getattr(it, "caption_mark", None)


def fp_of(it):
    fp = getattr(it, "caption_fp", None)
    if fp:
        return fp
    return fingerprint(getattr(it, "raw_caption", None) or getattr(it, "caption", "") or "")


def fp_accounts(view, fp):
    """The accounts whose items carry this fingerprint (worked out once per view)."""
    idx = getattr(view, "cm_fp_index", None)
    if idx is None:
        idx = defaultdict(set)
        for it in view.items.values():
            if it.platform == "instagram":
                f = fp_of(it)
                if f:
                    idx[f].add(it.creator)
        view.cm_fp_index = idx
    return idx.get(fp, set())


# ---------- what the person taught it (core data) ----------
def index(rows):
    """From caption_feedback rows (oldest first): the latest word per item and per fingerprint; per creator the
    mismatches since their last "fine" and the "fine"s since their last mismatch."""
    items, fps, mism, oks = {}, {}, defaultdict(int), defaultdict(int)
    for r in rows:
        k = r["kind"]
        items[r["item_id"]] = k
        if r.get("fp"):
            fps[r["fp"]] = k
        c = r.get("creator")
        if c:
            if k == "mismatch":
                mism[c] += 1
                oks[c] = 0
            elif k == "match_ok":
                oks[c] += 1
                mism[c] = 0
    return {"items": items, "fps": fps, "creators": {c: n for c, n in mism.items() if n},
            "fine": {c: n for c, n in oks.items() if n}}


def effective(it, fb=None):
    """(level, reasons) for one person (design C2, rules 1 to 6). `you_said` leads the reasons when it is their word."""
    level, reasons = mark(it), list(getattr(it, "caption_reasons", None) or ())
    if not fb:
        return level, reasons
    said = fb["items"].get(it.id)
    if said == "match_ok":
        return None, []
    if said == "mismatch":
        return "strong", ["you_said"] + reasons
    fp = fp_of(it) if (fb["fps"] or level) else None
    if fp and fb["fps"].get(fp) == "mismatch":
        return "strong", ["you_said"] + reasons
    if fp and fb["fps"].get(fp) == "match_ok":
        return None, []
    n = fb["creators"].get(it.creator, 0)
    if n:
        raw = getattr(it, "raw_caption", None) or it.caption or ""
        if level == "weak" or (n >= 2 and (howto(raw) or len(raw) >= 300)):
            return "strong", ["you_said"] + reasons
    if level == "strong" and fb["fine"].get(it.creator, 0) >= 2:
        return "weak", reasons   # two "that one was fine" for this account: its marks drop to weak
    return level, reasons


def creator_weights(fb):
    """Review design C2 rule 4: an account the person said posts mismatched captions counts half, on every request."""
    return {c: 0.5 for c in (fb or {}).get("creators", {})}


HOWTO_REQUEST = re.compile(r"\b(recipes?|workouts?|routines?|tutorials?|tips?|how to|steps?|guides?)\b", re.I)


def howto_request(spec, *texts):
    c = spec.content
    return bool(c.extract) or bool(HOWTO_REQUEST.search(" ".join([c.goal or "", *c.searches, *[t or "" for t in texts]])))


def rank_factor(level, howto_req):
    """No long-caption boost for a marked item is the caller's; a strong mark counts 0.4 on a how-to request, else 0.8.
    A marked item stays in the window, so it can still be the honest only fit."""
    if level == "strong":
        return 0.4 if howto_req else 0.8
    return 1.0


# ---------- the order of an answer and its words ----------
def what_of(spec, request_text, it):
    """What the caption is, for the doubt line: from the request's kind words, else from the caption itself."""
    words = " ".join([request_text or "", spec.content.goal or "", *spec.content.searches]).lower()
    if re.search(r"\b(recipes?|cook\w*|dish(?:es)?|meals?|bake|baking|dinner|lunch|breakfast)\b", words):
        return "recipe"
    if re.search(r"\b(workouts?|exercises?|training)\b", words):
        return "workout"
    if re.search(r"\b(tips?|hacks?|advice|ideas?)\b", words):
        return "tips"
    raw = getattr(it, "raw_caption", None) or it.caption or ""
    if recipe(raw):
        return "recipe"
    return "howto" if howto(raw) else "text"


def _annotate(p, fb):
    level, reasons = effective(p["item"], fb)
    p["cm"], p["cm_reasons"] = level, reasons
    if level == "strong":
        from .compose import display_title
        p["title"] = display_title(p["item"], level="strong")   # never a name taken from a pasted caption


def order_picks(result, spec, fb=None, request_text=None):
    """Design C3, in code after compose.check: a strong-marked pick never leads when a pick that is not strong-marked,
    with verdict clear or close, is among the picks, the wider list or the spare list; the strong ones move to the
    end of the picks. Returns how many strong picks were moved (steps["mark_demoted"]). Annotates every pick with
    `cm` / `cm_reasons` and sets result["only_marked"] (the lead is strong: every fit is) and the words' inputs."""
    picks = result.get("picks") or []
    wider, spare = result.get("wider") or [], result.get("spare") or []
    for p in picks + wider + spare + (result.get("others") or []):
        _annotate(p, fb)
    result["cm_howto"] = howto_request(spec, request_text)
    if not picks:
        return 0
    moved = 0
    if picks[0]["cm"] == "strong":
        keep = [p for p in picks if p["cm"] != "strong"]
        strong = [p for p in picks if p["cm"] == "strong"]
        if not keep:
            alt = next((p for p in wider + spare if p["cm"] != "strong" and p.get("verdict") in ("clear", "close")),
                       None)
            if alt is not None:
                keep = [alt]
                if any(alt is w for w in wider):
                    result["wider"] = [w for w in wider if w is not alt]
                else:
                    result["spare"] = [s for s in spare if s is not alt]
        if keep:
            moved = len(strong)
            result["picks"] = picks = keep + strong
            if picks[0].get("verdict") != "clear" and not result.get("closest"):
                # the trusted fits are only close: said as the closest, never "I recommend"
                result["closest"] = True
                crits = spec.content.criteria
                result["missing"] = [(cr, picks[0]["criteria"][i]) for i, cr in enumerate(crits)
                                     if i < len(picks[0].get("criteria") or []) and picks[0]["criteria"][i] != "yes"]
    result["only_marked"] = picks[0]["cm"] == "strong"
    if result["only_marked"]:
        result["cm_what"] = what_of(spec, request_text, picks[0]["item"])
    return moved


def is_strong(p):
    return p.get("cm") == "strong"


# the doubt line's reason, in a fixed order (design C3); `you_said` and `says_unrelated` are always named
REASON_ORDER = (("says_unrelated",), ("you_said",), ("account_memes", "account_mostly_chatbot"),
                ("pasted_elsewhere", "same_caption_repeated"), ("joke_over_block",), ("chatbot_text",))
SURE_REASONS = ("says_unrelated", "you_said")


def doubt_reason(reasons, all_reasons=True):
    """The first reason code (of the fixed order) that applies, or None. With all_reasons False (the founder's labels
    put the mark's precision under 85%), only the two reasons that do not rest on the mark."""
    for group in REASON_ORDER:
        hit = next((r for r in group if r in (reasons or ())), None)
        if hit and (all_reasons or hit in SURE_REASONS):
            return group[0] if group[0] in ("account_memes", "pasted_elsewhere") else hit
    return None


def lead_lines(result, lang=None):
    """The line right after the lead's sentence: the doubt line for a strong lead, the 'going by its caption' line
    for a weak lead on a how-to request; [] otherwise."""
    from . import config
    from . import lang as L
    picks = result.get("picks") or []
    if not picks:
        return []
    p = picks[0]
    t = L.table(lang)
    if p.get("cm") == "strong":
        why = doubt_reason(p.get("cm_reasons"), config.CM_DOUBT_ALL)
        if why is None:
            return [t["cm_weak"]]
        return [t["cm_doubt"].format(what=t["cm_what"][result.get("cm_what") or "text"], reason=t["cm_reason"][why])]
    if p.get("cm") == "weak" and result.get("cm_howto"):
        return [t["cm_weak"]]
    return []


def placeable(picks):
    """For a rule run that adds to the person's apps (slice G): the picks that may be added, and how many strong ones
    were left out (`T.cm_left_out(n)`). A strong-marked item is never placed in an outside app by a rule run."""
    keep = [p for p in picks if p.get("cm") != "strong"]
    return keep, len(picks) - len(keep)


# ---------- what the person says (fit_reads, the thumbs-down question) ----------
_N = r"(?:\s+(?:number\s+|#)?(\d))?"
_ORDW = r"(?:(?:first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th)\s+)?"
MISMATCH = re.compile(
    r"\b(?:(?:(?:that|the|this)\s+" + _ORDW + r"(?:reel|video|post|one|clip)|(?:reel|video|post|clip))" + _N +
    r"\s+(?:had|has)\s+nothing\s+to\s+do\s+with\b"
    r"|(?:the\s+)?(?:video|reel|clip)" + _N + r"\s+(?:doesn'?t|didn'?t|does\s+not|did\s+not|don'?t)\s+match\b"
    r"|wrong\s+video\b"
    r"|(?:it'?s|its|that'?s|thats)\s+(?:just\s+)?a\s+meme\b"
    r"|the\s+caption\s+(?:is|was)\s+(?:fake|wrong|unrelated|copied|pasted)\b"
    r"|the\s+caption\s+(?:has|had)\s+nothing\s+to\s+do\s+with\b"
    r"|(?:the\s+)?(?:video|reel)" + _N + r"\s+(?:is|was)\s+(?:something\s+else|unrelated)\b)", re.I)
MATCH_OK = re.compile(
    r"^\s*(?:(?:that|the)\s+" + _ORDW + r"(?:one|reel|video)" + _N + r"\s+(?:was|is)\s+(?:fine|ok|okay|right)"
    r"|the\s+video\s+(?:was|is)\s+(?:right|fine|ok|okay)"
    r"|it\s+did\s+match|the\s+caption\s+(?:was|is)\s+right)\b[\s.!]*$", re.I)
SLOP = re.compile(r"^\s*(?:(?:that'?s|thats|this\s+is|that\s+is|it'?s|its)\s+)?(?:just\s+|total\s+|pure\s+)?slop"
                  r"[\s.!]*$", re.I)
# ---------- checks of round 10 (reading): the everyday ways of saying "slop" ask too ("that's ai slop", "slop lol",
# "these are slop", "the first one is slop", "that was slop"); "that's not slop" is never one ----------
_SLOP_FILL = r"(?:lol|lmao|ugh|bro|man|honestly|ngl|tbh|fr|ok|okay|yeah|yea|so|again|omg)"
SLOP_MORE = re.compile(
    r"^\s*(?:" + _SLOP_FILL + r"[\s,!.]+)*"
    r"(?:(?:that'?s|thats|this\s+is|that\s+is|it'?s|its|that\s+was|this\s+was|it\s+was|these\s+are|those\s+are|"
    r"they'?re|they\s+are|(?:that|this|the)\s+" + _ORDW + r"(?:one|reel|video|post|clip|pick)" + _N +
    r"\s+(?:is|was))\s+)?"
    r"(?:just\s+|total\s+|pure\s+|such\s+|so\s+much\s+|complete\s+|absolute\s+|more\s+)?(?:a?\s*)?(?:ai\s+)?slop"
    r"(?:[\s,!.]+" + _SLOP_FILL + r")*[\s.!]*$", re.I)
# a complaint about what was asked ("the video doesn't match what i asked for", "wrong video, i wanted soup") is
# about the answer, not the caption: the bot asks before it learns anything (W-6)
ABOUT_ASK = re.compile(r"\b(?:what|the\s+thing)\s+i\s+(?:asked|wanted|meant|said|was\s+looking)\b|\bmy\s+(?:question|"
                       r"request|search)\b|\bi\s+(?:wanted|asked\s+for|meant|was\s+looking\s+for)\b", re.I)
_CLAUSE_END = re.compile(r"[,;.!]|\bbut\b|\band\b|\bwhile\b", re.I)


def _clause(t, m):
    """The words of the clause that holds the match m ("the first one was fine, the second one had nothing to do
    with it" -> "the second one had nothing to do with it")."""
    start = max([x.end() for x in _CLAUSE_END.finditer(t, 0, m.start())] or [0])
    nxt = _CLAUSE_END.search(t, m.end())
    return t[start:nxt.start() if nxt else len(t)]
# ---------- end checks of round 10 (reading) ----------
ORDINAL = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "1st": 1, "2nd": 2, "3rd": 3}
ORD = re.compile(r"\b(first|second|third|fourth|fifth|1st|2nd|3rd)\s+(?:one|reel|video|post|pick)\b", re.I)
YES = re.compile(r"^\s*(?:yes|yeah|yep|yup|y|right|exactly|it was|correct|that'?s it)\b[\s.!]*$", re.I)
NO = re.compile(r"^\s*(?:no|nope|nah|n|not really|it wasn'?t|no it was fine)\b[\s.!]*$", re.I)
WINDOW = timedelta(hours=48)
ASK_TTL = timedelta(minutes=30)


def _run_at(store, run_id):
    r = store.one("SELECT at FROM runs WHERE id=?", (run_id,)) if run_id else None
    try:
        return datetime.fromisoformat(r["at"]) if r and r.get("at") else None
    except ValueError:
        return None


def _shown(bot, h, now):
    """The last answer with picks, when it is still in view (48 hours)."""
    last = bot._answer_seen(h)
    if not last or not last.get("items"):
        return None
    at = _run_at(bot.store, last.get("run_id"))
    if at is None or now - at > WINDOW:
        return None
    return last


def _items(bot, person, ids):
    view = bot.view(person["library"])
    return view, [view.get(i) for i in ids]


def _chosen(its, fb, number):
    """The pick a message is about: the number named; else the only marked pick shown; else pick 1."""
    if number and 1 <= number <= len(its):
        return its[number - 1]
    marked = [it for it in its if it is not None and effective(it, fb)[0]]
    if len(marked) == 1:
        return marked[0]
    return its[0] if its else None


def _number(text, m):
    n = next((int(g) for g in (m.groups() if m else ()) if g), None)
    if n is None:
        o = ORD.search(text)
        n = ORDINAL.get(o.group(1).lower()) if o else None
    return n


def learn(bot, person, it, kind, source, now):
    """Keeps what the person said about one item (core data) and returns the reply."""
    from . import texts as T
    h = person["handle"]
    view = bot.view(person["library"])
    fp = fp_of(it)
    bot.store.add_caption_feedback(h, it.id, it.creator, fp, kind, source, at=now)
    bot._wrote_final(h, "feedback on a pick")
    if kind == "match_ok":
        return T.match_ok_reply(it.creator)
    others = len(fp_accounts(view, fp) - {it.creator}) if fp else 0
    return T.mismatch_reply(it.creator, others)


def fit_reads(bot, person, text, now):
    """Hook 0 (after the confirm_delete branch, before draft_reads): "that reel had nothing to do with it", "the video
    doesn't match", "that one was fine"; "slop" asks the one-line question. Needs an answer with picks in view within
    48 hours; None otherwise (the message goes on as before)."""
    from . import texts as T
    t = (text or "").strip()
    if not t or len(t.split()) > 20 or t.endswith("?"):   # a question ("why doesn't my video match ...?") goes on
        return None
    m_bad, m_ok, slop = MISMATCH.search(t), MATCH_OK.search(t), SLOP.search(t) or SLOP_MORE.search(t)
    if not (m_bad or m_ok or slop):
        return None
    h = person["handle"]
    last = _shown(bot, h, now)
    if last is None:
        return None
    fb = index(bot.store.caption_feedback(h))
    view, its = _items(bot, person, last["items"])
    # ---------- checks of round 10 (reading): the pick named in the mismatch's own clause, never one the same message
    # calls fine; a complaint about what was asked is asked about first ----------
    number = _number(t, m_bad or m_ok)
    if m_bad:
        part = _clause(t, m_bad)
        number = _number(part, MISMATCH.search(part))
        other = _number(t[:t.find(part)] + " " + t[t.find(part) + len(part):], None) if part != t else None
        if number is None and other is not None:
            if len(its) != 2:
                return None   # "the first one was fine but the reel had nothing to do with it": which one is unclear
            number = 3 - other
        if ABOUT_ASK.search(t) and not re.search(r"\bcaptions?\b", t, re.I):
            slop, m_bad = True, None
    it = _chosen(its, fb, number)
    # ---------- end checks of round 10 (reading) ----------
    if it is None:
        return None
    bot.note(intent="feedback")
    if slop and not m_bad:
        bot.store.set_state(f"mismatchask:{h}", {"run_id": last.get("run_id"), "item_id": it.id,
                                                 "at": now.isoformat()})
        return bot.send(h, T.MISMATCH_ASK)
    return bot.send(h, learn(bot, person, it, "match_ok" if m_ok and not m_bad else "mismatch", "words", now))


def take_ask(store, h):
    """The open thumbs-down question, taken off as the next message arrives (answered by that message only)."""
    ask = store.get_state(f"mismatchask:{h}")
    if ask:
        store.set_state(f"mismatchask:{h}", None)
    return ask or None


def mismatch_answer(bot, person, text, now, ask):
    """Hook 4b in _asked_reads: "yes" / "no" right after the question. Any other message: None (handled as usual)."""
    from . import texts as T
    if not ask:
        return None
    try:
        at = datetime.fromisoformat(ask["at"])
    except (KeyError, TypeError, ValueError):
        return None
    if now - at > ASK_TTL:
        return None
    t = (text or "").strip()
    if NO.match(t):
        bot.note(intent="feedback")
        return bot.send(person["handle"], T.MISMATCH_NOTED)
    if not YES.match(t):
        return None
    it = bot.view(person["library"]).get(ask.get("item_id"))
    if it is None:
        return None
    bot.note(intent="feedback")
    return bot.send(person["handle"], learn(bot, person, it, "mismatch", "thumbs", now))


def thumbs_ask(bot, person, run_id, items, pick_number, now):
    """After a 👎 on an answer: the one-line question when the answer showed a marked pick or an Instagram how-to,
    at most once per answer, and never when a rule preview, a draft card or a browser run is newer than the answer
    (W-7). Returns the line (and opens the next-message state) or None."""
    from . import browser
    from . import texts as T
    h = person["handle"]
    if not run_id or not items:
        return None
    if bot.store.get_state(f"mismatchasked:{h}") == run_id:
        return None
    at = _run_at(bot.store, run_id)
    if at is None or now - at > WINDOW:
        return None
    pend = bot.store.pending(h)
    if pend and pend.get("kind") == "confirm_rule" and _iso(pend.get("at")) and _iso(pend.get("at")) >= at:
        return None
    try:
        draft = bot.open_draft(h, now)
    except Exception:  # noqa: BLE001 - no drafts helper: no card can be newer
        draft = None
    if draft and _iso((draft.get("state") or {}).get("at")) and _iso(draft["state"]["at"]) >= at:
        return None
    if browser.run_open(bot.store, h, now):
        return None
    fb = index(bot.store.caption_feedback(h))
    _, its = _items(bot, person, items)
    its = [it for it in its if it is not None]
    if pick_number and 1 <= pick_number <= len(items):
        it = bot.view(person["library"]).get(items[pick_number - 1])
        cands = [it] if it is not None else []
    else:
        cands = its
    it = next((x for x in cands if effective(x, fb)[0]), None) or next(
        (x for x in cands if x.platform == "instagram" and howto(getattr(x, "raw_caption", "") or x.caption)), None)
    if it is None:
        return None
    bot.store.set_state(f"mismatchasked:{h}", run_id)
    bot.store.set_state(f"mismatchask:{h}", {"run_id": run_id, "item_id": it.id, "at": now.isoformat()})
    return T.MISMATCH_ASK


def _iso(s):
    try:
        d = datetime.fromisoformat(s) if s else None
    except (TypeError, ValueError):
        return None
    if d is not None and d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d
