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

from brand_pulse import format_report, run_brand_pulse

app = FastAPI()

INDEX_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Brand Pulse</title>
<style>
  body { font-family: -apple-system, sans-serif; max-width: 640px; margin: 3rem auto; padding: 0 1rem; }
  h1 { font-size: 1.4rem; }
  #controls { display: flex; gap: 0.5rem; margin-bottom: 1.5rem; }
  #brand { flex: 1; padding: 0.5rem; font-size: 1rem; }
  button { padding: 0.5rem 1rem; font-size: 1rem; cursor: pointer; }
  #progress div { padding: 0.25rem 0; font-family: monospace; }
  #progress .error { color: #b00020; }
  #report { white-space: pre-wrap; font-family: monospace; background: #f5f5f5; padding: 1rem; margin-top: 1rem; }
</style>
</head>
<body>
  <h1>Brand Pulse</h1>
  <div id="controls">
    <input id="brand" placeholder="Enter a brand name" autofocus>
    <button id="go">Check</button>
  </div>
  <div id="progress"></div>
  <pre id="report"></pre>
  <script>
    const brandInput = document.getElementById('brand');
    const goBtn = document.getElementById('go');
    const progressEl = document.getElementById('progress');
    const reportEl = document.getElementById('report');

    function runCheck() {
      const brand = brandInput.value.trim();
      if (!brand) return;
      progressEl.innerHTML = '';
      reportEl.textContent = '';
      goBtn.disabled = true;

      const es = new EventSource('/api/stream?brand=' + encodeURIComponent(brand));

      es.addEventListener('progress', (e) => {
        const data = JSON.parse(e.data);
        const line = document.createElement('div');
        if (data.status === 'ok') {
          line.textContent = '✓ ' + data.platform + ': ' + data.count + ' (' + data.scope + ')';
        } else {
          line.className = 'error';
          line.textContent = '✗ ' + data.platform + ' unavailable: ' + data.message;
        }
        progressEl.appendChild(line);
      });

      es.addEventListener('done', (e) => {
        const data = JSON.parse(e.data);
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
        if (e.data) {
          const data = JSON.parse(e.data);
          const line = document.createElement('div');
          line.className = 'error';
          line.textContent = '✗ ' + data.message;
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
                q.put(("done", results, errors))
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
            elif item[0] == "error":
                _, message = item
                yield f"event: error\ndata: {json.dumps({'message': message})}\n\n"
                break
            else:
                _, results, errors = item
                report = format_report(brand, results)
                payload = {
                    "report": report,
                    "total": sum(r.count for r in results),
                }
                yield f"event: done\ndata: {json.dumps(payload)}\n\n"
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
