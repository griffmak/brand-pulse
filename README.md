# Brand Pulse

A single-file CLI that gives marketers a real, honestly-scoped mention-count
snapshot for a brand across Reddit, Twitter/X, YouTube, and web/news — in one
command.

Built on top of [agent-reach](https://github.com/Panniantong/agent-reach),
which selects, installs, and health-checks the best current access method
per platform (twitter-cli, OpenCLI, yt-dlp, Exa search). This tool is the
next layer up: one command that fans out across all of them and reports a
usable number, not just raw search results.

## Install

1. Install and configure agent-reach first: see
   https://github.com/Panniantong/agent-reach — you need Reddit (OpenCLI)
   and Twitter (twitter-cli) authenticated in addition to the zero-config
   YouTube/web channels.
2. Clone this repo and run `python3 brand_pulse.py "Brand Name"`.

Note: the `config/mcporter.json` file in this repo is required for the
web/news platform (Exa search) to work — mcporter resolves its server config
relative to the directory you run the command from, and this repo ships that
config so it works out of the box (it contains only a public URL, no API
key). If you've moved agent-reach's own mcporter config elsewhere, you don't
need to do anything extra; this file is self-contained.

Reddit search (via OpenCLI) requires Chrome to be open with the OpenCLI
extension connected — it reads your live browser session, not a cookie
snapshot like Twitter/X does.

## Usage

```bash
python3 brand_pulse.py "Duolingo"
python3 brand_pulse.py "Duolingo" --days 30 --limit 50
python3 brand_pulse.py "Duolingo" --json
```

## Honest numbers, not fake precision

Every count is a **scoped result-set size** — "top N results in the last
M days" — not a certified exhaustive total (platform search APIs don't
expose that). The scope is always printed next to the number.

## Why this exists

Built as a demo tool while exploring agent-reach's capabilities — full story
at [link to LinkedIn post].
