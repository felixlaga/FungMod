from __future__ import annotations

from pathlib import Path

import pytest

from fungal_model import VirtualExperiment
from fungal_model.registry import RegistryLookupError, ResolutionError


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"

FUNGUS_ID = "sabiork_beta_glucosidase_source"
SUBSTRATE_ID = "cellobiose"
ENVIRONMENT_ID = "sabiork_reaction_618_selected_conditions"


def test_virtual_experiment_still_works_with_exact_registry_ids() -> None:
    study = VirtualExperiment.from_registry(
        fungi=[FUNGUS_ID],
        substrates=[SUBSTRATE_ID],
        environments=[ENVIRONMENT_ID],
        registry=REGISTRY_INDEX,
    )

    assert study.fungus_ids == (FUNGUS_ID,)
    assert study.substrate_ids == (SUBSTRATE_ID,)
    assert study.environment_ids == (ENVIRONMENT_ID,)
    assert study.resolved_records == ()


def test_virtual_experiment_from_names_resolves_aliases() -> None:
    study = VirtualExperiment.from_names(
        fungi=["beta-glucosidase source"],
        substrates=["cellobiose substrate"],
        environments=["30C_pH5_assay"],
        registry=REGISTRY_INDEX,
    )

    assert study.fungus_ids == (FUNGUS_ID,)
    assert study.substrate_ids == (SUBSTRATE_ID,)
    assert study.environment_ids == (ENVIRONMENT_ID,)
    assert {record.record_type for record in study.resolved_records} == {
        "fungus",
        "substrate",
        "environment",
    }
    assert study.preflight(mode="exploratory")[0].status == "exploratory"


def test_virtual_experiment_from_registry_resolve_names_option() -> None:
    study = VirtualExperiment.from_registry(
        fungi="BETA-GLUCOSIDASE SOURCE",
        substrates="cellobiose substrate",
        environments="30C_pH5_assay",
        registry=REGISTRY_INDEX,
        resolve_names=True,
    )

    assert study.fungus_ids == (FUNGUS_ID,)
    assert study.substrate_ids == (SUBSTRATE_ID,)
    assert study.environment_ids == (ENVIRONMENT_ID,)
    assert any(record.confidence == "case_insensitive_exact" for record in study.resolved_records)


def test_virtual_experiment_aliases_are_opt_in() -> None:
    with pytest.raises(RegistryLookupError, match="Unknown fungus"):
        VirtualExperiment.from_registry(
            fungi="beta-glucosidase source",
            substrates=SUBSTRATE_ID,
            environments=ENVIRONMENT_ID,
            registry=REGISTRY_INDEX,
        )


def test_virtual_experiment_resolution_error_names_record_type() -> None:
    with pytest.raises(ResolutionError, match="Could not resolve substrate") as exc_info:
        VirtualExperiment.from_names(
            fungi="beta-glucosidase source",
            substrates="cellulose film that is not registered",
            environments="30C_pH5_assay",
            registry=REGISTRY_INDEX,
        )

    assert exc_info.value.record_type == "substrate"
    assert "cellobiose substrate" in exc_info.value.known_terms
