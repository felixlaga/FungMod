"""Load curated FungMod kinetic records from YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

import yaml

from fungal_model.data.kinetic_records import KineticRecord, KineticRecordError


class KineticRecordLoadError(ValueError):
    """Raised when a curated kinetic-record file cannot be loaded."""


def load_kinetic_record(path: str | Path) -> KineticRecord:
    """Load and validate a curated kinetic record."""

    record_path = Path(path)
    try:
        data = yaml.safe_load(record_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise KineticRecordLoadError(f"Could not read kinetic record {record_path}: {exc}") from exc
    if not isinstance(data, Mapping):
        raise KineticRecordLoadError(f"Kinetic record {record_path} must contain a mapping.")
    try:
        return KineticRecord.from_mapping(data).require_valid()
    except (KineticRecordError, TypeError, ValueError) as exc:
        raise KineticRecordLoadError(f"Kinetic record {record_path} is invalid: {exc}") from exc


__all__ = ["KineticRecordLoadError", "load_kinetic_record"]
