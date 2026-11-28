"""PROTOTYPE ONLY - MVP skeleton settings. Everything personal lives under MVP_HOME (default data/mvp), outside git."""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
EXP = os.path.dirname(HERE)
REPO = os.path.dirname(EXP)
DEMO = os.path.join(EXP, "demo")
ENGINE = os.path.join(DEMO, "engine.py")
HOME = os.path.abspath(os.environ.get("MVP_HOME", os.path.join(REPO, "data", "mvp")))
DB = os.path.join(HOME, "mvp.sqlite")
PEOPLE = os.path.join(HOME, "people.json")  # handle -> {name, library, timezone}

MODEL = os.environ.get("MVP_MODEL", "gpt-5.4-mini")
PROMPT_INTERPRET = "interpret_v5"   # v3 plus the improvement round's rules (rule targets, two requests, surprises,
                                   # to-dos, outputs in do, avoid); v4 (profile rules) scored worse and is not in use
INTERPRET_TEMPERATURE = 0     # the most deterministic settings the model accepts (DESIGN.md sections 4 and 11)
INTERPRET_SEED = 7
INTERPRET_CACHE_HOURS = 6     # the same request from the same person reuses its interpretation (section 4)
PROMPT_COMPOSE = "compose_v5"  # v4 plus today's date and each candidate's dates (round 7, finding 91); v4: "because" as a
                               # bare clause and no internal words (fix pass, findings 7, 8, 37)
COMPOSE_TEMPERATURE = 0       # the interpreter's settings, for the same reason
COMPOSE_SEED = 7
PROMPT_EXTRACT = "extract_v4"  # v3 plus the kind asked for on its own line and "fit" yes only when the thing is itself
                               # one of that kind (a part, a term, a category, a step or a tip is "no"), with contrast
                               # examples from other topics (round 9, slice U); v3: v2 plus what an item is and is
                               # not, and "fit" yes only for the kind asked for (round 8, finding 93); v2: v1 plus
                               # the "items" kind (named things a post lists, with the request, the person and today's
                               # date; round 7, finding 90); details on the full text, one call per pick, cached
EXTRACT_TEMPERATURE = 0
EXTRACT_SEED = 7
# round 9, slice U2: one batched call to a stronger model judges, for a request that names a kind of thing, whether each
# thing the posts name is itself of that kind (judge.py). An empty model name turns it off. On by default after the
# kinds evaluation (22 requests): things shown that are truly of the kind 46 of 60 off, 51 of 60 with effort "none"
# (47 of 56 with "low"), at $0.0028 more per kind request ("low": $0.0054) and about 1.3 seconds per judged answer
JUDGE_MODEL = os.environ.get("MVP_JUDGE_MODEL", "gpt-5.5")
JUDGE_EFFORT = os.environ.get("MVP_JUDGE_EFFORT", "none")   # the reasoning effort sent with it ("" sends none)
PROMPT_JUDGE = "judge_kind_v2"   # v1 plus: a pack of assets made for such a thing is "no", and each thing is judged on
                                 # its own (live: a list made only of asset packs was judged "yes")
ANSWER_CACHE_HOURS = 24       # the same spec and candidates reuse the same composed answer ("another" bypasses it)
RANKED_CACHE_HOURS = 24 * 7   # the same search text on the same library build reuses its ranked list
WIDER_MAX = 3                 # "Or here's a wider selection:" (asks only)
YOUTUBE_KEY_ENV = "YOUTUBE_API_KEY"   # videos.list for YouTube candidates; without it the bot works as before
YOUTUBE_KEEP_DAYS = 30        # YouTube API data is kept at most 30 days (Developer Policies III.E.4)
YOUTUBE_TIMEOUT = float(os.environ.get("MVP_YOUTUBE_TIMEOUT", "8"))

SEARCH_DEPTH = 300      # ranked item IDs taken from each search
CANDIDATES = 40         # candidates shown to the composer
CAPTION_CHARS = 600     # caption text shown to the model per candidate
MAX_PICKS = 5
MAX_SCHEDULED_PER_DAY = 5
QUIET_START, QUIET_END = 22, 8   # local hours; scheduled sends are held in this window unless the rule's time is in it
DAILY_CAP_USD = float(os.environ.get("MVP_DAILY_CAP_USD", "1.00"))     # per person (rule 8)
TOTAL_CAP_USD = float(os.environ.get("MVP_TOTAL_CAP_USD", "10.00"))    # whole build and test (section 14)
# review fix X6: more than the worst case of the largest single call (a full compose: about $0.03)
TOTAL_CAP_MARGIN_USD = float(os.environ.get("MVP_TOTAL_CAP_MARGIN_USD", "0.05"))

# ---------- Claude as the text model (DESIGN.md section 20) ----------
# A model id starting with "claude-" (MVP_MODEL, MVP_JUDGE_MODEL, MVP_ERRAND_MODEL, or one call's model=) goes to
# Anthropic; any other stays on OpenAI. Nothing here changes a default: with no claude- model set, nothing below is used.
# Claude spend has its own total cap, counted from the ledger rows whose provider is "anthropic"; TOTAL_CAP_USD above
# then counts only the other rows (OpenAI and Gemini). The per-person daily cap counts everything.
CLAUDE_CAP_USD = float(os.environ.get("MVP_CLAUDE_CAP_USD", "10.00"))
# "off" (default): the small form-filling calls run without thinking where the model allows it (latency under the
# writer's 20 s deadline, and thinking would eat the max_tokens sized for the form); "adaptive": the model decides
CLAUDE_THINKING = os.environ.get("MVP_CLAUDE_THINKING", "off").strip().lower()
# output_config.effort when the caller names none ("" sends none: the model's own default, medium on Haiku and Opus 5.5)
CLAUDE_EFFORT = os.environ.get("MVP_CLAUDE_EFFORT", "low").strip().lower()
# the server-side fallback on a policy decline (Sonnet 5.5 and Opus 5.5; Haiku 5.5 has none). "0" turns it off.
CLAUDE_FALLBACKS = os.environ.get("MVP_CLAUDE_FALLBACKS", "1") != "0"


def is_claude(model):
    """True for a model id that goes to Anthropic (it starts with "claude-")."""
    return str(model or "").strip().lower().startswith("claude-")


def claude_models():
    """The Claude models the bot's own settings name (text model, judge, errand model), sorted; [] when none does.
    The consent and "what leaves this computer" name Anthropic only when this is not empty."""
    names = (MODEL, JUDGE_MODEL, os.environ.get("MVP_ERRAND_MODEL") or "")
    return sorted({str(m).strip() for m in names if is_claude(m)})
# ---------- end Claude ----------

# ---------- outputs (DESIGN.md sections 6 and 11, slice 4) ----------
# SMTP comes from the environment only, read when an email is sent (names only here; values are never printed).
SMTP_ENV = ("MVP_SMTP_HOST", "MVP_SMTP_PORT", "MVP_SMTP_USER", "MVP_SMTP_PASSWORD", "MVP_SMTP_FROM")
SMTP_TIMEOUT = 20
OUTBOX = os.path.join(HOME, "outbox")   # without SMTP every email (and every calendar file) is written here
BOT_NAME = os.environ.get("MVP_BOT_NAME", "Digest bot")
CODE_MINUTES = 15            # an email code works this long
CODE_TRIES = 5               # wrong tries before the code is cancelled
CODES_PER_DAY = 5            # codes sent per person a day at most (each one is an email to an address they typed)
EMAIL_WAIT_HOURS = 24        # an email waiting for a confirmed address is dropped after this
EMAIL_WAIT_MAX = 3           # emails kept waiting at most
CALENDAR_MINUTES = 30        # an event's length when none is named

# ---------- round 9, C1 (DESIGN.md section 16.D): the operator and the cap on outside writes ----------
# The operator is the one person who runs this bot on their own machine (their handle, as people.json spells it).
# Actions with who="operator" (their own mailbox, their Mac) run only for them. Unset: nobody is the operator.
OPERATOR = os.environ.get("MVP_OPERATOR") or None
OUTSIDE_WRITES_PER_DAY = 40   # outside actions (outside=True) per person per local day, all of them together
# ---------- round 10, slice K: the test page's own person is the operator ----------
# The test page runs on the computer of whoever runs the bot, so with `--channel web` and MVP_OPERATOR unset every
# person typed as on that page is the operator (bot.main sets this through use_page_operator). MVP_OPERATOR still wins
# when set; MVP_OPERATOR=none makes nobody the operator, also on the page (to try what a tester sees).
PAGE_OPERATOR = False
# ---------- end round 10, slice K ----------


def is_operator(handle):
    """True when MVP_OPERATOR names this handle (both in the handler's one spelling), or, with MVP_OPERATOR unset,
    when the bot runs the test page (round 10, slice K)."""
    if not handle:
        return False
    if not OPERATOR:
        return bool(PAGE_OPERATOR)
    if str(OPERATOR).strip().lower() == "none":
        return False
    from .handler import norm_handle   # here, not at the top: handler imports this module
    return norm_handle(str(OPERATOR)) == norm_handle(str(handle))


# ---------- mvp36 (DESIGN 35): the chat core behind a switch, first slice ----------
# MVP_BRAIN=1 and MVP_BRAIN_PEOPLE (comma separated handles) name the people whose history questions the chat core
# (brain/) may answer. Both are read per message. No default person: the operator is not implied (on the test page
# with MVP_OPERATOR unset, every person typed is the operator).
def brain_on(handle):
    """True only when MVP_BRAIN is "1" and MVP_BRAIN_PEOPLE lists this handle (both in the handler's one spelling)."""
    if not handle or (os.environ.get("MVP_BRAIN") or "").strip() != "1":
        return False
    from .handler import norm_handle   # here, not at the top: handler imports this module
    people = {norm_handle(x) for x in (os.environ.get("MVP_BRAIN_PEOPLE") or "").split(",") if x.strip()}
    return norm_handle(str(handle)) in people
# ---------- end mvp36 ----------


# ---------- round 10, slice K: who the operator is, and the build shown ----------
def use_page_operator(channel):
    """Called once at start by bot.main: on the test page with MVP_OPERATOR unset, the page's person is the operator."""
    global PAGE_OPERATOR
    PAGE_OPERATOR = channel == "web" and not OPERATOR
    return PAGE_OPERATOR


def operator_source():
    """'setting' (MVP_OPERATOR names someone), 'page' (the test page's person), or None (nobody)."""
    if OPERATOR:
        return None if str(OPERATOR).strip().lower() == "none" else "setting"
    return "page" if PAGE_OPERATOR else None


def _build():
    """MVP_BUILD when set; else the short commit and its date from git ("1a2b3c4 (17 Nov 2026)"); else "unknown"."""
    b = " ".join((os.environ.get("MVP_BUILD") or "").split())
    if b:
        return b[:60]
    try:
        import subprocess
        from datetime import datetime
        out = subprocess.run(["git", "-C", HERE, "log", "-1", "--format=%h %cs"], capture_output=True, text=True,
                             timeout=5, check=False)
        short, day = out.stdout.split()
        return f"{short} ({datetime.strptime(day, '%Y-%m-%d').strftime('%-d %b %Y')})"
    except Exception:  # noqa: BLE001 - no git, not a checkout, an odd answer: the page says "unknown"
        return "unknown"


BUILD = _build()   # read once at start: restart the bot to show a new build
# ---------- end round 10, slice K ----------


# ---------- round 9, slice A (DESIGN.md section 16.A): emails to other people ----------
SEND_HOLD_MIN = float(os.environ.get("MVP_SEND_HOLD_MIN", "2"))   # W4: "send" waits this long; "undo" stops it
SEND_LATE_MIN = 15             # W4: a hold this late (the bot was off) is not sent; the person is asked again
DRAFT_MODEL = os.environ.get("MVP_DRAFT_MODEL", "1") != "0"      # A6: the model writes the words (code checks them)
PROMPT_DRAFT = "draft_v2"      # round 9 live fix pass (finding 106): a complete, courteous email; draft_v1 stays
DRAFT_MODEL_PER_DAY = 6        # A6: model drafts and rewrites per person per local day; then the code-built words

# ---------- outside picks (DESIGN.md section 11 "Outside picks", slice 5) ----------
# YouTube only, official API only: one search.list per answer, checked by one videos.list. Off when MVP_OUTSIDE is "0"
# or YOUTUBE_API_KEY is unset (the key is read by name when a search is made, never printed).
OUTSIDE_ON = os.environ.get("MVP_OUTSIDE", "1") != "0"
OUTSIDE_SHOW = 3              # the first 3 that pass the checks, in YouTube's order
OUTSIDE_FETCH = 8             # maxResults of the one search
OUTSIDE_CACHE_HOURS = 24      # one search text reuses its results this long; then they are dropped
OUTSIDE_PER_DAY = 80          # searches a day for everyone (the project's search bucket is 100; the rest is headroom)
OUTSIDE_PER_PERSON = 5        # searches a day per person
OUTSIDE_DAY_TZ = "America/Los_Angeles"   # YouTube's quota day ends at midnight Pacific
OUTSIDE_REGION = os.environ.get("MVP_OUTSIDE_REGION", "US")
OUTSIDE_SHOWN_DAYS = 30       # a rule (or "another") does not show the same outside video again within this

# ---------- keeping the library fresh (DESIGN.md section 11 "Keeping the library fresh", slice 5) ----------
INBOX = os.path.abspath(os.environ.get("MVP_INBOX", os.path.join(REPO, "data", "inbox")))   # <INBOX>/<person>/
LIBRARY_ROOT = os.environ.get("MVP_LIBRARY_ROOT")   # where new libraries go; unset = beside the person's current one
INBOX_MINUTES = float(os.environ.get("MVP_INBOX_MINUTES", "3"))   # the scheduler looks at the inboxes this often
INBOX_SETTLE_SECONDS = float(os.environ.get("MVP_INBOX_SETTLE_SECONDS", "60"))  # a file must be unchanged this long
INBOX_PARTS_MINUTES = float(os.environ.get("MVP_INBOX_PARTS_MINUTES", "10"))   # a Takeout in parts waits for its last part
IMPORT_CAP_USD = float(os.environ.get("MVP_IMPORT_CAP_USD", "1.50"))   # one library build (its embeddings) at most
# review fix X2: library builds per person in 24 hours (a build has its own allowance, not the daily chat cap)
IMPORTS_PER_DAY = int(os.environ.get("MVP_IMPORTS_PER_DAY", "2"))
UPLOAD_MAX_MB = int(os.environ.get("MVP_UPLOAD_MAX_MB", "2048"))      # the test page's upload box
INBOX_EMAIL = os.environ.get("MVP_INBOX_EMAIL")     # the bot's inbox account a tester shares a Drive folder with
EXPORT_EVERY_DAYS = {"instagram": 28, "youtube": 61}   # the reminder's interval: 4 weeks; the Takeout schedule (2 months)

# ---------- the person's context and onboarding (DESIGN.md sections 5 and 11, slice 6) ----------
PROMPT_PROFILE_GUESS = "profile_guess_v3"      # one call groups a sample of their own kept items into topics (v3, fix
#                                               pass 2, finding 41: things they do or make, at the grain they would
#                                               say, up to 8, each with what they seem to be doing with it; v2 gave
#                                               coarse names like "Technology")
PROMPT_PROFILE_MERGE = "profile_merge_v3"      # what they say about themselves, as a form code validates (v2, finding
#                                               38: their own goals are kept in their words; only a stated diagnosis,
#                                               debt or income figures, religion, politics, sexuality or relationship
#                                               status is left out; finding 46: time they usually have; v3, findings
#                                               62 and 63: "allow" for what they no longer avoid, and a direction only
#                                               from a stated goal, never timing or the request)
PROMPT_FIRST_REQUESTS = "first_requests_v1"    # the first requests written for them, each checked against the library
PROFILE_TEMPERATURE = 0
PROFILE_SEED = 7
PROFILE_SAMPLE_RECENT = 45     # their newest saved, collected or sent-to-self items ...
PROFILE_SAMPLE_RANDOM = 45     # ... and this many more at random (seeded by the library build: the same sample each time)
PROFILE_SAMPLE_LIKED = 24      # likes and playlists weigh less (finding 41) ...
PROFILE_CHANNELS = 6           # ... and watch history least: their most watched YouTube channels (3 videos or more)
PROFILE_MAX_TOPICS = 8         # all of them are shown in the read (finding 41)
PROFILE_MIN_SUPPORT = 3        # a topic needs this many sample lines behind it
FIRST_REQUESTS = 3             # offered at the end of onboarding, each with at least FIRST_REQUEST_MIN candidates
FIRST_REQUEST_MIN = 3
ONBOARD_OFFER_HOURS = 24       # "1", "2", "3" and "every morning" pick from the offer this long
ONBOARD_STEP_HOURS = 24        # steps 2 and 3 wait this long for an answer; after that the setup ends quietly

# ---------- round 9, live fix (kinds; DESIGN.md section 12, "Round 9, live fix (kinds)", finding 103) ----------
# a request for a kind of thing whose kind has a modifier ("UI/UX libraries", "design tools") also searches the kind
# phrase itself, as spelled by code, when no search of the interpreter's already says it ("0" turns it off)
KIND_SEARCH = os.environ.get("MVP_KIND_SEARCH", "1") != "0"

# ---------- round 10, slice S (DESIGN.md section 17.S): a reel whose caption may not match its video ----------
# The doubt line names every reason by default. When the founder's labels put the strong mark's precision under 85%,
# set MVP_CM_DOUBT_ALL=0: demotion stays, and the line names only "the caption itself says so" and "you told me".
CM_DOUBT_ALL = os.environ.get("MVP_CM_DOUBT_ALL", "1") != "0"
# The marks are built at bot start in a background thread ("0" turns that off; the file is still read when it exists)
CM_BUILD_AT_START = os.environ.get("MVP_CM_BUILD_AT_START", "1") != "0"
# ---------- end round 10, slice S ----------
