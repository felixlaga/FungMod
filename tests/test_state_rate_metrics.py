"""Degradation and product-release rates come from recorded net state rates.

``degradation_rate`` is -d[substrate]/dt and ``product_release_rate`` is
+d[product]/dt of the case's mapped substrate and product states, read from
the ``state_rates.csv`` trajectory that the well-mixed solver records by
evaluating the same compiled right-hand side it integrated. They are never a
process rate, so a product yield other than one and multi-process cases keep
their own values and units. A bundle without a state-rate trajectory reports
them as not applicable instead of falling back to process rates.
"""

from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np
import pytest
import yaml

import fungal_model as fm
from fungal_model import VirtualExperiment
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_
from fungal_model.processes import FirstOrderDecayProcess, MassActionProcess, ModelBuilder, ProcessRegistry
from fungal_model.registry import load_registry
from fungal_model.screening import build_model_config_from_registry_case
from fungal_model.solvers import ProcessODESolver, RunRequest
from fungal_model.workflows import run_configured_model

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"

REACTION_618_TEMPLATE_ID = "sabiork_reaction_618_homogeneous_mm_template"
REACTION_618_PROCESS_RATE = "process_rate.sabiork_reaction_618_homogeneous_mm"

CULTURE_FUNGUS_ID = "trichoderma_harzianum_p49p11"
CULTURE_SUBSTRATE_ID = "cellulose_celufloc_200"
CULTURE_ENVIRONMENT_ID = "gelain_2020_cellulose_batch_10gl"
CULTURE_TEMPLATE_ID = "trichoderma_harzianum_cellulose_culture_template"
CULTURE_SUBSTRATE_STATE = "cellulose_concentration"
# The fine grid is this many times denser than the template's hourly output grid.
FINE_GRID_REFINEMENT = 20
# Second-order central differences on a 0.05 h grid of a trajectory integrated at
# the configured solver tolerances agree with the exact derivative to about 1e-5
# of the peak rate; 1e-4 of the peak rate leaves an order-of-magnitude margin.
FINITE_DIFFERENCE_RELATIVE_TOLERANCE = 1e-4

NO_STATE_RATE_REASON = "No state-rate trajectory was recorded for this sample."


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _series(rows: Sequence[Mapping[str, str]], sample_id: str, state: str) -> dict[int, Mapping[str, str]]:
    return {
        int(row["time_index"]): row
        for row in rows
        if row["sample_id"] == sample_id and row["state"] == state
    }


def _metric(rows: Sequence[Mapping[str, str]], sample_id: str, metric: str) -> Mapping[str, str]:
    matches = [row for row in rows if row["sample_id"] == sample_id and row["metric"] == metric]
    assert len(matches) == 1, (sample_id, metric)
    return matches[0]


def _same_dimensionality(units: str, reference_units: str) -> bool:
    return Q_(1.0, units).dimensionality == Q_(1.0, reference_units).dimensionality


@pytest.fixture(scope="module")
def registry():
    return load_registry(REGISTRY_INDEX)


@pytest.fixture(scope="module")
def reaction_618_result(tmp_path_factory: pytest.TempPathFactory):
    study = fm.virtual_experiment(
        fungi="beta-glucosidase source",
        substrates="cellobiose",
        environments="SABIO-RK Reaction 618 selected assay conditions",
    )
    return study.simulate(
        mode="exploratory",
        n_samples=3,
        seed=11,
        output_dir=tmp_path_factory.mktemp("reaction_618_state_rates"),
        quicklook=False,
    )


def test_reaction_618_product_release_is_the_stoichiometric_multiple_of_degradation(
    reaction_618_result, registry
) -> None:
    template = registry.get_case_template(REACTION_618_TEMPLATE_ID)
    product_yield = float(template.stoichiometric_yields["product"])
    assert product_yield == 2.0, "the template's cellobiose to glucose yield is the property under test"

    rows = reaction_618_result.time_series()
    sample_ids = sorted({row["sample_id"] for row in rows})
    assert len(sample_ids) == 3
    for sample_id in sample_ids:
        degradation = _series(rows, sample_id, "degradation_rate")
        release = _series(rows, sample_id, "product_release_rate")
        process = _series(rows, sample_id, REACTION_618_PROCESS_RATE)
        substrate = _series(rows, sample_id, "cellobiose_concentration")
        assert set(degradation) == set(release) == set(process) == set(substrate)
        assert len(degradation) == int(template.time_grid["points"])
        for index, row in degradation.items():
            assert row["source"] == release[index]["source"] == "simulation_state_rate"
            assert row["state_role"] == release[index]["state_role"] == "derived_rate"
            assert row["notes"] == release[index]["notes"] == ""
            degradation_value = float(row["value"])
            assert degradation_value > 0.0
            assert float(release[index]["value"]) == pytest.approx(product_yield * degradation_value, rel=1e-12)
            # One process consumes one cellobiose per unit rate, so -d[substrate]/dt is that process rate.
            assert degradation_value == pytest.approx(float(process[index]["value"]), rel=1e-12)
            for units in (row["units"], release[index]["units"]):
                assert units == process[index]["units"]
                assert _same_dimensionality(units, "mole / liter / second")
                assert _same_dimensionality(units, f"{substrate[index]['units']} / {row['time_units']}")

    metrics = reaction_618_result.final_metrics()
    for sample_id in sample_ids:
        depletion = _metric(metrics, sample_id, "maximum_substrate_depletion_rate")
        release_metric = _metric(metrics, sample_id, "maximum_product_release_rate")
        assert depletion["status"] == release_metric["status"] == "computed"
        assert float(depletion["value"]) == pytest.approx(
            max(float(row["value"]) for row in _series(rows, sample_id, "degradation_rate").values()), rel=1e-12
        )
        assert float(release_metric["value"]) == pytest.approx(product_yield * float(depletion["value"]), rel=1e-12)
        assert depletion["units"] == release_metric["units"]
        assert _same_dimensionality(depletion["units"], "mole / liter / second")
        assert "cellobiose_concentration" in depletion["notes"]
        assert "beta_D_glucose_concentration" in release_metric["notes"]


def test_reaction_618_sample_bundles_record_state_rates(reaction_618_result) -> None:
    sample = reaction_618_result.screen_result.case_results[0].samples[0]
    state_rate_rows = _csv_rows(Path(sample.output_directory) / "state_rates.csv")
    names = {row["name"] for row in state_rate_rows}
    assert names == {"cellobiose_concentration", "beta_D_glucose_concentration", "beta_glucosidase_concentration"}
    assert {row["kind"] for row in state_rate_rows} == {"state_rate"}
    enzyme = [float(row["value"]) for row in state_rate_rows if row["name"] == "beta_glucosidase_concentration"]
    assert enzyme and all(value == 0.0 for value in enzyme), "the free enzyme is not changed by any process"


@pytest.fixture(scope="module")
def culture_result(tmp_path_factory: pytest.TempPathFactory):
    study = VirtualExperiment.from_registry(
        fungi=[CULTURE_FUNGUS_ID],
        substrates=[CULTURE_SUBSTRATE_ID],
        environments=[CULTURE_ENVIRONMENT_ID],
        registry=REGISTRY_INDEX,
    )
    return study.simulate(
        mode="scientific",
        output_dir=tmp_path_factory.mktemp("culture_state_rates"),
        quicklook=False,
    )


def _fine_grid_cellulose(registry, output_root: Path) -> tuple[np.ndarray, np.ndarray]:
    """Cellulose trajectory of the same scientific case on a refined output grid."""

    config = build_model_config_from_registry_case(
        fungus_id=CULTURE_FUNGUS_ID,
        substrate_id=CULTURE_SUBSTRATE_ID,
        environment_id=CULTURE_ENVIRONMENT_ID,
        registry=registry,
        mode="scientific",
        output_directory=str(output_root / "bundle"),
    )
    data = config.to_dict()
    coarse_points = int(data["time"]["points"])
    data["time"]["points"] = (coarse_points - 1) * FINE_GRID_REFINEMENT + 1
    output_root.mkdir(parents=True, exist_ok=True)
    config_path = output_root / "fine_grid_config.yml"
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    result = run_configured_model(config_path, output_dir=output_root / "bundle")
    time = np.asarray(result.time.to("hour").magnitude, dtype=float)
    cellulose = np.asarray(result.states[CULTURE_SUBSTRATE_STATE].to("gram / liter").magnitude, dtype=float)
    return time, cellulose


def test_culture_depletion_rate_is_the_cellulose_derivative_not_an_enzyme_process_rate(
    culture_result, registry, tmp_path: Path
) -> None:
    template = registry.get_case_template(CULTURE_TEMPLATE_ID)
    assert template.state_roles["substrate"] == CULTURE_SUBSTRATE_STATE
    assert "product" not in template.output_state_roles, "the culture template maps no product state"

    rows = culture_result.time_series()
    (sample_id,) = sorted({row["sample_id"] for row in rows})
    substrate_units = {row["units"] for row in rows if row["state"] == CULTURE_SUBSTRATE_STATE}
    assert substrate_units == {"gram / liter"}
    degradation = _series(rows, sample_id, "degradation_rate")
    assert {row["source"] for row in degradation.values()} == {"simulation_state_rate"}
    (rate_units,) = {row["units"] for row in degradation.values()}
    assert _same_dimensionality(rate_units, "gram / liter / hour")

    depletion = _metric(culture_result.final_metrics(), sample_id, "maximum_substrate_depletion_rate")
    assert depletion["status"] == "computed"
    assert depletion["units"] == rate_units
    assert _same_dimensionality(depletion["units"], "kilogram / meter ** 3 / second")
    assert not _same_dimensionality(depletion["units"], "beta_glucosidase_assay_unit / liter / hour")
    reported_maximum = float(Q_(float(depletion["value"]), depletion["units"]).to("gram / liter / hour").magnitude)

    fine_time, fine_cellulose = _fine_grid_cellulose(registry, tmp_path / "fine_grid")
    finite_difference = -np.gradient(fine_cellulose, fine_time, edge_order=2)[::FINE_GRID_REFINEMENT]
    coarse_time = fine_time[::FINE_GRID_REFINEMENT]
    table_time = np.asarray([float(degradation[index]["time"]) for index in sorted(degradation)], dtype=float)
    np.testing.assert_allclose(coarse_time, table_time, rtol=0.0, atol=1e-9)
    table_rates = np.asarray(
        [
            float(Q_(float(degradation[index]["value"]), rate_units).to("gram / liter / hour").magnitude)
            for index in sorted(degradation)
        ],
        dtype=float,
    )
    tolerance = FINITE_DIFFERENCE_RELATIVE_TOLERANCE * float(np.max(finite_difference))
    np.testing.assert_allclose(table_rates, finite_difference, rtol=0.0, atol=tolerance)
    assert reported_maximum == pytest.approx(float(np.max(finite_difference)), abs=tolerance)
    assert reported_maximum == pytest.approx(float(np.max(table_rates)), rel=1e-12)


def test_culture_product_release_is_not_applicable_without_a_product_role(culture_result) -> None:
    rows = culture_result.time_series()
    release = [row for row in rows if row["state"] == "product_release_rate"]
    assert release, "the not-applicable rows stay visible in the long table"
    assert {(row["value"], row["units"], row["source"]) for row in release} == {
        ("", "not_applicable", "not_applicable")
    }
    assert {row["notes"] for row in release} == {"No product state mapping was available."}
    (sample_id,) = sorted({row["sample_id"] for row in rows})
    metric = _metric(culture_result.final_metrics(), sample_id, "maximum_product_release_rate")
    assert (metric["value"], metric["units"], metric["status"]) == ("", "not_applicable", "not_applicable")
    assert metric["notes"] == "No product state mapping was available."


def _parameter(symbol: str, value: float, units: str) -> Parameter:
    return Parameter(
        name=f"artificial {symbol}",
        symbol=symbol,
        value=value,
        units=units,
        uncertainty=0.0,
        source="Artificial state-rate bookkeeping benchmark value; no physical claim.",
        confidence_level="testing",
        notes="Used only to test state-rate recording.",
        measurement_method="defined benchmark value",
    )


def test_two_process_state_rates_equal_stoichiometry_times_process_rates(tmp_path: Path) -> None:
    """A + B -> 2 C at k1 [A][B] and C -> D at k2 [C]; rates in mM/s, time in minutes."""

    k1, k2 = 0.3, 0.05
    association = MassActionProcess(
        name="artificial A + B -> 2 C",
        reactants={"A": 1.0, "B": 1.0},
        products={"C": 2.0},
        state_units={"A": "millimolar", "B": "millimolar", "C": "millimolar"},
        rate_constant_symbol="k1",
        rate_constant_units="1 / (millimolar * second)",
        rate_units="millimolar / second",
    )
    decay = FirstOrderDecayProcess(
        name="artificial C -> D",
        substrate_state="C",
        product_state="D",
        rate_constant_symbol="k2",
        state_units="millimolar",
        rate_units="millimolar / second",
    )
    model = ModelBuilder(
        process_library=ProcessRegistry([association, decay]),
        requested_processes=("mass_action", "first_order_decay"),
        parameters=ParameterSet(
            [_parameter("k1", k1, "1 / (millimolar * second)"), _parameter("k2", k2, "1 / second")]
        ),
    ).assemble()
    result = ProcessODESolver(model).run(
        RunRequest(
            initial_state={
                "A": Q_(2.0, "millimolar"),
                "B": Q_(1.0, "millimolar"),
                "C": Q_(0.0, "millimolar"),
                "D": Q_(0.0, "millimolar"),
            },
            t_span=(Q_(0.0, "minute"), Q_(0.5, "minute")),
            t_eval=Q_(np.linspace(0.0, 0.5, 11), "minute"),
        )
    )

    states = {name: np.asarray(result.states[name].to("millimolar").magnitude, dtype=float) for name in "ABCD"}
    # Hand-computed process rates (mM/s) at the returned states.
    r1 = k1 * states["A"] * states["B"]
    r2 = k2 * states["C"]
    np.testing.assert_allclose(result.process_rates[association.name].to("millimolar / second").magnitude, r1)
    np.testing.assert_allclose(result.process_rates[decay.name].to("millimolar / second").magnitude, r2)
    # S (states x processes) per unit rate; rows A, B, C, D; columns association, decay.
    stoichiometry = np.array([[-1.0, 0.0], [-1.0, 0.0], [2.0, -1.0], [0.0, 1.0]])
    seconds_per_minute = 60.0
    expected = seconds_per_minute * stoichiometry @ np.vstack([r1, r2])

    assert set(result.state_rates) == {"A", "B", "C", "D"}
    for row, name in enumerate("ABCD"):
        recorded = result.state_rates[name]
        assert str(recorded.units) == "millimolar / minute"
        np.testing.assert_allclose(recorded.magnitude, expected[row], rtol=1e-12, atol=1e-15)
    assert np.all(expected[0] < 0.0) and np.all(expected[3][1:] > 0.0)

    record = result.to_dict()
    assert record["state_rates"]["C"]["units"] == "millimolar / minute"
    np.testing.assert_allclose(record["state_rates"]["C"]["value"], expected[2], rtol=1e-12, atol=1e-15)

    result.save(tmp_path / "bundle")
    saved = _csv_rows(tmp_path / "bundle" / "state_rates.csv")
    assert {row["kind"] for row in saved} == {"state_rate"}
    saved_d = [float(row["value"]) for row in saved if row["name"] == "D"]
    np.testing.assert_allclose(saved_d, expected[3], rtol=1e-12, atol=1e-15)
    assert {row["units"] for row in saved if row["name"] == "D"} == {"millimolar / minute"}


def test_bundle_without_state_rates_reports_rates_as_not_applicable(tmp_path: Path) -> None:
    study = fm.virtual_experiment(
        fungi="beta-glucosidase source",
        substrates="cellobiose",
        environments="SABIO-RK Reaction 618 selected assay conditions",
    )
    result = study.simulate(
        mode="exploratory",
        n_samples=1,
        seed=3,
        output_dir=tmp_path / "legacy_bundle",
        quicklook=False,
    )
    sample_dir = Path(result.screen_result.case_results[0].samples[0].output_directory)
    assert (sample_dir / "process_rates.csv").exists()
    (sample_dir / "state_rates.csv").unlink()

    result.write_tables()

    rows = result.time_series()
    rate_rows = [row for row in rows if row["state"] in {"degradation_rate", "product_release_rate"}]
    assert rate_rows
    assert {(row["value"], row["units"], row["source"], row["notes"]) for row in rate_rows} == {
        ("", "not_applicable", "not_applicable", NO_STATE_RATE_REASON)
    }
    # Process rates are still copied with their identity, but never stand in for state rates.
    assert any(row["state"] == REACTION_618_PROCESS_RATE and row["value"] for row in rows)
    metrics = {row["metric"]: row for row in result.final_metrics()}
    for name in ("maximum_product_release_rate", "maximum_substrate_depletion_rate"):
        assert (metrics[name]["value"], metrics[name]["units"], metrics[name]["status"]) == (
            "",
            "not_applicable",
            "not_applicable",
        )
        assert metrics[name]["notes"] == NO_STATE_RATE_REASON
    assert metrics["final_substrate_remaining"]["status"] == "computed"
    summary_metrics = {row["metric"] for row in _csv_rows(Path(result.output_directory) / "summary_metrics.csv")}
    assert not summary_metrics.intersection({"maximum_product_release_rate", "maximum_substrate_depletion_rate"})
