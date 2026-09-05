import html


def esc(text) -> str:
    """Escape text that will be interpolated into a parse_mode='HTML' message.
    Telegram rejects the whole message if raw '<', '>' or '&' sneak in from
    someone else's message text."""
    if text is None:
        return ""
    return html.escape(str(text))


def normalize_identifier(raw: str) -> str:
    """Turn a user-typed @username / id / link into the canonical form used
    to key contacts in the DB and to match incoming Pyrogram senders."""
    raw = raw.strip()
    if raw.startswith("https://t.me/"):
        raw = raw[len("https://t.me/"):]
    elif raw.startswith("t.me/"):
        raw = raw[len("t.me/"):]
    bare = raw.strip("/").lstrip("@")
    if bare.isdigit():
        return bare
    return "@" + bare.lower()


def resolve_target(identifier: str):
    """Convert a normalized identifier into what Pyrogram's send_message expects."""
    return int(identifier) if identifier.isdigit() else identifier
