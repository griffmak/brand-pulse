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
import sys
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
    except OSError as e:
        raise CommandError(f"{' '.join(cmd)} failed to start: {e}") from e
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
        sample_titles=[p["title"] for p in posts],
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
        sample_titles=[t["text"] for t in tweets],
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
        sample_titles=titles,
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
        sample_titles=titles,
    )


def format_report(brand: str, results: list[PlatformResult]) -> str:
    lines = [f"Brand Pulse: {brand}", "=" * (13 + len(brand))]
    for r in results:
        lines.append(f"  {r.platform}: {r.count} ({r.scope})")
        # ponytail: full sample_titles feed synthesize(); the report shows 3
        for title in r.sample_titles[:3]:
            lines.append(f"      - {title}")
    total = sum(r.count for r in results)
    lines.append("")
    lines.append(f"Total: {total} mentions across {len(results)} platform(s)")
    return "\n".join(lines)


SYNTH_MODEL = "claude-opus-4-8"


def synthesize(brand: str, results: list[PlatformResult]):
    """Turn the sampled titles into a brief + themes via the local claude CLI.

    Returns {"brief", "themes": [{"title", "platforms", "action"}],
    "relevant", "sampled"} or None when there is nothing to synthesize or the
    CLI is missing/fails — callers degrade to the counts-and-titles report.
    """
    items = [(r.platform, t) for r in results for t in r.sample_titles]
    if not items:
        return None
    listing = "\n".join(f"[{p}] {t}" for p, t in items)
    n = len(items)
    prompt = f"""You are a brand analyst. Below are {n} raw titles/snippets sampled from
Reddit, Twitter/X, YouTube, and Web/News search results for the brand
"{brand}" (roughly the past week). Counts are top-N samples, not exhaustive.

1. Discard items not plausibly about the brand "{brand}".
2. Group the rest into at most 3 themes.
3. For each theme: a short title, the platforms it appears on, and one
   suggested move for the brand's social/comms team. No invented numbers.
4. Write a 1-2 sentence overall brief. If little is relevant, say the
   conversation is quiet rather than inventing themes.

Respond with ONLY valid JSON, no markdown fences, in exactly this shape:
{{"brief": "...", "themes": [{{"title": "...", "platforms": ["..."], "action": "..."}}], "relevant": <int>, "sampled": {n}}}

Items:
{listing}"""
    try:
        proc = subprocess.run(
            ["claude", "-p", "--model", SYNTH_MODEL],
            input=prompt, capture_output=True, text=True, timeout=300,
        )
        if proc.returncode != 0:
            return None
        text = proc.stdout
        # ponytail: slice first { to last } — survives fences and preamble
        data = json.loads(text[text.index("{"): text.rindex("}") + 1])
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    if not isinstance(data, dict) or "brief" not in data or "themes" not in data:
        return None
    return data


def run_brand_pulse(
    brand: str,
    days: int = 7,
    limit: int = 25,
    reddit_fn=search_reddit,
    twitter_fn=search_twitter,
    youtube_fn=search_youtube,
    web_fn=search_web,
    on_progress=None,
) -> tuple[list[PlatformResult], list[tuple[str, str]]]:
    """Run all 4 platform searches, isolating failures per-platform.

    Returns (results, errors) — errors is a list of (platform_name, message)
    for any platform that raised CommandError (or a parsing-shape error like
    KeyError/IndexError/TypeError/AttributeError, since a JSON response can be
    well-formed JSON but still not have the fields or shape we expect), so one
    dead platform doesn't take down the whole report.

    If on_progress is given, it's called as on_progress(platform_name, result,
    error) right after each platform attempt: result is the PlatformResult and
    error is None on success; result is None and error is the message string
    on failure. This lets a caller (e.g. the web app's SSE stream) push live
    feedback as each platform resolves, without changing the return value.
    """
    platform_calls = [
        ("Reddit", lambda: reddit_fn(brand, days, limit)),
        ("Twitter/X", lambda: twitter_fn(brand, days, limit)),
        ("YouTube", lambda: youtube_fn(brand, limit)),
        ("Web/News", lambda: web_fn(brand, limit)),
    ]
    results = []
    errors = []
    for name, call in platform_calls:
        try:
            result = call()
            results.append(result)
            if on_progress:
                on_progress(name, result, None)
        except (CommandError, KeyError, IndexError, TypeError, AttributeError) as e:
            errors.append((name, str(e)))
            if on_progress:
                on_progress(name, None, str(e))
    return results, errors


def main():
    parser = argparse.ArgumentParser(
        prog="brand_pulse",
        description="Cross-platform mention-count snapshot for a brand, "
                     "built on agent-reach (github.com/Panniantong/agent-reach).",
    )
    parser.add_argument("brand", help="Brand name to search for")
    parser.add_argument("--days", type=int, default=7,
                         help="Timeframe in days for platforms that support it (default: 7)")
    parser.add_argument("--limit", type=int, default=25,
                         help="Max results to request per platform (default: 25)")
    parser.add_argument("--json", action="store_true",
                         help="Output machine-readable JSON instead of the text report")
    args = parser.parse_args()

    results, errors = run_brand_pulse(args.brand, days=args.days, limit=args.limit)
    synthesis = synthesize(args.brand, results)

    if args.json:
        payload = {
            "brand": args.brand,
            "results": [r.__dict__ for r in results],
            "errors": [{"platform": p, "message": m} for p, m in errors],
            "total_mentions": sum(r.count for r in results),
            "synthesis": synthesis,
        }
        print(json.dumps(payload, indent=2))
    else:
        print(format_report(args.brand, results))
        if synthesis:
            print(f"\nBrief: {synthesis['brief']}")
            for t in synthesis.get("themes", []):
                platforms = ", ".join(t.get("platforms", []))
                print(f"  - {t['title']} ({platforms}) -> {t['action']}")
            print(f"Signal: {synthesis.get('relevant', '?')} of "
                  f"{synthesis.get('sampled', '?')} sampled items about {args.brand}")
        else:
            print("\n  [!] synthesis unavailable (claude CLI missing or failed)",
                  file=sys.stderr)
        for platform, message in errors:
            print(f"\n  [!] {platform} unavailable: {message}", file=sys.stderr)

    if not results and errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
