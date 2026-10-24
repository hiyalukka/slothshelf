"""Download a page and pull out its readable article text."""
from dataclasses import dataclass

import httpx
import trafilatura

from . import config

# Wikipedia and similar sites block anonymous bot signatures. Set FETCH_USER_AGENT in .env
# to include your own contact email.
HEADERS = {"User-Agent": config.FETCH_USER_AGENT}
MIN_TEXT_CHARS = 200
MIN_CAPTION_CHARS = 40
LOGIN_WALL_HINTS = ("log in", "log into", "sign in", "sign up", "create an account", "login")


@dataclass
class FetchResult:
    ok: bool
    title: str | None = None
    text: str = ""
    error: str | None = None
    caption_only: bool = False


def _usable_caption(description: str) -> bool:
    low = description.lower()
    return len(description) >= MIN_CAPTION_CHARS and not any(h in low for h in LOGIN_WALL_HINTS)


def fetch_page(
    url: str, client: httpx.Client | None = None, max_chars: int | None = None
) -> FetchResult:
    max_chars = max_chars or config.MAX_CHARS
    owns_client = client is None
    client = client or httpx.Client(
        follow_redirects=True, timeout=config.FETCH_TIMEOUT, headers=HEADERS
    )
    try:
        resp = client.get(url)
        if resp.status_code >= 400:
            return FetchResult(False, error=f"HTTP {resp.status_code}")
        ctype = resp.headers.get("content-type", "")
        if "html" not in ctype and "text" not in ctype:
            return FetchResult(False, error=f"not a web page ({ctype or 'unknown type'})")
        html = resp.text
    except httpx.HTTPError as exc:
        return FetchResult(False, error=f"fetch failed: {exc.__class__.__name__}")
    finally:
        if owns_client:
            client.close()

    text = trafilatura.extract(html, include_comments=False, include_tables=False) or ""
    meta = trafilatura.extract_metadata(html)
    title = meta.title if meta and meta.title else None
    description = (meta.description or "").strip() if meta else ""
    if len(text) >= MIN_TEXT_CHARS:
        return FetchResult(True, title=title, text=text[:max_chars])
    # Short page (for example a reel): fall back to its public caption, and say so.
    if _usable_caption(description):
        body = f"{title}. {description}" if title else description
        return FetchResult(True, title=title, text=body[:max_chars], caption_only=True)
    return FetchResult(
        False, title=title,
        error="no readable text (login wall, JavaScript-only or very short page)",
    )
