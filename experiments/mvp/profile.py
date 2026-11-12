"""PROTOTYPE ONLY - the person's context (DESIGN.md sections 5 and 11, slice 6).

Stored per person on the people row: `profile` (JSON: interests [{topic, share, level, why, quote, confirmed, source,
saved, watched, words, support}]), `direction` (their own words) and `prefs` (avoid, tools, style, outside,
guess_level, exclude_kinds, exclude_platforms). Email, time zone and quiet hours are stored as before.

- The guess: code samples the person's own kept items (saved, sent to self, collections, playlists: the newest and a
  seeded random set, never friends' items, which LibraryView never loads) and their most watched YouTube channels; one
  model call groups them into topics with the lines behind each; code checks every line id, counts the support,
  computes the share, and counts the whole library's matching items. A level stays only with a quote from one of the
  topic's own lines. Topics about health, relationships, money, religion, politics or sexuality are removed by code
  (`sensitive`) whatever the model returned. The guess is cached per library build.
- merge(): what the person says about themselves ("I'm past beginner at Blender now", their answer during onboarding)
  is filled into a form by the model; code validates it and applies it; the reply says what changed.
- about_lines() for the interpreter, composer_context() for the composer, show_text() for "what do you know about me".
No item text or personal text is logged; the model calls go through llm.py.
"""
import hashlib
import json
import os
import random
import re
from datetime import datetime, timezone

from . import config, llm
from .compose import UNSAFE_TEXT, as_data, line_in_text
from .retrieve import _library_stamp, _stem, contains_word, norm

LEVELS = ["new", "beginner", "intermediate", "advanced"]
LEVEL_PLAIN = {"new": "just starting", "beginner": "a beginner", "intermediate": "past the basics",
               "advanced": "advanced"}
KEPT = {"save", "collection", "share_self", "playlist"}
LINE_CHARS = 140

# Never inferred or stored (docs/07): health, relationships, money, religion, politics, sexuality. Checked by code on
# topic names, reasons, words and anything the person's message would put in the profile.
# Fix pass, finding 35: whole words that are personal on their own, and phrases for words that have an everyday sense
# too ("partner workout", "god tier", "trading cards", "keto recipes", "chicken stock", "budget meals" stay allowed).
SENSITIVE = re.compile(
    r"\b(health\w*|medical|medicine|medication\w*|illness\w*|disease\w*|symptom\w*|diagnos\w*|therap\w*|mental|"
    r"anxiety|anxious|depress\w*|adhd|autis\w*|cancer|diabet\w*|pregnan\w*|fertility|ivf|weight[- ]?loss|"
    r"lose weight|losing weight|dieting|eating disorder\w*|disorder\w*|addiction\w*|sobriety|sober|rehab|surgery|"
    r"pills?|relationship\w*|dating|marriage|married|divorc\w*|breakup|break-up|boyfriend|girlfriend|husband|wife|"
    r"sex|sexual\w*|lgbt\w*|gay|lesbian|queer|transgender|bisexual|"
    r"money|financ\w*|invest\w*|crypto\w*|bitcoin|stock market|"
    r"stocks and shares|debt|loans?|budgeting|salary|income|taxes|mortgage|"
    r"religio\w*|church\w*|my faith|pray\w*|bible|quran|koran|islam\w*|muslim\w*|christian\w*|jewish|judaism|"
    r"hindu\w*|buddhis\w*|spiritual\w*|politic\w*|election\w*|democrat\w*|republican\w*|"
    r"voting|vote for|abortion|immigration|immigrants?|deportation|asylum|green card|"
    # checker additions: money, diet and faith words the first list missed (as phrases where a word has another sense)
    r"day trading|stock trading|forex|wealth\w*|millionaires?|retirement (?:savings|planning|fund)|savings|"
    r"side hustles?|passive income|credit (?:cards?|scores?)|real estate|fat[- ]?loss|lose fat|calorie deficit|diets?|"
    r"coming out|my partner|my ex|"
    r"jesus|christ|allah|torah|mosques?|synagogues?|scriptures?|porn\w*|onlyfans|hook-?ups?|tinder)\b", re.I)


def sensitive(*texts):
    return any(t and SENSITIVE.search(str(t)) for t in texts)


def _clean(s, n):
    s = " ".join(str(s or "").split())[:n].strip(" .,;:-")
    return "" if UNSAFE_TEXT.search(s) else s


def _prompt(name):
    return open(os.path.join(config.HERE, "prompts", f"{name}.md"), encoding="utf-8").read()


STOP = set("a an and the of for to in on with my your our this that is it at by from or how what when new best easy "
           "quick simple ideas idea video videos reel reels post posts tutorial tutorials tips tip recipe recipes "
           "beginner beginners guide make making learn learning start starting finish finished ends end whole full "
           "one some more any things thing stuff saved save saves".split())


def topic_words(*texts):
    """The content words of a topic or a request (stems of 3+ letters, no filler)."""
    out = []
    for t in texts:
        for w in re.findall(r"[^\W\d_]+", norm(t or "")):
            s = _stem(w)
            if len(s) >= 3 and s not in STOP and w not in STOP and s not in out:
                out.append(s)
    return out


# ---------- the guess ----------
def sample(view):
    """(items, channels): the newest kept items, then a seeded random set of the rest (the seed is the library build,
    so the same build gives the same sample), and the most watched YouTube channels with their watched videos."""
    kept = [it for it in view.items.values() if it.kinds & KEPT]
    kept.sort(key=lambda it: (it.kept_on() or "", it.id), reverse=True)
    recent = kept[:config.PROFILE_SAMPLE_RECENT]
    rest = sorted(kept[config.PROFILE_SAMPLE_RECENT:], key=lambda it: it.id)
    rnd = random.Random(_library_stamp(view.lib) + ":profile")
    items = recent + rnd.sample(rest, min(config.PROFILE_SAMPLE_RANDOM, len(rest)))
    by = {}
    for it in view.items.values():
        if it.platform == "youtube" and "watch" in it.kinds and it.creator:
            by.setdefault(it.creator, []).append(it)
    chans = sorted(by.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    chans = [(name, sorted(vids, key=lambda it: (it.dates.get("watch") or "", it.id), reverse=True))
             for name, vids in chans if len(vids) >= 3][:config.PROFILE_CHANNELS]
    return items, chans


def _item_text(it):
    return " ".join((it.caption or "").split())


def sample_block(items, chans):
    rows = []
    for i, it in enumerate(items, 1):
        how = "saved" if it.kinds & {"save", "collection"} else ("sent to self" if "share_self" in it.kinds
                                                                  else "in a playlist")
        rows.append(f"S{i}. {it.platform}, {how}: " + as_data(_item_text(it)[:LINE_CHARS] or "(no text)"))
    for j, (name, vids) in enumerate(chans, 1):
        titles = " | ".join(_item_text(v)[:70] for v in vids[:3])
        rows.append(f"C{j}. YouTube channel {as_data(name[:60])}, {len(vids)} videos watched; titles: " + as_data(titles))
    return "\n".join(rows)


def guess_key(view):
    parts = [os.path.abspath(view.lib), _library_stamp(view.lib), config.PROMPT_PROFILE_GUESS, config.MODEL,
             config.PROFILE_SAMPLE_RECENT, config.PROFILE_SAMPLE_RANDOM, config.PROFILE_CHANNELS]
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()


def check_guess(raw, items, chans, view):
    """The code checks on the model's topics (pure). Returns (interests, removed): line ids must be in the sample and
    count once; a topic needs PROFILE_MIN_SUPPORT lines; words must be in its lines; a level needs a quote found in one
    of its lines; a sensitive topic is removed. Shares and library counts are worked out here."""
    ids = {f"S{i}": it for i, it in enumerate(items, 1)}
    cids = {f"C{j}": c for j, c in enumerate(chans, 1)}
    total = max(len(items) + len(chans), 1)
    kept_all = [it for it in view.items.values() if it.kinds & KEPT]
    watched_all = [it for it in view.items.values() if it.platform == "youtube" and "watch" in it.kinds
                   and not it.kinds & KEPT]
    used, out, removed = set(), [], 0
    topics = raw.get("topics") if isinstance(raw, dict) else None
    for t in topics if isinstance(topics, list) else []:
        if not isinstance(t, dict):
            continue
        topic = _clean(t.get("topic"), 40)
        words = [_clean(w, 24).lower() for w in (t.get("words") or []) if isinstance(w, str)]
        why = _clean(t.get("why"), 160)
        if not topic:
            continue
        if sensitive(topic, why, " ".join(words)):
            removed += 1
            continue
        sup, sup_ch = [], []
        for x in t.get("items") or []:
            x = str(x).strip().upper()
            if x in used:
                continue
            if x in ids:
                sup.append(ids[x])
            elif x in cids:
                sup_ch.append(cids[x])
            else:
                continue
            used.add(x)
        support = len(sup) + len(sup_ch)
        if support < config.PROFILE_MIN_SUPPORT:
            continue
        texts = [_item_text(it) for it in sup] + [_item_text(v) for _, vids in sup_ch for v in vids]
        need = min(2, len(texts))
        words = [w for w in dict.fromkeys(words) if len(w) >= 3 and not sensitive(w)
                 and sum(contains_word(tx, w) for tx in texts) >= need][:4]
        saved = {it.id for it in sup}
        if words:
            saved |= {it.id for it in kept_all if any(contains_word(it.caption, w) for w in words)}
        names = {name for name, _ in sup_ch}
        watched = sum(1 for it in watched_all if it.creator in names
                      or (words and any(contains_word(it.caption, w) for w in words)))
        level = t.get("level") if t.get("level") in LEVELS else None
        quote = _clean(t.get("level_quote"), 80)
        if level and not (quote and any(line_in_text(quote, tx) for tx in texts)):
            level, quote = None, ""   # a level needs the topic's own words behind it
        if why and re.search(r"\d|@", why):
            why = ""
        out.append({"topic": topic, "share": round(support / total, 3), "support": support,
                    "support_ids": sorted(it.id for it in sup), "saved": len(saved),
                    "watched": watched, "words": words, "level": level, "quote": quote or None, "why": why or None,
                    "confirmed": False, "source": "guess"})
    out.sort(key=lambda x: (-x["share"], x["topic"].lower()))
    return out[:config.PROFILE_MAX_TOPICS], removed


def guess(view, store=None, handle=None, use_cache=True, now=None):
    """The guess for one library build: ({"interests", "sample", "kept", "removed", "build", "cached"}, cost)."""
    now = now or datetime.now(timezone.utc)
    key = guess_key(view)
    if store is not None and use_cache:
        r = store.one("SELECT result FROM profile_guess WHERE key=?", (key,))
        if r:
            return dict(json.loads(r["result"]), cached=True), 0.0
    items, chans = sample(view)
    kept = sum(1 for it in view.items.values() if it.kinds & KEPT)
    base = {"interests": [], "sample": len(items) + len(chans), "kept": kept, "removed": 0,
            "build": _library_stamp(view.lib), "cached": False}
    if len(items) + len(chans) < config.PROFILE_MIN_SUPPORT:
        return base, 0.0
    user = ("Lines from their library:\n" + sample_block(items, chans))
    raw, cost = llm.chat_json(_prompt(config.PROMPT_PROFILE_GUESS), user, purpose="mvp_profile_guess",
                              prompt_version=config.PROMPT_PROFILE_GUESS, person=handle, max_tokens=1800,
                              temperature=config.PROFILE_TEMPERATURE, seed=config.PROFILE_SEED)
    interests, removed = check_guess(raw, items, chans, view)
    result = dict(base, interests=interests, removed=removed)
    if store is not None:
        from .store import now_iso
        store.x("INSERT OR REPLACE INTO profile_guess(key,library,result,at) VALUES(?,?,?,?)",
                (key, os.path.abspath(view.lib), json.dumps(dict(result, cached=False)), now_iso(now)))
    return result, cost


# ---------- the stored profile ----------
def get(store, handle):
    """Everything the bot knows about the person, in one dict."""
    ctx = store.person_context(handle)
    data = store.profile_data(handle)
    p = store.person(handle) or {}
    email, ok = store.email_of(handle)
    return {"interests": [i for i in data.get("interests") or [] if isinstance(i, dict) and i.get("topic")],
            "direction": ctx.get("direction"), "prefs": ctx.get("prefs") or {}, "notes": ctx.get("notes") or [],
            "email": email, "email_verified": ok, "timezone": p.get("timezone"), "quiet": store.quiet(handle),
            "build": data.get("build"), "guessed": bool(data.get("guessed_at"))}


def set_interests(store, handle, interests, **extra):
    data = store.profile_data(handle)
    data.update(extra)
    data["interests"] = interests
    store.set_profile_data(handle, data)


def adopt_guess(store, handle, result, now=None):
    """The guess becomes the person's interests (unconfirmed), unless they already confirmed or told the bot more:
    what they said is never overwritten by a guess."""
    from .store import now_iso
    have = get(store, handle)["interests"]
    mine = [i for i in have if i.get("confirmed") or i.get("source") != "guess"]
    names = {i["topic"].lower() for i in mine}
    new = mine + [dict(i) for i in result.get("interests") or [] if i["topic"].lower() not in names
                  and not sensitive(i["topic"], i.get("why"), " ".join(i.get("words") or []))]   # an older cached guess
    set_interests(store, handle, new, build=result.get("build"), guessed_at=now_iso(now))
    return new


def level_allowed(interest, prefs):
    """A level may be used (and said) when the person confirmed it, or when it is a guess backed by a quote and they
    have not asked the bot to stop guessing."""
    if not interest or not interest.get("level"):
        return False
    if interest.get("confirmed") or interest.get("source") in ("person", "feedback"):
        return True
    return bool(interest.get("quote")) and prefs.get("guess_level", True) is not False


def match_topic(prof, *texts):
    """The interest a request is about: the one whose topic words (or checked words) appear in the text, most first."""
    have = set()
    for t in texts:
        have |= {_stem(w) for w in re.findall(r"[^\W\d_]+", norm(t or ""))}
    best, score = None, 0
    for i in prof.get("interests") or []:
        words = set(topic_words(i["topic"])) | {_stem(w) for w in i.get("words") or []}
        s = len(words & have)
        if s > score:
            best, score = i, s
    return best


def _level_text(i, prefs):
    if not i.get("level"):
        return None
    if i.get("confirmed") or i.get("source") in ("person", "feedback"):
        return i["level"]
    return f"{i['level']}, a guess" if level_allowed(i, prefs) else None


def _about(i, words):
    """True when the message is about this interest: one of its topic words (or its checked words) is in it."""
    return bool((set(topic_words(i["topic"])) | {_stem(w) for w in i.get("words") or []}) & words)


def about_lines(store, handle, message=None):
    """For the interpreter: the profile in the evaluation set's shape, then what they said about themselves.

    With the message, code keeps only what the message is about (DESIGN.md section 5: the profile fills criteria,
    avoid and level only for a request on a topic in the profile): the interests whose words are in the message, and
    the direction only when it shares a word with it. A level the message states itself always wins, so the profile's
    level is left out then. Preferences and their own notes are always given, as before."""
    prof = get(store, handle)
    prefs = prof["prefs"]
    interests = prof["interests"]
    direction = prof["direction"]
    named_level = False
    if message is not None:
        words = set(topic_words(message))
        interests = [i for i in interests if _about(i, words)]
        if direction and not (set(topic_words(direction)) & words):
            direction = None
        named_level = bool(LEVEL_ASKED.search(message))
    lines = []
    if interests:
        parts = []
        for i in interests:
            lv = None if named_level else _level_text(i, prefs)
            parts.append(f"{i['topic']} ({lv})" if lv else i["topic"])
        lines.append("Interests: " + ", ".join(parts) + ".")
    if direction:
        lines.append(f"Direction, in their words: \"{' '.join(direction.split())[:300]}\".")
    p = pref_words(prefs)
    if lines or p:
        lines.append("Preferences: " + ("; ".join(p) if p else "none given") + ".")
    return lines + list(prof["notes"])


# the kinds of their library in plain words ("don't use my likes": "I won't use your likes")
KIND_PLAIN = {"save": "saves", "collection": "collections", "share_self": "posts sent to yourself",
              "playlist": "playlists", "like": "likes", "watch": "watch history", "view": "views"}
PLATFORM_PLAIN = {"instagram": "Instagram", "youtube": "YouTube"}


def _plain(key, vals):
    names = KIND_PLAIN if key == "exclude_kinds" else PLATFORM_PLAIN
    return [names.get(v, v) for v in vals]


def pref_words(prefs):
    out = []
    if prefs.get("avoid"):
        out.append("avoid " + ", ".join(prefs["avoid"]))
    if prefs.get("tools"):
        out.append("has " + ", ".join(prefs["tools"]))
    if prefs.get("style") in ("brief", "full"):
        out.append("brief answers" if prefs["style"] == "brief" else "full answers")
    if prefs.get("outside") is True:
        out.append("wants new things from outside their saves too")
    if prefs.get("exclude_kinds"):
        out.append("never use their " + ", ".join(_plain("exclude_kinds", prefs["exclude_kinds"])))
    if prefs.get("exclude_platforms"):
        out.append("never use " + ", ".join(_plain("exclude_platforms", prefs["exclude_platforms"])))
    return out


LEVEL_ASKED = re.compile(r"\b(beginners?|newbies?|novice|first[- ]time|intermediate|advanced|experienced|"
                         r"just start\w*|starting out|new to)\b", re.I)


def composer_context(store, handle, *texts):
    """(text, level_ok, guessed): what the composer may use about the person for this request (direction, their level
    at the request's topic when it may be used, preferences, notes); whether "because" may mention a level; and the
    interest whose level is only a guess (code then says once that it is a guess)."""
    prof = get(store, handle)
    prefs = prof["prefs"]
    lines = []
    if prof["direction"]:
        lines.append("What they are working toward: " + " ".join(str(prof["direction"]).split())[:300])
    m = match_topic(prof, *texts)
    ok = level_allowed(m, prefs)
    if ok:
        how = "they told you" if (m.get("confirmed") or m.get("source") != "guess") else "a guess from what they saved"
        lines.append(f"Their level at {m['topic']}: {LEVEL_PLAIN[m['level']]} ({how})")
    p = pref_words({k: v for k, v in prefs.items() if k in ("avoid", "tools", "style")})
    if p:
        lines.append("Preferences: " + "; ".join(p))
    lines.extend(prof["notes"])
    asked = any(LEVEL_ASKED.search(t or "") for t in texts)
    guessed = m if ok and not (m.get("confirmed") or m.get("source") != "guess") else None
    return "\n".join(lines), bool(ok or asked), guessed


# ---------- what the person says about themselves ----------
def _find(interests, name):
    n = norm(name)
    if not n:
        return None
    for i in interests:
        if norm(i["topic"]) == n:
            return i
    words = set(topic_words(name))
    best, score = None, 0
    for i in interests:
        s = len(words & (set(topic_words(i["topic"])) | {_stem(w) for w in i.get("words") or []}))
        if s > score:
            best, score = i, s
    return best


def _strs(v, n=8, size=40):
    if isinstance(v, str):
        v = [v]
    return [s for s in (_clean(x, size) for x in (v or []) if isinstance(x, str)) if s][:n]


def merge(store, handle, message, asked=None, person=None, shown=None):
    """One model call fills the form; apply_merge() checks and applies it. Returns (result, cost); result is
    apply_merge's."""
    prof = get(store, handle)
    known = {"topics": [{"topic": i["topic"], "level": i.get("level"), "confirmed": bool(i.get("confirmed"))}
                        for i in prof["interests"]],
             "direction": prof["direction"], "preferences": pref_words(prof["prefs"])}
    user = ("What the bot knows now: " + json.dumps(known, ensure_ascii=False)
            + ("\nWhat the bot had just asked them: " + asked if asked else
               "\nThe bot had not asked them anything: this is something they said.")
            + "\n\nTheir message:\n<message>" + message.replace("<", "‹").replace(">", "›")[:1000] + "</message>")
    raw, cost = llm.chat_json(_prompt(config.PROMPT_PROFILE_MERGE), user, purpose="mvp_profile_merge",
                              prompt_version=config.PROMPT_PROFILE_MERGE, person=person or handle, max_tokens=700,
                              temperature=config.PROFILE_TEMPERATURE, seed=config.PROFILE_SEED)
    return apply_merge(store, handle, raw, message, shown=shown), cost


def apply_merge(store, handle, raw, message, shown=None):
    """Validates the model's form against the message and the stored profile and applies it. Returns {"kind",
    "changes": [plain lines], "other": [the lines short_summary() does not cover], "skipped_sensitive": bool}. Levels and topics must name a stored topic or use the person's
    own words; direction and tools must be their own words; anything sensitive is left out (and said)."""
    from .interpret import own_words
    from .schema import KINDS, PLATFORMS
    raw = raw if isinstance(raw, dict) else {}
    kind = raw.get("kind") if raw.get("kind") in ("about_me", "request", "both") else "about_me"
    prof = get(store, handle)
    interests = [dict(i) for i in prof["interests"]]
    prefs = dict(prof["prefs"])
    changes, skipped = [], False
    other = []   # the changes short_summary() does not show (onboarding step 3 says these too)
    for name in _strs(raw.get("drop_topics")):
        i = _find(interests, name)
        if i:
            interests.remove(i)
            changes.append(f"{i['topic']} is off your interests")
            other.append(changes[-1])
    # "that's right" confirms what the person was shown (the read shows at most 4 topics), never a topic they did not see
    seen = None if shown is None else {t.lower() for t in shown}
    confirm = [i for i in interests if raw.get("confirm_all") is True and (seen is None or i["topic"].lower() in seen)]
    confirm += [i for i in (_find(interests, n) for n in _strs(raw.get("confirm_topics"))) if i and i not in confirm]
    if any(not i.get("confirmed") for i in confirm):
        for i in confirm:
            i["confirmed"] = True
        changes.append("you confirmed " + _and([i["topic"] for i in confirm]))
    for lv in raw.get("levels") or []:
        if not isinstance(lv, dict) or lv.get("level") not in LEVELS:
            continue
        name = _clean(lv.get("topic"), 40)
        i = _find(interests, name) if name else None
        if i is None:
            if not name or sensitive(name) or not own_words(name, message):
                skipped = skipped or sensitive(name)
                continue
            i = {"topic": name, "share": 0.0, "support": 0, "saved": 0, "watched": 0, "words": topic_words(name)[:3],
                 "level": None, "quote": None, "why": None, "confirmed": True, "source": "person"}
            interests.append(i)
        if i.get("level") != lv["level"] or not i.get("confirmed") or i.get("source") == "guess":
            i.update(level=lv["level"], confirmed=True, source="person")
            changes.append(f"{i['topic']}: {LEVEL_PLAIN[lv['level']]}")
            _drop_notes_about(store, handle, i)
    for name in _strs(raw.get("add_topics"), 4):
        if sensitive(name):
            skipped = True
            continue
        if _find(interests, name) or not own_words(name, message):
            continue
        interests.append({"topic": name, "share": 0.0, "support": 0, "saved": 0, "watched": 0,
                          "words": topic_words(name)[:3], "level": None, "quote": None, "why": None,
                          "confirmed": True, "source": "person"})
        changes.append(f"you're into {name}")
    d = _clean(raw.get("direction"), 240)
    if d:
        if sensitive(d):
            skipped = True
        elif own_words(d, message) and d != prof["direction"]:
            store.set_direction(handle, d)
            changes.append(f"you're working toward \"{d}\"")
    for key, word in (("avoid", "you'd rather avoid"), ("tools", "you have")):
        vals = _strs(raw.get(key), 6, 30)
        bad = [v for v in vals if sensitive(v)]
        skipped = skipped or bool(bad)
        vals = [v for v in vals if v not in bad and (key == "avoid" or own_words(v, message))]
        new = [v for v in vals if v.lower() not in {x.lower() for x in prefs.get(key) or []}]
        if new:
            prefs[key] = (list(prefs.get(key) or []) + new)[-10:]
            changes.append(f"{word} {_and(new)}")
            other.append(changes[-1])
    if raw.get("style") in ("brief", "full") and prefs.get("style") != raw["style"]:
        prefs["style"] = raw["style"]
        changes.append("you like brief answers" if raw["style"] == "brief" else "you like full answers")
        other.append(changes[-1])
    if isinstance(raw.get("outside"), bool) and prefs.get("outside") is not raw["outside"]:
        prefs["outside"] = raw["outside"]
        changes.append("I'll add new things from outside your saves" if raw["outside"]
                       else "I'll stick to your own saves")
        other.append(changes[-1])
    if isinstance(raw.get("stop_guessing_level"), bool):
        want = not raw["stop_guessing_level"]
        if prefs.get("guess_level", True) is not want:
            prefs["guess_level"] = want
            changes.append("I'll stop guessing your level" if not want else "I'll guess your level again")
            other.append(changes[-1])
    for key, allowed in (("exclude_kinds", KINDS), ("exclude_platforms", PLATFORMS)):
        vals = [v for v in _strs(raw.get(key), 7, 20) if v in allowed]
        new = [v for v in vals if v not in (prefs.get(key) or [])]
        if new:
            prefs[key] = list(prefs.get(key) or []) + new
            changes.append(("I won't use your " if key == "exclude_kinds" else "I won't use ") + _and(_plain(key, new)))
            other.append(changes[-1])
    note = _clean(raw.get("note"), 120)
    if note:
        if sensitive(note):
            skipped = True
        elif note.lower() not in {n.lower() for n in store.profile_notes(handle)}:
            store.add_profile_note(handle, note)
            changes.append(f"noted: {note}")
            other.append(changes[-1])
    set_interests(store, handle, interests)
    store.x("UPDATE people SET prefs=? WHERE handle=?", (json.dumps(prefs), handle))
    return {"kind": kind, "changes": changes, "other": other, "skipped_sensitive": skipped}


def _drop_notes_about(store, handle, interest):
    """An older note about a topic whose level the person just gave ("I'm a beginner at Blender") would contradict it."""
    words = topic_words(interest["topic"])
    ids = [r["id"] for r in store.profile_note_rows(handle, limit=50)
           if words and any(contains_word(r["text"], w) for w in words)]
    store.drop_profile_notes(handle, ids)


def move_level(store, handle, topic_text, way):
    """Feedback "too hard" / "too easy": the matched topic's level moves one step (and counts as theirs). Returns
    (interest, new_level) or (None, None) when no topic matches."""
    prof = get(store, handle)
    interests = [dict(i) for i in prof["interests"]]
    m = match_topic({"interests": interests}, topic_text)
    if m is None:
        return None, None
    i = next(x for x in interests if x["topic"] == m["topic"])
    cur = i.get("level")
    if cur is None:
        new = "intermediate" if way == "harder" else "beginner"
    else:
        k = LEVELS.index(cur) + (1 if way == "harder" else -1)
        new = LEVELS[max(0, min(k, len(LEVELS) - 1))]
    i.update(level=new, confirmed=True, source="feedback")
    set_interests(store, handle, interests)
    return i, new


# ---------- in plain words ----------
def _and(xs):
    xs = list(xs)
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def about_count(n):
    """'about 40' for a count worked out by code: exact up to 20, then to the nearest 5 (10 past 100)."""
    if n <= 20:
        return str(n)
    step = 10 if n > 100 else 5
    return f"about {int(round(n / step) * step)}"


def count_words(i):
    """'about 40 saved posts and 12 watched videos': the counts code worked out for the topic."""
    parts = []
    if i.get("saved"):
        parts.append(f"{about_count(i['saved'])} saved {'post' if i['saved'] == 1 else 'posts'}")
    if i.get("watched"):
        parts.append(f"{about_count(i['watched'])} watched {'video' if i['watched'] == 1 else 'videos'}")
    return " and ".join(parts)


def read_lines(prof, limit=4):
    """The read of the person for onboarding: one short line per main interest, with the guessed level in plain words
    and the count behind it."""
    out = []
    for i in prof["interests"][:limit]:
        lv = i.get("level") if level_allowed(i, prof["prefs"]) else None
        level = {"new": "you look new to it", "beginner": "you look like a beginner",
                 "intermediate": "you look past the basics", "advanced": "you look advanced"}.get(lv)
        n = count_words(i)
        line = f"• {i['topic']}" + (f": {level}" if level else "") + (f" ({n})" if n else "")
        out.append(line)
    return out


def short_summary(prof):
    """One or two lines of what the bot now knows (onboarding step 3)."""
    parts = []
    for i in prof["interests"][:4]:
        lv = i.get("level") if level_allowed(i, prof["prefs"]) else None
        parts.append(f"{i['topic']}" + (f" ({LEVEL_PLAIN[lv]})" if lv else ""))
    lines = []
    if parts:
        lines.append("You're into " + _and(parts) + ".")
    if prof["direction"]:
        lines.append(f"You're working toward \"{prof['direction']}\".")
    return " ".join(lines)


def show_text(prof, now=None):
    """'What do you know about me': the profile in plain words, and how to correct it."""
    from . import texts as T
    lines = ["Here's what I know about you:"]
    prefs = prof["prefs"]
    for i in prof["interests"]:
        lv = i.get("level")
        if lv and (i.get("confirmed") or i.get("source") != "guess"):
            how = f"{LEVEL_PLAIN[lv]}, you told me"
        elif lv and level_allowed(i, prefs):
            how = f"{LEVEL_PLAIN[lv]}, my guess"
        else:
            how = "you told me" if i.get("source") != "guess" else ("you confirmed it" if i.get("confirmed")
                                                                    else "my guess")
        n = count_words(i) if i.get("source") == "guess" else ""
        lines.append(f"• {i['topic']} ({how}" + (f", from {n}" if n else "") + ")")
    if not prof["interests"]:
        lines.append("• No interests yet.")
    if prof["direction"]:
        lines.append(f"You're working toward: \"{prof['direction']}\".")
    p = []
    if prefs.get("tools"):
        p.append("you have " + _and(prefs["tools"]))
    if prefs.get("avoid"):
        p.append("you'd rather avoid " + _and(prefs["avoid"]))
    if prefs.get("style") in ("brief", "full"):
        p.append(f"you like {prefs['style']} answers")
    if prefs.get("outside") is True:
        p.append("you want new things from outside your saves too")
    if prefs.get("guess_level") is False:
        p.append("I don't guess your level")
    if prefs.get("exclude_kinds"):
        p.append("I don't use your " + _and(_plain("exclude_kinds", prefs["exclude_kinds"])))
    if prefs.get("exclude_platforms"):
        p.append("I don't use " + _and(_plain("exclude_platforms", prefs["exclude_platforms"])))
    if p:
        lines.append(T.cap_first("; ".join(p)) + ".")
    if prof["notes"]:
        lines.append("Things you told me: " + "; ".join(prof["notes"]) + ".")
    if prof["email"]:
        lines.append(f"Email: {prof['email']} ({'confirmed' if prof['email_verified'] else 'not confirmed yet'}).")
    else:
        lines.append("Email: none yet.")
    if prof["timezone"]:
        lines.append(f"Time zone: {T.zone_name(prof['timezone'])}. Quiet hours: {T.quiet_words(prof['quiet'])}.")
    lines.append(T.PROFILE_HOW_TO_CORRECT)
    return "\n".join(lines)
