# Ratiomaster.py

A Python reimplementation of the core proxy/tracker logic behind classic BitTorrent
ratio-management tools. Pure standard library — no third-party dependencies.
Runs on **Linux, Windows, and macOS** — same codebase, no platform-specific fork.

Built and shared for **educational and research purposes**: understanding tracker/proxy
behavior, protocol experimentation, and testing in controlled environments (your own
tracker, your own lab). See the Disclaimer section before using it anywhere else.

## What it does

Ratiomaster.py is a **ratio-maintenance tool**: its purpose is to let your BitTorrent
downloads happen normally in the background without them being counted against your
reported ratio — that's it. It is **not an upload-inflation tool**: it never fabricates
or boosts the upload figures reported to the tracker, only your real, actual upload
counts.

Concretely, it runs a small local proxy that sits between your BitTorrent client and
the trackers it talks to, and intercepts tracker announce traffic (HTTP, HTTPS via
optional MITM, and UDP/BEP 15). When stealth mode is enabled, it reports `downloaded=0`
and `left=0` to the tracker regardless of your real download progress — your client
keeps downloading normally, the tracker just never sees it as a debit against your
ratio. An optional web dashboard shows live stats and an event log.

This README stays high-level on purpose — see `rgpy/proxy.py` if you need the
implementation details of the rewriting logic.

## Platforms

| OS | Status |
|---|---|
| Linux | Supported — prebuilt binary via GitHub Actions (`rgpy-ubuntu-latest`) |
| Windows | Supported — prebuilt binary via GitHub Actions (`rgpy-windows-latest`) |
| macOS | Supported — prebuilt binary via GitHub Actions (`rgpy-macos-latest`) |

The whole project is standard-library-only asyncio Python, so no OS-specific code
paths to worry about beyond what Python itself already smooths over.

## Requirements

- Python 3.10+
- No third-party packages required

## Installation

```bash
git clone <this-repo>
cd Ratiomaster.py
```

Nothing else to install.

## Usage

### Terminal only (no web interface)

```bash
python -m rgpy.app --port 3773 --verbose
```

Prints live status to the terminal; stop with Ctrl+C. Settings are read from and
written to `settings.json` (see Configuration below).

### With the web dashboard

```bash
python -m rgpy.webui --port 3773 --webui-port 8088 --verbose
```

Then open:

```
http://127.0.0.1:8088
```

The dashboard shows proxy status and an event log, lets you edit and save the main
settings, and can restart the process from a button (no need for a separate terminal
command).

## Configuration

Settings persist in `settings.json`, created automatically on first run.

| Key | Purpose |
|---|---|
| `listen_port` | Proxy listen port — point your BitTorrent client's proxy setting here |
| `udp_enabled` | Enables the UDP tracker proxy (BEP 15) |
| `no_download` | Stealth mode for the download counters reported to the tracker |
| `mitm_https` | Enables HTTPS interception (requires a trusted local certificate) |
| `mitm_cert_path` / `mitm_key_path` | Local TLS certificate/key used for HTTPS interception |
| `inspect_bitfield` | Optional, read-only diagnostic: logs peer-wire handshake/bitfield activity without modifying any traffic |

A few advanced/fallback options (static UDP upstream, low-level tunnel logging,
upstream TLS verification) exist but aren't exposed in the dashboard — add them
directly to `settings.json` if needed; see `rgpy/settings.py` and `rgpy/proxy.py`.

### HTTPS interception (MITM)

Disabled by default. To use it:
1. Enable `MITM HTTPS` in the dashboard (or set `mitm_https: 1` in `settings.json`).
2. Make sure `mitm_cert_path` / `mitm_key_path` point to a valid certificate/key pair
   (`tls/server.crt` / `tls/server.key` by default).
3. Install that certificate as trusted on the OS or BitTorrent client — otherwise the
   TLS handshake will fail.
4. Restart the process.

## Building standalone executables

```bash
python -m pip install pyinstaller
python scripts/build_binaries.py
```

Produces `dist/rgpy-cli(.exe)` and `dist/rgpy-webui(.exe)`, built from `rgpy_cli.py`
and `rgpy_webui.py`.

Prebuilt binaries are also available via GitHub Actions
(`.github/workflows/build-binaries.yml` → `Run workflow` from the `Actions` tab) for
Windows, Ubuntu, and macOS.

## Limitations

- The original Tcl/Tk GUI is not reproduced here.
- The historical MITM TLS flow isn't reproduced exactly.
- Without a SOCKS5 UDP header or an existing `connection_id` mapping, UDP tracker
  routing needs a manually configured static upstream.

## FAQ

**What platforms does this support?**
Linux, Windows, and macOS — see the Platforms section above.

**Do I need to install anything besides Python?**
No. No third-party packages, no build step to run it from source.

**What is this actually for?**
Educational and research use — studying and testing BitTorrent tracker/proxy protocol
behavior in a controlled environment. It is not a commercial product and comes with no
support guarantee.

**Does this inflate my upload / fake my ratio upward?**
No. It's a ratio-*maintenance* tool, not an upload-inflation tool — it never touches or
boosts the upload figures reported to the tracker. The only thing it changes is hiding
your real download progress from the announce, so downloading doesn't count against
your ratio.

**Does it slow down or change my real download/upload traffic?**
No. It only rewrites what gets reported to the tracker in announce requests — it
doesn't touch the actual data exchanged with peers.

**Does it work with HTTPS trackers?**
Yes, through the optional local MITM mode, which requires trusting a locally generated
certificate. See the HTTPS interception section.

**Can I be detected using this?**
We cannot claim otherwise: **there is no guarantee you won't be detected.** Trackers
can rely on statistical analysis, peer-level verification, or manual staff audits that
this tool makes no attempt to defend against. Treat it as what it is — a research/test
tool, not a guaranteed-undetectable system — and only use it on infrastructure you own
or are explicitly authorized to test.

**Is this legal?**
That depends entirely on where you use it and against what. We provide no legal advice
here — see the Disclaimer below.

## Credits

Ratiomaster.py reimplements, from scratch in Python, the core proxy and
tracker-rewriting concepts of **Ratio Ghost**, originally created by **Yasmine**.
Full credit for the original idea and design goes to her — this project is an
independent Python port of the concept, not a copy of the original source.

## Disclaimer

This project is provided **as-is, for educational and research purposes only** — to
study and test BitTorrent tracker/proxy protocol behavior in a controlled environment.

- Use it only on infrastructure you own or are explicitly authorized to test against.
- We make no claim, express or implied, that its behavior is undetectable — see the
  FAQ. Any use against a tracker or service you don't control is at your own risk.
- You are solely responsible for complying with the rules of any tracker, service, or
  jurisdiction that applies to you. The authors and contributors of this project accept
  no liability for how it is used.
