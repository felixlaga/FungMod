"""Small shared integrity primitives for curation and promotion APIs."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


CURATION_AUDIT_PROVENANCE_KEY = "fungmod_curation"
PARAMETER_BRIDGE_PROVENANCE_KEY = "fungmod_parameter_bridge"
RESERVED_PROVENANCE_KEYS = frozenset(
    {CURATION_AUDIT_PROVENANCE_KEY, PARAMETER_BRIDGE_PROVENANCE_KEY}
)


def canonicalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): canonicalize(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [canonicalize(item) for item in value]
    return value


def type_exact_equal(left: Any, right: Any) -> bool:
    if isinstance(left, Mapping) or isinstance(right, Mapping):
        if not isinstance(left, Mapping) or not isinstance(right, Mapping) or len(left) != len(right):
            return False
        for left_key, left_value in left.items():
            matching = [
                key for key in right if type(left_key) is type(key) and left_key == key
            ]
            if len(matching) != 1 or not type_exact_equal(left_value, right[matching[0]]):
                return False
        return True
    left_sequence = isinstance(left, Sequence) and not isinstance(
        left, (str, bytes, bytearray)
    )
    right_sequence = isinstance(right, Sequence) and not isinstance(
        right, (str, bytes, bytearray)
    )
    if left_sequence or right_sequence:
        return bool(
            left_sequence
            and right_sequence
            and len(left) == len(right)
            and all(type_exact_equal(a, b) for a, b in zip(left, right, strict=True))
        )
    return type(left) is type(right) and left == right


def round_trip_differences(
    expected: Any,
    actual: Any,
    *,
    path: str = "",
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    dropped: list[str] = []
    synthesized: list[str] = []
    changed: list[str] = []
    if isinstance(expected, Mapping) and isinstance(actual, Mapping):
        expected_keys = {str(key) for key in expected}
        actual_keys = {str(key) for key in actual}
        dropped.extend(_field_path(path, key) for key in sorted(expected_keys - actual_keys))
        synthesized.extend(_field_path(path, key) for key in sorted(actual_keys - expected_keys))
        for key in sorted(expected_keys & actual_keys):
            nested = round_trip_differences(
                expected[key],
                actual[key],
                path=_field_path(path, key),
            )
            dropped.extend(nested[0])
            synthesized.extend(nested[1])
            changed.extend(nested[2])
    elif not type_exact_equal(expected, actual):
        changed.append(path or "<record>")
    return tuple(dropped), tuple(synthesized), tuple(changed)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def first_symlink_component(path: Path) -> Path | None:
    absolute = path if path.is_absolute() else Path.cwd() / path
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        if current.is_symlink():
            return current
    return None


def _field_path(parent: str, field: str) -> str:
    return field if not parent else f"{parent}.{field}"


__all__ = [
    "CURATION_AUDIT_PROVENANCE_KEY",
    "PARAMETER_BRIDGE_PROVENANCE_KEY",
    "RESERVED_PROVENANCE_KEYS",
    "canonicalize",
    "first_symlink_component",
    "round_trip_differences",
    "sha256_bytes",
    "type_exact_equal",
]
