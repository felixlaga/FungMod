"""Replay the recorded real-data comparison without refitting or promoting it."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from fungal_model.research.gelain_joint import load_joint_cultures, predict_joint, score_joint

ROOT=Path(__file__).resolve().parents[1]
RESULTS=ROOT/'data/benchmarks/gelain_2020_v2/results'


def test_joint_snapshot_hashes_and_scientific_evidence_boundaries():
    manifest=json.loads((RESULTS/'artifacts.json').read_text(encoding='utf-8'))
    actual={p.relative_to(RESULTS).as_posix() for p in RESULTS.rglob('*') if p.is_file() and p.name!='artifacts.json'}
    assert set(manifest)==actual
    for path,expected in manifest.items():
        assert hashlib.sha256((RESULTS/path).read_bytes()).hexdigest()==expected,path
    report=json.loads((RESULTS/'report.json').read_text(encoding='utf-8'))
    assert report['completed'] and not report['validated']
    assert report['observed_values']==144 and report['folds']==33
    assert report['successful_numerically_checked_folds']==33
    assert report['optimizer_starts']==132 and report['failed_starts']==6
    assert not report['source_activity_exact_parity_established']
    packets=list((RESULTS/'validation_readiness').glob('*.json'))
    assert len(packets)==11
    for path in packets:
        packet=json.loads(path.read_text(encoding='utf-8'))
        assert packet['status']=='awaiting_evidence' and not packet['validated']
        assert len(packet['missing_requirements'])==4
        assert packet['scope']['observation_time']['upper']==96
    for family in ('glycerol','cellulose'):
        bootstrap=json.loads((RESULTS/f'{family}_bootstrap.json').read_text(encoding='utf-8'))
        assert bootstrap['successful']==bootstrap['requested']==20
        assert not bootstrap['empirical_coverage_validated']
        assert bootstrap['error_assumption']['error_evidence']=='assumed'


def test_every_frozen_holdout_replays_with_training_only_scales_and_matching_scores():
    plan=json.loads((RESULTS/'plan.json').read_text(encoding='utf-8'))
    conditions=load_joint_cultures(ROOT)
    for fold in json.loads((RESULTS/'folds.json').read_text(encoding='utf-8')):
        fit=fold['fit']
        condition=next(c for c in conditions if c.design.condition_id==fold['condition'])
        training=[c for c in conditions if c.design.condition_id in fit['training_conditions']]
        assert condition.design.condition_id not in fit['training_conditions']
        assert len(training)==2
        np.testing.assert_allclose(fit['normalization'],np.max(np.concatenate([c.values for c in training]),axis=0))
        frozen=json.loads((RESULTS/fold['frozen_prediction_file']).read_text(encoding='utf-8'))
        replay=predict_joint(condition,fit,plan).values
        np.testing.assert_allclose(replay,frozen['predictions'],rtol=2e-6,atol=1e-6)
        score=score_joint(replay,condition,fit['normalization'])
        # A score cannot replay more tightly than the predictions it is computed
        # from; propagate the prediction tolerance per observable.
        tolerance=2e-6*np.max(np.abs(frozen['predictions']),axis=0)+1e-6
        for statistic in ('rmse','bias','normalized_mse'):
            assert set(score[statistic])==set(fold['score'][statistic])==set(condition.names)
            for index,name in enumerate(condition.names):
                assert score[statistic][name]==pytest.approx(fold['score'][statistic][name],rel=2e-6,abs=float(tolerance[index])),(statistic,name)
        assert frozen['plan_sha256']==hashlib.sha256((RESULTS/'plan.json').read_bytes()).hexdigest()
        assert frozen['software_manifest_sha256']==hashlib.sha256((RESULTS/'software.json').read_bytes()).hexdigest()
    comparison=json.loads((RESULTS/'comparison.json').read_text(encoding='utf-8'))
    cellulose=next(r for r in comparison if (r['family'],r['model'],r['scenario'])==('cellulose','published','primary'))
    assert not cellulose['complexity_screen_passed']
    assert cellulose['practical_rank']<=cellulose['parameter_count']
