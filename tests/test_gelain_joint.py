"""Model limits and artificial calibration tests; empirical artifacts are scored separately."""
from copy import deepcopy
from dataclasses import replace
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
from pint.errors import DimensionalityError

from fungal_model.core.units import Q_
from fungal_model.research import gelain_joint as joint
from fungal_model.research.gelain_culture import CultureBenchmarkError, CultureDesign, parameters_from_records, simulate_culture
from fungal_model.research.gelain_models import CultureMeasurements, OBSERVABLE_UNITS, parameter_units, simulate_candidate

ROOT = Path(__file__).resolve().parents[1]
PLAN = json.loads((ROOT/"data/benchmarks/gelain_2020_v2/plan.json").read_text())
spec = importlib.util.spec_from_file_location("joint_runner",ROOT/"scripts/run_gelain_2020_joint_benchmark.py")
assert spec and spec.loader
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def parameters(model, family, **overrides):
    values = {"mu":.1,"K":2,"Y":.5,"kd":.01,"f_retained":.8,"k_clear":.005,"initial_retained_fraction":0,
        "qF":2,"qB":3,"kF":.01,"kB":.02,"k_h":.03,"Kh":3,"K_ind":2}
    values.update(overrides)
    return parameters_from_records([{"symbol":k,"value":values[k],"units":u,"source":"Artificial numerical test"}
                                    for k,u in parameter_units(model,family).items()])


def design(family="glycerol", **kwargs):
    return CultureDesign("artificial",family,Q_([0,1,5,10,20],"hour"),Q_(.5,"g/L"),Q_(10,"g/L"),"Artificial software test",**kwargs)


def synthetic():
    d = design()
    truth = simulate_candidate(d,{},parameters("effective","glycerol"),model="effective",hypothesis_source="Artificial test")
    c = CultureMeasurements(d,truth.observables,{},"Synthetic recovery fixture")
    plan = deepcopy(PLAN)
    plan.update(starts=1,max_nfev=100)
    values = [.1,2,.5,.01]
    for r,v in zip(plan["models"]["glycerol"]["effective"]["parameters"],values,strict=True):
        r.update(lower=v/2,upper=v*2)
    return c,plan


def test_activity_dimensions_are_assay_specific_not_mass_or_each_other():
    for unit in ("g/L","mole/L","gelain_beta_u/L"):
        with pytest.raises(DimensionalityError):
            Q_(1,"gelain_fpu/L").to(unit)
    np.testing.assert_allclose(Q_(1,"gelain_fpu/mL").to("gelain_fpu/L").magnitude,1000)


def test_loader_uses_all_144_noninitial_observations_with_separate_initial_assays():
    conditions = joint.load_joint_cultures(ROOT)
    assert sum(c.values.size for c in conditions) == 144
    assert len(conditions)==6
    assert all(np.min(c.design.times.magnitude)>0 for c in conditions)
    assert all(set(c.initial_activities)==set(c.names[2:]) for c in conditions)


def test_retained_mass_does_not_claim_viable_biomass_and_conserves_loss_pool():
    d = replace(design(),initial_substrate=Q_(0,"g/L"))
    p = parameters("retained","glycerol",f_retained=1,k_clear=0,kd=.1)
    result = simulate_candidate(d,{},p,model="retained",hypothesis_source="Artificial no-clearance limit")
    np.testing.assert_allclose(result.values[:,0],.5,rtol=1e-8)
    np.testing.assert_allclose(result.retained_dry_mass.magnitude,.5*(1-np.exp(-.1*d.times.magnitude)),rtol=1e-7,atol=1e-9)
    assert set(result.observables)=={"biomass","substrate"}
    assert result.maturity == "exploratory_software_tested"


def test_hydrolysis_needs_activity_and_obeys_apparent_yield_bookkeeping():
    d = design("cellulose")
    initial = {k:Q_(0,u) for k,u in list(OBSERVABLE_UNITS.items())[2:]}
    inert = simulate_candidate(d,initial,parameters("hydrolysis","cellulose",qF=0,qB=0,kd=0),
        model="hydrolysis",hypothesis_source="Artificial zero-activity limit")
    np.testing.assert_allclose(inert.values,np.tile([.5,10,0,0],(5,1)))
    initial["cellulase_activity"] = Q_(1,"gelain_fpu/L")
    active = simulate_candidate(d,initial,parameters("hydrolysis","cellulose",kd=0),model="hydrolysis",hypothesis_source="Artificial limit")
    np.testing.assert_allclose(active.values[:,0]+.5*active.values[:,1],5.5,rtol=1e-8)
    assert active.values[-1,1]<10
    alternate = simulate_candidate(d,initial,parameters("hydrolysis","cellulose",kd=0),model="hydrolysis",hypothesis_source="Artificial limit",method="DOP853")
    np.testing.assert_allclose(active.values,alternate.values,rtol=2e-7,atol=1e-8)


def test_normalized_published_kernel_matches_original_source_mass_projection():
    d = design("cellulose")
    old = json.loads((ROOT/"data/benchmarks/gelain_2020/source_parameters.json").read_text())["cellulose"]
    new = json.loads((ROOT/"data/benchmarks/gelain_2020_v2/source_parameters.json").read_text())["parameters"]
    a = simulate_culture(d,parameters_from_records(old),model="source_deposited_v1",hypothesis_source="Source parity")
    b = simulate_candidate(d,{k:Q_(0,u) for k,u in list(OBSERVABLE_UNITS.items())[2:]},parameters_from_records(new),
                           model="published",hypothesis_source="Source parity")
    np.testing.assert_allclose(a.observations_g_l,b.values[:,:2],rtol=1e-6,atol=1e-8)


def test_zero_source_induction_leaves_only_activity_decay():
    d = replace(design("cellulose"),initial_substrate=Q_(0,"g/L"))
    records = json.loads((ROOT/"data/benchmarks/gelain_2020_v2/source_parameters.json").read_text())["parameters"]
    p = {r["symbol"]:r["value"] for r in records}
    initial = {"cellulase_activity":Q_(2,"gelain_fpu/L"),"beta_glucosidase_activity":Q_(3,"gelain_beta_u/L")}
    result = simulate_candidate(d,initial,parameters_from_records(records),model="published",hypothesis_source="Artificial source limit")
    np.testing.assert_allclose(result.values[:,2],2*np.exp(-p["kF"]*d.times.magnitude),rtol=1e-7)
    np.testing.assert_allclose(result.values[:,3],3*np.exp(-p["kB"]*d.times.magnitude),rtol=1e-7)


def test_artificial_recovery_determinism_profiles_and_conditional_bootstrap():
    c,plan = synthetic()
    fit = joint.fit_joint([c],plan,model="effective",scenario="primary")
    assert fit == joint.fit_joint([c],plan,model="effective",scenario="primary")
    assert fit["success"] and fit["objective"]<1e-14
    np.testing.assert_allclose([r['value'] for r in fit['parameters']],[.1,2,.5,.01],rtol=1e-5)
    assert fit["measurement_uncertainty"] is None and fit["confidence_intervals"] is None
    profile = joint.profile_joint([c],fit,plan)
    assert profile["confidence_intervals"] is None
    assert all(any(p['delta_objective']==pytest.approx(0,abs=1e-9) for p in points if p['success']) for points in profile['profiles'].values())
    plan["bootstrap"].update(samples=2,minimum_successful=1)
    boot = joint.conditional_bootstrap([c],fit,plan)
    assert boot == joint.conditional_bootstrap([c],fit,plan)
    assert not boot["empirical_coverage_validated"] and not boot["experimental_replicates_generated"]
    assert boot["error_assumption"]["error_evidence"] == "assumed"


def test_all_failed_starts_and_insufficient_bootstrap_draws_are_visible(monkeypatch):
    c,plan = synthetic()
    fit = joint.fit_joint([c],plan,model="effective",scenario="primary")
    def fail(*args,**kwargs):
        raise CultureBenchmarkError("Deliberate numerical failure")
    monkeypatch.setattr(joint,"_integrate",fail)
    failed = joint.fit_joint([c],plan,model="effective",scenario="primary")
    assert not failed['success'] and len(failed['starts'])==1
    assert 'parameters' not in failed
    plan['bootstrap'].update(samples=2,minimum_successful=2)
    boot = joint.conditional_bootstrap([c],fit,plan)
    assert boot['bands'] is None and boot['successful']==0


def test_measured_covariance_and_known_censoring_flow_through_fitter(monkeypatch):
    c,plan = synthetic()
    from fungal_model.calibration import GaussianObservationError
    err = GaussianObservationError(c.names,tuple(OBSERVABLE_UNITS[k] for k in c.names),
        {k:Q_(.1,OBSERVABLE_UNITS[k]) for k in c.names},np.array([[1,-.3],[-.3,1]]),
        "Artificial measured-noise fixture", "measured_standard_deviation",
        left_limits={"biomass":Q_([.6,np.nan,np.nan,np.nan,np.nan],"g/L")},detection_limit_source="Artificial limit")
    fit = joint.fit_joint([c],plan,model="effective",scenario="primary",observation_errors={c.design.condition_id:err})
    assert fit['success']
    assert fit['measurement_uncertainty']==['measured_standard_deviation']
    assert fit['noise']['artificial']['left_limits'][0][0]==.6
    real_fit = joint.fit_joint
    calls = []
    def checked(*args,**kwargs):
        restored = kwargs['observation_errors'][c.design.condition_id]
        assert restored.to_dict(len(c.values))==err.to_dict(len(c.values))
        calls.append(True)
        return real_fit(*args,**kwargs)
    monkeypatch.setattr(joint,'fit_joint',checked)
    joint.profile_joint([c],fit,plan)
    assert calls


def test_holdout_prediction_is_frozen_before_scoring_and_cannot_use_response(tmp_path,monkeypatch):
    c,plan = synthetic()
    fit = joint.fit_joint([c],plan,model="effective",scenario="primary")
    (tmp_path/'frozen_predictions').mkdir()
    original = runner.score_joint
    def checked(predicted,condition,scales):
        assert list((tmp_path/'frozen_predictions').glob('*.json'))
        return original(predicted,condition,scales)
    monkeypatch.setattr(runner,'score_joint',checked)
    first = runner.freeze_and_score(tmp_path,c,fit,plan,{})
    path = tmp_path/first['frozen_prediction_file']
    before = path.read_bytes()
    changed = replace(c,observations={k:v*10 for k,v in c.observations.items()})
    second_dir = tmp_path/'second'
    (second_dir/'frozen_predictions').mkdir(parents=True)
    second = runner.freeze_and_score(second_dir,changed,fit,plan,{})
    assert (second_dir/second['frozen_prediction_file']).read_bytes()==before
    assert first['score']!=second['score']


@pytest.mark.parametrize('bad', ['mixed','duplicates','unknown','missing_fixed','bad_bounds','bad_fraction','bad_bootstrap'])
def test_joint_contract_rejects_unsupported_inputs(bad):
    conditions = joint.load_joint_cultures(ROOT)
    c,plan = synthetic()
    training=[c]
    model='effective'
    if bad=='mixed':
        training=conditions[2:4]
    elif bad=='duplicates':
        training=[c,c]
    elif bad=='unknown':
        plan['hypotheses']['effective']=''
    elif bad=='missing_fixed':
        model='retained'
        plan['models']['glycerol'][model]['fixed_parameters']=[]
    elif bad=='bad_bounds':
        plan['models']['glycerol'][model]['parameters'][0]['lower']=0
    elif bad=='bad_fraction':
        plan['models']['glycerol'][model]['parameters'][2]['upper']=2
    else:
        fit = joint.fit_joint([c],plan,model=model,scenario='primary')
        plan['bootstrap']['minimum_successful']=0
        with pytest.raises(ValueError,match='Bootstrap'):
            joint.conditional_bootstrap([c],fit,plan)
        return
    with pytest.raises(ValueError):
        joint.fit_joint(training,plan,model=model,scenario='primary')
