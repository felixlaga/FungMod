"""Validated, frozen law-form evidence, distinct from parameter evidence."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any
import yaml


def load_mechanism_source(path: str | Path) -> dict[str, Any]:
    """Read an evidence record and verify every declared local artifact digest."""
    path = Path(path)
    record = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(record, dict):
        raise ValueError("Mechanism source must be a mapping.")
    for key in ("source_id", "citation", "doi", "url", "license", "retrieved_on", "study_system"):
        if not isinstance(record.get(key), str) or not record[key].strip():
            raise ValueError(f"Mechanism source requires {key}.")
    if not record["doi"].startswith("10.") or not record["url"].startswith("https://"):
        raise ValueError("Mechanism source requires a DOI and HTTPS source URL.")
    date.fromisoformat(record["retrieved_on"])
    for key in ("supports", "equations", "assumptions", "validity", "limitations"):
        if not isinstance(record.get(key), list) or not record[key]:
            raise ValueError(f"Mechanism source requires a nonempty {key} list.")
    for key in ("supports", "assumptions", "validity", "limitations"):
        if any(not isinstance(item, str) or not item.strip() for item in record[key]):
            raise ValueError(f"Mechanism source {key} entries must be nonempty strings.")
    if not set(record["supports"]) <= {"law_form", "constants", "data"}:
        raise ValueError("Unknown mechanism-source support classification.")
    for equation in record["equations"]:
        if not isinstance(equation, Mapping) or any(
            not isinstance(equation.get(key), str) or not equation[key].strip()
            for key in ("id", "location", "expression", "interpretation")
        ):
            raise ValueError("Each law equation requires id, location, expression and interpretation.")
    for artifact in record.get("artifacts", []):
        target = (path.parent / artifact["path"]).resolve()
        if not target.is_relative_to(path.parent.resolve()):
            raise ValueError("Mechanism-source artifact must remain inside the source directory.")
        if hashlib.sha256(target.read_bytes()).hexdigest() != artifact["sha256"]:
            raise ValueError(f"Mechanism-source artifact digest mismatch: {target.name}")
    return record


def validate_mechanism_source_links(proposal: Mapping[str, Any], *, root: str | Path) -> None:
    """Promoted BIO-004 mechanisms must link to checked law-form evidence."""
    if proposal.get("validation_status") == "proposed":
        return
    links = proposal.get("mechanism_sources", [])
    if not isinstance(links, list) or not links:
        raise ValueError("A promoted mechanism requires mechanism_sources.")
    root = Path(root).resolve()
    sources = []
    for link in links:
        path = (root / str(link)).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Mechanism-source reference must be inside the resource root.")
        sources.append(load_mechanism_source(path))
    if not any("law_form" in record["supports"] for record in sources):
        raise ValueError("A promoted mechanism requires at least one law_form source.")
