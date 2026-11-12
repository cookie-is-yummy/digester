"""PROTOTYPE ONLY - the model picks from the candidates; code enforces BRIEF-10 section 5 on what it returns.

Checks, all in code: a pick must be a listed candidate (rule 1); every extracted line must appear in that item's own
text (rule 2), and counts are computed here from the lines that matched; picks under the fit threshold are dropped,
and fewer picks or none are sent rather than padding (rule 3); avoided words are rechecked; reasons that state
numbers are replaced. Captions go to the model inside <item> tags as data (rule 6).
"""
import json
import os
import re
import unicodedata

from . import config, llm
from .retrieve import contains_word, norm

PROMPT = open(os.path.join(config.HERE, "prompts", f"{config.PROMPT_COMPOSE}.md"), encoding="utf-8").read()


def _squash(s):
    return re.sub(r"[\W_]+", "", norm(s))


NOT_DETAIL = re.compile(r"(link in bio|linkinbio|storefront|amazon|affiliate|follow\b|subscribe|comment\b|giveaway|#\w|"
                        r"http|www\.|@\w|dm me|save this|share this|code\s+\w+\s+for)", re.I)
HEADER = re.compile(r"^\W*(ingredients?|method|steps?|instructions?|directions?|recipe|tips?|for the \w+)\W*(\(.*\))?\W*:?\W*$", re.I)


def clean_line(line):
    """Strip list marks; return None for headers and promotional lines, which are not details."""
    line = " ".join(str(line).split())
    line = re.sub(r"^(?:\d\ufe0f?\u20e3\s*)+", "", line)  # keycap list numbers
    while line and (unicodedata.category(line[0]) in ("So", "Sk", "Mn", "Me", "Cf", "Co", "Cn") or line[0] == "\ufffd"):
        line = line[1:].lstrip()  # an emoji or symbol used as a list mark is not part of the detail
    line = re.sub(r"^(?:[\-\*•·▪✅✔️]+|\d+[\.\)](?!\d))\s*", "", line).strip()  # list marks, never "1.5 cups"
    line = re.sub(r"^(ingredients?|steps?|method|instructions?|tips?)\s*:\s*", "", line, flags=re.I).strip()
    if not line or len(line) > 110 or HEADER.match(line) or line.endswith(":") or NOT_DETAIL.search(line):
        return None
    return line


TOKEN = re.compile(r"\d+(?:[./,]\d+)*|[^\W\d_]+", re.UNICODE)
UNSAFE_TEXT = re.compile(r"(https?://|www\.|\b[\w-]+\.(com|net|org|io|co|ly|me|app|link)\b|@\w)", re.I)


def tokens(s):
    s = norm(s).replace("\u2044", "/").replace("½", " 1/2").replace("¼", " 1/4").replace("¾", " 3/4")
    return TOKEN.findall(re.sub(r"(?<=\d)(?=1/[234]\b)", " ", s))


def line_in_text(line, text):
    """The line's words and numbers must appear in the item's text as a whole run, in order (case, spacing and
    punctuation ignored). '2 cups' does not match '12 cups'; 'oil' does not match 'boil'. A one-word line needs at
    least 4 letters."""
    a, b = tokens(line), tokens(text)
    if not a or (len(a) == 1 and (len(a[0]) < 4 or a[0].isdigit())):
        return False
    n = len(a)
    return any(b[i:i + n] == a for i in range(len(b) - n + 1))


STOP = set("a an and the of for to in on with my your our this that is it at by from or easy best quick simple "
           "recipe video reel post how make".split())


PROMO_TITLE = re.compile(r"\b(comment|links?|giveaway|follow|dm|subscribe|shop|discount|code|sale|tap|click)\b", re.I)


def title_from_item(it, words=8):
    """A name made only of the item's own words (used when the model's title is not supported by the item): its first
    line that is not a call to comment, follow or shop; otherwise a neutral name with the creator."""
    kind = {"youtube": "video"}.get(it.platform, "post")
    neutral = f"A {kind} from {it.creator}" if it.creator else f"A {kind} from your library"
    for line in [it.first_line] + re.split(r"(?<=[.!?])\s+", it.caption)[:3]:
        line = re.split(r"(?<=[.!?])\s", line, maxsplit=1)[0]
        parts = [w for w in line.split() if not w.startswith(("#", "@", "http"))]
        if len(parts) < 2 or PROMO_TITLE.search(line) or NOT_DETAIL.search(line):
            continue
        out = " ".join(parts[:words]).strip(" -:|,(")
        if len(parts) > words:
            out += "…"
        return out[:72]
    return neutral


def title_ok(title, it):
    """At least half of the title's meaningful words must be in the item's own text or creator name. A short summary
    in the model's words passes; a name for a different thing does not."""
    text = norm(it.caption + " " + (it.creator or ""))
    words = [w for w in tokens(title) if len(w) >= 3 and w not in STOP and not w.isdigit()]
    if not words:
        return False
    hits = sum(1 for w in words if contains_word(text, w))
    return hits * 2 >= len(words)


def as_data(text):
    """Item text wrapped as data; angle brackets are neutralised so the text cannot close its own tag."""
    return "<item>" + text.replace("<", "‹").replace(">", "›") + "</item>"


def _safe(s, n):
    s = " ".join(str(s or "").split())[:n]
    return "" if UNSAFE_TEXT.search(s) else s


def _candidate_block(cands):
    rows = []
    for i, it in enumerate(cands, 1):
        how = ", ".join(it.how()) or "in their library"
        meta = f"{it.platform}{' ' + it.media if it.media else ''}; by {it.creator or 'unknown'}; {how}"
        if it.kept_on():
            meta += f" ({it.kept_on()[:7]})"
        text = it.caption[:config.CAPTION_CHARS] or "(no text; title unknown)"
        rows.append(f"{i}. {meta}\n{as_data(text)}")
    return "\n".join(rows)


def compose(cands, spec, person_handle, request_text=None, feedback_note="", known_lines=None):
    """Returns (result dict, cost). result: picks [{item, title, why, fit, lines, details_in_video, n_lines}],
    intro, none_reason, dropped (counts of what the checks removed)."""
    c = spec.content
    if not cands:
        reason = (f"nothing you kept since {c.saved_after} matched" if c.saved_after else
                  "nothing in your library matched")
        return {"picks": [], "intro": "", "none_reason": reason, "dropped": {}}, 0.0
    # compose v1 reads one extract word; a v2 list of several kinds is passed as one phrase ("ingredients and steps")
    extract = " and ".join(c.extract) if c.extract else "none"
    ask = {"request": request_text or c.goal, "goal": c.goal, "count": c.count, "extract": extract, "avoid": c.avoid}
    block = _candidate_block(cands)
    if known_lines is not None:  # a follow-up: the details already found, with counts computed here
        notes = []
        for i, it in enumerate(cands, 1):
            ls = known_lines.get(it.id) or []
            notes.append(f"{i}. details found in its text: {len(ls)}" + (": " + "; ".join(ls) if ls else
                         " (none; the details are only in the video, so it cannot answer questions about them)"))
        block += "\n\nWhat the bot already found (counts are exact):\n" + "\n".join(notes)
    user = ("Request: " + json.dumps(ask, ensure_ascii=False) + (("\n" + feedback_note) if feedback_note else "")
            + "\n\nCandidates:\n" + block)
    raw, cost = llm.chat_json(PROMPT, user, purpose="mvp_compose", prompt_version=config.PROMPT_COMPOSE,
                              person=person_handle, max_tokens=1600)
    dropped = {"not_a_candidate": 0, "low_fit": 0, "avoided": 0, "lines_not_in_text": 0, "repeat": 0, "over_count": 0,
               "title_replaced": 0}
    picks, seen = [], set()
    for p in raw.get("picks") or []:
        try:
            n = int(p.get("n"))
            fit = float(p.get("fit", 0))
        except (TypeError, ValueError):
            dropped["not_a_candidate"] += 1
            continue
        if not 1 <= n <= len(cands):
            dropped["not_a_candidate"] += 1
            continue
        if n in seen:
            dropped["repeat"] += 1
            continue
        it = cands[n - 1]
        if fit < config.FIT_MIN:
            dropped["low_fit"] += 1
            continue
        title = _safe(p.get("title"), 70)
        if any(contains_word(it.caption, w) or contains_word(title, w) for w in c.avoid):
            dropped["avoided"] += 1  # the model's own name for it counts too: it errs toward leaving the item out
            continue
        if not title or not title_ok(title, it):  # rule 2: a name the item's own text does not support is not shown
            dropped["title_replaced"] += 1
            title = title_from_item(it)
        else:  # a number in a title ("10-Minute", "3-Ingredient") must be in the post's text, or that word goes
            have = set(tokens(it.caption))
            kept = [w for w in title.split() if all(t in have for t in tokens(w) if t[0].isdigit())]
            if len(kept) != len(title.split()):
                title = " ".join(kept).strip(" -:|,") or title_from_item(it)
        if len(picks) >= max(c.count, 1):
            dropped["over_count"] += 1
            continue
        seen.add(n)
        lines = []
        for raw_line in (p.get("lines") or [])[:14]:
            raw_line = " ".join(str(raw_line).split())[:160]
            if not raw_line:
                continue
            if not line_in_text(raw_line, it.caption):
                dropped["lines_not_in_text"] += 1
                continue
            line = clean_line(raw_line)
            if line and line not in lines:
                lines.append(line)
            elif not line:
                dropped["not_a_detail"] = dropped.get("not_a_detail", 0) + 1
        reused = False
        if known_lines is not None and c.extract and not lines:
            lines = list(known_lines.get(it.id) or [])
            reused = bool(lines)   # the lines found before, not lines for this request
        why = _safe(p.get("why"), 160)
        if re.search(r"\d", why) or not why:
            why = f"It fits: {c.goal}."
        picks.append({"item": it, "title": title, "why": why, "fit": round(fit, 2), "lines": lines, "lines_reused": reused,
                      "n_lines": len(lines), "details_in_video": bool(c.extract) and not lines})
    intro = _safe(raw.get("intro"), 160)
    if re.search(r"\d", intro):
        intro = ""
    reason = _safe(raw.get("none_reason"), 200)
    return {"picks": picks, "intro": intro, "none_reason": reason, "dropped": dropped}, cost
