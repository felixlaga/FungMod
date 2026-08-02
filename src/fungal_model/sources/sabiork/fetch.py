"""Explicit live fetch and freeze support for SABIO-RK source snapshots."""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = "https://sabio.h-its.org/export-api/sabio"
ENDPOINT = "/kinlaw-entry/json"
DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 1000
EXPECTED_REACTION_618_TOTAL_COUNT = 29
MIN_REQUEST_INTERVAL_SECONDS = 1.0
ARTIFACT_LAYOUT_VERSION = "1.0"
COMBINED_EXPORT_FILENAME = "combined_export.json"


class SabioRKFetchError(RuntimeError):
    """Raised when a SABIO-RK export cannot be fetched or validated."""


@dataclass(frozen=True)
class HTTPResponseSnapshot:
    """Raw HTTP response details needed for a frozen source snapshot."""

    body: str
    http_status: int
    url: str


class SabioRKTransport(Protocol):
    """Injected transport contract used by offline tests and explicit refresh."""

    def __call__(self, url: str, *, timeout_seconds: float) -> HTTPResponseSnapshot: ...


def build_kinlaw_url(
    *,
    base_url: str,
    endpoint: str,
    query: str,
    page: int,
    page_size: int,
) -> str:
    """Build the SABIO-RK kinetic-law export URL."""

    root = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
    parameters = urlencode({"q": query, "page": page, "pageSize": page_size})
    return f"{root}?{parameters}"


def validate_kinlaw_export(payload: Any, *, reaction_id: str | None = None) -> None:
    """Validate the minimal SABIO-RK export envelope without changing values."""

    if not isinstance(payload, Mapping):
        raise SabioRKFetchError("SABIO-RK response must be a JSON object.")
    meta = payload.get("meta")
    data = payload.get("data")
    if not isinstance(meta, Mapping):
        raise SabioRKFetchError("SABIO-RK response is missing a JSON-object 'meta' field.")
    if "total_count" not in meta:
        raise SabioRKFetchError("SABIO-RK response meta is missing 'total_count'.")
    if not isinstance(data, list):
        raise SabioRKFetchError("SABIO-RK response is missing a JSON-array 'data' field.")
    if reaction_id is None:
        return

    for index, entry in enumerate(data):
        if not isinstance(entry, Mapping):
            continue
        reaction_ids = _entry_reaction_ids(entry)
        if reaction_ids and reaction_id not in reaction_ids:
            raise SabioRKFetchError(
                "SABIO-RK entry at data index "
                f"{index} has SabioReactionID {sorted(reaction_ids)!r}, expected {reaction_id!r}."
            )


def build_fetch_metadata(
    *,
    base_url: str,
    endpoint: str,
    query: str,
    page: int,
    page_size: int,
    fetched_at: str,
    http_status: int,
    total_count: int,
    expected_total_count: int | None,
    total_pages: int | None,
    requests_made: int,
    urls: Sequence[str],
    snapshot_id: str | None = None,
    query_key: str | None = None,
    raw_pages: Sequence[Mapping[str, Any]] = (),
    derived_export: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build JSON-safe fetch metadata for the source snapshot."""

    warnings: list[str] = []
    if expected_total_count is not None and total_count != expected_total_count:
        warnings.append(
            "SABIO-RK total_count differs from the browser count supplied for this milestone: "
            f"expected {expected_total_count}, got {total_count}."
        )
    metadata: dict[str, Any] = {
        "base_url": base_url.rstrip("/"),
        "endpoint": endpoint,
        "query": query,
        "page": page,
        "pageSize": page_size,
        "fetched_at": fetched_at,
        "http_status": http_status,
        "total_count": total_count,
        "total_pages": total_pages,
        "requests_made": requests_made,
        "source_urls": list(urls),
        "warnings": warnings,
    }
    if snapshot_id is not None and query_key is not None and derived_export is not None:
        metadata.update(
            {
                "artifact_layout_version": ARTIFACT_LAYOUT_VERSION,
                "snapshot_id": snapshot_id,
                "query_key": query_key,
                "immutable_snapshot_bundle": True,
                "raw_pages": [dict(item) for item in raw_pages],
                "derived_export": dict(derived_export),
            }
        )
    return metadata


def fetch_and_save_export(
    *,
    query: str,
    output_dir: Path,
    base_url: str = BASE_URL,
    endpoint: str = ENDPOINT,
    page: int = DEFAULT_PAGE,
    page_size: int = DEFAULT_PAGE_SIZE,
    expected_total_count: int | None = EXPECTED_REACTION_618_TOTAL_COUNT,
    timeout_seconds: float = 30.0,
    transport: SabioRKTransport | None = None,
) -> tuple[Path, Path]:
    """Fetch a SABIO-RK export and freeze the raw response plus fetch metadata."""

    query_key = query_bundle_key(query)
    snapshot_id = _snapshot_id()
    bundle_dir = output_dir / query_key / snapshot_id
    raw_dir = bundle_dir / "raw"
    derived_dir = bundle_dir / "derived"
    raw_dir.mkdir(parents=True, exist_ok=False)
    derived_dir.mkdir()
    export_path = derived_dir / COMBINED_EXPORT_FILENAME
    metadata_path = bundle_dir / "fetch_metadata.json"
    reaction_id = _reaction_id_from_query(query)
    fetch_text = transport or _fetch_text

    first_url = build_kinlaw_url(
        base_url=base_url,
        endpoint=endpoint,
        query=query,
        page=page,
        page_size=page_size,
    )
    first_response = fetch_text(first_url, timeout_seconds=timeout_seconds)
    first_raw_path, first_raw_page = _write_raw_page(
        response=first_response,
        raw_dir=raw_dir,
        page=page,
    )

    first_payload = _parse_json_body(first_response.body, export_path=first_raw_path)
    try:
        validate_kinlaw_export(first_payload, reaction_id=reaction_id)
        total_count = _required_meta_int(first_payload, "total_count")
        total_pages = _optional_meta_int(first_payload, "total_pages")
        if total_pages is None:
            total_pages = 1
    except SabioRKFetchError as exc:
        _write_error_metadata(
            metadata_path=metadata_path,
            base_url=base_url,
            endpoint=endpoint,
            query=query,
            page=page,
            page_size=page_size,
            fetched_at=_utc_now(),
            http_status=first_response.http_status,
            url=first_response.url,
            error=str(exc),
            snapshot_id=snapshot_id,
            query_key=query_key,
            raw_pages=(first_raw_page,),
        )
        raise

    responses = [first_response]
    raw_pages: list[Mapping[str, Any]] = [first_raw_page]
    payload = _combined_paginated_payload(first_payload)
    if total_pages > 1:
        last_request_at = time.monotonic()
        for next_page in range(page + 1, total_pages + 1):
            elapsed = time.monotonic() - last_request_at
            if elapsed < MIN_REQUEST_INTERVAL_SECONDS:
                time.sleep(MIN_REQUEST_INTERVAL_SECONDS - elapsed)
            next_url = build_kinlaw_url(
                base_url=base_url,
                endpoint=endpoint,
                query=query,
                page=next_page,
                page_size=page_size,
            )
            next_response = fetch_text(next_url, timeout_seconds=timeout_seconds)
            last_request_at = time.monotonic()
            next_raw_path, next_raw_page = _write_raw_page(
                response=next_response,
                raw_dir=raw_dir,
                page=next_page,
            )
            next_payload = _parse_json_body(next_response.body, export_path=next_raw_path)
            validate_kinlaw_export(next_payload, reaction_id=reaction_id)
            responses.append(next_response)
            raw_pages.append(next_raw_page)
            payload["data"].extend(next_payload["data"])
    payload["meta"]["combined_from_pages"] = total_pages > 1
    payload["meta"]["source_page_count"] = len(raw_pages)
    payload["meta"]["raw_pages_preserved"] = True
    payload["meta"]["pages_fetched"] = [response.url for response in responses]
    _write_json(export_path, payload)
    derived_export = {
        "artifact_role": "derived_combined_export",
        "path": export_path.relative_to(bundle_dir).as_posix(),
        "sha256": _sha256_bytes(export_path.read_bytes()),
        "source_page_count": len(raw_pages),
    }

    metadata = build_fetch_metadata(
        base_url=base_url,
        endpoint=endpoint,
        query=query,
        page=page,
        page_size=page_size,
        fetched_at=_utc_now(),
        http_status=first_response.http_status,
        total_count=total_count,
        expected_total_count=expected_total_count,
        total_pages=total_pages,
        requests_made=len(responses),
        urls=tuple(response.url for response in responses),
        snapshot_id=snapshot_id,
        query_key=query_key,
        raw_pages=raw_pages,
        derived_export=derived_export,
    )
    _write_json(metadata_path, metadata)
    return export_path, metadata_path


def _fetch_text(url: str, *, timeout_seconds: float) -> HTTPResponseSnapshot:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "FungMod REAL-001 source snapshot fetcher",
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        status = int(response.getcode())
        body = response.read().decode("utf-8")
    return HTTPResponseSnapshot(body=body, http_status=status, url=url)


def _parse_json_body(body: str, *, export_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise SabioRKFetchError(
            f"SABIO-RK response was not valid JSON. Raw response was saved to {export_path}."
        ) from exc
    if not isinstance(payload, dict):
        raise SabioRKFetchError(
            f"SABIO-RK response JSON was not an object. Raw response was saved to {export_path}."
        )
    return payload


def _combined_paginated_payload(first_payload: dict[str, Any]) -> dict[str, Any]:
    return {"meta": dict(first_payload["meta"]), "data": list(first_payload["data"])}


def _write_error_metadata(
    *,
    metadata_path: Path,
    base_url: str,
    endpoint: str,
    query: str,
    page: int,
    page_size: int,
    fetched_at: str,
    http_status: int,
    url: str,
    error: str,
    snapshot_id: str,
    query_key: str,
    raw_pages: Sequence[Mapping[str, Any]],
) -> None:
    _write_json(
        metadata_path,
        {
            "base_url": base_url.rstrip("/"),
            "endpoint": endpoint,
            "query": query,
            "page": page,
            "pageSize": page_size,
            "fetched_at": fetched_at,
            "http_status": http_status,
            "source_urls": [url],
            "error": error,
            "artifact_layout_version": ARTIFACT_LAYOUT_VERSION,
            "snapshot_id": snapshot_id,
            "query_key": query_key,
            "immutable_snapshot_bundle": True,
            "raw_pages": [dict(item) for item in raw_pages],
        },
    )


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _required_meta_int(payload: Mapping[str, Any], key: str) -> int:
    meta = payload["meta"]
    if not isinstance(meta, Mapping) or key not in meta:
        raise SabioRKFetchError(f"SABIO-RK response meta is missing {key!r}.")
    return _coerce_int(meta[key], field=f"meta.{key}")


def _optional_meta_int(payload: Mapping[str, Any], key: str) -> int | None:
    meta = payload["meta"]
    if not isinstance(meta, Mapping) or key not in meta or meta[key] is None:
        return None
    return _coerce_int(meta[key], field=f"meta.{key}")


def _coerce_int(value: Any, *, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise SabioRKFetchError(f"SABIO-RK response {field} must be an integer.") from exc


def _reaction_id_from_query(query: str) -> str | None:
    match = re.fullmatch(r"\s*SabioReactionID\s*:\s*(\d+)\s*", query)
    return None if match is None else match.group(1)


def query_bundle_key(query: str) -> str:
    """Return a filesystem-safe query identity with a collision-resistant digest."""

    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", query).strip("_").lower() or "query"
    digest = hashlib.sha256(query.encode("utf-8")).hexdigest()[:12]
    return f"{slug[:80]}-{digest}"


def _snapshot_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{timestamp}-{uuid.uuid4().hex}"


def _write_raw_page(
    *,
    response: HTTPResponseSnapshot,
    raw_dir: Path,
    page: int,
) -> tuple[Path, Mapping[str, Any]]:
    path = raw_dir / f"page_{page:04d}.json"
    body = response.body.encode("utf-8")
    path.write_bytes(body)
    return path, {
        "artifact_role": "raw_http_response",
        "page": page,
        "path": path.relative_to(raw_dir.parent).as_posix(),
        "sha256": _sha256_bytes(body),
        "size_bytes": len(body),
        "http_status": response.http_status,
        "source_url": response.url,
    }


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _text_values(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {value}
    if isinstance(value, int):
        return {str(value)}
    if isinstance(value, float):
        return {str(int(value)) if value.is_integer() else str(value)}
    if isinstance(value, Mapping):
        values: set[str] = set()
        for nested in value.values():
            values.update(_text_values(nested))
        return values
    if isinstance(value, Sequence) and not isinstance(value, bytes):
        values = set()
        for item in value:
            values.update(_text_values(item))
        return values
    return {str(value)}


def _entry_reaction_ids(entry: Mapping[str, Any]) -> set[str]:
    reaction_ids: set[str] = set()
    if "SabioReactionID" in entry:
        reaction_ids.update(_text_values(entry["SabioReactionID"]))
    reaction = entry.get("reaction")
    if isinstance(reaction, Mapping):
        if "SabioReactionID" in reaction:
            reaction_ids.update(_text_values(reaction["SabioReactionID"]))
        if "id" in reaction:
            reaction_ids.update(_text_values(reaction["id"]))
    return reaction_ids


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


__all__ = [
    "ARTIFACT_LAYOUT_VERSION",
    "BASE_URL",
    "COMBINED_EXPORT_FILENAME",
    "DEFAULT_PAGE",
    "DEFAULT_PAGE_SIZE",
    "ENDPOINT",
    "EXPECTED_REACTION_618_TOTAL_COUNT",
    "HTTPResponseSnapshot",
    "SabioRKFetchError",
    "SabioRKTransport",
    "build_fetch_metadata",
    "build_kinlaw_url",
    "fetch_and_save_export",
    "query_bundle_key",
    "validate_kinlaw_export",
]
