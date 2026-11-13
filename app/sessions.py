"""
Conversations live in memory and expire after SESSION_TTL_HOURS.
Restarting the server forgets them, which is acceptable for now.

Monthly token usage per property is written to data/usage.json so the
spending ceiling survives a restart. That is the one thing that must.
"""

import json
import threading
import time
from datetime import datetime

from . import config

_lock = threading.Lock()
_sessions = {}
_usage_path = config.DATA_DIR / "usage.json"


def _load_usage():
    if _usage_path.exists():
        with open(_usage_path, encoding="utf-8") as f:
            return json.load(f)
    return {}


_usage = _load_usage()


def _save_usage():
    with open(_usage_path, "w", encoding="utf-8") as f:
        json.dump(_usage, f, indent=2)


def _month_key():
    return datetime.now().strftime("%Y-%m")


def _day_key():
    return datetime.now().strftime("%Y-%m-%d")


def _purge_expired():
    cutoff = time.time() - config.SESSION_TTL_HOURS * 3600
    dead = [sid for sid, s in _sessions.items() if s["last_at"] < cutoff]
    for sid in dead:
        del _sessions[sid]


def get(session_id, property_token):
    with _lock:
        _purge_expired()
        s = _sessions.get(session_id)
        if s is None or s["property"] != property_token:
            s = {
                "property": property_token,
                "messages": [],
                "last_at": 0.0,
                "day": _day_key(),
                "count_today": 0,
                "flagged": False,
            }
            _sessions[session_id] = s
        if s["day"] != _day_key():
            s["day"] = _day_key()
            s["count_today"] = 0
        return s


class Blocked(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def check_limits(session, prop):
    """Raise Blocked with a reason the UI can show to the guest."""
    limits = prop.get("limits", {})
    now = time.time()

    if now - session["last_at"] < config.MIN_SECONDS_BETWEEN_MSGS:
        raise Blocked("too_fast")

    if session["count_today"] >= limits.get("session_messages_per_day", 40):
        raise Blocked("daily_cap")

    used = _usage.get(prop["access_token"], {}).get(_month_key(), 0)
    if used >= limits.get("monthly_tokens", 500_000):
        raise Blocked("monthly_cap")


def record_turn(session, prop, user_text, assistant_text, tokens_used):
    with _lock:
        session["messages"].append({"role": "user", "content": user_text})
        session["messages"].append({"role": "assistant", "content": assistant_text})
        # keep the last N exchanges only
        keep = config.HISTORY_TURNS * 2
        session["messages"] = session["messages"][-keep:]
        session["last_at"] = time.time()
        session["count_today"] += 1

        month = _month_key()
        per_prop = _usage.setdefault(prop["access_token"], {})
        per_prop[month] = per_prop.get(month, 0) + tokens_used
        _save_usage()


def touch(session):
    with _lock:
        session["last_at"] = time.time()
        session["count_today"] += 1


def usage_for(prop):
    return _usage.get(prop["access_token"], {}).get(_month_key(), 0)
