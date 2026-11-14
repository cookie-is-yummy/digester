"""PROTOTYPE ONLY - round 8 (BN3, BN4; DESIGN.md section 14): what the person has been into lately, and the theme check.

The vision's Understanding promise: what their attention keeps returning to, what is rising or fading, and how that
compares with what they say they want. Everything here is counted by code from the library view and the profile; no
model call, no minutes or time spent (docs/07), never a sensitive topic, never a friend's post (LibraryView leaves them
out).

- Kept means a save, a collection, a post sent to themselves or a playlist, dated by the latest of those. Likes are
  counted apart and always called "liked". Watches never count as wanting.
- A topic's posts are its guess's support lines plus kept posts whose text holds one of its checked words.
- The windows end at the newest date of any kind per platform in the library (never today, so moving the clock changes
  nothing): "lately" is the 56 days up to it, "before" the 182 days before that. Topics are compared by their part of
  all that was kept in each window, since overall keeping changes a lot over time.
- Labels: rising (at least 5 lately and at least twice the part before), fading (at least 10 before and at most 0.4
  times the part before), steady (at least 3 lately), else too few to tell.

Mixed into core.Bot: the code-read messages "what have I been into lately", the theme check's answer, "<topic> is
<label> now", "what did I park?" and "every export" right after a trends answer.
"""
from datetime import date

from . import profile as P
from . import texts as T
from .retrieve import contains_word

KEPT = ("save", "collection", "share_self", "playlist")
RECENT_DAYS = 56
BEFORE_DAYS = 182
RISING_MIN, RISING_TIMES = 5, 2.0
FADING_MIN, FADING_TIMES = 10, 0.4
STEADY_MIN = 3
MAX_LINES = 7          # the trends message
CHECK_TOPICS = 5       # topics the theme check asks about at most
ORDER = {"rising": 0, "steady": 1, "fading": 2, "few": 3}


def kept_day(it):
    """The day the person kept it: the latest save, collection, share to self or playlist date; None if none."""
    days = [it.dates[k][:10] for k in KEPT if it.dates.get(k)]
    return date.fromisoformat(max(days)) if days else None


def liked_day(it):
    d = it.dates.get("like")
    return date.fromisoformat(d[:10]) if d and not kept_day(it) else None


def anchors(view):
    """{platform: the newest date of any kind in the library on that platform}."""
    out = {}
    for it in view.items.values():
        if it.dates:
            d = date.fromisoformat(max(it.dates.values())[:10])
            if it.platform not in out or d > out[it.platform]:
                out[it.platform] = d
    return out


def _window(d, anchor):
    """'recent', 'before' or None for a day, against its platform's anchor."""
    if anchor is None or d is None or d > anchor:
        return None
    age = (anchor - d).days
    if age < RECENT_DAYS:
        return "recent"
    if age < RECENT_DAYS + BEFORE_DAYS:
        return "before"
    return None


def topic_words_of(i):
    return [w for w in i.get("words") or [] if w] or P.topic_words(i["topic"])


def label(recent, before, recent_total, before_total):
    now_part = recent / recent_total if recent_total else 0.0
    old_part = before / before_total if before_total else 0.0
    if recent >= RISING_MIN and (old_part == 0 or now_part >= RISING_TIMES * old_part):
        return "rising"
    if before >= FADING_MIN and now_part <= FADING_TIMES * old_part:
        return "fading"
    if recent >= STEADY_MIN:
        return "steady"
    return "few"


def trends(view, prof, direction=None):
    """The counts behind the trends message. Returns {"anchors", "recent_total", "before_total", "topics": [{"topic",
    "relation", "trend", "recent", "before", "liked"}], "direction": None | {"text", "topic", "recent", "before"}}."""
    anc = anchors(view)
    kept, liked = [], []
    for it in view.items.values():
        a = anc.get(it.platform)
        w = _window(kept_day(it), a)
        if w:
            kept.append((it, w))
            continue
        w = _window(liked_day(it), a)
        if w == "recent":
            liked.append(it)
    recent_total = sum(1 for _, w in kept if w == "recent")
    before_total = sum(1 for _, w in kept if w == "before")
    topics = []
    for i in prof.get("interests") or []:
        if i.get("relation") == "not_me" or P.sensitive(i.get("topic"), i.get("why"), " ".join(i.get("words") or [])):
            continue
        words = topic_words_of(i)
        support = set(i.get("support_ids") or [])

        def about(it, words=words, support=support):
            return it.id in support or any(contains_word(it.caption, x) for x in words)
        recent = sum(1 for it, w in kept if w == "recent" and about(it))
        before = sum(1 for it, w in kept if w == "before" and about(it))
        likes = sum(1 for it in liked if about(it))
        topics.append({"topic": P.shown_topic(i["topic"]), "relation": i.get("relation"),
                       "trend": label(recent, before, recent_total, before_total),
                       "recent": recent, "before": before, "liked": likes})
    out = {"anchors": anc, "recent_total": recent_total, "before_total": before_total, "topics": topics,
           "direction": None}
    if direction:
        # the direction is compared only with topics that are not "just for fun" (BN4), by profile.match_topic
        usable = [i for i in prof.get("interests") or [] if i.get("relation") not in ("enjoy", "not_me")
                  and not P.sensitive(i.get("topic"), i.get("why"), " ".join(i.get("words") or []))]
        m = P.match_topic({"interests": usable}, direction)
        row = next((t for t in topics if m and t["topic"] == P.shown_topic(m["topic"])), None)
        out["direction"] = {"text": " ".join(str(direction).split())[:120], "topic": row["topic"] if row else None,
                            "recent": row["recent"] if row else 0, "before": row["before"] if row else 0}
    return out


def message(data):
    """The trends message, at most MAX_LINES lines (texts.trends_message)."""
    return T.trends_message(data, MAX_LINES)


def shown_topics(data):
    """The topics a trends message shows that the theme check may ask about (no label yet), in the order shown."""
    return [t["topic"] for t in T.trend_rows(data, MAX_LINES)[0] if not t.get("relation")][:CHECK_TOPICS]


class AttentionMixin:
    # ---------- "what have I been into lately?" ----------
    def _trends_data(self, person):
        h = person["handle"]
        lib = (self.store.person(h) or person)["library"]   # after an import, the library it switched to
        prof = P.get(self.store, h)
        return trends(self.view(lib), prof, prof["direction"])

    def trends_text(self, person):
        """(message, number of topic lines) for a rule's send (content source "trends"); (None, 0) with no topics."""
        data = self._trends_data(person)
        if not data["topics"] or not (data["recent_total"] or data["before_total"]):
            return None, 0
        rows = T.trend_rows(data, MAX_LINES)
        return message(data), max(1, len(rows[0]) + len(rows[1]) + len(rows[2]))

    def _trends_answer(self, person, now):
        from .store import now_iso
        h = person["handle"]
        self.note(intent="trends")
        data = self._trends_data(person)
        if not data["topics"]:
            return self.send(h, T.TRENDS_NO_TOPICS)
        if not data["recent_total"] and not data["before_total"]:
            return self.send(h, T.TRENDS_NO_DATES)
        parts = [message(data)]
        has_rule = any((r["spec"].get("content") or {}).get("source") == "trends" for r in self.store.rules(h))
        if not has_rule:
            parts.append(T.TRENDS_EVERY_EXPORT)
            self.store.set_state(f"trendsoffer:{h}", {"at": now_iso(now)})
        onboarding = (self._onboard(h) or {}).get("step") not in (None, "done")
        ask = shown_topics(data)
        if ask and not onboarding and not self.store.get_state(f"themecheck_asked:{h}"):
            # BN4: asked once, after the first trends answer, never during the setup
            parts.append(T.theme_check_question(ask))
            self.store.set_state(f"themecheck:{h}", {"shown": ask, "at": now_iso(now)})
            self.store.set_state(f"themecheck_asked:{h}", now_iso(now))
        return self.send(h, "\n\n".join(parts))

    # ---------- the answers code reads ----------
    def _attention_reads(self, person, text, now):
        """(True, ref) for a message read here, else (False, None). The theme check and "every export" are answered by
        the next message only; any other message ends them."""
        from .followup import EVERY_EXPORT, TRENDS_ASK
        h = person["handle"]
        check = self.store.get_state(f"themecheck:{h}")
        offer = self.store.get_state(f"trendsoffer:{h}")
        if check:
            got = P.parse_labels(text, check.get("shown") or [])
            if got is not None:
                self.note(intent="theme_check")
                if got["bad"]:   # a number past the list: one question, and the theme check stays open
                    return True, self.send(h, T.theme_check_which(len(check.get("shown") or [])))
                self.store.set_state(f"themecheck:{h}", None)
                self.store.set_state(f"trendsoffer:{h}", None)
                done = P.set_relations(self.store, h, got["pairs"], now=now)
                return True, self.send(h, T.labels_saved(done))
        if offer and EVERY_EXPORT.match(text):
            self.store.set_state(f"trendsoffer:{h}", None)
            self.store.set_state(f"themecheck:{h}", None)
            return True, self._trends_rule(person, text, now)
        if check or offer:   # anything else ends both questions and is answered as usual
            self.store.set_state(f"themecheck:{h}", None)
            self.store.set_state(f"trendsoffer:{h}", None)
        if TRENDS_ASK.match(text):
            return True, self._trends_answer(person, now)
        said = P.relation_said(self.store, h, text)
        if said:
            self.note(intent="theme_check")
            P.set_relations(self.store, h, [said], now=now)
            return True, self.send(h, T.label_changed(*said))
        if P.PARKED_ASK.match(text):
            self.note(intent="parked")
            return True, self.send(h, T.parked_message(P.parked(P.get(self.store, h))))
        return False, None

    def _trends_rule(self, person, text, now):
        """'every export' after a trends answer: a rule that sends the trends message each time a new export comes in,
        built by code (content source "trends"); no model call."""
        from .schema import RuleSpec
        from .store import now_iso
        h = person["handle"]
        self.note(intent="new_rule")
        spec = RuleSpec.model_validate({"when": {"type": "new_items"}, "content": {"source": "trends"}})
        rule_id = self.store.add_rule(h, " ".join(text.split())[:300], spec.stored(), "active", None,
                                      created_at=now_iso(now))
        self._wrote_rule(h, f"saved a rule, \"{spec.content.goal}\"", rule_id)   # "undo" stops it
        return self.send(h, T.trends_rule_started(self.store.rule_number(h, rule_id)))


def main(argv=None):
    """The live check, counts only: python3 -m mvp.attention <library> [--store PATH] [--person N]. Prints the anchor
    dates, the totals, and per stored topic (by its number, never its name) its label and counts, then the seconds the
    counting took once the library is loaded. The store is opened read-only; nothing is written."""
    import argparse
    import json
    import sqlite3
    import time
    from . import config
    from .libview import LibraryView
    ap = argparse.ArgumentParser(description=main.__doc__)
    ap.add_argument("library")
    ap.add_argument("--store", default=config.DB)
    ap.add_argument("--person", type=int, default=1, help="the person's place in the store (1 = the first)")
    a = ap.parse_args(argv)
    t0 = time.time()
    view = LibraryView(a.library)
    loaded = time.time() - t0
    db = sqlite3.connect(f"file:{a.store}?mode=ro", uri=True)
    rows = db.execute("SELECT profile, direction FROM people ORDER BY rowid").fetchall()
    db.close()
    profile, direction = rows[a.person - 1] if len(rows) >= a.person else (None, None)
    interests = [i for i in (json.loads(profile or "{}").get("interests") or []) if isinstance(i, dict)
                 and i.get("topic") and i.get("relation") != "not_me"]
    t1 = time.time()
    data = trends(view, {"interests": interests}, direction)
    took = time.time() - t1
    print("anchors: " + ", ".join(f"{p} {d.isoformat()}" for p, d in sorted(data["anchors"].items())))
    print(f"kept lately: {data['recent_total']}, in the 182 days before: {data['before_total']}")
    names = {t["topic"]: k for k, t in enumerate(data["topics"], 1)}
    for k, t in enumerate(data["topics"], 1):
        print(f"topic {k}: {t['trend']}, lately {t['recent']}, before {t['before']}, liked {t['liked']}, "
              f"label {t['relation'] or '-'}")
    d = data["direction"]
    if d:
        print(f"direction: topic {names.get(d['topic'], '-')}, lately {d['recent']}, before {d['before']}")
    print(f"library loaded in {loaded:.1f} s; counted in {took:.2f} s ({len(view.items)} items, "
          f"{len(view.items) / max(took, 1e-9):.0f} items/s)")


if __name__ == "__main__":
    main()
