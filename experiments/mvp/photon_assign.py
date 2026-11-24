"""PROTOTYPE ONLY - give a tester a number to text on Photon's shared iMessage lines (channels/photon.py).

    python -m mvp.photon_assign +15551234567     # ask Photon for a number for this person; prints the number they text
    python -m mvp.photon_assign --list           # everyone assigned so far, and whether their first text has arrived

A shared line takes messages only from a person who was assigned to it, each person gets a different number, and the
bot can answer only after they text first. Asking twice for the same person is one assignment (the idempotency key is
made from their handle). The key needs the platforms:write permission. Free plan: 25 assignments a project.
"""
import argparse
import hashlib
import re

from .channels.photon import _env, call

HANDLE = re.compile(r"^(\+[1-9]\d{6,14}|[^@\s]+@[^@\s]+\.[^@\s]+)$")   # E.164, or an Apple Account email


def _path():
    return f"/v1/projects/{_env('PHOTON_PROJECT_ID')}/platforms/imessage/assignments"


def assign(handle, caller=call):
    if not HANDLE.match(handle or ""):
        raise SystemExit("Give the person's number with its country code and no spaces (+15551234567), "
                         "or their Apple Account email.")
    key = "assign-" + hashlib.sha256(handle.encode()).hexdigest()[:32]
    return caller("POST", _path(), {"handle": handle}, idem=key)


def assignments(caller=call):
    r = caller("GET", _path())
    return r.get("assignments", []) if isinstance(r, dict) else r   # the key seen on the live API, 21 Nov


def main(argv=None, caller=call):
    ap = argparse.ArgumentParser(description="Assign a Photon shared iMessage number to a tester.")
    ap.add_argument("handle", nargs="?", help="the person's number (+15551234567) or Apple Account email")
    ap.add_argument("--list", action="store_true", help="list the assignments")
    a = ap.parse_args(argv)
    if a.list:
        rows = assignments(caller)
        for r in rows:
            print(f"{r.get('handle')}  texts  {r.get('assignedPhoneNumber')}  "
                  f"first text: {(r.get('optIn') or {}).get('state', '?')}")
        print(f"{len(rows)} assigned.")
        return
    if not a.handle:
        ap.error("give a number or --list")
    r = assign(a.handle, caller)
    print(f"They text this number first: {r.get('assignedPhoneNumber')}")
    print(f"First text: {(r.get('optIn') or {}).get('state', '?')}. The bot can answer only after it arrives.")
    print("Their handle must also be a key in data/mvp/people.json, exactly as typed here.")


if __name__ == "__main__":
    main()
