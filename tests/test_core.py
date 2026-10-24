from datetime import datetime, timedelta, timezone

import mongomock
import pytest

from app import config, digest, memory, pipeline
from app.fetch import FetchResult
from app.llm import Card, build_prompt


@pytest.fixture
def db():
    d = mongomock.MongoClient().slothshelf
    d.links.create_index("url_norm", unique=True)
    return d


def fake_card(title, text, memory_ctx="", loved=None, note=None):
    verdict = "skip" if "boring" in text else "read"
    return Card(summary="A summary.", tags=["RAG", " #rag ", "eval", "x", "y"], verdict=verdict, reason="ok",
                overview="Gist.", terms=[], key_points=["Point one.", "Point two."], try_this="Try it.", topic="RAG")


def fake_page(url):
    return FetchResult(ok=True, title="T " + url, text="useful " * 50)


def fake_embed(text):
    return [0.1] * 768


def run(db, **kw):
    return pipeline.process_pending(
        db, fetch_fn=fake_page, card_fn=fake_card, embed_fn=fake_embed,
        loved_fn=lambda db, v: [], **kw,
    )


# --- card model -------------------------------------------------------------
def test_card_cleans_tags_and_whitespace():
    c = fake_card("t", "x")
    assert c.tags == ["rag", "eval", "x"]
    assert Card(summary="a   b\n c", tags=[], verdict="skim", reason=" r ", key_points=[], try_this="", topic="x", overview="", terms=[]).summary == "a b c"


def test_prompt_contains_memory_and_loved():
    msgs = build_prompt("Title", "body text", "Goals: x", ["Loved one: summary"], note="for later")
    user = msgs[1]["content"]
    assert "Goals: x" in user and "Loved one" in user and "for later" in user and "body text" in user


# --- import + pipeline ------------------------------------------------------
def test_import_dedupes_across_runs_and_tracking_params(db):
    items = [{"url": "https://a.com/x?utm_source=z"}, {"url": "https://www.a.com/x"}, {"url": ""}]
    r = pipeline.import_links(db, items, "text")
    assert (r["inserted"], r["duplicates"], r["invalid"]) == (1, 1, 1)
    assert pipeline.import_links(db, [{"url": "https://a.com/x"}], "text")["inserted"] == 0


def test_process_marks_carded_and_stores_card(db):
    pipeline.import_links(db, [{"url": "https://a.com/1"}, {"url": "https://a.com/2"}], "text")
    stats = run(db)
    assert stats == {"processed": 2, "carded": 2, "failed": 0, "remaining": 0}
    doc = db.links.find_one({"url_norm": "a.com/1"})
    assert doc["status"] == "carded" and doc["card"]["verdict"] == "read"
    assert len(doc["embedding"]) == 768 and doc["card"]["prompt_version"] == config.PROMPT_VERSION


def test_failed_fetch_is_flagged_not_faked(db):
    pipeline.import_links(db, [{"url": "https://a.com/1"}], "text")
    stats = pipeline.process_pending(
        db, fetch_fn=lambda u: FetchResult(False, error="HTTP 403"),
        card_fn=fake_card, embed_fn=fake_embed, loved_fn=lambda d, v: [],
    )
    doc = db.links.find_one({})
    assert stats["failed"] == 1 and doc["status"] == "failed" and doc["error"] == "HTTP 403"
    assert doc["card"] is None


def test_model_error_marks_failed_and_batch_continues(db):
    pipeline.import_links(db, [{"url": "https://a.com/1"}, {"url": "https://a.com/2"}], "text")
    calls = {"n": 0}

    def flaky(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("ollama down")
        return fake_card(*a)

    stats = pipeline.process_pending(
        db, fetch_fn=fake_page, card_fn=flaky, embed_fn=fake_embed, loved_fn=lambda d, v: []
    )
    assert (stats["carded"], stats["failed"]) == (1, 1)
    assert "ollama down" in db.links.find_one({"status": "failed"})["error"]


def test_retry_failed_reprocesses(db):
    pipeline.import_links(db, [{"url": "https://a.com/1"}], "text")
    pipeline.process_pending(db, fetch_fn=lambda u: FetchResult(False, error="x"))
    assert run(db)["processed"] == 0
    assert run(db, retry_failed=True)["carded"] == 1


# --- memory -----------------------------------------------------------------
def test_feedback_moves_weights_and_undo_restores(db):
    memory.record_feedback(db, ["rag"], "loved")
    memory.record_feedback(db, ["rag"], "read")
    assert memory.tag_weights(db)["rag"] == 3
    memory.record_feedback(db, ["rag"], "skipped", old_state="loved")  # change of mind
    assert memory.tag_weights(db)["rag"] == 0
    memory.record_feedback(db, ["rag"], "unread", old_state="read")  # undo
    assert memory.tag_weights(db)["rag"] == -1


def test_memory_summary_and_goals(db):
    memory.add_goal(db, "build a RAG project")
    memory.add_goal(db, "build   a RAG project")  # same goal, extra spaces
    memory.record_feedback(db, ["python"], "loved")
    memory.record_feedback(db, ["listicle"], "skipped")
    m = memory.get_memory(db)
    assert m["goals"] == ["build a RAG project"]
    assert m["liked"] == ["python"] and m["disliked"] == ["listicle"]
    text = memory.format_memory(**m)
    assert "build a RAG project" in text and "python" in text and "listicle" in text
    assert memory.format_memory([], [], []) == ""
    memory.remove_goal(db, "build a RAG project")
    assert memory.list_goals(db) == []


# --- digest + stats ---------------------------------------------------------
NOW = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)


def link(url, verdict, tags=(), state="unread", days_old=1, status="carded"):
    return {
        "url": url, "url_norm": url, "status": status, "added_at": NOW - timedelta(days=days_old),
        "card": {"verdict": verdict, "tags": list(tags), "summary": "s", "reason": "r"},
        "user": {"state": state}, "embedding": None,
    }


def test_rank_prefers_verdict_then_taste():
    docs = [link("skim1", "skim"), link("read1", "read"), link("read-liked", "read", ["rag"])]
    ranked = digest.rank_links(docs, {"rag": 5}, NOW)
    assert [d["url"] for d in ranked] == ["read-liked", "read1", "skim1"]


def test_agreement_rate():
    docs = [
        link("a", "read", state="loved"), link("b", "read", state="skipped"),
        link("c", "skip", state="skipped"), link("d", "skim", state="read"),
        link("e", "read", state="unread"),
    ]
    assert digest.agreement(docs) == {"checked": 3, "agreed": 2, "rate": 0.667}
    assert digest.agreement([])["rate"] is None


def test_digest_picks_top_three_unread_and_is_repeatable(db):
    for i in range(5):
        db.links.insert_one(link(f"r{i}", "read", days_old=i))
    db.links.insert_one(link("done", "read", state="read"))
    db.links.insert_one(link("nope", "skip"))
    d = digest.build_digest(db, now=NOW, k=3)
    assert len(d["picks"]) == 3 and d["week"] == "2026-W43"
    assert {p["url"] for p in d["picks"]}.isdisjoint({"done", "nope"})
    again = digest.build_digest(db, now=NOW, k=3)  # same week: replaced, not duplicated
    assert db.digests.count_documents({}) == 1 and len(again["picks"]) == 3
    assert "embedding" not in d["picks"][0]


def test_next_week_skips_links_already_picked(db):
    for i in range(4):
        db.links.insert_one(link(f"r{i}", "read", days_old=i))
    first = {p["url"] for p in digest.build_digest(db, now=NOW, k=3)["picks"]}
    second = {p["url"] for p in digest.build_digest(db, now=NOW + timedelta(days=7), k=3)["picks"]}
    assert first.isdisjoint(second) and len(second) == 1


def test_digest_fills_with_skim_when_few_reads(db):
    db.links.insert_one(link("r", "read"))
    db.links.insert_one(link("s", "skim"))
    assert [p["url"] for p in digest.build_digest(db, now=NOW)["picks"]] == ["r", "s"]


def test_compute_stats(db):
    db.links.insert_one(link("a", "read", state="loved"))
    db.links.insert_one(link("b", "skip"))
    db.links.insert_one(link("c", "read", status="failed"))
    s = digest.compute_stats(db)
    assert s["links_in"] == 3 and s["status"] == {"carded": 2, "failed": 1}
    assert s["verdicts"]["read"] == 2 and s["states"]["loved"] == 1


# --- richer digest, notes, PDF ---------------------------------------------
def test_card_new_fields_are_cleaned():
    c = Card(summary="a", tags=[], verdict="skim", reason="r", key_points=[" one ", "", "two"], try_this="", topic="", overview="", terms=[])
    assert c.key_points == ["one", "two"] and c.topic == "General"


def test_note_fallback_when_page_unreadable(db):
    db.links.insert_one({**link("ig", "read"), "status": "new", "note": "Python tip: use enumerate instead of range(len(x))",
                         "url": "https://instagram.com/reel/abc"})
    bad = lambda url: FetchResult(ok=False, title=None, text="", error="login wall")
    out = pipeline.process_pending(db, fetch_fn=bad, card_fn=fake_card, embed_fn=fake_embed, loved_fn=lambda d, v: [])
    assert out["carded"] == 1
    assert db.links.find_one({"url": "https://instagram.com/reel/abc"})["source_quality"] == "note"


def test_reset_old_cards_requeues_only_old(db):
    db.links.insert_one({**link("old", "read"), "card": {"verdict": "read", "prompt_version": 1}})
    db.links.insert_one({**link("new", "read"), "card": {"verdict": "read", "prompt_version": config.PROMPT_VERSION, "overview": "ok"}})
    assert pipeline.reset_old_cards(db) == 1


def test_report_groups_topics_and_pdf_renders(db):
    from app.pdf import render_digest_pdf
    for i in range(8):
        d = link(f"r{i}", "read", days_old=i)
        d["card"].update(topic="Python" if i % 2 else "AI tools", overview="Long gist. " * 5, terms=["Pandas: dataframes"], key_points=["Use X \u2014 \U0001F600 \u4e2d"], try_this="Do Y")
        db.links.insert_one(d)
    db.links.insert_one(link("nope", "skip"))
    db.links.insert_one({**link("bad", "read"), "status": "failed", "error": "HTTP 403"})
    rep = digest.build_report(db, now=NOW, k=3)
    assert len(rep["picks"]) == 3 and {t["topic"] for t in rep["topics"]} <= {"Python", "Ai Tools"}
    assert len(rep["skipped"]) == 1 and len(rep["failed"]) == 1
    pdf = render_digest_pdf({**rep, "week": rep["week"]})
    assert pdf.startswith(b"%PDF") and len(pdf) > 2000
    assert render_digest_pdf({"week": None, "picks": [], "stats": {}}).startswith(b"%PDF")
