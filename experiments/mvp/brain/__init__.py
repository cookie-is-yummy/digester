"""PROTOTYPE ONLY - the brain on the processor's tools (design/brain_v1/SPEC.md), step 1: the tools, offline.

Nothing here is wired into the message path: there is no switch, no loop, no provider and no prompt in step 1. The
modules are imported by their own tests only.

- results.py   the result envelope (2.3), present(), refs, neutralised third-party text
- windows.py   a tool's window, read by code from their own words (2.2)
- names.py     a name they use, resolved to a ref in a fixed order (2.2, 2.5)
- tools.py     the registry and the read tools of 2.4
- context.py   the saved context cards ctx1 and ctx2 (6.1, 6.2)
"""
