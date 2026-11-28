"""The fixture ledgers of the examples in prompts/brain_v1.md: real tool results of the made-up brain library
(tests/brain_library.py), every entity renamed to names that are in no library of the repository, so an example the
model copies fails `unknown_name` instead of passing. Used by tests/test_brain_slice.py (every example sentence of the
prompt passes the verifier on these ledgers) and by nothing else.
"""
import json

# library name -> the example's name (channels, themes, areas); longest first when replaced
RENAME = {"Clip Factory": "Moss Garden", "Pan Theory": "Kettle Craft", "Pixel Pencil": "Tidepool Tours",
          "Brick Realm": "Lantern Lane", "Gaming Daily": "Fern Hour", "Limit Lane": "Quiet Orbit",
          "@wetpaper.ig": "@paper.kite", "Wet Paper": "Paper Kite", "Gaming clips": "Bonsai care",
          "Home cooking": "Tea rituals", "Digital drawing": "Tide pools", "Minecraft builds": "Garden builds",
          "Calculus lessons": "Star charts", "Watercolor painting": "Kite making",
          "art and design": "travel", "food and cooking": "drinks", "gaming": "gardening", "Gaming": "Gardening"}

# (rid, message, tool, args): the calls behind the examples
CALLS = [
    ("r1", "which channels did I watch the most in October?", "breakdown",
     {"by": "channel", "window": {"words": "in October"}}),
    ("r1", "and lately, without gaming?", "breakdown",
     {"by": "area", "window": {"words": "lately"}, "scope": {"exclude": ["gaming"]}}),
]


def _rename(o):
    s = json.dumps(o)
    for a in sorted(RENAME, key=len, reverse=True):
        s = s.replace(a, RENAME[a])
    return json.loads(s)


def ledgers(h):
    """[{rid: envelope}] for each call of CALLS, renamed; `h` an eval_brain.Harness on the brain library."""
    from mvp.brain import tools as TL
    out = []
    for rid, msg, tool, args in CALLS:
        t = h.turn(msg)
        r = TL.call(t, tool, args)
        assert r.get("rid") == rid, r
        out.append({rid: _rename(r)})
    return out


# mvp27 (DESIGN 29.4): the call behind brain_v3b's left_out example, a result that left a friend's post out
SAVED_CALL = ("r1", "what have I saved lately?", "breakdown",
              {"by": "channel", "window": {"words": "lately"}, "scope": {"how": "saved"}})


def saved_ledger(h):
    """{rid: envelope} of SAVED_CALL, renamed (its left_out.friends is 1)."""
    from mvp.brain import tools as TL
    rid, msg, tool, args = SAVED_CALL
    r = TL.call(h.turn(msg), tool, args)
    assert r.get("rid") == rid and (r["sheet"].get("left_out") or {}).get("friends") == 1, r
    return {rid: _rename(r)}
