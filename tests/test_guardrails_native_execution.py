from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest
import yaml

from fungal_model import ConfiguredModelExecutionError, ValidatorRegistry, run_configured_model
from fungal_model.chemistry.reactions import Reaction
from fungal_model.core.simulation import SimulationEngine
from fungal_model.core.validators import validate_mass_balance, validate_non_negative
from fungal_model.plugins.pet import pet_substrate_loader_registry
from fungal_model.processes import AssembledModel
from fungal_model.processes.homogeneous import (
    FirstOrderDecayProcess,
    HomogeneousMichaelisMentenProcess,
    MassActionProcess,
)
from fungal_model.processes.surface import SurfaceCatalysisProcess
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


def test_configured_well_mixed_benchmarks_do_not_use_legacy_reaction_engine(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _forbid_legacy_reaction_execution(monkeypatch)
    cases = (
        (MODEL_CONFIGS / "toy_homogeneous_ab.yml", {}),
        (MODEL_CONFIGS / "synthetic_first_order_calibration.yml", {}),
        (MODEL_CONFIGS / "toy_surface_dummy_non_pet.yml", {}),
        (
            MODEL_CONFIGS / "toy_surface_pet_plugin.yml",
            {"substrate_registry": pet_substrate_loader_registry()},
        ),
    )

    for config_path, options in cases:
        result = run_configured_model(
            config_path,
            output_dir=tmp_path / config_path.stem,
            **options,
        )

        assert isinstance(result, SimulationResult)
        assert result.solver_metadata["backend"] == "scipy.solve_ivp"
        assert result.assembly_report is not None
        assert result.assembly_report.success


def test_configured_validator_path_runs_after_native_solver(tmp_path: Path) -> None:
    calls: list[tuple[str, tuple[str, ...]]] = []
    registry = ValidatorRegistry()

    def non_negative_validator(data):
        species = tuple(data.get("species", ()) or ())

        def validator(result):
            calls.append(("non_negative", tuple(sorted(result.species))))
            return validate_non_negative(result, species=species)

        return validator

    def mass_balance_validator(data):
        weights = dict(data["conserved_weights"])

        def validator(result):
            calls.append(("mass_balance", tuple(sorted(result.species))))
            return validate_mass_balance(result, conserved_weights=weights)

        return validator

    registry.register("non_negative", non_negative_validator)
    registry.register("mass_balance", mass_balance_validator)

    result = run_configured_model(
        MODEL_CONFIGS / "toy_homogeneous_ab.yml",
        output_dir=tmp_path / "validated",
        validator_registry=registry,
    )

    assert result.solver_metadata["backend"] == "scipy.solve_ivp"
    assert [name for name, _species in calls] == ["non_negative", "mass_balance"]
    assert all(
        species == ("dissolved_substrate_amount", "released_product_amount")
        for _name, species in calls
    )
    assert len(result.validation_results) == 2
    assert all(validation.passed for validation in result.validation_results)


def test_configured_unsupported_geometry_fails_before_legacy_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _forbid_legacy_reaction_execution(monkeypatch)
    config = yaml.safe_load((MODEL_CONFIGS / "toy_homogeneous_ab.yml").read_text(encoding="utf-8"))
    config["entities"]["geometry"] = {
        "id": "geometry",
        "path": "data/geometries/pet_film_1d.yml",
        "loader": "film_1d",
    }
    config_path = tmp_path / "unsupported_geometry.yml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    with pytest.raises(ConfiguredModelExecutionError) as error:
        run_configured_model(config_path, output_dir=tmp_path / "output")

    report = error.value.report
    assert report.stage == "model_execution"
    assert "successful_model_execution" in report.missing_capabilities
    assert report.details["error_type"] == "ValueError"
    assert "supports only well_mixed geometry" in report.message


def test_high_level_workflows_do_not_construct_low_level_solvers_directly() -> None:
    forbidden = re.compile(r"\b(SimulationEngine|ReactionDiffusionEngine|solve_ivp|as_reaction)\b")
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


def _forbid_legacy_reaction_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_args, **_kwargs) -> None:
        raise AssertionError("configured public workflows must not use the legacy Reaction engine")

    monkeypatch.setattr(SimulationEngine, "__post_init__", forbidden)
    monkeypatch.setattr(Reaction, "__post_init__", forbidden)
    for process_class in (
        FirstOrderDecayProcess,
        HomogeneousMichaelisMentenProcess,
        MassActionProcess,
        SurfaceCatalysisProcess,
    ):
        monkeypatch.setattr(process_class, "as_reaction", forbidden)
