import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
PROPERTIES_DIR = ROOT / "properties"
DATA_DIR = ROOT / "data"
PROMPT_PATH = ROOT / "app" / "prompts" / "alfred_system.md"
CHAT_PAGE = ROOT / "app" / "static" / "chat.html"

DATA_DIR.mkdir(exist_ok=True)

# "anthropic": Claude through the Anthropic API (what paying customers should get).
# "openai": any OpenAI-compatible endpoint — Gemini's free tier, OpenRouter, a local
#           Ollama — for demos before there's money for API credits.
PROVIDER = os.getenv("ALFRED_PROVIDER", "anthropic").lower()
MODEL = os.getenv("ALFRED_MODEL", "claude-haiku-5-5" if PROVIDER == "anthropic" else "")
MAX_OUTPUT_TOKENS = int(os.getenv("ALFRED_MAX_OUTPUT_TOKENS", "350"))
OPENAI_BASE_URL = os.getenv("ALFRED_BASE_URL", "").rstrip("/")
OPENAI_API_KEY = os.getenv("ALFRED_API_KEY", "")

# With no key set, Alfred answers with a canned reply so the page
# and the safety layer can be tested before you buy credits.
if PROVIDER == "anthropic":
    DRY_RUN = not os.getenv("ANTHROPIC_API_KEY")
else:
    DRY_RUN = not (OPENAI_BASE_URL and MODEL)

# where escalations go when a property has no telegram_chat_id of its own (the demo)
ALERT_CHAT_ID = os.getenv("ALFRED_ALERT_CHAT_ID", "")

HISTORY_TURNS = 12            # how many past exchanges Alfred sees
SESSION_TTL_HOURS = 24        # conversation forgotten after this
MIN_SECONDS_BETWEEN_MSGS = 2  # per session
