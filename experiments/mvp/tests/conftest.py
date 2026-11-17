"""Shared test setup (round 9, slice A).

Many fixtures drop every mvp module and import them again, and each import of mvp/llm.py wraps experiments/lib/ai.py's
_log once more around the wrapper before it. After about a thousand such imports in one pytest process, the chain
passed Python's recursion limit and a ledger write failed (seen in test_slice5.py's imports once the suite grew).
Before each test the chain is collapsed to one wrapper: the newest one stays and calls ai.py's own _log directly.
The behaviour of llm.py is unchanged; the root cause (a guard in llm.py against wrapping twice) is for its owner.
"""
import sys

import pytest


@pytest.fixture(autouse=True)
def _one_ledger_wrapper():
    ai = sys.modules.get("ai")
    f = getattr(ai, "_log", None) if ai is not None else None
    orig = f
    while orig is not None and getattr(orig, "__module__", None) == "mvp.llm" and \
            "_orig_log" in getattr(orig, "__globals__", {}):
        orig = orig.__globals__["_orig_log"]
    if f is not None and orig is not f and getattr(f, "__module__", None) == "mvp.llm":
        f.__globals__["_orig_log"] = orig
    yield
