"""
One call to the model, with up to two rounds of tool use.

Anthropic: the system prompt is marked for prompt caching. It is the same for
every message in a stay, so after the first call the property facts are read
from cache at a fraction of the input price.

OpenAI-compatible (Gemini, OpenRouter, Ollama): same tools and loop, translated
to that format. Good enough for demos; use Claude for paying customers.
"""

import json

import httpx

from . import config, notify

TOOLS = [
    {
        "name": "escalate_to_host",
        "description": (
            "Pass something to the host. Use for questions you cannot answer "
            "from the property facts, maintenance problems, complaints, and any "
            "safety concern."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "enum": ["safety", "unknown", "maintenance", "complaint", "other"],
                },
                "summary": {
                    "type": "string",
                    "description": "One or two sentences the host will read on their phone.",
                },
            },
            "required": ["reason", "summary"],
        },
    },
    {
        "name": "log_unanswered",
        "description": (
            "Record a question you could not answer from the property facts, "
            "so the host can add the answer later."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": ["question"],
        },
    },
]

_client = None
if not config.DRY_RUN and config.PROVIDER == "anthropic":
    import anthropic
    _client = anthropic.Anthropic()


def _run_tool(name, args, prop, session_id):
    if name == "escalate_to_host":
        return notify.escalate(prop, args["reason"], args["summary"], session_id)
    if name == "log_unanswered":
        return notify.log_unanswered(prop, args["question"], session_id)
    return {"error": f"unknown tool {name}"}


def reply(system_prompt, history, user_text, prop, session_id, hint=None):
    """
    Returns (text, tokens_used, escalated).
    """
    if config.DRY_RUN:
        return (
            "Dry run: no model is set up, so this is a canned answer. "
            "Once a key is in .env I will answer from the property facts.",
            0,
            False,
        )

    content = f"[Note to Alfred: {hint}]\n\n{user_text}" if hint else user_text
    if config.PROVIDER != "anthropic":
        return _reply_openai(system_prompt, history, content, prop, session_id)
    messages = history + [{"role": "user", "content": content}]
    system = [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]

    tokens = 0
    escalated = False
    text_parts = []

    for _ in range(3):
        resp = _client.messages.create(
            model=config.MODEL,
            max_tokens=config.MAX_OUTPUT_TOKENS,
            system=system,
            tools=TOOLS,
            messages=messages,
        )
        u = resp.usage
        cache_write = getattr(u, "cache_creation_input_tokens", None) or 0
        cache_read = getattr(u, "cache_read_input_tokens", None) or 0
        tokens += u.input_tokens + u.output_tokens + cache_write + cache_read

        for block in resp.content:
            if block.type == "text" and block.text.strip():
                text_parts.append(block.text.strip())

        if resp.stop_reason != "tool_use":
            break

        tool_results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            if block.name == "escalate_to_host":
                escalated = True
            result = _run_tool(block.name, block.input, prop, session_id)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": str(result),
            })

        messages.append({"role": "assistant", "content": resp.content})
        messages.append({"role": "user", "content": tool_results})

    text = "\n\n".join(text_parts) or "I've passed that to the host."
    return text, tokens, escalated


OPENAI_TOOLS = [{"type": "function", "function": {
    "name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
    for t in TOOLS]


def _reply_openai(system_prompt, history, content, prop, session_id):
    messages = [{"role": "system", "content": system_prompt}, *history,
                {"role": "user", "content": content}]
    headers = {"Authorization": f"Bearer {config.OPENAI_API_KEY}"} if config.OPENAI_API_KEY else {}
    tokens, escalated, text_parts = 0, False, []

    for _ in range(3):
        r = httpx.post(f"{config.OPENAI_BASE_URL}/chat/completions", headers=headers, timeout=60,
                       json={"model": config.MODEL, "max_tokens": config.MAX_OUTPUT_TOKENS,
                             "messages": messages, "tools": OPENAI_TOOLS})
        r.raise_for_status()
        data = r.json()
        u = data.get("usage") or {}
        tokens += (u.get("prompt_tokens") or 0) + (u.get("completion_tokens") or 0)
        msg = data["choices"][0]["message"]
        if (msg.get("content") or "").strip():
            text_parts.append(msg["content"].strip())
        calls = msg.get("tool_calls") or []
        if not calls:
            break
        messages.append({"role": "assistant", "content": msg.get("content") or "",
                         "tool_calls": calls})
        for c in calls:
            name = c["function"]["name"]
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
            except ValueError:
                args = {}
            if name == "escalate_to_host":
                escalated = True
                args.setdefault("reason", "other")
                args.setdefault("summary", content[:200])
            if name == "log_unanswered":
                args.setdefault("question", content[:200])
            result = _run_tool(name, args, prop, session_id)
            messages.append({"role": "tool", "tool_call_id": c.get("id", name),
                             "content": str(result)})

    text = "\n\n".join(text_parts) or "I've passed that to the host."
    return text, tokens, escalated
