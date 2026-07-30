from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

GENERIC_SOURCE_PATHS = (
    "src/fungal_model/core",
    "src/fungal_model/processes",
    "src/fungal_model/solvers",
    "src/fungal_model/results",
    "src/fungal_model/modifiers",
    "src/fungal_model/io",
    "src/fungal_model/workflows",
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
