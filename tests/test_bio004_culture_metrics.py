"""Numerical reductions of synthetic trajectories, never biological validation."""
import pytest
from fungal_model.api.culture_metrics import trajectory_metrics, time_below_threshold


def _rows():
    return [dict(time=t,time_units="h",G=g,G_units="mmol/L",X=x,X_units="g/L",O=o,O_units="mmol/L")
            for t,g,x,o in [(0,1,.1,.4),(2,3,.2,.0),(5,3,.4,.3)]]


def test_extrema_first_peak_and_explicit_converted_threshold():
    roles={"soluble_product":"G","biomass":"X","ledger_respired_carbon":"L","dissolved_oxygen":"O"}
    metrics={m["metric_name"]:m for m in trajectory_metrics(_rows(),roles,oxygen_threshold={"value":200,"units":"umol/L"})}
    assert metrics["peak_soluble_sugar"]["value"]==3
    assert metrics["time_of_peak_soluble_sugar"]["value"]==2
    assert metrics["final_biomass"]["value"]==.4
    assert metrics["minimum_dissolved_oxygen"]["value"]==0
    # Downcross at t=1, upcross at t=4; all 3 hours count.
    assert metrics["time_below_oxygen_threshold"]["value"]==pytest.approx(3)


@pytest.mark.parametrize("values,threshold,expected",[
    ([0,0,0],.1,5),([.2,.2,.2],.1,0),([.1,.1,.1],.1,0),
    ([.2,.1,0],.1,3),([0,.1,.2],.1,2),([.1,0,.1],.1,5),
])
def test_threshold_duration_uses_strict_below_and_crossings(values,threshold,expected):
    assert time_below_threshold([0,2,5],values,threshold)==pytest.approx(expected)


def test_absent_threshold_is_unknown_and_legacy_roles_add_no_rows():
    metrics=trajectory_metrics(_rows(),{"dissolved_oxygen":"O"})
    assert metrics[-1]["status"]=="unknown" and metrics[-1]["value"]==""
    assert trajectory_metrics(_rows(),{"biomass":"X"})==[]


@pytest.mark.parametrize("threshold",[
    {"value":True,"units":"mmol/L"},{"value":-1,"units":"mmol/L"},
    {"value":float("nan"),"units":"mmol/L"},{"value":[.1],"units":"mmol/L"},
])
def test_invalid_thresholds_do_not_turn_into_hidden_cutoffs(threshold):
    with pytest.raises(ValueError):
        trajectory_metrics(_rows(),{"dissolved_oxygen":"O"},oxygen_threshold=threshold)


@pytest.mark.parametrize("template,expected", [
    (None, set()),
    ({"state_roles": {"dissolved_oxygen": "O"}}, {"minimum_dissolved_oxygen", "time_below_oxygen_threshold"}),
    ({"output_state_roles": {}, "state_roles": {"dissolved_oxygen": "O"}},
     {"minimum_dissolved_oxygen", "time_below_oxygen_threshold"}),
])
def test_configured_reductions_accept_null_and_fallback_role_metadata(template, expected):
    from pathlib import Path
    from types import SimpleNamespace
    from fungal_model.core.units import Q_
    from fungal_model.io.model_config import ModelConfig, load_model_config
    from fungal_model.workflows.mechanism_metrics import summarize_mechanisms

    base = load_model_config(Path(__file__).resolve().parents[1] / "data/model_configs/toy_homogeneous_ab.yml")
    # These optional metadata forms pass the public config loader. The result
    # is synthetic reporting input, not evidence for an oxygen mechanism.
    config = ModelConfig.from_mapping({**base.raw, "case_template": template}, path=base.path)
    result = SimpleNamespace(time=Q_([0, 1], "s"), states={"O": Q_([.2, .1], "mM")}, derived_quantities={})
    metrics = {row["metric_name"]: row for row in summarize_mechanisms(config, result)}
    assert set(metrics) == expected
    if metrics:
        assert metrics["minimum_dissolved_oxygen"]["value"] == .1
        assert metrics["time_below_oxygen_threshold"]["status"] == "unknown"
