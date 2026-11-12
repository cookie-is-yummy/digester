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
                    "done": "Nice! I've noted that you made it.",
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


def changed(when, goal):
    return f"Changed: {when}, {goal}."


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
# features that come in later slices: one honest line each
NOT_YET = {
    "profile_show": "Showing what I know about you isn't ready yet.",
    "library_status": "I can't check your library imports from here yet. The founders can tell you when the last export "
                      "arrived.",
    "outside_only": "I can only look in your own saves for now, not for new things outside them.",
}
OUTSIDE_SOME = "I can only look in your own saves for now, so these are all from your library."


def first_send(first):
    """'The first one would come on Friday 13 November at 7pm.' (None for random moments, never shown in advance)."""
    return f" The first one would come {first}." if first else ""


def preview_tail(when, what, first=None):
    return (f"\n\n{cap_first(when)} I'll send {what} that I haven't sent you before.{first_send(first)} "
            "Reply YES to start, or tell me what to change.")


def preview_also_tail(when, what, first=None):
    return (f"\n\nAnd {when} I'll send {what}.{first_send(first)} Reply YES to start both, or tell me what to change.")


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
PROFILE_NOTED = "Noted. I'll keep that in mind when I read your requests. A full profile isn't ready yet."
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
