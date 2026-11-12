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


class SendUncertain(Exception):
    """The send timed out: it may or may not have gone out. It is recorded as unknown and never retried, because a
    second copy of a message is worse than a missing one."""


class Channel:
    name = "base"
    poll_seconds = 1.0   # how often the bot's loop asks for new messages
    join_seconds = 2.0   # texts from one person closer together than this are handled as one request

    def receive(self):
        raise NotImplementedError

    def send(self, handle, text):
        raise NotImplementedError

    def done(self, msg):
        """Called by the loop when one inbound message has been handled (the test page shows 'typing…' until then)."""

    def wants_tick(self):
        """True when the scheduler should run now rather than at its next 30-second turn."""
        return False

    def close(self):
        pass
