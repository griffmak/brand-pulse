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
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise CommandError(f"{' '.join(cmd)} failed: {result.stderr.strip()}")
    return result.stdout


@dataclass
class PlatformResult:
    platform: str
    count: int
    scope: str
    sample_titles: list[str] = field(default_factory=list)
