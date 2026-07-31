from __future__ import annotations

import argparse
import asyncio
import base64
import contextlib
import json
import logging
import os
import signal
import sys
import time
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .proxy import RatioGhostProxy
from .settings import Settings
from .utils import format_data, format_elapsed, get_resource_path

LOGO_PATH = get_resource_path("logos/rgpy_long.png")
FAVICON_PATH = get_resource_path("logos/rgpy_logo.png")

HTML_PAGE = """<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link rel="icon" type="image/png" href="__FAVICON_SRC__" />
  <title>Ratio Ghost - WebUI</title>
  <style>
    :root {
      --text: #1c1c1e;
      --muted: rgba(60, 60, 67, 0.6);
      --accent: #0a84ff;
      --accent-2: #5e5ce6;
      --danger: #ff453a;
      --glass-bg: rgba(255, 255, 255, 0.55);
      --glass-bg-strong: rgba(255, 255, 255, 0.75);
      --glass-border: rgba(255, 255, 255, 0.6);
      --glass-shadow: 0 8px 32px rgba(31, 38, 80, 0.14);
      --glass-highlight: inset 0 1px 0 rgba(255, 255, 255, 0.8);
      --field-bg: rgba(255, 255, 255, 0.6);
      --field-border: rgba(60, 60, 67, 0.18);
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --text: #f2f2f7;
        --muted: rgba(235, 235, 245, 0.6);
        --glass-bg: rgba(40, 40, 46, 0.55);
        --glass-bg-strong: rgba(50, 50, 58, 0.7);
        --glass-border: rgba(255, 255, 255, 0.14);
        --glass-shadow: 0 8px 32px rgba(0, 0, 0, 0.45);
        --glass-highlight: inset 0 1px 0 rgba(255, 255, 255, 0.08);
        --field-bg: rgba(20, 20, 24, 0.45);
        --field-border: rgba(255, 255, 255, 0.14);
      }
    }
    * { box-sizing: border-box; }
    html, body { height: 100%; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at 12% 8%, #7fd8ff 0, transparent 40%),
        radial-gradient(circle at 88% 15%, #c99bff 0, transparent 45%),
        radial-gradient(circle at 20% 90%, #a0f0c8 0, transparent 40%),
        radial-gradient(circle at 90% 85%, #ffb4c6 0, transparent 45%),
        linear-gradient(135deg, #eaf3ff, #f6ecff 60%, #eafff5);
      background-attachment: fixed;
      background-size: 140% 140%;
      animation: drift 24s ease-in-out infinite alternate;
    }
    @media (prefers-color-scheme: dark) {
      body {
        background:
          radial-gradient(circle at 12% 8%, rgba(10, 132, 255, 0.35) 0, transparent 40%),
          radial-gradient(circle at 88% 15%, rgba(94, 92, 230, 0.35) 0, transparent 45%),
          radial-gradient(circle at 20% 90%, rgba(48, 209, 88, 0.22) 0, transparent 40%),
          radial-gradient(circle at 90% 85%, rgba(255, 69, 58, 0.2) 0, transparent 45%),
          linear-gradient(135deg, #0b0b10, #131018 60%, #0c1210);
      }
    }
    @keyframes drift {
      from { background-position: 0% 0%, 0% 0%, 0% 0%, 0% 0%, 0% 0%; }
      to { background-position: 6% 4%, -6% -4%, 4% -6%, -4% 6%, 0% 0%; }
    }
    .wrap { max-width: 1000px; margin: 24px auto; padding: 0 16px; }
    .hero { padding: 8px 0 12px; margin-bottom: 8px; }
    .brand { display: flex; justify-content: center; align-items: center; }
    .brand img { width: min(92vw, 520px); height: auto; max-height: 120px; object-fit: contain; }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
      margin-bottom: 16px;
    }
    .card, .panel {
      background: var(--glass-bg);
      -webkit-backdrop-filter: blur(24px) saturate(180%);
      backdrop-filter: blur(24px) saturate(180%);
      border: 1px solid var(--glass-border);
      border-radius: 26px;
      padding: 16px 18px;
      box-shadow: var(--glass-shadow), var(--glass-highlight);
      transition: transform .25s ease, box-shadow .25s ease;
    }
    .card { min-height: 100px; }
    .card:hover { transform: translateY(-2px); }
    .events-card { min-height: 180px; margin-bottom: 16px; }
    .events-box {
      margin-top: 8px;
      max-height: 220px;
      overflow-y: auto;
      overflow-x: hidden;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      background: rgba(0, 0, 0, 0.06);
      border: 1px solid var(--glass-border);
      border-radius: 16px;
      padding: 10px;
      font-size: 12px;
      font-family: "SF Mono", ui-monospace, Menlo, Consolas, monospace;
      color: var(--text);
    }
    @media (prefers-color-scheme: dark) {
      .events-box { background: rgba(0, 0, 0, 0.35); }
    }
    .k { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .07em; }
    .v { margin-top: 8px; font-size: 24px; font-weight: 600; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px; }
    label { display: block; font-size: 13px; color: var(--muted); margin-bottom: 4px; }
    input[type="text"], input[type="number"] {
      width: 100%;
      border: 1px solid var(--field-border);
      border-radius: 14px;
      padding: 9px 12px;
      font-size: 14px;
      background: var(--field-bg);
      color: var(--text);
      outline: none;
      transition: box-shadow .2s ease, border-color .2s ease;
    }
    input[type="text"]:focus, input[type="number"]:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 4px rgba(10, 132, 255, 0.22);
    }
    input[type="checkbox"] { transform: translateY(1px) scale(1.1); margin-right: 8px; accent-color: var(--accent); }
    .actions { display: flex; gap: 10px; margin-top: 8px; flex-wrap: wrap; }
    button {
      border: 1px solid var(--glass-border);
      border-radius: 999px;
      padding: 10px 18px;
      cursor: pointer;
      color: #fff;
      background: linear-gradient(180deg, var(--accent), var(--accent-2));
      box-shadow: 0 4px 14px rgba(10, 132, 255, 0.35), var(--glass-highlight);
      font-weight: 600;
      font-family: inherit;
      transition: transform .15s ease, box-shadow .15s ease;
    }
    button:hover { transform: translateY(-1px); }
    button:active { transform: scale(0.96); }
    button.secondary {
      background: var(--glass-bg-strong);
      color: var(--text);
      box-shadow: var(--glass-shadow), var(--glass-highlight);
    }
    button.danger { background: linear-gradient(180deg, var(--danger), #c4281d); box-shadow: 0 4px 14px rgba(255, 69, 58, 0.35), var(--glass-highlight); }
    .status { margin-top: 10px; font-size: 13px; color: var(--muted); min-height: 18px; }
    @media (max-width: 760px) { .row { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <div class="brand">
        <img src="__LOGO_SRC__" alt="RGPy logo">
      </div>
    </section>
    <section class="grid">
      <article class="card"><div class="k">Etat proxy</div><div class="v" id="state">-</div></article>
      <article class="card"><div class="k">Stealth download</div><div class="v" id="stealth_state">-</div></article>
      <article class="card"><div class="k">Runtime</div><div class="v" id="runtime">-</div></article>
    </section>
    <section class="card events-card">
      <div class="k">Events</div>
      <pre id="events" class="events-box"></pre>
    </section>
    <section class="panel">
      <div class="row">
        <div><label>Listen port</label><input id="listen_port" type="number" min="1" max="65535"></div>
        <div><label><input id="udp_enabled" type="checkbox">UDP enabled</label></div>
      </div>
      <div class="row">
        <div><label><input id="no_download" type="checkbox">Stealth download (masquer le telechargement, left=0)</label></div>
        <div><label><input id="mitm_https" type="checkbox">MITM HTTPS (necessaire pour trackers en HTTPS)</label></div>
      </div>
      <div class="row">
        <div><label>MITM cert path</label><input id="mitm_cert_path" type="text"></div>
        <div><label>MITM key path</label><input id="mitm_key_path" type="text"></div>
      </div>
      <div class="row">
        <div><label><input id="inspect_bitfield" type="checkbox">Observer le bitfield envoye aux peers (lecture seule, diagnostic)</label></div>
      </div>
      <div class="actions">
        <button id="save">Sauvegarder</button>
        <button id="reload" class="secondary">Recharger (redemarrer)</button>
        <button id="shutdown" class="danger">Arreter WebUI</button>
      </div>
      <div class="status" id="status"></div>
    </section>
  </div>
  <script>
    const fields = [
      "listen_port","udp_enabled","no_download","mitm_https","mitm_cert_path","mitm_key_path","inspect_bitfield"
    ];
    let lastEventId = 0;
    let formDirty = false;
    let formLoaded = false;
    function setStatus(msg, bad=false){ const el=document.getElementById("status"); el.textContent=msg; el.style.color=bad?"#b94747":"#61727f"; }
    function readForm(){
      const out = {};
      for (const k of fields){
        const el = document.getElementById(k);
        if (!el) continue;
        out[k] = el.type === "checkbox" ? !!el.checked : el.value;
      }
      return out;
    }
    function fillForm(cfg){
      for (const k of fields){
        const el = document.getElementById(k);
        if (!el || !(k in cfg)) continue;
        if (el.type === "checkbox") el.checked = !!cfg[k];
        else el.value = cfg[k];
      }
    }
    async function refresh(){
      const r = await fetch("/api/status");
      if (!r.ok) throw new Error(`status ${r.status}`);
      const data = await r.json();
      document.getElementById("state").textContent = data.running ? "Running" : "Stopped";
      document.getElementById("stealth_state").textContent = data.settings.no_download ? "Actif" : "Inactif";
      document.getElementById("runtime").textContent = data.human.runtime;
      if (!formLoaded || !formDirty) {
        fillForm(data.settings);
        formLoaded = true;
      }
      await refreshEvents();
    }
    async function refreshEvents(){
      const r = await fetch(`/api/events?since=${lastEventId}`);
      if (!r.ok) return;
      const data = await r.json();
      const items = Array.isArray(data.items) ? data.items : [];
      if (!items.length) return;
      const box = document.getElementById("events");
      for (const e of items){
        const dt = new Date((e.ts || 0) * 1000);
        box.textContent += `[${dt.toLocaleTimeString()}] ${e.message}\n`;
        lastEventId = Math.max(lastEventId, Number(e.id || 0));
      }
      box.scrollTop = box.scrollHeight;
    }
    async function save(){
      const r = await fetch("/api/settings", {method:"POST", headers:{"content-type":"application/json"}, body:JSON.stringify(readForm())});
      if (!r.ok) { setStatus("Erreur de sauvegarde", true); return; }
      formDirty = false;
      setStatus("Settings sauvegardes. Redemarre le proxy pour listen_port/UDP structurels.");
      await refresh();
    }
    async function shutdown(){
      await fetch("/api/shutdown", {method:"POST"});
      setStatus("Arret en cours...");
    }
    document.getElementById("save").addEventListener("click", save);
    document.getElementById("reload").addEventListener("click", async () => {
      try {
        await save();
        const r = await fetch("/api/restart", {method:"POST"});
        if (!r.ok) { setStatus("Echec du redemarrage", true); return; }
        setStatus("Redemarrage en cours...");
      } catch {
        setStatus("Echec du redemarrage", true);
      }
    });
    document.getElementById("shutdown").addEventListener("click", shutdown);
    for (const k of fields) {
      const el = document.getElementById(k);
      if (!el) continue;
      el.addEventListener("input", () => { formDirty = true; });
      el.addEventListener("change", () => { formDirty = true; });
    }
    refresh().then(()=>setStatus("Pret.")).catch(()=>setStatus("Impossible de lire l'etat.", true));
    setInterval(()=>refresh().catch(()=>{}), 3000);
  </script>
</body>
</html>
"""


class WebUIApp:
    def __init__(self, settings: dict[str, Any], proxy: RatioGhostProxy, store: Settings, stop_event: asyncio.Event):
        self.settings = settings
        self.proxy = proxy
        self.store = store
        self.stop_event = stop_event
        self.restart_requested = False

    def snapshot(self) -> dict[str, Any]:
        totals = self.proxy.get_totals()
        runtime = int(self.settings.get("runtime", 0))
        if int(self.settings.get("start", 0)):
            runtime += int(time.time()) - int(self.settings.get("start", 0))
        return {
            "running": True,
            "totals": totals,
            "human": {
                "actual_down": format_data(totals["actual_down"]),
                "actual_up": format_data(totals["actual_up"]),
                "reported_down": format_data(totals["reported_down"]),
                "reported_up": format_data(totals["reported_up"]),
                "runtime": format_elapsed(runtime),
            },
            "settings": self.settings,
        }

    def update_settings(self, payload: dict[str, Any]) -> None:
        int_keys = {
            "listen_port",
            "udp_enabled",
            "no_download",
            "mitm_https",
            "inspect_bitfield",
        }
        str_keys = {"mitm_cert_path", "mitm_key_path"}
        bool_as_int = {
            "udp_enabled",
            "no_download",
            "mitm_https",
            "inspect_bitfield",
        }

        for key, raw in payload.items():
            if key in int_keys:
                if isinstance(raw, bool) and key in bool_as_int:
                    self.settings[key] = int(raw)
                else:
                    self.settings[key] = int(str(raw).strip() or "0")
            elif key in str_keys:
                self.settings[key] = str(raw).strip()

        self.persist_settings()

    def persist_settings(self) -> None:
        data = {k: v for k, v in self.settings.items() if k != "start"}
        self.store.path.write_text(json.dumps(data, indent=2), encoding="utf-8")


async def _read_request(reader: asyncio.StreamReader) -> tuple[str, str, dict[str, str], bytes] | None:
    try:
        raw_head = await reader.readuntil(b"\r\n\r\n")
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionResetError, OSError):
        return None

    text = raw_head.decode("latin-1", errors="ignore")
    lines = text.split("\r\n")
    if not lines or len(lines[0].split()) < 3:
        return None
    method, path, _ = lines[0].split(maxsplit=2)

    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line or ":" not in line:
            continue
        k, v = line.split(":", 1)
        headers[k.strip().lower()] = v.strip()

    body = b""
    content_len = int(headers.get("content-length", "0") or "0")
    if content_len > 0:
        body = await reader.readexactly(content_len)
    return method.upper(), path, headers, body


def _build_data_src(path: Path, mime: str, fallback: str) -> str:
    if path.exists():
        raw = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{raw}"
    return fallback


async def _write_response(
    writer: asyncio.StreamWriter,
    status: int,
    content_type: str,
    body: bytes,
) -> None:
    reason = {200: "OK", 204: "No Content", 400: "Bad Request", 404: "Not Found", 500: "Internal Server Error"}.get(
        status,
        "OK",
    )
    head = (
        f"HTTP/1.1 {status} {reason}\r\n"
        f"Content-Type: {content_type}\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n"
        "\r\n"
    )
    writer.write(head.encode("latin-1", errors="ignore") + body)
    await writer.drain()
    writer.close()
    with contextlib.suppress(Exception):
        await writer.wait_closed()


async def _handle_web_request(app: WebUIApp, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    req = await _read_request(reader)
    if req is None:
        await _write_response(writer, 400, "text/plain; charset=utf-8", b"bad request")
        return

    method, path, _, body = req
    split = urlsplit(path)
    route = split.path
    query = parse_qs(split.query or "")
    try:
        if method == "GET" and route == "/":
            page = HTML_PAGE
            page = page.replace("__LOGO_SRC__", _build_data_src(LOGO_PATH, "image/png", "/logo.png"))
            page = page.replace("__FAVICON_SRC__", _build_data_src(FAVICON_PATH, "image/png", "/logo.png"))
            await _write_response(writer, 200, "text/html; charset=utf-8", page.encode("utf-8"))
            return

        if method == "GET" and route == "/logo.png":
            if not LOGO_PATH.exists():
                await _write_response(writer, 404, "text/plain; charset=utf-8", b"logo not found")
                return
            await _write_response(writer, 200, "image/png", LOGO_PATH.read_bytes())
            return

        if method == "GET" and route == "/api/status":
            payload = json.dumps(app.snapshot(), ensure_ascii=False).encode("utf-8")
            await _write_response(writer, 200, "application/json; charset=utf-8", payload)
            return

        if method == "GET" and route == "/api/events":
            since = int((query.get("since") or ["0"])[0] or "0")
            payload = json.dumps({"items": app.proxy.get_events(since)}, ensure_ascii=False).encode("utf-8")
            await _write_response(writer, 200, "application/json; charset=utf-8", payload)
            return

        if method == "POST" and route == "/api/settings":
            data = json.loads(body.decode("utf-8") or "{}")
            if not isinstance(data, dict):
                await _write_response(writer, 400, "application/json; charset=utf-8", b'{"error":"invalid payload"}')
                return
            app.update_settings(data)
            await _write_response(writer, 200, "application/json; charset=utf-8", b'{"ok":true}')
            return

        if method == "POST" and route == "/api/shutdown":
            app.persist_settings()
            app.stop_event.set()
            await _write_response(writer, 204, "text/plain; charset=utf-8", b"")
            return

        if method == "POST" and route == "/api/restart":
            app.persist_settings()
            app.restart_requested = True
            app.stop_event.set()
            await _write_response(writer, 200, "application/json; charset=utf-8", b'{"ok":true,"restart":true}')
            return

        await _write_response(writer, 404, "text/plain; charset=utf-8", b"not found")
    except Exception as exc:
        payload = json.dumps({"error": str(exc)}).encode("utf-8")
        await _write_response(writer, 500, "application/json; charset=utf-8", payload)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Ratio Ghost Python WebUI")
    parser.add_argument("--port", type=int, default=None, help="Proxy listen port")
    parser.add_argument("--webui-port", type=int, default=8088, help="WebUI listen port")
    parser.add_argument("--verbose", action="store_true", help="Enable proxy traffic logs")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    store = Settings()
    store.load()
    if args.port:
        store.values["listen_port"] = args.port

    proxy = RatioGhostProxy(store.values, verbose=args.verbose)
    await proxy.start()

    stop = asyncio.Event()
    app = WebUIApp(store.values, proxy, store, stop)

    web_server = await asyncio.start_server(
        lambda r, w: _handle_web_request(app, r, w),
        host="127.0.0.1",
        port=int(args.webui_port),
    )

    def _stop(*_: object) -> None:
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            asyncio.get_running_loop().add_signal_handler(sig, _stop)
        except NotImplementedError:
            pass

    print(f"Proxy: 127.0.0.1:{store.values['listen_port']}")
    print(f"WebUI: http://127.0.0.1:{args.webui_port}")

    proxy_task = asyncio.create_task(proxy.serve_forever())
    web_task = asyncio.create_task(web_server.serve_forever())
    await stop.wait()

    for task in (proxy_task, web_task):
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    web_server.close()
    await web_server.wait_closed()

    totals = proxy.get_totals()
    store.save(totals)
    if app.restart_requested:
        cli_args = sys.argv[1:]
        if getattr(sys, "frozen", False):
            os.execv(sys.executable, [sys.executable, *cli_args])
        else:
            os.execv(sys.executable, [sys.executable, "-m", "rgpy.webui", *cli_args])


if __name__ == "__main__":
    asyncio.run(main())
