"""MongoDB Atlas connection, indexes and the vector index definition."""
import logging

from pymongo import ASCENDING, MongoClient
from pymongo.database import Database
from pymongo.operations import SearchIndexModel

from . import config

log = logging.getLogger("slothshelf.db")
_client: MongoClient | None = None

VECTOR_DEFINITION = {
    "fields": [
        {
            "type": "vector",
            "path": "embedding",
            "numDimensions": config.EMBED_DIMS,
            "similarity": "cosine",
        },
        {"type": "filter", "path": "user.state"},
    ]
}


def get_db() -> Database:
    global _client
    if not config.MONGODB_URI:
        raise RuntimeError("MONGODB_URI is not set. Copy .env.example to .env and fill it in.")
    if _client is None:
        _client = MongoClient(config.MONGODB_URI, serverSelectionTimeoutMS=8000)
    return _client[config.MONGODB_DB]


def ensure_indexes(db: Database) -> None:
    db.links.create_index([("url_norm", ASCENDING)], unique=True)
    db.links.create_index([("status", ASCENDING)])
    db.memory.create_index([("kind", ASCENDING), ("tag", ASCENDING)])
    db.digests.create_index([("week", ASCENDING)], unique=True)


def ensure_vector_index(db: Database) -> str:
    """Create the Atlas Vector Search index if missing. Never raises.

    You can also create it by hand in the Atlas UI with VECTOR_DEFINITION.
    The index takes a minute or so to become queryable after creation.
    """
    try:
        if list(db.links.list_search_indexes(config.VECTOR_INDEX)):
            return "exists"
        db.links.create_search_index(
            SearchIndexModel(
                definition=VECTOR_DEFINITION, name=config.VECTOR_INDEX, type="vectorSearch"
            )
        )
        return "created (may take a minute to build)"
    except Exception as exc:  # noqa: BLE001 - startup helper must not crash the app
        log.warning("Could not ensure vector index: %s", exc)
        return f"error: {exc}"
