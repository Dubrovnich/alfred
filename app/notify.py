"""
Every escalation and every unanswered question is written to disk per
property, so the host can be shown "here is what guests asked that Alfred
couldn't answer". That list is what turns a mediocre knowledge base into a
good one.

If TELEGRAM_BOT_TOKEN is set and the property's host has a telegram_chat_id,
escalations are also pushed to the host's phone. Telegram is free and takes
five minutes to set up; SMS and WhatsApp both cost money and paperwork.
"""

import json
import os
from datetime import datetime

import httpx

from . import config

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


def _append(prop, kind, record):
    path = config.DATA_DIR / f"{prop['id']}_{kind}.jsonl"
    record = {"at": datetime.now().isoformat(timespec="seconds"), **record}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def _telegram(chat_id, text):
    if not TELEGRAM_TOKEN or not chat_id:
        return False
    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
        return r.status_code == 200
    except httpx.HTTPError:
        return False


def escalate(prop, reason, summary, session_id):
    _append(prop, "escalations", {
        "reason": reason, "summary": summary, "session": session_id,
    })
    prefix = "🚨 SAFETY — " if reason == "safety" else ""
    sent = _telegram(
        prop["host"].get("telegram_chat_id") or config.ALERT_CHAT_ID,
        f"{prefix}Alfred @ {prop['name']}\n[{reason}] {summary}",
    )
    return {"delivered_to_host": sent, "host_phone": prop["host"]["phone"]}


def log_unanswered(prop, question, session_id):
    _append(prop, "unanswered", {"question": question, "session": session_id})
    return {"logged": True}
