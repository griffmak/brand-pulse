#!/usr/bin/env python3
"""Brand Pulse web frontend — a local page you type a brand name into and
watch each platform (Reddit, Twitter/X, YouTube, Web/News) resolve live.

Run with: python3 app.py
Then open: http://127.0.0.1:8000
"""

import json
import queue
import threading

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse

from brand_pulse import format_report, run_brand_pulse, synthesize

app = FastAPI()

INDEX_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Brand Pulse</title>
<style>
  :root {
    --bg: #010409; --term: #0d1117; --chrome: #161b22; --border: #30363d;
    --green: #3fb950; --dim: #8b949e; --red: #f85149;
  }
  * { box-sizing: border-box; }
  body {
    background: var(--bg); color: var(--green);
    font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
    font-size: 14px; line-height: 1.7;
    max-width: 680px; margin: 8vh auto; padding: 0 1rem;
  }
  ::selection { background: var(--green); color: var(--term); }
  .window {
    background: var(--term); border: 1px solid var(--border);
    border-radius: 8px; box-shadow: 0 12px 40px rgba(0, 0, 0, 0.65);
    overflow: hidden;
  }
  .chrome {
    display: flex; align-items: center; gap: 7px; padding: 9px 12px;
    background: var(--chrome); border-bottom: 1px solid var(--border);
  }
  .dot { width: 12px; height: 12px; border-radius: 50%; flex: none; }
  .dot.r { background: #ff5f56; }
  .dot.y { background: #ffbd2e; }
  .dot.g { background: #27c93f; }
  .chrome h1 {
    flex: 1; margin: 0 45px 0 0; /* right margin balances the dots */
    font-size: 12px; font-weight: 400; color: var(--dim); text-align: center;
  }
  .term { padding: 1.1rem 1.25rem 1.4rem; min-height: 280px; }
  #controls { display: flex; flex-wrap: wrap; align-items: baseline; margin-bottom: 1rem; }
  .ps1 { color: var(--dim); white-space: pre; }
  #brand {
    field-sizing: content; min-width: 2ch; max-width: 100%;
    background: none; border: none; outline: none; padding: 0;
    font: inherit; color: inherit; caret-color: var(--green);
  }
  #brand::placeholder { color: var(--dim); opacity: 0.6; }
  .cursor { animation: blink 1.1s steps(1) infinite; }
  #brand:focus + .cursor { visibility: hidden; }
  #go {
    margin-left: auto; padding: 1px 10px;
    background: none; border: 1px solid var(--green); border-radius: 4px;
    font: inherit; color: var(--green); cursor: pointer;
  }
  #go:hover:not(:disabled) { background: rgba(63, 185, 80, 0.12); }
  #go:focus-visible { outline: 1px solid var(--green); outline-offset: 2px; }
  #go:disabled { border-color: var(--border); color: var(--dim); cursor: default; }
  #status { color: var(--dim); min-height: 1.7em; }
  #progress { white-space: pre-wrap; }
  #progress div { animation: rise 0.25s ease-out; }
  #progress .pending { color: var(--dim); }
  #progress .error { color: var(--red); }
  #summary {
    margin-top: 1rem; padding-top: 1rem; border-top: 1px dashed var(--border);
    animation: rise 0.25s ease-out;
  }
  #summary:empty { display: none; }
  #summary .brief { font-size: 1.05rem; font-weight: 700; margin-bottom: 0.5rem; }
  #summary .sub { color: var(--dim); }
  #summary .theme { margin-top: 0.4rem; }
  #summary .src { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  #summary a { color: var(--dim); text-decoration: underline dotted; }
  #summary a:hover, #summary a:focus-visible { color: var(--green); outline: none; }
  #report {
    white-space: pre-wrap; font: inherit; font-size: 12px; color: var(--dim);
    margin: 0.75rem 0 0;
  }
  #report:empty { display: none; }
  @keyframes blink { 50% { opacity: 0; } }
  @keyframes rise { from { opacity: 0; transform: translateY(3px); } }
  @media (prefers-reduced-motion: reduce) {
    .cursor, #progress div { animation: none; }
  }
</style>
</head>
<body>
  <div class="window">
    <div class="chrome">
      <span class="dot r"></span><span class="dot y"></span><span class="dot g"></span>
      <h1>brand-pulse — zsh</h1>
    </div>
    <div class="term">
      <div id="controls">
        <span class="ps1">$ </span><span>brand-pulse check&nbsp;</span><input
          id="brand" placeholder="enter a brand name" autofocus
          autocomplete="off" spellcheck="false"><span class="cursor"
          aria-hidden="true">&#9615;</span>
        <button id="go">run</button>
      </div>
      <div id="status"></div>
      <div id="progress"></div>
      <div id="summary"></div>
      <pre id="report"></pre>
    </div>
  </div>
  <script>
    const brandInput = document.getElementById('brand');
    const goBtn = document.getElementById('go');
    const statusEl = document.getElementById('status');
    const progressEl = document.getElementById('progress');
    const summaryEl = document.getElementById('summary');
    const reportEl = document.getElementById('report');

    // Must match the platform names run_brand_pulse reports via on_progress.
    const PLATFORMS = ['Reddit', 'Twitter/X', 'YouTube', 'Web/News'];
    const SPIN = ['\\u280b', '\\u2819', '\\u2839', '\\u2838', '\\u283c',
                  '\\u2834', '\\u2826', '\\u2827', '\\u2807', '\\u280f'];
    const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
    let spinTimer = null;
    let spinFrame = 0;

    function pad(name) { return name.toLowerCase().padEnd(10); }

    function startSpinner() {
      if (reducedMotion) return; // rows keep a static glyph instead
      spinTimer = setInterval(() => {
        spinFrame = (spinFrame + 1) % SPIN.length;
        for (const el of document.querySelectorAll('#progress .spin')) {
          el.textContent = SPIN[spinFrame];
        }
      }, 90);
    }

    function stopSpinner() {
      clearInterval(spinTimer);
      spinTimer = null;
    }

    function runCheck() {
      const brand = brandInput.value.trim();
      if (!brand) return;
      statusEl.textContent = '> checking ' + brand + '...';
      progressEl.innerHTML = '';
      summaryEl.textContent = '';
      reportEl.textContent = '';
      goBtn.disabled = true;

      for (const p of PLATFORMS) {
        const row = document.createElement('div');
        row.className = 'pending';
        row.dataset.platform = p;
        const spin = document.createElement('span');
        spin.className = 'spin';
        spin.textContent = '\\u25b8';
        row.append('  ', spin, ' ' + pad(p) + 'scanning...');
        progressEl.appendChild(row);
      }
      startSpinner();

      const es = new EventSource('/api/stream?brand=' + encodeURIComponent(brand));

      es.addEventListener('progress', (e) => {
        const data = JSON.parse(e.data);
        const line = document.createElement('div');
        if (data.status === 'ok') {
          line.textContent = '  \\u2713 ' + pad(data.platform) + data.count + ' (' + data.scope + ')';
        } else {
          line.className = 'error';
          line.textContent = '  \\u2717 ' + pad(data.platform) + 'unavailable: ' + data.message;
        }
        const row = progressEl.querySelector('[data-platform="' + CSS.escape(data.platform) + '"]');
        if (row) row.replaceWith(line); else progressEl.appendChild(line);
      });

      es.addEventListener('synth', (e) => {
        const data = JSON.parse(e.data);
        const row = document.createElement('div');
        row.className = 'pending';
        row.dataset.platform = 'synthesis';
        const spin = document.createElement('span');
        spin.className = 'spin';
        spin.textContent = '\\u25b8';
        row.append('  ', spin, ' ' + pad('synthesis') + 'reading ' +
          data.headlines + ' headlines...');
        progressEl.appendChild(row);
      });

      es.addEventListener('done', (e) => {
        const data = JSON.parse(e.data);
        stopSpinner();
        statusEl.textContent = '';
        const synthRow = progressEl.querySelector('[data-platform="synthesis"]');
        if (data.synthesis) {
          const s = data.synthesis;
          const themes = (s.themes || []).slice(0, 3);
          if (synthRow) {
            const line = document.createElement('div');
            line.textContent = '  \\u2713 ' + pad('synthesis') + themes.length +
              ' theme' + (themes.length === 1 ? '' : 's');
            synthRow.replaceWith(line);
          }
          const brief = document.createElement('div');
          brief.className = 'brief';
          brief.textContent = s.brief;
          summaryEl.append(brief);
          for (const t of themes) {
            const theme = document.createElement('div');
            theme.className = 'theme';
            theme.textContent = '\\u25b8 ' + t.title + ' \\u00b7 ' +
              (t.platforms || []).join(', ').toLowerCase();
            const action = document.createElement('div');
            action.className = 'sub';
            action.textContent = '   \\u2192 ' + t.action;
            summaryEl.append(theme, action);
            for (const src of (t.sources || [])) {
              const line = document.createElement('div');
              line.className = 'sub src';
              line.append('   \\u2197 ');
              if (src.url) {
                const a = document.createElement('a');
                a.href = src.url;
                a.target = '_blank';
                a.rel = 'noopener';
                a.textContent = src.title;
                line.append(a);
              } else {
                line.append(src.title);
              }
              summaryEl.append(line);
            }
          }
          const signal = document.createElement('div');
          signal.className = 'sub';
          signal.style.marginTop = '0.6rem';
          signal.textContent = '> signal: ' + s.relevant + ' of ' + s.sampled +
            ' sampled items about ' + brand;
          summaryEl.append(signal);
        } else if (synthRow) {
          synthRow.textContent = '  \\u00b7 ' + pad('synthesis') + 'unavailable';
        }
        reportEl.textContent = data.report;
        goBtn.disabled = false;
        es.close();
      });

      // Note: the browser fires the same "error" event both for a named
      // `event: error` block sent by the server (a MessageEvent, with
      // .data) and for a connection failure (a plain Event, no .data).
      // Using addEventListener('error', ...) AND es.onerror would both
      // fire for both cases, so this single handler covers both.
      es.addEventListener('error', (e) => {
        stopSpinner();
        statusEl.textContent = '';
        for (const row of progressEl.querySelectorAll('.pending')) {
          row.textContent = '  \\u00b7 ' + pad(row.dataset.platform) + 'skipped';
        }
        if (e.data) {
          const data = JSON.parse(e.data);
          const line = document.createElement('div');
          line.className = 'error';
          line.textContent = '  \\u2717 ' + data.message;
          progressEl.appendChild(line);
        }
        goBtn.disabled = false;
        es.close();
      });
    }

    goBtn.addEventListener('click', runCheck);
    brandInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') runCheck();
    });
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index():
    return INDEX_HTML


@app.get("/api/stream")
def stream(brand: str, days: int = 7, limit: int = 25):
    def event_generator():
        q: queue.Queue = queue.Queue()

        def on_progress(platform, result, error):
            q.put(("progress", platform, result, error))

        def worker():
            try:
                results, errors = run_brand_pulse(
                    brand, days=days, limit=limit, on_progress=on_progress
                )
                headlines = sum(len(r.sample_titles) for r in results)
                if headlines:
                    q.put(("synth", headlines))
                synthesis = synthesize(brand, results)
                q.put(("done", results, errors, synthesis))
            except Exception as e:
                q.put(("error", str(e)))

        threading.Thread(target=worker, daemon=True).start()

        while True:
            item = q.get()
            if item[0] == "progress":
                _, platform, result, error = item
                if result is not None:
                    payload = {
                        "platform": platform,
                        "status": "ok",
                        "count": result.count,
                        "scope": result.scope,
                    }
                else:
                    payload = {
                        "platform": platform,
                        "status": "error",
                        "message": error,
                    }
                yield f"event: progress\ndata: {json.dumps(payload)}\n\n"
            elif item[0] == "synth":
                _, headlines = item
                yield f"event: synth\ndata: {json.dumps({'headlines': headlines})}\n\n"
            elif item[0] == "error":
                _, message = item
                yield f"event: error\ndata: {json.dumps({'message': message})}\n\n"
                break
            else:
                _, results, errors, synthesis = item
                report = format_report(brand, results)
                payload = {
                    "report": report,
                    "total": sum(r.count for r in results),
                    "synthesis": synthesis,
                }
                yield f"event: done\ndata: {json.dumps(payload)}\n\n"
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
