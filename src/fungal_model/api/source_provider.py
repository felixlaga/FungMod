"""Minimal researcher-facing source-provider onboarding."""

from __future__ import annotations

from pathlib import Path

from fungal_model.sources.sabiork import (
    LiveKinlawFetcher,
    RegistryProposal,
    SabioRKSource,
    SabioRKSourceError,
)
from fungal_model.sources.sabiork.fetch import (
    SabioRKFetchError,
    SabioRKTransport,
    fetch_and_save_export,
)


AVAILABLE_SOURCE_PROVIDERS = ("sabiork",)


class SourceProviderError(ValueError):
    """Raised when public source-provider onboarding cannot proceed safely."""


def source_proposal(
    *,
    provider: str,
    reaction_id: str | int | None = None,
    ec_number: str | None = None,
    enzyme: str | None = None,
    substrate: str | None = None,
    organism: str | None = None,
    source: str | None = None,
    entry_id: str | int | None = None,
    credential: str | None = None,
    refresh: bool = False,
    cache_dir: str | Path = "data/source_snapshots/sabiork",
    transport: SabioRKTransport | None = None,
) -> RegistryProposal:
    """Discover SABIO-RK records and return a review-only registry proposal.

    One friendly scientific selector is required. Frozen snapshots are used by
    default; live source access occurs only when ``refresh=True`` is explicit.
    """

    normalized_provider = provider.strip().lower()
    if normalized_provider not in AVAILABLE_SOURCE_PROVIDERS:
        available = ", ".join(AVAILABLE_SOURCE_PROVIDERS)
        raise SourceProviderError(
            f"Unknown source provider {provider!r}. Available providers: {available}."
        )
    if credential not in {None, ""}:
        raise SourceProviderError(
            "The sabiork provider does not require or accept a credential; omit credential."
        )
    if organism and source and organism != source:
        raise SourceProviderError("Provide only one organism/source value, or use matching values.")
    if not any(
        value not in {None, ""}
        for value in (reaction_id, ec_number, enzyme, substrate, organism, source, entry_id)
    ):
        raise SourceProviderError(
            "The sabiork provider requires at least one scientific selector: reaction_id, "
            "ec_number, enzyme, substrate, organism/source, or entry_id."
        )
    if transport is not None and not refresh:
        raise SourceProviderError("A transport is used only for an explicit refresh=True call.")

    fetcher = _sabiork_live_fetcher(transport=transport) if refresh else None
    adapter = SabioRKSource(cache_dir=cache_dir, live_fetcher=fetcher)
    try:
        discovery = adapter.discover_for_virtual_experiment(
            source=source or organism,
            substrate=substrate,
            enzyme=enzyme,
            ec_number=ec_number,
            reaction_id=reaction_id,
            entry_id=entry_id,
            refresh=refresh,
        )
        return discovery.to_registry_proposal()
    except (SabioRKFetchError, SabioRKSourceError, OSError, ValueError) as exc:
        raise SourceProviderError(f"SABIO-RK source proposal failed: {exc}") from exc


def _sabiork_live_fetcher(*, transport: SabioRKTransport | None) -> LiveKinlawFetcher:
    def fetch(query: str, output_dir: Path) -> tuple[Path, Path]:
        return fetch_and_save_export(
            query=query,
            output_dir=output_dir,
            expected_total_count=None,
            transport=transport,
        )

    return fetch


__all__ = [
    "AVAILABLE_SOURCE_PROVIDERS",
    "SourceProviderError",
    "source_proposal",
]
