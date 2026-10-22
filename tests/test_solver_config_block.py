"""The optional top-level ``solver`` block: parsed, validated, assembled, recorded and honoured by the predictor."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import yaml

from fungal_model.calibration import compiled_predictor
from fungal_model.calibration.compiled_predictor import (
    ConfiguredCondition,
    ConfiguredConditionPredictor,
    ObservableMapping,
    inline_parameter_config_factory,
)
from fungal_model.core.numerics import JACOBIAN_COMPILED, SolverSettings
from fungal_model.core.units import Q_
from fungal_model.io.model_config import ModelConfig, ModelConfigError, SolverConfig, load_model_config
from fungal_model.solvers.compiled import JACOBIAN_COMPILED_LABEL
from fungal_model.workflows.configured_model import ConfiguredInputLoader, ConfiguredProcessAssembler, run_configured_model

ROOT = Path(__file__).resolve().parents[1]
TOY = ROOT / "data" / "model_configs" / "toy_homogeneous_ab.yml"
STATES = ("dissolved_substrate_amount", "released_product_amount")
BLOCK = {
    "method": "BDF",
    "rtol": 1e-9,
    "atol": {name: {"value": 1e-12, "units": "kilogram"} for name in STATES},  # the toy states are masses
    "max_step": {"value": 0.5, "units": "second"},
    "jacobian": JACOBIAN_COMPILED,
}


def _toy_mapping(block: dict | None) -> dict:
    data = yaml.safe_load(TOY.read_text(encoding="utf-8"))
    if block is not None:
        data["solver"] = block
    return data


def _assembled(config: ModelConfig):
    inputs = ConfiguredInputLoader().load(config)
    return ConfiguredProcessAssembler().assemble(config, inputs).model


def test_solver_block_round_trips_into_the_assembled_model() -> None:
    config = ModelConfig.from_mapping(_toy_mapping(BLOCK), path=TOY)
    assert isinstance(config.solver, SolverConfig)
    assert config.solver.to_dict() == BLOCK and config.to_dict()["solver"] == BLOCK
    assert config.solver.method == "BDF" and config.solver.jacobian == JACOBIAN_COMPILED and config.solver.first_step is None
    assert config.validate().passed
    expected = SolverSettings(method="BDF", rtol=1e-9, atol={name: Q_(1e-12, "kilogram") for name in STATES},
                              max_step=Q_(0.5, "second"), jacobian=JACOBIAN_COMPILED)
    assert config.solver.to_solver_settings() == expected
    assert _assembled(config).solver_settings == expected


def test_a_config_without_a_solver_block_keeps_the_default_settings() -> None:
    config = load_model_config(TOY)
    assert config.solver is None
    assert _assembled(config).solver_settings == SolverSettings()


@pytest.mark.parametrize("block, match", [
    ({"methd": "BDF"}, "unsupported keys"),
    ({"method": "BDF", "events": True}, "unsupported keys"),
    ({"rtol": 0.0}, "invalid"),
    ({"atol": {"dissolved_substrate_amount": 1e-12}}, "invalid"),
    ({"jacobian": "symbolic"}, "invalid"),
    ("BDF", "mapping"),
])
def test_unknown_keys_and_invalid_values_are_refused_when_the_config_is_loaded(block, match: str) -> None:
    with pytest.raises(ModelConfigError, match=match):
        ModelConfig.from_mapping(_toy_mapping(block), path=TOY)


def test_solver_settings_json_records_the_block_and_the_compiled_jacobian(tmp_path: Path) -> None:
    path = tmp_path / "toy_with_solver_block.yml"
    path.write_text(yaml.safe_dump(_toy_mapping(BLOCK), sort_keys=False), encoding="utf-8")
    result = run_configured_model(path, output_dir=tmp_path / "out")
    recorded = json.loads((tmp_path / "out" / "solver_settings.json").read_text(encoding="utf-8"))
    settings = recorded["solver_settings"]
    assert settings["method"] == "BDF" and settings["rtol"] == 1e-9 and settings["jacobian"] == JACOBIAN_COMPILED
    assert settings["atol"] == {name: {"value": 1e-12, "units": "kilogram"} for name in STATES}
    assert settings["max_step"] == {"value": 0.5, "units": "second"}
    assert recorded["solver_metadata"]["method"] == "BDF"
    assert recorded["solver_metadata"]["kernel"]["jacobian"] == JACOBIAN_COMPILED_LABEL
    assert recorded["solver_metadata"]["njev"] > 0
    assert result.solver_settings.to_dict() == settings


def test_predictor_honours_the_compiled_jacobian_and_matches_the_public_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = _toy_mapping(BLOCK)
    path = tmp_path / "toy_with_solver_block.yml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    fitted_value = next(
        float(entry["value"]) for parameter_set in data["parameters"] for entry in parameter_set["parameters"] if entry["symbol"] == "k_ab"
    )
    config = ModelConfig.from_mapping(data, path=TOY)
    condition = ConfiguredCondition("toy", inline_parameter_config_factory(config), (ObservableMapping("product", STATES[1], "gram"),))
    predictor = ConfiguredConditionPredictor([condition], fitted_symbols=["k_ab"])
    seen: list[tuple[str, int]] = []
    original = compiled_predictor.integrate_compiled

    def spy(settings, compiled, t_span, y0, *, t_eval=None):
        solution, label = original(settings, compiled, t_span, y0, t_eval=t_eval)
        seen.append((label, int(solution.njev)))
        return solution, label

    monkeypatch.setattr(compiled_predictor, "integrate_compiled", spy)
    times = np.linspace(0.0, 10.0, 11)
    predicted = predictor.predict_values({"k_ab": fitted_value}, "toy", times)
    assert seen == [(JACOBIAN_COMPILED_LABEL, seen[0][1])] and seen[0][1] > 0
    reference = run_configured_model(path, output_dir=tmp_path / "ref")
    assert reference.solver_metadata["kernel"]["jacobian"] == JACOBIAN_COMPILED_LABEL
    expected = np.asarray(reference.states[STATES[1]].to("gram").magnitude, dtype=float)
    np.testing.assert_allclose(predicted[:, 0], expected, rtol=1e-9, atol=1e-12)


def test_a_per_state_atol_in_a_unit_incompatible_with_the_state_is_refused_at_run_time(tmp_path: Path) -> None:
    block = dict(BLOCK, atol={name: {"value": 1e-12, "units": "millimolar"} for name in STATES})
    config = ModelConfig.from_mapping(_toy_mapping(block), path=TOY)
    assert config.validate().passed  # the block alone is well formed; the unit clash surfaces against the states
    path = tmp_path / "toy_with_wrong_atol_units.yml"
    path.write_text(yaml.safe_dump(_toy_mapping(block), sort_keys=False), encoding="utf-8")
    with pytest.raises(Exception, match="millimolar, which are incompatible with kilogram"):
        run_configured_model(path, output_dir=tmp_path / "out")
