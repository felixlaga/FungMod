from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

HIGH_RISK_PATHS = (
    "src/fungal_model/processes",
    "src/fungal_model/workflows",
    "src/fungal_model/io",
    "src/fungal_model/solvers",
)

SUSPICIOUS_PATTERNS = {
    'fallback k lookup via .get("k_': re.compile(r"""\.get\(["']k_"""),
    "fallback quantity via or Q_(": re.compile(r"\bor\s+Q_\("),
    "fallback numeric via or 1.0": re.compile(r"\bor\s+1\.0\b"),
    "fallback numeric via or 0.0": re.compile(r"\bor\s+0\.0\b"),
    "quick fix wording": re.compile(r"\bquick fix\b", re.IGNORECASE),
    "hack wording": re.compile(r"\bhack\b", re.IGNORECASE),
    "temporary wording": re.compile(r"\btemporary\b", re.IGNORECASE),
    "for now wording": re.compile(r"\bfor now\b", re.IGNORECASE),
    "placeholder wording": re.compile(r"\bplaceholder\b", re.IGNORECASE),
    "public NotImplementedError": re.compile(r"\bNotImplementedError\b"),
}

ABSTRACT_INTERFACE_LINES = {
    "src/fungal_model/processes/base.py": {
        'raise NotImplementedError(f"Process {self.name!r} has no rate implementation.")',
        'raise NotImplementedError(f"Process {self.name!r} has no contribution implementation.")',
    },
}

TRANSITIONAL_DEBT_LINES = {
    "src/fungal_model/processes/assembly.py": {
        '"""Placeholder until solver-backed process execution is implemented."""',
        "raise NotImplementedError(",
    },
}


def test_no_undocumented_shortcut_patterns_in_high_risk_modules() -> None:
    violations: list[str] = []
    for path in _python_files(HIGH_RISK_PATHS):
        relative = path.relative_to(ROOT).as_posix()
        allowed_lines = ABSTRACT_INTERFACE_LINES.get(relative, set()) | TRANSITIONAL_DEBT_LINES.get(relative, set())
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            for label, pattern in SUSPICIOUS_PATTERNS.items():
                if not pattern.search(line):
                    continue
                if stripped in allowed_lines:
                    continue
                violations.append(f"{relative}:{line_number}: {label}: {stripped}")

    assert not violations, (
        "High-risk modules contain undocumented shortcut patterns. Remove the "
        "shortcut, make it an abstract interface, or document a precise "
        "temporary allowance in ARCHITECTURE_DEBT.md.\n"
        + "\n".join(violations)
    )


def test_shortcut_allowlist_is_documented_as_architecture_debt() -> None:
    debt = (ROOT / "ARCHITECTURE_DEBT.md").read_text(encoding="utf-8")
    assert "FD-003" in debt
    assert "AssembledModel.run" in debt
    assert "tests/test_guardrails_no_shortcuts.py" in debt


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
