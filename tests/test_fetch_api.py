import httpx

from app.fetch import fetch_page
from app.search import vector_pipeline

ARTICLE = "<html><head><title>Good post</title></head><body><article><p>" + (
    "Retrieval augmented generation combines search with a language model. " * 12
) + "</p></article></body></html>"


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_fetch_extracts_text_and_title():
    c = client_for(lambda r: httpx.Response(200, text=ARTICLE, headers={"content-type": "text/html"}))
    res = fetch_page("https://a.com/p", client=c, max_chars=300)
    assert res.ok and res.title == "Good post" and 100 < len(res.text) <= 300


def test_fetch_http_error_and_non_html_and_empty():
    c = client_for(lambda r: httpx.Response(403))
    assert fetch_page("https://a.com", client=c).error == "HTTP 403"
    c = client_for(lambda r: httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"}))
    assert "not a web page" in fetch_page("https://a.com", client=c).error
    c = client_for(lambda r: httpx.Response(200, text="<html><body>hi</body></html>",
                                            headers={"content-type": "text/html"}))
    assert "no readable text" in fetch_page("https://a.com", client=c).error


def test_fetch_network_error_is_reported_not_raised():
    def boom(request):
        raise httpx.ConnectError("nope")

    res = fetch_page("https://a.com", client=client_for(boom))
    assert not res.ok and "ConnectError" in res.error


def test_vector_pipeline_shape():
    p = vector_pipeline([0.0] * 768, limit=5, state="loved")
    stage = p[0]["$vectorSearch"]
    assert stage["index"] == "links_vector" and stage["path"] == "embedding"
    assert stage["filter"] == {"user.state": "loved"} and stage["numCandidates"] >= 100
    assert "filter" not in vector_pipeline([0.0], 3)[0]["$vectorSearch"]
    assert p[-1] == {"$project": {"embedding": 0}}


def test_app_imports_and_routes_exist():
    from app.main import app

    paths = {r.path for r in app.routes}
    for expected in ["/", "/api/import", "/api/process", "/api/links", "/api/search",
                     "/api/links/{link_id}/mark", "/api/digest", "/api/goals", "/api/stats",
                     "/api/health"]:
        assert expected in paths
