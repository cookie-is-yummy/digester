"""PROTOTYPE ONLY - browser.cancel: presses the last button of a merchant's cancel pages, once (round 10, slice V3;
DESIGN.md section 17.V; amendment A-016, Proposed).

Only the bot's own code runs it (browser.py, after "yes cancel <merchant>"): never named by the model, never in a rule
(registry: from_model=False, in_rules=False), the operator only. Its yes token is the hash of the page as it is NOW
(browser_guard.el_hash: the address, the button's name and tag, the page's whole text), so perform runs only when the
person's yes was for exactly this page; the press itself checks the hash again on a fresh snapshot in the browser's own
thread. What it returns names the page's kind and the merchant's one outcome sentence; the caller keeps only that.
"""
from .. import browser_guard as G
from .base import Outcome

NONE = "no-final-button"   # the token when the page has no such button now (never equal to a real hash)


def _run(ctx, params):
    from ..browser import _sessions, route
    run = _sessions(ctx.bot)["runs"].get(ctx.handle)
    st = ctx.store.get_state(f"browserrun:{ctx.handle}") or {}
    if run is None or run["run_id"] != params.run_id or not run["session"].alive or st.get("run_id") != params.run_id:
        return None, None, None
    return run, st, route(st["key"])


def yes_token(ctx, params):
    run, st, r = _run(ctx, params)
    if run is None or r is None:
        return NONE
    snap = run["session"].call("snapshot")
    hits = [e for e in snap["elements"] if e["name"] == st.get("final_name") and e["tag"] == st.get("final_tag")]
    return G.el_hash(snap, hits[0]) if len(hits) == 1 else NONE


def run(ctx, params):
    got, st, r = _run(ctx, params)
    if got is None or r is None:
        return Outcome("skipped", detail={"refused": "closed"})
    s = got["session"]
    did = s.call("press", st["final_name"], st["final_tag"], "confirmed_click", params.yes_hash, r["final_names"])
    if "refused" in did:
        return Outcome("skipped", detail={"refused": did["refused"]})
    snap = s.call("snapshot")
    page = G.page_state(snap, tuple(r["domains"]), r["final_names"])
    quote = G.outcome_quote(snap["text"], r.get("outcome_phrases")) if page == "outcome_ok" else ""
    return Outcome("done", detail={"page": page, "quote": quote})
