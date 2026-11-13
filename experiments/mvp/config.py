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
PROMPT_COMPOSE = "compose_v4"  # v3 with "because" as a bare clause and no internal words (fix pass, findings 7, 8, 37)
COMPOSE_TEMPERATURE = 0       # the interpreter's settings, for the same reason
COMPOSE_SEED = 7
PROMPT_EXTRACT = "extract_v1"  # details on the full text, one call per picked item, cached (section 4)
EXTRACT_TEMPERATURE = 0
EXTRACT_SEED = 7
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
