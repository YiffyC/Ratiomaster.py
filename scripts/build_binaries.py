from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ICON_PATH = ROOT / "logos" / "rgpy_logo.png"


def _data_arg(src: str, dst: str) -> str:
    sep = ";" if os.name == "nt" else ":"
    return f"{src}{sep}{dst}"


def _run_pyinstaller(name: str, entry: str) -> None:
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        name,
        "--add-data",
        _data_arg(str(ROOT / "logos"), "logos"),
        "--add-data",
        _data_arg(str(ROOT / "tls"), "tls"),
        str(ROOT / entry),
    ]
    if ICON_PATH.exists():
        cmd.extend(["--icon", str(ICON_PATH)])
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True, cwd=ROOT)


def main() -> None:
    _run_pyinstaller("rgpy-cli", "rgpy_cli.py")
    _run_pyinstaller("rgpy-webui", "rgpy_webui.py")
    print("Done. Binaries in:", ROOT / "dist")


if __name__ == "__main__":
    main()
