import json
import subprocess
import pytest

from brand_pulse import run_command, CommandError


def test_run_command_returns_stdout_on_success():
    output = run_command(["echo", "hello"])
    assert output.strip() == "hello"


def test_run_command_raises_on_nonzero_exit():
    with pytest.raises(CommandError):
        run_command(["python3", "-c", "import sys; sys.exit(1)"])


def test_run_command_raises_commanderror_on_timeout():
    with pytest.raises(CommandError):
        run_command(["sleep", "5"], timeout=1)


def test_run_command_raises_commanderror_when_binary_missing():
    with pytest.raises(CommandError):
        run_command(["this-binary-does-not-exist-xyz"])


from unittest.mock import patch

from brand_pulse import search_reddit

_REDDIT_JSON = """[
  {"id": "1ujtebv", "title": "Canceling Duolingo Max and selling my stock.",
   "subreddit": "r/duolingo", "author": "SDLivinGames", "score": 757,
   "comments": 114, "url": "https://reddit.com/r/duolingo/1ujtebv",
   "created_utc": 1782835569, "selftext": "", "post_hint": "",
   "url_overridden_by_dest": "", "preview_image_url": "", "gallery_urls": []},
  {"id": "1uibfc3", "title": "Duolingo is overhated.",
   "subreddit": "r/duolingo", "author": "someone", "score": 200,
   "comments": 40, "url": "https://reddit.com/r/duolingo/1uibfc3",
   "created_utc": 1782800000, "selftext": "", "post_hint": "",
   "url_overridden_by_dest": "", "preview_image_url": "", "gallery_urls": []}
]"""


def test_search_reddit_parses_count_and_scope():
    with patch("brand_pulse.run_command", return_value=_REDDIT_JSON) as mock_run:
        result = search_reddit("Duolingo", days=7, limit=25)

    assert result.platform == "Reddit"
    assert result.count == 2
    assert result.scope == "top 25 Reddit results, past week"
    assert result.sample_titles == [
        "Canceling Duolingo Max and selling my stock.",
        "Duolingo is overhated.",
    ]
    mock_run.assert_called_once_with(
        ["opencli", "reddit", "search", "Duolingo",
         "--time", "week", "--limit", "25", "-f", "json"]
    )


def test_search_reddit_time_filter_boundaries():
    with patch("brand_pulse.run_command", return_value="[]"):
        assert search_reddit("x", days=1, limit=10).scope == "top 10 Reddit results, past day"
        assert search_reddit("x", days=30, limit=10).scope == "top 10 Reddit results, past month"
        assert search_reddit("x", days=400, limit=10).scope == "top 10 Reddit results, all time"


def test_search_reddit_raises_commanderror_on_invalid_json():
    with patch("brand_pulse.run_command", return_value="not json"):
        with pytest.raises(CommandError):
            search_reddit("Duolingo")


from brand_pulse import search_twitter

_TWITTER_JSON = json.dumps({
    "ok": True,
    "schema_version": "1",
    "data": [
        {"id": "1", "text": "Duolingo streak day 400, still going strong"},
        {"id": "2", "text": "why does the duolingo owl haunt my dreams"},
    ],
})


def test_search_twitter_parses_count_and_scope():
    with patch("brand_pulse.run_command", return_value=_TWITTER_JSON) as mock_run:
        result = search_twitter("Duolingo", days=7, limit=25)

    assert result.platform == "Twitter/X"
    assert result.count == 2
    assert result.scope.startswith("top 25 tweets since ")
    assert result.sample_titles == [
        "Duolingo streak day 400, still going strong",
        "why does the duolingo owl haunt my dreams",
    ]
    called_cmd = mock_run.call_args[0][0]
    assert called_cmd[:3] == ["twitter", "search", "Duolingo"]
    assert "--since" in called_cmd
    assert "--json" in called_cmd


def test_search_twitter_raises_commanderror_on_invalid_json():
    with patch("brand_pulse.run_command", return_value="not json"):
        with pytest.raises(CommandError):
            search_twitter("Duolingo")


from brand_pulse import search_youtube

_YOUTUBE_TITLES = "Learn Chess on Duolingo\nDo your lesson, no buts.\nLanguage Learning Is Hard\n"


def test_search_youtube_parses_count_and_scope():
    with patch("brand_pulse.run_command", return_value=_YOUTUBE_TITLES) as mock_run:
        result = search_youtube("Duolingo", limit=25)

    assert result.platform == "YouTube"
    assert result.count == 3
    assert result.scope == "top 25 YouTube results (no native recency filter)"
    assert result.sample_titles == [
        "Learn Chess on Duolingo",
        "Do your lesson, no buts.",
        "Language Learning Is Hard",
    ]
    mock_run.assert_called_once_with(
        ["yt-dlp", "ytsearch25:Duolingo", "--flat-playlist",
         "--print", "%(title)s", "--no-warnings"],
        timeout=60,
    )


from brand_pulse import search_web

_EXA_JSON = json.dumps({
    "content": [
        {
            "type": "text",
            "text": (
                "Title: Duolingo Resets 'Unhinged' Marketing - Business Insider\n"
                "URL: https://example.com/a\nPublished: 2026-04-22\n"
                "Highlights:\n...\n\n---\n\n"
                "Title: Duolingo Won the Internet With Chaos - Inc.\n"
                "URL: https://example.com/b\nPublished: 2026-04-23\n"
                "Highlights:\n...\n\n---\n\n"
                "Title: Duolingo makes licensing debut with MINISO - Brands Untapped\n"
                "URL: https://example.com/c\nPublished: 2026-05-30\n"
                "Highlights:\n...\n"
            ),
        }
    ]
})


def test_search_web_parses_count_and_scope():
    with patch("brand_pulse.run_command", return_value=_EXA_JSON) as mock_run:
        result = search_web("Duolingo", limit=25)

    assert result.platform == "Web/News"
    assert result.count == 3
    assert result.scope == "top 25 web/news results"
    assert result.sample_titles == [
        "Duolingo Resets 'Unhinged' Marketing - Business Insider",
        "Duolingo Won the Internet With Chaos - Inc.",
        "Duolingo makes licensing debut with MINISO - Brands Untapped",
    ]
    mock_run.assert_called_once_with(
        ["mcporter", "call", "exa.web_search_exa",
         "query=Duolingo brand news", "numResults=25", "--output", "json"],
        timeout=45,
    )


def test_search_web_raises_commanderror_on_invalid_json():
    with patch("brand_pulse.run_command", return_value="not json"):
        with pytest.raises(CommandError):
            search_web("Duolingo")


from brand_pulse import format_report, PlatformResult


def test_format_report_renders_all_platforms_and_total():
    results = [
        PlatformResult("Reddit", 12, "top 25 Reddit results, past week", ["a", "b"]),
        PlatformResult("Twitter/X", 25, "top 25 tweets since 2026-06-26", ["c"]),
        PlatformResult("YouTube", 8, "top 25 YouTube results (no native recency filter)", []),
        PlatformResult("Web/News", 5, "top 25 web/news results", []),
    ]

    report = format_report("Duolingo", results)

    assert "Duolingo" in report
    assert "Reddit: 12 (top 25 Reddit results, past week)" in report
    assert "Twitter/X: 25 (top 25 tweets since 2026-06-26)" in report
    assert "YouTube: 8 (top 25 YouTube results (no native recency filter))" in report
    assert "Web/News: 5 (top 25 web/news results)" in report
    assert "Total: 50 mentions" in report


def test_format_report_handles_empty_results():
    report = format_report("Nobody", [])
    assert "Total: 0 mentions" in report


from brand_pulse import run_brand_pulse


def test_run_brand_pulse_continues_when_one_platform_fails():
    good_result = PlatformResult("Reddit", 5, "top 25 Reddit results, past week", [])

    def fake_reddit(query, days, limit):
        return good_result

    def fake_twitter(query, days, limit):
        raise CommandError("twitter-cli: cookies expired")

    def fake_youtube(query, limit):
        return PlatformResult("YouTube", 3, "top 25 YouTube results (no native recency filter)", [])

    def fake_web(query, limit):
        return PlatformResult("Web/News", 2, "top 25 web/news results", [])

    results, errors = run_brand_pulse(
        "Duolingo", days=7, limit=25,
        reddit_fn=fake_reddit, twitter_fn=fake_twitter,
        youtube_fn=fake_youtube, web_fn=fake_web,
    )

    assert results == [good_result,
                        PlatformResult("YouTube", 3, "top 25 YouTube results (no native recency filter)", []),
                        PlatformResult("Web/News", 2, "top 25 web/news results", [])]
    assert errors == [("Twitter/X", "twitter-cli: cookies expired")]


def test_run_brand_pulse_isolates_keyerror_and_indexerror_too():
    """Widened exception handling: parsing bugs (KeyError/IndexError/TypeError)
    in a platform function must be isolated the same way CommandError is,
    since json.loads() succeeding doesn't guarantee the expected shape."""
    def fake_reddit(query, days, limit):
        return PlatformResult("Reddit", 5, "top 25 Reddit results, past week", [])

    def fake_twitter(query, days, limit):
        raise KeyError("text")

    def fake_youtube(query, limit):
        raise IndexError("list index out of range")

    def fake_web(query, limit):
        return PlatformResult("Web/News", 2, "top 25 web/news results", [])

    results, errors = run_brand_pulse(
        "Duolingo", days=7, limit=25,
        reddit_fn=fake_reddit, twitter_fn=fake_twitter,
        youtube_fn=fake_youtube, web_fn=fake_web,
    )

    assert [r.platform for r in results] == ["Reddit", "Web/News"]
    assert ("Twitter/X", "'text'") == errors[0]
    assert errors[1][0] == "YouTube"


def test_run_brand_pulse_isolates_attributeerror_too():
    """A platform response can be valid JSON but the wrong shape (e.g. a bare
    list/None instead of a dict), so payload.get(...) raises AttributeError —
    that must be isolated the same way CommandError/KeyError/IndexError are."""
    def fake_reddit(query, days, limit):
        return PlatformResult("Reddit", 5, "top 25 Reddit results, past week", [])

    def fake_twitter(query, days, limit):
        raise AttributeError("'list' object has no attribute 'get'")

    def fake_youtube(query, limit):
        return PlatformResult("YouTube", 3, "top 25 YouTube results (no native recency filter)", [])

    def fake_web(query, limit):
        return PlatformResult("Web/News", 2, "top 25 web/news results", [])

    results, errors = run_brand_pulse(
        "Duolingo", days=7, limit=25,
        reddit_fn=fake_reddit, twitter_fn=fake_twitter,
        youtube_fn=fake_youtube, web_fn=fake_web,
    )

    assert [r.platform for r in results] == ["Reddit", "YouTube", "Web/News"]
    assert errors == [("Twitter/X", "'list' object has no attribute 'get'")]


def test_run_brand_pulse_calls_on_progress_for_each_platform():
    def fake_reddit(query, days, limit):
        return PlatformResult("Reddit", 5, "top 25 Reddit results, past week", [])

    def fake_twitter(query, days, limit):
        raise CommandError("twitter-cli: cookies expired")

    def fake_youtube(query, limit):
        return PlatformResult("YouTube", 3, "top 25 YouTube results (no native recency filter)", [])

    def fake_web(query, limit):
        return PlatformResult("Web/News", 2, "top 25 web/news results", [])

    progress_calls = []

    def record_progress(platform, result, error):
        progress_calls.append((platform, result, error))

    run_brand_pulse(
        "Duolingo", days=7, limit=25,
        reddit_fn=fake_reddit, twitter_fn=fake_twitter,
        youtube_fn=fake_youtube, web_fn=fake_web,
        on_progress=record_progress,
    )

    assert progress_calls == [
        ("Reddit", PlatformResult("Reddit", 5, "top 25 Reddit results, past week", []), None),
        ("Twitter/X", None, "twitter-cli: cookies expired"),
        ("YouTube", PlatformResult("YouTube", 3, "top 25 YouTube results (no native recency filter)", []), None),
        ("Web/News", PlatformResult("Web/News", 2, "top 25 web/news results", []), None),
    ]


def test_run_brand_pulse_without_on_progress_still_works():
    """Existing callers that don't pass on_progress must be unaffected."""
    def fake_reddit(query, days, limit):
        return PlatformResult("Reddit", 5, "top 25 Reddit results, past week", [])

    def fake_twitter(query, days, limit):
        return PlatformResult("Twitter/X", 1, "top 25 tweets since 2026-06-26", [])

    def fake_youtube(query, limit):
        return PlatformResult("YouTube", 1, "top 25 YouTube results (no native recency filter)", [])

    def fake_web(query, limit):
        return PlatformResult("Web/News", 1, "top 25 web/news results", [])

    results, errors = run_brand_pulse(
        "Duolingo", reddit_fn=fake_reddit, twitter_fn=fake_twitter,
        youtube_fn=fake_youtube, web_fn=fake_web,
    )
    assert len(results) == 4
    assert errors == []
