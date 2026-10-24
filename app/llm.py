"""Local AI: Gemma writes the card, nomic-embed-text makes the vector (both via Ollama)."""
from typing import Literal

import ollama
from pydantic import BaseModel, Field, field_validator

from . import config


class CardError(RuntimeError):
    pass


class Card(BaseModel):
    summary: str = Field(description="At most two short sentences, using only facts from the text.")
    tags: list[str] = Field(description="One to three short lowercase tags.")
    verdict: Literal["read", "skim", "skip"]
    reason: str = Field(description="One sentence explaining the verdict.")
    key_points: list[str] = Field(
        description="Four to eight points from the text: tools, commands, steps, numbers, advice."
    )
    overview: str = Field(description="Three to six sentences covering the main ideas of the text, in order.")
    terms: list[str] = Field(description="Up to five 'Name: what it is or does' items for tools, libraries or concepts in the text.")
    try_this: str = Field(description="One concrete thing to try, under 20 words, or an empty string.")
    topic: str = Field(description="A one or two word topic label, for example Python or AI tools.")

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, tags: list[str]) -> list[str]:
        seen: list[str] = []
        for tag in tags:
            tag = tag.strip().lower().lstrip("#")
            if tag and tag not in seen:
                seen.append(tag)
        return seen[:3]

    @field_validator("key_points")
    @classmethod
    def _clean_points(cls, points: list[str]) -> list[str]:
        cleaned = [" ".join(p.split())[:300] for p in points if p and p.strip()]
        return cleaned[:8]

    @field_validator("terms")
    @classmethod
    def _clean_terms(cls, terms: list[str]) -> list[str]:
        return [" ".join(t.split())[:140] for t in terms if t and t.strip()][:5]

    @field_validator("overview")
    @classmethod
    def _overview(cls, value: str) -> str:
        return " ".join(value.split())[:900]

    @field_validator("summary", "reason", "try_this")
    @classmethod
    def _strip(cls, value: str) -> str:
        return " ".join(value.split())

    @field_validator("topic")
    @classmethod
    def _topic(cls, value: str) -> str:
        return " ".join(value.split())[:30] or "General"


SYSTEM_PROMPT = """You triage saved links for one person so they do not have to read everything.
Rules:
- Use ONLY facts from the page text. If the text does not say it, do not say it.
- summary: at most two short sentences.
- tags: one to three short lowercase tags.
- verdict: "read" = clearly useful for the person's goals or exceptionally good;
  "skim" = might be useful, worth a quick look at the headings;
  "skip" = off-topic, shallow, repetitive or not worth their time.
- reason: one sentence. Mention a goal when it is the reason.
- overview: three to six sentences covering the main ideas of the text in order, so the
  person can skip reading it. Facts only.
- key_points: four to eight points from the text. Prefer names of tools, commands, steps,
  numbers and concrete advice over general statements. Each point one full sentence.
- terms: up to five "Name: what it is" items for tools, libraries or concepts mentioned.
  Empty list if none.
- try_this: one concrete action the person could take after reading, under 20 words.
  Use an empty string if the text suggests none.
- topic: one or two words, for example "Python", "AI tools", "Careers".
Answer with JSON only."""


def build_prompt(
    title: str | None, text: str, memory_ctx: str = "", loved: list[str] | None = None,
    note: str | None = None,
) -> list[dict]:
    parts = []
    if memory_ctx:
        parts.append(memory_ctx)
    if loved:
        parts.append(
            "Links the person loved before that look similar:\n" + "\n".join(f"- {t}" for t in loved)
        )
    if note:
        parts.append(f"The person's own note when saving it: {note}")
    parts.append(f"Page title: {title or '(unknown)'}\n\nPage text:\n{text}")
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


def get_client() -> ollama.Client:
    return ollama.Client(host=config.OLLAMA_HOST)


def generate_card(
    title: str | None, text: str, memory_ctx: str = "", loved: list[str] | None = None,
    note: str | None = None, client=None, retries: int = 2,
) -> Card:
    client = client or get_client()
    messages = build_prompt(title, text, memory_ctx, loved, note)
    last_error: Exception | None = None
    for _ in range(retries + 1):
        try:
            resp = client.chat(
                model=config.CARD_MODEL,
                messages=messages,
                format=Card.model_json_schema(),
                options={"temperature": 0.2, "num_ctx": 4096, "num_predict": 900},
            )
            return Card.model_validate_json(resp["message"]["content"])
        except Exception as exc:  # noqa: BLE001 - retry on bad JSON or transient errors
            last_error = exc
    raise CardError(f"model did not return a valid card: {last_error}")


def _embed(prefix: str, text: str, client=None) -> list[float]:
    client = client or get_client()
    resp = client.embed(model=config.EMBED_MODEL, input=prefix + text)
    vector = list(resp["embeddings"][0])
    if len(vector) != config.EMBED_DIMS:
        raise ValueError(
            f"embedding has {len(vector)} dimensions, expected {config.EMBED_DIMS}; "
            "check EMBED_MODEL and the Atlas vector index"
        )
    return vector


def embed_document(text: str, client=None) -> list[float]:
    return _embed("search_document: ", text, client)


def embed_query(text: str, client=None) -> list[float]:
    return _embed("search_query: ", text, client)
