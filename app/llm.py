"""
One call to the model, with up to two rounds of tool use.

The system prompt is marked for prompt caching: it is the same for every
message in a stay, so after the first call the property facts are read
from cache at a fraction of the input price.
"""

import anthropic

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

_client = None if config.DRY_RUN else anthropic.Anthropic()


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
            "Dry run: no API key set, so this is a canned answer. "
            "Once ANTHROPIC_API_KEY is in .env I will answer from the property facts.",
            0,
            False,
        )

    content = f"[Note to Alfred: {hint}]\n\n{user_text}" if hint else user_text
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
