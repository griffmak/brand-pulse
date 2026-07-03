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
    posts = json.loads(output)
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
