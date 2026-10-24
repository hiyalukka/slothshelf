"""URL helpers: pull links out of text and normalise them for dedupe."""
import re
from urllib.parse import parse_qsl, urlencode, urlsplit

URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.IGNORECASE)
TRAILING_PUNCT = ".,;:!?"

TRACKING_PARAMS = {
    "fbclid", "gclid", "igshid", "igsh", "mc_cid", "mc_eid", "ref", "ref_src",
    "si", "feature", "s", "t",
}


def extract_urls(text: str) -> list[str]:
    """All http(s) URLs in text, in order, trailing punctuation removed."""
    urls = []
    for match in URL_RE.findall(text or ""):
        urls.append(match.rstrip(TRAILING_PUNCT))
    return urls


def normalize_url(url: str) -> str:
    """Stable key for a URL: no scheme, no www, no fragment, no tracking params."""
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path.rstrip("/")
    query = sorted(
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS
    )
    key = host + path
    if query:
        key += "?" + urlencode(query)
    return key
