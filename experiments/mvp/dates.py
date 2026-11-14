"""PROTOTYPE ONLY - when a post was made, what today is, and which dates in a post's own text have passed (round 7,
finding 91; DESIGN.md section 12).

- An Instagram link's shortcode encodes the post's creation time: the media id is the shortcode read as a base-64
  number with Instagram's alphabet, and `id >> 23` is milliseconds since 1314220021721. Worked out from the link the
  person gave us; nothing is fetched. (Checked on the founder's library: 20,958 of 20,963 Instagram items with a kept
  date decode to a date on or before it.)
- A YouTube video's published date comes from videos.list (`snippet.publishedAt`, kept in youtube_cache).
- Time-sensitive requests (opportunities, deadlines, applications, events, "soon", a year ...) are recognised here,
  in code. For them a date written in the text is read by code; a passed date makes the thing "passed"; a post more
  than 12 months old that speaks of now ("now open", "apply now") with no date code can read is "old".
- A time-relative claim ("now open", "currently", "this week", "new") from a post older than 60 days is never shown as
  current (STALE).
Nothing here prints item text.
"""
import re
from datetime import date, datetime, timezone

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
IG_EPOCH_MS = 1314220021721
IG_CODE = re.compile(r"instagram\.com/(?:[^/?#]+/)?(?:p|reel|reels|tv)/([A-Za-z0-9_-]{6,})")
OLD_DAYS = 365          # older than this, a post's "now open" has probably closed
STALE_DAYS = 60         # older than this, a post's "currently", "this week", "new" is not said as current


def shortcode_time(code):
    """The creation time (UTC datetime) a shortcode encodes, or None. A long (private-link) code keeps the media id in
    its first 11 characters."""
    code = (code or "")[:11]
    if len(code) < 6 or any(ch not in ALPHABET for ch in code):
        return None
    n = 0
    for ch in code:
        n = n * 64 + ALPHABET.index(ch)
    ms = (n >> 23) + IG_EPOCH_MS
    try:
        d = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    return d if 2010 <= d.year <= 2100 else None


def instagram_posted(url):
    """'YYYY-MM-DD' the Instagram post was made, from its link; None for any other link."""
    m = IG_CODE.search(url or "")
    d = shortcode_time(m.group(1)) if m else None
    return d.date().isoformat() if d else None


def posted_on(it, extra=None):
    """'YYYY-MM-DD' the item was posted, when known: Instagram from its link, YouTube from videos.list."""
    if getattr(it, "platform", None) == "instagram":
        return instagram_posted(getattr(it, "url", None))
    if getattr(it, "platform", None) == "youtube":
        p = ((extra or {}).get(it.id) or {}).get("published_at")
        return str(p)[:10] if p else None
    return None


def first_kept(it):
    """The earliest date the person kept or saw it ('YYYY-MM-DD'), or None."""
    ds = [str(v)[:10] for v in (getattr(it, "dates", None) or {}).values() if v]
    return min(ds) if ds else None


def age_date(it, extra=None):
    """The date a post's claims date from: when it was posted, else when it was first kept (a lower bound on its age)."""
    return posted_on(it, extra) or first_kept(it)


def _d(s):
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def days_old(day, today):
    d = _d(day)
    return (today - d).days if d and today else None


# ---------- which requests are time-sensitive ----------
TIME_SENSITIVE = re.compile(
    r"\b(opportunit\w*|deadlines?|due dates?|apply|applying|applications?|internships?|scholarships?|fellowships?|"
    r"grants?|programs?|programmes?|events?|conferences?|hackathons?|competitions?|contests?|awards?|sales?|"
    r"discounts?|deals?|giveaways?|openings?|jobs?|hiring|cohorts?|bootcamps?|summits?|festivals?|tickets?|"
    r"registrations?|register|sign[- ]?ups?|soon|upcoming|coming up|this (?:week|month|year|summer|winter|spring|fall|"
    r"autumn|weekend)|next (?:week|month|year|summer|winter|spring|fall|autumn|semester)|missed|(?:19|20)\d\d)\b", re.I)
YEAR = re.compile(r"\b(20\d\d)\b")


def time_sensitive(*texts):
    return bool(TIME_SENSITIVE.search(" ".join(t for t in texts if t)))


def request_year(*texts):
    """A year the request names ("for 2026"), or None."""
    m = YEAR.search(" ".join(t for t in texts if t))
    return int(m.group(1)) if m else None


# ---------- dates written in a post's own text ----------
MONTHS = {m: i for i, ms in enumerate(
    ["jan january", "feb february", "mar march", "apr april", "may", "jun june", "jul july", "aug august",
     "sep sept september", "oct october", "nov november", "dec december"], 1) for m in ms.split()}
_MON = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|" \
       r"nov(?:ember)?|dec(?:ember)?)\.?"
_DAY = r"(\d{1,2})(?:st|nd|rd|th)?"
DATE_FORMS = [
    re.compile(rf"\b{_DAY}\s+(?:of\s+)?{_MON}(?:,?\s+(\d{{4}}))?\b", re.I),            # 14 February 2025
    re.compile(rf"\b{_MON}\s+{_DAY}(?:,?\s+(\d{{4}}))?\b", re.I),                       # February 14, 2025
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),                                          # 2025-02-14
    re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"),                                      # 2/14/2025 (US order)
]
DEADLINE_WORD = re.compile(r"\b(deadline|due|apply by|applications? close|closes?|closing|until|by|ends?|last day|"
                           r"before|register by)\b", re.I)


def find_dates(text, year_hint=None):
    """[(date, start, end)] for each full date written in the text. A day and month with no year take the year the post
    was made (`year_hint`); a year-less date more than a week before that day is the next year's."""
    out = []
    t = text or ""
    hint = _d(year_hint)
    for i, rx in enumerate(DATE_FORMS):
        for m in rx.finditer(t):
            try:
                if i == 0:
                    d, mon, y = int(m.group(1)), MONTHS[m.group(2).lower()[:3]], m.group(3)
                elif i == 1:
                    mon, d, y = MONTHS[m.group(1).lower()[:3]], int(m.group(2)), m.group(3)
                elif i == 2:
                    y, mon, d = m.group(1), int(m.group(2)), int(m.group(3))
                else:
                    mon, d, y = int(m.group(1)), int(m.group(2)), m.group(3)
                if y:
                    day = date(int(y), mon, d)
                elif hint:
                    day = date(hint.year, mon, d)
                    if (hint - day).days > 7:
                        day = date(hint.year + 1, mon, d)
                else:
                    continue
            except (ValueError, KeyError):
                continue
            if 2000 <= day.year <= 2100 and not any(s <= m.start() < e for _, s, e in out):
                out.append((day, m.start(), m.end()))
    return sorted(out, key=lambda x: x[1])


def deadline_in(text, year_hint=None):
    """(date, is_deadline) the text gives for something: the date next to a deadline word, else the latest date
    written; (None, False) when there is none."""
    found = find_dates(text, year_hint)
    if not found:
        return None, False
    t = text or ""
    near = [d for d, s, e in found if DEADLINE_WORD.search(t[max(0, s - 30):s])]
    if near:
        return max(near), True
    return max(d for d, _, _ in found), False


# words that speak of now: said in an old post they were true when it was posted, not today
NOW_TALK = re.compile(r"\b(now open|open now|(?:are|is) (?:now )?open|apply (?:now|today)|applications? (?:are |is )?"
                      r"(?:now )?open|deadline (?:is )?(?:soon|approaching|coming up)|closing soon|ends soon|limited time|"
                      r"last chance|register (?:now|today)|sign up (?:now|today)|don'?t miss|this week|this month|"
                      r"(?:happening|starts?) (?:soon|this)|now accepting|accepting applications|spots? left|"
                      r"currently (?:open|accepting|hiring))\b", re.I)
# a time-relative claim stated as current (finding 91: "it offers an application now open")
STALE = re.compile(r"\b(now open|open now|(?:is|are) (?:now )?open|currently|right now|this (?:week|month|year|season)|"
                   r"soon|today|tonight|tomorrow|upcoming|new|newest|latest|just (?:launched|released|dropped|opened|"
                   r"announced)|apply now|limited time|closing|still open|now accepting|accepting|ongoing|recent|"
                   r"recently|at the moment|coming up)\b", re.I)


def stale(text, day, today):
    """True when `text` states a time-relative claim and the post it came from is older than STALE_DAYS."""
    n = days_old(day, today)
    return bool(n is not None and n > STALE_DAYS and STALE.search(text or ""))


def state_of(text, posted, kept, today, own=None):
    """{'state': 'passed' | 'old' | 'open' | None, 'date': date or None, 'deadline': bool, 'from': date or None}.
    `text` is what the thing's own words say (an item's when and about, or a post's text); `own` the whole post, for the
    now-talk test. passed: a date it gives is before today. open: a date it gives is today or later. old: posted (or kept)
    more than OLD_DAYS ago, speaking of now, with no date code can read."""
    hint = posted or kept
    d, is_deadline = deadline_in(text, hint)
    base = _d(posted) or _d(kept)
    out = {"state": None, "date": d, "deadline": is_deadline, "from": base}
    if d is not None:
        out["state"] = "passed" if d < today else "open"
        return out
    if base is not None and (today - base).days > OLD_DAYS and NOW_TALK.search(" ".join([text or "", own or ""])):
        out["state"] = "old"
    return out


# ---------- dates said to the person ----------
def say_day(d, today):
    """'1 December' this year, '14 February 2025' any other year."""
    return f"{d.day} {d.strftime('%B')}" + ("" if d.year == today.year else f" {d.year}")


def how_far(d, today):
    """'in 17 days', 'tomorrow', 'today', 'in about 3 months'."""
    n = (d - today).days
    if n == 0:
        return "today"
    if n == 1:
        return "tomorrow"
    if n <= 60:
        return f"in {n} days"
    m = round(n / 30.4)
    return f"in about {m} months" if m < 24 else f"in about {round(n / 365)} years"


def date_note(st, today):
    """The few words said about a thing's date ('deadline 1 December (in 17 days)', 'its deadline, 14 February 2025,
    has passed', 'from May 2024, so this round has probably closed'), or ''."""
    if not st or not st.get("state"):
        return ""
    d = st.get("date")
    if st["state"] == "passed" and d:
        what = "deadline" if st.get("deadline") else "date"
        return f"its {what}, {d.day} {d.strftime('%B')} {d.year}, has passed"
    if st["state"] == "open" and d:
        return f"{'deadline' if st.get('deadline') else 'date'} {say_day(d, today)} ({how_far(d, today)})"
    if st["state"] == "old" and st.get("from"):
        return f"from {st['from'].strftime('%B %Y')}, so this round has probably closed; check whether it runs again"
    return ""


def month_year(day):
    d = _d(day)
    return d.strftime("%B %Y") if d else ""
