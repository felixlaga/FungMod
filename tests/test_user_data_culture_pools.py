"""A growing culture whose secreted pools act together on its substrate (CULTURE-002).

``culture.csv`` (USERDATA-009) bound the registry's ``culture_physiology``
composition with exactly one consuming pool. Now every culture pool whose class
acts on the culture substrate consumes it, each by its own existing
homogeneous Michaelis-Menten law ``k_h E S / (K_h + S)`` with its own
``hydrolysis_capacity`` and ``hydrolysis_half_saturation``; the processes add
their rates on the shared substrate (the enzyme network's additive, independent
action) and every consumed gram feeds growth through the culture's one yield,
the rest going to the closure ledger. Every pool is induced by the substrate
with the one shared constant and lost at its own rate. No new numerics; one
consuming pool keeps every USERDATA-009 identifier (the existing culture
fixtures and the shipped *T. harzianum* case stay pinned by
``tests/test_user_data_culture.py`` and ``tests/test_user_data_network_cross_basis.py``).

Released soluble pools are not part of a culture: the core has no uptake law
for a soluble pool with an explicit yield that a user table binds, so a culture
stays refused in an ``enzyme_network`` dataset, with that reason.

``tests/fixtures/user_data/culture_parallel_pools`` is one user-defined strain
whose endo- and exo-cutter-like pools consume a cellulose-like solid in parallel
while a third pool acts on nothing in the culture. ``tests/fixtures/user_data/
culture_shared_pools`` is the materially different case: two strains share one
culture model on a chitin-like solid, the second states its capacities as ranges
(sampled) and lists its pools in the other order, and a second condition is all
gaps. Every value is an illustrative estimate.
"""

from __future__ import annotations

import csv
import io
import json
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from fungal_model import UserDataError, UserDataset, load_user_dataset, virtual_experiment
from fungal_model.api import VirtualExperimentError
from fungal_model.api.user_data import CULTURE_TABLE, USER_DATASET_CULTURE_PROCESS_TYPE, USER_DATASET_MATURITY_GAP
from fungal_model.cli import EXIT_OK, EXIT_USAGE, main
from fungal_model.registry import load_registry

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"
FIXTURES = ROOT / "tests" / "fixtures" / "user_data"
PARALLEL = FIXTURES / "culture_parallel_pools"
SHARED = FIXTURES / "culture_shared_pools"
ESTIMATES = FIXTURES / "culture_estimates"

PARALLEL_ID = "culture_parallel_pools"
ENDO = "endo_cutter_g5_like"
EXO = "exo_cutter_g5_like"
DIMER = "dimer_hydrolase_g5_like"
PARALLEL_ENVIRONMENT = f"{PARALLEL_ID}__c28_ph5"
SHARED_ID = "culture_shared_pools"
K_ENDO = "endo_cleaver_k_like"
K_EXO = "exo_cleaver_k_like"

# The parallel fixture's constants (g/L, g/g, 1/h, g/(mg h), mg/L, mg/(g h)); every one an illustrative estimate.
S0, X0, YIELD, LOSS, K_IND = 12.0, 0.15, 0.4, 0.005, 0.8
CONSUMERS = {ENDO: (0.004, 6.0), EXO: (0.006, 10.0)}  # hydrolysis_capacity, hydrolysis_half_saturation
POOLS = {ENDO: (0.5, 1.5, 0.015), EXO: (0.3, 1.0, 0.01), DIMER: (0.2, 0.3, 0.02)}  # initial, production, loss
POOL_ROLES = {ENDO: "enzyme", EXO: f"enzyme_{EXO}", DIMER: f"enzyme_{DIMER}"}

CULTURE_HEADER = (
    "strain_id",
    "substrate_id",
    "condition_id",
    "quantity",
    "enzyme_class",
    "value",
    "lower",
    "upper",
    "units",
    "evidence_type",
    "method",
    "source",
)


# ---------------------------------------------------------------------------
# Helpers


def _copy_fixture(tmp_path: Path, source: Path, *, edits: Mapping[str, str | None] | None = None) -> Path:
    target = tmp_path / source.name
    shutil.copytree(source, target)
    for name, text in (edits or {}).items():
        path = target / name
        if text is None:
            path.unlink()
        else:
            path.write_text(text, encoding="utf-8")
    return target


def _load(tmp_path: Path, source: Path, edits: Mapping[str, str | None]) -> UserDataset:
    return load_user_dataset(_copy_fixture(tmp_path, source, edits=edits), registry=REGISTRY_INDEX)


def _issues(tmp_path: Path, source: Path, edits: Mapping[str, str | None]) -> list[dict[str, Any]]:
    with pytest.raises(UserDataError) as excinfo:
        _load(tmp_path, source, edits)
    return excinfo.value.issues


def _has_issue(issues: Sequence[Mapping[str, Any]], file: str, row: int | None, column: str | None, text: str) -> bool:
    return any(
        issue["file"] == file and issue["row"] == row and issue["column"] == column and text in issue["message"]
        for issue in issues
    )


def _rows(source: Path, name: str) -> list[dict[str, str]]:
    with (source / name).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _csv_text(rows: Sequence[Mapping[str, str]], columns: Sequence[str]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(columns), restval="", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def _culture(
    source: Path,
    *,
    drop: Sequence[tuple[str, str]] = (),
    change: Mapping[tuple[str, str], Mapping[str, str]] | None = None,
    add: Sequence[Mapping[str, str]] = (),
) -> str:
    """The fixture's culture.csv with (quantity, pool) rows dropped or changed and rows added."""

    rows = []
    for row in _rows(source, CULTURE_TABLE):
        key = (row["quantity"], row["enzyme_class"])
        if key in drop:
            continue
        rows.append({**row, **(change or {}).get(key, {})})
    rows.extend({**{column: "" for column in CULTURE_HEADER}, **extra} for extra in add)
    return _csv_text(rows, CULTURE_HEADER)


def _line(source: Path, quantity: str, pool: str = "") -> int:
    for index, row in enumerate(_rows(source, CULTURE_TABLE), start=2):
        if (row["quantity"], row["enzyme_class"]) == (quantity, pool):
            return index
    raise AssertionError((quantity, pool))


def _series(result: Any, sample: str = "0") -> dict[tuple[str, str], tuple[np.ndarray, np.ndarray, str]]:
    """(environment id, state role or rate key) -> (times, values, units) of one sample."""

    series: dict[tuple[str, str], list[tuple[float, float, str]]] = {}
    for row in result.time_series():
        if row["sample_index"] != sample or row["value"] == "":
            continue
        if row["source"] == "simulation_state":
            key = row["state_role"]
        elif row["source"] in {"simulation_process_rate", "simulation_state_rate"}:
            key = row["state"]
        else:
            continue
        series.setdefault((row["environment_id"], key), []).append((float(row["time"]), float(row["value"]), row["units"]))
    return {
        key: (np.array([item[0] for item in items]), np.array([item[1] for item in items]), items[0][2])
        for key, items in series.items()
    }


def _per_hour(values: np.ndarray, units: str) -> np.ndarray:
    """A rate series in its pool's units per hour (first-order process rates are written per second)."""

    return values * 3600.0 if units.endswith("/ second") else values


def _simulate(tmp_path: Path, user_data: Path | UserDataset, *, fungus: str, substrate: str, environments: Any, **kwargs: Any) -> Any:
    study = virtual_experiment(
        fungi=[fungus], substrates=[substrate], environments=environments, registry=REGISTRY_INDEX, user_data=user_data
    )
    options: dict[str, Any] = {"mode": "exploratory", "n_samples": 1, "seed": 1, "quicklook": False}
    options.update(kwargs)
    return study.simulate(output_dir=tmp_path, **options)


def _cli(capsys: pytest.CaptureFixture[str], *args: str | Path) -> tuple[int, str, str]:
    code = main([str(arg) for arg in args])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _records(dataset: UserDataset) -> dict[str, Mapping[str, Any]]:
    return {str(item["record_id"]): item for item in dataset.records["parameter_records"]}


@pytest.fixture(scope="module")
def parallel() -> UserDataset:
    return load_user_dataset(PARALLEL, registry=REGISTRY_INDEX)


@pytest.fixture(scope="module")
def parallel_run(tmp_path_factory: pytest.TempPathFactory) -> Any:
    return _simulate(
        tmp_path_factory.mktemp("culture_parallel"), PARALLEL, fungus="strain_g5", substrate="solid_g5", environments=["c28_ph5"]
    )


# ---------------------------------------------------------------------------
# What a culture with several consuming pools generates


def test_every_pool_acting_on_the_substrate_consumes_it(parallel: UserDataset) -> None:
    (culture,) = parallel.cultures
    assert culture["enzyme_class"] == ENDO, "the first consuming pool in culture.csv names the model"
    assert culture["consuming_pools"] == [ENDO, EXO]
    assert culture["enzyme_pools"] == [ENDO, EXO, DIMER]
    template_id = f"{PARALLEL_ID}__{ENDO}__solid_g5__culture_template"
    assert culture["case_template_id"] == template_id
    compatibilities = {item["record_id"]: item for item in parallel.records["process_compatibility"]}
    assert culture["process_compatibility_ids"] == list(compatibilities) == [
        f"{PARALLEL_ID}__{ENDO}__solid_g5__culture_physiology",
        f"{PARALLEL_ID}__{EXO}__solid_g5__culture_physiology",
    ]
    # One compatibility per consuming class, all pointing to the one template with the same roles.
    assert {item["case_template_id"] for item in compatibilities.values()} == {template_id}
    assert [item["enzyme_class"] for item in compatibilities.values()] == [f"{PARALLEL_ID}__{ENDO}", f"{PARALLEL_ID}__{EXO}"]
    (roles,) = {tuple(item["parameter_roles"]) for item in compatibilities.values()}
    assert roles[:9] == (
        "initial_substrate",
        "initial_biomass",
        "biomass_yield",
        "biomass_loss_rate",
        "induction_half_saturation",
        f"hydrolysis_capacity__{ENDO}",
        f"hydrolysis_half_saturation__{ENDO}",
        f"hydrolysis_capacity__{EXO}",
        f"hydrolysis_half_saturation__{EXO}",
    )
    (template,) = parallel.records["case_templates"]
    processes = {item["id"]: item for item in template["process_state_metadata"]["process_templates"]}
    assert list(processes) == [
        f"substrate_consumption__{ENDO}",
        f"substrate_consumption__{EXO}",
        "biomass_loss",
        *(f"enzyme_{kind}__{pool}" for pool in (ENDO, EXO, DIMER) for kind in ("synthesis", "loss")),
    ]
    for pool in (ENDO, EXO):
        consumption = processes[f"substrate_consumption__{pool}"]
        assert consumption["process_type"] == "homogeneous_michaelis_menten"
        assert consumption["state_roles"] == {"substrate": "substrate", "enzyme": POOL_ROLES[pool], "product": "biomass"}
        assert consumption["parameter_roles"] == {
            "kcat": f"hydrolysis_capacity__{pool}",
            "km": f"hydrolysis_half_saturation__{pool}",
        }
        # One product map for every consuming pool: the culture's one yield and its closure ledger.
        assert consumption["product_map"] == f"{PARALLEL_ID}__{ENDO}__solid_g5__biomass_yield_map"
    assert processes[f"enzyme_synthesis__{DIMER}"]["state_roles"] == {
        "producer": "biomass",
        "inducer": "substrate",
        "product": f"enzyme_{DIMER}",
    }
    assert processes[f"enzyme_synthesis__{DIMER}"]["parameter_roles"]["induction_half_saturation"] == (
        "induction_half_saturation"
    )
    limitations = " ".join(template["limitations"])
    assert "substrate consumption by several enzyme pools in parallel" in limitations
    assert "their consumption rates add, with no competition for substrate or adsorption sites, no synergy" in limitations
    assert "The other pools (Dimer hydrolase-like pool G5) are produced and lost only" in limitations
    assert "FungMod has no uptake law for a soluble pool with an explicit yield" in limitations
    assert "All pools share one induction half-saturation constant." in limitations
    classes = {item["record_id"]: item["compatible_processes"] for item in parallel.records["enzyme_classes"]}
    assert classes[f"{PARALLEL_ID}__{ENDO}"] == classes[f"{PARALLEL_ID}__{EXO}"] == [USER_DATASET_CULTURE_PROCESS_TYPE]


def test_records_are_per_consuming_pool_and_selected_by_every_compatibility(parallel: UserDataset) -> None:
    records = _records(parallel)
    prefix = f"{PARALLEL_ID}__strain_g5__solid_g5__c28_ph5__culture__"
    capacity = records[f"{prefix}hydrolysis_capacity__{EXO}"]
    assert capacity["parameter_symbol"] == f"{PARALLEL_ID}__culture__hydrolysis_capacity__{EXO}__{ENDO}__solid_g5"
    assert (capacity["value"]["value"], capacity["value"]["units"]) == (0.006, "g/mg/h")
    assert capacity["provenance"]["fungmod_user_dataset"]["enzyme_pool"] == f"{PARALLEL_ID}__{EXO}"
    assert capacity["provenance"]["fungmod_user_dataset"]["row"] == _line(PARALLEL, "hydrolysis_capacity", EXO)
    # The enzyme-class selector is empty, so the compatibility of either consuming class selects the records.
    assert {item["enzyme_class"] for item in records.values()} == {None}
    assert len(records) == 5 + 2 * 2 + 3 * 3
    assert records[f"{prefix}biomass_yield"]["parameter_symbol"] == f"{PARALLEL_ID}__culture__biomass_yield__{ENDO}__solid_g5"
    study = virtual_experiment(
        fungi=["strain_g5"], substrates=["solid_g5"], environments=["c28_ph5"], registry=REGISTRY_INDEX, user_data=parallel
    )
    (report,) = study.preflight(mode="exploratory")
    assert report.status == "modelable", report.to_dict()
    assert report.required_processes == (USER_DATASET_CULTURE_PROCESS_TYPE,)


# ---------------------------------------------------------------------------
# Analytic checks on the simulated culture


def test_the_parallel_culture_closes_and_grows_through_one_yield(parallel_run: Any) -> None:
    series = _series(parallel_run)
    times, substrate, substrate_units = series[(PARALLEL_ENVIRONMENT, "substrate")]
    biomass = series[(PARALLEL_ENVIRONMENT, "biomass")][1]
    unassimilated = series[(PARALLEL_ENVIRONMENT, "ledger_unassimilated_substrate")][1]
    lost = series[(PARALLEL_ENVIRONMENT, "ledger_biomass_loss")][1]
    assert substrate_units == "gram / liter" and times[-1] == 144.0
    assert substrate[0] == S0 and substrate[-1] < 0.01 * S0
    consumed = S0 - substrate
    # The dry-mass closure, growth equal to the yield times the consumed substrate, and the ledger, at every time.
    np.testing.assert_allclose(substrate + biomass + unassimilated + lost, S0 + X0, rtol=1e-9)
    np.testing.assert_allclose(biomass - X0 + lost, YIELD * consumed, rtol=1e-9, atol=1e-12)
    np.testing.assert_allclose(unassimilated, (1.0 - YIELD) * consumed, rtol=1e-9, atol=1e-12)
    pools = {pool: series[(PARALLEL_ENVIRONMENT, role)] for pool, role in POOL_ROLES.items()}
    assert {pool: units for pool, (_t, _v, units) in pools.items()} == dict.fromkeys(POOLS, "milligram / liter")
    total = np.zeros_like(substrate)
    for pool, (capacity, half_saturation) in CONSUMERS.items():
        rate, units = series[(PARALLEL_ENVIRONMENT, f"process_rate.substrate_consumption__{pool}")][1:]
        assert units == "gram / hour / liter"
        np.testing.assert_allclose(
            rate, capacity * pools[pool][1] * substrate / (half_saturation + substrate), rtol=1e-9, atol=1e-15
        )
        total = total + rate
    # The consuming pools add their rates on the one substrate.
    np.testing.assert_allclose(series[(PARALLEL_ENVIRONMENT, "degradation_rate")][1], total, rtol=1e-9, atol=1e-15)
    for pool, (initial, production, loss) in POOLS.items():
        assert pools[pool][1][0] == pytest.approx(initial, rel=1e-12)
        synthesis, units = series[(PARALLEL_ENVIRONMENT, f"process_rate.enzyme_synthesis__{pool}")][1:]
        np.testing.assert_allclose(
            _per_hour(synthesis, units), production * biomass * substrate / (K_IND + substrate), rtol=1e-9, atol=1e-15
        )
        decay, units = series[(PARALLEL_ENVIRONMENT, f"process_rate.enzyme_loss__{pool}")][1:]
        np.testing.assert_allclose(_per_hour(decay, units), loss * pools[pool][1], rtol=1e-9, atol=1e-15)
    decay, units = series[(PARALLEL_ENVIRONMENT, "process_rate.biomass_loss")][1:]
    np.testing.assert_allclose(_per_hour(decay, units), LOSS * biomass, rtol=1e-9, atol=1e-15)


def test_the_parallel_culture_reports_rates_thresholds_and_the_ledger(parallel_run: Any) -> None:
    thresholds = {row["metric"]: float(row["value"]) for row in parallel_run.threshold_times()}
    assert thresholds["time_to_10_percent_substrate_degradation"] < thresholds["time_to_50_percent_substrate_degradation"]
    assert thresholds["time_to_50_percent_substrate_degradation"] == pytest.approx(78.70, abs=0.01)
    output = Path(parallel_run.output_directory)
    with (output / "conservation_diagnostics.csv").open(encoding="utf-8", newline="") as handle:
        (row,) = list(csv.DictReader(handle))
    assert row["validator_id"] == "dry_mass_closure_ledger" and row["status"] == "evaluated"
    assert float(row["relative_max_absolute_drift"]) < 1e-9
    (mechanism,) = [item for item in parallel_run.mechanism_summary() if item["mechanism_id"] == "culture_physiology"]
    assert mechanism["maturity"] == "software_tested_exploratory_parameterized"


def test_a_second_pool_without_capacity_reproduces_the_one_pool_culture(tmp_path: Path) -> None:
    """The one-pool culture (USERDATA-009) is the limit of two consuming pools when the second consumes nothing."""

    classes = (ESTIMATES / "enzyme_classes.csv").read_text(encoding="utf-8") + (
        "second_cutter_x_like,Second cutter-like pool X1,,beta_1_4_xylosidic,xylan_like_solid,Illustrative test class\n"
    )
    enzymes = (ESTIMATES / "enzymes.csv").read_text(encoding="utf-8") + (
        "strain_x1,second_cutter_x_like,assumed secreted activity (illustrative),Illustrative test note IT-9 p. 4\n"
    )
    second = [
        ("hydrolysis_capacity", "0", "g/mg/h"),
        ("hydrolysis_half_saturation", "5", "g/L"),
        ("initial_enzyme_concentration", "1", "mg/L"),
        ("specific_production_rate", "2", "mg/g/h"),
        ("enzyme_loss_rate", "0.05", "1/h"),
    ]
    culture = _culture(
        ESTIMATES,
        add=[
            {
                "strain_id": "strain_x1",
                "substrate_id": "xylan_lot_x1",
                "condition_id": "c25",
                "quantity": quantity,
                "enzyme_class": "second_cutter_x_like",
                "value": value,
                "units": units,
                "evidence_type": "estimate",
                "method": "illustrative estimate",
                "source": "Illustrative test note IT-9 p. 4",
            }
            for quantity, value, units in second
        ],
    )
    dataset = _load(
        tmp_path / "data", ESTIMATES, {"enzyme_classes.csv": classes, "enzymes.csv": enzymes, CULTURE_TABLE: culture}
    )
    assert dataset.cultures[0]["consuming_pools"] == ["endo_xylanase_like", "second_cutter_x_like"]
    kwargs = {"fungus": "strain_x1", "substrate": "xylan_lot_x1", "environments": ["c25"]}
    one = _series(_simulate(tmp_path / "one", ESTIMATES, **kwargs))
    two = _series(_simulate(tmp_path / "two", dataset, **kwargs))
    environment = "culture_estimates__c25"
    for role in ("substrate", "biomass", "enzyme", "ledger_unassimilated_substrate", "ledger_biomass_loss"):
        times, expected, units = one[(environment, role)]
        other_times, actual, other_units = two[(environment, role)]
        assert units == other_units
        np.testing.assert_allclose(other_times, times)
        # Two systems of different size integrate to the solver's tolerance, not to the last digit.
        np.testing.assert_allclose(actual, expected, rtol=1e-6, atol=1e-7 * 15.0)
    assert np.all(two[(environment, "process_rate.substrate_consumption__second_cutter_x_like")][1] == 0.0)


# ---------------------------------------------------------------------------
# The materially different case: two strains, ranges, a gap condition


def test_two_strains_share_one_model_whatever_order_they_list_its_pools(tmp_path: Path) -> None:
    dataset = load_user_dataset(SHARED, registry=REGISTRY_INDEX)
    entries = {item["strain_id"]: item for item in dataset.cultures}
    assert set(entries) == {"strain_k6", "strain_k7"}
    for entry in entries.values():
        assert entry["enzyme_class"] == K_ENDO
        assert entry["consuming_pools"] == entry["enzyme_pools"] == [K_ENDO, K_EXO]
    assert entries["strain_k7"]["rows"] == list(range(17, 32))
    assert len(dataset.records["case_templates"]) == 1
    records = _records(dataset)
    capacity = records[f"{SHARED_ID}__strain_k7__solid_k6__c30_ph6__culture__hydrolysis_capacity__{K_EXO}"]
    assert capacity["value"] == {**capacity["value"], "kind": "range", "lower": 0.0015, "upper": 0.0025}
    assert capacity["range_scope"] == "user_supplied_range"
    gaps = [item for item in records.values() if item["maturity"] == USER_DATASET_MATURITY_GAP]
    assert len(gaps) == 2 * (5 + 2 * 2 + 2 * 3), "every role of both strains at the condition without rows"
    request = records[f"{SHARED_ID}__strain_k6__solid_k6__c37_ph6__culture__hydrolysis_capacity__{K_EXO}__gap"][
        "provenance"
    ]["measurement_request"]
    assert request.startswith(
        "Measure the Chitin-like solid K6 consumption capacity of Exo-cleaver-like pool K from Illustrative culture "
        "strain K6 at condition c37_ph6 (37 degC, pH 6.0)"
    )
    study = virtual_experiment(
        fungi=["strain_k6"], substrates=["solid_k6"], environments=["c37_ph6"], registry=REGISTRY_INDEX, user_data=dataset
    )
    (report,) = study.preflight(mode="exploratory")
    assert report.status == "underparameterized"
    assert request in report.suggested_experiments


@pytest.mark.parametrize("strain", ["strain_k6", "strain_k7"])
def test_each_sample_of_each_strain_closes_and_follows_its_own_laws(tmp_path: Path, strain: str) -> None:
    result = _simulate(
        tmp_path, SHARED, fungus=strain, substrate="solid_k6", environments=["c30_ph6"], n_samples=3, seed=5
    )
    sampled: dict[str, dict[str, float]] = {}
    for row in result.sampled_parameters():
        sampled.setdefault(str(row["sample_index"]), {})[str(row["symbol"])] = float(row["sampled_value"])
    environment = f"{SHARED_ID}__c30_ph6"
    yield_value = 0.3 if strain == "strain_k6" else 0.25
    capacities = []
    for sample in ("0", "1", "2"):
        series = _series(result, sample)
        substrate = series[(environment, "substrate")][1]
        biomass = series[(environment, "biomass")][1]
        unassimilated = series[(environment, "ledger_unassimilated_substrate")][1]
        lost = series[(environment, "ledger_biomass_loss")][1]
        np.testing.assert_allclose(substrate + biomass + unassimilated + lost, 8.1, rtol=1e-9)
        np.testing.assert_allclose(biomass - 0.1 + lost, yield_value * (8.0 - substrate), rtol=1e-9, atol=1e-12)
        values = sampled[sample]
        total = np.zeros_like(substrate)
        for pool, role, half_saturation in ((K_ENDO, "enzyme", 4.0), (K_EXO, f"enzyme_{K_EXO}", 2.0)):
            symbol = f"{SHARED_ID}__culture__hydrolysis_capacity__{pool}__{K_ENDO}__solid_k6"
            capacity = values[symbol]
            capacities.append(capacity)
            rate = series[(environment, f"process_rate.substrate_consumption__{pool}")][1]
            pool_state = series[(environment, role)][1]
            np.testing.assert_allclose(
                rate, capacity * pool_state * substrate / (half_saturation + substrate), rtol=1e-9, atol=1e-15
            )
            total = total + rate
        np.testing.assert_allclose(series[(environment, "degradation_rate")][1], total, rtol=1e-9, atol=1e-15)
    if strain == "strain_k6":
        assert set(capacities) == {0.003, 0.002}
    else:
        assert len(set(capacities)) == 6, "both capacity ranges are sampled"
        assert all(0.0015 <= value <= 0.004 for value in capacities)


def test_another_solid_of_the_consumers_is_a_culture_of_gaps_with_both(tmp_path: Path) -> None:
    classes = (
        (PARALLEL / "enzyme_classes.csv")
        .read_text(encoding="utf-8")
        .replace(",glycosidic_like_bond,glucan_like_solid,", ",glycosidic_like_bond,glucan_like_solid;glucan_like_film,")
    )
    substrates = (PARALLEL / "substrates.csv").read_text(encoding="utf-8") + (
        "film_g5,,Glucan-like film G5,glucan_like_film,solid_polymer,glycosidic_like_bond,dry_mass,solubilized_mass_f5,"
        "1,g/g,Illustrative test note CG-5 p. 6\n"
    )
    dataset = _load(tmp_path, PARALLEL, {"enzyme_classes.csv": classes, "substrates.csv": substrates})
    entries = {item["substrate_id"]: item for item in dataset.cultures}
    assert entries["film_g5"]["consuming_pools"] == entries["film_g5"]["enzyme_pools"] == [ENDO, EXO]
    assert entries["film_g5"]["rows"] == []
    assert {item["record_id"] for item in dataset.records["process_compatibility"]} == {
        f"{PARALLEL_ID}__{pool}__{substrate}__culture_physiology" for pool in (ENDO, EXO) for substrate in ("solid_g5", "film_g5")
    }
    study = virtual_experiment(
        fungi=["strain_g5"], substrates=["film_g5"], environments=["c28_ph5"], registry=REGISTRY_INDEX, user_data=dataset
    )
    (report,) = study.preflight(mode="exploratory")
    assert report.status == "underparameterized"
    assert sum("consumption capacity" in text for text in report.suggested_experiments) == 2


def test_measured_rows_make_the_culture_scientific_until_one_is_an_estimate(tmp_path: Path) -> None:
    culture = _culture(PARALLEL).replace(",estimate,illustrative estimate,", ",measured,illustrative measurement for the test,")
    dataset = _load(tmp_path / "measured", PARALLEL, {CULTURE_TABLE: culture})
    assert dataset.records["case_templates"][0]["process_state_metadata"]["config_mode"] == "scientific"
    study = virtual_experiment(
        fungi=["strain_g5"], substrates=["solid_g5"], environments=["c28_ph5"], registry=REGISTRY_INDEX, user_data=dataset
    )
    (report,) = study.preflight(mode="scientific")
    assert report.status == "modelable", report.to_dict()
    study.simulate(mode="scientific", output_dir=tmp_path / "scientific", quicklook=False)
    manifest = json.loads((tmp_path / "scientific" / "output_manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_label"] == "scientific_exact_unvalidated"
    weak = culture.replace(
        f"hydrolysis_half_saturation,{EXO},10,,,g/L,measured,illustrative measurement for the test,",
        f"hydrolysis_half_saturation,{EXO},10,,,g/L,estimate,illustrative estimate,",
    )
    assert weak != culture
    weak_dataset = _load(tmp_path / "weak", PARALLEL, {CULTURE_TABLE: weak})
    assert weak_dataset.records["case_templates"][0]["process_state_metadata"]["config_mode"] == "exploratory"
    weak_study = virtual_experiment(
        fungi=["strain_g5"], substrates=["solid_g5"], environments=["c28_ph5"], registry=REGISTRY_INDEX, user_data=weak_dataset
    )
    with pytest.raises(VirtualExperimentError, match="Scientific simulation requires"):
        weak_study.simulate(mode="scientific", output_dir=tmp_path / "blocked", quicklook=False)


# ---------------------------------------------------------------------------
# Refusals


def test_a_culture_is_not_combined_with_released_pools(tmp_path: Path) -> None:
    manifest = yaml.safe_load((PARALLEL / "user_dataset.yml").read_text(encoding="utf-8"))
    manifest["enzyme_network"] = {"entry_substrates": ["solid_g5"]}
    issues = _issues(tmp_path, PARALLEL, {"user_dataset.yml": yaml.safe_dump(manifest, sort_keys=False)})
    assert _has_issue(issues, CULTURE_TABLE, None, None, "culture.csv is not combined with enzyme_network")
    assert _has_issue(
        issues, CULTURE_TABLE, None, None, "FungMod has no uptake law for a released soluble pool with an explicit yield"
    )


def test_a_consuming_pool_takes_its_constants_from_culture_csv_only(tmp_path: Path) -> None:
    """One process, one law: kinetics.csv rows of a consuming pool are refused, whichever consumer it is."""

    kinetics = (PARALLEL / "kinetics.csv").read_text(encoding="utf-8") + (
        f"strain_g5,{EXO},solid_g5,c28_ph5,km,10,,,g/L,estimate,illustrative estimate,Illustrative test note CG-5 p. 7\n"
    )
    issues = _issues(tmp_path, PARALLEL, {"kinetics.csv": kinetics})
    assert _has_issue(issues, "kinetics.csv", 2, "substrate_id", "Strain 'strain_g5' has a culture on substrate 'solid_g5'")


def test_every_strain_running_the_model_declares_all_its_pools(tmp_path: Path) -> None:
    strains = (PARALLEL / "strains.csv").read_text(encoding="utf-8") + "strain_g6,Illustrative culture strain G6,,\n"
    # A strain that declares only the second consuming pool still runs the model, through that pool.
    enzymes = (PARALLEL / "enzymes.csv").read_text(encoding="utf-8") + (
        f"strain_g6,{EXO},assumed secreted activity (illustrative),Illustrative test note CG-6 p. 1\n"
    )
    issues = _issues(tmp_path, PARALLEL, {"strains.csv": strains, "enzymes.csv": enzymes})
    assert _has_issue(
        issues,
        CULTURE_TABLE,
        _line(PARALLEL, "hydrolysis_capacity", ENDO),
        "enzyme_class",
        f"strain 'strain_g6' declares '{EXO}' (enzymes.csv row 5) but not '{ENDO}'",
    ), issues
    assert _has_issue(
        issues,
        CULTURE_TABLE,
        _line(PARALLEL, "initial_enzyme_concentration", DIMER),
        "enzyme_class",
        f"strain 'strain_g6' declares '{EXO}' (enzymes.csv row 5) but not '{DIMER}'",
    ), issues


def test_another_class_acting_on_the_substrate_must_be_a_culture_pool(tmp_path: Path) -> None:
    classes = (PARALLEL / "enzyme_classes.csv").read_text(encoding="utf-8") + (
        "third_cutter_g5_like,Third cutter-like pool G5,,glycosidic_like_bond,glucan_like_solid,Illustrative test class\n"
    )
    enzymes = (PARALLEL / "enzymes.csv").read_text(encoding="utf-8") + (
        "strain_g5,third_cutter_g5_like,assumed secreted activity (illustrative),Illustrative test note CG-5 p. 8\n"
    )
    issues = _issues(tmp_path, PARALLEL, {"enzyme_classes.csv": classes, "enzymes.csv": enzymes})
    assert _has_issue(
        issues,
        "enzymes.csv",
        5,
        "enzyme_class",
        "To make 'third_cutter_g5_like' a consuming pool of the culture, give its rows in culture.csv",
    ), issues


_CONSUMER_QUANTITIES = (
    "hydrolysis_capacity",
    "hydrolysis_half_saturation",
    "initial_enzyme_concentration",
    "specific_production_rate",
    "enzyme_loss_rate",
)


@pytest.mark.parametrize(
    ("drop", "change", "line", "column", "message"),
    [
        pytest.param(
            (),
            {("hydrolysis_capacity", ENDO): {"enzyme_class": DIMER}},
            7,
            "enzyme_class",
            f"belongs to a pool that consumes the substrate ('{ENDO}', '{EXO}' in the culture of strain 'strain_g5'",
            id="consumption_on_a_pool_that_consumes_nothing",
        ),
        pytest.param(
            tuple((quantity, pool) for pool in (ENDO, EXO) for quantity in _CONSUMER_QUANTITIES),
            {},
            2,
            "enzyme_class",
            "consumes its substrate through at least one enzyme pool",
            id="no_consuming_pool",
        ),
        pytest.param(
            (),
            {("hydrolysis_capacity", EXO): {"units": "g/(FPU*h)"}},
            12,
            "units",
            f"do not fit the consuming pool '{EXO}'",
            id="units_of_one_consumer_checked_with_its_own_pool",
        ),
    ],
)
def test_culture_pool_refusals(
    tmp_path: Path,
    drop: tuple[tuple[str, str], ...],
    change: Mapping[tuple[str, str], Mapping[str, str]],
    line: int,
    column: str,
    message: str,
) -> None:
    issues = _issues(tmp_path, PARALLEL, {CULTURE_TABLE: _culture(PARALLEL, drop=drop, change=change)})
    assert _has_issue(issues, CULTURE_TABLE, line, column, message), issues


def test_response_laws_stay_refused_on_every_consuming_pool(tmp_path: Path) -> None:
    responses = (
        "strain_id,enzyme_class,substrate_id,law,parameter,value,units,evidence_type,method,source\n"
        f"strain_g5,{EXO},solid_g5,temperature_arrhenius_reference,activation_energy,50,kJ/mol,estimate,,CG-5\n"
        f"strain_g5,{EXO},solid_g5,temperature_arrhenius_reference,reference_temperature,28,degC,estimate,,CG-5\n"
    )
    issues = _issues(tmp_path, PARALLEL, {"responses.csv": responses})
    for row in (2, 3):
        assert _has_issue(issues, "responses.csv", row, "law", "response laws are not bound to culture cases"), issues


# ---------------------------------------------------------------------------
# Command line


def test_check_data_lists_the_consuming_pools(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = _cli(capsys, "check-data", PARALLEL, "--registry", REGISTRY_INDEX)
    assert code == EXIT_OK, err
    assert "Kinetic values: 18; gaps: 0" in out
    assert "strain     substrate  consuming pools                          enzyme pools" in out
    assert f"strain_g5  solid_g5   {ENDO}, {EXO}  {ENDO}, {EXO}, {DIMER}  2-19" in out
    # One consuming pool keeps the earlier column title.
    code, out, err = _cli(capsys, "check-data", ESTIMATES, "--registry", REGISTRY_INDEX)
    assert code == EXIT_OK, err
    assert "consuming pool      enzyme pools" in out


def test_check_data_reports_a_pool_refusal(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    culture = _culture(PARALLEL, change={("hydrolysis_capacity", ENDO): {"enzyme_class": DIMER}})
    dataset = _copy_fixture(tmp_path, PARALLEL, edits={CULTURE_TABLE: culture})
    code, _out, err = _cli(capsys, "check-data", dataset, "--registry", REGISTRY_INDEX)
    assert code == EXIT_USAGE
    assert f"culture.csv:{_line(PARALLEL, 'hydrolysis_capacity', ENDO)}:enzyme_class: hydrolysis_capacity belongs to" in err


def test_run_simulates_the_parallel_culture(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code, out, err = _cli(
        capsys,
        "run",
        "--user-data",
        PARALLEL,
        "--fungus",
        "strain_g5",
        "--substrate",
        "solid_g5",
        "--environment",
        "c28_ph5",
        "--mode",
        "exploratory",
        "--samples",
        "1",
        "--seed",
        "2",
        "--output",
        tmp_path / "run",
        "--no-plots",
    )
    assert code == EXIT_OK, err
    assert "Simulated 1 case(s) in exploratory mode" in out
    assert "time_to_50_percent_substrate_degradation" in out


def test_the_base_registry_is_not_changed(parallel: UserDataset) -> None:
    base = load_registry(REGISTRY_INDEX)
    overlaid = parallel.overlay(base)
    assert len(overlaid.process_compatibility) == len(base.process_compatibility) + 2
    assert not any(record_id.startswith(PARALLEL_ID) for record_id in base.process_compatibility)
