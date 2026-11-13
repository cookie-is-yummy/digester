"""PROTOTYPE ONLY - messages code reads without the model, and answers about a pick already shown (fix pass after the
live findings of 12 Nov: findings 1, 2, 4, 5, 6 and 27). Mixed into core.Bot.

- Plain commands ("stop 2", "pause 1", "resume all", "skip 3", "run 1", "done 2", "remove 3", "my rules", "undo",
  "help") are read here before any model call: exact, case-insensitive, optional trailing punctuation. They cannot be
  misread, cost nothing and answer at once. Anything longer goes to the model.
- After an answer, "another", "more", "one more", "next" are `more` with the last spec unchanged, and "only new stuff,
  not from my saves" is `more` with outside "only", with no model call.
- A question about the details of a pick already shown ("what are the steps for the first one?") is answered
  directly: one line naming the pick, then the lines asked for (from what was found before, or the details step on
  the pick's whole text now; for YouTube its description), or one honest line saying the post does not write them
  out, with the link. Never "I recommend" about a pick already shown.
"""
import re

from . import texts as T
from .render import Reply, by, kind_lines, link_part
from .schema import Interpretation, RuleSpec

COMMAND = re.compile(r"^\s*(?:(?:please|pls|plz)[\s,]+)?(stop|pause|resume|skip|run|done|remove)\s+"
                     r"(?:rule\s+|#\s*|number\s+)?(\d{1,2}|all)\s*(?:,?\s*(?:please|pls|plz))?\s*[.!?]*\s*$", re.I)
WORDS = {"my rules": "list_rules", "rules": "list_rules", "list my rules": "list_rules", "show my rules": "list_rules",
         "undo": "undo", "help": "help"}
MORE = re.compile(r"^\s*(?:(?:give me|send me|show me|try|ok|okay)\s+)?(another(?: one)?|more|one more|next(?: one)?|"
                  r"something else|a different one)\s*(?:please|pls)?\s*[.!?]*\s*$", re.I)
# a message that only asks for new things from outside the saves; what is left after these phrases must be nothing
_NEW_PARTS = re.compile(r"\b(?:only|just|please|pls|give me|show me|send me|find me|i want|some|stuff|ones?|things|"
                        r"picks|videos|something|new|instead|"
                        r"(?:not|nothing|none) from my saves?|from outside(?: of)? my saves?|outside(?: of)? my saves?|"
                        r"not (?:what|stuff) i (?:saved|kept))\b", re.I)
_NEW_NEEDS = re.compile(r"\b(new|outside)\b", re.I)

DETAIL = {"ingredients": re.compile(r"\b(ingredients?|what do i need|what does it need|shopping list"
                                    r"|ingredientes?|qu[eé] necesito)\b", re.I),   # review fix X3: and in Spanish
          "steps": re.compile(r"\b(steps?|method|instructions?|directions|how (?:do|did|can|to) (?:i |you |we )?"
                              r"(?:make|cook|bake|build|do|prepare)|walk me through|exercises?"
                              r"|pasos?|instrucciones|ejercicios?|c[oó]mo (?:se )?(?:hace|prepara|cocina))\b", re.I),
          "key_points": re.compile(r"\b(key points?|main points?|takeaways?|tips|summar\w*|the gist|highlights|"
                                   r"what does it say|what (?:is|are) (?:it|they) about)\b", re.I)}
POINTER = re.compile(r"\b(?:the\s+)?(first|second|third|fourth|fifth|last|1st|2nd|3rd|4th|5th)\s+(?:one|pick|recipe|"
                     r"video|post|reel|tutorial|workout)\b|#\s?([1-9])\b|\bnumber\s+([1-9])\b|"
                     r"\b(?:that|this|the|those|these)\s+(?:\w+\s+)?(?:one|ones|recipe|video|post|reel|tutorial|workout)\b|"
                     r"\b(?:it|its|it's|that|this|them)\b", re.I)
ORDINAL = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4, "fifth": 5,
           "5th": 5}
# "add its ingredients to my list", "email me the steps": an action on the answer, not a question about it
ACTING = re.compile(r"\b(add|put|jot|stick|throw|pop|save|email|e-mail|send|text me|remind|calendar|schedule|"
                    r"every|daily|tomorrow|tonight|at \d)\b", re.I)
KIND_WORDS = {"ingredients": "the ingredients", "steps": "the steps", "key_points": "the key points"}


# fix pass 3, finding 69: "when I say boost, send me a motivational video": the word is read from the rule's own
# request text (the person's words, kept with the rule), so it works after a restart with nothing else stored
TRIGGER = re.compile(r"\bwhen(?:ever)?\s+i\s+(?:say|text|type|write|send(?:\s+you)?)\s+[\"'“‘]?"
                     r"([^\W\d_][\w'-]{0,24}?(?:\s+[^\W\d_][\w'-]{0,24}?)?)[\"'”’]?"
                     r"(?=\s*(?:[,.;:!?]|$)|\s+(?:send|give|show|find|get|pick|remind|text|then|you|please|pls)\b)", re.I)
NOT_A_WORD = set("it that this so yes no ok okay something anything".split())


def trigger_word(text):
    """The word a saved rule is asked for by ("boost"), from the person's own request, lower case; or None."""
    m = TRIGGER.search((text or "").split(" / ")[0])
    if not m:
        return None
    word = " ".join(m.group(1).lower().split())
    return None if word in NOT_A_WORD or plain_command(word) is not None else word


def _said(text):
    return " ".join(re.sub(r"[\"'“”‘’.!?,]+", " ", (text or "").lower()).split())


def plain_command(text):
    """The Interpretation for a plain command, or None. Code only; no model call."""
    t = " ".join((text or "").lower().split()).rstrip(" .!?")
    t = re.sub(r"^(?:please|pls|plz)[\s,]+|[\s,]+(?:please|pls|plz)$", "", t)   # "pls stop rule 2", "undo please"
    if t in WORDS:
        return Interpretation(intent=WORDS[t])
    m = COMMAND.match(text or "")
    if not m:
        return None
    verb, arg = m.group(1).lower(), m.group(2).lower()
    if arg == "all":
        if verb not in ("pause", "resume", "stop"):
            return None
        return Interpretation(intent=verb, all_rules=True)
    n = int(arg)
    if n < 1:
        return None
    if verb in ("done", "remove"):
        return Interpretation(intent="todo_done" if verb == "done" else "todo_remove", todo_number=[n])
    if verb == "run":
        return Interpretation(intent="run_rule", rule_number=n)
    return Interpretation(intent=verb, rule_number=n)


def more_command(text):
    """'another', 'more', 'one more', 'next' -> more; 'only new stuff, not from my saves' -> more with outside only.
    None for anything else."""
    if MORE.match(text or ""):
        return Interpretation(intent="more")
    t = (text or "").lower()
    if _NEW_NEEDS.search(t) and not re.sub(r"[\W_]+", " ", _NEW_PARTS.sub(" ", t)).strip():
        return Interpretation(intent="more", outside="only")
    return None


def detail_kinds(*texts):
    t = " ".join(x for x in texts if x)
    return [k for k, rx in DETAIL.items() if rx.search(t)]


def pick_number(text, n_items):
    """The pick a message names ("the first one", "#2", "the last one"), or None."""
    for m in POINTER.finditer(text or ""):
        if m.group(1):
            w = m.group(1).lower()
            return n_items if w == "last" else ORDINAL[w]
        if m.group(2) or m.group(3):
            return int(m.group(2) or m.group(3))
    return None


def points_at_pick(text):
    return bool(POINTER.search(text or ""))


_ASK_WORDS = set("what are is the its for of please pls can could you give me show send list all and how about do i "
                 "tell what's whats them those these"
                 # review fix X3: the same in Spanish
                 " cuales cuáles son los las el la del de dame dime muestra muéstrame muestrame qué que por favor"
                 " tiene lleva".split())


def only_detail_words(text):
    """'what are the steps?', 'ingredients please': nothing but the detail asked for (so it is about the last answer,
    not a new search like "any tips for Blender?")."""
    t = text or ""
    for rx in DETAIL.values():
        t = rx.sub(" ", t)
    return not [w for w in re.findall(r"[^\W\d_]+", t.lower()) if w not in _ASK_WORDS]


class FollowupMixin:
    def code_reads(self, person, text, last):
        """(Interpretation, needs_paid_call) for a message code reads by itself, or (None, False)."""
        it = plain_command(text)
        if it is not None:
            return it, False
        h = person["handle"]
        said = _said(text)
        if said and len(said) <= 50:   # finding 69: a saved rule's own word, exact and in any case
            from .store import numbered
            for n, r in numbered(self.store.rules(h)):
                if r["status"] == "active" and (r["spec"].get("when") or {}).get("type") == "on_request" \
                        and trigger_word(r.get("text")) == said:
                    return Interpretation(intent="run_rule", rule_number=n), True
        if self.store.get_state(f"lastspec:{h}"):
            it = more_command(text)
            if it is not None:
                return it, True
        if last and last.get("items") and detail_kinds(text) and not ACTING.search(text) and \
                (points_at_pick(text) or only_detail_words(text)):
            return Interpretation(intent="follow_up", question=" ".join(text.split())[:300],
                                  pick_number=pick_number(text, len(last["items"]))), True
        return None, False

    # ---------- another one ----------
    def _more(self, person, it, text, lead="", easier=False, lead_none=""):
        """One more like the last answer, without what it showed. A change rides on it ("another but shorter"); a
        must-have made of filler words never does (finding 2). `lead` starts the reply (a feedback line)."""
        from .interpret import clean_criteria
        h = person["handle"]
        st = self.store.get_state(f"lastspec:{h}")
        if not st:
            return self.send(h, T.MORE_OF_WHAT)
        spec = RuleSpec.model_validate(st["spec"])
        c = spec.content
        crit = clean_criteria(list(it.criteria or []), c.goal or "", *c.searches)
        if it.avoid or crit or it.outside:   # "another but shorter": the change rides on the same request
            c.avoid = list(dict.fromkeys([*c.avoid, *it.avoid]))[:8]
            c.criteria = list(dict.fromkeys([*c.criteria, *crit]))[:5]
            if it.outside:
                c.outside = it.outside
        if easier:   # "too hard": the easiest first, for the level that just moved down
            c.order = "easiest_first"
        rule = self.store.rule(st["rule_id"]) if st.get("rule_id") else None
        request = st.get("text") or text
        if rule and rule["status"] in ("active", "paused"):  # one more from a rule counts as sent by that rule
            msg, run_id, n = self.run(person, spec, "manual", rule_id=rule["id"], request_text=request,
                                      shown=st.get("shown") or [])
        else:
            msg, run_id, n = self.run(person, spec, "more", request_text=request, shown=st.get("shown") or [])
        block = getattr(self._tl, "outside_block", None)
        if not n and not self._run_failed(run_id) and c.source == "library" and c.outside == "none" \
                and not (block and block[0] == run_id):
            msg = self._more_none(person, spec, request)   # review fix X11 (experience): what is left, not a dead end
        if lead:   # "Here's an easier one:" only above one; above "nothing found" or an error, the feedback line alone
            msg = (lead if n and not self._run_failed(run_id) else (lead_none or "")) + msg
        return self.deliver(person, spec, msg + self._not_yet_notes(spec, sep="\n\n"), run_id,
                            kind="manual" if rule else "more", rule_id=rule["id"] if rule else None,
                            request_text=request)

    def _more_none(self, person, spec, request):
        """Review fix X11: "another" once everything that fits was shown: say that, and offer new ones from YouTube
        when that route can serve this request (English only: "new ones" is read in English)."""
        from . import lang as L
        lang = self._answer_lang()
        t = L.table(lang)
        msg = (t.get("more_none") or L.EN["more_none"]).format(goal=spec.content.goal)
        if lang is None:
            try:
                ok = self._outside().available(person["handle"], spec, [request], now=self.clock())
            except Exception:  # noqa: BLE001
                ok = False
            if ok:
                msg += L.EN["more_new"]
        return msg

    # ---------- a question about a pick already shown ----------
    def _detail_answer(self, person, last, kinds, n):
        """The lines asked for of pick n of the last answer, or one honest line and its link. No compose call."""
        from .compose import title_from_item
        from .extract import details
        from .store import now_iso
        h = person["handle"]
        now = self.clock()
        items = last.get("items") or []
        if not 1 <= n <= len(items):
            return self.send(h, T.which_pick(len(items)))
        iid = items[n - 1]
        view = self.view(person["library"])
        it = view.get(iid)
        if it is None:
            return self.send(h, T.ITEMS_GONE)
        snap = self.store.answer(last["run_id"]) or {}
        rec = next((p for p in snap.get("picks") or [] if p.get("item_id") == iid), None) or {}
        title = rec.get("title") or title_from_item(it)
        cur = self.store.last_answer(h)
        is_last = bool(cur) and cur["run_id"] == last["run_id"]
        state_facts = (self.store.get_state(f"facts:{h}", {}) or {}) if is_last else {}
        facts = dict((state_facts.get(iid) if isinstance(state_facts, dict) else None) or rec.get("facts") or {})
        need = [k for k in kinds if not facts.get(k)]
        cost, calls, extra, status = 0.0, 0, {}, "ok"
        if it.platform == "youtube":
            try:
                extra = self._youtube().details([it], now=now)
            except Exception:  # noqa: BLE001 - without the description, the title is all there is
                extra = {}
        if need and not self._over_cap(person):
            try:
                got, info = details(it, need, view.lib, store=self.store, person=h, extra=extra, now=now)
                cost, calls = info["cost"], info["calls"]
                for k, v in got.items():
                    if v:
                        facts[k] = v
            except Exception:  # noqa: BLE001 - one honest line instead
                status = "error"
        found = [k for k in kinds if facts.get(k)]
        missing = [k for k in kinds if not facts.get(k)]
        name = f"{title}{by(it)}"
        has_desc = bool((extra.get(iid) or {}).get("description"))
        parts = []
        if found:
            lines = [T.detail_head([KIND_WORDS[k] for k in found], name)]
            for k in found:
                lines += kind_lines(k, facts[k], label=len(found) > 1)
            for k in missing:
                lines.append(T.detail_missing(KIND_WORDS[k], it.platform, has_desc))
            parts.append({"type": "text", "text": "\n".join(lines)})
            if it.url:
                parts.append(link_part(it, title))
        else:
            words = T.and_words([KIND_WORDS[k] for k in kinds])
            parts.append({"type": "text", "text": T.detail_none(words, name, it.platform, has_desc)})
            if it.url:
                parts.append(link_part(it, title))
        run_id = self.store.add_run(handle=h, kind="follow_up", at=now_iso(now), n_candidates=1,
                                    n_picks=1 if found else 0, n_dropped=0, cost_usd=round(cost, 6),
                                    status="picked" if found else ("error" if status == "error" else "none"),
                                    prompt_version=None, seconds=0.0, steps={"details": calls})
        self.note(run_id=run_id)
        if is_last and found:   # what "add its ingredients" and the next follow-up read
            fs = state_facts if isinstance(state_facts, dict) else {}
            fs[iid] = facts
            self.store.set_state(f"facts:{h}", fs)
            lines_st = self.store.get_state(f"lines:{h}", {}) or {}
            lines_st[iid] = [x for k in ("ingredients", "steps", "key_points") for x in facts.get(k) or []]
            self.store.set_state(f"lines:{h}", lines_st)
            kinds_st = self.store.get_state(f"linekinds:{h}", {}) or {}
            kinds_st[iid] = [k for k in ("ingredients", "steps", "key_points") if facts.get(k)]
            self.store.set_state(f"linekinds:{h}", kinds_st)
        return self.send(h, Reply(parts), run_id)
