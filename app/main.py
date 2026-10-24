"""FastAPI backend: import links, let the local model read them, search, mark, digest."""
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from . import config, memory, pipeline
from . import digest as digest_mod
from .db import ensure_indexes, ensure_vector_index, get_db
from .llm import get_client
from .parsers import parse_any
from .pdf import render_digest_pdf
from .search import semantic_search
from .util import public

log = logging.getLogger("slothshelf")
STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.vector_index = "not checked"
    try:
        db = get_db()
        ensure_indexes(db)
        app.state.vector_index = ensure_vector_index(db)
    except Exception as exc:  # noqa: BLE001 - keep the UI up so /api/health can explain
        log.warning("Startup without database: %s", exc)
        app.state.vector_index = f"error: {exc}"
    yield


app = FastAPI(title="SlothShelf", lifespan=lifespan)


def db_dep():
    try:
        return get_db()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"Database not available: {exc}") from exc


def oid(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except InvalidId as exc:
        raise HTTPException(404, "Unknown link id") from exc


class Mark(BaseModel):
    state: Literal["unread", "read", "skipped", "loved"]


class Goal(BaseModel):
    text: str


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health():
    out = {"mongo": False, "ollama": False, "models": {}, "vector_index": app.state.vector_index}
    try:
        get_db().command("ping")
        out["mongo"] = True
    except Exception as exc:  # noqa: BLE001
        out["mongo_error"] = str(exc)
    try:
        names = [m.model for m in get_client().list().models]
        out["ollama"] = True
        for wanted in (config.CARD_MODEL, config.EMBED_MODEL):
            out["models"][wanted] = any(n == wanted or n.startswith(wanted + ":") for n in names)
    except Exception as exc:  # noqa: BLE001
        out["ollama_error"] = str(exc)
    return out


@app.post("/api/import")
async def import_endpoint(
    file: UploadFile | None = File(None), text: str | None = Form(None), db=Depends(db_dep)
):
    if file is not None:
        content = (await file.read()).decode("utf-8", errors="ignore")
    elif text:
        content = text
    else:
        raise HTTPException(400, "Send a file or paste some text.")
    source, items = parse_any(content)
    result = pipeline.import_links(db, items, source)
    return {"source": source, **result}


@app.post("/api/process")
def process(
    limit: int = Query(3, ge=1, le=50), retry_failed: bool = False, db=Depends(db_dep)
):
    return pipeline.process_pending(db, limit=limit, retry_failed=retry_failed)


@app.get("/api/links")
def list_links(
    status: str | None = None, verdict: str | None = None, state: str | None = None,
    limit: int = Query(300, ge=1, le=1000), db=Depends(db_dep),
):
    query: dict = {}
    if status:
        query["status"] = status
    if verdict:
        query["card.verdict"] = verdict
    if state:
        query["user.state"] = state
    docs = db.links.find(query, {"embedding": 0}).sort("added_at", -1).limit(limit)
    return [public(d) for d in docs]


@app.post("/api/links/{link_id}/mark")
def mark_link(link_id: str, body: Mark, db=Depends(db_dep)):
    doc = db.links.find_one({"_id": oid(link_id)}, {"embedding": 0})
    if not doc:
        raise HTTPException(404, "Unknown link id")
    old = (doc.get("user") or {}).get("state", "unread")
    if old != body.state:
        db.links.update_one(
            {"_id": doc["_id"]},
            {"$set": {"user.state": body.state, "user.acted_at": datetime.now(timezone.utc)}},
        )
        memory.record_feedback(db, (doc.get("card") or {}).get("tags", []), body.state, old)
    return public(db.links.find_one({"_id": doc["_id"]}, {"embedding": 0}))


@app.get("/api/search")
def search(q: str = Query(..., min_length=2), limit: int = Query(5, ge=1, le=20), db=Depends(db_dep)):
    try:
        return [public(d) for d in semantic_search(db, q, limit)]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            502, f"Search failed: {exc}. Is the Atlas vector index built and Ollama running?"
        ) from exc


@app.get("/api/goals")
def get_goals(db=Depends(db_dep)):
    return {"goals": memory.list_goals(db)}


@app.post("/api/goals")
def add_goal(body: Goal, db=Depends(db_dep)):
    memory.add_goal(db, body.text)
    return {"goals": memory.list_goals(db)}


@app.delete("/api/goals")
def remove_goal(body: Goal, db=Depends(db_dep)):
    memory.remove_goal(db, body.text)
    return {"goals": memory.list_goals(db)}


@app.get("/api/stats")
def stats(db=Depends(db_dep)):
    return digest_mod.compute_stats(db)


@app.post("/api/digest")
def make_digest(db=Depends(db_dep)):
    return digest_mod.build_digest(db)


@app.get("/api/digest/latest")
def latest(db=Depends(db_dep)):
    return digest_mod.latest_digest(db) or {"week": None, "picks": [], "stats": {}}


@app.get("/api/digest/pdf")
def digest_pdf(db=Depends(db_dep)):
    report = digest_mod.build_report(db)
    name = f"slothshelf-digest-{report['week']}.pdf"
    return Response(
        render_digest_pdf(report),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@app.post("/api/reread-old")
def reread_old(db=Depends(db_dep)):
    return {"queued": pipeline.reset_old_cards(db)}
