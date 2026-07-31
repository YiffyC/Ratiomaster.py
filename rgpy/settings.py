from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from .utils import get_profile_directory


DEFAULTS = {
    "first": 0,
    "id": "",
    "runtime": 0,
    "sessions": 0,
    "listen_port": 3773,
    "udp_enabled": 1,
    "mitm_https": 0,
    "mitm_cert_path": "tls/server.crt",
    "mitm_key_path": "tls/server.key",
    "update": 1,
    "no_download": 0,
    "inspect_bitfield": 1,
    "actual_down": 0,
    "reported_down": 0,
    "actual_up": 0,
    "reported_up": 0,
}


@dataclass
class Settings:
    path: Path = field(default_factory=lambda: get_profile_directory() / "settings.json")
    values: dict = field(default_factory=dict)

    def load(self) -> None:
        data = {}
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))

        now = int(time.time())
        defaults = dict(DEFAULTS)
        defaults["first"] = data.get("first", now)
        defaults["id"] = data.get("id") or hashlib.md5(f"{now}".encode("utf-8")).hexdigest()

        defaults.update(data)
        defaults["start"] = now
        self.values = defaults

    def save(self, totals: dict[str, int]) -> None:
        data = dict(self.values)
        data["sessions"] = int(data.get("sessions", 0)) + 1
        data["runtime"] = int(data.get("runtime", 0)) + int(time.time()) - int(data.get("start", 0))

        data["actual_down"] = int(data.get("actual_down", 0)) + int(totals.get("actual_down", 0))
        data["actual_up"] = int(data.get("actual_up", 0)) + int(totals.get("actual_up", 0))
        data["reported_down"] = int(data.get("reported_down", 0)) + int(totals.get("reported_down", 0))
        data["reported_up"] = int(data.get("reported_up", 0)) + int(totals.get("reported_up", 0))

        data.pop("start", None)
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")
