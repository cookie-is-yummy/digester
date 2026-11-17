"""PROTOTYPE ONLY - STUB published by round 10's foundation (slice K) for slice W, which replaces this file (W4).

Other slices may call these names now and get today's behaviour: the text unchanged, one clause, no time word.
Never stored, logged, fed to the interpreter, a rule text or a draft (W-2).
"""
import re

STUB = True
TIME_WORDS = re.compile(r"(?!)")   # stub: matches nothing (W4 fills the list that stops the splitter and the errand)


def normalize(text):
    return text


def variants(text):
    """[text, normalized] for hooks 5 to 8 only. Stub: the text alone."""
    return [text]


def clauses(text):
    """The message split into requests. Stub: one clause."""
    return [text]
