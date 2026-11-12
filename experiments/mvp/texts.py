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
SCHEDULED_FOOTER = "Reply 👎 if it's not for you, \"another\" for one more now, or \"pause {n}\" to pause this."
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
                    "less": "Noted: less like that."}
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


def preview_tail(when, what):
    return (f"\n\n{cap_first(when)} I'll send {what} that I haven't sent you before. "
            "Reply YES to start, or tell me what to change.")


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
