"""JSON export helpers for configs and reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def export_json(data: Any, path: str | Path) -> None:
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


__all__ = ["export_json"]
