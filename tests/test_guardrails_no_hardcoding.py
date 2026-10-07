from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]

GENERIC_SOURCE_PATHS = (
    "src/fungal_model/core",
    "src/fungal_model/processes",
    "src/fungal_model/solvers",
    "src/fungal_model/results",
    "src/fungal_model/modifiers",
    "src/fungal_model/io",
    "src/fungal_model/workflows",
    "src/fungal_model/api/user_data.py",
    "src/fungal_model/api/user_data_fit.py",
    "src/fungal_model/cli.py",
    "src/fungal_model/__main__.py",
)

ALLOWED_DOMAIN_SPECIFIC_PATHS = (
    "src/fungal_model/plugins/pet",
    "src/fungal_model/substrates/pet.py",
    "examples",
    "data",
    "tests/test_pet_*.py",
)

FORBIDDEN_PATTERNS = {
    "PETSubstrate": re.compile(r"\bPETSubstrate\b"),
    "PETSurfaceHydrolysisRateLaw": re.compile(r"\bPETSurfaceHydrolysisRateLaw\b"),
    "PETAccessibleSurfaceAreaModel": re.compile(r"\bPETAccessibleSurfaceAreaModel\b"),
    "pet_product_release_map": re.compile(r"\bpet_product_release_map\b"),
    "run_pet_surface_integration": re.compile(r"\brun_pet_surface_integration\b"),
    "hardcoded PET state": re.compile(r"""["']PET["']"""),
    "hardcoded hydrolysate state": re.compile(r"""["']hydrolysate["']"""),
    "PET token": re.compile(r"\bPET\b"),
    "hydrolysate token": re.compile(r"\bhydrolysate\b"),
    "petase token": re.compile(r"petase", re.IGNORECASE),
}


def test_no_new_pet_or_product_hardcoding_in_generic_source_paths() -> None:
    violations: list[str] = []
    for path in _python_files(GENERIC_SOURCE_PATHS):
        relative = path.relative_to(ROOT).as_posix()
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            for label, pattern in FORBIDDEN_PATTERNS.items():
                if not pattern.search(line):
                    continue
                violations.append(f"{relative}:{line_number}: {label}: {stripped}")

    assert not violations, (
        "PET/product hardcoding is not allowed in generic/core source paths. "
        "Move plugin-specific code to an allowed path, or document a narrow "
        "temporary allowance in ARCHITECTURE_DEBT.md.\n"
        + "\n".join(violations)
    )


def test_hardcoding_allowlist_is_documented_as_architecture_debt() -> None:
    debt = (ROOT / "ARCHITECTURE_DEBT.md").read_text(encoding="utf-8")
    assert "FD-001" in debt
    assert "resolved in Milestone 9" in debt
    assert "FD-002" in debt
    assert "tests/test_guardrails_no_hardcoding.py" in debt


def test_registry_case_builder_has_no_reaction_specific_onboarding_tokens() -> None:
    case_builder = (
        ROOT / "src" / "fungal_model" / "screening" / "case_builder.py"
    ).read_text(encoding="utf-8")

    for forbidden in (
        "reaction_618",
        "Reaction 618",
        "beta-glucosidase",
        "cellobiose",
        "SABIO-RK",
    ):
        assert forbidden not in case_builder


USER_DATA_FORBIDDEN_TOKENS = (
    "reaction_618",
    "reaction 618",
    "glucosidase",
    "cellobiose",
    "glucose",
    "cellulose",
    "cellulase",
    "esterase",
    "nitrophenyl",
    "trichoderma",
    "harzianum",
    "oryza",
    "laccase",
    "syringaldazine",
    # USERDATA-003 genome-route fixture: the classes and substrates come from the family map and tables.
    "maltose",
    "glucoamylase",
    "xylanase",
    "cellobiohydrolase",
    "synthetic_g",
    # USERDATA-007 UniProt-route fixture: accessions and the proteome id come from the export and genomes.csv.
    "x0test",
    "up000000000",
    # USERDATA-005: organisms and hosts of the Reaction 618 snapshot come from the source entries.
    "phanerochaete",
    "hordeum",
    "escherichia",
    "bacteroides",
    # USERDATA-008 solid-substrate tests: the classes, substrates and re-entered constants come from the tables.
    "xylan",
    "celufloc",
)


# user_data.py and the command line name no source database either.
ORGANISM_SUBSTRATE_ENZYME_TOKENS = (*USER_DATA_FORBIDDEN_TOKENS, "sabio")


def test_user_data_sources_has_no_organism_substrate_or_enzyme_specific_tokens() -> None:
    """The SABIO-RK drafting module names its source, never an organism, substrate or enzyme."""

    module = (ROOT / "src" / "fungal_model" / "api" / "user_data_sources.py").read_text(encoding="utf-8").lower()
    for forbidden in USER_DATA_FORBIDDEN_TOKENS:
        assert forbidden not in module, forbidden


def test_user_data_assembly_has_no_organism_substrate_or_enzyme_specific_tokens() -> None:
    """The assembly module names its sources and rules, never an organism, substrate or enzyme."""

    module = (ROOT / "src" / "fungal_model" / "api" / "user_data_assembly.py").read_text(encoding="utf-8").lower()
    for forbidden in USER_DATA_FORBIDDEN_TOKENS:
        assert forbidden not in module, forbidden


@pytest.mark.parametrize("module", ("user_data.py", "user_data_fit.py"))
def test_user_data_import_has_no_organism_substrate_or_enzyme_specific_tokens(module: str) -> None:
    user_data = (ROOT / "src" / "fungal_model" / "api" / module).read_text(encoding="utf-8").lower()

    for forbidden in ORGANISM_SUBSTRATE_ENZYME_TOKENS:
        assert forbidden not in user_data, forbidden


def test_command_line_has_no_organism_substrate_or_enzyme_specific_tokens() -> None:
    for relative in ("src/fungal_model/cli.py", "src/fungal_model/__main__.py"):
        source = (ROOT / relative).read_text(encoding="utf-8").lower()
        for forbidden in ORGANISM_SUBSTRATE_ENZYME_TOKENS:
            assert forbidden not in source, f"{relative}: {forbidden}"


def test_uniprot_route_modules_have_no_organism_substrate_or_enzyme_specific_tokens() -> None:
    """The UniProt parser, resolver and fetch client name UniProt's format, never an organism, class or EC number."""

    for relative in ("src/fungal_model/capability/uniprot.py", "src/fungal_model/sources/uniprot.py"):
        module = (ROOT / relative).read_text(encoding="utf-8").lower()
        for forbidden in (
            "glucosidase",
            "cellobiose",
            "cellulose",
            "cellulase",
            "cellobiohydrolase",
            "glucoamylase",
            "maltose",
            "xylanase",
            "laccase",
            "esterase",
            "trichoderma",
            "aspergillus",
            "3.2.1.21",
            "3.2.1.3",
            "x0test",
            "up000000000",
        ):
            assert forbidden not in module, (relative, forbidden)


def _python_files(paths: tuple[str, ...]) -> tuple[Path, ...]:
    files: list[Path] = []
    for relative in paths:
        path = ROOT / relative
        if not path.exists():
            continue
        if path.is_file() and path.suffix == ".py":
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(item for item in path.rglob("*.py") if "__pycache__" not in item.parts))
    return tuple(files)
