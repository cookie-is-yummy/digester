"""PROTOTYPE ONLY - the model picks from the candidates; code enforces BRIEF-10 section 5 on what it returns.

Checks, all in code: a pick must be a listed candidate (rule 1); every extracted line must appear in that item's own
text (rule 2), and counts are computed here from the lines that matched; picks under the fit threshold are dropped,
and fewer picks or none are sent rather than padding (rule 3); avoided words are rechecked; reasons that state
numbers are replaced. Captions go to the model inside <item> tags as data (rule 6).
"""
import json
import os
import re

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
    line = re.sub(r"^(?:[\-\*•·▪✅✔️]+|\d+[\.\)])\s*", "", line).strip()  # list marks only, not quantities
    line = re.sub(r"^(ingredients?|steps?|method|instructions?|tips?)\s*:\s*", "", line, flags=re.I).strip()
    if not line or len(line) > 110 or HEADER.match(line) or line.endswith(":") or NOT_DETAIL.search(line):
        return None
    return line


def line_in_text(line, text):
    """A normalised match: case, spacing and punctuation are ignored; the words and numbers must all be there, in order."""
    a = _squash(line)
    return len(a) >= 3 and a in _squash(text)


def _candidate_block(cands):
    rows = []
    for i, it in enumerate(cands, 1):
        how = ", ".join(it.how()) or "in their library"
        meta = f"{it.platform}{' ' + it.media if it.media else ''}; by {it.creator or 'unknown'}; {how}"
        if it.kept_on():
            meta += f" ({it.kept_on()[:7]})"
        text = it.caption[:config.CAPTION_CHARS] or "(no text; title unknown)"
        rows.append(f"{i}. {meta}\n<item>{text}</item>")
    return "\n".join(rows)


def compose(cands, spec, person_handle, request_text=None, feedback_note="", known_lines=None):
    """Returns (result dict, cost). result: picks [{item, title, why, fit, lines, details_in_video, n_lines}],
    intro, none_reason, dropped (counts of what the checks removed)."""
    c = spec.content
    if not cands:
        reason = (f"nothing you kept since {c.saved_after} matched" if c.saved_after else
                  "nothing in your library matched")
        return {"picks": [], "intro": "", "none_reason": reason, "dropped": {}}, 0.0
    ask = {"request": request_text or c.goal, "goal": c.goal, "count": c.count, "extract": c.extract, "avoid": c.avoid}
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
    dropped = {"not_a_candidate": 0, "low_fit": 0, "avoided": 0, "lines_not_in_text": 0, "repeat": 0, "over_count": 0}
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
        title = " ".join(str(p.get("title") or "").split())[:70] or (it.creator or "From your library")
        if any(contains_word(it.caption, w) or contains_word(title, w) for w in c.avoid):
            dropped["avoided"] += 1
            continue
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
        if known_lines is not None and c.extract != "none" and not lines:
            lines = list(known_lines.get(it.id) or [])
        why = " ".join(str(p.get("why") or "").split())[:160]
        if re.search(r"\d", why) or not why:
            why = f"It fits: {c.goal}."
        picks.append({"item": it, "title": title, "why": why, "fit": round(fit, 2), "lines": lines,
                      "n_lines": len(lines), "details_in_video": c.extract != "none" and not lines})
    intro = " ".join(str(raw.get("intro") or "").split())[:160]
    if re.search(r"\d", intro):
        intro = ""
    reason = " ".join(str(raw.get("none_reason") or "").split())[:200]
    return {"picks": picks, "intro": intro, "none_reason": reason, "dropped": dropped}, cost
