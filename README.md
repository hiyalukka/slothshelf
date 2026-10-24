# SlothShelf

**Save fast. Read slow. Skip the rest.**
A local-first AI that reads the links and reels you saved, then tells you which few are worth your time.

[Live demo](https://hiyalukka.github.io/slothshelf/) | Built for the DEV Hacktoberfest Open-Source AI Challenge, "Slow and Steady" | Categories: MongoDB Atlas, Gemma

## What it does

Paste links, drop a bookmarks file or a WhatsApp export. A local Gemma model reads each page and writes a card:

| Field | What you get |
| --- | --- |
| Verdict | **read**, **skim** or **skip**, with a one-line reason |
| Gist | A short paragraph covering the main ideas |
| Key points | 4 to 8 concrete points: tools, commands, steps, numbers |
| Worth knowing | Tools and concepts mentioned, in one line each |
| Try this | One action to take after reading |

Every week it builds a **PDF digest**: your top picks with full detail, the rest of your shelf grouped by topic, a safe-to-skip list and anything it could not read.

Marking links as read, loved or skipped teaches it your taste, so later verdicts match you better. The page shows how often you agreed with it.

## How it works

```
links -> dedupe -> fetch and clean -> Gemma card + embedding -> MongoDB Atlas
                                            ^                        |
                                            +-- goals and taste -----+
```

| Piece | Role |
| --- | --- |
| Ollama with `gemma2:2b` | Writes the cards, on your machine |
| `nomic-embed-text` | Makes 768-number embeddings for search and taste matching |
| MongoDB Atlas | `links`, `memory` (goals and tag weights) and `digests` collections |
| Atlas Vector Search | "Find by meaning" and "links you loved that look like this one" |
| FastAPI and reportlab | Backend and the PDF digest |

Page text stays on your machine and is discarded after the card is made. Atlas stores the URL, title, card, embedding and your memory signals. Atlas is a cloud database, so this is not fully offline.

## Quick start

Needs Python 3.11+, [Ollama](https://ollama.com) and a free [MongoDB Atlas](https://www.mongodb.com/cloud/atlas/register) cluster.

```bash
ollama pull gemma2:2b
ollama pull nomic-embed-text

python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

copy .env.example .env          # macOS/Linux: cp .env.example .env

python -m uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. The two pills at the top show whether Atlas and Ollama are ready.

**Atlas setup**

1. Create a free M0 cluster and a database user.
2. Network Access: add your current IP.
3. Put the connection string in `MONGODB_URI` in `.env`.
4. The app creates the vector index (`links_vector`, 768 dimensions, cosine) on startup. It takes a minute to build. If it fails, create it by hand in the Atlas UI using `VECTOR_DEFINITION` in `app/db.py`.

## Using it

1. **Feed the shelf:** paste links or drop a file. Try `sample/links.txt`.
2. **Read:** press *Read next batch*. Unreadable pages are marked failed, never guessed.
3. **Set goals** (optional) so verdicts reflect what you care about.
4. **Mark links** as read, loved or skipped.
5. **Build this week**, then **Download PDF**.
6. **Search** by meaning, for example "that thing about evaluating RAG".

**Instagram reels.** Reels need a login, so SlothShelf cannot read them directly. Put the caption on the same line as the link and it uses that, flagged as "from your note":

```
https://instagram.com/reel/abc  Python tip: use enumerate instead of range(len(x))
```

## Configuration

Set in `.env`.

| Variable | Default | Meaning |
| --- | --- | --- |
| `MONGODB_URI` | required | Atlas connection string |
| `MONGODB_DB` | `slothshelf` | Database name |
| `OLLAMA_HOST` | `http://localhost:11434` | Where Ollama runs |
| `CARD_MODEL` | `gemma2:2b` | Any Ollama chat model |
| `EMBED_MODEL` | `nomic-embed-text` | Must output 768 dimensions |
| `FETCH_USER_AGENT` | built in | Put your email here. Sites like Wikipedia block anonymous scripts |
| `MAX_CHARS` | `6000` | Page text sent to the model. Lower is faster |
| `TASTE_RETRIEVAL` | `true` | Show similar loved links to the model |

## API

Interactive docs at `/docs` while the server runs.

| Endpoint | Purpose |
| --- | --- |
| `POST /api/import` | Upload a file or send `text` |
| `POST /api/process` | Read the next links (`limit`, `retry_failed`) |
| `POST /api/reread-old` | Requeue cards made by an older prompt |
| `GET /api/links` | List links |
| `POST /api/links/{id}/mark` | `read`, `loved`, `skipped`, `unread` |
| `GET /api/search?q=` | Atlas Vector Search |
| `GET/POST/DELETE /api/goals` | Your goals |
| `POST /api/digest`, `GET /api/digest/latest` | Weekly picks |
| `GET /api/digest/pdf` | Download the PDF digest |
| `GET /api/stats`, `GET /api/health` | Numbers and status |

## Tests

```bash
python -m pytest
```

Covers parsers, URL handling, fetching, the pipeline, memory weights, the digest and the PDF. Needs neither Atlas nor Ollama. Vector Search itself can only be checked against a real Atlas cluster.

## Limits

- It cannot read logged-in sites such as Instagram. Use the caption trick above.
- A small local model can miss nuance. Cards use only the fetched text, and the verdict is a suggestion.
- Single user, no login. Run it on your own machine.

## Credits

[Ollama](https://ollama.com), [Gemma](https://ai.google.dev/gemma), [nomic-embed-text](https://ollama.com/library/nomic-embed-text), [MongoDB Atlas](https://www.mongodb.com/atlas), [FastAPI](https://fastapi.tiangolo.com), [reportlab](https://www.reportlab.com), [trafilatura](https://trafilatura.readthedocs.io), [httpx](https://www.python-httpx.org), [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/).

MIT licence.
