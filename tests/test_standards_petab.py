"""PEtab export for FungMod calibration cases."""

from __future__ import annotations

import csv

import pytest

libsbml = pytest.importorskip("libsbml", reason="requires the optional 'standards' extra")

from fungal_model.resources import example_data_path
from fungal_model.standards import PetabExportError, calibration_config_to_petab

CALIBRATION_CONFIG = "calibration/synthetic/first_order_ab/calibration_config.yml"


def _read_tsv(path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        rows = list(reader)
        return list(reader.fieldnames or []), rows


def test_petab_export_writes_all_tables(tmp_path) -> None:
    export = calibration_config_to_petab(
        example_data_path(CALIBRATION_CONFIG), tmp_path / "petab"
    )
    for path in (
        export.problem_yaml, export.sbml_model, export.observables,
        export.measurements, export.conditions, export.parameters,
    ):
        assert path.exists() and path.stat().st_size > 0

    param_header, param_rows = _read_tsv(export.parameters)
    assert {"parameterId", "lowerBound", "upperBound", "nominalValue", "estimate"} <= set(param_header)
    k_ab = {row["parameterId"]: row for row in param_rows}["k_ab"]
    assert float(k_ab["lowerBound"]) == 0.0 and float(k_ab["upperBound"]) == 1.0
    assert float(k_ab["nominalValue"]) == 0.03 and k_ab["estimate"] == "1"

    obs_header, obs_rows = _read_tsv(export.observables)
    assert {"observableId", "observableFormula", "noiseFormula"} <= set(obs_header)
    assert obs_rows[0]["observableFormula"] == "released_product_amount"

    meas_header, meas_rows = _read_tsv(export.measurements)
    assert {"observableId", "simulationConditionId", "measurement", "time"} <= set(meas_header)
    assert len(meas_rows) > 0
    assert all(row["simulationConditionId"] == "condition1" for row in meas_rows)


def test_petab_export_validates_with_petab_library(tmp_path) -> None:
    pytest.importorskip("petab", reason="requires petab for validation")
    import petab.v1 as petab_v1

    export = calibration_config_to_petab(
        example_data_path(CALIBRATION_CONFIG), tmp_path / "petab"
    )
    problem = petab_v1.Problem.from_yaml(str(export.problem_yaml))
    # lint_problem returns False when the problem is valid (no errors).
    assert petab_v1.lint_problem(problem) is False


def test_petab_export_rejects_non_calibration_config(tmp_path) -> None:
    with pytest.raises(PetabExportError, match="calibration_config"):
        calibration_config_to_petab(
            example_data_path("model_configs/toy_homogeneous_ab.yml"), tmp_path / "petab"
        )


def test_petab_export_requires_bounds(tmp_path) -> None:
    import yaml

    config = yaml.safe_load(example_data_path(CALIBRATION_CONFIG).read_text(encoding="utf-8"))
    config.pop("bounds", None)
    broken = tmp_path / "no_bounds_calibration_config.yml"
    broken.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(PetabExportError, match="bounds"):
        calibration_config_to_petab(broken, tmp_path / "petab")


def test_petab_keeps_validation_out_of_fitting(tmp_path):
    import json
    export = calibration_config_to_petab(example_data_path(CALIBRATION_CONFIG), tmp_path)
    _, train = _read_tsv(export.measurements)
    _, validation = _read_tsv(export.validation_measurements)
    assert [float(row['time']) for row in train] == [0, 2, 4, 6]
    assert [float(row['time']) for row in validation] == [8, 10]
    assert 'validation_measurements.tsv' not in export.problem_yaml.read_text()
    assert json.loads(export.metadata.read_text())['training_rows'] == 4


@pytest.mark.parametrize('uncertainty', [None, 0.0])
def test_petab_refuses_unknown_or_zero_noise_before_writing(tmp_path, monkeypatch, uncertainty):
    from dataclasses import replace
    from fungal_model.data import loaders
    from fungal_model.data.loaders import load_experiment_dataset
    dataset = load_experiment_dataset(example_data_path('experiments/synthetic/first_order_ab/synthetic_first_order_ab.yml'))
    series = dataset.measurements[0]
    series = replace(series, points=tuple(replace(p, uncertainty=uncertainty) for p in series.points))
    monkeypatch.setattr(loaders, 'load_experiment_dataset', lambda path: replace(dataset, measurements=(series,)))
    with pytest.raises(PetabExportError, match='uncertainty'):
        calibration_config_to_petab(example_data_path(CALIBRATION_CONFIG), tmp_path / 'export')
    assert not (tmp_path / 'export').exists()


def test_petab_resource_resolution_outside_checkout(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    export = calibration_config_to_petab(example_data_path(CALIBRATION_CONFIG), tmp_path/'export')
    assert len(_read_tsv(export.measurements)[1]) == 4


def test_petab_keeps_unused_holdout_rows_outside_estimation(tmp_path):
    import yaml
    config = yaml.safe_load(example_data_path(CALIBRATION_CONFIG).read_text())
    config['split'] = {'method': 'by_time', 'train_fraction': 0.5, 'validation_fraction': 0.2}
    path = tmp_path/'case.yml'
    path.write_text(yaml.safe_dump(config))
    export = calibration_config_to_petab(path, tmp_path/'export')
    train = {r['time'] for r in _read_tsv(export.measurements)[1]}
    validation = {r['time'] for r in _read_tsv(export.validation_measurements)[1]}
    holdout = {r['time'] for r in _read_tsv(export.holdout_measurements)[1]}
    assert (len(train), len(validation), len(holdout)) == (3, 1, 2)
    assert not train & (validation | holdout)
    assert 'holdout_measurements.tsv' not in export.problem_yaml.read_text()


def test_petab_maps_colliding_parameter_ids_to_the_actual_export():
    from fungal_model.standards.petab import _sbml_symbol_maps
    document = libsbml.SBMLDocument(3, 2)
    model = document.createModel()
    for name, sid in [('K-m', 'K_m'), ('K_m', 'K_m_1')]:
        parameter = model.createParameter()
        parameter.setName(name)
        parameter.setId(sid)
        parameter.setConstant(True)
    _, parameters = _sbml_symbol_maps(libsbml.writeSBMLToString(document), ['K-m', 'K_m'])
    assert parameters == {'K-m': 'K_m', 'K_m': 'K_m_1'}


# --- multi-condition export -------------------------------------------------

import json

import numpy as np

from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.simulation import SolverSettings
from fungal_model.core.units import Q_
from fungal_model.processes.assembly import AssembledModel, AssemblyReport, ModelAssemblyContext
from fungal_model.processes.homogeneous import FirstOrderDecayProcess, MassActionProcess
from fungal_model.standards import PetabCondition, PetabObservable, PetabParameter, conditions_to_petab


def _parameter(symbol: str, value: float, units: str) -> Parameter:
    return Parameter(
        name=f"descriptive {symbol}", symbol=symbol, value=value, units=units,
        uncertainty=None, source="unit test", confidence_level="unknown", notes="",
    )


def _assembled(process, parameters) -> AssembledModel:
    context = ModelAssemblyContext()
    return AssembledModel(
        processes=(process,), parameters=ParameterSet(parameters), context=context,
        state_variables=tuple(process.state_variables), assumptions=(), validators=(),
        solver_settings=SolverSettings(), assembly_report=AssemblyReport(context=context),
    )


def _decay_model(k: float) -> AssembledModel:
    process = FirstOrderDecayProcess(
        name="conversion", substrate_state="A", rate_constant_symbol="k", state_units="millimolar", product_state="B",
    )
    return _assembled(process, [_parameter("k", k, "1/minute")])


TIMES_MIN = np.array([0.0, 5.0, 10.0, 20.0, 40.0])


def _two_conditions(k_nominal: float = 0.12, k_true: float = 0.08, noise=(100.0, 0.05)) -> list[PetabCondition]:
    conditions = []
    for condition_id, a0 in (("low", 2.0), ("high", 8.0)):
        b = a0 * (1.0 - np.exp(-k_true * TIMES_MIN))
        observed = np.column_stack([(a0 - b) * 1000.0, b])  # A reported in micromolar, B in millimolar
        conditions.append(
            PetabCondition(
                condition_id, _decay_model(k_nominal), {"A": Q_(a0, "millimolar"), "B": Q_(0.0, "millimolar")},
                "minute", TIMES_MIN, observed, np.asarray(noise),
            )
        )
    return conditions


OBSERVABLES = [PetabObservable("a_conc", "A", "micromolar"), PetabObservable("b_conc", "B", "millimolar")]
PARAMETERS = [PetabParameter("k", 1e-3, 1.0, 0.12, "log10", "rate constant")]


def test_multi_condition_export_writes_shared_model_condition_columns_and_lints(tmp_path):
    export = conditions_to_petab(
        _two_conditions(), observables=OBSERVABLES, parameters=PARAMETERS, output_dir=tmp_path / "petab", model_id="toy",
    )
    _, conditions = _read_tsv(export.conditions)
    assert [(row["conditionId"], float(row["A"])) for row in conditions] == [("low", 2.0), ("high", 8.0)]
    assert "B" not in conditions[0]  # B starts at 0 in both conditions: no column
    _, observables = _read_tsv(export.observables)
    by_id = {row["observableId"]: row for row in observables}
    assert by_id["observable_a_conc"]["observableFormula"] == "1000 * A"
    assert by_id["observable_b_conc"]["observableFormula"] == "B"
    assert float(by_id["observable_a_conc"]["noiseFormula"]) == 100.0
    header, measurements = _read_tsv(export.measurements)
    assert header == ["observableId", "simulationConditionId", "measurement", "time"]
    assert len(measurements) == 2 * 5 * 2
    assert {float(row["time"]) for row in measurements} == {0.0, 300.0, 600.0, 1200.0, 2400.0}
    _, parameters = _read_tsv(export.parameters)
    assert parameters[0]["parameterId"] == "k" and parameters[0]["parameterScale"] == "log10"
    assert parameters[0]["parameterName"] == "rate constant"
    # Parameter names in the SBML repeat the identifiers so tools can address them by name.
    assert libsbml.readSBMLFromString(export.sbml_model.read_text(encoding="utf-8")).getModel().getParameter("k").getName() == "k"
    pytest.importorskip("petab", reason="requires petab for validation")
    import petab.v1 as petab_v1

    assert petab_v1.lint_problem(petab_v1.Problem.from_yaml(str(export.problem_yaml))) is False
    metadata = json.loads(export.metadata.read_text(encoding="utf-8"))
    assert metadata["condition_species_columns"] == {"A": "A"}
    assert metadata["observables"]["observable_a_conc"]["state_to_observable_factor"] == 1000.0


def test_multi_condition_export_uses_per_row_noise_when_a_scale_varies(tmp_path):
    conditions = _two_conditions()
    noise = np.ones_like(conditions[0].observed) * np.array([100.0, 0.05])
    noise[-1, 1] = 0.5
    conditions[0] = PetabCondition(
        "low", conditions[0].model, conditions[0].initial_state, "minute", TIMES_MIN, conditions[0].observed, noise,
    )
    export = conditions_to_petab(conditions, observables=OBSERVABLES, parameters=PARAMETERS, output_dir=tmp_path)
    _, observables = _read_tsv(export.observables)
    by_id = {row["observableId"]: row for row in observables}
    assert by_id["observable_b_conc"]["noiseFormula"] == "noiseParameter1_observable_b_conc"
    assert float(by_id["observable_a_conc"]["noiseFormula"]) == 100.0
    header, measurements = _read_tsv(export.measurements)
    assert header[-1] == "noiseParameters"
    b_rows = [row for row in measurements if row["observableId"] == "observable_b_conc" and row["simulationConditionId"] == "low"]
    assert [float(row["noiseParameters"]) for row in b_rows] == [0.05, 0.05, 0.05, 0.05, 0.5]


def test_multi_condition_export_skips_unmeasured_values_and_refuses_bad_noise(tmp_path):
    conditions = _two_conditions()
    observed = conditions[0].observed.copy()
    observed[2, 0] = np.nan
    conditions[0] = PetabCondition("low", conditions[0].model, conditions[0].initial_state, "minute", TIMES_MIN, observed, np.array([100.0, 0.05]))
    export = conditions_to_petab(conditions, observables=OBSERVABLES, parameters=PARAMETERS, output_dir=tmp_path / "ok")
    assert len(_read_tsv(export.measurements)[1]) == 19
    with pytest.raises(PetabExportError, match="noise standard deviation"):
        conditions_to_petab(_two_conditions(noise=(100.0, 0.0)), observables=OBSERVABLES, parameters=PARAMETERS, output_dir=tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


def test_multi_condition_export_refuses_structurally_different_conditions(tmp_path):
    conditions = _two_conditions()
    other = MassActionProcess(
        name="conversion", reactants={"A": 1.0}, products={"B": 1.0}, state_units={"A": "millimolar", "B": "millimolar"},
        rate_constant_symbol="k", rate_constant_units="1/minute", rate_units="millimolar/minute",
    )
    conditions[1] = PetabCondition(
        "high", _assembled(other, [_parameter("k", 0.12, "1/minute")]), conditions[1].initial_state, "minute",
        TIMES_MIN, conditions[1].observed, np.array([100.0, 0.05]),
    )
    with pytest.raises(PetabExportError, match="different model"):
        conditions_to_petab(conditions, observables=OBSERVABLES, parameters=PARAMETERS, output_dir=tmp_path)


def test_multi_condition_export_validates_observables_and_parameters(tmp_path):
    with pytest.raises(PetabExportError, match="not an exported SBML species"):
        conditions_to_petab(
            _two_conditions(), observables=[OBSERVABLES[0], PetabObservable("c", "C", "millimolar")],
            parameters=PARAMETERS, output_dir=tmp_path,
        )
    with pytest.raises(PetabExportError, match="not an exported SBML parameter"):
        conditions_to_petab(_two_conditions(), observables=OBSERVABLES, parameters=[PetabParameter("q", 0.1, 1.0, 0.5)], output_dir=tmp_path)
    with pytest.raises(PetabExportError, match="containing its nominal value"):
        PetabParameter("k", 0.1, 1.0, 5.0)
    with pytest.raises(PetabExportError, match="positive lower bound"):
        PetabParameter("k", 0.0, 1.0, 0.5, "log10")
    with pytest.raises(PetabExportError, match="shape"):
        PetabCondition("c", _decay_model(0.1), {"A": Q_(1, "millimolar"), "B": Q_(0, "millimolar")}, "minute", TIMES_MIN, np.zeros((3, 2)), np.ones(2))


def test_multi_condition_export_puts_condition_specific_parameter_values_in_the_condition_table(tmp_path):
    conditions = []
    for condition_id, a0, loading in (("low", 2.0, 2.0), ("high", 8.0, 8.0)):
        process = FirstOrderDecayProcess(
            name="conversion", substrate_state="A", rate_constant_symbol="k", state_units="millimolar", product_state="B",
        )
        model = _assembled(process, [_parameter("k", 0.12, "1/minute"), _parameter("loading", loading, "millimolar")])
        b = a0 * (1.0 - np.exp(-0.08 * TIMES_MIN))
        conditions.append(
            PetabCondition(
                condition_id, model, {"A": Q_(a0, "millimolar"), "B": Q_(0.0, "millimolar")}, "minute", TIMES_MIN,
                np.column_stack([(a0 - b) * 1000.0, b]), np.array([100.0, 0.05]),
            )
        )
    export = conditions_to_petab(conditions, observables=OBSERVABLES, parameters=PARAMETERS, output_dir=tmp_path)
    header, rows = _read_tsv(export.conditions)
    assert header == ["conditionId", "conditionName", "A", "loading"]
    assert [(row["conditionId"], float(row["loading"])) for row in rows] == [("low", 2.0), ("high", 8.0)]
    assert json.loads(export.metadata.read_text(encoding="utf-8"))["condition_parameter_columns"] == ["loading"]
    with pytest.raises(PetabExportError, match="condition-specific values"):
        conditions_to_petab(
            conditions, observables=OBSERVABLES, parameters=[*PARAMETERS, PetabParameter("loading", 1.0, 10.0, 2.0)],
            output_dir=tmp_path / "clash",
        )
