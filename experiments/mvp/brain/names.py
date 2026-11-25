"""PROTOTYPE ONLY - a name they use, resolved to a ref by code (design/brain_v1/SPEC.md 2.2, 2.5), step 1.

The resolve order, first match wins, each match saying how it was read:
1. their own words (a vocabulary of step 3 and later: empty here);
2. an area word: an area's name or plural, or an alias of it        -> area:<slug>        "area name"
3. a theme's shown name (case and plural folded); an area word wins   -> theme:<id>         "theme name"
4. a channel's name (history.channel_of)                              -> channel:<key>      "channel name"
5. a collection's or a playlist's name                                -> collection:<slug>  "collection name"
6. theme words: every content word in exactly one theme's name/words  -> theme:<id>         "theme words"
   (in two or more: ambiguous)
7. title words: at least 20 items hold the words in their own text    -> words:<text>       "title words"
8. none: up to 3 options by spelling and by meaning.
Ambiguous and no match carry options and never a number: a closest match is an option, never a count. Sensitive
themes, channels and items are never a match, nor an option, unless the turn's unlock is their topic.
"""
import difflib
import re

from .. import facts as F
from .. import history as Hm
from .. import themes as T

TITLE_WORDS_MIN = 20
OPTIONS_MAX = 3
SENSITIVE_CHANNEL = 0.5     # a channel with at least this share of its items hidden is hidden too
GENERIC = re.compile(r"\s+(?:videos?|stuff|content|posts?|reels?|things)$")
# the code-owned aliases: a word a person uses for an area (themes.CATEGORY_WORDS has more)
ALIASES = {"gaming": ("games", "video games", "videogames", "gamer", "gameplay", "game", "esports", "streams"),
           "art and design": ("art", "arts", "drawing", "painting", "design", "artwork", "illustration", "sketching"),
           "food and cooking": ("food", "cooking", "recipes", "recipe", "baking", "cook", "meals", "cuisine"),
           "music": ("music", "songs", "musicians", "concerts"),
           "comedy": ("comedy", "funny", "humor", "humour", "standup", "stand-up", "sketches"),
           "film and tv": ("movies", "films", "film", "tv", "shows", "series", "television", "cinema"),
           "sports": ("sports", "sport", "football", "soccer", "basketball"),
           "fitness": ("fitness", "workouts", "workout", "gym", "exercise", "training"),
           "travel": ("travel", "trips", "traveling", "travelling"),
           "science": ("science", "physics", "chemistry", "biology"),
           "technology": ("tech", "technology", "coding", "programming", "gadgets", "computers"),
           "math": ("math", "maths", "mathematics"),
           "education": ("education", "learning", "studying", "lessons"),
           "history": ("history",),
           "nature and animals": ("nature", "animals", "pets", "dogs", "cats", "wildlife"),
           "family and kids": ("family", "kids", "parenting"),
           "fashion and beauty": ("fashion", "beauty", "makeup", "skincare", "outfits"),
           "vehicles": ("cars", "vehicles", "motorbikes", "trucks"),
           "diy and making": ("diy", "making", "crafts", "woodworking", "maker"),
           "internet culture": ("memes", "internet culture"),
           "news": ("news",)}


class Lib:
    """One person's library as the tools read it: the view, the record, facts' index, and which items are hidden
    (friends' posts are not in the view at all; sensitive items unless the turn's unlock is their topic)."""

    def __init__(self, bot, person, unlock=None):
        self.tz = person.get("timezone") or "UTC"
        self.view = bot.view(person["library"])
        self.rec = Hm.record(self.view, self.tz)
        self.idx, self.facts = F.index(self.view, self.tz)
        self.unlock = unlock
        self.hidden = F.sensitive_items(self.view, self.idx, self.facts, unlock)[0]
        self._memo = {}

    def visible_ids(self):
        return {i for k, i in enumerate(self.idx.ids) if not self.hidden[k]}

    def is_visible(self, iid):
        k = self.idx.pos.get(iid)
        return k is not None and not bool(self.hidden[k])


def fold(name):
    t = Hm.strip_accents(" ".join(str(name or "").lower().split())).strip(" .,!?\"'")
    return GENERIC.sub("", t)


def _plural(t):
    return {t, t[:-1] if t.endswith("s") and len(t) > 3 else t + "s"}


def _area_words(lib):
    """{folded word: (area shown name, how)} for the areas this library has (never a sensitive one)."""
    if "areas" in lib._memo:
        return lib._memo["areas"]
    out = {}
    for shown in lib.facts.area_names:
        cat = next((c for c in T.CATEGORIES if F.AREA_SHOWN.get(c, c) == shown), shown)
        if cat in T.SENSITIVE_CATEGORIES:
            continue
        words = {cat, shown.lower()} | set(T.CATEGORY_WORDS.get(cat, ())) | set(ALIASES.get(cat, ()))
        for w in words:
            for p in _plural(fold(w)):
                out.setdefault(p, shown)
    lib._memo["areas"] = out
    return out


def _themes(lib):
    """[(canon theme id, shown name, words)] of the themes that may be named (never a sensitive one)."""
    if "themes" in lib._memo:
        return lib._memo["themes"]
    th = lib.facts.th
    out = []
    if th is not None:
        for tid in sorted(set(lib.facts.canon.values())):
            nm = th.shown(tid)
            meta = th.themes.get(tid) or {}
            cat = meta.get("category") or (th.fields.get(meta.get("field")) or {}).get("category")
            if nm and cat not in T.SENSITIVE_CATEGORIES:
                out.append((int(tid), nm, list(meta.get("words") or [])))
    lib._memo["themes"] = out
    return out


def _channels(lib):
    """{channel name: hidden?} over the library's creators."""
    if "channels" in lib._memo:
        return lib._memo["channels"]
    import numpy as np
    idx = lib.idx
    n = len(idx.creators)
    has = idx.creator >= 0
    total = np.bincount(idx.creator[has], minlength=n)
    hid = np.bincount(idx.creator[has], weights=lib.hidden[has].astype(np.float64), minlength=n)
    out = {}
    for cid, name in enumerate(idx.creators):
        out[name] = bool(total[cid]) and hid[cid] / total[cid] >= SENSITIVE_CHANNEL
    lib._memo["channels"] = out
    return out


def _collections(lib):
    """{folded name: shown name} of the playlists and collections their visible items sit in."""
    if "collections" in lib._memo:
        return lib._memo["collections"]
    out = {}
    for k, i in enumerate(lib.idx.ids):
        if lib.hidden[k]:
            continue
        for c in lib.view.items[i].collections or []:
            out.setdefault(fold(c), c)
    lib._memo["collections"] = out
    return out


def displays(lib):
    """{creator: display name} of the Instagram accounts whose export gives a name of their own (toolfix 7: a row
    named only by its handle, which an answer never prints). A display name that is another creator's name, or
    another account's display name too, is not used: the handle stays the row's name."""
    if "displays" in lib._memo:
        return lib._memo["displays"]
    seen = {}
    for it in lib.view.items.values():
        d = getattr(it, "display", None)
        if d and it.creator and it.creator.startswith("@"):
            seen.setdefault(it.creator, d)
    taken = {Hm._squash(c) for c in lib.idx.creators}
    counts = {}
    for d in seen.values():
        counts[Hm._squash(d)] = counts.get(Hm._squash(d), 0) + 1
    out = {c: d for c, d in seen.items() if Hm._squash(d) not in taken and counts[Hm._squash(d)] == 1}
    lib._memo["displays"] = out
    return out


def topic_ref(lib):
    """The ref of the topic the turn's own message unlocked (toolfix 2), else None."""
    return f"topic:{lib.unlock}" if lib.unlock else None


def words_count(lib, name):
    """Toolfix 6 (a no-match had no cell, so "nothing called X in your history" could not be checked): (the words
    searched, how many of their items, opened, liked or saved, ever, hold them in their own text), or None for a name
    of a sensitive topic their message did not unlock (never a count of private titles) and for a typed ref."""
    import numpy as np
    raw = " ".join(str(name or "").split())
    if not raw or len(raw) > 80 or re.match(r"^(?:area|theme|channel|collection|words|topic):", raw):
        return None
    from .. import outside as O
    topic = O.sensitive_topic([raw])
    if topic and topic != lib.unlock:
        return None
    t = fold(raw)
    words = " ".join(_content_words(t)) or t
    have = np.zeros(len(lib.idx.ids), bool)
    have[np.unique(lib.idx.it)] = True
    n = sum(1 for k, i in enumerate(lib.idx.ids) if have[k] and not lib.hidden[k]
            and Hm.holds(lib.view.items[i].caption or "", words))
    return words, int(n)


def area_ref(shown):
    return "area:" + F.slug(shown)


def items_all_time(lib, ref):
    """How many of their visible items (opened, liked or saved, any time) the ref names."""
    import numpy as np
    m = F.ref_mask(lib.view, lib.idx, lib.facts, ref) & ~lib.hidden
    have = np.zeros(len(lib.idx.ids), bool)
    have[np.unique(lib.idx.it)] = True
    return int((m & have).sum())


def _label(lib, ref):
    form, _, val = ref.partition(":")
    if form == "area":
        return next((a for a in lib.facts.area_names if F.slug(a) == val), val)
    if form == "theme":
        return next((nm for t, nm, _w in _themes(lib) if str(t) == val), val)
    if form == "channel":
        c = next((c for c in lib.idx.creators if F.channel_key(c) == val), val)
        return displays(lib).get(c, c)
    if form == "collection":
        return next((c for c in _collections(lib).values() if F.slug(c) == val), val)
    return val


def _parent(lib, ref):
    """A theme's area; a channel's main theme."""
    form, _, val = ref.partition(":")
    th = lib.facts.th
    if form == "theme" and th is not None:
        a = F.theme_area(th, int(val))
        return area_ref(a) if a else None
    if form == "channel":
        import numpy as np
        from collections import Counter
        cids = [k for k, c in enumerate(lib.idx.creators) if F.channel_key(c) == val]
        mem = np.nonzero(np.isin(lib.idx.creator, cids) & ~lib.hidden)[0]
        tc = Counter(int(t) for t in lib.facts.theme[mem] if t >= 0)
        return f"theme:{tc.most_common(1)[0][0]}" if tc else None
    return None


def _match(lib, ref, how):
    return {"ref": ref, "label": _label(lib, ref), "how": how, "items_all_time": items_all_time(lib, ref),
            "parent": _parent(lib, ref)}


def _option(lib, ref, how):
    """An option never carries a number (a closest match is never a count)."""
    return {"ref": ref, "label": _label(lib, ref), "how": how}


def valid_ref(lib, ref):
    """A typed ref that names something they may see, else None."""
    form, _, val = (ref or "").partition(":")
    if not val:
        return None
    if form == "area":
        return ref if any(F.slug(a) == val for a in set(_area_words(lib).values())) else None
    if form == "theme":
        return ref if any(str(t) == val for t, _n, _w in _themes(lib)) else None
    if form == "channel":
        return ref if any(F.channel_key(c) == val and not hid for c, hid in _channels(lib).items()) else None
    if form == "collection":
        return ref if any(F.slug(c) == val for c in _collections(lib).values()) else None
    if form == "words":
        return ref if 2 <= len(val.strip()) <= 60 else None
    if form == "topic":
        return ref if ref == topic_ref(lib) else None
    return None


def _content_words(t):
    return [w for w in re.findall(r"[a-z0-9]+", t) if w not in Hm.STOP and len(w) > 1]


def _title_items(lib, phrase):
    return sum(1 for k, i in enumerate(lib.idx.ids) if not lib.hidden[k]
               and Hm.holds(lib.view.items[i].caption or "", phrase))


def _options(lib, name):
    """Up to 3 nearest names: by spelling over every name they may see, then by meaning (the stored item vectors,
    history.topic_fit: no model call)."""
    index = {}
    for w, shown in _area_words(lib).items():
        index.setdefault(w, area_ref(shown))
    for tid, nm, _w in _themes(lib):
        index.setdefault(fold(nm), f"theme:{tid}")
    for c, hid in _channels(lib).items():
        if not hid:
            index.setdefault(fold(c), "channel:" + F.channel_key(c))
    for f_, c in _collections(lib).items():
        index.setdefault(f_, "collection:" + F.slug(c))
    out, seen = [], set()
    for w in difflib.get_close_matches(fold(name), list(index), n=OPTIONS_MAX, cutoff=0.6):
        if index[w] not in seen:
            seen.add(index[w])
            out.append(_option(lib, index[w], "close spelling"))
    if len(out) < OPTIONS_MAX:
        try:
            fit = Hm.topic_fit(lib.view, lib.rec, fold(name))
        except Exception:  # noqa: BLE001 - the meaning is extra; spelling stands without it
            fit = None
        if fit is not None and lib.facts.th is not None:
            from collections import Counter
            scores, cut = fit
            allowed = {t for t, _n, _w in _themes(lib)}
            c = Counter()
            for i, s in scores.items():
                k = lib.idx.pos.get(i)
                if s >= cut and k is not None and not lib.hidden[k] and int(lib.facts.theme[k]) in allowed:
                    c[int(lib.facts.theme[k])] += 1
            for tid, _n in c.most_common(OPTIONS_MAX):
                ref = f"theme:{tid}"
                if ref not in seen and len(out) < OPTIONS_MAX:
                    seen.add(ref)
                    out.append(_option(lib, ref, "closest meaning"))
    return out


def resolve_one(lib, name, kinds=()):
    """{"name", "status": "ok"|"ambiguous"|"no_match", "matches": [...], "options": [...], "also": [...]}.
    `kinds`: the forms asked for (area, theme, channel, collection, words); empty = all."""
    kinds = set(kinds or ("area", "theme", "channel", "collection", "words"))
    out = {"name": name, "status": "no_match", "matches": [], "options": [], "also": []}
    raw = " ".join(str(name or "").split())
    if not raw or len(raw) > 80:
        return out
    from .. import outside as O
    topic = O.sensitive_topic([raw])
    if topic and topic != lib.unlock:
        # step 1 fix (the tools audit: find("dating") gave words:dating with 33 items while no message had unlocked
        # the topic, so the counts of a private topic could be read through title words): a name in a sensitive topic
        # resolves only when their own message unlocked that topic; no options, no count
        return out
    # a typed ref ("area:gaming", "theme:3") is checked, never trusted
    if re.match(r"^(?:area|theme|channel|collection|words|topic):", raw):
        ref = valid_ref(lib, raw)
        form = (ref or "").split(":", 1)[0]
        if ref and (form in kinds or (form == "topic" and kinds & {"area", "theme"})):
            out.update(status="ok", matches=[_match(lib, ref, "ref")])
        elif not raw.startswith("topic:"):
            out["options"] = _options(lib, raw.split(":", 1)[1])
        return out
    t = fold(raw)
    if topic and topic == lib.unlock and kinds & {"area", "theme"}:
        # toolfix 2 (held-out I02.0: "dating advice" was no_match on a turn that unlocked it, so the model said there
        # was no such theme while 50 of 58 videos were of it): a name in the topic their message unlocked is that
        # topic (its theme has no name in the build), unless it is a channel's own name
        ch = Hm.channel_of(lib.view, raw)
        if not (ch and "channel" in kinds and not _channels(lib).get(ch, True)):
            out.update(status="ok", matches=[_match(lib, topic_ref(lib), "private topic")])
            return out
    # 1. their own words: a vocabulary of step 3 and later (empty in the first version)
    # 2. an area word
    areas = _area_words(lib)
    theme_by_name = {}
    for tid, nm, _w in _themes(lib):
        for p in _plural(fold(nm)):
            theme_by_name.setdefault(p, tid)
    hit_area = next((areas[p] for p in _plural(t) if p in areas), None)
    hit_theme = next((theme_by_name[p] for p in _plural(t) if p in theme_by_name), None)
    if hit_area and "area" in kinds:
        out.update(status="ok", matches=[_match(lib, area_ref(hit_area), "area name")])
        if hit_theme is not None:
            out["also"] = [_option(lib, f"theme:{hit_theme}", "theme name")]
        return out
    # 3. a theme's shown name
    if hit_theme is not None and "theme" in kinds:
        out.update(status="ok", matches=[_match(lib, f"theme:{hit_theme}", "theme name")])
        return out
    # 4. a channel's name
    if "channel" in kinds:
        ch = Hm.channel_of(lib.view, raw)
        if not ch:   # toolfix 7: an Instagram account by its display name
            ch = next((c for c, d in displays(lib).items() if Hm._squash(d) == Hm._squash(raw)), None)
        if ch and not _channels(lib).get(ch, True):
            out.update(status="ok", matches=[_match(lib, "channel:" + F.channel_key(ch), "channel name")])
            return out
    # 5. a collection or a playlist
    if "collection" in kinds and t in _collections(lib):
        out.update(status="ok", matches=[_match(lib, "collection:" + F.slug(_collections(lib)[t]),
                                                "collection name")])
        return out
    # 6. theme words
    words = _content_words(t)
    if words and "theme" in kinds:
        hits = [tid for tid, nm, ws in _themes(lib)
                if all(Hm.holds(nm + " . " + " . ".join(ws), w) for w in words)]
        if len(hits) == 1:
            out.update(status="ok", matches=[_match(lib, f"theme:{hits[0]}", "theme words")])
            return out
        if len(hits) > 1:
            out.update(status="ambiguous", options=[_option(lib, f"theme:{h}", "theme words") for h in hits])
            return out
    # 7. title words
    if words and "words" in kinds and _title_items(lib, " ".join(words)) >= TITLE_WORDS_MIN:
        out.update(status="ok", matches=[_match(lib, "words:" + " ".join(words), "title words")])
        return out
    # 8. none
    out["options"] = _options(lib, raw)
    return out
