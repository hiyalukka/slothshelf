"""The agent's long-term memory, stored in Atlas.

Two kinds of document live in the `memory` collection:
  {"kind": "goal",   "text": "..."}                       what you are working towards
  {"kind": "signal", "tag": "rag", "weight": 3, ...}      what you read, loved or skipped
The summary of both is put into every Gemma prompt, so verdicts shift as you use it.
"""
from datetime import datetime, timezone

from pymongo.database import Database

# How much each action moves a tag's weight, and which counter it bumps.
DELTAS = {"read": 1, "loved": 2, "skipped": -1}
COUNTERS = {"read": "reads", "loved": "loves", "skipped": "skips"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def add_goal(db: Database, text: str) -> None:
    text = " ".join(text.split())
    if text and not db.memory.find_one({"kind": "goal", "text": text}):
        db.memory.insert_one({"kind": "goal", "text": text, "updated_at": _now()})


def remove_goal(db: Database, text: str) -> None:
    db.memory.delete_one({"kind": "goal", "text": " ".join(text.split())})


def list_goals(db: Database) -> list[str]:
    return [d["text"] for d in db.memory.find({"kind": "goal"}).sort("updated_at", 1)]


def _bump(db: Database, tag: str, state: str, sign: int) -> None:
    db.memory.update_one(
        {"kind": "signal", "tag": tag},
        {
            "$inc": {"weight": sign * DELTAS[state], COUNTERS[state]: sign},
            "$set": {"updated_at": _now()},
        },
        upsert=True,
    )


def record_feedback(db: Database, tags: list[str], new_state: str, old_state: str = "unread") -> None:
    """Move tag weights when a link changes state (undoing the previous state first)."""
    for tag in tags:
        if old_state in DELTAS:
            _bump(db, tag, old_state, -1)
        if new_state in DELTAS:
            _bump(db, tag, new_state, +1)


def tag_weights(db: Database) -> dict[str, float]:
    return {d["tag"]: d.get("weight", 0) for d in db.memory.find({"kind": "signal"})}


def get_memory(db: Database, top: int = 5) -> dict:
    weights = tag_weights(db)
    ranked = sorted(weights.items(), key=lambda kv: kv[1], reverse=True)
    liked = [t for t, w in ranked if w > 0][:top]
    disliked = [t for t, w in reversed(ranked) if w < 0][:top]
    return {"goals": list_goals(db), "liked": liked, "disliked": disliked}


def format_memory(goals: list[str], liked: list[str], disliked: list[str]) -> str:
    """Plain-text summary for the prompt. Empty string when there is nothing yet."""
    lines = []
    if goals:
        lines.append("The person's current goals: " + "; ".join(goals) + ".")
    if liked:
        lines.append("Topics they usually read or love: " + ", ".join(liked) + ".")
    if disliked:
        lines.append("Topics they usually skip: " + ", ".join(disliked) + ".")
    return "\n".join(lines)
