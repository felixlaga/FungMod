"""Artificial end-to-end evidence tests; never empirical validation."""
import csv
import hashlib
from dataclasses import replace

import pytest

from fungal_model import run_configured_model
from fungal_model.calibration import IndependentValidationPlan, evaluate_frozen_prediction, freeze_prediction
from fungal_model.core.parameters import Parameter
from fungal_model.data.comparison import ObservableMapping
from fungal_model.data.loaders import load_experiment_dataset
from fungal_model.resources import example_data_path


@pytest.fixture
def case(tmp_path):
    training = load_experiment_dataset(example_data_path('experiments/synthetic/first_order_ab/synthetic_first_order_ab.yml'))
    result = run_configured_model(example_data_path('model_configs/synthetic_first_order_calibration.yml'), output_dir=tmp_path/'model')
    series = training.measurements[0]
    validation = replace(training, dataset_id='artificial-independent-test',
        measurements=(replace(series, points=tuple(replace(p, value=p.value+0.001) for p in series.points)),))
    frozen = tmp_path/'prediction.json'
    digest = freeze_prediction(result=result, training_dataset=training, model_source='Artificial immutable fixture v1', path=frozen)
    raw = tmp_path/'raw.csv'
    with raw.open('w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['measurement_id', 'time', 'time_units', 'value', 'units', 'replicate_id', 'experiment_id', 'preparation_id'])
        for point in validation.measurements[0].points:
            for rep, offset in [('a', -0.001), ('b', 0.001)]:
                writer.writerow(['product_mass', point.time, 'second', point.value+offset, 'kilogram', rep, 'validation', 'test preparation'])
    plan = IndependentValidationPlan(analysis_plan_source='Artificial prespecified criteria test',
        prediction_sha256=digest, training_experiment_id='training', validation_experiment_id='validation',
        preparation_id='test preparation', preparation_match_source='Artificial same-preparation fixture',
        independence_source='Artificial separate-dataset test', uncertainty_source='Artificial known noise',
        raw_replicates_source='Artificial raw replicate test table', raw_replicates_sha256=hashlib.sha256(raw.read_bytes()).hexdigest())
    threshold = Parameter(name='test RMSE', symbol='max_rmse', value=0.01, units='kilogram', uncertainty=None,
                          source='Artificial declared threshold', confidence_level='testing', notes='No empirical claim')
    return dict(prediction_path=frozen, dataset=validation, plan=plan, raw_replicates_path=raw,
        observable_mapping=[ObservableMapping('product_mass', 'released_product_amount', 'state')],
        maximum_rmse={'product_mass': threshold}, allow_synthetic_for_testing=True, output_dir=tmp_path/'report')


def test_frozen_prediction_scores_without_refitting_or_empirical_claim(case):
    before = case['prediction_path'].read_bytes()
    report = evaluate_frozen_prediction(**case)
    assert report['meets_declared_criteria']
    assert not report['parameters_refitted']
    assert not report['empirical_criteria_met']
    assert not report['publication_claim_authorized']
    assert report['evidence_mode'] == 'synthetic_software_test'
    assert case['prediction_path'].read_bytes() == before
    assert (case['output_dir']/'independent_validation.json').exists()


@pytest.mark.parametrize('defect', ['prediction_changed', 'raw_changed', 'synthetic', 'reused_id',
    'no_raw', 'digitization', 'unmatched_mean', 'missing_threshold', 'preparation'])
def test_independent_validation_rejects_inadequate_evidence(case, defect):
    dataset = case['dataset']
    if defect == 'prediction_changed':
        case['prediction_path'].write_text('{}')
    elif defect == 'raw_changed':
        case['raw_replicates_path'].write_text('bad')
    elif defect == 'synthetic':
        case['allow_synthetic_for_testing'] = False
    elif defect == 'reused_id':
        case['dataset'] = replace(dataset, dataset_id='synthetic_first_order_ab_v1')
    elif defect == 'no_raw':
        case['dataset'] = replace(dataset, preprocessing=replace(dataset.preprocessing, raw_data_available=False))
    elif defect == 'digitization':
        case['dataset'] = replace(dataset, measurements=(replace(dataset.measurements[0], uncertainty_type='digitization_resolution'),))
    elif defect == 'unmatched_mean':
        series = dataset.measurements[0]
        case['dataset'] = replace(dataset, measurements=(replace(series, points=tuple(replace(p, value=p.value+0.1) for p in series.points)),))
    elif defect == 'missing_threshold':
        case['maximum_rmse'] = {}
    else:
        case['plan'] = replace(case['plan'], preparation_id='different preparation')
    with pytest.raises(ValueError):
        evaluate_frozen_prediction(**case)
    assert not case['output_dir'].exists()


def test_freeze_refuses_overwrite(case):
    # Exclusive creation is also essential when a caller reuses an output path.
    from fungal_model.core.parameters import ParameterSet
    from fungal_model.core.simulation import SolverSettings
    from fungal_model.core.units import Q_
    from fungal_model.results import SimulationResult
    result = SimulationResult(time=Q_([0,1], 'second'), states={'x': Q_([1,0], 'mole')},
        parameters=ParameterSet([]), assumptions=(), solver_settings=SolverSettings(), solver_metadata={'success': True})
    with pytest.raises(FileExistsError):
        freeze_prediction(result=result, training_dataset=case['dataset'], model_source='Artificial test', path=case['prediction_path'])
