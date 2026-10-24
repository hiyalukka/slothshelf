from app.parsers import detect_source, parse_any, parse_bookmarks_html, parse_whatsapp_chat
from app.urls import extract_urls, normalize_url


def test_normalize_strips_tracking_www_fragment_slash():
    a = normalize_url("https://www.Example.com/post/?utm_source=x&b=2&a=1#top")
    b = normalize_url("http://example.com/post?a=1&b=2")
    assert a == b == "example.com/post?a=1&b=2"


def test_normalize_keeps_meaningful_query():
    assert normalize_url("https://youtube.com/watch?v=abc123&si=zzz") == "youtube.com/watch?v=abc123"


def test_extract_urls_trims_punctuation():
    text = "see https://a.com/x, and (https://b.org/y). also http://c.io/z!"
    assert extract_urls(text) == ["https://a.com/x", "https://b.org/y", "http://c.io/z"]


BOOKMARKS = """<!DOCTYPE NETSCAPE-Bookmark-file-1><DL><p>
<DT><A HREF="https://a.com/one">First</A>
<DT><A HREF="https://b.com/two">Second</A>
<DT><A HREF="javascript:void(0)">Bad</A></DL>"""


def test_bookmarks_html():
    items = parse_bookmarks_html(BOOKMARKS)
    assert [i["url"] for i in items] == ["https://a.com/one", "https://b.com/two"]
    assert items[0]["title"] == "First"


WHATSAPP = """12/10/24, 9:41 pm - You: read later https://a.com/rag
12/10/24, 9:42 pm - You: just a thought
13/10/24, 8:00 am - You: https://b.com/x and https://c.com/y
"""


def test_whatsapp_notes_and_multiple_links():
    items = parse_whatsapp_chat(WHATSAPP)
    assert [i["url"] for i in items] == ["https://a.com/rag", "https://b.com/x", "https://c.com/y"]
    assert items[0]["note"] == "read later"
    assert items[1]["note"] == "and"


def test_detect_and_parse_any():
    assert detect_source(BOOKMARKS) == "bookmarks"
    assert detect_source(WHATSAPP) == "whatsapp"
    source, items = parse_any("https://a.com\nhttps://b.com\nnot a link")
    assert source == "text" and len(items) == 2
