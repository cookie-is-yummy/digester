"""PROTOTYPE ONLY - the channel interface. A channel turns the outside world into Inbound messages and sends text.

receive() returns new Inbound messages (never the bot's own); send(handle, text) returns a channel reference for the
sent message (used to map tapbacks to deliveries), or None.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class Inbound:
    handle: str                       # phone number in E.164, or an Apple Account email
    text: str = ""
    tapback: Optional[str] = None     # "up" | "down" for a reaction on an earlier bot message
    tapback_ref: Optional[str] = None  # the channel reference of the message reacted to
    ref: Optional[str] = None         # this message's own channel reference (for dedupe)


class Channel:
    name = "base"

    def receive(self):
        raise NotImplementedError

    def send(self, handle, text):
        raise NotImplementedError

    def close(self):
        pass
