"""
Layer 1 of safety. Plain code, no model involved.

"life"   -> someone may be in danger. We do NOT call the model.
            The guest gets 112 + host contact immediately.
"urgent" -> property emergency (flood, no power, locked out).
            The model still answers, but the host contact card is
            shown on top and the session is flagged.
None     -> normal message.
"""

import re
import unicodedata

LIFE_THREATENING = [
    # English
    "gas", "smell of gas", "gas leak", "smoke", "fire", "burning smell",
    "something is burning", "carbon monoxide", "can't breathe", "cant breathe",
    "cannot breathe", "not breathing", "blood", "bleeding", "unconscious",
    "passed out", "injured", "electric shock", "electrocuted", "sparks",
    "chest pain", "heart attack", "ambulance", "choking", "overdose",
    "explosion", "emergency",
    # Romanian (diacritics stripped, see normalize())
    "gaz", "miros de gaz", "scurgere de gaz", "fum", "foc", "incendiu",
    "arde", "miros de ars", "monoxid", "nu pot respira", "nu respira",
    "sange", "sangereaza", "lesinat", "inconstient", "ranit", "ranita",
    "electrocutat", "curentat", "scantei", "durere in piept", "infarct",
    "ambulanta", "salvare", "se ineaca", "supradoza", "explozie", "urgenta"
    "gaza", "gaze", "miroase a gaz", "miroase a gaza", "sangerez", "sangerezi",
    "sangerare", "am cazut", "a cazut", "m-am lovit", "m-am ranit", "ma doare rau",
]

PROPERTY_URGENT = [
    # English
    "flood", "flooding", "leak", "leaking", "water everywhere", "no power",
    "power is out", "no electricity", "blackout", "locked out", "lost the key",
    "lost my key", "no water", "no hot water", "break in", "broken into",
    "burglar", "someone is inside", "alarm",
    # Romanian
    "inundatie", "inundat", "scurgere", "curge apa", "apa peste tot",
    "nu am curent", "nu este curent", "nu e curent", "pana de curent",
    "am ramas afara", "pierdut cheia", "am pierdut cheia", "nu am apa",
    "nu este apa", "nu am apa calda", "spargere", "au intrat", "a intrat cineva",
    "cineva in apartament", "alarma",
]


def normalize(text):
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.lower()


def _compile(words):
    return [re.compile(r"\b" + re.escape(w) + r"\b") for w in words]


_LIFE = _compile(LIFE_THREATENING)
_URGENT = _compile(PROPERTY_URGENT)


# Words that make a bare "gas"/"gaz"/"fire" mean something harmless.
# Checked first. If present, the single ambiguous word is ignored and the
# message goes to the model with a caution note instead.
HARMLESS_CONTEXT = [
    "gas station", "petrol", "fuel", "refuel", "fill up", "gas stove", "gas hob",
    "gas bill", "gas cooker", "fireplace", "campfire", "fire station",
    "benzinarie", "benzina", "motorina", "carburant", "combustibil", "alimentez",
    "aragaz", "plita pe gaz", "factura de gaz", "semineu",
]

# Ambiguous on their own: harmless in "gas station", deadly in "GAS!!".
AMBIGUOUS = ["gas", "gaz", "fire", "foc", "emergency", "urgenta", "alarm", "alarma"]

# If any of these appear, a harmless context no longer excuses "gas".
# "the gas stove smells" is a leak until proven otherwise.
SMELL_OR_LEAK = ["smell", "smells", "smelling", "miros", "miroase", "leak", "leaking",
                 "scurgere", "scapare", "hiss", "hissing", "sfarait", "suiera"]

# Smell + one of these = treat as a leak.
GAS_APPLIANCES = ["stove", "hob", "cooker", "boiler", "heater", "oven",
                  "aragaz", "aragazul", "plita", "centrala", "cuptor", "boilerul"]

_APPLIANCE = _compile(GAS_APPLIANCES)
_SMELL = _compile(SMELL_OR_LEAK)
_HARMLESS = _compile(HARMLESS_CONTEXT)
_AMBIGUOUS = _compile(AMBIGUOUS)


def classify(message):
    """
    Returns "life", "urgent", "ambiguous" or None.

    "ambiguous": the message has a word like "gas" but also a harmless
    context like "station". The model answers, but with a note to lead
    with 112 if there is any chance of danger.
    """
    text = normalize(message)
    harmless = any(p.search(text) for p in _HARMLESS)
    smell = any(p.search(text) for p in _SMELL)
    if smell and re.search(r"\bgaz", text):
        return "life"
    if smell and any(p.search(text) for p in _APPLIANCE):
        return "life"
    if harmless and smell:
        harmless = False

    for pattern in _LIFE:
        if pattern.search(text):
            if harmless and pattern.pattern in _ambiguous_patterns:
                continue
            return "life"
    if harmless and any(p.search(text) for p in _AMBIGUOUS):
        return "ambiguous"
    for pattern in _URGENT:
        if pattern.search(text):
            return "urgent"
    return None


_ambiguous_patterns = {p.pattern for p in _AMBIGUOUS}

AMBIGUOUS_HINT = (
    "This message contains a word like 'gas' or 'fire' in what looks like a harmless "
    "context (petrol, cooking, a station). Answer normally. But if there is any chance "
    "the guest means a leak, smoke, or danger, lead with 112 and the host's number."
)


def life_reply(host, emergency):
    """Fixed bilingual reply. Never generated."""
    lines = [
        "If anyone is in danger, call 112 now.",
        "Dacă cineva este în pericol, sunați la 112 acum.",
        "",
        f"Host / gazdă: {host['name']} — {host['phone']}",
    ]
    if emergency.get("gas_company"):
        lines.append(f"Gas / gaze: {emergency['gas_company']}")
    if emergency.get("building_admin"):
        lines.append(f"Building / administrator: {emergency['building_admin']}")
    lines += [
        "",
        "Leave the apartment if you smell gas or see smoke. Don't switch lights on or off.",
        "Părăsiți apartamentul dacă simțiți miros de gaz sau vedeți fum. Nu atingeți întrerupătoarele.",
    ]
    return "\n".join(lines)
