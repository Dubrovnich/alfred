"""
One JSON file per property in /properties. The whole file becomes the
"Property facts" block of Alfred's system prompt. No retrieval, no
vector search: an apartment fits in a few thousand tokens.
"""

import json
from datetime import date

from . import config


def load_all():
    props = {}
    for path in config.PROPERTIES_DIR.glob("*.json"):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        token = data["access_token"]
        if len(token) < 24:
            raise ValueError(f"{path.name}: access_token is too short to be safe")
        props[token] = data
    return props


def stay_window_open(prop, today=None):
    """
    If the property has a current_stay with dates, access details are only
    shared inside that window. If no dates are set, we allow it and rely on
    the physical tap as the gate.
    """
    stay = prop.get("current_stay") or {}
    if not stay.get("checkin_date") or not stay.get("checkout_date"):
        return True
    today = today or date.today()
    start = date.fromisoformat(stay["checkin_date"])
    end = date.fromisoformat(stay["checkout_date"])
    return start <= today <= end


def _section(title, body):
    return f"## {title}\n{body.strip()}\n"


def render_facts(prop, allow_access):
    parts = []

    host = prop["host"]
    parts.append(_section(
        "Host",
        f"{host['name']}. Phone: {host['phone']}. "
        f"Speaks: {', '.join(host.get('languages', []))}. "
        f"Typical reply time: {host.get('reply_time', 'within an hour')}.",
    ))

    parts.append(_section("Address", prop["address"]))
    coords = prop.get("coordinates")
    if coords:
        parts.append(_section(
            "Map fallback",
            "For 'nearest X' questions where X is not in the host's list below "
            "(petrol station, ATM, laundrette, hospital), give this link with X filled in, "
            "in the guest's language: "
            f"https://www.google.com/maps/search/X/@{coords['lat']},{coords['lng']},16z",
        ))

    stay = prop.get("stay", {})
    parts.append(_section("Check-in and check-out", "\n".join(
        f"- {k.replace('_', ' ').capitalize()}: {v}" for k, v in stay.items()
    )))

    access = prop.get("access", {})
    wifi = access.get("wifi", {})
    wifi_line = f"- Wi-Fi network: {wifi.get('ssid')}, password: {wifi.get('password')}"
    if allow_access:
        access_lines = [wifi_line] + [
            f"- {k.replace('_', ' ').capitalize()}: {v}"
            for k, v in access.items() if k != "wifi"
        ]
    else:
        access_lines = [wifi_line, "- (door and building codes withheld: outside a confirmed stay)"]
    parts.append(_section("Access", "\n".join(access_lines)))

    appl = prop.get("appliances", [])
    if appl:
        body = ""
        for a in appl:
            body += f"### {a['name']}\n{a['instructions']}\n"
            if a.get("video_url"):
                body += f"Video: {a['video_url']}\n"
        parts.append(_section("Appliances", body))

    for key, title in [
        ("house_rules", "House rules"),
        ("waste", "Rubbish and recycling"),
        ("parking", "Parking"),
        ("transport", "Getting around"),
    ]:
        val = prop.get(key)
        if val:
            body = "\n".join(f"- {x}" for x in val) if isinstance(val, list) else str(val)
            parts.append(_section(title, body))

    nb = prop.get("neighborhood", [])
    if nb:
        parts.append(_section("Nearby (host recommendations)", "\n".join(
            f"- {p['name']} ({p['type']}, {p.get('distance', '')}): {p.get('note', '')}"
            for p in nb
        )))

    faq = prop.get("faq", [])
    if faq:
        parts.append(_section("Questions the host gets often", "\n".join(
            f"Q: {x['q']}\nA: {x['a']}" for x in faq
        )))

    return "\n".join(parts)


def build_system_prompt(prop, today=None):
    today = today or date.today()
    allow_access = stay_window_open(prop, today)

    if allow_access:
        access_rule = "share them plainly when a guest asks; they are inside the apartment"
    else:
        access_rule = (
            "do not share them. Today's date is outside a confirmed stay. Say that "
            "access details are only available during a booked stay and point to the host"
        )

    stay = prop.get("current_stay") or {}
    if stay.get("checkin_date"):
        stay_context = (
            f"The current booking runs {stay['checkin_date']} to {stay['checkout_date']}."
        )
    else:
        stay_context = "No booking dates are on file for this stay."

    template = config.PROMPT_PATH.read_text(encoding="utf-8")
    return (
        template
        .replace("{{PROPERTY_NAME}}", prop["name"])
        .replace("{{HOST_NAME}}", prop["host"]["name"])
        .replace("{{ACCESS_RULE}}", access_rule)
        .replace("{{TODAY}}", today.isoformat())
        .replace("{{STAY_CONTEXT}}", stay_context)
        .replace("{{PROPERTY_KB}}", render_facts(prop, allow_access))
    )
