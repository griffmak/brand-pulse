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
