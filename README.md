# SlothShelf

**A local-first AI that reads the links you saved and never opened, then tells you which few are worth your time.**

Built for the DEV Hacktoberfest Open-Source AI Challenge, Week "Slow and Steady".
Started and built during the challenge window (24-26 Oct 2026).

You drop in a file of links. A local Gemma model reads each page, writes a two-line summary,
adds tags, and gives a verdict: **read**, **skim** or **skip**, with a one-line reason.
MongoDB Atlas remembers your goals and what you actually read or skipped, so the verdicts get
sharper over time. Every week you get the three links worth reading.

## How it works

```
saved links -> ingest (dedupe) -> fetch + clean -> local AI (Gemma card + embedding)
                                                        |  ^
                                              store     v  | goals + taste go into the prompt
                                            MongoDB Atlas: links / memory / digests
                                                        |
                                            browser page: cards, search, digest, marks
```

- **Open pieces:** Gemma and `nomic-embed-text` run locally through Ollama. No page text is sent to an AI vendor.
- **Atlas as data layer:** one document per link (card + 768-number embedding), a `memory` collection
  (goals and per-tag weights), and a `digests` collection. Atlas Vector Search powers "find by meaning"
  and "links you loved that look like this one".
- **What goes where:** raw page text stays on your machine and is discarded after the card is made.
  Atlas gets the URL, title, summary, tags, verdict, the embedding and your memory signals.
  Atlas is a cloud database, so this is not fully offline.

## Setup

You need Python 3.11+, [Ollama](https://ollama.com), and a free [MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register) cluster.

```bash
# 1. models (run once)
ollama pull gemma2:2b
ollama pull nomic-embed-text

# 2. Python environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. configuration
cp .env.example .env             # then edit .env (see below)

# 4. run
uvicorn app.main:app --reload
# open http://127.0.0.1:8000
```

**Atlas checklist** (the usual first stumbling block):

1. Create a free (M0) cluster and a database user.
2. Network Access: add your current IP address.
3. Copy the connection string into `MONGODB_URI` in `.env`.
4. On startup the app creates the vector index (`links_vector`, 768 dimensions, cosine) and the
   normal indexes. The vector index takes a minute to build. If creation fails, create it by hand
   in the Atlas UI with the definition in `app/db.py` (`VECTOR_DEFINITION`).

The pills at the top of the page show whether Atlas and Ollama (and both models) are reachable.

## Using it

1. **Feed the sloth:** upload a bookmarks export (HTML), a text file of links, or a WhatsApp
   "message yourself" chat export, or paste links. Duplicates are skipped. Try `sample/links.txt`.
2. **Let it read:** the sloth fetches each page and writes its card. Pages that cannot be read
   (login wall, JavaScript-only, error) are marked **failed**, never guessed.
3. **Tell it your goals** (optional but it helps the verdicts).
4. **Mark links** Read it / Loved it / Skip. That moves the tag weights in `memory`, and the next
   cards use them.
5. **Make the digest:** the top three unread links worth your time this week.
6. **Find by meaning:** search for "that thing about evaluating RAG" and get the closest links.

The page also shows how often you agreed with the sloth's verdicts on links you acted on.

## Configuration (`.env`)

| Variable | Default | Meaning |
| --- | --- | --- |
| `MONGODB_URI` | (required) | Atlas connection string |
| `MONGODB_DB` | `slothshelf` | Database name |
| `OLLAMA_HOST` | `http://localhost:11434` | Where Ollama runs |
| `CARD_MODEL` | `gemma2:2b` | Model that writes cards. Swap for any Ollama model |
| `EMBED_MODEL` | `nomic-embed-text` | Embedding model. Must output 768 dimensions |
| `MAX_CHARS` | `6000` | Page text sent to the model. Lower is faster |
| `TASTE_RETRIEVAL` | `true` | Show similar loved links to the model |

## API

| Method and path | Purpose |
| --- | --- |
| `POST /api/import` | Upload a file or send `text`; parses, dedupes and stores links |
| `POST /api/process?limit=3&retry_failed=false` | Read the next links with the local model |
| `GET /api/links` | List links (filter by `status`, `verdict`, `state`) |
| `POST /api/links/{id}/mark` | Set `read`, `loved`, `skipped` or `unread` |
| `GET /api/search?q=...` | Atlas Vector Search by meaning |
| `GET/POST/DELETE /api/goals` | Your goals (agent memory) |
| `POST /api/digest`, `GET /api/digest/latest` | Weekly top three |
| `GET /api/stats` | Counts and agreement rate |
| `GET /api/health` | Atlas, Ollama and model status |

Interactive docs are at `/docs` while the server runs.

## Tests

```bash
pytest
```

The tests cover URL normalising, the three file parsers, page fetching (with a mock server),
the pipeline (with a fake model and an in-memory database), memory weights, the digest and the
agreement rate. They do not need Atlas or Ollama. Vector Search itself can only be checked
against a real Atlas cluster.

## Limits

- It does not scrape Instagram or other logged-in sites. Use links, bookmarks or chat exports.
- Small local models can be wrong or miss nuance. The summary is based only on the fetched text,
  and the verdict is a suggestion, which is why the page measures how often you agree with it.
- Single user, no login. Run it on your own machine.

## Credits

[Ollama](https://ollama.com), [Gemma](https://ai.google.dev/gemma) (Google),
[nomic-embed-text](https://ollama.com/library/nomic-embed-text), [MongoDB Atlas](https://www.mongodb.com/atlas)
and PyMongo, [FastAPI](https://fastapi.tiangolo.com), [trafilatura](https://trafilatura.readthedocs.io),
[httpx](https://www.python-httpx.org), [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/).
