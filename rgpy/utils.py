from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


REAL_RE = re.compile(r"^[0-9]{0,3}(\.[0-9]{0,3})?$")
PER_RE = re.compile(r"^1?[0-9]{0,2}$")
PORT_RE = re.compile(r"^[0-9]{0,5}$")


def open_document(target: str) -> None:
    try:
        if os.name == "nt":
            subprocess.Popen(["rundll32.exe", "url.dll,FileProtocolHandler", target])
        else:
            subprocess.Popen(["xdg-open", target])
    except Exception:
        pass


def get_profile_directory() -> Path:
    cwd = Path.cwd()
    if (cwd / "settings.json").exists():
        return cwd

    if os.name != "nt":
        return cwd

    appdata = os.environ.get("APPDATA")
    if not appdata:
        return cwd

    path = Path(appdata) / "RatioGhost"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_resource_path(relative_path: str) -> Path:
    # PyInstaller onefile extracts bundled data under sys._MEIPASS.
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / relative_path


def validate_real(value: str) -> bool:
    return bool(REAL_RE.match(value))


def validate_percent(value: str) -> bool:
    if not PER_RE.match(value):
        return False
    return int(value or "0") <= 100


def validate_port(value: str) -> bool:
    if not PORT_RE.match(value):
        return False
    return int(value or "0") <= 65534


def format_data(num: float) -> str:
    if num == 0:
        return "0"

    units = [(1024**4, "TB"), (1024**3, "GB"), (1024**2, "MB"), (1024, "KB")]
    for threshold, label in units:
        if num > threshold:
            return f"{num / threshold:.1f}{label}"
    return f"{round(num)}B"


def format_elapsed(num: float) -> str:
    if num == 0:
        return "0"

    units = [(86400, "d"), (3600, "h"), (60, "m")]
    for threshold, label in units:
        if num > threshold:
            return f"{num / threshold:.1f}{label}"
    return f"{round(num)}s"
