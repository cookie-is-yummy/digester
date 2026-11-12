"""PROTOTYPE ONLY - what the bot says, and the patterns that read what people say to it.

Every reply string the handler, executor and scheduler send lives here, so wording can change in one place.
"""
import re

CONSENT_VERSION = "mvp-consent-v1"

# ---------- patterns that read a message ----------
YES = re.compile(r"^\s*(yes|y|yep|yeah|yup|sure|ok|okay|go|start|do it|sounds good|👍)[\s.!]*$", re.I)
NO = re.compile(r"^\s*(no|n|nope|nah|cancel|don'?t)[\s.!]*$", re.I)
AGREE = re.compile(r"^\s*(i agree|agree|agreed|i'm in|im in|yes)\b", re.I)
NEGATION = re.compile(r"\b(not|don'?t|do not|no|disagree|never)\b", re.I)
QUICK_FEEDBACK = re.compile(r"^\s*(👍|👎)\s*(\d)?\s*$")
# How a reaction reaches a phone that shows it as text (SMS, or a reaction the channel passes on as text).
REACTION_TEXT = re.compile(r"^\s*(Liked|Loved|Laughed at|Emphasized|Disliked|Reacted (👍|👎|❤️)( to)?)\s+[“\"]", re.I)
# a "yes" that also edits an open preview ("yes but at 8pm")
YES_WITH_EDIT = re.compile(r"^\s*(yes|yep|yeah|ok|okay|sure)\b", re.I)
# a follow-up question that wants ingredients
RECIPE_WORDS = re.compile(r"ingredient|recipe|make|cook", re.I)

# ---------- fixed replies ----------
HELP = ("I find things in what you've saved and watched on Instagram and YouTube. Ask whenever you want something, "
        "or tell me when to send it.\n"
        "Now: \"what can I make with chicken and rice?\"\n"
        "Later: \"tonight at 9 send me something to wind down with\" or \"in two hours…\"\n"
        "Repeating: \"a pasta recipe every Friday at 7pm\"\n"
        "Manage: \"my rules\", \"run 1\", \"skip 1\", \"pause 1\", \"stop 1\". Reply 👍 or 👎, or \"👎 2\" for one pick. "
        "\"delete my data\" removes everything I hold about you.")
CONSENT = ("Hi! I'm a prototype that finds things in your own saved and watched posts and sends them when you ask. "
           "Your library stays on the founders' Mac. Your messages to me are stored so I work, and the founders look at "
           "them only to fix problems. Your requests and the text of posts I consider go to OpenAI to understand them "
           "(not used for training). You can say "
           "\"delete my data\" at any time. Reply \"I agree\" to start, and confirm you're 18 or over.")
WELCOME = "Thanks! " + HELP
SCHEDULED_FOOTER = "Not for you? Reply 👎. Want one more now? Reply \"another\". To pause these, reply \"pause {n}\"."
LAST_SEND = "That was the last one of this rule."
STILL_USEFUL = "Still useful? Reply 👍 to keep these coming."
PAUSED_QUIET = ("I've paused your timed sends because I haven't heard from you in a while. "
                "Reply \"resume all\" to restart them, or just ask me for something any time.")
UNKNOWN = "Hi! I'm a private test bot, and you're not set up with me yet."
NOTHING_PENDING = "I don't have anything waiting for a yes. Tell me what you'd like and I'll set it up."
LOADING = "One moment, I'm opening your library…"
LIMIT = "I've reached today's limit for you. I'll be able to search again tomorrow."
LIMIT_TOTAL = "The test budget is used up, so I can't search right now. The founders need to raise it."

RUN_ERROR = "Something went wrong on my side; I'll look into it. Please try again in a bit."
INTERPRET_ERROR = "Something went wrong on my side. Please try again in a bit."
NOT_DELETED = "OK, nothing is deleted."
NOT_STARTED = "OK, I won't start it. Tell me what you'd like instead."
DECLINED = "OK, I won't do that."
PREVIEW_HEAD = "Here's what that would look like now:\n\n"
MORE_OF_WHAT = "More of what? Tell me what you're looking for."
NOTHING_TO_FOLLOW_UP = "I haven't sent you anything to follow up on yet. What are you looking for?"
WHICH_RULE = "Which rule? Reply \"my rules\" to see their numbers."
NO_RULES = "You have no rules yet."
NO_RULES_ASK = "You have no rules yet. Just ask me for what you want."
CHANGE_TIME_PASSED = "That time has already passed, so I left the rule as it was. When should I send it?"
NO_SEND_COMING = "That one has no send coming up."
SKIPPED_LAST = "Skipped. That was its only send, so the rule is finished."
SKIPPED_RANDOM = "Skipped. The next one comes at a random time as usual."
DELETE_ASK = "This deletes your library, rules and history with me. Reply YES to delete everything."
DELETED = ("Done: your rules and history are deleted. A founder will remove your library "
           "and our message thread within 24 hours and confirm here.")
TIME_PASSED = "That time has already passed. When should I send it?"
ALL_QUIET = ("Those hours are all inside your quiet hours, and I only send at a time you name there. "
             "Pick other hours, or tell me an exact time.")
NOTHING_TO_ATTACH = "Thanks! Nothing to attach that to yet."
FEEDBACK_REPLIES = {"up": "Noted 👍", "down": "Noted. I won't send that again.", "more": "Noted: more like that.",
                    "less": "Noted: less like that.",
                    "harder": "Noted. Ask for \"a harder one\" and I'll look for one now.",
                    "easier": "Noted. Ask for \"an easier one\" and I'll look for one now.",
                    "done": "Nice! I've marked it as done, so I won't send it again.",
                    "hide": "Hidden. I won't send that one again."}
FEEDBACK_OTHER = "Noted."
NO_RULES_LIST = ("You have no rules yet. Ask me anything now, or tell me when to send something: "
                 "\"tonight at 9…\", \"every Friday at 7pm…\".")
RULES_HEAD = "Your rules:"
RULES_FOOT = "Reply \"run 1\" to get one now, or \"skip 1\", \"pause 1\", \"stop 1\", \"change 1 to …\"."
RULE_PAUSED = " (paused)"
MANAGE_WORDS = {"pause": "Paused", "stop": "Stopped", "resume": "Resumed"}


# ---------- replies built from parts ----------
def cap_first(s):
    return s[0].upper() + s[1:]


def picks_for(count, goal):
    """'1 pick for "a pasta recipe"'."""
    return f"{count} {'pick' if count == 1 else 'picks'} for \"{goal}\""


def avoid_clause(avoid):
    return f", nothing with {', '.join(avoid)}" if avoid else ""


def changed(when, goal, what=None):
    """'Changed: every day at 8am, mini Blender tutorials, now from YouTube, outside your saves.' (fix pass 2,
    finding 50: what changed is said, not only the rule as it now is)"""
    return f"Changed: {when}, {goal}" + (f", {what}" if what else "") + "."


def skipped(next_time, count=1, dates=None):
    """'Skipped. Next one ...'; 'Skipped the next 2. ...'; 'Skipped Thursday 26 November. ...'"""
    if dates:
        head = f"Skipped {dates}."
    elif count > 1:
        head = f"Skipped the next {count}."
    else:
        head = "Skipped."
    return f"{head} Next one {next_time}."


def zone_name(tz_name):
    return tz_name.split('/')[-1].replace('_', ' ')


def timezone_set(tz_name, local):
    return (f"OK, I'll use {zone_name(tz_name)} time from now on "
            f"(it's {local} there). Your send times keep their clock time.")


def timezone_back(home, when):
    return f" I'll switch back to {zone_name(home)} time {when}."


def resumes_at(when):
    return f" It starts again {when}."


def daily_limit_note(n):
    return f" I send at most {n} timed messages a day, so some of these will be left out."


def saved_rule(n, what):
    return (f"Saved as rule {n}: {what}. Ask for it, or text \"run {n}\", whenever you want it. "
            "I won't repeat picks.")


def once_set(first, what, n):
    return f"OK. {cap_first(first)} I'll send {what}. Reply \"stop {n}\" to cancel."


def rule_started(edited, when, goal, avoid, first):
    """`first` is None for random times, which are never shown in advance."""
    lead = "Got it" + (" with your change" if edited else "")
    first = f" First one {first}." if first else ""
    return (f"{lead}: {when}, {goal}{avoid}.{first} "
            "Reply \"my rules\" any time to see or change it.")


def which_pick(n):
    return f"My last message had {n} {'pick' if n == 1 else 'picks'}. Which one?"


def rule_next(when_text):
    return f" (next: {when_text})"


def rule_line(i, goal, when, state, nxt):
    return f"{i}. {goal}: {when}{state}{nxt}"


def managed(word, names):
    return f"{word}: {names}."


# ---------- slice 2: previews, reminders, to-dos, person-level timing, undo, and what is not ready yet ----------
WAITING_FOR_ANSWER = "OK, I won't set that up. Tell me what you'd like instead."
NOTHING_TO_UNDO = "There's nothing from the last 10 minutes to undo."
NO_TODOS = "Your list is empty. Add something with \"add … to my list\"."
TODO_NOT_FOUND = "I can't find that on your list. Reply \"my list\" to see the numbers."
NO_PICK_TO_ADD = "I haven't sent you anything to add yet. Ask me for something first."
QUIET_RESET = "OK, quiet hours are back to normal: no timed messages from 10pm to 8am."
SNOOZE_CLEARED = "OK, timed messages are back on."
SNOOZE_NONE = "Nothing was paused, so nothing changes."
TODO_DUE_PASSED = "That time has already passed, so I didn't set a reminder for it."
TODO_LIST_EMPTY_SEND = "Your list is empty right now. Nice work."
# features that come in later slices: one honest line each (none left after slice 6)
NOT_YET = {}

# ---------- slice 5: outside picks (YouTube) ----------
OUTSIDE_HEAD = "Not from your saves, but close to them:"
OUTSIDE_INSTAGRAM = "I can only look for new things on YouTube, not on Instagram."
OUTSIDE_SENSITIVE = ("I didn't look for new things on YouTube for this: I keep personal topics like health, money and "
                     "relationships to your own saves.")
OUTSIDE_OFF = "I can't look for new things outside your saves right now."
OUTSIDE_NO_WORDS = "Tell me what kind of thing you want, and I'll look for new ones on YouTube."
OUTSIDE_LIMIT_ALL = "I've used up today's searches for new things on YouTube. Ask me again tomorrow."
OUTSIDE_NONE = "I didn't find anything new on YouTube for this that isn't already in your saves."
OUTSIDE_ERROR = "I couldn't reach YouTube just now, so I couldn't look for new things."
OUTSIDE_ONLY_TAIL = " Ask without \"new\" and I'll look in your own saves."


def outside_none_short(minutes):
    """Findings 57 and 59: every new video found was longer than the request allows."""
    return f"There's no new one on YouTube under {minutes} minutes today, so I didn't send a longer one."


def outside_only_no_actions(actions):
    """New finds from YouTube are shown here only: 'so I didn't email them or put them on your calendar.'"""
    words = {"email.send": "email them", "calendar.add": "put them on your calendar", "todo.add": "add them to your list"}
    xs = [words.get(a, "do anything else with them") for a in dict.fromkeys(actions)]
    did_not = xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " or " + xs[-1]   # "didn't ... or ...", not "and"
    return f"New finds from YouTube only come here in the chat, so I didn't {did_not}."


def outside_limit_person(n):
    return f"You've had today's {n} searches for new things on YouTube. Ask me again tomorrow."


def outside_line(it, lang=None):
    """'• Title by Channel (9 minutes 40 seconds), on YouTube': YouTube's own title and channel, the length from
    videos.list worked out by code."""
    from . import lang as L
    from .ytinfo import minutes_text
    length = L.length(minutes_text(it.get("duration_s")), lang)
    return L.table(lang)["outside_line"].format(title=it["title"], channel=it["channel"],
                                                length=f" ({length})" if length else "")


# ---------- slice 5: keeping the library fresh ----------
PLATFORM_NAMES = {"instagram": "Instagram", "youtube": "YouTube"}
IMPORT_NOT_EXPORT = ("I couldn't use the file you sent: it isn't an Instagram export (JSON) or a Google Takeout zip "
                     "with YouTube in it. Nothing changed in your library.")
IMPORT_HTML = ("Your Instagram export is in HTML format, and I can only read JSON. Please request it again and choose "
               "JSON. Nothing changed in your library.")
IMPORT_NO_FOLLOWERS = ("Your Instagram export is missing \"Followers and following\", which I need to leave your "
                       "friends' posts out. Please request it again with that ticked. Nothing changed in your library.")
IMPORT_FAILED = ("Something went wrong while I was adding your new export, so I'm still using your library as it was. "
                 "The founders will look into it.")


def import_too_costly(est, cap):
    return (f"Your new export is big: adding it would cost about ${est:.2f}, and I can only spend ${cap:.2f} on one "
            "import. I'm still using your library as it was. The founders can raise the limit.")


def import_over_budget():
    return ("The test budget doesn't have room to add your new export, so I'm still using your library as it was. "
            "The founders need to raise it.")


def _by_source(counts):
    parts = [f"{n} from {PLATFORM_NAMES.get(p, p)}" for p, n in counts.items() if n]
    return _and(parts) if parts else ""


def import_done(new_counts, total_counts, refused=0):
    """'Your new export is in: 42 new items (12 from Instagram, 30 from YouTube). Your library now has 1,234 items.'"""
    n = sum(new_counts.values())
    total = sum(total_counts.values())
    head = (f"Your new export is in: {n} new {'item' if n == 1 else 'items'}"
            + (f" ({_by_source(new_counts)})" if n else "") + "." if n else "Your new export is in, with nothing new in it.")
    msg = f"{head} Your library now has {total:,} {'item' if total == 1 else 'items'}, and I'm using it from now on."
    if refused:
        msg += f" I couldn't use {refused} other {'file' if refused == 1 else 'files'} you sent: " + \
            "they aren't an Instagram export (JSON) or a Google Takeout zip with YouTube in it."
    return msg


def nothing_new_matched(goals):
    names = ", ".join(f"\"{g}\"" for g in goals)
    return f"Nothing new matched {'your rule' if len(goals) == 1 else 'your rules'} {names}."


def new_items_ended(goals):
    names = ", ".join(f"\"{g}\"" for g in goals)
    return (f"{'Your rule' if len(goals) == 1 else 'Your rules'} {names} "
            f"{'has' if len(goals) == 1 else 'have'} ended: {'its' if len(goals) == 1 else 'their'} end date has passed.")


def library_status_message(last_import, counts, newest, next_due, links):
    """When the last export came in, items by source, how old the newest item is, when the next export is due, and
    the export links. Every number is worked out by code."""
    lines = [last_import or "I haven't added an export for you yet: your library is the one the founders set up."]
    total = sum(counts.values())
    lines.append(f"It has {total:,} {'item' if total == 1 else 'items'}" + (f": {_by_source(counts)}." if total else "."))
    if newest:
        lines.append(newest)
    lines.append(next_due)
    if links:
        lines.append("To export again: " + "; ".join(f"{PLATFORM_NAMES.get(p, p)}: {u}" for p, u in links) + ".")
    return "\n".join(lines)


def first_send(first):
    """'The first one would come on Friday 13 November at 7pm.' (None for random moments, never shown in advance)."""
    return f" The first one would come {first}." if first else ""


def when_lead(when):
    """'every weekday at 7am and 6pm until 20 December,': the schedule as the start of a sentence, with its comma at
    the end of the whole phrase (fix pass, finding 13), never before "until"."""
    for word in ("until", "starting", "except on", "just once"):
        when = when.replace(f", {word} ", f" {word} ").replace(f", {word}", f" {word}")
    return when.rstrip(",") + ","


def preview_tail(when, what, first=None, heads="", offer=""):
    """`heads`, `offer`: a heads-up and an offer (findings 19 and 26), said before the YES they are answered by."""
    return (f"\n\n{cap_first(when_lead(when))} I'll send {what} that I haven't sent you before.{first_send(first)}"
            f"{heads}{offer or ' Reply YES to start'}, or tell me what to change.")


def preview_also_tail(when, what, first=None):
    return (f"\n\nAnd {when_lead(when)} I'll send {what}.{first_send(first)} Reply YES to start both, or tell me what to "
            "change.")


def reminder_once(first, text, n):
    return f"OK. {cap_first(first)} I'll remind you: \"{text}\". Reply \"stop {n}\" to cancel."


def reminder_started(when, text, first, n):
    first = f" First one {first}." if first else ""
    return f"Got it: {when}, I'll remind you: \"{text}\".{first} Reply \"stop {n}\" to end it."


def todos_rule_started(when, first, n):
    first = f" First one {first}." if first else ""
    return f"Got it: {when}, I'll send you your open to-dos.{first} Reply \"stop {n}\" to end it."


def reminder(text):
    return f"Reminder: {text}"


def todo_reminder(text):
    return f"Reminder from your list: {text}"


def todo_line(i, t, due_text=None, show_list=False):
    tail = f" (due {due_text})" if due_text else ""
    return f"{i}. {t['text']}{tail}" + (f" [{t['list']}]" if show_list and t.get("list") not in (None, "todo") else "")


def todo_list_head(name=None):
    return f"Your {name} list:" if name and name != "todo" else "Your list:"


TODO_FOOT = "Reply \"done 1\" when one is done, or \"remove 1\"."


def todos_added(texts, name, due_text=None):
    where = "your list" if name in (None, "todo") else f"your {name} list"
    due = f" I'll remind you {due_text}." if due_text else ""
    if len(texts) == 1:
        return f"Added \"{texts[0]}\" to {where}.{due}"
    return f"Added {len(texts)} things to {where}: " + "; ".join(texts) + "." + due


def todos_done(texts, left):
    return f"Done: {'; '.join(texts)}. {left} left on your list." if left else f"Done: {'; '.join(texts)}. Your list is clear."


def todos_removed(texts):
    return f"Removed: {'; '.join(texts)}."


def todo_due_set(text, due_text):
    return f"OK. I'll remind you about \"{text}\" {due_text}."


def which_todo(matches):
    return "Which one? " + "; ".join(f"{i}. {t['text']}" for i, t in matches)


def todo_numbers_unknown(n):
    return f"Your list has {n} {'thing' if n == 1 else 'things'} on it. Which number?"


NO_INGREDIENTS = ("I don't have the ingredients of that one written out, so I can't add them. "
                  "Ask me for its ingredients first.")


def quiet_set(blocks_text):
    return f"OK, no timed messages {blocks_text}. Times you named yourself still go out."


def quiet_ended(goals):
    """A window or random rule whose hours are now all quiet ends; the reply names it."""
    names = ", ".join(f"\"{g}\"" for g in goals)
    one = len(goals) == 1
    return (f" That leaves no time to send {names}, so I stopped {'that rule' if one else 'those rules'}. "
            "Reply \"undo\" to keep your old quiet hours.")


def ended_on_resume(goals):
    names = ", ".join(f"\"{g}\"" for g in goals)
    return f"{names} had no send left after its pause, so that rule is finished. Ask me to set it up again with a new time."


def ended_by_move(goals):
    names = ", ".join(f"\"{g}\"" for g in goals)
    return (f" At the same clock time there, {names} has no send left, so I ended "
            f"{'that rule' if len(goals) == 1 else 'those rules'}. Reply \"undo\" to go back.")


SNOOZE_PASSED = "That time has already passed, so nothing changes. Until when should I hold timed messages?"


def snoozed(until_text):
    until_text = until_text[3:] if until_text.startswith("on ") else until_text   # "until Monday 16 November at 12am"
    return (f"OK, no timed messages until {until_text}. Any sends in that time are skipped, "
            "and you can still ask me for things.")


def undone(what):
    return f"Undone: {what}."


# words that say what kind of thing a post is, not what it is about (fix pass, finding 14): never counted as topics
GENERIC_WORDS = set("video videos post posts reel reels saved save saves things thing stuff content clip clips "
                    "item items photo photos pic pics".split())


def stats_message(total, by_platform, by_kind, words=None, matched=None, by=None, extra=None):
    """Counts worked out by code only; friends' posts are not counted."""
    parts = [f"You've kept {total} {'thing' if total == 1 else 'things'}"]
    if by_platform:
        parts[0] += ": " + ", ".join(f"{n} on {p}" for p, n in by_platform)
    lines = [parts[0] + "."]
    if by_kind:
        lines.append("By how you kept them: " + ", ".join(f"{k} {n}" for k, n in by_kind) + ".")
    if words:
        lines.append(f"{matched} of them mention " + " or ".join(f"\"{w}\"" for w in words) + ".")
    if extra:
        lines.append(extra)
    lines.append("Posts from friends are not counted.")
    return "\n".join(lines)


def clarify_ask(question):
    return question


def stopped_rule(n_goal):
    return f"I stopped {n_goal}"


CONTACT_CARD = "Save me as a contact, so the links I send show a preview."
PROFILE_NOTED = "Noted. I'll keep that in mind when I read your requests."
QUIET_NEEDS_BOTH = "For quiet hours on some days only, tell me both times, for example \"not 9am to 3pm on weekdays\"."
QUIET_INVALID = "I can keep up to 4 sets of quiet hours, each with a start and a different end. Could you say it another way?"


def preview_more_note(n):
    return f"(Your other {'rule' if n == 1 else f'{n} rules'} from before will start with the same YES.)"


def skipped_next(when):
    return f"The next scheduled one is skipped, so the one after comes {when}."


def todos_once(first, n):
    return f"OK. {cap_first(first)} I'll send you your open to-dos. Reply \"stop {n}\" to cancel."


def _hm(hhmm):
    h, m = map(int, hhmm.split(":"))
    if (h, m) == (12, 0):
        return "noon"
    if (h, m) == (0, 0):
        return "midnight"
    return f"{h % 12 or 12}{'' if m == 0 else f':{m:02d}'}{'am' if h < 12 else 'pm'}"


DAY_NAMES = {"MON": "Mondays", "TUE": "Tuesdays", "WED": "Wednesdays", "THU": "Thursdays", "FRI": "Fridays",
             "SAT": "Saturdays", "SUN": "Sundays"}


def quiet_words(blocks):
    """'from 10pm to 10am, and from 9am to 3pm on weekdays'."""
    out = []
    for b in blocks:
        days = b.get("days") or []
        when = ""
        if days == ["MON", "TUE", "WED", "THU", "FRI"]:
            when = " on weekdays"
        elif days == ["SAT", "SUN"]:
            when = " on weekends"
        elif days:
            when = " on " + ", ".join(DAY_NAMES[d] for d in days)
        out.append(f"from {_hm(b['start'])} to {_hm(b['end'])}{when}")
    return ", and ".join(out)

REMINDER_FOOTER = "Reply \"stop {n}\" to end these."


# ---------- slice 4: outputs (email, calendar, to-dos) and the email code ----------
ACTION_FAILED = {"email.send": "I couldn't email this, sorry. Ask me again in a bit.",
                 "calendar.add": "I couldn't make the calendar entry this time, sorry.",
                 "todo.add": "I couldn't add it to your list this time, sorry."}
ACTION_FAILED_OTHER = "One of the things you asked for didn't work this time, sorry."
EMAIL_ASK = ("What's your email address? I'll send a 6-digit code there to check it's yours, then email this to you.")
EMAIL_ASK_RULE = ("What's your email address? I'll send a 6-digit code there to check it's yours. Until then I can't "
                  "email these.")
CODE_EXPIRED = "That code has expired. Reply \"new code\" and I'll send another."
CODE_CANCELLED = "That code was cancelled after too many wrong tries. Reply \"new code\" and I'll send another."
CODE_TOO_MANY = ("That's not it either, so I've cancelled that code. Reply \"new code\" and I'll send another, or send "
                 "me a different address.")
CODE_LIMIT = "I've sent enough codes for today. Please try again tomorrow."
EMAIL_ONLY_YOU = ("I can only email you, at your own address. Say \"email it to me\" and I'll send it to you, so you can "
                  "forward it.")
EMAIL_TYPE_IT = "What's your email address? Type it out and I'll send a 6-digit code there to check it's yours."
NOTHING_TO_ACT_ON = "I haven't sent you anything yet. Ask me for something first."


def code_wrong(left):
    return f"That's not the code. You have {left} {'try' if left == 1 else 'tries'} left."


def code_sent(email, minutes, changed=False, again=False):
    if again:
        return f"I sent a new 6-digit code to {email}. Text it to me here within {minutes} minutes."
    lead = f"I changed your email address to {email}" if changed else f"I saved {email} as your email address"
    tail = " Until then I won't email you." if changed else ""
    return (f"{lead} and sent a 6-digit code to it. Text me the code within {minutes} minutes to confirm it's "
            f"yours.{tail}")


def code_in_outbox(where, failed=False):
    if failed:
        return f"I couldn't send that email just now, so it's {where} instead."
    return f"Email isn't connected here, so the code email is {where} instead of your inbox."


def email_confirmed(email):
    return f"Thanks, {email} is confirmed."


def email_already(email):
    return f"{email} is already your email address, and it's confirmed."


def email_confirm_first(email):
    return f"Your email isn't confirmed yet. Text me the 6-digit code I sent to {email}, and I'll email it then."


def email_new_code_first(email):
    return (f"Your email isn't confirmed yet, and the code I sent to {email} has run out. Reply \"new code\" and I'll "
            "send another, then email it.")


def waiting_sent(subject, to, via, err, where):
    if via == "smtp":
        return f"I emailed you \"{subject}\" at {to}."
    if err:
        return f"I couldn't send \"{subject}\" just now, so the email is {where} instead."
    return f"Email isn't connected here, so I didn't send \"{subject}\". The email is {where}."


def waiting_failed(subject):
    return f"I couldn't email \"{subject}\", sorry. Ask me again in a bit."


def _and(xs):
    xs = list(xs)
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def outputs_note(names, repeating=False):
    """What a rule's do adds, in a preview or when it starts: ' Each time I'll also email it to you.'"""
    words = {"email.send": "email it to you", "calendar.add": "give you a link to put it on your calendar",
             "todo.add": "put it on your list"}
    extra = [words[n] for n in ("todo.add", "calendar.add", "email.send") if n in names]
    if not extra:
        return ""
    if "message.send" not in names:
        return f" I'll {_and(extra)} instead of sending it here."
    return f" Each time I'll also {_and(extra)}." if repeating else f" I'll also {_and(extra)}."


def later_set(first, verbs, what, n):
    """'OK. Today at 8pm I'll send it to you here: "One Pot Chicken Rice". Reply "stop 2" to cancel.'"""
    return f"OK. {cap_first(first)} I'll {_and(verbs or ['send it to you here'])}: {what}. Reply \"stop {n}\" to cancel."


SENT_AGAIN_HEAD = "Here's what you asked me to send you:"
ITEMS_GONE = "The post you asked me to send again isn't in your library any more, so there's nothing to send."


# fix pass 2, finding 62: a request the bot will not do gets a sentence picked by code, never the model's own words
NOT_CAUGHT = "Sorry, I didn't catch that. Could you say it another way?"
UNSUPPORTED = ("That's not something I can do. I find things in what you've saved and watched, now or at a time you "
               "pick, and I keep reminders and to-do lists.")
UNSUPPORTED_EVENT = ("I can't tell when that happens, so I can't send things then. Pick a time instead, like \"every "
                     "day at 6pm\".")
EVENT_TRIGGER = re.compile(r"\b(?:when|whenever|once|as soon as|if)\s+(?:i|it|i'm|im|i am|my|the|we)\b[^?]{0,40}"
                           r"\b(?:get|gets|got|arrive|arrives|leave|leaves|rains?|snows?|wake|wakes|home|work|gym|"
                           r"office|school|land|lands|done|finish|finishes|start|starts)\b", re.I)


def unsupported_reply(text, model_reply=None, lang=None):
    """The reply to a request the bot will not do: the parse-failure line as it is, an event the bot cannot see
    ("when I get home") with the offer to pick a time, else one plain line about what the bot does. In the person's
    language when lang.py has it (checker, round 2: the model's own reply in Spanish was replaced by English)."""
    from . import lang as L
    t = L.table(lang)
    if model_reply == NOT_CAUGHT:
        return t.get("not_caught") or NOT_CAUGHT
    if EVENT_TRIGGER.search(text or ""):
        return t.get("unsupported_event") or UNSUPPORTED_EVENT
    return t.get("unsupported") or UNSUPPORTED


# ---------- slice 6: the person's context and onboarding ----------
PROFILE_HOW_TO_CORRECT = ("To correct me, just say it: \"I'm past beginner at Blender\", \"I'm not into cooking any more\", "
                          "\"I have an air fryer\" or \"stop guessing my level\".")
# fix pass 2, finding 38: said at most once per reply, and it names nothing (not even the kind of thing left out)
PROFILE_SENSITIVE = "I left out one personal detail; I don't keep those."
SKIP = re.compile(r"^\W*(skip|skip it|skip this|skip that|next|later|not now|pass|no thanks)\W*$", re.I)
# a bare "that's right" (with thanks and the like): anything more ("yes, but I'm past beginner", "ok but I'm in
# Chicago") is an answer of its own and goes to the form call or the interpreter
_RIGHT_WORDS = (r"yes|yep|yeah|yup|right|correct|that'?s right|thats right|that'?s it|spot on|exactly|ok|okay|sure|"
                r"sounds right|looks right|all good|good|perfect|great|thanks|thank you|you got it|nailed it|totally|"
                r"pretty much|it is|yes it is|all correct")
RIGHT = re.compile(rf"^\W*(?:{_RIGHT_WORDS})(?:[\s!.,]+(?:{_RIGHT_WORDS}))*[\s!.,:)]*$", re.I)
SET_ME_UP_AGAIN = re.compile(r"^\W*(please\s+)?(set me up again|set up again|redo (my |the )?(setup|set ?up|onboarding)|"
                             r"start (the |my )?(setup|set ?up|onboarding) (again|over)|run (the )?setup again)\W*$", re.I)
ONBOARD_PICK = re.compile(r"^\W*(?:(?:number|#|no\.?)\s*)?([1-3])\W*$|^\W*(?:the\s+)?(first|second|third)(?:\s+one)?\W*$", re.I)
ONBOARD_REPEAT = re.compile(r"^\W*(?:yes,?\s+)?(?:every\s+(?:morning|day)|daily|each morning|repeat it|"
                            r"make it a rule|send (?:it|that|me one) every (?:morning|day))\W*$", re.I)


def read_message(lines, lead="Thanks!", direction=None):
    """Onboarding step 2: the read of the person (every guessed topic), the direction the bot guesses from it (finding
    41: built by code from the checked topics), then the two questions."""
    if lines:
        head = f"{lead} Here's my read of you from what you've saved and watched:\n" + "\n".join(lines)
        if direction:
            head += f"\nIt looks like you're {direction}."
        ask = ("Did I get that right? And in a sentence or two, what are you working toward right now? "
               "(Or say \"skip\".)")
    else:
        head = f"{lead} I couldn't get a good read of your library yet."
        ask = "In a sentence or two, what are you working toward right now? (Or say \"skip\".)"
    return head + "\n\n" + ask


READ_AGAIN = ("When you're ready: did I get that right, and what are you working toward right now? "
              "(Or say \"skip\".)")


def contact_message(lead, zone, local, has_email=False):
    """Onboarding step 3: what the bot now knows (lead), then the email and the time zone check."""
    email = ("" if has_email else "What's your email address? I use it to email you answers and calendar files, after "
             "a 6-digit code to check it's yours. ")
    return (f"{lead}\n\n{email}I have you on {zone} time, where it's {local} now. If that's wrong, tell me the city "
            f"you're in. (Or say \"skip\".)").strip()


def export_offer(platforms):
    """Finding 43: at setup only the reminder offer; the steps go out with each reminder, and on request."""
    every = {"instagram": "Instagram every 4 weeks", "youtube": "YouTube every 2 months"}
    names = ", ".join(every[p] for p in ("instagram", "youtube") if p in platforms)
    return f"I'll remind you when a fresh export is due ({names}) and send the steps then. OK?"


def export_started(nexts):
    """Finding 44: one line for every export reminder the YES started: [(platform, date)]."""
    parts = []
    for i, (p, d) in enumerate(nexts):
        day = d.strftime("%-d %B")
        parts.append(f"next {PLATFORM_NAMES.get(p, p)} reminder {day}" if i == 0 else
                     f"next {PLATFORM_NAMES.get(p, p)} one {day}")
    return "Done. " + cap_first(", ".join(parts)) + "."


# finding 46: the one optional question of the setup's last message, answered in free text or skipped
PREFS_QUESTION = ("Anything I should know to pick better: food you avoid, kit you have, how much time you usually "
                  "have? (Or say \"skip\".)")
PREFS_THANKS = "Thanks, that helps."
PREFS_SKIPPED = "No problem. Ask me for anything you've saved, any time."


def first_requests_block(texts, repeat_first=True):
    lines = ["Or try one of these, picked from your own saves:"]
    lines += [f"{i}. \"{t}\"" for i, t in enumerate(texts, 1)]
    tail = f"Reply {', '.join(str(i) for i in range(1, len(texts)))} or {len(texts)}" if len(texts) > 1 else "Reply 1"
    tail += " and I'll find it now."
    if repeat_first:
        tail += " Or reply \"every morning\" and I'll send you number 1 every morning at 8 (I'll show you one first)."
    return "\n".join(lines) + "\n" + tail


SETUP_DONE = "That's the setup done. Ask me for anything you've saved, any time, or say \"help\"."


def export_more_note(n):
    return f"(Your export {'reminder' if n == 1 else 'reminders'} will start with the same YES.)"


def profile_changed(changes, skipped=False):
    """'Noted: Blender: past the basics; you have an air fryer.'"""
    msg = "Noted: " + "; ".join(changes) + "." if changes else PROFILE_NOTED
    if skipped:
        msg += " " + PROFILE_SENSITIVE
    return msg + " Say \"what do you know about me\" to see it all."


def level_moved(topic, plain, way):
    lead = "Noted, I'll aim higher" if way == "harder" else "Noted, I'll keep it simpler"
    ask = "a harder one" if way == "harder" else "an easier one"
    return f"{lead} with {topic}: I now have you as {plain}. Ask for \"{ask}\" and I'll look for one now."


def level_moved_only(topic, plain, way):
    """The feedback line alone, when nothing easier (or harder) could be sent with it."""
    lead = "Noted, I'll aim higher" if way == "harder" else "Noted, I'll keep it simpler"
    return f"{lead} with {topic}: I now have you as {plain}."


def level_guess_note(topic, level, lang=None):
    """Said at most once per topic while the level is a guess (in the answer's language: lang.py)."""
    from . import lang as L
    t = L.table(lang)
    return t["level"][level].format(topic=topic) + t["level_tail"]


# ---------- fix pass (live findings of 12 Nov) ----------
SHORTER = re.compile(r"\b(short|shorter|quick|quicker|mini|less time|not so long)\b", re.I)


def and_words(xs):
    return _and(xs)


def detail_head(kinds, name):
    """'Here are the steps of One Pot Pasta by @chef:' (finding 4: one line naming the pick, then the lines)."""
    return f"Here are {_and(kinds)} of {name}:"


def detail_missing(kind_words, platform, has_description):
    """One honest line for a kind the pick does not write out (findings 5 and 16)."""
    if platform == "youtube":
        return (f"The video's description doesn't list {kind_words}." if has_description else
                f"I only have the video's title, so I can't quote {kind_words}.")
    return f"{cap_first(kind_words)} aren't written out in the post; they're in the video."


def detail_none(kind_words, name, platform, has_description):
    """Nothing of what was asked is written out: say so, then the link (finding 5)."""
    if platform == "youtube":
        if has_description:
            return f"The description of {name} doesn't list {kind_words}, so I can't quote them. Here's the video:"
        return f"I only have the title of {name}, not its description, so I can't quote {kind_words}. Here's the video:"
    return f"{name} doesn't write out {kind_words}; they're in the video. Here's the post:"


def level_moved_now(topic, plain, way, shorter=False):
    """The feedback line, then the one sent now (finding 6)."""
    one = ("a shorter, harder one" if way == "harder" else "a shorter, easier one") if shorter else \
        ("a harder one" if way == "harder" else "an easier one")
    if topic:
        lead = "Noted, I'll aim higher" if way == "harder" else "Noted, I'll keep it simpler"
        return f"{lead} with {topic}: I now have you as {plain}. Here's {one}:\n\n"
    return f"Noted. Here's {one}:\n\n"


REQUEST_NOUNS = {"recipe": "recipes", "tutorial": "tutorials", "workout": "workouts", "routine": "routines",
                 "project": "projects", "lesson": "lessons", "dish": "dishes", "meal": "meals", "build": "builds",
                 "guide": "guides", "craft": "crafts", "drill": "drills", "exercise": "exercises",
                 "stretch": "stretches", "how-to": "how-tos", "course": "courses", "class": "classes",
                 "dinner": "dinners", "lunch": "lunches", "breakfast": "breakfasts", "snack": "snacks",
                 "dessert": "desserts", "bake": "bakes", "video": "videos"}
_NOUN = re.compile(r"(?:\b([A-Z][\w+#-]*)\s+)?\b(" + "|".join(sorted(map(re.escape, REQUEST_NOUNS), key=len, reverse=True))
                   + r")(?:s|es)?\b", re.I)


def request_noun(*texts):
    """(singular, plural) of what the request is for, in its own terms ("Blender tutorial", "Blender tutorials";
    "recipe", "recipes"), or None. A name just before the noun (a capital: "Blender") is kept."""
    for t in texts:
        m = _NOUN.search(t or "")
        if m:
            one = m.group(2).lower()
            name = m.group(1) + " " if m.group(1) and m.group(1)[0].isupper() and m.group(1).lower() not in (
                "a", "an", "the", "some", "any", "my", "new", "mini", "short", "quick", "easy") else ""
            return name + one, name + REQUEST_NOUNS[one]
    return None


def outside_auto_head(n_clear, lang=None, noun=None):
    """Findings 26 and 64: the YouTube block that comes without being asked, because the saves hold too few, said in
    the request's terms: "You only have 2 saved recipes that fit, so here are a few more from YouTube:"."""
    from . import lang as L
    t = L.table(lang)
    one, many = noun or ("one", "ones")
    if not n_clear:
        return t["outside_auto0"].format(nouns=many) if noun or "outside_auto0_any" not in t \
            else t["outside_auto0_any"]
    return t["outside_autoN"].format(n=n_clear, go=t["go"][0 if n_clear == 1 else 1], noun=one if n_clear == 1 else many,
                                     fit=t.get("fit", ("", ""))[0 if n_clear == 1 else 1])


def few_finished(n_clear, lang=None, noun=None):
    from . import lang as L
    t = L.table(lang)
    one, many = noun or ("one", "ones")
    return t["few_finished"].format(n=n_clear, go=t["go"][0 if n_clear == 1 else 1],
                                    noun=one if n_clear == 1 else many, fit=t.get("fit", ("", ""))[0 if n_clear == 1 else 1])


def supply_note(n):
    """Finding 19: a repeating rule whose supply in the library is tiny."""
    if n == 0:
        return " Heads up: I don't see anything in your library that clearly fits, so this will run dry quickly."
    return (f" Heads up: I only see about {n} {'post' if n == 1 else 'posts'} in your library that "
            f"{'fits' if n == 1 else 'fit'}, so this will run dry quickly.")


def outside_offer(when, shown=False):
    """Findings 19 and 26: the offer in a preview; YES starts the rule with new videos from YouTube as well."""
    if shown:
        return f" Want these {when} from YouTube as well as your saves? Reply YES to start it that way"
    return " Want me to add related videos from outside your saves? Reply YES to start it that way"


def ended_by_revert(zone, goals):
    """Finding 21: the temporary time zone ended, and with it a rule's only send."""
    names = ", ".join(f"\"{g}\"" for g in goals)
    return (f"I'm back on {zone_name(zone)} time. At the same clock time here, {names} has no send left, so I ended "
            f"{'that rule' if len(goals) == 1 else 'those rules'}. Ask me to set it up again with a new time.")


def emails_dropped(expired, over):
    """Finding 30: emails that waited for a confirmed address and were dropped."""
    out = []
    if expired:
        out.append(f"{'One email' if expired == 1 else f'{expired} emails'} that waited more than a day for your "
                   f"address {'was' if expired == 1 else 'were'} dropped; ask me again if you still want "
                   f"{'it' if expired == 1 else 'them'}.")
    if over:
        out.append(f"I can keep only {config_wait_max()} emails waiting, so the oldest "
                   f"{'one was' if over == 1 else f'{over} were'} dropped.")
    return " ".join(out)


def config_wait_max():
    from . import config
    return config.EMAIL_WAIT_MAX
