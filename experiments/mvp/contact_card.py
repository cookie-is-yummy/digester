"""PROTOTYPE ONLY - the bot's contact card (.vcf), for the founders to host (DESIGN.md section 11, "Link previews").

Messages only expands links from senders in the person's contacts, so after their first reply the bot sends this card
(SendblueChannel.send_contact_card, from MVP_CONTACT_CARD_URL). This makes the file; hosting it at a public https
address ending in .vcf is done by the founders, not here.

    python3 -m mvp.contact_card --out /path/to/bot.vcf [--name "Digest bot"] [--number +15551234567]

The name comes from --name or MVP_BOT_NAME; the number from --number or SENDBLUE_FROM_NUMBER (the bot's own sending
number). Prints only where the file was written.
"""
import argparse
import os
import re
import sys


def _esc(s):
    return str(s).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def make_vcf(name, number, email=None):
    """A vCard 3.0 with the bot's name and number (and an email, if one is given). CRLF line ends."""
    name = " ".join(str(name or "").split())
    number = re.sub(r"[^\d+]", "", str(number or ""))
    if not name:
        raise ValueError("the card needs a name (MVP_BOT_NAME)")
    if not re.fullmatch(r"\+?\d{7,15}", number):
        raise ValueError("the card needs the sending number with its country code (SENDBLUE_FROM_NUMBER)")
    lines = ["BEGIN:VCARD", "VERSION:3.0", f"FN:{_esc(name)}", f"N:;{_esc(name)};;;", f"ORG:{_esc(name)}",
             f"TEL;TYPE=CELL,VOICE:{number}"]
    if email:
        lines.append(f"EMAIL;TYPE=INTERNET:{_esc(email)}")
    lines.append("END:VCARD")
    return "\r\n".join(lines) + "\r\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Write the bot's contact card (.vcf).")
    ap.add_argument("--out", required=True, help="where to write the .vcf file")
    ap.add_argument("--name", default=os.environ.get("MVP_BOT_NAME"))
    ap.add_argument("--number", default=os.environ.get("SENDBLUE_FROM_NUMBER"))
    a = ap.parse_args(argv)
    try:
        card = make_vcf(a.name, a.number)
    except ValueError as e:
        raise SystemExit(str(e)) from None
    with open(a.out, "w", encoding="utf-8", newline="") as f:
        f.write(card)
    print(f"Wrote the contact card to {a.out}. Host it at a public https address ending in .vcf and set "
          "MVP_CONTACT_CARD_URL to that address.", file=sys.stderr)


if __name__ == "__main__":
    main()
