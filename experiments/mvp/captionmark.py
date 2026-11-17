"""PROTOTYPE ONLY - STUB published by round 10's foundation (slice K) for slice S, which replaces this file.

Other slices call these names now and get today's behaviour (no item is marked); slice S builds the real marks
(verdict S1 to S3). The self-test (slice T) skips conversations that need S while STUB is True.
"""
STUB = True
SIGNAL_VERSION = "cm-v1"


def mark(it):
    """'strong', 'weak' or None for a library item. Stub: whatever the item carries (nothing until S), so None."""
    return getattr(it, "caption_mark", None)
