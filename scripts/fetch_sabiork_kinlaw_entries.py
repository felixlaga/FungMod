#!/usr/bin/env python3
"""Fetch and freeze a SABIO-RK kinetic-law JSON export."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = "https://sabio.h-its.org/export-api/sabio"
ENDPOINT = "/kinlaw-entry/json"
DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 1000
EXPECTED_REACTION_618_TOTAL_COUNT = 29
MIN_REQUEST_INTERVAL_SECONDS = 1.0


class SabioRKFetchError(RuntimeError):
    """Raised when a SABIO-RK export cannot be fetched or validated."""


@dataclass(frozen=True)
class HTTPResponseSnapshot:
    """Raw HTTP response details needed for a frozen source snapshot."""

    body: str
    http_status: int
    url: str


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
        if not reaction_ids:
            continue
        if reaction_id not in reaction_ids:
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
) -> dict[str, Any]:
    """Build JSON-safe fetch metadata for the source snapshot."""

    warnings: list[str] = []
    if expected_total_count is not None and total_count != expected_total_count:
        warnings.append(
            "SABIO-RK total_count differs from the browser count supplied for this milestone: "
            f"expected {expected_total_count}, got {total_count}."
        )
    return {
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
) -> tuple[Path, Path]:
    """Fetch a SABIO-RK export and save the raw export plus fetch metadata."""

    output_dir.mkdir(parents=True, exist_ok=True)
    export_path = output_dir / _raw_export_filename(query)
    metadata_path = output_dir / "fetch_metadata.json"
    reaction_id = _reaction_id_from_query(query)

    first_url = build_kinlaw_url(
        base_url=base_url,
        endpoint=endpoint,
        query=query,
        page=page,
        page_size=page_size,
    )
    first_response = _fetch_text(first_url, timeout_seconds=timeout_seconds)
    export_path.write_text(_with_trailing_newline(first_response.body), encoding="utf-8")

    first_payload = _parse_json_body(first_response.body, export_path=export_path)
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
        )
        raise

    responses = [first_response]
    payload = first_payload
    if total_pages > 1:
        payload = _combined_paginated_payload(first_payload)
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
            next_response = _fetch_text(next_url, timeout_seconds=timeout_seconds)
            last_request_at = time.monotonic()
            next_payload = _parse_json_body(next_response.body, export_path=export_path)
            validate_kinlaw_export(next_payload, reaction_id=reaction_id)
            responses.append(next_response)
            payload["data"].extend(next_payload["data"])
        payload["meta"]["combined_from_pages"] = True
        payload["meta"]["pages_fetched"] = [page_response.url for page_response in responses]
        _write_json(export_path, payload)

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
    )
    _write_json(metadata_path, metadata)
    return export_path, metadata_path


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch a SABIO-RK kinlaw-entry JSON export and freeze it locally."
    )
    parser.add_argument("--query", required=True, help="SABIO-RK Solr query string, e.g. SabioReactionID:618.")
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory where raw JSON files are saved.")
    parser.add_argument("--base-url", default=BASE_URL)
    parser.add_argument("--endpoint", default=ENDPOINT)
    parser.add_argument("--page", default=DEFAULT_PAGE, type=int)
    parser.add_argument("--pageSize", default=DEFAULT_PAGE_SIZE, type=int)
    parser.add_argument("--timeout-seconds", default=30.0, type=float)
    parser.add_argument(
        "--expected-total-count",
        default=EXPECTED_REACTION_618_TOTAL_COUNT,
        type=int,
        help="Expected total_count for warning-only drift detection. Use -1 to disable.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    expected_total_count = None if args.expected_total_count < 0 else args.expected_total_count
    try:
        export_path, metadata_path = fetch_and_save_export(
            query=args.query,
            output_dir=args.output_dir,
            base_url=args.base_url,
            endpoint=args.endpoint,
            page=args.page,
            page_size=args.pageSize,
            expected_total_count=expected_total_count,
            timeout_seconds=args.timeout_seconds,
        )
    except (SabioRKFetchError, HTTPError, URLError, OSError) as exc:
        print(f"SABIO-RK fetch failed: {exc}", file=sys.stderr)
        return 1
    print(f"Saved raw export: {export_path}")
    print(f"Saved fetch metadata: {metadata_path}")
    return 0


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
    meta = dict(first_payload["meta"])
    data = list(first_payload["data"])
    return {"meta": meta, "data": data}


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
    if match is None:
        return None
    return match.group(1)


def _raw_export_filename(query: str) -> str:
    reaction_id = _reaction_id_from_query(query)
    if reaction_id is not None:
        return f"kinlaw_entries_reaction_{reaction_id}.json"
    safe_query = re.sub(r"[^A-Za-z0-9_.-]+", "_", query).strip("_") or "query"
    return f"kinlaw_entries_{safe_query}.json"


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


def _with_trailing_newline(text: str) -> str:
    if text.endswith("\n"):
        return text
    return text + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
