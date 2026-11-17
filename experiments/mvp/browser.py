"""PROTOTYPE ONLY - STUB published by round 10's foundation (slice K) for slice V, which replaces this file.

Other slices call these names now and get today's behaviour (no browser): the cancel helper's offer branch asks
`available`, and slice S's thumbs-down question never opens while `run_open` is True (W-7). The self-test (slice T)
skips conversations that need V while STUB is True.
"""
STUB = True


def available(bot, person, merchant_key):
    """True when the bot may offer to cancel this merchant in a browser for this person. Stub: never."""
    return False


def run_open(store, handle, now=None):
    """True while this person's browser run is open (30 minutes at most). Stub: never."""
    return False
