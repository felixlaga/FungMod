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
