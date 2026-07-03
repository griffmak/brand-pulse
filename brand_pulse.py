#!/usr/bin/env python3
"""Brand Pulse — cross-platform mention-count snapshot for a brand.

Built on top of agent-reach (https://github.com/Panniantong/agent-reach) —
this script shells out to the same upstream CLIs agent-reach installs and
health-checks (twitter-cli, OpenCLI, yt-dlp, Exa via mcporter), and adds a
single command that fans out to all of them and reports a scoped mention
count per platform.
"""

import argparse
import json
import subprocess
from dataclasses import dataclass, field
from datetime import date, timedelta


class CommandError(RuntimeError):
    """Raised when an underlying platform CLI fails."""


def run_command(cmd: list[str], timeout: int = 30) -> str:
    """Run a shell command and return its stdout, raising CommandError on failure."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise CommandError(f"{' '.join(cmd)} timed out after {timeout}s")
    if result.returncode != 0:
        raise CommandError(f"{' '.join(cmd)} failed: {result.stderr.strip()}")
    return result.stdout


@dataclass
class PlatformResult:
    platform: str
    count: int
    scope: str
    sample_titles: list[str] = field(default_factory=list)


def _reddit_time_filter(days: int) -> str:
    if days <= 1:
        return "day"
    if days <= 7:
        return "week"
    if days <= 30:
        return "month"
    if days <= 365:
        return "year"
    return "all"


def search_reddit(query: str, days: int = 7, limit: int = 25) -> PlatformResult:
    time_filter = _reddit_time_filter(days)
    output = run_command([
        "opencli", "reddit", "search", query,
        "--time", time_filter, "--limit", str(limit), "-f", "json",
    ])
    try:
        posts = json.loads(output)
    except json.JSONDecodeError as e:
        raise CommandError(f"opencli returned invalid JSON: {e}") from e
    scope = (
        f"top {limit} Reddit results, all time"
        if time_filter == "all"
        else f"top {limit} Reddit results, past {time_filter}"
    )
    return PlatformResult(
        platform="Reddit",
        count=len(posts),
        scope=scope,
        sample_titles=[p["title"] for p in posts[:3]],
    )


def _date_days_ago(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


def search_twitter(query: str, days: int = 7, limit: int = 25) -> PlatformResult:
    since_date = _date_days_ago(days)
    output = run_command([
        "twitter", "search", query,
        "--since", since_date, "--max", str(limit), "--json",
    ])
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as e:
        raise CommandError(f"twitter-cli returned invalid JSON: {e}") from e
    tweets = payload.get("data", [])
    return PlatformResult(
        platform="Twitter/X",
        count=len(tweets),
        scope=f"top {limit} tweets since {since_date}",
        sample_titles=[t["text"] for t in tweets[:3]],
    )


def search_youtube(query: str, limit: int = 25) -> PlatformResult:
    output = run_command([
        "yt-dlp", f"ytsearch{limit}:{query}",
        "--flat-playlist", "--print", "%(title)s", "--no-warnings",
    ], timeout=60)
    titles = [line for line in output.splitlines() if line.strip()]
    return PlatformResult(
        platform="YouTube",
        count=len(titles),
        scope=f"top {limit} YouTube results (no native recency filter)",
        sample_titles=titles[:3],
    )


def search_web(query: str, limit: int = 25) -> PlatformResult:
    output = run_command([
        "mcporter", "call", "exa.web_search_exa",
        f"query={query} brand news", f"numResults={limit}", "--output", "json",
    ], timeout=45)
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as e:
        raise CommandError(f"mcporter returned invalid JSON: {e}") from e
    text = payload["content"][0]["text"]
    titles = [
        line[len("Title: "):].strip()
        for line in text.splitlines()
        if line.startswith("Title: ")
    ]
    return PlatformResult(
        platform="Web/News",
        count=len(titles),
        scope=f"top {limit} web/news results",
        sample_titles=titles[:3],
    )


def format_report(brand: str, results: list[PlatformResult]) -> str:
    lines = [f"Brand Pulse: {brand}", "=" * (13 + len(brand))]
    for r in results:
        lines.append(f"  {r.platform}: {r.count} ({r.scope})")
        for title in r.sample_titles:
            lines.append(f"      - {title}")
    total = sum(r.count for r in results)
    lines.append("")
    lines.append(f"Total: {total} mentions across {len(results)} platform(s)")
    return "\n".join(lines)
