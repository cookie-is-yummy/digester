"""PROTOTYPE ONLY - what the bot says, and the patterns that read what people say to it.

Every reply string the handler, executor and scheduler send lives here, so wording can change in one place.
"""
import re

CONSENT_VERSION = "mvp-consent-v1"

# ---------- patterns that read a message ----------
YES = re.compile(r"^\s*(yes|y|yep|yeah|yup|sure|ok|okay|go|start|do it|sounds good|👍)[\s.!]*$", re.I)
NO = re.compile(r"^\s*(no|n|nope|nah|cancel|don'?t)[\s.!]*$", re.I)
YES_LEAD = re.compile(r"^\s*(yes|yep|yeah|yup|sure|ok|okay|sounds good|go ahead|s[ií]|vale|claro)\b", re.I)
# review fix X12 (experience): a filler word first ("ok i agree", "sure, I agree"), a typo ("I agre") and Spanish
AGREE = re.compile(r"^\s*(?:(?:ok|okay|sure|yes|yeah|yep|fine|alright|s[ií]|vale|claro)\b[\s,.!]*)*"
                   r"(i agree?d?|agree?d?|i'm in|im in|yes|acepto|de acuerdo|estoy de acuerdo)(?!\w)", re.I)
CONSENT_AGAIN = "To start, reply \"I agree\". My message above says what I keep and why."
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
        "Errands: \"email my landlord that the sink is broken\", \"cancel my netflix\", \"apply to the second one\", "
        "\"do 2 for me\" on your list, \"what did you do for me\". I always show you an email first.\n"
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
# review fix X9 (experience): an ask does not learn from "less like that"; a creator the person names out is left out
LESS_ON_ASK = "Noted. If it's the creator you'd rather not see, say \"not this creator\" and I'll leave them out."
NO_CREATOR = "I don't know who made that one, so I can't leave them out."
CREATOR_WORDS = re.compile(r"\b(creators?|accounts?|channels?|this (?:person|guy|girl|chef)|from (?:them|him|her)|"
                           r"by (?:them|him|her))\b", re.I)


def creator_avoided(name):
    return f"Got it: I'll leave out posts by {name} from now on."
NO_RULES_LIST = ("You have no rules yet. Ask me anything now, or tell me when to send something: "
                 "\"tonight at 9…\", \"every Friday at 7pm…\".")
RULES_HEAD = "Your rules:"
RULES_FOOT = "Reply \"run 1\" to get one now, or \"skip 1\", \"pause 1\", \"stop 1\", \"change 1 to …\"."
RULE_PAUSED = " (paused)"
MANAGE_WORDS = {"pause": "Paused", "stop": "Stopped", "resume": "Resumed"}


# ---------- replies built from parts ----------
def cap_first(s):
    return s[0].upper() + s[1:]


COUNT_LEAD = re.compile(r"^\s*(?:(\d{1,2})|(one|two|three|four|five|six|seven|eight|nine|ten|a couple of|a few))\s+"
                        r"(?=[^\W\d_])", re.I)
COUNT_NAMES = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
               "ten": 10, "a couple of": 2, "a few": 3}


def goal_without_count(goal, count):
    """Fix pass 3, finding 70: '3 videos about investing' with 3 picks is "videos about investing" (the count is said
    once). A number that is not the count ("5 minute workouts", 1 pick) stays."""
    m = COUNT_LEAD.match(goal or "")
    if not m:
        return goal
    n = int(m.group(1)) if m.group(1) else COUNT_NAMES[m.group(2).lower()]
    return goal[m.end():] if n == count and goal[m.end():].strip() else goal


def picks_for(count, goal):
    """'1 pick for "a pasta recipe"'."""
    return f"{count} {'pick' if count == 1 else 'picks'} for \"{goal_without_count(goal, count)}\""


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


def daily_limit_shared(n):
    """Review fix X2 (experience): this rule and the person's other daily ones need more sends than the limit."""
    return (f" With your other timed messages that's more than {n} a day, and {n} is the most I send, so on some days "
            "a few will be left out.")


KEEP_COMING = "Thanks! I'll keep them coming."


def reminder_down(n):
    return f"Noted. Reply \"stop {n}\" to end these reminders, or \"pause {n}\" for a break."


def new_items_started(when, what, n):
    """Review fix X8 (experience): a "when I save a new ..." rule, said as what it is."""
    return (f"Got it: {when}, I'll send you {what}. I see new saves when a new export of your library comes in. "
            f"Reply \"stop {n}\" to end it.")


def saved_rule(n, what, word=None):
    if word:   # fix pass 3, finding 69: their own word back
        return f"Saved. Say \"{word}\" whenever you want one (or \"run {n}\")."
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


def which_item(n):
    """Round 7: an items answer numbers its things; a number past them."""
    return f"My last message listed {n} {'thing' if n == 1 else 'things'}. Which number?"


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


# fix pass 5, finding 87: a repeating rule whose preview was the closest only because of its length limit
def length_way_out(minutes):
    return (f" Heads up: nothing I found is under {minutes} minutes, so each pick may be longer. Say \"any length\" to "
            "drop the limit, or \"include YouTube\" and I'll look for shorter ones there too.")


# fix pass 6, finding 89: words that only say there is no length limit ("no, any length", "no limit on length",
# "length doesn't matter", "longer is fine"); never a must-have: code lifts the length bound instead
_NO_LIMIT = (r"any (?:length|duration)|drop the (?:length |time )?limit|no (?:length |time |duration )?limit"
             r"(?: on (?:the )?(?:length|time|duration))?|(?:the )?(?:length|duration) (?:doesn['’]?t|does not) matter"
             r"|(?:it )?doesn['’]?t matter how long|longer (?:ones )?(?:is|are) (?:fine|ok|okay)"
             r"|(?:they|it) can be (?:any length|longer)")
NO_LENGTH_LIMIT = re.compile(r"\b(?:" + _NO_LIMIT + r")\b", re.I)
ANY_LENGTH = re.compile(r"^\W*(?:(?:no|nah|nope|ok|okay|sure|yes|fine|actually)[\s,.!]+)*(?:" + _NO_LIMIT + r")"
                        r"(?:\s+(?:is|are|works?)(?:\s+(?:fine|ok|okay|good))?)?(?:[\s,.!]+(?:please|thanks))?\W*$", re.I)
INCLUDE_YOUTUBE = re.compile(r"^\W*(?:(?:ok|okay|sure|yes)[\s,.!]+)?(?:include youtube|add youtube|youtube too|"
                             r"youtube as well|look on youtube|include youtube too|include youtube as well|"
                             r"try youtube)(?:\s+too)?(?:[\s,.!]+please)?\W*$", re.I)


# checker of fix pass 6: words that say every rule ("stop everything", "pause all of them", "stop texting me")
ALL_RULES_SAID = re.compile(r"\b(?:all|every|everything|both|any more|anymore|them|altogether|texting|messaging|"
                            r"all of them)\b", re.I)
# checker of fix pass 6: a limit said for one request only, read as a statement about the person
ONE_TIME_ONLY = ("That sounds like it's for one request, so I haven't changed your settings. Say it with what you "
                 "want, like \"pasta recipes, no YouTube\".")


def reminder_fixed(number):
    """Fix pass 6, finding 89: a reminder keeps its own words; only when it comes can change."""
    return (f"Rule {number} is a reminder, so I can only change when it comes. You can also pause it, skip one or "
            "stop it.")


def length_changed(way, number=None, pending=False):
    what = "picks any length" if way == "any" else "looks on YouTube too, for shorter ones"
    if pending:
        return ("OK, it'll pick any length." if way == "any" else
                "OK, I'll look on YouTube too, for shorter ones.") + " Reply YES to start it."
    return f"Done: rule {number} now {what}." if number else f"Done: it now {what}."


def outside_only_head(noun=None):
    """Fix pass 5, finding 85: the opening line of an answer made only of new finds from YouTube."""
    many = (noun or (None, None))[1]
    return f"Here are some new {many} from YouTube, not from your saves:" if many else \
        "Here are some new ones from YouTube, not from your saves:"


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


IMPORT_SAME = ("That's the same export you sent me before, so there's nothing new to add. Your library stays as it "
               "is.")


def import_too_many(n):
    return (f"I've already added {n} {'export' if n == 1 else 'exports'} for you today, and that's the most I can do "
            "in a day. Please send this one again tomorrow. Your library stays as it is.")


def new_items_over_cap(goals):
    """review fix X3: a new_items rule held because the person's daily limit is used up, said in the import message."""
    names = ", ".join(f"\"{g}\"" for g in goals)
    return (f"I've reached today's limit for you, so I didn't check the new items against "
            f"{'your rule' if len(goals) == 1 else 'your rules'} {names}. I'll do it tomorrow.")


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


def compose_cut_rule(goal):
    """Review fix X7: a timed send whose answer could not be put together (the same input fails the same way)."""
    return (f"I couldn't put together your \"{goal}\" send this time, so I skipped it. The next one comes as "
            "planned.")


COMPOSE_CUT_ASK = "I couldn't put that answer together. Please ask for fewer at a time."


def missed_once(what, when):
    """Review fix S3: a one-time send the person asked for could not go out on time (the bot was offline)."""
    return f"I was offline and missed a send you asked for {when}: \"{what}\". Ask me again if you still want it."


def missed_todo(text, when):
    """Review fix S3: a to-do's reminder could not go out on time; the to-do stays on the list."""
    return f"I was offline and missed your reminder {when}: \"{text}\". It's still on your list."


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


def cant_undo(what):
    """Review fix S5: the last thing the person did cannot be taken back, and nothing older is undone instead."""
    return f"I can't take back {what}, so I left everything else as it was."


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


# ---------- round 8 (BN3 to BN5, DESIGN.md section 14): trends, the theme check, the recap ----------
# Every number below is counted by code (attention.py, digest.py). Plain words: no minutes or time spent, and nothing
# that judges what the person keeps.
def long_day(d):
    """'15 October 2026': an anchor date, always with its year."""
    return f"{d.day} {d.strftime('%B')} {d.year}"


def _posts_mention(n):
    return "no posts that mention it" if not n else f"{n} {'post that mentions' if n == 1 else 'posts that mention'} it"


def trend_rows(data, max_lines):
    """(main, parked, for_fun) rows the trends message shows within `max_lines`: the topics with any count, rising
    first, then steady, fading and too few to tell; "someday" topics go under Parked and "enjoy" ones under For fun."""
    order = {"rising": 0, "steady": 1, "fading": 2, "few": 3}
    rows = [t for t in data["topics"] if t["recent"] or t["before"] or t["liked"]]
    parked = [t for t in data["topics"] if t.get("relation") == "someday"]
    fun = [t for t in rows if t.get("relation") == "enjoy"]
    main = sorted((t for t in rows if t.get("relation") not in ("someday", "enjoy")),
                  key=lambda t: (order[t["trend"]], -t["recent"], -t["before"], t["topic"].lower()))
    room = max_lines - 1 - bool(parked) - bool(fun) - bool(data.get("direction"))
    return main[:max(room, 0)], parked, fun


def _trend_line(t):
    counts = f"{_posts_mention(t['recent'])} lately, {t['before']} before"
    if t["trend"] == "few":
        return f"• {t['topic']}: too few to tell ({counts}, {t['liked']} liked)."
    return f"• {t['topic']} is {t['trend']}: {counts}."


def _counted(t):
    return f"{t['topic']} ({_posts_mention(t['recent'])} lately)"


def trends_message(data, max_lines=7):
    """BN3: what the person kept lately against the 6 months before, topic by topic, at most `max_lines` lines."""
    anc = data["anchors"]
    names = {"instagram": "Instagram", "youtube": "YouTube"}
    plats = [p for p in ("instagram", "youtube") if p in anc] + sorted(p for p in anc if p not in names)
    if len(plats) == 1:
        upto = long_day(anc[plats[0]])
    else:
        upto = _and([f"{long_day(anc[p])} on {names.get(p, p)}" for p in plats])
    n, m = data["recent_total"], data["before_total"]
    lines = [f"What you kept lately: {n} {'post' if n == 1 else 'posts'} in the 8 weeks up to {upto}, and {m} in "
             "the 6 months before that."]
    main, parked, fun = trend_rows(data, max_lines)
    lines += [_trend_line(t) for t in main]
    if parked:
        lines.append("Parked for someday: " + ", ".join(_counted(t) for t in parked) + ".")
    if fun:
        lines.append("Just for fun: " + ", ".join(_counted(t) for t in fun) + ".")
    d = data.get("direction")
    if d:
        head = f"You said you're working toward \"{d['text']}\"."
        if d["topic"] and d["recent"]:
            lines.append(f"{head} {d['topic']}: {_posts_mention(d['recent'])} lately, {d['before']} before.")
        else:
            lines.append(f"{head} Nothing you kept lately mentions it, so I can't tell how that's going from your saves.")
    return "\n".join(lines[:max_lines])


TRENDS_NO_TOPICS = ("I don't know your topics yet, so I can't say what's rising or fading. Tell me what you're into, or "
                    "say \"set me up again\".")
TRENDS_NO_DATES = "None of what you kept has a date I can read, so I can't say what's rising or fading."
TRENDS_WHEN = "each time a new export of your library comes in"   # a trends rule's timing, as "my rules" says it
TRENDS_EVERY_EXPORT = "Reply \"every export\" and I'll send you this each time a new export of your library comes in."


def trends_rule_started(n):
    return (f"Got it: each time a new export of your library comes in, I'll send you what you've been into lately. "
            f"Reply \"stop {n}\" to end it.")


RELATION_SAY = {"pursue": "something you're going for", "practise": "a skill you're practising",
                "someday": "parked for someday", "enjoy": "just for fun",
                "not_me": "not you, so I'll leave it out of what I say about you"}
_EXAMPLE_LABELS = ["practise", "for fun", "someday", "not me", "pursue"]


def theme_check_question(topics):
    """BN4: asked once, after the first trends answer."""
    listed = "  ".join(f"{i}. {t}" for i, t in enumerate(topics, 1))
    example = ", ".join(f"{i} {w}" for i, w in enumerate(_EXAMPLE_LABELS[:len(topics)], 1))
    return ("One question, so I read these right: what is each one to you?\n" + listed + "\n"
            f"Reply like \"{example}\" (or \"pursue\" for something you're going for). Anything else and I'll drop "
            "the question.")


def theme_check_which(n):
    return f"Which one? I listed {n}. Reply with their numbers, like \"1 practise\"."


def labels_saved(pairs):
    if not pairs:
        return "Noted."
    said = "; ".join(f"{t}: {RELATION_SAY[lb]}" for t, lb in pairs)
    first, lb = pairs[0]
    other = "someday" if lb == "pursue" else "pursue"
    tail = " Asking for it by name still finds those posts." if any(x == "not_me" for _, x in pairs) else ""
    return f"Thanks, noted. {said}.{tail} To change one, say \"{first} is {other} now\"."


def label_changed(topic, label):
    if label == "not_me":
        return f"OK: I'll leave {topic} out of what I say about you. Asking for it by name still finds those posts."
    return f"OK: {topic} is {RELATION_SAY[label]} now."


def parked_message(interests):
    if not interests:
        return "Nothing is parked yet. Say something like \"climbing is someday now\" to park a topic."
    from .profile import count_words, shown_topic
    parts = []
    for i in interests:
        n = count_words(i)
        parts.append(f"{shown_topic(i['topic'])} ({n})" if n else shown_topic(i["topic"]))
    return "Parked for someday: " + ", ".join(parts) + "."


def _times(n):
    return "once" if n == 1 else "twice" if n == 2 else f"{n} times"


def recap_rule_clause(n, name, counts, fb):
    """'1 "a pasta recipe" sent 3, stayed quiet twice with nothing new (2 made it, 1 👍)'."""
    parts = []
    if counts.get("sent"):
        parts.append(f"sent {counts['sent']}")
    if counts.get("quiet"):
        parts.append(f"stayed quiet {_times(counts['quiet'])} with nothing new")
    if counts.get("skipped"):
        parts.append(f"{counts['skipped']} skipped")
    if counts.get("snoozed"):
        parts.append(f"{counts['snoozed']} held back by a snooze")
    if counts.get("daily_limit"):
        parts.append(f"{counts['daily_limit']} past the daily limit")
    said = []
    for kind, word in (("done", "made it"), ("up", "👍"), ("harder", "too easy"), ("easier", "too hard")):
        if fb.get(kind):
            said.append(f"{fb[kind]} {word}")
    return f"{n} \"{name}\" " + ", ".join(parts) + (f" ({', '.join(said)})" if said else "")


def recap_head(since):
    return f"Your recap since {since}:"


def recap_rules(clauses):
    return "• Rules: " + "; ".join(clauses) + "."


def recap_todos(done, open_, overdue):
    left = ("none are open" if not open_ else f"{open_} {'is' if open_ == 1 else 'are'} open"
            + (f", {overdue} of them past {'its' if overdue == 1 else 'their'} due date" if overdue else ""))
    return "• To-dos: " + (f"you ticked off {done}; {left}" if done else left[:1].upper() + left[1:]) + "."


def recap_coming(entries, more=0):
    return "• Coming up: " + "; ".join(entries) + (f"; and {more} more" if more else "") + "."


def recap_calendar(n):
    return f"• I gave you {n} calendar {'link' if n == 1 else 'links'}."


def recap_library(newest, due):
    head = f"the newest thing you kept is from {newest}" if newest else "I can't date anything you kept yet"
    return "• Your library: " + head + (f"; {due}" if due else "") + "."


def recap_suggest(word, n, since):
    return (f"• You asked about {word} {n} times since {since}. Want one pick for it every Saturday at 10am? Reply "
            "\"yes\" and I'll show you a preview first.")


RECAP_NOTHING = "Nothing to report for the last 7 days: no rule sent anything and no to-do changed."
RECAP_PREVIEW_EMPTY = "There's nothing to report this week yet. On a week like that I send nothing."


def recap_preview_tail(when, first=None):
    return (f"\n\n{cap_first(when_lead(when))} I'll send you a recap like this one.{first_send(first)} Reply YES to "
            "start, or tell me what to change.")


# fix pass 3, finding 66: "once in a while" names no frequency, so the bot asks, with a default a "yes" accepts
HOW_OFTEN_ASK = ("How often would you like it? For example \"every 3 days\" or \"about twice a week\". "
                 "Or reply \"yes\" for about once a week, at a random time between 9am and 9pm.")


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
# round 10, slice W (W1): never offers "email it to me" when nothing has been written
EMAIL_ONLY_YOU = ("Tell me who it's for and what to say, like \"email my teacher that I'm sick today\", and I'll write it "
                  "for you to check.")
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


EMAIL_NOT_SET_UP = ("Email isn't set up on my side yet, so I can't send you a code or any emails. I'll keep "
                    "answering you here.")


def code_not_sent(email, changed=False):
    """Review fix X8: the code email could not be sent, on a channel where the person cannot open the outbox."""
    lead = f"I changed your email address to {email}" if changed else f"I saved {email} as your email address"
    return (f"{lead}, but I couldn't send the code to it just now. Reply \"new code\" in a little while and I'll "
            "try again.")


def code_failed_to_outbox(email, minutes, where, changed=False):
    """The code email could not be sent and was written to an outbox this person can open (the test page, the
    console). Never "I sent a code" and "I couldn't send that email" in one reply (final check, cost-failure X8)."""
    lead = f"I changed your email address to {email}" if changed else f"I saved {email} as your email address"
    tail = " Until then I won't email you." if changed else ""
    return (f"{lead}. I couldn't email the 6-digit code to it just now, so the code email is {where} instead. Text me "
            f"the code within {minutes} minutes to confirm it's yours.{tail}")


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
    if t is L.EN:   # round 9, slice C (W8): the nearest offer for a booking or a purchase, chosen by code
        if BOOK_ASK.search(text or ""):
            return UNSUPPORTED_BOOK
        if BUY_ASK.search(text or ""):
            return UNSUPPORTED_BUY
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


# fix pass 3, finding 72: a "no" to the export reminders, with other words beside it, is said back
EXPORT_DECLINED = "OK, no export reminders. Ask \"how do I export?\" any time for the steps."
NO_LEAD = re.compile(r"^\s*(?:no|nope|nah|not now|no thanks|no thank you)(?:\s*[.,!;:-]|\s+thanks?\b|\s+thank you\b|"
                     r"\s+(?:to\s+)?(?:the\s+)?(?:export\s+)?reminders?\b|\s*$)", re.I)
NO_REMINDERS = re.compile(r"\bno\s+(?:export\s+)?reminders?\b|\bdon'?t\s+remind\b|\bwithout\s+(?:the\s+)?reminders?\b|"
                          r"\bskip\s+(?:the\s+)?reminders?\b|\bno\s+to\s+the\s+reminders?\b", re.I)

# fix pass 5, finding 86: replies that only answer the setup's own question, so nothing else may answer them too
_SETUP_FILLER = set("and but so the a an my it its it's is that's thats this that all fine good ok okay sure yes yep "
                    "yeah right correct perfect great thanks thank you please for now then just i i'm im am we".split())
_CONTACT_PARTS = re.compile(
    r"\b(?:skip|no|without|don'?t need|do not need|no need for|not giving|pass on|leave out|forget)\s+(?:the\s+|an?\s+|my\s+)?"
    r"e-?mail(?:\s+address)?(?:\s+(?:part|bit|step|one))?\b"
    r"|\b(?:i\s+)?(?:don'?t|do not)\s+(?:want|need)\s+(?:to\s+give\s+)?(?:an?\s+|my\s+)?e-?mail\b"
    r"|\b(?:the\s+|my\s+)?time\s?zone(?:'s|\s+is|\s+looks)?\s+(?:is\s+)?(?:fine|right|correct|good|ok|okay|perfect|"
    r"spot on)\b|\b(?:the\s+|my\s+)?time\s?zone\b|\b(?:the\s+)?time\b(?=.*\b(?:fine|right|correct)\b)", re.I)
_REMINDER_WORDS = set("set setup up start the export exports reminder reminders remind me them those it that please do "
                      "go ahead both instagram youtube for and a sure ok okay yes yep yeah thanks thank you sounds good "
                      "great".split())


def _left_words(text):
    return [w for w in re.findall(r"[a-z']+", text.lower()) if w not in _SETUP_FILLER]


def contact_only(text):
    """'skip the email, time zone is fine', 'no email, the time zone is right': the reply says only that the email can
    wait and the time zone is right, with nothing else to act on."""
    if not _CONTACT_PARTS.search(text or ""):
        return False
    return not _left_words(_CONTACT_PARTS.sub(" ", text))


def reminders_only(text):
    """'set up the export reminders', 'remind me', 'set them up please': the rest of a yes to the export reminders
    says nothing more than yes."""
    words = re.findall(r"[a-z']+", (text or "").lower())
    return bool(words) and all(w in _REMINDER_WORDS or w in _SETUP_FILLER for w in words)


def profile_changed(changes, skipped=False):
    """'Noted: Blender: past the basics; you have an air fryer.'"""
    # fix pass 3, finding 73: one plain sentence ("Noted: you usually have about 20 minutes a day, and you have an
    # Instant Pot."), not a list joined with semicolons
    if changes:
        msg = "Noted: " + (changes[0] if len(changes) == 1 else
                           ", ".join(changes[:-1]) + ", and " + changes[-1]) + "."
    else:
        msg = PROFILE_NOTED
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


# fix pass 4, finding 77: a rule with new videos from YouTube as well never runs dry; the preview and the start line say
# where its picks come from instead of a heads-up
OUTSIDE_RULE_NOTE = " Picks come from your saves, with related videos from YouTube as well, so it won't run dry."
OUTSIDE_RULE_ONLY = " Picks come from YouTube, not from your saves."


def supply_note(n):
    """Finding 19: a repeating rule whose supply in the library is tiny."""
    if n == 0:
        return " Heads up: I don't see anything in your library that clearly fits, so this will run dry quickly."
    return (f" Heads up: I only see about {n} {'post' if n == 1 else 'posts'} in your library that "
            f"{'fits' if n == 1 else 'fit'}, so this will run dry quickly.")


def supply_note_close(n):
    """Review fix X10: nothing fits clearly; the count is of the posts that come close."""
    if n == 0:
        return supply_note(0)
    return (f" Heads up: I only see about {n} {'post' if n == 1 else 'posts'} in your library that "
            f"{'comes' if n == 1 else 'come'} close, so this will run dry quickly.")


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


# ---------- round 7, finding 92: a follow-up that changes the request ----------
def _change_words(ch, who):
    out = []
    if ch.get("avoid"):
        out.append("leaving out anything about " + and_words(ch["avoid"]))
    if who:
        out.append("not from " + and_words(who))
    if ch.get("wanted_names"):
        out.append("only from " + and_words(ch["wanted_names"][:3]))
    if ch.get("platform"):
        out.append("only from " + {"instagram": "Instagram", "youtube": "YouTube"}[ch["platform"]])
    if ch.get("shorter"):
        out.append("shorter ones")
    if ch.get("easier"):
        out.append("the easiest first")
    elif ch.get("newest"):
        out.append("the newest first")
    elif ch.get("oldest"):
        out.append("the oldest first")
    return out


def changed_intro(goal, ch, who):
    """'Here's what I found in your saves for basic Blender tutorials, leaving out anything about donut.' Built from
    the merged request, never from the person's message."""
    words = _change_words(ch, who)
    g = " ".join((goal or "").split())
    # checker: "else" only when something shown was ruled out (not for "ok and for dinner?" alone)
    other = " else" if not ch.get("add") or ch.get("others") or ch.get("avoid") or who else ""
    head = f"Here's what{other} I found in your saves for {g}" if g and len(g.split()) <= 6 else \
        f"Here's what{other} I found in your saves"
    return head + (", " + ", ".join(words) if words else "") + "."


def changed_what(goal, ch, who):
    """Live fix pass, round 8 (finding 101): the merged request in plain words ('basic blender tutorials, leaving out
    anything about donut'), for the nothing-clear line; 'your request, ...' for a goal of more than 6 words."""
    words = _change_words(ch, who)
    g = " ".join((goal or "").split())
    what = g if g and len(g.split()) <= 6 else "your request"
    return what + (", " + ", ".join(words) if words else "")


def changed_none(goal, ch, who):
    """Nothing is left once the change is applied: said plainly, never a rejected pick again."""
    words = _change_words(ch, who)
    g = " ".join((goal or "").split())
    what = f" for {g}" if g and len(g.split()) <= 6 else ""
    return f"I found nothing else in your saves{what}" + (", " + ", ".join(words) if words else "") + "."


# checker, round 7: "the opposite" names no change code can read; "what about ones from X" with no X in the library
CHANGE_SAY_HOW = ("I'm not sure what the opposite would be here. Tell me what to change, like \"something shorter\", "
                  "\"not from that creator\" or \"anything else\".")
CHANGE_NO_CREATOR = "I found nothing from that creator in your saves."


def no_date_for(name):
    """Checker, round 7: "remind me two days before its deadline" when the post gives no date for it."""
    return (f"The post gives no date for {name}, so I can't count back from it. Tell me a day, like \"remind me about "
            f"it on Friday\", and I'll remind you then.")


def date_passed_for(name, note):
    return f"{name}: {note}, so I didn't set a reminder."


def date_too_near(name, day):
    return f"{name}'s date is {day}, sooner than that, so I didn't set a reminder. Tell me when you'd like one."


# ---------- round 8 (DESIGN.md section 13): rules beyond timing ----------
def before_words(days):
    """'the day', 'a week', '3 days': how long before a thing's date a reminder comes."""
    return "the day" if days == 1 else ("a week" if days == 7 else f"{days} days")


def deadline_set(name, first, days, deadline, day, far, n):
    """BN1: 'OK. I'll remind you about NASA L'SPACE Academy on Friday 27 November at 9am, 3 days before its deadline,
    30 November (in 16 days).'"""
    what = "its deadline" if deadline else "the date in its post"
    return (f"OK. I'll remind you about {name} {first}, {before_words(days)} before {what}, {day} ({far}). "
            f"Reply \"stop {n}\" to cancel.")


def deadline_soon(name, first, days, deadline, day, far, n):
    """BN1: the moment asked for has passed but the date has not: the next 9am."""
    what = "deadline" if deadline else "date"
    return (f"OK. {name}'s {what} is {day} ({far}), less than {before_words(days)} away, so I'll remind you {first}. "
            f"Reply \"stop {n}\" to cancel.")


def deadline_today(name, day):
    return f"{name}'s date is today, {day}, so it's too late for a reminder before it. I didn't set one."


def deadline_ask(name):
    """BN1: the post gives no date: one question; the next message is read for a date."""
    return f"The post doesn't say when {name} closes. Tell me the date, like \"dec 5\", and I'll set the reminder."


def deadline_head(name, deadline, day, far):
    """BN1: the head line of the reminder when it comes."""
    what = "deadline" if deadline else "date"
    return f"Reminder: {name}'s {what} is {day} ({far})."


QUIET_EMPTY_NOTE = " On a day with nothing new I'll stay quiet."


def empty_quiet_line(goal, since, n):
    """BN2: the one line on the first empty day after a send with picks; then nothing until there is something."""
    when = f" since {since}" if since else ""
    return f"Nothing new for \"{goal}\"{when}. I'll stay quiet until there is. \"run {n}\" asks now."


def empty_quiet_last(goal):
    return f"Nothing new for \"{goal}\" this time. {LAST_SEND}"


def if_empty_changed(way, n=None):
    """BN2: "tell me even if there's nothing" / "don't text me if there's nothing" for a preview or the rule just
    started."""
    said = ("On a day with nothing new I'll tell you so." if way == "say"
            else "On a day with nothing new I'll stay quiet.")
    return f"OK. {said}" + (" Reply YES to start it." if n is None else f" (rule {n})")


def rule_finished(n):
    return f"Rule {n} is finished."


def overdue_nudge(text, when, n):
    """BN2: the one nudge about a to-do past its due time."""
    return f"\"{text}\" was due {when}. Reply \"done {n}\", \"tomorrow\" or \"drop it\"."


def overdue_moved(text, when):
    return f"OK. \"{text}\" is now due {when}."


def overdue_dropped(text):
    return f"OK. I took \"{text}\" off your list."


OVERDUE_OFF = "OK. I won't nudge you about to-dos that are past due. Say \"overdue nudges on\" to have them back."
OVERDUE_ON = "OK. When a to-do is a day past due, I'll nudge you once."


# ---------- round 8, slice B: integrations (DESIGN.md section 15): export, share ----------
def export_where(path):
    """The export folder as the person reads it: its place under MVP_HOME ("outbox/1a2b3c4d5e6f/export-2026-11-12")."""
    import os
    from . import config
    try:
        rel = os.path.relpath(path, config.HOME)
    except ValueError:
        rel = path
    return path if rel.startswith("..") else rel


def export_done(n_saves, where):
    return (f"I saved a copy of your data: your rules, your lists, what I know about you, the answers I sent you, and "
            f"the list of your {n_saves} saves (links and dates only, no post text). It's in the folder {where} on the "
            f"bot's computer. Say \"email it to me\" and I'll send you the files.")


def export_lists_done(n, where):
    return (f"I saved your lists ({n} to-do{'s' if n != 1 else ''}) as two files: todos.csv, a table a to-do app can "
            f"import, and todos.md, a page to read. They're in the folder {where} on the bot's computer. Say \"email "
            f"it to me\" and I'll send them to you.")


EXPORT_LISTS_EMPTY = "Your lists are empty, so there's nothing to export yet. Add something with \"add … to my list\"."


def export_emailed(to, via, err, where, left=()):
    if via == "smtp":
        msg = f"I emailed your files to {to}."
    elif err:
        msg = f"I couldn't send the email just now, so I put it {where} instead."
    else:
        msg = f"Email isn't connected here, so I didn't send it. The email with your files is {where}."
    if left:
        msg += f" {' and '.join(left)} is too big to email (over 5 MB), so it's only in the folder."
    return msg


# ---------- round 9, slice D (C1, DESIGN.md section 16.D): an action past its daily limit ----------
# A slice adds its action's plain words here ("mailbox.send": "emails"); with none, the line says "this".
ACTION_CAP_LABEL = {}


def over_action_cap(label, n):
    if label:
        return f"I've reached my limit of {n} {label} a day for you. I can do more tomorrow."
    return f"I've reached my limit for this today ({n} a day). I can do it again tomorrow."


# ---------- round 9, slice A (DESIGN.md section 16.A): emails to other people, a link to yourself ----------
ACTION_CAP_LABEL.update({"email.draft_link": "email links", "mailbox.send": "emails", "mailbox.draft": "drafts"})
# W1: a model's small talk that claims an outcome the bot cannot see is never shown
CHAT_CLAIM = re.compile(r"\b(?:I'?ve|I have|I)\s+(?:just\s+|already\s+)?(?:sent|emailed|cancell?ed|canceled|booked|"
                        r"ordered|bought|paid|applied|signed you up|unsubscribed you|reserved|purchased)\b", re.I)
CHAT_NO_CLAIM = "I haven't sent, booked or bought anything. Tell me what you'd like and I'll show you what I can do."
PLACEHOLDER = "(fill this in)"
DRAFT_HEAD = "Here's the email. Nothing has been sent."
DRAFT_NEW_VERSION = "Here's the new version. Nothing has been sent."
DRAFT_SIGN_ASK = "How should I sign your emails? Reply with your name, like \"Alex\", or \"no name\"."
DRAFT_SAY_ASK = "What should it say? Tell me in your own words, like \"the kitchen sink is broken\"."
DRAFT_SENSITIVE = "I left out the post's words because it's on a personal topic."
DRAFT_REST_IN_POST = "(The rest is in the post: {url})"
DRAFT_COPY_IT = "You can copy the email above into your mail app."
DRAFT_CHANGE_HINT = "To change it: \"say ...\", \"subject: ...\", \"to: ...\", \"remove the link\", or \"cancel\"."
DRAFT_ONE_AT_A_TIME = "I can write to one person at a time. Who first?"
DRAFT_NOT_READY = "The email isn't finished yet. Answer my question above first, or say \"cancel\"."
DRAFT_STILL_OPEN = "Your email draft is still open: say \"show the draft\" to see it."
DRAFT_YES = "To send it, tap the link above and press Send in your mail app. Or tell me what to change."
DRAFT_YES_MAILBOX = "To send it, reply \"send\". Or tell me what to change."
DRAFT_THANKS = "Thanks."
DRAFT_DROPPED = "OK, I've dropped it. Nothing was sent. The link I sent still opens it, so just don't press Send."
DRAFT_DROPPED_UNSHOWN = "OK, I've dropped it. Nothing was sent."
PREVIEW_STILL_OPEN = "Your rule preview is still waiting: reply YES to start it."
DRAFT_TOO_MANY_CHANGES = "That's 5 changes. Tell me the whole text you want, like: instead say ..."
DRAFT_NO_TONE = ("I can't rewrite it in a new tone yet. Tell me the words to use, like: instead say I'll be late on "
                 "Friday.")
DRAFT_POST_ADDRESS = "The post gives an address. I only write to an address you type yourself."
DRAFT_NOTHING_SHOWN = ("I haven't sent you anything to put in an email yet. Ask me for something first, or tell me what "
                       "the email should say.")
DRAFT_SEND_LINK = "I can't send from your address. Tap the link above and press Send in your mail app."
DRAFT_SAVE_LINK = ("I can't save to your Drafts folder. Tap the link above: it opens the email in your mail app, where "
                   "you can save it as a draft.")
HOLD_STOPPED_BY_CHANGE = "That stopped the send I had waiting. Reply \"send\" to send this version."
# (who it is for is never repeated: DESIGN.md section 15)
SHARE_EMAIL_OFFER = "Or say \"email it to\" and their email address, and I'll write the email."
SELF_LINK = ("Here it is as an email to yourself. Tap to open it in your mail app, then send it to yourself or save it "
             "as a draft:")


def draft_who(whose):
    return f"Who should it go to? Reply with {whose} email address, or \"blank\" to pick them in your mail app."


def draft_to_line(to):
    return f"To: {to}" if to else "To: (you pick them in your mail app)"


def draft_which_address(two):
    return f"Who should it go to: {two[0]} or {two[1]}?"


def fill_first(label):
    return f"Fill in the {label} first: reply \"{label} 12345\", or \"remove it\"."


def draft_link_message(link, sender=None):
    if sender:
        return f"Reply \"send\" to send it from {sender}. Or tap to send it yourself:\n{link}\n{DRAFT_CHANGE_HINT}"
    return f"Tap to open it in your mail app, check it, and press Send there:\n{link}\n{DRAFT_CHANGE_HINT}"


_DAY_NAMES = {d.lower(): d for d in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")}


# W4: the operator's own mailbox (amendment A-013). Times are the person's local clock ("6:04 pm").
MAILBOX_STOPPED = "Stopped. Nothing was sent. Reply \"send\" when you're ready."
MAILBOX_NEEDS_TO = "I need an address to send it to. Say \"to:\" and their email address."
MAILBOX_OUTLOOK = ("Outlook.com doesn't allow app passwords any more, so I can't send from it. Tap the link to send it "
                   "yourself.")
MAILBOX_ERRORS = {
    "auth": "Your mailbox refused my sign-in, so nothing was sent. Tap the link to send it yourself.",
    "address": "The address was refused, so nothing was sent. Check it and say \"to: <address>\".",
    "reach": "I couldn't reach your mailbox, so nothing was sent.",
    "unknown": "I may or may not have sent it. Check your Sent folder before you ask me again.",
}


# A5: a draft in the operator's own Drafts folder
MAILBOX_DRAFT_FAILED = {
    "auth": "I couldn't save it to your Drafts folder: your mailbox refused my sign-in.",
    "reach": "I couldn't save it to your Drafts folder: I couldn't reach your mailbox.",
    "folder": "I couldn't save it: I couldn't find your Drafts folder.",
    "server": "I couldn't save it to your Drafts folder: your mailbox said no.",
}
MAILBOX_DRAFT_USE_LINK = "Tap the link above to open it in your mail app instead."
MAILBOX_UNDRAFTED = "I deleted the draft from your Drafts folder"
MAILBOX_UNDRAFT_FAILED = "I couldn't delete the draft from your Drafts folder just now, so please delete it there"


def mailbox_drafted(to, can_undo):
    head = (f"I saved it in your Drafts folder ({to} is filled in). Nothing has been sent." if to else
            "I saved it in your Drafts folder. Nothing has been sent.")
    return head + (" Reply \"undo\" within 10 minutes to take it out again." if can_undo else
                   " I can't take it out again from here, so delete it in Drafts if you change your mind.")


def mailbox_held(to, when):
    return f"Sending to {to} at {when}. Reply \"undo\" before then to stop it."


def mailbox_already_held(when):
    return f"It's already waiting to go at {when}. Reply \"undo\" to stop it."


def mailbox_already_sent(when):
    return f"I already sent that one at {when}."


def mailbox_stale(when):
    return f"That draft is from {when}. Reply \"send\" if it's still right."


def mailbox_cap(n, link):
    return f"I've sent {n} emails for you today, which is my limit. Tap to send this one yourself:\n{link}"


def mailbox_accepted(to, when):
    return f"Your mail server accepted the email to {to} at {when}. I can't unsend it."


def mailbox_cant_unsend(to, when):
    return f"I can't unsend an email. It went to {to} at {when}."


# round 9 checks (DESIGN.md section 16.A): a question is never the yes; one send waits at a time; "unknown" stays unknown
DRAFT_SEND_ASKED = "Nothing has been sent yet. Reply \"send\" when you want it to go."


def mailbox_cant_stop_unknown(masked):
    return (f"I can't stop it now. I may or may not have sent the email to {masked}. Check your Sent folder before "
            "you ask me again.")


def mailbox_other_waiting(to, when):
    return (f"Your email to {to} is still waiting to go at {when}. Reply \"send\" again once it has gone, or \"undo\" "
            "to stop it.")


def mailbox_offline(who, when):
    return f"I didn't send your email to {who} at {when} because I was offline. Reply \"send\" to send it now."


def mailbox_restarted(masked):
    return (f"I may or may not have sent the email to {masked} before I restarted. Check your Sent folder before you "
            "ask me again.")


def draft_no_schedule(when):
    w = " ".join(_DAY_NAMES.get(x.lower().rstrip("s"), x.lower()) for x in str(when or "").split())
    return f"I can't email other people on a schedule. I can send it to you {w or 'then'}, so you can forward it."


# ---------- round 9, slice B (W5, W6, DESIGN.md section 16.B): the cancel helper ----------
# The bot never signs in as the person, never says a subscription is cancelled or done, and never sets a follow-up
# by itself: it offers one and the person says when.
CANCEL_OFFER_CHECK = "Want a reminder to check it went through? Tell me when, like \"friday\"."
CANCEL_OFFER_CALL = "Want a reminder to call? Tell me when, like \"tomorrow at 10am\"."
CANCEL_WHICH = "Which one? Tell me the name, like \"cancel my Spotify\"."
CANCEL_WHICH_COMPANY = "Which company is it? Tell me the name and I'll find the way out."
CANCEL_WHICH_GYM = "Which gym?"
CANCEL_MEMBER_NAME = "What name is the membership under? I only use it for the notice."
CANCEL_CARD = "I can't help cancel a card or a bank account. Call the number on the back of the card."
CANCEL_PASSWORD = ("No. I never sign in as you and I never need your password. If you sent a real password here, please "
                   "change it. I find the way out, write what's needed, and remind you.")
CANCEL_WHEN_AGAIN = "When should I remind you? Tell me a day, like \"friday\" or \"tomorrow at 6pm\"."
CANCEL_NO_REMINDER = "OK, no reminder."
CANCEL_SAID_DONE = "Good. I've stopped the check reminder."
CANCEL_SAID_DONE_NO_RULE = "Good, thanks for telling me."
CANCEL_LEFT = "OK, I've left it."
CANCEL_OTHER_BILLING = "If you pay for it through Apple, Google Play or another company, you end it there instead."
CANCEL_TO_HINT = "(type their email address; their website or your contract has it)"
CANCEL_FILL = "(fill this in)"


def cancel_web(name, steps, checked):
    lines = [f"{name} cancels on its website. I can't do it for you, because I never sign in as you. Here's where it is:"]
    lines += [f"{i}. {s}" for i, s in enumerate(steps, 1)]
    if checked:
        lines.append(f"(From {name}'s help page, checked {checked}.)")
    return lines


def cancel_store(store_name, path, url, note):
    where = "in your Apple account" if store_name == "Apple" else "in the Play Store"
    msg = f"{store_name} subscriptions cancel {where}: {path}."
    if url:
        msg += f" Or open {url} ."
    if note:
        msg += f" {note}"
    return msg


def cancel_phone(name, phone, checked):
    return (f"{name} cancels by phone. Call {phone} (checked {checked}). You can say: \"I'm calling to cancel my "
            f"subscription, effective today. Please give me a confirmation number.\"")


def cancel_ask_billing(name):
    return f"How do you pay for {name}: through Apple (iPhone), Google Play (Android), or their website?"


def cancel_web_unchecked(name):
    return (f"I don't have a checked page for {name}'s website yet. Look for the account or billing page on their "
            f"website, and the cancel button there. If you can't find it, type their support address and I'll write a "
            f"cancellation email.")


def cancel_unknown(name, apple_url, play_url):
    links = " ".join(u for u in (apple_url, play_url) if u)
    first = "1. If you pay through Apple or Google Play: " + (links + "." if links else
                                                             "your phone's Settings, or the Play Store's Subscriptions.")
    return "\n".join([f"I don't have a checked way out of {name} yet. These usually work:", first,
                      "2. The account or billing page of their website.",
                      "3. A cancellation email: type their support address and I'll write it."])


def cancel_check_text(name):
    return f"Check that {name} confirmed your cancellation (look for their email)."


def cancel_call_text(name):
    return f"Call {name} to end your subscription."


def cancel_reminder_set(when, n):
    return f"OK. {cap_first(when)} I'll remind you to check. Reply \"stop {n}\" to drop it."


def cancel_call_reminder_set(when, n):
    return f"OK. {cap_first(when)} I'll remind you to call. Reply \"stop {n}\" to drop it."


def cancel_notice_head(merchant):
    """The first line of the notice's draft card (slice A's card, kind "notice")."""
    return f"Here's a cancellation notice you can send to {merchant}. Nothing has been sent."


# after the person sends the notice (W4's mailbox, or "sent" after the link): it is not over until they confirm
NOTICE_NOT_YET = "That doesn't end it yet: it ends when they confirm in writing."


# ---------- round 9, slice C (W7, W8, V1; DESIGN.md section 16.C): offers, acting on a saved post, the things ----------
# Never "booked", "ordered", "bought", "applied", "signed up" or "registered" about the person: the bot does none of it.
OFFERS_NONE = "OK. They're still in your saves if you want them later."
OFFER_DONE_ALREADY = "I've done that one already. Tell me what else you'd like."


def offers_which(n):
    """W7: a number past the offers."""
    if n == 1:
        return "I offered 1 thing. Reply 1, or \"none\"."
    return f"I offered {n} things. Reply " + ", ".join(str(i) for i in range(1, n)) + f" or {n}."


def offers_reply_line(n):
    return "Reply 1, or \"none\"." if n == 1 else \
        "Reply " + ", ".join(str(i) for i in range(1, n + 1)) + ", \"all\", or \"none\"."


def undo_line(what):
    return f"Reply \"undo\" within 10 minutes to take {what} off."


def undo_kept(what):
    """W8: "undo" after a menu's "all": what an undo cannot take back is named, never silently left."""
    return f"I can't take back {what}, so that stays."


POST_LINK_HEAD = "The post:"
DONE_HEAD = "Here's what I set up:"


def apply_head(name, source):
    return f"I can't fill in or send the application myself, but here's what I can set up for {name} ({source}):"


APPLY_CANT = "I can't fill in or send the application myself."
APPLY_DONE_END = "I didn't apply for you: you do that on their site."


def apply_deadline_offer(deadline, day, at_text, days):
    what = "Its deadline" if deadline else "Its date"
    if not at_text:
        return f"{what}, {day}, on your calendar."
    return f"{what}, {day}, on your calendar, and a reminder {at_text}, {before_words(days)} before."


def apply_checklist_offer(lines):
    return "A checklist from the post's own words: " + ", ".join(lines) + "."


def apply_passed(deadline, day):
    return f"{'Its deadline' if deadline else 'Its date'}, {day}, has passed."


def done_deadline(deadline, day):
    return f"• {'Deadline' if deadline else 'Its date'} {day}: tap to add it to your calendar:"


def done_reminder(at_text, n):
    return f"• A reminder {at_text} (rule {n})"


def done_checklist(lines, where):
    n = len(lines)
    return f"• {n} {'thing' if n == 1 else 'things'} on your list \"{where}\": " + ", ".join(lines)


def book_head(name, tables):
    return f"I can't book {'tables' if tables else 'for you'}. Here's what I can do for {name} (from your saves):"


def maps_offer(url):
    return f"Find it in Google Maps: {url}"


MAPS_NAME_ONLY = "I searched for the name only; add the city in Maps if it finds the wrong place."


def hold_offer(when):
    return f"Put {when} on your calendar as a hold."


def book_ask_time(day):
    return f"What time on {day}? Say a time like \"7pm\" and I'll put a hold on your calendar."


BOOK_ASK_WHEN = "To hold a time on your calendar, tell me when, like \"saturday at 7\"."
BOOK_EMAIL_HINT = "To ask them by email, type their address, like \"email bookings@example.com ...\"."
BOOK_DONE_END = "I didn't book anything: that's up to you and them."
HOLD_PASSED = "That time has already passed, so I didn't put a hold on your calendar."


def post_number(number):
    return f"The post gives this number: {number}. I can't call for you."


def done_maps(name, url):
    return f"• {name} in Google Maps: {url}"


def done_hold(when):
    return f"• A hold for {when}: tap to add it to your calendar:"


BUY_CANT = "I can't buy things or pay for you."
NO_CHECKLIST = "That post doesn't list what you need in its own words, so there's no checklist to add."


def buy_ingredients(names):
    n = len(names)
    return (f"I can't buy things or pay for you. I put the {n} {'ingredient' if n == 1 else 'ingredients'} on your "
            f"shopping list: " + ", ".join(names) + ".")


def buy_product(name, price=None, month=None):
    note = f" (it said {price} in {month}, so check today's price)" if price and month else ""
    return f"I can't buy things for you. Here's {name} from the post{note}:"


BUY_LIST_OFFER = "Want it on your list? Reply 1."


def done_todo(line):
    return f"• {line}"


# the nearest thing the bot can do, when a book or buy request is not about something it showed (docs/06 step 4)
UNSUPPORTED_BOOK = "I can't book. I can put it on your calendar or remind you, if you tell me when."
UNSUPPORTED_BUY = "I can't buy things. I can add it to your list or send you the link."
BOOK_ASK = re.compile(r"\b(?:book|reserve|reservation)\b", re.I)
BUY_ASK = re.compile(r"\b(?:buy|purchase|pay for|order(?!\s+(?:to|of|by)\b))\b", re.I)


# V1: the things of an items answer
def things_added(names, where, already=(), rest=0, listed=False):
    """'Added 6 things to your list:' and the names one a line, or 'Added 3 things to your list: A, B, C.'; what was
    on the list already, and what is left past the first 12."""
    n = len(names)
    head = f"Added {n} {'thing' if n == 1 else 'things'} to {where}"
    if listed and n > 3:
        msg = head + ":\n" + "\n".join(f"{i}. {x}" for i, x in enumerate(names, 1)) + \
            "\nEach one links to the post it came from."
    else:
        msg = head + ": " + ", ".join(names) + "."
    if already:
        msg += f" \"{already[0]}\" was already on it." if len(already) == 1 else \
            f" {len(already)} were already on it: " + ", ".join(f"\"{x}\"" for x in already) + "."
    if rest:
        msg += f" That's the first {n}. Say \"add the rest\" for the other {rest}."
    return msg + " " + undo_line("them" if n > 1 else "it")


def things_all_on(where):
    return f"They're all on {where} already."


def things_count_off(n):
    return f"I listed {n} things. Reply \"add them all\" for all {n}, or give the numbers."


def things_later(first, n, rule_n):
    return (f"OK. {cap_first(first)} I'll send you the {n} things again, with their links. Reply \"stop {rule_n}\" "
            f"to cancel.")


def things_dates(found, missing, passed):
    """(head, tail): found is [(name, day words)]; 'Tap to add each:' is followed by the links, then the tail."""
    k = len(found)
    if not k:
        head = "None of them has a date ahead that I can read, so there's nothing to put on your calendar."
    else:
        names = _and([f"{name} ({day})" for name, day in found])
        head = (f"1 of them has a date I can read: {names}. Tap to add it:" if k == 1 else
                f"{k} of them have a date I can read: {names}. Tap to add each:")
    tail = []
    if missing:
        tail.append((f"The other {missing} {'has' if missing == 1 else 'have'} no date in their words." if k and
                     not passed else f"{missing} of them {'has' if missing == 1 else 'have'} no date in their words."))
    if passed:
        tail.append(f"{passed} of them {'has' if passed == 1 else 'have'} a date that has passed.")
    return head, " ".join(tail)


def thing_words(name, about, when, source_title, creator):
    """V1: a question about a numbered thing, answered from the thing's own words (no model call)."""
    w = f" ({when})" if when else ""
    said = (f"{name}: \"{about}\"{w}. The post doesn't say more about it." if about else
            f"The post names {name}{w} and doesn't say more about it.")
    if source_title:
        said += f" It's in \"{source_title}\"" + (f" by {creator}" if creator else "") + ":"
    return said


# ---------- round 9, slice D (C2, C3; DESIGN.md section 16.D): lists named after an app, the operator's Mac ----------
ACTION_CAP_LABEL.update({"mac.reminder": "reminders on your Mac", "mac.event": "events on your Mac"})
SETTINGS_PATH = "System Settings › Privacy & Security › Automation"
# why a to-do or an event did not go to the place the person named; each is the start of a sentence
PLACE_CLAUSE = {
    "no_connector": "I can't reach {app}",
    "operator": "{short} on my Mac only works for the person who runs me",
    "unreachable": "I can't reach a Mac from where I'm running",
    "not_connected": "{short} on your Mac isn't connected yet",
    "off": "{short} on your Mac is turned off",
    "broken": "I've stopped using {short} on your Mac after 3 failures in a row",
    "blocked": "Your Mac blocked me from {short}",
    "timeout": "{short} didn't answer in time",
    "failed": "{short} on your Mac gave an error",
    "no_calendar": "I couldn't find a calendar called \"Digest\" on this Mac",
    "scheduled": "I only add to {short} on your Mac after you say yes",
    "cap": "I've reached my limit of {n} {nouns} a day on your Mac",
}
PLACE_AFTER = {
    "not_connected": " Text me \"connect my mac\" to set it up.",
    "off": " Text me \"check my mac\" to turn it back on.",
    "broken": " Text me \"check my mac\" when it's ready.",
    "blocked": f" Turn it on in {SETTINGS_PATH}.",
    "no_calendar": " Make one in Calendar, then text me \"check my mac\".",
}


def place_clause(code, app, short, n=None, nouns=None):
    return PLACE_CLAUSE.get(code, PLACE_CLAUSE["failed"]).format(app=app, short=short, n=n, nouns=nouns)


def added_here(texts, name, due_text=None):
    """What went on the bot's own list instead: 'I added "milk" to your list here, called "notion".'"""
    called = "" if name in (None, "todo") else f", called \"{name}\""
    due = f" I'll remind you {due_text}." if due_text else ""
    if len(texts) == 1:
        return f"I added \"{texts[0]}\" to your list here{called}.{due}"
    return f"I added {len(texts)} things to your list here{called}: " + "; ".join(texts) + "." + due


def place_fell_back(clause, texts, name, due_text=None, after=""):
    return f"{clause}, so {added_here(texts, name, due_text)}{after}"


def place_link_instead(clause, after=""):
    return f"{clause}, so here's a link instead.{after}"


def place_ask_todo(titles, notes, list_name, due_text):
    """The preview of reminders: every title (and its link) exactly as it will be added."""
    where = f"your Reminders list \"{list_name}\"" if list_name else "Reminders"
    due = f", due {due_text}" if due_text else ""
    if len(titles) == 1:
        head = f"I'll add \"{titles[0]}\" to {where} on your Mac{due}."
        if notes[0]:
            head += f"\nWith its link: {notes[0]}"
        return head + "\nReply \"yes\" to add it, or \"no\" to leave it."
    lines = [f"I'll add these {len(titles)} to {where} on your Mac{due}:"]
    lines += [f"• {t}" + (f" ({u})" if u else "") for t, u in zip(titles, notes)]
    return "\n".join(lines) + "\nReply \"yes\" to add them, or \"no\" to leave them."


def place_ask_event(title, when, notes, calendar):
    out = f"I'll put \"{title}\" in your \"{calendar}\" calendar on your Mac, {when}."
    if notes:
        out += f"\nWith the note: {notes}"
    return out + "\nReply \"yes\" to add it, or \"no\" to leave it."


PLACE_LEFT = "OK, I didn't add anything."


def place_already(short):
    return f"I already added that to {short} on your Mac today."


def place_done_todo(titles, list_name, due_text):
    where = f"your Reminders list \"{list_name}\"" if list_name else "Reminders"
    n = len(titles)
    what = f"\"{titles[0]}\"" if n == 1 else f"{n} items"
    due = f" Reminders will remind you {due_text}; I won't send my own reminder." if due_text else ""
    return (f"Added {what} to {where}.{due} Reply \"undo\" within 10 minutes to remove "
            f"{'it' if n == 1 else 'them'}.")


def place_done_event(title, calendar, when):
    return (f"Added \"{title}\" to your \"{calendar}\" calendar, {when}. Reply \"undo\" within 10 minutes to remove "
            f"it.")


def place_undone(n, short, title=None):
    if n == 1 and title:
        return f"I took \"{title}\" out of {short} on your Mac"
    return f"I took {'that' if n == 1 else f'those {n}'} out of {short} on your Mac"


def place_undo_failed(short, titles):
    if len(titles) == 1:
        return f"I couldn't take it out of {short} just now. It's \"{titles[0]}\"; delete it there."
    return (f"I couldn't take {len(titles)} of them out of {short} just now: "
            + ", ".join(f"\"{t}\"" for t in titles) + ". Delete them there.")


PLACE_UNDO_GONE = "Those are already gone from your Mac, so there was nothing to take out."

# the Mac, by text: connect, check, what are you connected to, disconnect, from now on
MAC_ONLY_OPERATOR = "Reminders and Calendar on my Mac are only for the person who runs me."
MAC_TESTER_INSTEAD = " I keep your lists here, and I give you a calendar link you tap, with no sign-in."
MAC_UNREACHABLE = "I can't reach a Mac from where I'm running. Run me on your Mac to use Reminders and Calendar."
MAC_CONNECT = ("I can add to Reminders and Calendar on this Mac, with no password.\n"
               "1. In Calendar on the Mac, make a calendar called \"Digest\" in your iCloud account, so it reaches your "
               "phone.\n"
               "2. Text me \"check my mac\". The Mac may ask \"Terminal wants to control Reminders\" (and Calendar): "
               "click OK on the Mac.\n"
               "I'll always show you what I'm about to add and wait for your yes.")
MAC_CONNECTED = "Reminders and Calendar are connected on this Mac. Events go to your \"Digest\" calendar."
MAC_CONNECTED_NO_CALENDAR = ("Reminders is connected on this Mac. I couldn't find a calendar called \"Digest\", so "
                             "events still come as a link. Make one in Calendar, then text me \"check my mac\" again.")


def mac_check_failed(code, app):
    app = app or "Reminders"
    if code == "blocked":
        return (f"Your Mac blocked me from {app}. Turn it on in {SETTINGS_PATH}, then text me \"check my mac\" "
                f"again.")
    if code == "timeout":
        return f"{app} didn't answer in time. Make sure the Mac is awake, then text me \"check my mac\" again."
    if code == "unreachable":
        return MAC_UNREACHABLE
    return f"{app} on the Mac gave an error. Text me \"check my mac\" to try again."


MAC_NOT_ON = "Reminders and Calendar on the Mac aren't connected, so there's nothing to stop."
MAC_SETTINGS_TAIL = f"To take back my access completely, go to {SETTINGS_PATH}."


def _made(reminders, events):
    parts = []
    if reminders:
        parts.append(f"{reminders} {'reminder' if reminders == 1 else 'reminders'}")
    if events:
        parts.append(f"{events} {'event' if events == 1 else 'events'}")
    return " and ".join(parts)


def mac_off(reminders, events):
    made = _made(reminders, events)
    if not made:
        return (f"I've stopped using Reminders and Calendar. I hadn't added anything there in the last 30 days. "
                f"{MAC_SETTINGS_TAIL}")
    return (f"I've stopped using Reminders and Calendar. I added {made} in the last 30 days. Reply REMOVE to delete "
            f"those, or KEEP to leave them.")


def mac_removed(reminders, events, failed):
    made = _made(reminders, events)
    out = f"I deleted the {made} I'd added." if made else ""
    if failed:
        out += (" " if out else "") + (f"I couldn't delete {failed} {'thing' if failed == 1 else 'things'} just now; "
                                       f"{'it is' if failed == 1 else 'they are'} still there.")
    return (out or "There was nothing left to delete.") + " " + MAC_SETTINGS_TAIL


MAC_REMOVE_UNREACHABLE = ("I can't reach a Mac from where I'm running, so I couldn't delete them. They're still there. "
                          + MAC_SETTINGS_TAIL)
MAC_KEPT = "OK, they stay where they are. " + MAC_SETTINGS_TAIL
MAC_DELETE_DATA = " This also stops Reminders and Calendar on the Mac. What I added there stays there."


def place_pref_set(kind, connected):
    if kind == "todo":
        out = ("OK. From now on I'll offer to put new things for your lists in Reminders on your Mac, and show you "
               "each one first. Say \"use my list here again\" to go back.")
    else:
        out = ("OK. From now on I'll offer to put events straight in your \"Digest\" calendar on your Mac, and show "
               "you each one first. Say \"use calendar links again\" to go back.")
    return out if connected else out + " It isn't connected yet: text me \"connect my mac\" to set it up."


PLACE_PREF_TODO_OFF = "OK. New things for your lists stay on your list here."
PLACE_PREF_CAL_OFF = "OK. Calendar entries come as a link you tap again."


def connected_lines(email_status, mac_line, others=None):
    lines = ["Here's where I can put things for you:", "• Your list here: always on.",
             f"• Email to you: {email_status}.", "• Calendar: a link you tap, no sign-in.",
             f"• Email to other people: {others or OTHERS_LINK}."]
    if mac_line:
        lines.append(f"• Reminders and Calendar on this Mac: {mac_line}.")
    return "\n".join(lines)


MAC_STATUS = {
    "connected": "connected",
    "not_connected": "not connected yet (say \"connect my mac\")",
    "off": "turned off (say \"check my mac\" to turn it back on)",
    "broken": "stopped after 3 failures in a row (say \"check my mac\")",
    "unreachable": "I can't reach a Mac from where I'm running",
}
MAC_DISCONNECT_HINT = "Say \"disconnect my mac\" to stop."


# the round 9 merge: "what are you connected to" says what the merged code does (slice A's card, link and mailbox)
OTHERS_LINK = "a draft you send from your mail app"
EMAIL_SELF_LINK = "not connected here, so I give you a link that opens an email to yourself"


def others_mailbox(sender, drafts_on):
    line = f"a draft I show you first, and I send it from {sender} only after you reply \"send\""
    return line + (". \"save it as a draft\" puts it in your Drafts folder" if drafts_on else "")


def email_waits(where):
    return f"not connected here, so emails wait {where}"


def email_status(address, confirmed):
    if address and confirmed:
        return f"on, to {address}"
    if address:
        return f"waiting for the 6-digit code I sent to {address}"
    return "not set up yet (tell me your email address)"


# ---------- round 9, W9 (DESIGN.md section 16.F): "what did you do for me" ----------
# Only what the bot can see: "I sent" only for an email the mail server took; "you sent" only when the person said so.
RECEIPTS_HEAD = "In the last 7 days I:"
RECEIPTS_HEAD_TODAY = "Today I:"
RECEIPTS_NOTHING = "I haven't done anything for you in the last 7 days."
RECEIPTS_NOTHING_TODAY = "I haven't done anything for you today."
RECEIPTS_WAITING = "Waiting for you:"
RECEIPTS_NOTHING_WAITING = "Nothing is waiting for you."
RECEIPT_PREVIEW_WAITING = "something I showed you to add, waiting for your \"yes\""


def _count(n, one, many=None):
    return f"{n} {one if n == 1 else (many or one + 's')}"


def receipt_emailed_you(n, day):
    return f"emailed you {_count(n, 'time')} (last {day})"


def receipt_outbox(n, day):
    return f"kept {_count(n, 'email')} for you in the outbox here, because email isn't set up (last {day})"


def receipt_self_link(n, day):
    return (f"gave you {_count(n, 'link')} that {'opens' if n == 1 else 'open'} an email to yourself (last {day}; I "
            f"can't see whether you sent "
            f"{'it' if n == 1 else 'them'})")


def receipt_sent(what, who, sender, when):
    frm = f" from {sender}" if sender else ""
    return f"sent the {what} to {who}{frm} {when}, after your \"send\" (the mail server took it)"


def receipt_person_sent(what, who, day):
    return f"wrote the {what} to {who}, and you told me you sent it ({day})"


def receipt_unknown(what, who):
    return (f"tried to send the {what} to {who}, but the connection dropped, so I can't tell whether it went. Check your "
            f"Sent folder before sending it again")


def receipt_prepared(what, who, mailbox, day):
    # (round 9 checks) "not sent", never "you haven't said send": after "send" then "undo", or a hold the bot missed
    # while offline, the person did say it
    tail = "not sent" if mailbox else "a link you open in your mail app; I can't see whether you sent it"
    return f"prepared the {what} to {who} ({day}; {tail})"


def receipt_drafts_folder(n, gone):
    out = f"saved {_count(n, 'draft')} in your Drafts folder (nothing was sent)"
    return out + (f", and removed {gone} again" if gone else "")


def receipt_calendar_links(n):
    return f"gave you {_count(n, 'calendar link')} (I can't see whether you added {'it' if n == 1 else 'them'})"


def receipt_todos(n, done, gone):
    out = f"added {_count(n, 'thing')} to your lists here"
    extra = []
    if done:
        extra.append(f"you ticked off {done}")
    if gone:
        extra.append(f"{gone} {'was' if gone == 1 else 'were'} removed")
    return out + (f" ({', '.join(extra)})" if extra else "")


def receipt_placed(n, gone, one, many, where, kind):
    if kind == "webhook":
        out = f"sent {_count(n, one, many)} {where} (I can't see what it did with {'it' if n == 1 else 'them'})"
        return out
    out = f"added {_count(n, one, many)} {where}"
    return out + (f", and removed {gone} again" if gone else "")


def receipt_cancellations(n, said_done, sent, open_, mine=0):
    parts = []
    if said_done:
        parts.append(f"you said {said_done} {'is' if said_done == 1 else 'are'} done")
    if sent:
        parts.append(f"you sent {_count(sent, 'notice')}")
    if mine:
        parts.append(f"I sent {_count(mine, 'notice')} after your \"send\"")
    if open_:
        parts.append(f"{open_} still open")
    return f"helped with {_count(n, 'cancellation')}" + (f" ({', '.join(parts)})" if parts else "")


def receipt_held(what, who, clock):
    at = f" at {clock}" if clock else ""
    return f"the {what} to {who} goes{at}. Say \"undo\" to stop it"


def receipt_open_draft(what, who):
    return f"the {what} to {who} (say \"show the draft\")"


def receipts_undo(say):
    return f"You can still undo the last thing ({say}): say \"undo\" within 10 minutes."


def receipts_agent(n):
    return f"Your agent asked me for things {_count(n, 'time')}. Say \"what did my agent ask\" to see them."


def receipt_no_draft(who):
    return f"I haven't written an email to {who} for you. To start one, say \"email {who} that ...\"."


def did_sent(what, who, sender, when):
    frm = f" from {sender}" if sender else ""
    return f"Yes. I sent the {what} to {who}{frm} {when}, after your \"send\". The mail server took it."


def did_person_sent(what, who, day):
    return f"I wrote it, and you told me you sent the {what} to {who} ({day}). I can't see your mail myself."


def did_held(what, who):
    return f"Not yet. The {what} to {who} is waiting to go out. Say \"undo\" to stop it."


def did_prepared(what, who, mailbox):
    if mailbox:
        return f"No. I wrote the {what} to {who}, and it hasn't been sent. Say \"show the draft\" to see it."
    return (f"I didn't send it: I wrote the {what} to {who} and gave you a link to send it from your mail app. I can't "
            f"see whether you sent it. Tell me \"sent\" if you did.")


def did_not_yet(what, who):
    return f"No. I started the {what} to {who}, but it isn't finished. Say \"show the draft\" to see it."


# ---------- round 9, W10 (DESIGN.md section 16.F): "do 2 for me" on the to-do list ----------
DOIT_WHICH = "Which one? Say \"do 2 for me\" (\"my list\" shows the numbers)."
DOIT_CALL = "I can't make calls. Want a reminder? Tell me when, like \"tomorrow at 10am\"."


def doit_tick(n):
    return f"Tick it off once it's done: \"done {n}\"."


def doit_buy(n):
    return (f"I can't buy things for you. It's on your list; tick it off with \"done {n}\" when you have it. Want a "
            f"reminder? Tell me when.")


def doit_none(text):
    return f"I can't do \"{text}\" for you. I can remind you if you tell me when, like \"friday\"."


def doit_ticked(text):
    return f"I ticked \"{text}\" off your list."


# ---------- round 9, E (DESIGN.md section 16.E): TickTick, Todoist and a webhook, by a setting in the environment ----
ACTION_CAP_LABEL.update({"ticktick.add": "tasks in TickTick", "todoist.add": "tasks in Todoist",
                         "webhook.post": "things sent to your webhook"})
# why a to-do did not go to the app the person named; each is the start of a sentence ({app}: "TickTick")
TOKEN_CLAUSE = {
    "no_connector": "I can't reach {app}",
    "operator": "I can't reach {app}",          # a tester: the same honest line as an app with no connector
    "unreachable": "I can't reach {app} yet",
    "off": "{app} is turned off",
    "broken": "I've stopped using {app} after 3 failures in a row",
    "refused": "{app} refused my key",
    "rate": "{app} asked me to slow down",
    "server": "{app} had a problem on its side",
    "gone": "{app} said that address doesn't exist",
    "timeout": "{app} didn't answer in time",
    "failed": "{app} gave an error",
    "partial": "{app} took only part of it, and I couldn't take that part out again (check {app})",
    "scheduled": "I only add to {app} after you say yes",
    "cap": "I've reached my limit of {n} {nouns} a day for {app}",
}


def token_after(code, key):
    word = {"ticktick": "ticktick", "todoist": "todoist", "webhook": "webhook"}.get(key, key)
    return {
        "unreachable": f" Text me \"connect my {word}\" to see how to set it up.",
        "off": f" Text me \"check my {word}\" to turn it back on.",
        "broken": f" Text me \"check my {word}\" when it's ready.",
        "refused": f" Text me \"connect my {word}\" to see how to make a new one.",
    }.get(code, "")


def token_clause(code, app, n=None, nouns=None):
    return TOKEN_CLAUSE.get(code, TOKEN_CLAUSE["failed"]).format(app=app, n=n, nouns=nouns)


TOKEN_NO_UNDO = "I can't see what your automation does with it, and I can't undo it."


def token_ask(kind, app, titles, notes, due_text):
    """The preview of tasks for a task app, or of what goes to a webhook: every title (and its link) exactly as it will
    be sent. A webhook says before the yes that it can't be undone."""
    due = f", due {due_text}" if due_text else ""
    if len(titles) == 1:
        if kind == "webhook":
            head = f"I'll send \"{titles[0]}\" to your webhook{due}."
        else:
            head = f"I'll add \"{titles[0]}\" to {app}{due}."
        if notes[0]:
            head += f"\nWith its link: {notes[0]}"
    else:
        verb = f"send these {len(titles)} to your webhook" if kind == "webhook" else f"add these {len(titles)} to {app}"
        head = "\n".join([f"I'll {verb}{due}:"] + [f"• {t}" + (f" ({u})" if u else "") for t, u in zip(titles, notes)])
    if kind == "webhook":
        head += "\n" + TOKEN_NO_UNDO
        return head + "\nReply \"yes\" to send " + ("it" if len(titles) == 1 else "them") + ", or \"no\" to leave " + \
            ("it." if len(titles) == 1 else "them.")
    return head + "\nReply \"yes\" to add " + ("it" if len(titles) == 1 else "them") + ", or \"no\" to leave " + \
        ("it." if len(titles) == 1 else "them.")


def token_done(kind, app, titles, due_text):
    n = len(titles)
    what = f"\"{titles[0]}\"" if n == 1 else f"{n} tasks"
    if kind == "webhook":
        return "I sent it to your webhook. I can't see what it did there, and I can't undo it."
    due = f" It's due {due_text} there; I won't send my own reminder." if due_text else ""
    return f"Added {what} to {app}.{due} Reply \"undo\" within 10 minutes to remove {'it' if n == 1 else 'them'}."


def token_already(kind, app):
    return "I already sent that to your webhook today." if kind == "webhook" else f"I already added that to {app} today."


def token_undone(n, app, title=None):
    if n == 1 and title:
        return f"I took \"{title}\" out of {app}"
    return f"I took {'that' if n == 1 else f'those {n}'} out of {app}"


def token_undo_failed(app, titles):
    if len(titles) == 1:
        return f"I couldn't take it out of {app} just now. It's \"{titles[0]}\"; delete it there."
    return (f"I couldn't take {len(titles)} of them out of {app} just now: " + ", ".join(f"\"{t}\"" for t in titles)
            + ". Delete them there.")


def token_undo_gone(app):
    return f"Those are already gone from {app}, so there was nothing to take out."


LIST_STAYS = " Your list stays here."

# connect, check, disconnect, by text. A key or an address is never asked for in the chat.
TOKEN_SETUP = {
    "ticktick": ("I can add tasks to your TickTick with a personal API token. Never send the token here.\n"
                 "1. In TickTick on the web: your avatar › Settings › Account › API Token. Make one and copy it.\n"
                 "2. On the computer I run on, put MVP_TICKTICK_TOKEN=<the token> in the settings file only you can "
                 "read (chmod 600), then restart me. New tasks go to your Inbox (or set MVP_TICKTICK_PROJECT to a "
                 "project's id).\n"
                 "3. Text me \"check my ticktick\".\n"
                 "I'll always show you what I'm about to add and wait for your yes."),
    "todoist": ("I can add tasks to your Todoist with a personal API token. Never send the token here.\n"
                "1. In Todoist: Settings › Integrations › Developer › API token. Copy it.\n"
                "2. On the computer I run on, put MVP_TODOIST_TOKEN=<the token> in the settings file only you can read "
                "(chmod 600), then restart me. New tasks go to your Inbox (or set MVP_TODOIST_PROJECT to a project's "
                "id).\n"
                "3. Text me \"check my todoist\".\n"
                "I'll always show you what I'm about to add and wait for your yes."),
    "webhook": ("I can send things to an automation you make in IFTTT, Make, Zapier or n8n. Its web address works like "
                "a password, so never send it here.\n"
                "1. Make an automation that starts with a web request that takes JSON (in IFTTT: Webhooks, \"Receive a "
                "web request with a JSON payload\"; in Make: a custom webhook). Copy its address; it must start with "
                "https://.\n"
                "2. On the computer I run on, put MVP_WEBHOOK_URL=<the address> in the settings file only you can read "
                "(chmod 600), then restart me.\n"
                "3. Text me \"check my webhook\".\n"
                "I'll always show you what I'm about to send and wait for your yes. I can't see or undo what your "
                "automation does with it."),
}
TOKEN_ONLY_OPERATOR = "{app} is only for the person who runs me. I keep your lists here."


def token_set_already(word):
    return f"It's already set up here. Text me \"check my {word}\" to test it."


def token_checked(key, app):
    if key == "webhook":
        return ("Your webhook's address is set. I haven't sent anything to it: the first time you send something "
                "there, I'll show it to you first.")
    return f"{app} is connected. New tasks go to your Inbox there, unless you set a project."


def token_check_failed(code, app, word):
    if code == "unreachable":
        return f"{app} isn't set up on the computer I run on yet. Text me \"connect my {word}\" to see how."
    if code == "refused":
        return (f"{app} refused my key. Make a new one, put it in the settings file, restart me, then text me \"check "
                f"my {word}\" again.")
    if code == "timeout":
        return f"{app} didn't answer in time. Text me \"check my {word}\" to try again."
    if code == "rate":
        return f"{app} asked me to slow down. Try \"check my {word}\" again in a minute."
    return f"{app} gave an error. Text me \"check my {word}\" to try again."


WEBHOOK_NOT_HTTPS = ("The webhook address on the computer I run on doesn't start with https://, so I won't use it. Put "
                     "the https address in the settings file and restart me.")


def token_not_on(app):
    return f"{app} isn't connected, so there's nothing to stop."


def token_off(key, app, n, word):
    if key == "webhook":
        tail = (f" I can't undo what your automation did with the {_count(n, 'thing')} I sent it." if n else "")
        return (f"I've stopped using your webhook.{tail} To stop it completely, take MVP_WEBHOOK_URL out of the "
                f"settings file and restart me.")
    if not n:
        return (f"I've stopped using {app}. I hadn't added anything there in the last 30 days. To stop it completely, "
                f"delete the token in {app} and take it out of the settings file.")
    return (f"I've stopped using {app}. I added {_count(n, 'task')} there in the last 30 days. Reply REMOVE to delete "
            f"those, or KEEP to leave them.")


def token_removed(app, n, failed):
    out = f"I deleted the {_count(n, 'task')} I'd added to {app}." if n else ""
    if failed:
        out += (" " if out else "") + (f"I couldn't delete {failed} just now; {'it is' if failed == 1 else 'they are'} "
                                       f"still there.")
    return (out or "There was nothing left to delete.") + (f" To stop it completely, delete the token in {app} and "
                                                           f"take it out of the settings file.")


def token_kept(app):
    return f"OK, they stay in {app}. To stop it completely, delete the token in {app} and take it out of the settings file."


def token_pref_set(app, ready, word):
    out = (f"OK. From now on I'll offer to put new things for your lists in {app}, and show you each one first. Say "
           f"\"use my list here again\" to go back.")
    return out if ready else out + f" It isn't set up yet: text me \"connect my {word}\" to see how."


def token_status(key, why):
    word = "webhook" if key == "webhook" else key
    return {None: "connected", "broken": f"stopped after 3 failures in a row (say \"check my {word}\")",
            "off": f"turned off (say \"check my {word}\" to turn it back on)"}.get(why, "not set up")


def token_delete_data(names):
    return f" This also stops {' and '.join(names)}. What I added there stays there."


# a password, a key or an address typed into the chat (the narrow guard; the message is not kept)
SECRET_IN_CHAT = ("I never take passwords, keys or webhook addresses in the chat, so I didn't keep that message. It's "
                  "still on your phone, so please make a new one and delete the old one. Keys go in the settings file "
                  "on the computer I run on: say \"connect my ticktick\" (or todoist, or webhook) to see how.")


def token_moved(n):
    return f" {'It is' if n == 1 else 'They are'} off your list here now."


# ---------- round 9 checks of acting, connectors and receipts (DESIGN.md section 16.G) ----------
# a timed send of things from several posts numbers each post's things from 1 (executor._run_items): a number alone
# could mean two things, so the bot asks instead of guessing
THINGS_BY_POST = ("Those were numbered post by post, so that number could mean more than one thing. Say its name "
                  "instead, or \"add them all\".")


def place_maybe_there(app):
    """After a time-out: the outside place may have taken it anyway (the request may have arrived)."""
    return f" It may have reached {app} anyway, so check there before you ask me again."


def place_maybe_twice(app):
    """In the preview, when the same thing timed out in the last 24 hours."""
    return f"Last time {app} didn't answer in time, so this may be there already. Check {app} before you say yes."


def receipt_failed(what, who):
    return f"tried to send the {what} to {who} after your \"send\", but it didn't go (nothing was sent)"


def did_failed(what, who):
    return (f"No. I tried to send the {what} to {who} after your \"send\", but it didn't go, so nothing was sent. Say "
            f"\"show the draft\" to try again.")


# ---------- round 9 live fix pass (DESIGN.md section 16.H) ----------
# finding 105: a rewrite that came back the same (or could not pass the checks) is not a new version
def draft_tone_same(tone):
    if tone and tone.startswith("in "):
        what = f"put it in {tone[3:].capitalize()}"
    else:
        what = f"make it {tone}" if tone else "rewrite it"
    return (f"I couldn't {what} without adding things you didn't say, so the email is the same as before. Tell me "
            f"the words to use, like: say \"hope you're well\", or instead say ...")


DRAFT_SAME_TEXT = "That's already how the email reads, so nothing changed."
DRAFT_TONE_FAILED = ("I couldn't rewrite it just now, so the email is the same as before. Try again in a minute, or "
                     "tell me the words to use, like: instead say ...")


# finding 107: "put this in my email" with a card open, for anyone without the operator's mailbox
def draft_save_link(link):
    return ("I can't save it in your mail myself. This link opens it as a new message in your mail app; close it "
            "there without sending, and your mail app keeps it as a draft (some ask you first):\n" + link)


# finding 108: "apply to the first one" on a thing whose post gives no date: what the bot can do now
def apply_todo_text(name):
    return name if re.match(r"^\W*apply\b", name or "", re.I) else f"Apply to {name}"


def apply_todo_offer(name):
    return f"\"{apply_todo_text(name)}\" on your to-do list, with the post's link."


APPLY_ASK_DATE = "The post doesn't say when it closes. Tell me the date, like \"dec 5\", and I'll set a reminder too."


# check of the live fix pass (fix9): a brief that says its own claim is not true
DRAFT_NOT_TRUE = ("I can't write something you've told me isn't true, so I didn't write this one. Tell me what you'd "
                  "like to say instead, like: email my boss that I need one more day.")


# ---------- round 10, slice K (DESIGN.md section 17.K): the build, on the page, at the end of "help", and "version" ---
def build_line(build):
    return f"I'm running build {build}."


def help_text(build):
    """The help reply: HELP, then the build it runs (round 10, slice K)."""
    return f"{HELP}\n{build_line(build)}"


def page_status_line(build, switches):
    """The line under the test page: the build, then each switch by name ("TickTick: off"). Never a value."""
    return " · ".join([f"Build {build}"] + [f"{k}: {v}" for k, v in switches.items()])
# ---------- end round 10, slice K ----------


# ---------- round 10, slice W: wording, the setup answer, "email it to me" ----------
# W1: "email it to me" with nothing written and no answer in view
NOTHING_TO_EMAIL = ("There's nothing written yet to email you. Tell me what to write, like \"email my teacher that I'm "
                    "sick today\".")


def draft_whom(name=None, word=None):
    """'your teacher', 'Sam', or 'them': who an open draft is for, in the person's own words."""
    return name or (f"your {word}" if word else "them")


def draft_self_emailed(masked, whom):
    return f"I emailed the draft to you at {masked}, so you can forward it. The draft to {whom} is still open."


def draft_still_open(whom, needs_address):
    return f"The draft to {whom} is still open." + (" Send me their address when you have it." if needs_address else "")


def draft_self_link(link, whom, needs_address):
    return (f"Here's the draft as an email to yourself (tap to open it in your mail app): {link}\n"
            + draft_still_open(whom, needs_address))


# W3: the setup answer that asks for regular exports, and export_reads
EXPORT_FACTS_HEAD = "About regular exports: Instagram doesn't let any app pull your saves, so here's the closest I can do."
EXPORT_FACT_YOUTUBE = ("• YouTube: Google Takeout can repeat your export every 2 months for a year. You set that up once; "
                       "say \"steps\" and I'll send them.")
EXPORT_FACT_YOUTUBE_CONNECT = (" Your likes, subscriptions and playlists I can also read straight from YouTube: say "
                               "\"connect youtube\".")
EXPORT_FACT_INSTAGRAM = ("• Instagram: I can't confirm a repeating export for your account, so I'll remind you every 4 "
                         "weeks.")


def export_facts(platforms, where, yt_connect=False):
    """The facts about regular exports, per platform the person has, and where a new file goes."""
    lines = [EXPORT_FACTS_HEAD]
    if "youtube" in platforms:
        lines.append(EXPORT_FACT_YOUTUBE + (EXPORT_FACT_YOUTUBE_CONNECT if yt_connect else ""))
    if "instagram" in platforms:
        lines.append(EXPORT_FACT_INSTAGRAM)
    lines.append(f"• Each new file goes in {where}, and I add it by myself.")
    return "\n".join(lines)


def _nexts_words(nexts, word="reminder"):
    parts = []
    for i, (p, d) in enumerate(nexts):
        day = d.strftime("%-d %B")
        parts.append(f"next {PLATFORM_NAMES.get(p, p)} {word} {day}" if i == 0 else
                     f"next {PLATFORM_NAMES.get(p, p)} one {day}")
    return ", ".join(parts)


def export_setup_done(nexts):
    """'Done: next Instagram reminder 15 December, next YouTube one 17 January. Say "undo" to stop the reminders.'"""
    return f"Done: {_nexts_words(nexts)}. Say \"undo\" to stop the reminders."


EXPORT_OFFER_TAIL = "Want me to remind you? Say yes."


def export_on(nexts):
    return f"Your export reminders are on: {_nexts_words(nexts, 'one')}. Say \"steps\" for how to do it."


def export_remind_offer(platform, every, first):
    return (f"I'll remind you {every} to send me a new {PLATFORM_NAMES.get(platform, platform)} export, with the steps, "
            f"starting {first.strftime('%-d %B')}. Want me to? Say yes.")


UPLOAD_HERE = "the upload box on this page"
UPLOAD_TEST_PAGE = "the upload box on the test page"


def you_also_asked(part):
    return f"You also asked: \"{part}\". Send it on its own and I'll do it."


# W6: what code says instead of a model reading that clashes with what is on screen
CHAT_INSIDE = "I keep a list of what I did for you: say \"what did you do for me\"."
DRAFT_CHANGE_HOW = ("I didn't change the draft or make a reminder from that. Tell me the change, like \"say Tuesday "
                    "instead of Monday\" or \"take out the part about the doctor\".")


def draft_words_not_found(words):
    return (f"The draft doesn't say \"{words}\", so I didn't change it. Tell me the words to change, like \"say "
            f"Tuesday instead of Monday\".")


def doit_next(n, text):
    """'do all of them': one at a time; the next one is named, never done without being asked."""
    return f"One at a time: next is \"{text}\". Say \"do {n} for me\" when you're ready."


def app_cant_connect(app):
    return f"I can't connect to {app} yet. Say \"what are you connected to\" to see what I can reach."


def app_not_connected(app):
    return f"I'm not connected to {app}, so there's nothing to check or disconnect."


_KNOW_TAIL = " Say \"what do you know about me\" to see it all."


def noted_only(changes, skipped=False):
    """profile_changed without its "what do you know about me" tail (inside the setup, offered already)."""
    m = profile_changed(changes, skipped)
    return m[:-len(_KNOW_TAIL)] if m.endswith(_KNOW_TAIL) else m
# ---------- end round 10, slice W ----------
# ---------- round 10, slice S (DESIGN.md section 17.S): "that reel had nothing to do with it" ----------
MISMATCH_ASK = "Was it that the video didn't match what its caption said? Reply \"yes\" or \"no\"."
MISMATCH_NOTED = "OK, noted."


def mismatch_reply(creator, others=0):
    """After "that reel had nothing to do with it" (or "yes" to MISMATCH_ASK). `others`: how many other accounts carry
    the same text."""
    who = f"captions from {creator}" if creator else "captions from that account"
    out = (f"Thanks, that helps. I've taken that reel out of your picks and I'll trust {who} less from now on. "
           "Say \"another\" for a different one.")
    if others:
        out += (f" The same text is under {others} other account{'s' if others != 1 else ''}; "
                "I'll treat those the same.")
    return out


def match_ok_reply(creator):
    return f"Good to know. I'll trust {creator}'s captions again." if creator else \
        "Good to know. I'll trust that account's captions again."


def cm_left_out(n):
    """A rule run that adds to the person's apps (slice G) left strong-marked picks out."""
    return "1 left out: its caption may not match the video." if n == 1 else \
        f"{n} left out: their captions may not match the videos."
# ---------- end round 10, slice S ----------
# ---------- round 10, slice D (DESIGN.md section 17.D): sending, the notice's follow-up, the Connections panel ----------
# D1: the route read at "send" differs from the one the card showed: the card again, and no yes is taken
SEND_ROUTE_CHANGED = "Your mail connection changed, so here's the email again. Reply \"send\" if it's still right."
SEND_ROUTE_GONE = ("Your mail connection changed, so here's the email again. I can't send it from here now: tap the link "
                   "to send it yourself.")
SEND_ROUTE_GONE_HELD = "Your mail connection changed before it went, so nothing was sent."
# D4: "can you send it for me"
SEND_FOR_ME_TESTER = "I can't send from your address yet. Tap the link above and press Send in your mail app."
SEND_SWITCH_ON = ("To let me send from your own address, the person who runs me sets MVP_MAILBOX_ADDRESS and an app "
                  "password (never in this chat).")
SEND_SWITCH_ON_PAGE = ("To let me send from your own address, add your email address and an app password in the "
                       "Connections panel on this page (never in this chat). Then say \"send\" again.")
PANEL_TAIL = " On the test page, use the Connections panel."
_PANEL_FIELD = {"ticktick": "TickTick API token", "todoist": "Todoist API token", "webhook": "Webhook address"}


def token_setup_page(key):
    """'connect my ticktick' on the test page: step 2 is the Connections panel, not a settings file."""
    step = (f"2. Paste it into \"{_PANEL_FIELD[key]}\" in the Connections panel beside this chat and press Save. It's "
            f"sealed on this computer and never shown again.")
    return re.sub(r"\n2\. On the computer I run on,.*?(?=\n3\. )", "\n" + step, TOKEN_SETUP[key], flags=re.S)


def notice_accepted(merchant, to, when):
    """The receipt for a cancellation notice the operator's mailbox sent (never "cancelled")."""
    whom = f"{merchant} ({to})" if merchant and to else (merchant or to or "them")
    return f"Your mail server accepted your cancellation notice to {whom} at {when}. I can't unsend it."


def notice_offer(day_words):
    """D2: after a notice went (the bot's send, or "sent" after the link): not over yet, and a check date offered."""
    return (f"That doesn't end it yet: it ends when they confirm in writing. Keep their reply. Want a reminder on "
            f"{day_words} to check they confirmed? Reply \"yes\", or give another day.")


def notice_check_text(name):
    """The check reminder for a notice (the words the person sees when it fires)."""
    return (f"Check that {name} confirmed your cancellation (look for their email). If they did, say \"they "
            f"confirmed\". If not, I can write a second notice.")


def second_notice_offer(asked_on):
    return (f"Want me to write a second notice? It says you asked on {asked_on} and asks them to confirm within 7 "
            f"days.")


SECOND_NOTICE_SUBJECT = "Second notice: cancel my membership"


def second_notice_paragraph(asked_on):
    return (f"I asked you to cancel my membership on {asked_on} and have not had a confirmation. Please cancel my "
            f"membership effective immediately, stop all future charges, and confirm the cancellation in writing "
            f"within 7 days.")


def second_notice_head(merchant):
    return f"Here's a second notice you can send to {merchant}. Nothing has been sent."


SECOND_NOTICE_NO = "OK, I've left it. If you want one later, say \"write a second notice\"."


def notice_post_line(name, where, checked):
    """D3: a merchant that takes written notice by post (from its own page)."""
    return f"{name} takes a written notice by post to {where} (from their help page, checked {checked})."


def notice_deadline_line(deadline):
    return f"They ask for it {deadline}."


# the Connections panel (test page only): names and states, never a value
PANEL_STATE = {"setting": "set in this computer's settings", "sealed": "set",
               "unreadable": "set, but I can't read it with this key", None: "not set"}
PANEL_ERRORS = {
    "name": "That isn't one of the fields here.",
    "empty": "Type a value first.",
    "too_long": "That's too long to be a key or an address.",
    "address": "That doesn't look like an email address.",
    "outlook": "Outlook.com doesn't allow app passwords any more, so I can't send from it.",
    "https": "The webhook address must start with https://.",
    "spaces": "That has spaces in it. Copy it again.",
    "no_key": "I can't keep it safely: set MVP_TOKEN_KEY on this computer first.",
    "in_setting": "This one is set in this computer's settings. Change it there, then restart me.",
    "failed": "I couldn't save it. Nothing was kept.",
}


def panel_sending(state):
    return {"on": "Sending is on: say \"send\" on an email card and I'll send it from your address after a 2-minute "
                  "wait.",
            "need_both": "Sending is off: add your email address and its app password.",
            "outlook": "Sending is off: Outlook.com doesn't allow app passwords any more.",
            "host": "Sending is off: I don't know the mail server for that address. Set MVP_MAILBOX_SMTP_HOST on this "
                    "computer.",
            "nobody": "Sending is off: MVP_OPERATOR is set to none, so I send for nobody."}.get(state, "Sending is off.")
# ---------- end round 10, slice D ----------
# ---------- round 10, slice G (DESIGN.md section 17.G): rules that add to the person's own apps, one yes per rule ------
_G_DAY_NAMES = {"MON": "Monday", "TUE": "Tuesday", "WED": "Wednesday", "THU": "Thursday", "FRI": "Friday",
              "SAT": "Saturday", "SUN": "Sunday"}


def grant_each(days, daily):
    """'each Sunday', 'each day', 'each weekday', 'each time': how often a rule's caps apply, for the preview."""
    days = sorted(set(days or []))
    if daily or len(days) == 7:
        return "each day"
    if days == sorted(["MON", "TUE", "WED", "THU", "FRI"]):
        return "each weekday"
    if len(days) == 1:
        return f"each {_G_DAY_NAMES.get(days[0], 'time')}"
    return "each time"


def grant_where(kind, app, target, settings_project=False):
    """'in your Inbox', 'in your "Dinners" list', 'in your "Digest" calendar', 'in your default list'."""
    if kind == "calendar":
        return f"in your \"{target or 'Digest'}\" calendar"
    if kind == "playlist":
        return f"in your private playlist \"{target}\"" if target else "in a private playlist"
    if target:
        return f"in your \"{target}\" list"
    if app in ("TickTick", "Todoist"):
        return "in the project in your settings" if settings_project else "in your Inbox"
    return "in your default list"


def grant_thing(kind, noun_many):
    """'as tasks with their links', 'as reminders with their links', 'as an event'."""
    if kind == "calendar":
        return "as an event"
    if kind == "playlist":
        return "as videos"
    return f"as {noun_many} with their links"


def place_grant_note(app, where, thing, per_run, each, per_day, calendar=False, youtube=False):
    """G3: (the lines a rule's preview gains when it will add to the person's own app under their yes, the YES line
    that replaces the preview's own). Word for word in the verdict."""
    on = " on YouTube" if youtube and "YouTube" not in app else ""
    them = "it" if calendar and per_run == 1 else "them"
    out = (f"\nI'll also add {them} to {app}{on}, {where}, {thing}: at most {per_run} {each} and {per_day} a day."
           + ("\nNobody else is invited and nobody gets an email." if calendar else "")
           + "\nEach time I'll tell you here what I added, and you can say \"undo\".")
    return out, f"\nReply YES to start and let me add {them}"


def place_unusable(app, word, n):
    """The place can't be used for this person now: the rule sends here, and the line says how to change that."""
    return (f" {app} isn't connected for you, so I'll put them in my message here instead. Say \"connect {word}\", "
            f"then \"use {word} for rule {n}\".")


def place_no_route(app):
    return f" I can't add to {app} on a schedule, so I'll put them in my message here instead."


def place_not_timed(app):
    return f" I can only add to {app} from a rule that runs at set times, so I'll put them in my message here instead."


def rule_email_other(when, who):
    """M-14: a rule never emails another person."""
    return (f" I can't email other people on a schedule. I can send you the picks here {when}; then say "
            f"\"email {who} …\" and I'll write it.")


def grant_started(app):
    return f" Each time I'll add them to {app} and tell you here what I added."


def grant_not_made(app, word, n):
    return (f" {app} isn't connected now, so I'll put them in my message here instead. Say \"check my {word}\", then "
            f"\"use {word} for rule {n}\".")


def grant_ran(count, one, many, app, n, titles, more=0):
    """G4: what one run added, always in the run's message."""
    what = f"{count} {one if count == 1 else many}"
    more_line = f" {more} more {'is' if more == 1 else 'are'} only in this message." if more else ""
    return (f"Added {what} to {app} (rule {n}): {'; '.join(titles)}.{more_line} Say \"undo\" to take "
            f"{'it' if count == 1 else 'them'} out, or \"stop {n}\" to end the rule.")


def grant_already(app, n):
    return f"I'd already added these to {app} for rule {n}."


def grant_failed_once(app):
    return f"{app} didn't answer, so I kept them in my message here."


def grant_paused(app, n, word):
    return (f"I've stopped adding to {app} for rule {n} after 3 failures in a row. The rule keeps sending here. Say "
            f"\"check my {word}\" to try again.")


def grant_not_added(app):
    return f"I didn't add these to {app} this time, so they're only in this message."


def grant_dropped(app):
    return f" I won't add them to {app} any more."


def grant_day_full(app, n, per_day):
    return f"Rule {n} has added its {per_day} for today to {app}, so these are only in this message."


def grant_rule_changed(app, word, n):
    return (f"Rule {n} changed since you said yes, so I didn't add anything to {app}. Say \"use {word} for rule {n}\" "
            f"to add them again.")


def grant_stopped_adding(app, numbers):
    if not numbers:
        return f"OK. I won't add anything to {app} on my own any more."
    rules = f"Rule {numbers[0]} keeps" if len(numbers) == 1 else \
        "Rules " + _and([str(n) for n in numbers]) + " keep"
    return f"OK. I won't add anything to {app} on my own any more. {rules} sending here."


def grant_nothing_to_stop(app):
    return f"No rule adds to {app} on its own, so there's nothing to stop."


def grant_use_preview(n, when, what, note_lines, yes_line):
    return f"Rule {n} sends {what} {when}.{note_lines}{yes_line}, or tell me what to change."


def grant_use_same(n, app):
    return f"Rule {n} already adds to {app}."


GRANT_NO_RULE = "I don't have a rule with that number. Say \"my rules\" to see them."
GRANT_ONLY_PICKS = "That rule doesn't send things from your saves, so there's nothing to add to an app."


def grant_change_ask(app, note_lines, yes_line):
    """After "change 3 ...": the old yes ended; the place line asks again."""
    return f" I've stopped adding to {app} until you say yes again.{note_lines}{yes_line} to keep adding them."


def grant_change_done(app, n):
    return f"OK. Rule {n} will add them to {app} again, and tell you here what it added."


def grant_change_stale(n):
    return f"Rule {n} changed since I asked, so I didn't start adding. Say \"my rules\" to see it."


def grant_undone(count, one, many, app, n):
    return f"I took the {count} {one if count == 1 else many} rule {n} added out of {app}."


def grant_undo_failed(app, titles):
    names = _and([f"\"{t}\"" for t in titles]) if titles else "some of them"
    return f"I couldn't take {names} out of {app}; please remove {'it' if len(titles) == 1 else 'them'} there."


def grant_undo_none(n):
    return f"Rule {n} hasn't added anything in the last 7 days that's still there."


def receipt_by_rule(by_rule):
    """' (4 by rule 3)', ' (4 by rule 3, 2 by rule 5)'."""
    if not by_rule:
        return ""
    return " (" + ", ".join(f"{c} by rule {n}" for n, c in by_rule) + ")"


RECEIPT_STANDING = "Standing permissions:"


def receipt_standing(n, app, many, per_run, per_day, status):
    state = " (paused after 3 failures)" if status == "paused" else ""
    return f"rule {n} may add {many} to {app}: at most {per_run} a run and {per_day} a day{state}"
# ---------- end round 10, slice G ----------
# ---------- round 10, slice C (DESIGN.md section 17.C): Todoist through its own MCP server, signed in with "Allow" ---
ACTION_CAP_LABEL.update({"todoist.mcp_add": "tasks in Todoist"})
TOKEN_CLAUSE.update({
    "needs_signin": "{app} needs you to sign in again",
    "changed": "{app} changed how adding a task works",
    "unpinned": "{app} no longer offers adding a task the way I know",
    "input_required": "{app} wants you to confirm this in {app} itself",
    "no_due": "I can't give {app} a due time yet",
})
_token_after_r9, _token_status_r9 = token_after, token_status


def token_after(code, key):   # noqa: F811 - round 10, slice C: two more reasons, then round 9's
    if code == "needs_signin":
        return f" Say \"connect {key}\"."
    if code == "changed":
        return f" Say \"yes {key}\" to keep using it, or \"disconnect {key}\"."
    return _token_after_r9(code, key)


def token_status(key, why):   # noqa: F811 - round 10, slice C: two more states, then round 9's
    if why == "needs_signin":
        return f"needs you to sign in again (say \"connect {key}\")"
    if why == "changed":
        return f"stopped, because it changed how adding a task works (say \"yes {key}\" or \"disconnect {key}\")"
    return _token_status_r9(key, why)


def mcp_connect_link(app, link, word):
    return (f"To let me add tasks to your {app}, open this link and press Allow: {link}\n"
            f"I'll only add things after you say yes to them, and you can say \"disconnect {word}\" any time. The link "
            f"works for 10 minutes.")


def mcp_connected(app, word):
    return (f"{app} is connected. Try \"add it to my {word}\" after an answer, or make a rule like \"every sunday put 3 "
            f"recipes in my {word}\".")


def mcp_tester(app):
    return f"Connecting {app} from a phone isn't ready yet. I'll keep your list here; say \"my list\" to see it."


MCP_NO_KEY = "I can't keep sign-ins safely yet: the person who runs me needs to set a key first."


def mcp_changed(app, word):
    return (f"{app} changed how adding a task works, so I stopped adding there. Say \"yes {word}\" to keep using it, or "
            f"\"disconnect {word}\".")


def mcp_needs_signin(app, word):
    return f"{app} needs you to sign in again: say \"connect {word}\"."


def mcp_revoke_failed(app):
    return f"I couldn't reach {app} to cancel my access; remove it in {app} under Settings › Integrations."


def mcp_maybe_arrived(app):
    return f" It may have arrived in {app} anyway; check before asking again."


def mcp_already(app, word):
    return f"{app} is already connected. Say \"check my {word}\" to test it, or \"disconnect {word}\" to stop."


def mcp_connect_failed(app, code, word):
    if code == "port":
        return "I can't open the sign-in page on the computer I run on right now. Try again in a few minutes."
    if code == "unreachable":
        return f"I couldn't reach {app} to sign you in just now. Try \"connect {word}\" again in a few minutes."
    return f"{app}'s sign-in didn't look the way I expect, so I stopped. Nothing was connected."


def mcp_signin_failed(app, code, word):
    """After the person came back from the sign-in page and it did not work."""
    if code == "denied":
        return f"{app} didn't let me in, so nothing changed. Say \"connect {word}\" to try again."
    if code == "expired":
        return f"That sign-in link had run out, so nothing changed. Say \"connect {word}\" for a new one."
    if code == "key":
        return MCP_NO_KEY
    return f"Signing in to {app} didn't work, so nothing changed. Say \"connect {word}\" to try again."


def mcp_pin_failed(app):
    return f"{app} doesn't offer adding a task the way I know, so I cancelled my access there. Nothing was added."


def mcp_checked(app):
    return f"{app} is connected. New tasks go to your Inbox there."


def mcp_off(app, revoked, rules):
    out = f"I've disconnected {app}." + (" I cancelled my access there." if revoked else "")
    if rules:
        out += " Rules that added there keep sending here."
    return out + ("" if revoked else " " + mcp_revoke_failed(app))


def mcp_off_ask(app, n):
    return (f"I've stopped adding to {app}. I added {_count(n, 'task')} there in the last 30 days. Reply REMOVE to "
            f"delete those, or KEEP to leave them. Then I'll cancel my access there.")


def mcp_off_done(app, removed, failed, revoked):
    """After REMOVE (removed: how many went) or KEEP (removed None), the disconnect is finished."""
    if removed is None:
        out = f"OK, they stay in {app}."
    else:
        out = f"I deleted the {_count(removed, 'task')} I'd added to {app}." if removed else ""
        if failed:
            out += (" " if out else "") + (f"I couldn't delete {failed} just now; "
                                           f"{'it is' if failed == 1 else 'they are'} still there.")
    out = (out + f" I've disconnected {app}" + (" and cancelled my access there." if revoked else ".")).strip()
    return out + ("" if revoked else " " + mcp_revoke_failed(app))


def mcp_yes_again(app, word, rules):
    out = f"OK, I'll use {app} again. I'll still show you what I add first."
    if rules:
        out += f" Rules that added there keep things here until you say \"use {word} for rule\" and its number."
    return out
# ---------- end round 10, slice C ----------
# ---------- review of the round 10 merge: a rule's run when the route under the app changed since the yes ----------


def grant_route_changed(app, word, n):
    """Slice G's grant was given on one route (a Todoist token, or slice C's sign-in) and the app is now reached the
    other way: nothing is added, the grant ends, and this is said once."""
    return (f"The way I reach {app} changed since you said yes to rule {n}, so I didn't add anything there. Say "
            f"\"use {word} for rule {n}\" to add them again.")
# ---------- end review of the round 10 merge ----------
