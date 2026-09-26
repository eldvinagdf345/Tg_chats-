import asyncio
import time

# Lightweight in-process pub/sub so the dialogue engine, campaigns and the
# inactivity sweep can broadcast what they're doing to any connected web
# dashboard clients (see webapp.py's /ws/events). No-ops with zero
# subscribers, so it costs nothing when the web dashboard isn't running.

_subscribers: "set[asyncio.Queue]" = set()


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=200)
    _subscribers.add(q)
    return q


def unsubscribe(q: asyncio.Queue):
    _subscribers.discard(q)


def emit(event_type: str, **data):
    """event_type: 'out' | 'in' | 'system' | 'warn'"""
    if not _subscribers:
        return
    payload = {"type": event_type, "ts": time.time(), **data}
    for q in list(_subscribers):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass
