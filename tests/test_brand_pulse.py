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
