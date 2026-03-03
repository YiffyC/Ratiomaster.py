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
      --bg: #f2f5f7;
      --card: #ffffff;
      --text: #1e2a32;
      --muted: #61727f;
      --accent: #0e7c86;
      --accent-2: #15909c;
      --line: #d9e1e6;
      --danger: #b94747;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at 0% 0%, #d8ecee 0, transparent 35%),
        radial-gradient(circle at 100% 100%, #e7f1e3 0, transparent 30%),
        var(--bg);
    }
    .wrap { max-width: 1000px; margin: 24px auto; padding: 0 16px; }
    .hero {
      padding: 8px 0 12px;
      margin-bottom: 8px;
    }
    .brand {
      display: flex;
      justify-content: center;
      align-items: center;
    }
    .brand img {
      width: min(92vw, 520px);
      height: auto;
      max-height: 120px;
      object-fit: contain;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px;
      min-height: 100px;
    }
    .events-card { min-height: 180px; }
    .events-box {
      margin-top: 8px;
      max-height: 120px;
      overflow: auto;
      white-space: pre-wrap;
      background: #f7fbfc;
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 8px;
      font-size: 12px;
      color: var(--text);
    }
    .k { font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .07em; }
    .v { margin-top: 8px; font-size: 24px; font-weight: 600; }
    .panel {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px;
    }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px; }
    label { display: block; font-size: 13px; color: var(--muted); margin-bottom: 4px; }
    input[type="text"], input[type="number"] {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 8px 10px;
      font-size: 14px;
      background: #fff;
    }
    input[type="checkbox"] { transform: translateY(1px); margin-right: 6px; }
    .actions { display: flex; gap: 8px; margin-top: 6px; }
    button {
      border: 0;
      border-radius: 10px;
      padding: 9px 12px;
      cursor: pointer;
      color: #fff;
      background: var(--accent);
      font-weight: 600;
    }
    button.secondary { background: #8b9aa5; }
    button.danger { background: var(--danger); }
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
      <article class="card events-card"><div class="k">Events</div><pre id="events" class="events-box"></pre></article>
      <article class="card"><div class="k">Runtime</div><div class="v" id="runtime">-</div></article>
    </section>
    <section class="panel">
      <div class="row">
        <div><label>Listen port</label><input id="listen_port" type="number" min="1" max="65535"></div>
        <div><label>Min peers</label><input id="min_peers" type="number" min="0" max="100000"></div>
      </div>
      <div class="row">
        <div><label>UDP upstream host</label><input id="udp_upstream_host" type="text"></div>
        <div><label>UDP upstream port</label><input id="udp_upstream_port" type="number" min="0" max="65535"></div>
      </div>
      <div class="row">
        <div><label>Boost</label><input id="boost" type="number" min="0" max="1000000"></div>
        <div><label>Boost chance (%)</label><input id="boost_chance" type="number" min="0" max="100"></div>
      </div>
      <div class="row">
        <div><label>Upload ratio A</label><input id="upup_ratio_a" type="number" step="0.01"></div>
        <div><label>Upload ratio B</label><input id="upup_ratio_b" type="number" step="0.01"></div>
      </div>
      <div class="row">
        <div><label>Up/Down ratio A</label><input id="updown_ratio_a" type="number" step="0.01"></div>
        <div><label>Up/Down ratio B</label><input id="updown_ratio_b" type="number" step="0.01"></div>
      </div>
      <div class="row">
        <div><label><input id="udp_enabled" type="checkbox">UDP enabled</label></div>
        <div><label><input id="only_tracker" type="checkbox">Only tracker traffic</label></div>
      </div>
      <div class="row">
        <div><label><input id="only_local" type="checkbox">Only local clients</label></div>
        <div><label><input id="no_download" type="checkbox">No download mode</label></div>
      </div>
      <div class="row">
        <div><label><input id="seed" type="checkbox">Seed mode</label></div>
        <div><label><input id="log_tunnel_chunks" type="checkbox">Log tunnel chunks</label></div>
      </div>
      <div class="row">
        <div><label><input id="mitm_https" type="checkbox">MITM HTTPS</label></div>
        <div><label><input id="mitm_insecure_upstream" type="checkbox">MITM upstream insecure</label></div>
      </div>
      <div class="row">
        <div><label>MITM cert path</label><input id="mitm_cert_path" type="text"></div>
        <div><label>MITM key path</label><input id="mitm_key_path" type="text"></div>
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
      "listen_port","min_peers","udp_upstream_host","udp_upstream_port","boost","boost_chance",
      "upup_ratio_a","upup_ratio_b","updown_ratio_a","updown_ratio_b",
      "udp_enabled","only_tracker","only_local","no_download","seed","log_tunnel_chunks",
      "mitm_https","mitm_insecure_upstream","mitm_cert_path","mitm_key_path"
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
            "min_peers",
            "udp_upstream_port",
            "boost",
            "boost_chance",
            "udp_enabled",
            "only_tracker",
            "only_local",
            "no_download",
            "seed",
            "log_tunnel_chunks",
            "mitm_https",
            "mitm_insecure_upstream",
        }
        float_keys = {"upup_ratio_a", "upup_ratio_b", "updown_ratio_a", "updown_ratio_b"}
        str_keys = {"udp_upstream_host", "mitm_cert_path", "mitm_key_path"}
        bool_as_int = {
            "udp_enabled",
            "only_tracker",
            "only_local",
            "no_download",
            "seed",
            "log_tunnel_chunks",
            "mitm_https",
            "mitm_insecure_upstream",
        }

        for key, raw in payload.items():
            if key in int_keys:
                if isinstance(raw, bool) and key in bool_as_int:
                    self.settings[key] = int(raw)
                else:
                    self.settings[key] = int(str(raw).strip() or "0")
            elif key in float_keys:
                self.settings[key] = float(str(raw).strip() or "0")
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
        os.execv(sys.executable, [sys.executable, *sys.argv])


if __name__ == "__main__":
    asyncio.run(main())
