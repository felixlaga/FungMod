"""Genome-derived capability resolution: presence only, never rates.

These tests pin the two distinctions the module exists to preserve. Having a
capability is not the same as FungMod being able to model it, and a
family-polyspecific assignment is not the same as a diagnostic one. They also
pin the refusal path, because a breadth layer that guesses is worse than one
that declines.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fungal_model.capability import (
    DIAGNOSTIC,
    POLYSPECIFIC,
    CapabilityResolutionError,
    CapabilityResolver,
    CazymeAnnotation,
    CazymeFamilyMap,
    annotation_from_overview,
    families_from_overview,
)
from fungal_model.core.provenance import ProvenanceError

WHITE_ROT_FAMILIES = (
    "GH1", "GH3", "GH5", "GH6", "GH7", "GH10", "GH11", "GH12",
    "AA1", "AA2", "AA3", "AA9", "CE1", "GH18", "GT2", "CBM1",
)


def _annotation(**overrides: object) -> CazymeAnnotation:
    fields: dict = {
        "organism": "Phanerochaete chrysosporium",
        "families": WHITE_ROT_FAMILIES,
        "genome_accession": "GCF_000143535.1",
        "annotation_tool": "dbCAN3",
        "annotation_tool_version": "4.1.4",
        "annotation_date": "2026-08-18",
    }
    fields.update(overrides)
    return CazymeAnnotation(**fields)  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# Family map
# --------------------------------------------------------------------------


def test_family_map_loads_with_provenance_and_known_specificities() -> None:
    family_map = CazymeFamilyMap.load()

    assert family_map.sources, "The family map must carry literature sources."
    assert len(family_map.mappings) >= 15
    for mapping in family_map.mappings:
        assert mapping.specificity in {DIAGNOSTIC, POLYSPECIFIC}


def test_large_polyspecific_families_are_not_marked_diagnostic() -> None:
    """GH5 and GH13 carry many activities; membership alone is weak evidence."""

    family_map = CazymeFamilyMap.load()
    for family in ("GH5", "GH13", "GH1", "GH3"):
        for mapping in family_map.for_family(family):
            assert mapping.specificity == POLYSPECIFIC, family


def test_cellulose_workhorse_families_are_diagnostic() -> None:
    family_map = CazymeFamilyMap.load()
    for family in ("GH6", "GH7", "AA9"):
        mappings = family_map.for_family(family)
        assert mappings, family
        assert all(m.specificity == DIAGNOSTIC for m in mappings), family


# --------------------------------------------------------------------------
# Annotation provenance
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "blank_field",
    ["organism", "genome_accession", "annotation_tool", "annotation_tool_version", "annotation_date"],
)
def test_annotation_refuses_missing_provenance(blank_field: str) -> None:
    with pytest.raises(ProvenanceError):
        _annotation(**{blank_field: "  "})


def test_annotation_refuses_an_empty_family_list() -> None:
    with pytest.raises(CapabilityResolutionError):
        _annotation(families=())


def test_annotation_normalizes_and_deduplicates_families() -> None:
    annotation = _annotation(families=("gh7", "GH7", " AA9 ", "aa9"))

    assert annotation.families == ("AA9", "GH7")


# --------------------------------------------------------------------------
# Resolution
# --------------------------------------------------------------------------


def test_resolution_separates_modellable_from_merely_present_capability() -> None:
    """A capability FungMod cannot model must be reported, not dropped."""

    resolution = CapabilityResolver.from_registry().resolve(_annotation())

    assert "beta_glucosidase" in resolution.modellable_enzyme_classes
    # The cellulose workhorse is encoded but has no registry enzyme class yet.
    assert "cellobiohydrolase" in resolution.capabilities_without_model
    assert "lytic_polysaccharide_monooxygenase" in resolution.capabilities_without_model
    assert set(resolution.modellable_enzyme_classes).isdisjoint(resolution.capabilities_without_model)


def test_non_catalytic_and_biosynthetic_families_are_left_unmapped() -> None:
    """CBM1 is a binding module and GT2 is biosynthetic; neither is degradative."""

    resolution = CapabilityResolver.from_registry().resolve(_annotation())

    assert "CBM1" in resolution.unmapped_families
    assert "GT2" in resolution.unmapped_families


def test_requiring_diagnostic_evidence_discards_polyspecific_assignments() -> None:
    resolver = CapabilityResolver.from_registry()

    permissive = resolver.resolve(_annotation())
    strict = resolver.resolve(_annotation(), require_diagnostic=True)

    # beta-glucosidase rests only on polyspecific GH1/GH3 here.
    assert "beta_glucosidase" in permissive.modellable_enzyme_classes
    assert "beta_glucosidase" not in strict.modellable_enzyme_classes
    # The diagnostic cellulose families survive the stricter filter.
    assert "cellobiohydrolase" in {c.enzyme_class for c in strict.capabilities}


def test_resolution_refuses_explicitly_when_nothing_is_modellable() -> None:
    """The refusal must name what was found and what is missing."""

    annotation = _annotation(organism="Serpula lacrymans", families=("AA9", "GH10", "AA2"))
    resolution = CapabilityResolver.from_registry().resolve(annotation)

    assert resolution.modellable_enzyme_classes == ()
    with pytest.raises(CapabilityResolutionError) as excinfo:
        resolution.require_modellable()
    message = str(excinfo.value)
    assert "Serpula lacrymans" in message
    assert "lytic_polysaccharide_monooxygenase" in message
    assert "Add a registry enzyme-class record" in message


def test_resolution_never_reports_a_rate_or_kinetic_constant() -> None:
    """The breadth layer states what an organism encodes, never how fast."""

    data = CapabilityResolver.from_registry().resolve(_annotation()).to_dict()
    boundary = data.pop("claim_boundary")
    # Scan the payload, not the prose that disclaims rates.
    payload = repr(data).lower()

    for forbidden in ("k_cat", "kcat", "v_max", "vmax", "k_m", "rate", "turnover", "activity"):
        assert forbidden not in payload, forbidden
    assert "not what it expresses, secretes, or how fast" in boundary


# --------------------------------------------------------------------------
# dbCAN parsing
# --------------------------------------------------------------------------


OVERVIEW = (
    "Gene ID\tEC#\tHMMER\tdbCAN_sub\tDIAMOND\t#ofTools\n"
    "gene_1\t3.2.1.4\tGH5_5(123-456)\tGH5_e123\tGH5\t3\n"
    "gene_2\t3.2.1.91\tGH7(1-430)\tGH7_e1\tGH7\t3\n"
    "gene_3\t-\tAA9(30-250)\t-\tAA9\t2\n"
    "gene_4\t-\t-\t-\tCBM1\t1\n"
    "gene_5\t-\tGH10(5-300)+CE1(320-400)\t-\tGH10\t2\n"
)


def test_dbcan_parser_strips_subfamilies_and_residue_ranges(tmp_path: Path) -> None:
    path = tmp_path / "overview.txt"
    path.write_text(OVERVIEW, encoding="utf-8")

    families = families_from_overview(path)

    assert families == ("AA9", "CBM1", "CE1", "GH10", "GH5", "GH7")


def test_dbcan_annotation_carries_caller_supplied_provenance(tmp_path: Path) -> None:
    """The overview file records no genome or version, so the caller must."""

    path = tmp_path / "overview.txt"
    path.write_text(OVERVIEW, encoding="utf-8")

    annotation = annotation_from_overview(
        path,
        organism="Trichoderma reesei",
        genome_accession="GCF_000167675.1",
        annotation_tool="dbCAN3",
        annotation_tool_version="4.1.4",
        annotation_date="2026-08-18",
    )

    assert annotation.organism == "Trichoderma reesei"
    assert "GH7" in annotation.families
    resolution = CapabilityResolver.from_registry().resolve(annotation)
    assert "cellulase_generic" in resolution.modellable_enzyme_classes


def test_dbcan_parser_rejects_files_without_tool_columns(tmp_path: Path) -> None:
    path = tmp_path / "bad.txt"
    path.write_text("Gene ID\tEC#\nfoo\t1.1.1.1\n", encoding="utf-8")

    with pytest.raises(CapabilityResolutionError, match="tool columns"):
        families_from_overview(path)


def test_dbcan_parser_rejects_files_with_no_family_calls(tmp_path: Path) -> None:
    path = tmp_path / "empty.txt"
    path.write_text("Gene ID\tEC#\tHMMER\tdbCAN_sub\tDIAMOND\t#ofTools\ng\t-\t-\t-\t-\t0\n", encoding="utf-8")

    with pytest.raises(CapabilityResolutionError, match="no CAZy family calls"):
        families_from_overview(path)
