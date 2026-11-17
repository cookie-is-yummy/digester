"""PROTOTYPE ONLY - the draft card (round 9, slice A: W2, W3, W4; DESIGN.md section 16.A). STUB published by C1.

The entry points other slices call are fixed here so they can import them before slice A merges. Slice A replaces
this file. Until then: `start` raises NotImplementedError (a caller must not pretend a card was shown), and
`open_draft` and `from_todo` return None (no draft is open; the to-do is not handled here).
"""


def start(person, kind, to=None, to_name=None, subject=None, paragraphs=(), post=None, placeholders=(), job=None,
          now=None):
    """Opens a draft card (kind "email" or "notice") for this person and returns its ref. Slice A builds it."""
    raise NotImplementedError("drafts.start is built by round 9, slice A")


def open_draft(handle):
    """The person's open draft (a dict), or None. Stub: None."""
    return None


def from_todo(person, todo, now=None):
    """A Reply that starts a draft for an "email ..." to-do, or None when it is not one. Stub: None."""
    return None
