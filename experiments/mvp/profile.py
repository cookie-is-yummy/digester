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
# fix pass 2, finding 41: what the person chose to keep weighs far more than what they watched. Saves, collections
# and posts sent to themselves fill most of the sample; likes and playlists a smaller part; watch history only the
# few channels they watch most.
CHOSEN = {"save", "collection", "share_self"}
LIKED = {"like", "playlist"}
LINE_CHARS = 140

# Never inferred or stored (docs/07): health, relationships, money, religion, politics, sexuality. Checked by code on
# topic names, reasons, words and anything the person's message would put in the profile.
# Fix pass, finding 35: whole words that are personal on their own, and phrases for words that have an everyday sense
# too ("partner workout", "god tier", "trading cards", "keto recipes", "chicken stock", "budget meals" stay allowed).
SENSITIVE = re.compile(
    r"\b(health(?!y\b|ier\b|iest\b)\w*|chemo\w*|trump|biden|harris|medical|medicine|medication\w*|illness\w*|disease\w*|symptom\w*|diagnos\w*|therap\w*|mental|"
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
    r"jesus|christ|allah|torah|mosques?|synagogues?|scriptures?|porn\w*|onlyfans|hook-?ups?|tinder|"
    # review fix PRIV-4: religious observances, named conditions and gender words the lists above missed
    r"ramadan|iftar|suhoor|eid|halal|kosher|shabbat|sabbath|passover|hanukkah|lent|hijabi?s?|diwali|"
    r"pcos|endometriosis|menopaus\w*|perimenopaus\w*|hiv|bipolar|ocd|ptsd|ibs|celiac|coeliac|crohn'?s|"
    r"non-?binary|genderqueer)\b", re.I)


def sensitive(*texts):
    return any(t and SENSITIVE.search(str(t)) for t in texts)


# Fix pass 2, finding 38: what the person TELLS us about their own goal is kept in their words ("eating healthier on a
# budget", "getting fit", "saving money", "learning to invest", "sleeping better"). SENSITIVE above is for what the bot
# would INFER from what they watched. From their own words only these are left out, and only the clause that says
# them: a stated diagnosis or condition, debt or income figures, religion, politics, sexuality, relationship status.
STATED_SENSITIVE = re.compile(
    r"\b(diagnos\w*|my (?:illness|disease|condition|meds|medication|therapy|therapist|doctor|psychiatrist)|cancer|"
    r"diabet\w*|adhd|autis\w*|depress\w*|anxiety|anxious|bipolar|ocd|ptsd|chemo\w*|pregnan\w*|ivf|infertil\w*|"
    r"eating disorder\w*|anorexi\w*|bulimi\w*|addict\w*|rehab|sobriety|hiv|surgery|miscarriage|"
    r"debts?|in debt|owe|owing|loans?|bankrupt\w*|paycheck|salary|income|mortgage|money (?:trouble|problems|worries)|"
    r"worr\w* about money|"
    r"religio\w*|church\w*|mosques?|synagogues?|pray\w*|bible|quran|koran|torah|jesus|christ|allah|my faith|"
    r"christian\w*|muslim\w*|islam\w*|jewish|judaism|hindu\w*|buddhis\w*|atheis\w*|spiritual\w*|"
    r"politic\w*|elections?|democrat\w*|republican\w*|trump|biden|harris|voting|vote for|abortion|"
    r"immigra\w*|deport\w*|asylum|green card|"
    r"sex|sexual\w*|gay|lesbian|bisexual|queer|lgbt\w*|transgender|non-?binary|coming out|porn\w*|"
    r"i(?:'|’)?m (?:single|married|divorced|engaged|separated|widowed|dating)|in a relationship|"
    r"my (?:wife|husband|partner|boyfriend|girlfriend|ex|fianc\w*)|divorc\w*|break-?up|dating)\b"
    r"|\$\s?\d|\b\d+(?:[.,]\d+)?\s?(?:k|grand|dollars|bucks|euros|pounds)\b", re.I)
_CLAUSE = re.compile(r"(\s*(?:[,;.]|\band\b|\bbut\b|\bplus\b|\balso\b)\s*)", re.I)


def stated_sensitive(*texts):
    return any(t and STATED_SENSITIVE.search(str(t)) for t in texts)


def keep_stated(text):
    """(kept, dropped): the person's own words without any clause that states one of the things left out (finding
    38), never the rest of the sentence. A clause is a run between commas, semicolons, "and", "but" or full stops."""
    text = " ".join(str(text or "").split())
    if not stated_sensitive(text):
        return text, False
    pieces = _CLAUSE.split(text)
    out, sep = [], ""
    for i, piece in enumerate(pieces):
        if i % 2:   # a separator
            sep = piece
            continue
        if not piece.strip() or stated_sensitive(piece):
            continue
        out.append((sep if out else "") + piece)
    return "".join(out).strip(" ,;.") if out else "", True


def _clean(s, n):
    s = " ".join(str(s or "").split())[:n].strip(" .,;:-")
    return "" if UNSAFE_TEXT.search(s) else s


def _prompt(name):
    return open(os.path.join(config.HERE, "prompts", f"{name}.md"), encoding="utf-8").read()


STOP = set("a an and the of for to in on with my your our this that is it at by from or how what when new best easy "
           "quick simple ideas idea video videos reel reels post posts tutorial tutorials tips tip recipe recipes "
           "beginner beginners guide make making learn learning start starting finish finished ends end whole full "
           "one some more any things thing stuff saved save saves mostly".split())


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
    """(items, channels): the newest items the person chose to keep (saved, in a collection, sent to themselves), then
    a seeded random set of the rest of them (the seed is the library build, so the same build gives the same sample),
    then a smaller seeded set of their likes and playlists, and the few YouTube channels they watch most (finding 41:
    watched videos must not drown what they kept)."""
    chosen = [it for it in view.items.values() if it.kinds & CHOSEN]
    chosen.sort(key=lambda it: (it.kept_on() or "", it.id), reverse=True)
    recent = chosen[:config.PROFILE_SAMPLE_RECENT]
    rest = sorted(chosen[config.PROFILE_SAMPLE_RECENT:], key=lambda it: it.id)
    rnd = random.Random(_library_stamp(view.lib) + ":profile")
    items = recent + rnd.sample(rest, min(config.PROFILE_SAMPLE_RANDOM, len(rest)))
    liked = sorted((it for it in view.items.values() if it.kinds & LIKED and not it.kinds & CHOSEN
                    and (it.caption or "").strip()), key=lambda it: it.id)
    short = max(0, config.PROFILE_SAMPLE_RECENT + config.PROFILE_SAMPLE_RANDOM - len(items))   # few kept: more likes
    items += rnd.sample(liked, min(config.PROFILE_SAMPLE_LIKED + short // 2, len(liked)))
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
                                                                  else "in a playlist" if "playlist" in it.kinds
                                                                  else "liked")
        rows.append(f"S{i}. {it.platform}, {how}: " + as_data(_item_text(it)[:LINE_CHARS] or "(no text)"))
    for j, (name, vids) in enumerate(chans, 1):
        titles = " | ".join(_item_text(v)[:70] for v in vids[:3])
        rows.append(f"C{j}. YouTube channel {as_data(name[:60])}, {len(vids)} videos watched; titles: " + as_data(titles))
    return "\n".join(rows)


def guess_key(view):
    parts = [os.path.abspath(view.lib), _library_stamp(view.lib), config.PROMPT_PROFILE_GUESS, config.MODEL,
             config.PROFILE_SAMPLE_RECENT, config.PROFILE_SAMPLE_RANDOM, config.PROFILE_SAMPLE_LIKED,
             config.PROFILE_CHANNELS, config.PROFILE_MAX_TOPICS]
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()


# fix pass 2, finding 41: a broad field alone ("Gaming", "Music") says nothing a person would say; code adds the topic's
# own words, which it checked in the topic's lines ("Gaming, mostly Minecraft and Fortnite"). Nothing is invented.
BROAD_FIELDS = set("""animation gaming games music technology tech art arts cooking food fitness design entertainment
    comedy lifestyle diy sports sport travel fashion beauty education science crafts memes media hobbies""".split())


def refine_broad(topic, words, texts):
    if norm(topic) not in BROAD_FIELDS:
        return topic
    own = {_stem(norm(topic))}
    specific = [w for w in words if w not in BROAD_FIELDS and _stem(w) not in own and w not in STOP][:2]
    if not specific:
        return topic
    shown = []
    for w in specific:
        found = re.findall(r"(?<![\w])(" + re.escape(w) + r")(?![\w])", " ".join(texts), re.I)
        caps = sum(1 for f in found if f[:1].isupper())
        shown.append(w.capitalize() if found and caps * 2 > len(found) else w)
    return f"{topic}, mostly {_and(shown)}"


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
        topic = refine_broad(topic, words, texts)
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
        doing = t.get("doing") if t.get("doing") in DOING else None
        out.append({"topic": topic, "share": round(support / total, 3), "support": support,
                    "support_ids": sorted(it.id for it in sup), "saved": len(saved),
                    "watched": watched, "words": words, "level": level, "quote": quote or None, "why": why or None,
                    "doing": doing, "confirmed": False, "source": "guess"})
    # finding 41: the read lists them most-saved first (what they chose to keep), then by their share of the sample
    out.sort(key=lambda x: (-x["saved"], -x["share"], x["topic"].lower()))
    return out[:config.PROFILE_MAX_TOPICS], removed


# what the guess says the person seems to be doing with a topic; the direction guess is built from these by code
DOING = {"learning": "learning", "making": "making", "collecting": "collecting", "practising": "practising",
         "following": "following"}


def shown_topic(topic):
    """A topic as it is shown: its words, with "2d" and "3d" written "2D" and "3D" (fix pass 4, finding 83)."""
    return re.sub(r"\b([234])d\b", r"\1D", " ".join(str(topic).split()), flags=re.I)


def topic_in_sentence(topic):
    """'quick dinners', 'Blender 3D': a topic as it reads inside a sentence (a capital only where the name has one
    past its first letter, or the model gave one for a name)."""
    t = shown_topic(topic)
    first = t.split(" ")[0]
    if len(first) > 1 and first[1:].islower() and first.lower() in COMMON_WORDS:
        return first.lower() + t[len(first):]
    return t


COMMON_WORDS = set("""quick easy home street video photo music guitar piano drawing painting cooking baking dinner
    dinners lunch lunches breakfast recipes recipe meals meal workouts workout running yoga gardening knitting
    sewing woodworking pottery dance dancing travel coffee cocktails sourdough bread pasta skincare makeup fashion
    hair nails cars bikes cycling climbing hiking fishing camping language languages spanish french chess board
    card magic film movie animation animated digital 3d graphic graphics web game games gaming minecraft lego
    interior home plant plants pet pets dog dogs cat cats calligraphy lettering crochet embroidery jewelry
    origami photography editing writing reading poetry productivity study studying coding programming motion design
    calisthenics fitness stretching mobility running""".split())


def direction_guess(interests, n=2):
    """'learning Blender 3D and collecting quick dinners': what the person seems to be working toward, built by code
    from the top topics the guess backed and what it says they do with each (finding 41). None without two."""
    # fix pass 4, finding 83: "making motion design" read badly; a verb that fits any topic ("into"), and "learning"
    # only where a level says they are learning it
    learning, into = [], []
    for i in interests:
        if i.get("source") != "guess" or not i.get("doing") or i["doing"] == "following" or i["doing"] not in DOING:
            continue
        (learning if i.get("level") in ("new", "beginner", "intermediate") else into).append(
            topic_in_sentence(i["topic"]))
        if len(learning) + len(into) >= n:
            break
    parts = ([f"learning {_and(learning)}"] if learning else []) + ([f"into {_and(into)}"] if into else [])
    return " and ".join(parts) if parts else None


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
    if not interests:
        # review fix X11 (section 4): an empty or unusable form is kept for the whole build only after a second try
        raw, c2 = llm.chat_json(_prompt(config.PROMPT_PROFILE_GUESS), user, purpose="mvp_profile_guess",
                                prompt_version=config.PROMPT_PROFILE_GUESS, person=handle, max_tokens=1800,
                                temperature=config.PROFILE_TEMPERATURE, seed=config.PROFILE_SEED + 1)
        cost += c2
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


# ---------- what the message asks for wins over the profile (fix pass 2, finding 62) ----------
# A thing to avoid and the things it covers: "meat" covers chicken, so "what can I make with chicken and rice?" from
# someone whose profile says "avoid meat" runs as asked. A diet word covers its kinds.
AVOID_COVERS = {
    "meat": "chicken beef pork lamb bacon steak turkey ham sausage mince veal duck chorizo pepperoni salami brisket "
            "prosciutto",
    "fish": "salmon tuna cod trout shrimp prawn seafood anchovy sardine tilapia halibut mackerel",
    "seafood": "shrimp prawn crab lobster mussel clam oyster scallop squid octopus",
    "pork": "bacon ham sausage chorizo pepperoni prosciutto",
    "dairy": "milk cheese cream butter yogurt yoghurt",
    "egg": "omelette omelet frittata quiche",
}
DIETS = {"vegetarian": ("meat", "fish", "seafood"), "pescatarian": ("meat",),
         "vegan": ("meat", "fish", "seafood", "dairy", "egg", "honey")}
# round 7 check: "something that isnt a donut" (finding 92) rules donut out; it does not ask for it
_NEGATING = (r"\b(?:no|not|without|avoid|skip|minus|hold the|free of|never|don['’]?t|do not|can['’]?t|cannot|"
             r"isn['’]?t|aren['’]?t|wasn['’]?t|doesn['’]?t|other than|except|rather than|instead of)\s+"
             r"(?:any\s+)?(?:\w+\s+){0,2}?")


def _covered(entry):
    """The words a thing to avoid (or a diet word) covers: itself, its kinds and their members."""
    out = set()
    for w in re.findall(r"[^\W\d_]+", str(entry or "").lower()):
        heads = list(DIETS.get(w, ())) + [w]
        for h in heads:
            out.add(h)
            out.update(AVOID_COVERS.get(h, "").split())
            out.update(AVOID_COVERS.get(h.rstrip("s"), "").split())
    return out


def named_against(entry, *texts):
    """True when the message names the thing to avoid, or something it covers, and does not say to leave it out:
    "chicken and rice" names chicken, which "meat" and "vegetarian" cover; "no chicken" does not."""
    from .retrieve import contains_word
    for t in texts:
        for w in _covered(entry):
            if contains_word(t or "", w) and not re.search(_NEGATING + re.escape(w), t or "", re.I) \
                    and not re.search(re.escape(w) + r"\w*[- ]free\b", t or "", re.I):
                return True
    return False


def avoid_for(avoid, *texts):
    """The person's things to avoid without the ones this message asks for (finding 62)."""
    return [a for a in avoid or [] if not named_against(a, *texts)]


def notes_for(notes, *texts):
    """Their notes without one this message overrides ("vegetarian now" when they ask for chicken)."""
    return [n for n in notes if not any(w in DIETS or w in AVOID_COVERS for w in re.findall(r"[a-z]+", n.lower())
                                        if named_against(w, *texts))]


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
    notes = list(prof["notes"])
    if message is not None:
        # finding 62: what the message asks for wins: an avoid entry it names is not given to the interpreter
        prefs = dict(prefs, avoid=avoid_for(prefs.get("avoid"), message))
        notes = notes_for(notes, message)
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
        # fix pass 4, finding 74: the wording stays as it was (a version that called these "never must-haves" made
        # the live interpreter read "what should I cook tonight?" as chat); code drops a must-have that restates them
        # (interpret.profile_guard)
        lines.append("Preferences: " + ("; ".join(p) if p else "none given") + ".")
    return lines + notes


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
        out.append("has " + kit_words(prefs["tools"]))
    if prefs.get("time"):
        out.append("usually has " + prefs["time"])
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


ASKED_LEVEL_WORD = re.compile(r"\b(?:easy|easier|simple|beginners?|intermediate|advanced|for kids|kid-friendly)\b", re.I)


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
    hard = pref_words({"avoid": avoid_for(prefs.get("avoid"), *texts)})   # finding 62: the message wins over the profile
    if hard:
        lines.append("Leave out: " + "; ".join(hard))
    p = pref_words({k: v for k, v in prefs.items() if k in ("tools", "time", "style")})
    if p:
        # fix pass 4, finding 74: prefer picks that fit these and say so only when the post's text backs it; never a
        # reason to call a pick close or to say nothing fits
        lines.append("Preferences (prefer picks that fit these; never a reason to call a pick close or no): "
                     + "; ".join(p))
    lines.extend(notes_for(prof["notes"], *texts))
    from .interpret import LEVEL_NEGATED
    said = next((m.group(0) for t in texts for m in ASKED_LEVEL_WORD.finditer(t or "")
                 if not LEVEL_NEGATED.search((t or "")[:m.start()])), None)   # never a level they rule out
    if said:   # fix pass 2, finding 58: a level in their own words ("easy", "beginner") reaches the composer
        lines.append(f"The level they asked for, in their words: {said.lower()}")
    asked = any(LEVEL_ASKED.search(t or "") for t in texts)
    guessed = m if ok and not (m.get("confirmed") or m.get("source") != "guess") else None
    return "\n".join(lines), bool(ok or asked), guessed


# ---------- what the person says about themselves ----------
def _find(interests, name):
    """The stored topic the person NAMED: the same name, or one whose own name shares a word with it ("Blender" is
    "Blender 3D"). Fix pass 2, finding 39: never by the guess's supporting words, so "I'm a beginner at Blender" can
    not land on a guessed "Animation" whose lines mention Blender."""
    n = norm(name)
    if not n:
        return None
    for i in interests:
        if norm(i["topic"]) == n:
            return i
    words = set(topic_words(name))
    best, score = None, 0
    for i in interests:
        s = len(words & set(topic_words(i["topic"])))
        if s > score:
            best, score = i, s
    return best


def _named_in(i, message):
    """True when the person's message names this stored topic (a word of its name is in their message)."""
    return bool(set(topic_words(i["topic"])) & set(topic_words(message)))


def _strs(v, n=8, size=40):
    if isinstance(v, str):
        v = [v]
    return [s for s in (_clean(x, size) for x in (v or []) if isinstance(x, str)) if s][:n]


def merge(store, handle, message, asked=None, person=None, shown=None, side=False):
    """One model call fills the form; apply_merge() checks and applies it. Returns (result, cost); result is
    apply_merge's. side: the message is a request (finding 88: only what a request may teach is applied)."""
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
    return apply_merge(store, handle, raw, message, shown=shown,
                       asked_direction=bool(asked and "working toward" in asked), side=side), cost


# fix pass 2, finding 63: a direction is stored only when the person states a goal ("I'm working toward...", "I want to
# learn...", "my goal is..."), or answers the setup's question about it; never words about timing or the request
GOAL = re.compile(r"\b(?:working (?:toward|towards|on)|work toward|(?:want|wanna|hope|hoping|plan|planning|aim|aiming|"
                  r"trying|try|need|going) to (?!send|show|find|get me|see|have|know|watch)|my (?:main |big )?goals?\b|"
                  r"goals? (?:is|are|for)\b|i(?:'|’)?m learning|i am learning|learning (?:to|how)|i(?:'|’)?d like to|"
                  r"i would like to|getting (?:better|into)|so (?:that )?i can|to become|i(?:'|’)?m (?:getting|"
                  r"building|training|studying|practi[sc]ing|starting)|i(?:'|’)?ve started)", re.I)
# fix pass 2, finding 62: "I eat meat again", "I'm not vegetarian any more": an avoid entry the person takes back
ALLOW_AGAIN = re.compile(
    r"\bi(?:'|’)?m not (?:a )?(vegetarian|vegan|pescatarian)\b|\bi am not (?:a )?(vegetarian|vegan|pescatarian)\b"
    r"|\bno longer (?:a )?(vegetarian|vegan|pescatarian)\b|\bnot (vegetarian|vegan|pescatarian) any ?more\b"
    r"|\bi (?:eat|drink|do eat|can eat) ([a-z]+(?: [a-z]+)?) again\b|\bi(?:'|’)?m eating ([a-z]+) again\b"
    r"|\bstop (?:avoiding|leaving out) ([a-z]+(?: [a-z]+)?)", re.I)


LEVEL_SAID = [("new", re.compile(r"\b(?:total|complete|absolute|real) (?:beginner|newbie|novice)|\bbrand new\b|"
                                 r"\bnever (?:tried|done|used)\b|\bjust (?:starting|started)\b|\bnew to\b", re.I)),
              ("intermediate", re.compile(r"\bintermediate\b|\bpast (?:the )?(?:beginner|basics)\b", re.I)),
              ("advanced", re.compile(r"\badvanced\b|\bexpert\b|\bpro\b", re.I)),
              ("beginner", re.compile(r"\bbeginner\b|\bnovice\b|\bnewbie\b", re.I))]


def level_said(message):
    """The one level the person's message states in so many words, or None (none, or more than one)."""
    found = []
    for lv, rx in LEVEL_SAID:
        if rx.search(message or "") and not (lv == "beginner" and {"new", "intermediate"} & set(found)):
            found.append(lv)
    return found[0] if len(found) == 1 else None


# fix pass 6, live check of finding 88: "I'm a beginner at guitar, find me a first song" states a level for a topic
# it names, in so many words; code reads it (the interpreter's form may leave the note out)
_TOPIC = r"([a-z][a-z0-9+#'’ -]{1,30}?)(?=\s*(?:[,.;!?]|$)|\s+(?:and|so|but|find|send|show|give|any|what|can|" \
         r"could|please|now|looking|need|want|got|have|help)\b)"
LEVEL_AT = re.compile(
    r"\bi(?:['’]?m| am)\s+(?:(?:a|an)\s+)?(?:(?:total|complete|absolute|real)\s+)?(?:beginner|novice|newbie|"
    r"intermediate|advanced|expert)\s+(?:at|in|with|on)\s+" + _TOPIC +
    r"|\bi(?:['’]?m| am)\s+(?:brand\s+|totally\s+|completely\s+)?new to\s+" + _TOPIC +
    r"|\bi(?:['’]?m| am)\s+(?:just\s+)?starting (?:out\s+)?(?:with|at|in|on)\s+" + _TOPIC +
    r"|\bi(?:['’]?m| am)\s+past (?:the )?(?:beginner stage|beginner|basics) (?:at|in|with|on)\s+" + _TOPIC, re.I)


def level_phrase(topic, level):
    """A level in words level_said() reads back ("new to guitar", "beginner at guitar")."""
    return {"new": "new to", "beginner": "beginner at", "intermediate": "intermediate at",
            "advanced": "advanced at"}[level] + " " + topic


def level_stated(message):
    """(the words that state it, topic, level) when the message states the person's level at a topic it names, else
    None."""
    m = LEVEL_AT.search(message or "")
    if not m:
        return None
    topic = next(g for g in m.groups() if g).strip(" '’-")
    lv = level_said(m.group(0)) or ("new" if re.search(r"\bnew to\b|\bstarting\b", m.group(0), re.I) else None)
    if not topic or not lv or stated_sensitive(topic) or not topic_words(topic):   # "I'm new to it" names nothing
        return None
    return " ".join(m.group(0).split()), topic, lv


def allowed_again(message):
    """The things the person says they no longer avoid, in their words ("meat", "vegetarian")."""
    out = []
    for m in ALLOW_AGAIN.finditer(message or ""):
        w = next(g for g in m.groups() if g).lower()
        if w not in out:
            out.append(w)
    return out


# ---------- fix pass 6, finding 88: a request changes no standing preference it did not ask to change ----------
# a standing preference is said as one: "always", "from now on", "in general", "by default", "every time"
STANDING = re.compile(r"\b(?:always|from now on|in general|generally|by default|every ?time|each time|going forward|"
                      r"from here on|for good|in (?:the )?future|all the time)\b", re.I)
# "only my own saves", "stick to my library", "no new stuff": outside off, in their words
SAVES_ONLY = re.compile(r"\b(?:only|just|stick to|stay with|keep (?:it )?to)\b[^.!?]{0,30}?\b(?:my|your) (?:own )?"
                        r"(?:saves|saved|library|stuff)\b|\bno (?:more )?(?:new|outside) (?:things|stuff|picks|videos|ones)\b"
                        r"|\bstop (?:adding|showing|sending|looking for) (?:me )?(?:new|outside)\b", re.I)
# the words that name a platform or a kind of their library, and a negation said before it ("no YouTube", "not from
# YouTube", "don't show me Instagram", "without my watch history", "stop using my likes", "never use my YouTube")
_NAMES = {"youtube": r"youtube|yt", "instagram": r"instagram|insta|ig",
          "like": r"likes|liked|liking", "watch": r"watch(?:ing)? history|watched|watches",
          "save": r"saves|saved", "collection": r"collections?", "playlist": r"playlists?",
          "share_self": r"(?:posts? |things |stuff )?(?:i )?(?:sent|send|shared|share|dm['’]?d) (?:to )?(?:myself|me)",
          "view": r"views|viewed|view history"}
_NEG = r"\b(?:no|not|never|don['’]?t|do not|doesn['’]?t|stop|quit|without|exclude|excluding|leave out|skip|ignore|" \
       r"avoid|except|minus|nothing from|none from)\b"


def negated(key, message):
    """True when the message says not to use this platform or kind, in words (finding 88)."""
    rx = _NAMES.get(key)
    return bool(rx) and bool(re.search(_NEG + r"(?:\W+[\w'’]+){0,4}?\W+(?:" + rx + r")\b", message or "", re.I))


LEVEL_WORDS = set("beginner beginners new novice newbie intermediate advanced expert pro level basics basic past "
                  "total complete absolute just starting started has have got owns own uses use".split())
DIET_SAID = re.compile(r"\b(vegetarian|vegan|pescatarian)\b", re.I)
DONT_EAT = re.compile(r"\bi\s+(?:don['’]?t|do not|can['’]?t|cannot|never|no longer)\s+eat\s+([a-z][a-z ,-]{1,40})", re.I)


def _avoid_stated(v, message):
    """A thing to avoid a request may add to the profile: covered by a diet the message states ("I'm vegetarian now")
    or by "I don't eat ..." in the message (finding 88)."""
    words = set(re.findall(r"[a-z]+", v.lower()))
    for d in DIET_SAID.findall(message or ""):
        if words & _covered(d.lower()):
            return True
    return any(words & _covered(m.group(1)) for m in DONT_EAT.finditer(message or ""))


# checker of fix pass 6: words that make a limit one request's only ("no YouTube this time"): never a standing change
ONE_TIME = re.compile(r"\b(?:this time|just this once|this once|this one time|for today|for tonight|"
                      r"(?<!from )(?<!starting )(?<!as of )(?:today|tonight)|right now|for this (?:one|request|search|ask|answer)|just for (?:this|now|today|tonight))\b", re.I)
# (checker) the words that say a style, a dropped topic or the level guessing, for a form that sets one
STYLE_SAID = {"brief": re.compile(r"\b(?:brief|briefer|short|shorter|concise|less detail|fewer words|to the point|"
                                  r"tl;?dr|keep (?:it|them|answers) (?:short|brief))\b", re.I),
              "full": re.compile(r"\b(?:full|fuller|longer|long answers|more detail|more details|detailed|in detail|"
                                 r"all the details|everything)\b", re.I)}
OUTSIDE_SAID = re.compile(r"\b(?:new|outside|fresh|discover\w*|beyond|saves?|saved|library|kept)\b|"
                          r"\bhaven['’]?t (?:seen|watched)\b", re.I)
CONFIRM_SAID = re.compile(r"\b(?:right|correct|spot on|accurate|true|exactly|yes|yep|yeah|that['’]?s me)\b", re.I)
GUESS_SAID = re.compile(r"\bguess\w*\b|\blevels?\b", re.I)


def one_time(message):
    """True when the message says its limit is for this request only and says nothing standing."""
    return bool(ONE_TIME.search(message or "")) and not STANDING.search(message or "")


# (checker of fix pass 6) a kit or a usual time a request states, not one it only names: "for my new air fryer",
# "I have an Instant Pot", "I usually have 20 minutes"; never "find me guitar songs" or "pasta in under 20 minutes"
_KIT_LEAD = r"\b(?:my|our|i have|i['’]ve got|ive got|i got|i own|i bought|i just bought|we have|we got|i use|using)\b"
_TIME_LEAD = r"\b(?:i|we)\s+(?:usually\s+|normally\s+|typically\s+|only\s+|just\s+|always\s+|never\s+)?" \
             r"(?:have|get|got|['’]ve got)\b|\b(?:my|our)\s+(?:usual|normal)\b"


def _stated_with(value, message, lead):
    words = re.findall(r"[^\W\d_]+", value or "")
    if not words:
        return False
    return bool(re.search(r"(?:" + lead + r")(?:\W+[\w'’-]+){0,4}?\W+" + re.escape(words[-1]) + r"\b", message or "",
                          re.I))


def side_form(raw, message):
    """Finding 88: what a request (an ask, a rule, a change, an action on the last answer, a follow-up) may teach the
    profile as a side effect: a level the message states for a topic it names, a kit, a usual time, a plain note, a
    thing it says they no longer avoid, and a diet it states. Never outside, exclusions, style, topics, the direction or
    confirmations: those change only through a message that is about the person's preferences."""
    raw = raw if isinstance(raw, dict) else {}
    out = {k: raw[k] for k in ("kind", "note") if k in raw}
    out["tools"] = [v for v in _strs(raw.get("tools"), 6, 30) if _stated_with(v, message, _KIT_LEAD)]
    if isinstance(raw.get("time"), str) and _stated_with(raw["time"], message, _TIME_LEAD):
        out["time"] = raw["time"]
    # (checker) a thing no longer avoided only when the message says so ("I eat meat again"), never because the
    # request names it ("a chicken recipe"): the request's own words already win over the avoid list for it
    again = set().union(*(_covered(a) for a in allowed_again(message))) if allowed_again(message) else set()
    out["allow"] = [a for a in _strs(raw.get("allow"), 6, 30) if set(re.findall(r"[a-z]+", a.lower())) & again]
    if level_said(message):
        out["levels"] = raw.get("levels") or []
    out["avoid"] = [v for v in _strs(raw.get("avoid"), 6, 30) if _avoid_stated(v, message)]
    return out


def restates(prof, note):
    """True when a note says only what the profile already holds, in other words ("Blender (beginner)" beside a topic
    Blender 3D at that level): it is not merged again and never makes a "Noted" line (finding 88)."""
    words = [w for w in topic_words(note) if w not in LEVEL_WORDS]
    if not words:
        return False
    prefs = prof.get("prefs") or {}
    have = set(topic_words(*[i["topic"] for i in prof.get("interests") or []], *(prefs.get("tools") or []),
                           *(prefs.get("avoid") or []), str(prefs.get("time") or ""), prof.get("direction") or "",
                           *(prof.get("notes") or [])))
    if not set(words) <= have:
        return False
    lv = level_said(note)
    if lv:
        i = _find(prof.get("interests") or [], " ".join(words))
        return bool(i) and i.get("level") == lv
    return True


def apply_merge(store, handle, raw, message, shown=None, asked_direction=False, side=False):
    """Validates the model's form against the message and the stored profile and applies it. Returns {"kind",
    "changes": [plain lines], "other": [the lines short_summary() does not cover], "skipped_sensitive": bool}. Levels and topics must name a stored topic or use the person's
    own words; direction and tools must be their own words; anything sensitive is left out (and said).
    side: the message is a request and this is its side effect (finding 88); a form that reads the message as only a
    request is treated the same."""
    from .interpret import own_words, timing_only
    from .schema import KINDS, PLATFORMS
    raw = raw if isinstance(raw, dict) else {}
    kind = raw.get("kind") if raw.get("kind") in ("about_me", "request", "both") else "about_me"
    if side or kind == "request":
        raw = side_form(raw, message)
        side = True
    prof = get(store, handle)
    interests = [dict(i) for i in prof["interests"]]
    prefs = dict(prof["prefs"])
    changes, skipped = [], False
    other = []   # the changes short_summary() does not show (onboarding step 3 says these too)
    for name in _strs(raw.get("drop_topics")):
        i = _find(interests, name)
        if i and _named_in(i, message):   # (checker of fix pass 6) only a topic the message names is dropped
            interests.remove(i)
            changes.append(f"{i['topic']} is off your interests")
            other.append(changes[-1])
    # "that's right" confirms what the person was shown (the read shows at most 4 topics), never a topic they did not see
    seen = None if shown is None else {t.lower() for t in shown}
    # (checker of fix pass 6) outside the setup's read (nothing shown), a confirmation is said in words or names the topic
    yes = seen is not None or bool(CONFIRM_SAID.search(message or ""))
    confirm = [i for i in interests if raw.get("confirm_all") is True and yes
               and (seen is None or i["topic"].lower() in seen)]
    confirm += [i for i in (_find(interests, n) for n in _strs(raw.get("confirm_topics")))
                if i and i not in confirm and (seen is not None or _named_in(i, message))]
    if any(not i.get("confirmed") for i in confirm):
        for i in confirm:
            i["confirmed"] = True
        changes.append("you confirmed " + _and([i["topic"] for i in confirm]))
    said_level = level_said(message)
    for lv in raw.get("levels") or []:
        if not isinstance(lv, dict) or lv.get("level") not in LEVELS:
            continue
        if said_level and len(raw.get("levels") or []) == 1 and lv["level"] != said_level:
            lv = dict(lv, level=said_level)   # their own word wins: "a beginner" is beginner, never "new"
        name = _clean(lv.get("topic"), 40)
        i = _find(interests, name) if name else None
        if i is not None and not _named_in(i, message):
            i = None   # finding 39: a level goes only to the topic the person named, never a nearby one
        if i is None:
            if not name or stated_sensitive(name) or not own_words(name, message):
                skipped = skipped or stated_sensitive(name)
                continue
            i = {"topic": name, "share": 0.0, "support": 0, "saved": 0, "watched": 0, "words": topic_words(name)[:3],
                 "level": None, "quote": None, "why": None, "confirmed": True, "source": "person"}
            interests.append(i)   # a new topic is added beside the guessed ones
        if i.get("level") != lv["level"] or not i.get("confirmed") or \
                (i.get("source") == "guess" and i.get("level_from") != "person"):
            # the topic keeps its counts and where it came from; the level is now theirs (finding 39)
            i.update(level=lv["level"], confirmed=True, level_from="person")
            if i.get("source") != "guess":
                i["source"] = "person"
            changes.append(f"{i['topic']}: {LEVEL_PLAIN[lv['level']]}")
            _drop_notes_about(store, handle, i)
    for name in _strs(raw.get("add_topics"), 4):
        if stated_sensitive(name):
            skipped = True
            continue
        if _find(interests, name) or not own_words(name, message):
            continue
        interests.append({"topic": name, "share": 0.0, "support": 0, "saved": 0, "watched": 0,
                          "words": topic_words(name)[:3], "level": None, "quote": None, "why": None,
                          "confirmed": True, "source": "person"})
        changes.append(f"you're into {name}")
    d = _clean(raw.get("direction"), 240)
    if d and not (asked_direction or GOAL.search(message)) or timing_only(d) or kind == "request":
        # finding 63: no goal stated, or only words about timing ("start doing daily"): never a direction; nor is a
        # message the form read as only a request, even as the answer to the setup's question (checker, round 2)
        d = ""
    if d:
        d, cut = keep_stated(d)   # finding 38: only the clause that states a personal matter goes, never the rest
        skipped = skipped or cut
        if d and own_words(d, message) and d != prof["direction"]:
            store.set_direction(handle, d)
            changes.append(f"you're working toward \"{d}\"")
    t = _clean(raw.get("time"), 60)
    if t and not stated_sensitive(t) and own_words(t, message) and t != prefs.get("time"):
        prefs["time"] = t   # finding 46: how much time they usually have, in their words
        changes.append(f"you usually have {t}")
        other.append(changes[-1])
    allow = [a for a in _strs(raw.get("allow"), 6, 30) + allowed_again(message) if own_words(a, message)]
    if allow:   # finding 62: "I eat meat again, I'm not vegetarian": those avoid entries go, and the reply says so
        cover = set().union(*(_covered(a) for a in allow))
        gone = [e for e in prefs.get("avoid") or [] if set(re.findall(r"[a-z]+", e.lower())) & cover]
        if gone:
            prefs["avoid"] = [e for e in prefs["avoid"] if e not in gone]
            changes.append(f"I won't leave out {_and(gone)} any more")
            other.append(changes[-1])
        ids = [r["id"] for r in store.profile_note_rows(handle, limit=50)
               if any(w in allow or ((w in DIETS or w in AVOID_COVERS) and _covered(w) & cover)
                      for w in re.findall(r"[a-z]+", r["text"].lower()))]
        store.drop_profile_notes(handle, ids)   # "vegetarian now" no longer holds
    for key, word in (("avoid", "you'd rather avoid"), ("tools", "you have")):
        vals = _strs(raw.get(key), 6, 30)
        if key == "avoid" and allow:
            vals = [v for v in vals if not set(re.findall(r"[a-z]+", v.lower())) & set().union(
                *(_covered(a) for a in allow))]
        bad = [v for v in vals if stated_sensitive(v)]
        skipped = skipped or bool(bad)
        # (checker of fix pass 6) a thing to avoid is in their words or covered by a diet they state, as a kit is
        vals = [v for v in vals if v not in bad and (own_words(v, message) or (key == "avoid" and _avoid_stated(v, message)))]
        new = [v for v in vals if v.lower() not in {x.lower() for x in prefs.get(key) or []}]
        if new:
            prefs[key] = (list(prefs.get(key) or []) + new)[-10:]
            changes.append(f"{word} {kit_words(new) if key == 'tools' else _and(new)}")
            other.append(changes[-1])
    if raw.get("style") in ("brief", "full") and prefs.get("style") != raw["style"] \
            and STYLE_SAID[raw["style"]].search(message or ""):   # (checker of fix pass 6) said in words
        prefs["style"] = raw["style"]
        changes.append("you like brief answers" if raw["style"] == "brief" else "you like full answers")
        other.append(changes[-1])
    if isinstance(raw.get("outside"), bool) and prefs.get("outside") is not raw["outside"] \
            and (STANDING.search(message) if raw["outside"] else (STANDING.search(message) or SAVES_ONLY.search(message))) \
            and (OUTSIDE_SAID.search(message) or SAVES_ONLY.search(message)) and not one_time(message):
        # (checker) and it is about new things or their saves at all: "from now on skip YouTube" is not
        # finding 88: a standing yes or no to new things is said as one ("always", "from now on", "only my saves")
        prefs["outside"] = raw["outside"]
        changes.append("I'll add new things from outside your saves" if raw["outside"]
                       else "I'll stick to your own saves")
        other.append(changes[-1])
    if isinstance(raw.get("stop_guessing_level"), bool) and GUESS_SAID.search(message or ""):
        want = not raw["stop_guessing_level"]
        if prefs.get("guess_level", True) is not want:
            prefs["guess_level"] = want
            changes.append("I'll stop guessing your level" if not want else "I'll guess your level again")
            other.append(changes[-1])
    for key, allowed in (("exclude_kinds", KINDS), ("exclude_platforms", PLATFORMS)):
        # finding 88: never a platform or kind the message does not say not to use, in words
        # (checker) and never a limit the message says is for this request only ("no YouTube this time")
        vals = [v for v in _strs(raw.get(key), 7, 20) if v in allowed and negated(v, message) and not one_time(message)]
        new = [v for v in vals if v not in (prefs.get(key) or [])]
        if new:
            prefs[key] = list(prefs.get(key) or []) + new
            changes.append(("I won't use your " if key == "exclude_kinds" else "I won't use ") + _and(_plain(key, new)))
            other.append(changes[-1])
    note = _clean(raw.get("note"), 120)
    if note and (timing_only(note) or kind == "request" or (allow and any(named_against(a, note) for a in allow))
                 or (side and not own_words(note, message)) or restates(prof, note)):
        # finding 63: words about timing are never a note; a note that repeats what they took back neither; finding
        # 88: a request's note is in its own words, and a note that restates the profile is not kept again
        note = ""
    if note:
        note, cut = keep_stated(note)
        skipped = skipped or cut
        if note and note.lower() not in {n.lower() for n in store.profile_notes(handle)}:
            store.add_profile_note(handle, note)
            changes.append(f"noted: {note}")
            other.append(changes[-1])
    set_interests(store, handle, interests)
    store.x("UPDATE people SET prefs=? WHERE handle=?", (json.dumps(prefs), handle))
    return {"kind": kind, "changes": changes, "other": other, "skipped_sensitive": skipped,
            "confirmed_all": raw.get("confirm_all") is True}


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


DETERMINER = re.compile(r"^(?:a|an|the|my|our|some|any|two|three|four|five|several|lots?\s+of|a\s+few|\d+)\s", re.I)


def with_article(kit):
    """Fix pass 3, finding 73: "you have an Instant Pot", not "you have Instant Pot". A plural or a name that already
    has a determiner is kept as it is."""
    k = " ".join(str(kit).split())
    last = k.split()[-1].lower() if k else ""
    if not k or DETERMINER.match(k + " ") or (len(last) > 3 and last.endswith("s") and not last.endswith("ss")):
        return k
    return ("an " if k[0].lower() in "aeio" or (k[0].lower() == "u" and not k.lower().startswith("us")) else "a ") + k


def kit_words(tools):
    return _and(with_article(t) for t in tools)


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


def short_count(i):
    """'about 45 saved, 3 watched': the counts code worked out for the topic, in the fewest words."""
    parts = []
    if i.get("saved"):
        parts.append(f"{about_count(i['saved'])} saved")
    if i.get("watched"):
        parts.append(f"{about_count(i['watched'])} watched")
    return ", ".join(parts)


def read_lines(prof, limit=None):
    """The read of the person for onboarding: one short line per guessed topic, ALL of them (finding 41), in the
    order the guess put them (most saved first), with the guessed level in plain words and the counts behind it."""
    out = []
    for i in prof["interests"][:limit]:
        lv = i.get("level") if level_allowed(i, prof["prefs"]) else None
        level = {"new": "new to it", "beginner": "a beginner", "intermediate": "past the basics",
                 "advanced": "advanced"}.get(lv)
        n = short_count(i)
        topic = shown_topic(i["topic"])
        out.append(f"• {topic[:1].upper() + topic[1:]}" + (f": {level}" if level else "")
                   + (f" ({n})" if n else ""))
    return out


def short_summary(prof):
    """What the bot now knows, in one or two lines (onboarding step 3): every topic with its level, and the direction
    in their words (finding 42: the topics they just added are never left out)."""
    parts = []
    for i in prof["interests"]:
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
        told = i.get("source") != "guess" or i.get("level_from") in ("person", "feedback")
        if lv and told:
            how = f"{LEVEL_PLAIN[lv]}, you told me"
        elif lv and level_allowed(i, prefs):   # finding 40: a guess they confirmed is not something they told me
            how = f"{LEVEL_PLAIN[lv]}, " + ("you confirmed it" if i.get("confirmed") else "my guess")
        else:
            how = "you told me" if i.get("source") != "guess" else ("you confirmed it" if i.get("confirmed")
                                                                    else "my guess")
        n = count_words(i)   # finding 39: a topic keeps its counts when its level changes
        lines.append(f"• {i['topic']} ({how}" + (f", from {n}" if n else "") + ")")
    if not prof["interests"]:
        lines.append("• No interests yet.")
    if prof["direction"]:
        lines.append(f"You're working toward: \"{prof['direction']}\".")
    p = []
    if prefs.get("tools"):
        p.append("you have " + kit_words(prefs["tools"]))
    if prefs.get("time"):
        p.append("you usually have " + prefs["time"])
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
    if prefs.get("avoid_creators"):   # review fix X9 (experience): "not this creator"
        p.append("I leave out posts by " + _and([str(x) for x in prefs["avoid_creators"]]))
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
