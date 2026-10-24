"""Settings, read once from the environment (.env supported)."""
import os

from dotenv import load_dotenv

load_dotenv()


def _flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


MONGODB_URI = os.getenv("MONGODB_URI", "")
MONGODB_DB = os.getenv("MONGODB_DB", "slothshelf")

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
CARD_MODEL = os.getenv("CARD_MODEL", "gemma2:2b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
EMBED_DIMS = 768  # nomic-embed-text; must match the Atlas vector index

MAX_CHARS = int(os.getenv("MAX_CHARS", "6000"))
FETCH_TIMEOUT = float(os.getenv("FETCH_TIMEOUT", "15"))
FETCH_USER_AGENT = os.getenv(
    "FETCH_USER_AGENT",
    "SlothShelf/0.1 (personal reading triage; contact: your-email@example.com) httpx",
)
TASTE_RETRIEVAL = _flag("TASTE_RETRIEVAL", "true")

VECTOR_INDEX = "links_vector"
PROMPT_VERSION = 3
