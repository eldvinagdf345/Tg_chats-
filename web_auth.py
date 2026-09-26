import hashlib
import hmac
import time

from config import WEB_PASSWORD

COOKIE_NAME = "mx_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def _sign(msg: str) -> str:
    key = WEB_PASSWORD.encode()
    return hmac.new(key, msg.encode(), hashlib.sha256).hexdigest()


def create_token() -> str:
    ts = str(int(time.time()))
    return f"{ts}.{_sign(ts)}"


def verify_token(token: str | None) -> bool:
    if not token or not WEB_PASSWORD:
        return False
    try:
        ts, sig = token.split(".", 1)
    except ValueError:
        return False
    if not hmac.compare_digest(sig, _sign(ts)):
        return False
    return (int(time.time()) - int(ts)) <= SESSION_MAX_AGE


def check_password(candidate: str) -> bool:
    return bool(WEB_PASSWORD) and hmac.compare_digest(candidate, WEB_PASSWORD)
