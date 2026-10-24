"""import -> fetch -> Gemma card -> embedding -> store in Atlas."""
import logging
from datetime import datetime, timezone

from pymongo.database import Database
from pymongo.errors import DuplicateKeyError

from . import config
from .fetch import FetchResult, fetch_page
from .llm import embed_document, generate_card
from .memory import format_memory, get_memory
from .search import similar_loved
from .urls import normalize_url

log = logging.getLogger("slothshelf.pipeline")
MIN_NOTE_CHARS = 25


def reset_old_cards(db: Database) -> int:
    """Queue cards written by an older prompt version for a fresh read. Your marks are kept."""
    res = db.links.update_many(
        {"status": "carded", "$or": [
            {"card.prompt_version": {"$lt": config.PROMPT_VERSION}},
            {"card.overview": {"$in": [None, ""]}},
        ]},
        {"$set": {"status": "new"}},
    )
    return res.modified_count


def _now() -> datetime:
    return datetime.now(timezone.utc)


def import_links(db: Database, items: list[dict], source: str) -> dict:
    """Store new links with status "new". Duplicates (same normalised URL) are skipped."""
    inserted = duplicates = invalid = 0
    for item in items:
        url = (item.get("url") or "").strip()
        key = normalize_url(url) if url else ""
        if not key:
            invalid += 1
            continue
        doc = {
            "url": url,
            "url_norm": key,
            "source": source,
            "added_at": _now(),
            "status": "new",
            "title": item.get("title"),
            "note": item.get("note"),
            "card": None,
            "embedding": None,
            "user": {"state": "unread", "acted_at": None},
        }
        try:
            db.links.insert_one(doc)
            inserted += 1
        except DuplicateKeyError:
            duplicates += 1
    return {"inserted": inserted, "duplicates": duplicates, "invalid": invalid, "found": len(items)}


def process_link(
    db: Database, doc: dict,
    fetch_fn=fetch_page, card_fn=generate_card, embed_fn=embed_document, loved_fn=similar_loved,
) -> str:
    """Turn one stored link into a card. Returns "carded" or "failed". Never raises."""
    try:
        page = fetch_fn(doc["url"])
        quality = "caption" if getattr(page, "caption_only", False) else "full"
        if not page.ok:
            note = (doc.get("note") or "").strip()
            if len(note) < MIN_NOTE_CHARS:
                return _fail(db, doc, page.error, page.title)
            # Page unreadable (login wall): fall back to the caption the person pasted.
            page = FetchResult(True, title=page.title or doc.get("title"), text=note)
            quality = "note"
        title = page.title or doc.get("title")

        vector = embed_fn(f"{title or ''}\n{page.text[:1500]}")

        loved: list[str] = []
        if config.TASTE_RETRIEVAL:
            try:
                loved = loved_fn(db, vector)
            except Exception as exc:  # noqa: BLE001 - index may still be building
                log.info("taste retrieval skipped: %s", exc)

        memory_ctx = format_memory(**get_memory(db))
        card = card_fn(title, page.text, memory_ctx, loved, doc.get("note"))

        db.links.update_one(
            {"_id": doc["_id"]},
            {"$set": {
                "status": "carded",
                "title": title,
                "card": {
                    **card.model_dump(),
                    "model": config.CARD_MODEL,
                    "prompt_version": config.PROMPT_VERSION,
                },
                "embedding": vector,
                "source_quality": quality,
                "fetched_at": _now(),
                "error": None,
            }},
        )
        return "carded"
    except Exception as exc:  # noqa: BLE001 - one bad link must not stop the batch
        log.warning("failed %s: %s", doc.get("url"), exc)
        return _fail(db, doc, str(exc))


def _fail(db: Database, doc: dict, error: str | None, title: str | None = None) -> str:
    update = {"status": "failed", "error": error, "fetched_at": _now()}
    if title:
        update["title"] = title
    db.links.update_one({"_id": doc["_id"]}, {"$set": update})
    return "failed"


def process_pending(db: Database, limit: int = 20, retry_failed: bool = False, **fns) -> dict:
    statuses = ["new", "failed"] if retry_failed else ["new"]
    docs = list(db.links.find({"status": {"$in": statuses}}).sort("added_at", 1).limit(limit))
    carded = failed = 0
    for doc in docs:
        if process_link(db, doc, **fns) == "carded":
            carded += 1
        else:
            failed += 1
    remaining = db.links.count_documents({"status": "new"})
    return {"processed": len(docs), "carded": carded, "failed": failed, "remaining": remaining}
