"""Compatibility import for Pyrogram on Python 3.14+."""

import asyncio

try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from pyrogram import Client  # noqa: E402
from pyrogram.errors import FloodWait  # noqa: E402

__all__ = ["Client", "FloodWait"]

