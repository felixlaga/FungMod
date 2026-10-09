"""Keep historical annotation imports stable while richer mechanisms are opt-in.

A registry enzyme class is not proof that every input route can supply that
class's required physical states. The ordinary table route has no finite-chain
or peroxide-state schema; those mechanisms use explicit mechanism tables.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from fungal_model.capability.resolution import default_family_map_path
from fungal_model.registry.records import EnzymeClassRecord
from fungal_model.registry.store import FungModRegistry

EXPLICIT_MECHANISM_PROCESSES = frozenset({"chain_endo_scission", "chain_exo_scission", "peroxide_oxidative_cleavage"})


def requires_explicit_mechanism_tables(record: EnzymeClassRecord) -> bool:
    return bool(record.compatible_processes) and set(record.compatible_processes) <= EXPLICIT_MECHANISM_PROCESSES


def legacy_annotation_registry(registry: FungModRegistry) -> FungModRegistry:
    """Return a scoped view for unchanged legacy genome/UniProt imports."""
    return replace(
        registry,
        enzyme_classes={
            key: record
            for key, record in registry.enzyme_classes.items()
            if not requires_explicit_mechanism_tables(record)
        },
    )


def mechanism_family_map_path() -> Path:
    """Explicitly opt in to enriched endo/LPMO family annotations."""
    return default_family_map_path().with_name("cazyme_mechanisms_map.yml")
