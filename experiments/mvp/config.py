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
PROMPT_INTERPRET = "interpret_v3"
INTERPRET_TEMPERATURE = 0     # the most deterministic settings the model accepts (DESIGN.md sections 4 and 11)
INTERPRET_SEED = 7
INTERPRET_CACHE_HOURS = 6     # the same request from the same person reuses its interpretation (section 4)
PROMPT_COMPOSE = "compose_v2"  # verdicts clear / close / no, backed "because", criteria per item (section 11)
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
