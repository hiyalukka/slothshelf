"""Turn the files people actually have into a list of links.

Supported: browser bookmarks export (HTML), a plain text file of links, and a
WhatsApp "message yourself" chat export. Every parser returns items shaped
{"url": str, "title": str | None, "note": str | None}.
"""
import re

from bs4 import BeautifulSoup

from .urls import extract_urls

WHATSAPP_LINE = re.compile(r"^\[?\d{1,2}[/.]\d{1,2}[/.]\d{2,4},?\s+\d{1,2}:\d{2}")
WHATSAPP_PREFIX = re.compile(r"^\[?[^\]-]*?\d{1,2}:\d{2}[^-\]]*[\]-]\s*[^:]*:\s*")


def parse_bookmarks_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.lower().startswith(("http://", "https://")):
            title = a.get_text(strip=True) or None
            items.append({"url": href, "title": title, "note": None})
    return items


def parse_text_links(text: str) -> list[dict]:
    """One link per line. Words after or before the link become its note (a pasted caption)."""
    items = []
    for line in text.splitlines():
        urls = extract_urls(line)
        if not urls:
            continue
        rest = line
        for url in urls:
            rest = rest.replace(url, "")
        note = " ".join(rest.strip(" -|:,.\t").split()) or None
        items.extend({"url": u, "title": None, "note": note} for u in urls)
    return items


def parse_whatsapp_chat(text: str) -> list[dict]:
    """Links from a chat export. The words around a link become its note."""
    items = []
    for line in text.splitlines():
        urls = extract_urls(line)
        if not urls:
            continue
        body = WHATSAPP_PREFIX.sub("", line, count=1) if WHATSAPP_LINE.match(line) else line
        for url in urls:
            body = body.replace(url, "")
        note = " ".join(body.split()) or None
        for url in urls:
            items.append({"url": url, "title": None, "note": note})
    return items


def detect_source(content: str) -> str:
    head = content[:4000].lower()
    if "netscape-bookmark" in head or ("<dt>" in head and "<a " in head):
        return "bookmarks"
    if any(WHATSAPP_LINE.match(line) for line in content.splitlines()[:30]):
        return "whatsapp"
    return "text"


def parse_any(content: str) -> tuple[str, list[dict]]:
    """Detect the file kind and parse it. Returns (source, items)."""
    source = detect_source(content)
    parser = {
        "bookmarks": parse_bookmarks_html,
        "whatsapp": parse_whatsapp_chat,
        "text": parse_text_links,
    }[source]
    return source, parser(content)
