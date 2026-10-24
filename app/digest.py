"""The Sunday digest and the numbers for the post (verdict counts, agreement rate)."""
from datetime import datetime, timezone

from pymongo.database import Database

from .memory import tag_weights
from .util import as_utc, public

VERDICT_BASE = {"read": 10.0, "skim": 3.0, "skip": 0.0}
READ_STATES = {"read", "loved"}


def iso_week(now: datetime) -> str:
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


def score_link(doc: dict, weights: dict[str, float], now: datetime) -> float:
    """Verdict first, then your tag history, then a small bonus for newer saves."""
    card = doc.get("card") or {}
    score = VERDICT_BASE.get(card.get("verdict"), 0.0)
    score += sum(weights.get(tag, 0) for tag in card.get("tags", []))
    added = doc.get("added_at")
    if added:
        age_days = (now - as_utc(added)).total_seconds() / 86400
        score += max(0.0, 3.0 - age_days / 7)
    return score


def rank_links(docs: list[dict], weights: dict[str, float], now: datetime) -> list[dict]:
    return sorted(docs, key=lambda d: (-score_link(d, weights, now), d.get("url", "")))


def agreement(docs: list[dict]) -> dict:
    """How often your choice matched the verdict, among links you have acted on.

    Only "read" and "skip" verdicts count; "skim" is a middle answer with no clear match.
    """
    checked = agreed = 0
    for d in docs:
        verdict = (d.get("card") or {}).get("verdict")
        state = (d.get("user") or {}).get("state")
        if verdict not in {"read", "skip"} or state not in READ_STATES | {"skipped"}:
            continue
        checked += 1
        if (verdict == "read" and state in READ_STATES) or (verdict == "skip" and state == "skipped"):
            agreed += 1
    return {"checked": checked, "agreed": agreed, "rate": round(agreed / checked, 3) if checked else None}


def compute_stats(db: Database) -> dict:
    docs = list(db.links.find({}, {"status": 1, "card.verdict": 1, "user.state": 1}))
    by_status: dict[str, int] = {}
    verdicts = {"read": 0, "skim": 0, "skip": 0}
    states = {"unread": 0, "read": 0, "skipped": 0, "loved": 0}
    for d in docs:
        by_status[d.get("status", "new")] = by_status.get(d.get("status", "new"), 0) + 1
        verdict = (d.get("card") or {}).get("verdict")
        if verdict in verdicts:
            verdicts[verdict] += 1
        state = (d.get("user") or {}).get("state", "unread")
        states[state] = states.get(state, 0) + 1
    return {
        "links_in": len(docs),
        "status": by_status,
        "verdicts": verdicts,
        "states": states,
        "agreement": agreement(docs),
    }


def _expand(db: Database, digest: dict) -> dict:
    by_id = {d["_id"]: d for d in db.links.find({"_id": {"$in": digest["picks"]}})}
    out = public({k: v for k, v in digest.items() if k != "picks"})
    out["picks"] = [public(by_id[i]) for i in digest["picks"] if i in by_id]
    return out


def build_digest(db: Database, now: datetime | None = None, k: int = 5) -> dict:
    """Pick the top k unread links worth your time and save this week's digest."""
    now = now or datetime.now(timezone.utc)
    week = iso_week(now)
    seen = {i for d in db.digests.find({"week": {"$ne": week}}) for i in d.get("picks", [])}

    def candidates(verdict: str) -> list[dict]:
        return [
            d for d in db.links.find(
                {"status": "carded", "card.verdict": verdict, "user.state": "unread"}
            )
            if d["_id"] not in seen
        ]

    weights = tag_weights(db)
    ranked = rank_links(candidates("read"), weights, now)
    if len(ranked) < k:  # not enough "read" verdicts: fill the rest with the best "skim"
        ranked += rank_links(candidates("skim"), weights, now)
    picks = ranked[:k]

    stats = compute_stats(db)
    digest = {
        "week": week,
        "picks": [d["_id"] for d in picks],
        "stats": {
            "links_in": stats["links_in"],
            "carded": stats["status"].get("carded", 0),
            "failed": stats["status"].get("failed", 0),
            "picked": len(picks),
            "skipped_by_verdict": stats["verdicts"]["skip"],
        },
        "generated_at": now,
    }
    db.digests.replace_one({"week": week}, digest, upsert=True)
    return _expand(db, digest)


def latest_digest(db: Database) -> dict | None:
    digest = db.digests.find_one(sort=[("generated_at", -1)])
    return _expand(db, digest) if digest else None


def _topic_of(doc: dict) -> str:
    card = doc.get("card") or {}
    label = (card.get("topic") or "").strip()
    if not label and card.get("tags"):
        label = card["tags"][0]
    return (label or "General").title()


def build_report(db: Database, now: datetime | None = None, k: int = 5, per_topic: int = 8) -> dict:
    """Everything the weekly PDF needs: top picks, the rest by topic, skipped and unreadable links."""
    now = now or datetime.now(timezone.utc)
    digest = build_digest(db, now, k)
    picked = {p["_id"] for p in digest["picks"]}
    weights = tag_weights(db)

    rest = [
        d for d in db.links.find(
            {"status": "carded", "user.state": "unread", "card.verdict": {"$in": ["read", "skim"]}}
        )
        if str(d["_id"]) not in picked
    ]
    topics: dict[str, list[dict]] = {}
    for d in rank_links(rest, weights, now):
        bucket = topics.setdefault(_topic_of(d), [])
        if len(bucket) < per_topic:
            bucket.append(public(d))
    ordered = sorted(topics.items(), key=lambda kv: (-len(kv[1]), kv[0]))

    skipped = [
        {"title": d.get("title") or d["url"], "url": d["url"], "reason": (d.get("card") or {}).get("reason", "")}
        for d in db.links.find({"status": "carded", "user.state": "unread", "card.verdict": "skip"}).limit(40)
    ]
    failed = [
        {"url": d["url"], "error": d.get("error") or "unknown error"}
        for d in db.links.find({"status": "failed"}).limit(40)
    ]
    return {
        **digest,
        "topics": [{"topic": name, "items": items} for name, items in ordered],
        "skipped": skipped,
        "failed": failed,
    }
