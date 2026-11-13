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

# claude-sonnet-4-6 is the safer default for a first paying customer.
# claude-haiku-4-5 is roughly a third of the cost if you want to trim later.
MODEL = os.getenv("ALFRED_MODEL", "claude-sonnet-4-6")
MAX_OUTPUT_TOKENS = int(os.getenv("ALFRED_MAX_OUTPUT_TOKENS", "350"))

# With no API key set, Alfred answers with a canned reply so the page
# and the safety layer can be tested before you buy credits.
DRY_RUN = not os.getenv("ANTHROPIC_API_KEY")

HISTORY_TURNS = 12            # how many past exchanges Alfred sees
SESSION_TTL_HOURS = 24        # conversation forgotten after this
MIN_SECONDS_BETWEEN_MSGS = 2  # per session
