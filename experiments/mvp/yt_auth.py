"""PROTOTYPE ONLY - STUB published by round 10's foundation (slice K) for slice Y, which replaces this file (Y2).

Slice W's setup reply adds its YouTube line only when `connectable` is True (W3); slice G's playlist place needs a
connected YouTube. The self-test (slice T) skips conversations that need Y while STUB is True.
"""
STUB = True


def connectable(store, handle):
    """True when this person could connect YouTube now (a client id and secret are set). Stub: never."""
    return False


def connected(store, handle):
    """True when this person's YouTube sign-in is kept. Stub: never."""
    return False
