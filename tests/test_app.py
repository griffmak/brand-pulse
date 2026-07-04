from unittest.mock import patch

from fastapi.testclient import TestClient

import app as app_module
from brand_pulse import PlatformResult


def test_index_serves_html_page():
    client = TestClient(app_module.app)
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Brand Pulse" in response.text
    assert "EventSource" in response.text


def test_stream_endpoint_emits_progress_and_done_events():
    def fake_run_brand_pulse(brand, days, limit, on_progress=None):
        result = PlatformResult("Reddit", 5, "top 25 Reddit results, past week", [])
        if on_progress:
            on_progress("Reddit", result, None)
            on_progress("Twitter/X", None, "twitter-cli: cookies expired")
        return [result], [("Twitter/X", "twitter-cli: cookies expired")]

    with patch("app.run_brand_pulse", fake_run_brand_pulse):
        client = TestClient(app_module.app)
        with client.stream("GET", "/api/stream", params={"brand": "Duolingo"}) as response:
            body = "".join(response.iter_text())

    assert "event: progress" in body
    assert '"platform": "Reddit"' in body
    assert '"status": "ok"' in body
    assert '"count": 5' in body
    assert '"platform": "Twitter/X"' in body
    assert '"status": "error"' in body
    assert "event: done" in body
    assert "Total: 5 mentions" in body


def test_stream_endpoint_emits_error_event_on_worker_exception():
    def fake_run_brand_pulse(brand, days, limit, on_progress=None):
        raise RuntimeError("boom")

    with patch("app.run_brand_pulse", fake_run_brand_pulse):
        client = TestClient(app_module.app)
        # If the generator failed to terminate (the bug under test), this
        # `with` block would hang forever instead of returning.
        with client.stream("GET", "/api/stream", params={"brand": "Duolingo"}) as response:
            body = "".join(response.iter_text())

    assert "event: error" in body
    assert '"message": "boom"' in body
