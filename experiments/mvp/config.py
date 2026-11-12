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
PROMPT_INTERPRET = "interpret_v2"
PROMPT_COMPOSE = "compose_v1"

SEARCH_DEPTH = 300      # ranked item IDs taken from each search
CANDIDATES = 40         # candidates shown to the composer
CAPTION_CHARS = 600     # caption text shown to the model per candidate
FIT_MIN = 0.6           # picks below this fit score are not sent (rule 3)
MAX_PICKS = 5
MAX_SCHEDULED_PER_DAY = 5
QUIET_START, QUIET_END = 22, 8   # local hours; scheduled sends are held in this window unless the rule's time is in it
DAILY_CAP_USD = float(os.environ.get("MVP_DAILY_CAP_USD", "1.00"))     # per person (rule 8)
TOTAL_CAP_USD = float(os.environ.get("MVP_TOTAL_CAP_USD", "10.00"))    # whole build and test (section 14)
