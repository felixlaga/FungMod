"""Scoped evidence contracts on a non-fungal artificial chemical reaction."""
from dataclasses import replace
import json

import pytest

from fungal_model import run_configured_model
from fungal_model.calibration import (ModelScope, ScopeRange, evaluate_scoped_prediction, freeze_scoped_prediction,
                                      model_identity, validation_readiness)
from fungal_model.core.units import Q_
from fungal_model.data.comparison import ObservableMapping
from fungal_model.data.loaders import load_experiment_dataset
from fungal_model.resources import example_data_path
from tests.test_independent_validation import case  # noqa: F401 -- reusable pytest fixture


def identity(result):
    return model_identity(model_id="artificial_first_order_chemistry",model_version=result.model_version,
        equation_source="Artificial chemical-reaction software fixture",equation_sha256="a"*64,
        parameter_records=[{"symbol":p.symbol,"value":float(p.quantity.magnitude),"units":str(p.quantity.units),
                            "source":p.source} for p in result.parameters],
        observation_model={"product_mass":"released_product_amount"},training_experiment_ids=["training"])


def scope():
    return ModelScope({"preparation":"artificial chemical fixture"},
        {"temperature":ScopeRange(Q_(290,"K"),Q_(310,"K"))}, {"product_mass":"kilogram"},"Artificial proposed test domain",
        observation_time=ScopeRange(Q_(0,"s"),Q_(100000,"s")))


@pytest.fixture
def scoped_case(request,tmp_path):
    base = request.getfixturevalue("case")
    training = load_experiment_dataset(example_data_path('experiments/synthetic/first_order_ab/synthetic_first_order_ab.yml'))
    result = run_configured_model(example_data_path('model_configs/synthetic_first_order_calibration.yml'),output_dir=tmp_path/'model2')
    bundle = tmp_path/'bundle'
    frozen = freeze_scoped_prediction(result=result,training_dataset=training,identity=identity(result),scope=scope(),
        maximum_rmse=base['maximum_rmse'],observable_mapping=base['observable_mapping'],output_dir=bundle)
    return {"bundle_dir":bundle,"dataset":base['dataset'],"plan":replace(base['plan'],prediction_sha256=frozen['prediction_sha256']),
        "raw_replicates_path":base['raw_replicates_path'],"observable_mapping":base['observable_mapping'],
        "categorical_conditions":{"preparation":"artificial chemical fixture"},"numeric_conditions":{"temperature":Q_(300,"K")},
        "domain_review_source":"Artificial review fixture, not a real domain review","allow_synthetic_for_testing":True},result,training,base


def test_synthetic_case_can_never_promote_model_despite_passing_scores(scoped_case,tmp_path):
    args,_,_,_=scoped_case
    record = evaluate_scoped_prediction(**args,output_dir=tmp_path/'scoped-report')
    assert record['evidence']['meets_declared_criteria']
    assert record['status']=='not_validated'
    assert not record['entire_declared_range_validated'] and not record['publication_claim_authorized']
    assert not record['external_review_authenticated_by_software']
    assert record['tested_observation_times']['product_mass']['values']
    with pytest.raises(FileExistsError):
        evaluate_scoped_prediction(**args,output_dir=tmp_path/'scoped-report')


@pytest.mark.parametrize('defect',['contract','prediction','parameter','version','scope','review','training_id','reused_training','mapping','time'])
def test_scoped_contract_rejects_changes_and_out_of_scope_claims(scoped_case,tmp_path,defect):
    args,result,training,base = scoped_case
    if defect in {'parameter','version'}:
        ident = identity(result)
        if defect=='parameter':
            ident['parameters'][0]['value']*=2
        else:
            ident['model_version']='different'
        with pytest.raises(ValueError):
            freeze_scoped_prediction(result=result,training_dataset=training,identity=ident,scope=scope(),
                maximum_rmse=base['maximum_rmse'],observable_mapping=base['observable_mapping'],output_dir=tmp_path/'changed')
        return
    if defect=='contract':
        path = args['bundle_dir']/'contract.json'
        record=json.loads(path.read_text())
        record['scope']['source']='changed after prediction'
        path.write_text(json.dumps(record))
    elif defect=='prediction':
        args['plan']=replace(args['plan'],prediction_sha256='b'*64)
    elif defect=='scope':
        args['numeric_conditions']={'temperature':Q_(100,"K")}
    elif defect=='review':
        args['domain_review_source']=''
    elif defect=='training_id':
        args['plan']=replace(args['plan'],training_experiment_id='unrelated')
    elif defect=='reused_training':
        args['plan']=replace(args['plan'],training_experiment_id='other',validation_experiment_id='training')
    elif defect=='mapping':
        args['observable_mapping']=[ObservableMapping('product_mass','remaining_substrate_amount','state')]
    else:
        series=args['dataset'].measurements[0]
        args['dataset']=replace(args['dataset'],measurements=(replace(series,points=tuple(replace(p,time=p.time+200000) for p in series.points)),))
    with pytest.raises(ValueError):
        evaluate_scoped_prediction(**args)


def test_evidence_declarations_are_never_a_validated_flag(scoped_case):
    _,result,_,_=scoped_case
    sources=dict(criteria_source=None,independent_data_source=None,measurement_error_source=None,domain_review_source=None)
    pending=validation_readiness(identity(result),scope(),**sources)
    assert pending['status']=='awaiting_evidence' and len(pending['missing_requirements'])==4
    ready=validation_readiness(identity(result),scope(),**{k:'Artificial named evidence' for k in sources})
    assert ready['status']=='ready_for_frozen_evaluation' and not ready['validated']
    changed=identity(result)
    changed['observation_model']['product_mass']='a different law'
    assert validation_readiness(changed,scope(),**sources)['model_sha256']!=pending['model_sha256']


def test_scope_unit_conversion_roundtrip_and_bounds():
    domain=ModelScope({'sensor':'pressure instrument'},{'pressure':ScopeRange(Q_(1,'bar'),Q_(2,'bar'))},
                      {'reading':'pascal'},'Non-biological generic test')
    assert ModelScope.from_dict(domain.to_dict()).to_dict()==domain.to_dict()
    domain.check({'sensor':'pressure instrument'},{'pressure':Q_(150,'kilopascal')})
    for numeric in ({'pressure':Q_(3,'bar')},{}, {'pressure':Q_(float('nan'),'bar')}):
        with pytest.raises(ValueError):
            domain.check({'sensor':'pressure instrument'},numeric)
    with pytest.raises(ValueError):
        ScopeRange(Q_(2,'bar'),Q_(1,'bar'))


def test_frozen_contract_requires_all_observables_and_refuses_overwrite(scoped_case,tmp_path):
    args,result,training,base=scoped_case
    common=dict(result=result,training_dataset=training,identity=identity(result),scope=scope(),maximum_rmse=base['maximum_rmse'])
    with pytest.raises(ValueError,match='empty'):
        freeze_scoped_prediction(**common,observable_mapping=base['observable_mapping'],output_dir=args['bundle_dir'])
    with pytest.raises(ValueError,match='mapping'):
        freeze_scoped_prediction(**common,observable_mapping=[],output_dir=tmp_path/'no-mapping')
