from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

ACTIVE_INSTRUCTION_PATHS = (
    ROOT / "AGENTS.md",
    ROOT / "README.md",
    ROOT / "foundation_progress" / "README.md",
    ROOT / "foundation_progress" / "FUNGMOD_CENTRAL_GOAL_VIRTUAL_EXPERIMENTS.md",
    ROOT / "foundation_progress" / "FUNGMOD_NEXT_PHASES_ROADMAP.md",
    ROOT / "ARCHITECTURE_DEBT.md",
)

ACTIVE_SOURCE_OF_TRUTH_PATHS = (
    "AGENTS.md",
    "README.md",
    "foundation_progress/FUNGMOD_CENTRAL_GOAL_VIRTUAL_EXPERIMENTS.md",
    "foundation_progress/FUNGMOD_NEXT_PHASES_ROADMAP.md",
    "progress.md",
    "ARCHITECTURE_DEBT.md",
)

UNCONDITIONAL_BIOLOGY_BAN_PATTERNS = (
    r"\bdo not add biology\b",
    r"\bdo not add real biology\b",
    r"\bno biology before foundation\b",
    r"\bCodex must not add real biology\b",
    r"\bnot permission to add biology\b",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_root_agents_defines_active_instruction_hierarchy() -> None:
    agents_path = ROOT / "AGENTS.md"
    assert agents_path.exists()

    agents = _read(agents_path)
    for active_path in ACTIVE_SOURCE_OF_TRUTH_PATHS:
        assert active_path in agents

    assert "old_progress/" in agents
    assert "historical and non-binding" in agents
    assert "Active Source Of Truth" in agents
    assert re.search(r"verify\s+the\s+behavior\s+from\s+code\s+and\s+tests", agents)


def test_active_docs_keep_unsupported_biology_rule() -> None:
    combined = "\n".join(_read(path) for path in ACTIVE_INSTRUCTION_PATHS)

    assert re.search(
        r"Unsupported,\s+invented,\s+silently\s+guessed,\s+or\s+falsely\s+validated\s+biology\s+is\s+forbidden",
        combined,
    )
    assert "FungMod is not a tool that invents biological facts" in combined
    assert "FungMod must not turn unsupported biology into fake simulations" in combined


def test_active_instruction_files_do_not_contain_blanket_biology_bans() -> None:
    for path in ACTIVE_INSTRUCTION_PATHS:
        text = _read(path)
        for pattern in UNCONDITIONAL_BIOLOGY_BAN_PATTERNS:
            assert re.search(pattern, text, flags=re.IGNORECASE) is None, path


def test_historical_files_are_not_active_instructions() -> None:
    for path in ACTIVE_INSTRUCTION_PATHS:
        assert "old_progress" not in path.parts

    archive_readme = _read(ROOT / "old_progress" / "README.md")
    assert "historical" in archive_readme.lower()
    assert "non-binding" in archive_readme.lower()
    assert re.search(r"must\s+not\s+be\s+treated\s+as\s+current\s+implementation\s+instructions", archive_readme)
