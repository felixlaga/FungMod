from __future__ import annotations

import inspect
import re
from pathlib import Path

from fungal_model import run_configured_model
from fungal_model.processes import AssembledModel
from fungal_model.results import SimulationResult


ROOT = Path(__file__).resolve().parents[1]
MODEL_CONFIGS = ROOT / "data" / "model_configs"


def test_configured_workflow_calls_assembled_model_run(monkeypatch, tmp_path) -> None:
    calls: list[str] = []
    original_run = AssembledModel.run

    def wrapped_run(self: AssembledModel, **kwargs):
        calls.append(kwargs["name"])
        return original_run(self, **kwargs)

    monkeypatch.setattr(AssembledModel, "run", wrapped_run)

    result = run_configured_model(
        MODEL_CONFIGS / "toy_homogeneous_ab.yml",
        output_dir=tmp_path / "homogeneous",
    )

    assert isinstance(result, SimulationResult)
    assert calls == ["toy homogeneous A to B benchmark"]


def test_high_level_workflows_do_not_construct_low_level_solvers_directly() -> None:
    forbidden = re.compile(r"\b(SimulationEngine|ReactionDiffusionEngine|solve_ivp)\b")
    searched_paths = (
        ROOT / "src" / "fungal_model" / "workflows",
        ROOT / "src" / "fungal_model" / "plugins" / "pet",
        ROOT / "notebooks" / "examples",
    )
    violations: list[str] = []

    for root in searched_paths:
        for path in sorted(root.rglob("*")):
            if path.suffix not in {".py", ".ipynb"}:
                continue
            relative = path.relative_to(ROOT).as_posix()
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if forbidden.search(line):
                    violations.append(f"{relative}:{line_number}: {line.strip()}")

    assert not violations, "High-level workflows must execute through AssembledModel.run().\n" + "\n".join(violations)


def test_assembled_model_run_is_public_and_not_placeholder() -> None:
    source = inspect.getsource(AssembledModel.run)

    assert "ProcessODESolver" in source
    assert "NotImplementedError" not in source
    assert "placeholder" not in source.lower()
