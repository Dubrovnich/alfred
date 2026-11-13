"""
Tap the tag -> phone opens https://your-domain/a/<access_token>
The page calls /a/<token>/bootstrap once, then /a/<token>/chat per message.

Run:  uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from . import config, kb, llm, notify, safety, sessions

app = FastAPI(title="Alfred", docs_url=None, redoc_url=None)

PROPERTIES = kb.load_all()


def _prop(token):
    prop = PROPERTIES.get(token)
    if prop is None:
        raise HTTPException(status_code=404)
    return prop


def _host_card(prop):
    h = prop["host"]
    return {"name": h["name"], "phone": h["phone"]}


class ChatIn(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)
    message: str = Field(min_length=1, max_length=1000)


@app.get("/healthz")
def healthz():
    return {"ok": True, "properties": len(PROPERTIES), "dry_run": config.DRY_RUN}


@app.get("/a/{token}", response_class=HTMLResponse)
def page(token: str):
    _prop(token)
    return config.CHAT_PAGE.read_text(encoding="utf-8")


@app.get("/a/{token}/bootstrap")
def bootstrap(token: str):
    prop = _prop(token)
    return {
        "property_name": prop["name"],
        "host": _host_card(prop),
        "greeting": (
            f"Welcome to {prop['name']}. I'm Alfred, {prop['host']['name']}'s assistant "
            f"for this apartment. Ask me about Wi-Fi, appliances, check-out, or the area — "
            f"in any language."
        ),
        "chips": ["Wi-Fi", "Check-out time", "How does the hob work?", "Where are the bins?",
                  "Ceva de mâncare pe aproape?"],
    }


@app.post("/a/{token}/chat")
def chat(token: str, body: ChatIn):
    prop = _prop(token)
    session = sessions.get(body.session_id, token)
    host = _host_card(prop)

    # Layer 1: plain-code tripwire, before the model.
    kind = safety.classify(body.message)

    if kind == "life":
        sessions.touch(session)
        session["flagged"] = True
        notify.escalate(prop, "safety", f"Guest message: {body.message[:200]}", body.session_id)
        return {
            "kind": "life",
            "reply": safety.life_reply(prop["host"], prop.get("emergency", {})),
            "host": host,
        }

    try:
        sessions.check_limits(session, prop)
    except sessions.Blocked as b:
        replies = {
            "too_fast": "One moment — I'm still on your last message.",
            "daily_cap": f"We've talked a lot today. For anything else, please reach {host['name']} directly.",
            "monthly_cap": f"I'm unavailable right now. Please contact {host['name']} directly.",
        }
        return JSONResponse(
            status_code=429,
            content={"kind": "blocked", "reason": b.reason, "reply": replies[b.reason], "host": host},
        )

    system_prompt = kb.build_system_prompt(prop)
    hint = safety.AMBIGUOUS_HINT if kind == "ambiguous" else None
    text, tokens, escalated = llm.reply(
        system_prompt, session["messages"], body.message, prop, body.session_id, hint=hint
    )
    sessions.record_turn(session, prop, body.message, text, tokens)

    if kind == "urgent":
        session["flagged"] = True
        if not escalated:
            notify.escalate(prop, "maintenance", f"Guest message: {body.message[:200]}", body.session_id)

    return {
        "kind": kind if kind == "urgent" else "normal",
        "reply": text,
        "host": host if (kind == "urgent" or escalated) else None,
    }
