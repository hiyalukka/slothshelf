"""Atlas Vector Search: find links by meaning, and recall links you loved."""
from pymongo.database import Database

from . import config
from .llm import embed_query


def vector_pipeline(vector: list[float], limit: int, state: str | None = None) -> list[dict]:
    stage = {
        "index": config.VECTOR_INDEX,
        "path": "embedding",
        "queryVector": vector,
        "numCandidates": max(100, limit * 20),
        "limit": limit,
    }
    if state:
        stage["filter"] = {"user.state": state}
    return [
        {"$vectorSearch": stage},
        {"$addFields": {"score": {"$meta": "vectorSearchScore"}}},
        {"$project": {"embedding": 0}},
    ]


def semantic_search(
    db: Database, query: str, limit: int = 5, state: str | None = None, embed_fn=embed_query
) -> list[dict]:
    vector = embed_fn(query)
    return list(db.links.aggregate(vector_pipeline(vector, limit, state)))


def similar_loved(db: Database, vector: list[float], limit: int = 3) -> list[str]:
    """Titles and summaries of loved links closest to this vector (taste retrieval)."""
    docs = db.links.aggregate(vector_pipeline(vector, limit, state="loved"))
    lines = []
    for d in docs:
        title = d.get("title") or d.get("url", "")
        summary = (d.get("card") or {}).get("summary", "")
        lines.append(f"{title}: {summary}".strip(": "))
    return lines
