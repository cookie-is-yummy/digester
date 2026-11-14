"""PROTOTYPE ONLY - related picks from outside the library: YouTube only, official API only (DESIGN.md section 11
"Outside picks", which replaces the method in section 8; research note outside_recs.md, "Final, corrected
recommendation").

- Used only when the spec says outside "some" or "only", for a library request; never for a personal topic (health,
  relationships, money, religion, politics, sexuality), found by a code check on the request words; only when
  YOUTUBE_API_KEY is set and MVP_OUTSIDE is not "0". When the person asked for new things and this route cannot serve
  them, the reply says so in one line (section 11).
- The search text is built here, by code, from the person's own words: a word of the spec's search or goal is sent
  only when it also appears in the person's own message (or the rule's stored request), after handles, emails, links,
  phone numbers and digits are removed and the spec's creators, collections and avoided words are dropped. Never
  captions, titles, creators' names from the library, or the profile.
- One search.list call per answer (the key in the X-Goog-Api-Key header, never in a URL or a log), then one
  videos.list call that checks each result: returned, public, embeddable, not made for kids, not live or upcoming, a
  known length, not blocked in the region. Videos already in the person's library are removed. The first 3, in
  YouTube's order, are shown with YouTube's own title and channel name exactly as returned, the link and the length.
  No model call reads, ranks, describes or rewords them.
- Limits: a search text reuses its checked results for 24 hours, then they are dropped; at most 80 searches a day for
  everyone and 5 per person (YouTube's quota day ends at midnight Pacific), counted in the store; everyone's count is
  also kept in a file beside the MVP ledger, shared by every process that uses the same key.
- Results are never stored in the library and never recorded as deliveries, so feedback never lands on them.
"""
import hashlib
import json
import os
import re
import sys
import threading
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import config
from .retrieve import _stem, norm

sys.path.insert(0, os.path.join(config.EXP, "youtube"))
from api_enrich import _ssl_ctx, parse_duration  # noqa: E402

SEARCH_API = "https://www.googleapis.com/youtube/v3/search"
VIDEOS_API = "https://www.googleapis.com/youtube/v3/videos"
MAX_WORDS = 8

# ---------- the person's own words ----------
URL = re.compile(r"(?:https?://|www\.)\S+", re.I)
EMAIL_RX = re.compile(r"\S+@\S+")
HANDLE = re.compile(r"(?<!\w)@[\w.]+")
PHONE = re.compile(r"\+?\d[\d\s().-]{6,}\d")
TOKEN = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)?", re.UNICODE)
# words that say how to look, not what to look for; and plain function words
STOP = set("""a an the and or but nor so of to in on at by for with from into onto about as than then that this these those
it its it's is are was were be been being am do does did done have has had i me my mine myself we us our you your
yours he she they them their his her him what which who whom whose when where why how all any some few more most
other another such only own same too very just also not no yes please pls can could would should will shall may might
must let lets let's get gets got give gives show shows send sends find finds look looking see want wants need needs
like likes love new newer newest fresh outside beyond else there here out stuff thing things one ones something
anything everything saves saved save saving library libraries collection collections list lists feed youtube
instagram insta ig video videos reel reels post posts clip clips channel channels recommend recommendation
recommendations suggest suggestion suggestions good great best nice cool cute quick few couple bunch lot lots
today tonight tomorrow now later soon every each daily weekly week weeks day days morning evening night time times
monday tuesday wednesday thursday friday saturday sunday am pm minute minutes hour hours already yet again maybe
really actually kind sort type""".split())

# personal topics (docs/07, DESIGN.md sections 5 and 11): a whole word or phrase match in the request blocks the search
# Fix pass, finding 35: only words that are personal on their own. Words with an everyday sense ("partner workout",
# "god tier", "trading cards", "chicken stock", "liberal amount of salt", "injury-friendly workout": an injury is an
# ordinary topic with avoid words, DESIGN.md section 11) are not here; the personal sense comes in as a phrase below.
SENSITIVE = {
    "health": """health diagnosis diagnosed symptom symptoms disease illness cancer diabetes depression depressed
        anxiety adhd autism autistic bipolar ocd ptsd therapist psychiatrist psychiatry medication medications
        prescription pregnant pregnancy fertility ivf surgery addiction sobriety suicide suicidal anorexia bulimia
        hospital std hiv covid vaccine vaccines chemo chemotherapy menopause miscarriage
        pcos endometriosis perimenopause ibs celiac coeliac crohn crohns crohn's""",
    "relationships": """relationship relationships dating breakup divorce divorced hookup tinder bumble""",
    "money": """debt debts loan loans salary paycheck investing investment investments crypto bitcoin finances financial
        banking mortgage taxes bankruptcy savings""",
    "religion": """religion religious jesus christ allah church mosque synagogue prayer prayers bible quran koran torah
        christian christians christianity muslim islam jewish judaism hindu hinduism buddhist buddhism atheist
        ramadan iftar suhoor eid halal kosher shabbat sabbath passover hanukkah lent hijab hijabi diwali""",
    "politics": """politics political election elections voting voter democrat democrats republican republicans trump
        biden harris congress senate abortion immigration immigrant immigrants deportation asylum""",
    "sexuality": """sex sexual sexuality gay lesbian bisexual queer lgbt lgbtq transgender nonbinary porn nsfw kink
        kinky nude nudes erotic genderqueer""",
}
SENSITIVE_STEMS = {_stem(w): topic for topic, words in SENSITIVE.items() for w in words.split()}
SENSITIVE_PHRASES = {"self harm": "health", "eating disorder": "health", "mental health": "health",
                     "weight loss": "health", "lose weight": "health", "birth control": "health",
                     "my doctor": "health", "my therapy": "health", "physical therapy": "health", "my meds": "health",
                     "panic attack": "health", "panic attacks": "health", "my partner": "relationships",
                     "my boyfriend": "relationships", "my girlfriend": "relationships", "my husband": "relationships",
                     "my wife": "relationships", "my ex": "relationships", "my marriage": "relationships",
                     "relationship advice": "relationships", "dating advice": "relationships",
                     "coming out": "sexuality", "stock market": "money", "side hustle": "money",
                     "make money": "money", "get rich": "money", "money trouble": "money", "money problems": "money",
                     "pay off": "money", "credit score": "money", "credit card debt": "money", "day trading": "money",
                     "stock trading": "money", "personal finance": "money", "green card": "politics",
                     "god's word": "religion", "praise god": "religion", "my faith": "religion",
                     "how to pray": "religion", "vote for": "politics", "non binary": "sexuality"}


def _clean(text):
    """The text without links, emails, @handles, phone numbers and digits."""
    t = URL.sub(" ", text or "")
    t = EMAIL_RX.sub(" ", t)
    t = HANDLE.sub(" ", t)
    t = PHONE.sub(" ", t)
    return re.sub(r"\d+", " ", t)


def _tokens(text):
    return [w.replace("’", "'") for w in TOKEN.findall(norm(_clean(text)))]


def sensitive_topic(texts):
    """The personal topic the request is about, or None. Whole words (and a few phrases) of every text given."""
    for text in texts:
        if not text:
            continue
        toks = _tokens(text)
        t = " " + " ".join(toks) + " "
        for phrase, topic in SENSITIVE_PHRASES.items():
            if f" {phrase} " in t:
                return topic
        for tok in toks:
            topic = SENSITIVE_STEMS.get(tok) or SENSITIVE_STEMS.get(_stem(tok))
            if topic:
                return topic
    return None


# ---------- fix pass 3, finding 67: topic words, one fixed kind word, and the checks on what comes back ----------
# The kind of thing asked for, found by code in the person's words (then the form's), and the one fixed word sent for
# it. Words that only say the kind ("cook", "recipe", "make", "tutorial", "ideas") are never topic words: "what should I
# cook tonight?" has no topic, so it gets no outside search (it once searched "cook tonight" and got news about a man
# called Cook).
KINDS = (("recipe", re.compile(r"\b(?:cook|cooking|cooked|recipes?|bake|baking|meals?|dinners?|lunch(?:es)?|"
                               r"breakfasts?|brunch|dish(?:es)?|desserts?|snacks?|food|eat|supper)\b", re.I)),
         ("workout", re.compile(r"\b(?:workouts?|exercises?|exercising|work\s+out|training|stretch(?:es|ing)?|yoga|"
                                r"pilates|cardio|hiit|gym)\b", re.I)),
         ("tutorial", re.compile(r"\b(?:tutorials?|how\s+to|lessons?|learn(?:ing)?|make|making|build|building|"
                                 r"draw(?:ing)?|paint(?:ing)?|model(?:ing|ling)?|sculpt(?:ing)?|knit(?:ting)?|"
                                 r"sew(?:ing)?|crafts?|diy|projects?)\b", re.I)))
KIND_ONLY = set("""cook cooking cooked recipe recipes bake baking make making made build building tutorial tutorials
    workout workouts exercise exercises lesson lessons learn learning idea ideas project projects inspiration inspo
    how guide guides tips tip trick tricks hack hacks diy craft crafts should could would
    short shorter mini tiny long longer easy easier simple""".split())   # length words: the length bound covers them
# words about time are dropped (STOP has the days and parts of the day)
TIME_WORDS = set("""weekend weekends month months year years lately recently currently right asap upcoming coming
    next last this tonight's today's week's""".split())
NEWS_CATEGORY = "25"    # YouTube's "News & Politics"
NEWS_ASKED = re.compile(r"\bnews\b|\bheadlines?\b", re.I)


def request_kind(texts, spec=None):
    """'recipe' | 'workout' | 'tutorial' | None: from the person's own words first, then the form's goal and searches.
    The word sent is code's (this table), never the model's."""
    for group in ([t for t in texts if t], [spec.content.goal or "", *spec.content.searches] if spec else []):
        joined = " ".join(group)
        for kind, rx in KINDS:
            if rx.search(joined):
                return kind
    return None


def query_words(spec, texts):
    """The topic words: the spec's search and goal words that also appear in the person's own texts (compared in
    singular form), in the spec's order, without function words, words about time, words that only say the kind,
    the spec's creators, collections or avoided words, and at most 7. The form sent is the person's own spelling."""
    own = {}
    for text in texts:
        for tok in _tokens(text):
            own.setdefault(_stem(tok), tok)
    c = spec.content
    blocked = set()
    for name in [*c.creators, *c.avoid_creators, *c.collections, *c.avoid_collections, *c.avoid]:
        blocked |= {_stem(t) for t in _tokens(name)}
    out, seen = [], set()
    for source in [*c.searches, c.goal or ""]:
        for tok in _tokens(source):
            s = _stem(tok)
            if s in seen or s in blocked or tok in STOP or s in STOP or len(s) < 2 or s not in own \
                    or tok in KIND_ONLY or s in KIND_ONLY or tok in TIME_WORDS:
                continue
            seen.add(s)
            out.append(own[s])
    return out[:MAX_WORDS - 1]


def search_text(spec, texts):
    """The topic words and one fixed word for the kind ("lemon pasta recipe"); None when no topic word is left."""
    words = query_words(spec, texts)
    if not words:
        return None
    kind = request_kind(texts, spec)
    if kind and _stem(kind) not in {_stem(w) for w in words}:
        words = words + [kind]
    return " ".join(words)


def shares_topic(video, topic):
    """Finding 67 (d): a result is kept only when its title or channel has one of the request's topic words (whole
    word, any case, singular or plural)."""
    stems = {_stem(w) for w in topic}
    have = {_stem(t) for t in _tokens(f"{video.get('title') or ''} {video.get('channel') or ''}")}
    return bool(stems & have)


def keep_results(checked, topic, texts):
    """The checked results that may be shown: on the topic, and not news unless the person asked for news."""
    news_ok = any(NEWS_ASKED.search(t or "") for t in texts)
    return [v for v in checked if shares_topic(v, topic)
            and (news_ok or str(v.get("category") or "") != NEWS_CATEGORY)]


def kind_fits(items, spec, texts, own_text):
    """Finding 67 (a): how many of the candidates look like the kind asked for in their own text (a recipe, a
    workout, a whole tutorial; not tips alone) and share a topic word with the request when it has one. None when the
    request names no kind. The uninvited outside block needs fewer than 3 of these as well as fewer than 3 clear picks."""
    fit = kind_fit_items(items, spec, texts, own_text)
    return None if fit is None else len(fit)


def kind_fit_items(items, spec, texts, own_text):
    """The candidates kind_fits counts, in their order (fix pass 5, finding 84: the second look draws on these); None
    when the request names no kind."""
    from .compose import PROJECT, tips_only
    kind = request_kind(texts, spec)
    if not kind:
        return None
    rx = {"recipe": ITEM_RECIPE, "workout": ITEM_WORKOUT, "tutorial": PROJECT}[kind]
    stems = {_stem(w) for w in query_words(spec, texts)}
    out = []
    for it in items:
        text = own_text(it)
        if not rx.search(text) or tips_only(text):
            continue
        if stems and not stems & {_stem(t) for t in _tokens(text)}:
            continue
        out.append(it)
    return out


ITEM_RECIPE = re.compile(r"\b(?:recipes?|ingredients?|tbsp|tsp|tablespoons?|teaspoons?|cups?|bake[ds]?|baking|"
                         r"roast(?:ed)?|simmer|saut[eé]|stir[- ]?fry|whisk|oven|air ?fryer|instant ?pot|serves|marinade|"
                         r"dinner|lunch|breakfast|meal)\b", re.I)
ITEM_WORKOUT = re.compile(r"\b(?:workouts?|reps|sets|exercises?|routine|circuit|squats?|lunges?|plank|stretch(?:es|ing)?|"
                          r"yoga|hiit|cardio)\b", re.I)


# ---------- the HTTP layer (replaced by a fake in tests) ----------
def http_get(url, params, key, timeout=None):
    """One GET to a YouTube Data API endpoint. The key goes in a header; errors never carry it."""
    req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}",
                                 headers={"X-Goog-Api-Key": key, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout or config.YOUTUBE_TIMEOUT, context=_ssl_ctx()) as r:
        return json.loads(r.read().decode("utf-8"))


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


# ---------- the shared daily count (one file beside the MVP ledger, whatever MVP_HOME is) ----------
_count_lock = threading.Lock()


def _count_path():
    from . import llm   # its LEDGER_HOME is the one ledger every MVP process shares
    return os.path.join(llm.LEDGER_HOME, "outside_searches.jsonl")


def _shared_rows():
    try:
        with open(_count_path(), encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
    except (OSError, ValueError):
        return []


def _shared_count(day):
    return sum(1 for r in _shared_rows() if r.get("day") == day)


def _shared_add(day, at):
    """One search, with its quota day and time only (no person, no words)."""
    path = _count_path()
    with _count_lock:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        rows = _shared_rows()
        if len(rows) > 1000:   # only the last few days matter
            keep = sorted({r.get("day") for r in rows if r.get("day")})[-3:]
            rows = [r for r in rows if r.get("day") in keep]
            with open(path + ".tmp", "w", encoding="utf-8") as f:
                f.writelines(json.dumps(r) + "\n" for r in rows)
            os.replace(path + ".tmp", path)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"day": day, "at": at}) + "\n")


def check_videos(resp, ids, region=None):
    """videos.list response -> the videos that pass, in the order of `ids` (YouTube's search order):
    [{"video_id", "title", "channel", "duration_s"}] with the title and channel exactly as returned."""
    got = {}
    for v in (resp or {}).get("items") or []:
        if not isinstance(v, dict) or v.get("id") not in ids:
            continue
        sn, st, cd = v.get("snippet") or {}, v.get("status") or {}, v.get("contentDetails") or {}
        if st.get("privacyStatus") != "public" or st.get("embeddable") is not True or st.get("madeForKids") is True:
            continue
        if sn.get("liveBroadcastContent", "none") != "none":
            continue
        dur = parse_duration(cd.get("duration"))
        if not dur:
            continue
        rr = cd.get("regionRestriction") or {}
        if region and (region in (rr.get("blocked") or []) or ("allowed" in rr and region not in rr["allowed"])):
            continue
        title, channel = sn.get("title"), sn.get("channelTitle")
        if not (isinstance(title, str) and title.strip() and isinstance(channel, str) and channel.strip()):
            continue
        got[v["id"]] = {"video_id": v["id"], "title": title, "channel": channel, "duration_s": int(dur),
                        "category": str(sn.get("categoryId") or "")}   # finding 67 (c): News & Politics is "25"
    return [got[i] for i in ids if i in got]


class Outside:
    """find(...) -> {"picks": [...], "status": str, "line": str|None, "query": bool, "searched": bool, "cached": bool}.

    status: shown | none_found | not_library | instagram_only | sensitive | off | no_words | limit_all |
    limit_person | error. `line` is the one plain line the reply carries when the block cannot be served."""

    def __init__(self, store, http=None, key_env=None):
        self.store = store
        self.http = http or http_get
        self.key_env = key_env or config.YOUTUBE_KEY_ENV
        self.searches = 0     # search.list calls made by this object
        self.checks = 0       # videos.list calls made by this object

    def _day(self, now=None):
        """The quota day (YouTube's, Pacific time). Review fix X10: from the real time, never the bot's clock, which
        the test page can move: a moved clock must not open a new day of real searches."""
        return datetime.now(timezone.utc).astimezone(ZoneInfo(config.OUTSIDE_DAY_TZ)).date().isoformat()

    def used_today(self, now, handle=None):
        """Searches made today: for one person (this store), or for everyone. Everyone's count is the larger of this
        store's and the shared count file's: the test page and the real bot keep separate stores but share one key and
        one quota, and deleting a person's data does not hand the day's searches back."""
        day = self._day(now)
        if handle is None:
            mine = self.store.one("SELECT COUNT(*) n FROM outside_searches WHERE day=?", (day,))["n"]
            return max(mine, _shared_count(day))
        return self.store.one("SELECT COUNT(*) n FROM outside_searches WHERE day=? AND handle=?", (day, handle))["n"]

    def available(self, handle, spec, texts, now=None):
        """True when find() could serve this request now (a key, the route on, not personal, not Instagram only, words
        to search with, the daily limits not reached). No search is made."""
        now = now or datetime.now(timezone.utc)
        c = spec.content
        texts = [t for t in texts if t]
        if c.source != "library" or c.platforms == ["instagram"] or not config.OUTSIDE_ON \
                or not os.environ.get(self.key_env):
            return False
        if sensitive_topic(texts + [c.goal or "", *c.searches, *c.criteria]) or not search_text(spec, texts):
            return False
        return self.used_today(now) < config.OUTSIDE_PER_DAY and \
            self.used_today(now, handle) < config.OUTSIDE_PER_PERSON

    def find(self, handle, spec, texts, have_ids=(), now=None, skip_ids=(), max_minutes=None):
        from . import texts as T
        now = now or datetime.now(timezone.utc)
        c = spec.content
        texts = [t for t in texts if t]
        out = {"picks": [], "status": None, "line": None, "query": False, "searched": False, "cached": False}

        def stop(status, line=None):
            out.update(status=status, line=line)
            return out
        if c.source != "library":
            return stop("not_library")
        if c.platforms == ["instagram"]:
            return stop("instagram_only", T.OUTSIDE_INSTAGRAM)
        if sensitive_topic(texts + [c.goal or "", *c.searches, *c.criteria]):
            return stop("sensitive", T.OUTSIDE_SENSITIVE)
        key = os.environ.get(self.key_env)
        if not config.OUTSIDE_ON or not key:
            return stop("off", T.OUTSIDE_OFF)
        q = search_text(spec, texts)
        if not q:
            return stop("no_words", T.OUTSIDE_NO_WORDS)
        out["query"] = True
        since = _iso(now - timedelta(hours=config.OUTSIDE_CACHE_HOURS))
        self.store.x("DELETE FROM outside_cache WHERE at<?", (since,))   # results are dropped after 24 hours
        dur = video_duration(max_minutes)
        ck = hashlib.sha256(json.dumps([q.lower(), config.OUTSIDE_REGION] + ([dur] if dur else [])).encode()).hexdigest()
        row = self.store.one("SELECT results FROM outside_cache WHERE key=? AND at>=?", (ck, since))
        if row is not None:
            checked = json.loads(row["results"])
            out["cached"] = True
        else:
            if self.used_today(now) >= config.OUTSIDE_PER_DAY:
                return stop("limit_all", T.OUTSIDE_LIMIT_ALL)
            if self.used_today(now, handle) >= config.OUTSIDE_PER_PERSON:
                return stop("limit_person", T.outside_limit_person(config.OUTSIDE_PER_PERSON))
            # counted before the call: every request uses quota, even one that fails
            sid = self.store.x("INSERT INTO outside_searches(handle,day,at,status) VALUES(?,?,?,?)",
                               (handle, self._day(now), _iso(now), "sent")).lastrowid
            _shared_add(self._day(now), _iso(now))
            out["searched"] = True
            try:
                self.searches += 1
                params = {"part": "snippet", "type": "video", "videoEmbeddable": "true", "safeSearch": "strict",
                          "maxResults": config.OUTSIDE_FETCH, "regionCode": config.OUTSIDE_REGION, "q": q}
                if dur:   # fix pass 2, finding 57: YouTube's own length filter for a request with a length bound
                    params["videoDuration"] = dur
                resp = self.http(SEARCH_API, params, key)
                ids = []
                for it in (resp or {}).get("items") or []:
                    vid = ((it or {}).get("id") or {}).get("videoId") if isinstance(it, dict) else None
                    if isinstance(vid, str) and re.fullmatch(r"[A-Za-z0-9_-]{6,20}", vid) and vid not in ids:
                        ids.append(vid)
                checked = []
                if ids:
                    self.checks += 1
                    checked = check_videos(self.http(VIDEOS_API, {"part": "snippet,status,contentDetails",
                                                                  "id": ",".join(ids), "maxResults": len(ids)}, key),
                                           ids, region=config.OUTSIDE_REGION)
            except Exception as e:  # noqa: BLE001 - an HTTP error, a timeout, quota used up: the type only is kept
                self.store.x("UPDATE outside_searches SET status=? WHERE id=?", (f"error:{type(e).__name__}", sid))
                return stop("error", T.OUTSIDE_ERROR)
            self.store.x("UPDATE outside_searches SET status='ok' WHERE id=?", (sid,))
            self.store.x("INSERT OR REPLACE INTO outside_cache(key,results,at) VALUES(?,?,?)",
                         (ck, json.dumps(checked), _iso(now)))
        have, skip = set(have_ids), set(skip_ids)
        checked = keep_results(checked, query_words(spec, texts), texts)   # finding 67: on the topic, no news
        left = [v for v in checked if v["video_id"] not in have and v["video_id"] not in skip]
        over = 0
        if max_minutes:   # findings 57 and 59: a video over the length the request allows is never shown
            over = sum(1 for v in left if v["duration_s"] > max_minutes * 60)
            left = [v for v in left if v["duration_s"] <= max_minutes * 60]
        from .compose import FINISHED, tips_only
        if any(FINISHED.search(cr) for cr in c.criteria) or request_kind(texts, spec):
            # fix pass 5, finding 85: for something to make or do, a whole video comes before tips (by YouTube's own
            # title) and one under 3 minutes; only an order, so never fewer picks because of it
            left = sorted(left, key=lambda v: (tips_only(v["title"]), 0 < (v.get("duration_s") or 0) < 180))
        picks = left[:config.OUTSIDE_SHOW]
        out["picks"] = picks
        if not picks:
            if over:
                return stop("none_short", T.outside_none_short(max_minutes))
            return stop("none_found", T.OUTSIDE_NONE)
        out["status"] = "shown"
        return out


def video_duration(max_minutes):
    """search.list's videoDuration for a length bound: "short" is under 4 minutes, "medium" 4 to 20; a longer bound
    gets no filter (the length check after videos.list still applies)."""
    if not max_minutes:
        return None
    if max_minutes <= 4:
        return "short"
    if max_minutes <= 20:
        return "medium"
    return None


def watch_url(video_id):
    return f"https://www.youtube.com/watch?v={video_id}"
