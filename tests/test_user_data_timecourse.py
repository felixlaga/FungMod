"""Time courses in user data: compare simulations with them and fit kinetic constants (USERDATA-004).

Every time course in this module is synthetic and labelled so in its source:
either computed from the integrated Michaelis-Menten equation or taken from a
FungMod simulation of the dataset with known constants. None is a measurement.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from scipy.special import lambertw

import fungal_model
from fungal_model import (
    TimecourseComparison,
    UserDataError,
    UserDataFitError,
    UserDataset,
    UserDatasetFit,
    VirtualExperiment,
    compare_with_timecourses,
    fit_user_dataset,
    load_user_dataset,
    virtual_experiment,
)
from fungal_model.api import VirtualExperimentError
from fungal_model.api.output_schema import OUTPUT_SCHEMA_VERSION, OUTPUT_TABLE_SCHEMAS
from fungal_model.api.result_tables import _mechanism_maturity
from fungal_model.api.user_data import (
    FIT_IDENTIFIED,
    FITTED_EVIDENCE_TYPE,
    TIMECOURSE_TABLE,
    USER_DATASET_MATURITY_FITTED,
)
from fungal_model.api.user_data_fit import TIMECOURSE_COMPARISON_NOTE
from fungal_model.registry import FungModRegistry, load_registry
from fungal_model.registry.loaders import load_parameter_record_mapping
from fungal_model.registry.records import PARAMETER_ALLOWED_USE_EXPLORATORY_SCREENING

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"
FIXTURES = ROOT / "tests" / "fixtures" / "user_data"
ESTERASE = FIXTURES / "esterase_case"
LITERATURE = FIXTURES / "literature_reentry"
OXIDASE = FIXTURES / "oxidase_case"
SNAPSHOTS = FIXTURES / "assembled_config_snapshots.json"

ESTERASE_SOURCE = "FungMod user-data import fixture; illustrative values, not measurements"
TIMECOURSE_HEADER = (
    "strain_id,enzyme_class,substrate_id,condition_id,observable,time,time_units,value,units,sd,replicates,source,method"
)
ANALYTIC_SOURCE = (
    "synthetic: integrated Michaelis-Menten solution computed in tests/test_user_data_timecourse.py from the "
    "dataset's own Km, kcat and concentrations; not a measurement"
)
SIMULATED_SOURCE = (
    "synthetic: FungMod simulation of this dataset with known constants in tests/test_user_data_timecourse.py, "
    "plus seeded Gaussian noise where stated; not a measurement"
)
ESTERASE_CASE = ("strain_e1", "carboxylesterase", "p_nitrophenyl_butyrate")
TRUE_KM = 150.0  # µM
TRUE_KCAT = 30.0  # 1/min
STARTING_CONDITIONS = {"s50": 50.0, "s200": 200.0, "s800": 800.0}  # initial substrate, µM
SAMPLE_TIMES = (0, 5, 10, 20, 30, 40, 50, 60)  # minutes, on the simulated grid

LITERATURE_FUNGUS = "reaction_618_reentry__os3bglu6_source"
LITERATURE_ENVIRONMENT = "reaction_618_reentry__c30_ph5"
LITERATURE_KM = 15.3  # mM
LITERATURE_VMAX = 0.13 * 3600.0 * 1e-3  # kcat (1/s) x enzyme (mM), in mM/h
LITERATURE_S0 = 10.0  # mM


@pytest.fixture(scope="module")
def base_registry() -> FungModRegistry:
    return load_registry(REGISTRY_INDEX)


def _copy(source: Path, destination: Path, edits: Mapping[str, str | None] | None = None) -> Path:
    shutil.copytree(source, destination)
    for name, text in (edits or {}).items():
        if text is None:
            (destination / name).unlink()
        else:
            (destination / name).write_text(text, encoding="utf-8")
    return destination


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _csv_text(rows: list[dict[str, str]]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


# ---------------------------------------------------------------------------
# Literature re-entry with the integrated Michaelis-Menten solution as observations


def _integrated_substrate(hours: float) -> float:
    """S(t) from Km ln(S0/S) + (S0 - S) = Vmax t (Lambert W form)."""

    argument = (LITERATURE_S0 / LITERATURE_KM) * math.exp((LITERATURE_S0 - LITERATURE_VMAX * hours) / LITERATURE_KM)
    return float(LITERATURE_KM * lambertw(argument).real)


def _literature_timecourse(times_h: tuple[float, ...] = (0.0, 1.0, 2.5, 5.0, 7.5, 10.0)) -> str:
    lines = [TIMECOURSE_HEADER]
    case = "os3bglu6_source,beta_glucosidase,cellobiose,c30_ph5"
    for hours in times_h:
        substrate = _integrated_substrate(hours)
        lines.append(f'{case},substrate,{hours},hour,{substrate!r},mM,0.05,3,"{ANALYTIC_SOURCE}",analytic solution')
    for hours in times_h:
        product = 2.0 * (LITERATURE_S0 - _integrated_substrate(hours))
        lines.append(f'{case},product,{hours},hour,{product!r},mM,,,"{ANALYTIC_SOURCE}",analytic solution')
    return "\n".join(lines) + "\n"


@pytest.fixture(scope="module")
def literature_with_timecourse(tmp_path_factory: pytest.TempPathFactory, base_registry: FungModRegistry) -> UserDataset:
    directory = tmp_path_factory.mktemp("literature") / "dataset"
    _copy(LITERATURE, directory, {TIMECOURSE_TABLE: _literature_timecourse()})
    return load_user_dataset(directory, registry=base_registry)


def test_timecourse_rows_join_the_dataset_keyed_by_generated_case_ids_without_records(
    literature_with_timecourse: UserDataset, base_registry: FungModRegistry
) -> None:
    plain = load_user_dataset(LITERATURE, registry=base_registry)
    case_id = "reaction_618_reentry__os3bglu6_source__beta_glucosidase__cellobiose__c30_ph5"

    assert list(literature_with_timecourse.timecourses) == [case_id]
    substrate, product = literature_with_timecourse.timecourses[case_id]
    assert (substrate.observable, product.observable) == ("substrate", "product")
    assert substrate.fungus_id == LITERATURE_FUNGUS
    assert substrate.substrate_record_id == "cellobiose"
    assert substrate.environment_id == LITERATURE_ENVIRONMENT
    assert substrate.enzyme_class_id == "reaction_618_reentry__beta_glucosidase"
    assert [point.time for point in substrate.points] == [0.0, 1.0, 2.5, 5.0, 7.5, 10.0]
    assert substrate.points[0].row == 2 and substrate.points[0].sd == 0.05 and substrate.points[0].replicates == 3
    assert all(point.sd is None for point in product.points)
    # Time courses are observations: the table enters the digest, and the generated records differ only by
    # the digest every record cites.
    assert literature_with_timecourse.digest != plain.digest
    with_timecourse = json.dumps(literature_with_timecourse.to_dict()["records"], sort_keys=True)
    assert with_timecourse.replace(literature_with_timecourse.digest, "<digest>") == json.dumps(
        plain.to_dict()["records"], sort_keys=True
    ).replace(plain.digest, "<digest>")
    assert TIMECOURSE_TABLE in literature_with_timecourse.file_digests
    assert literature_with_timecourse.to_dict()["timecourses"][case_id][0]["points"][0]["row"] == 2
    assert literature_with_timecourse.summary()["timecourse_case_ids"] == [case_id]
    overlaid = literature_with_timecourse.overlay(base_registry)
    assert len(overlaid.parameters) == len(plain.overlay(base_registry).parameters)


def test_comparison_with_the_integrated_solution_has_near_zero_rmse(
    tmp_path: Path, literature_with_timecourse: UserDataset, base_registry: FungModRegistry
) -> None:
    study = virtual_experiment(
        fungi=LITERATURE_FUNGUS,
        substrates="cellobiose",
        environments="c30_ph5",
        user_data=literature_with_timecourse,
        registry=base_registry,
    )
    result = study.simulate(mode="exploratory", n_samples=3, seed=4, output_dir=tmp_path / "run", quicklook=False)

    comparison = result.compare_with_timecourses()

    assert isinstance(comparison, TimecourseComparison)
    by_observable = {item["observable"]: item for item in comparison.series}
    assert set(by_observable) == {"substrate", "product"}
    for summary in by_observable.values():
        assert summary["rmse"] < 1e-5  # mM; solver tolerance, not a model difference
        assert 0.0 <= summary["fraction_inside_band"] <= 1.0
        assert summary["n_observations"] == 6
    assert by_observable["substrate"]["n_with_sd"] == 6
    assert by_observable["product"]["n_with_sd"] == 0
    assert by_observable["substrate"]["simulated_state"] == "cellobiose_concentration"
    assert by_observable["product"]["simulated_state"] == "product_formed"
    assert comparison.not_compared == ()

    table = Path(result.output_directory) / "timecourse_comparison.csv"
    assert comparison.path == str(table)
    rows = _csv_rows(table)
    assert rows == result.timecourse_comparison()
    assert len(rows) == 12
    assert list(rows[0])[: len(OUTPUT_TABLE_SCHEMAS["timecourse_comparison"]["columns"])] == [
        column["name"] for column in OUTPUT_TABLE_SCHEMAS["timecourse_comparison"]["columns"]
    ]
    assert {row["output_schema_version"] for row in rows} == {OUTPUT_SCHEMA_VERSION} == {"1.9.0"}
    assert {row["allowed_use"] for row in rows} == {"in_sample_agreement_with_user_timecourses_not_validation"}
    assert {row["interpretation_guardrail"] for row in rows} == {TIMECOURSE_COMPARISON_NOTE}
    assert "not validation" in TIMECOURSE_COMPARISON_NOTE
    assert all("linear interpolation" in row["interpolation"] and "never extrapolated" in row["interpolation"] for row in rows)
    assert {row["used_in_fit"] for row in rows} == {"false"}
    product_rows = [row for row in rows if row["observable"] == "product"]
    assert all(row["sd"] == "" and row["standardized_residual"] == "" for row in product_rows)
    final = next(row for row in rows if row["observable"] == "substrate" and float(row["time"]) == 10.0)
    assert float(final["simulated_p50"]) == pytest.approx(_integrated_substrate(10.0), abs=1e-5)
    assert final["units"] == "mM" and final["time_units"] == "hour"

    manifest = json.loads((Path(result.output_directory) / "output_manifest.json").read_text(encoding="utf-8"))
    assert "timecourse_comparison.csv" in manifest["files"]
    assert manifest["tables"]["timecourse_comparison"] == str(table)
    dictionary = _csv_rows(Path(result.output_directory) / "virtual_experiment_output_data_dictionary.csv")
    assert any(row["table"] == "timecourse_comparison" and row["column"] == "series_rmse" for row in dictionary)


def test_comparison_interpolates_linearly_between_grid_points(
    tmp_path: Path, base_registry: FungModRegistry
) -> None:
    directory = _copy(LITERATURE, tmp_path / "dataset", {TIMECOURSE_TABLE: _literature_timecourse((0.0, 0.25, 3.05))})
    dataset = load_user_dataset(directory, registry=base_registry)
    result = virtual_experiment(
        fungi=LITERATURE_FUNGUS, substrates="cellobiose", environments="c30_ph5", user_data=dataset, registry=base_registry
    ).simulate(mode="exploratory", n_samples=1, seed=1, output_dir=tmp_path / "run", quicklook=False)

    comparison = compare_with_timecourses(result, dataset, output_dir=tmp_path / "elsewhere")

    grid = sorted(
        (float(row["time"]), float(row["p50"]))
        for row in result.trajectory_quantiles()
        if row["state_role"] == "substrate"
    )
    times, values = zip(*grid, strict=True)
    row = next(item for item in comparison.rows if item["observable"] == "substrate" and item["time"] == 3.05)
    assert 3.05 not in times
    assert row["simulated_p50"] == pytest.approx(float(np.interp(3.05, times, values)), rel=1e-12)
    # Written elsewhere on request, so the result's own tables and manifest are left alone.
    assert Path(comparison.path or "") == tmp_path / "elsewhere" / "timecourse_comparison.csv"
    assert result.tables is not None and "timecourse_comparison" not in result.tables.paths


def test_observations_outside_the_simulated_range_are_refused(tmp_path: Path, base_registry: FungModRegistry) -> None:
    directory = _copy(LITERATURE, tmp_path / "dataset", {TIMECOURSE_TABLE: _literature_timecourse((0.0, 5.0, 12.0))})
    dataset = load_user_dataset(directory, registry=base_registry)
    result = virtual_experiment(
        fungi=LITERATURE_FUNGUS, substrates="cellobiose", environments="c30_ph5", user_data=dataset, registry=base_registry
    ).simulate(mode="exploratory", n_samples=1, seed=1, output_dir=tmp_path / "run", quicklook=False)

    with pytest.raises(UserDataError) as excinfo:
        result.compare_with_timecourses()

    located = {(issue["file"], issue["row"], issue["column"]) for issue in excinfo.value.issues}
    assert located == {(TIMECOURSE_TABLE, 4, "time"), (TIMECOURSE_TABLE, 7, "time")}
    assert all("outside the simulated time range" in issue["message"] for issue in excinfo.value.issues)
    assert all("does not extrapolate" in issue["message"] for issue in excinfo.value.issues)
    assert not (Path(result.output_directory) / "timecourse_comparison.csv").exists()


def test_comparison_needs_the_simulated_dataset_and_its_time_courses(
    tmp_path: Path, literature_with_timecourse: UserDataset, base_registry: FungModRegistry
) -> None:
    plain = load_user_dataset(LITERATURE, registry=base_registry)
    without = virtual_experiment(
        fungi=LITERATURE_FUNGUS, substrates="cellobiose", environments="c30_ph5", user_data=plain, registry=base_registry
    ).simulate(mode="exploratory", n_samples=1, seed=1, output_dir=tmp_path / "plain", quicklook=False)
    with pytest.raises(VirtualExperimentError, match="no timecourse.csv"):
        without.compare_with_timecourses()
    # A result is compared only with the dataset it simulated.
    with pytest.raises(UserDataError, match="not built from this user dataset"):
        compare_with_timecourses(without, literature_with_timecourse)

    registry_only = VirtualExperiment.from_registry(
        fungi="sabiork_beta_glucosidase_source",
        substrates="cellobiose",
        environments="sabiork_reaction_618_selected_conditions",
        registry=base_registry,
    ).simulate(mode="exploratory", n_samples=1, seed=1, output_dir=tmp_path / "registry", quicklook=False)
    with pytest.raises(VirtualExperimentError, match="without user_data"):
        registry_only.compare_with_timecourses()


# ---------------------------------------------------------------------------
# (a) Synthetic recovery on the non-specific esterase case


def _esterase_dataset(directory: Path, *, conditions: Mapping[str, float], duration: int = 60) -> Path:
    """The esterase fixture with one condition per initial substrate concentration, all at 37 degC and pH 7.5."""

    source = f'"{ESTERASE_SOURCE}"'
    kinetics = ["strain_id,enzyme_class,substrate_id,condition_id,quantity,value,lower,upper,units,evidence_type,method,source,sd,replicates"]
    case = ",".join(ESTERASE_CASE)
    for condition, initial in conditions.items():
        kinetics += [
            f"{case},{condition},km,{TRUE_KM},,,µM,estimate,,{source},,",
            f"{case},{condition},kcat,{TRUE_KCAT},,,1/min,estimate,,{source},,",
            f"{case},{condition},substrate_initial_concentration,{initial},,,µM,design,experimental design,{source},,",
            f"{case},{condition},enzyme_concentration,0.05,,,µM,design,experimental design,{source},,",
        ]
    manifest = yaml.safe_load((ESTERASE / "user_dataset.yml").read_text(encoding="utf-8"))
    manifest["simulation"] = {"duration": duration, "units": "minute", "points": duration + 1}
    return _copy(
        ESTERASE,
        directory,
        {
            "conditions.csv": "condition_id,temperature,temperature_units,ph,notes\n"
            + "".join(f"{condition},37,degC,7.5,\n" for condition in conditions),
            "kinetics.csv": "\n".join(kinetics) + "\n",
            "user_dataset.yml": yaml.safe_dump(manifest, sort_keys=False),
        },
    )


def _simulated_medians(
    directory: Path, registry: FungModRegistry, output: Path, *, strain: str, substrate: str
) -> dict[tuple[str, str], dict[float, float]]:
    dataset = load_user_dataset(directory, registry=registry)
    conditions = [record["aliases"][0] for record in dataset.records["environments"]]
    result = virtual_experiment(
        fungi=strain, substrates=substrate, environments=conditions, user_data=dataset, registry=registry
    ).simulate(mode="exploratory", n_samples=1, seed=1, output_dir=output, quicklook=False)
    medians: dict[tuple[str, str], dict[float, float]] = {}
    for row in result.trajectory_quantiles():
        condition = row["environment_id"].split("__", 1)[1]
        if row["state_role"] == "substrate":
            medians.setdefault((condition, "substrate"), {})[float(row["time"])] = float(row["p50"])
        if row["state"] == "product_formed":
            medians.setdefault((condition, "product"), {})[float(row["time"])] = float(row["p50"])
    return medians


def _timecourse_from(
    medians: Mapping[tuple[str, str], Mapping[float, float]],
    *,
    case: tuple[str, str, str],
    sd: Mapping[str, float],
    observables: tuple[str, ...] = ("substrate", "product"),
    noise_seed: int | None = None,
) -> str:
    rng = None if noise_seed is None else np.random.default_rng(noise_seed)
    lines = [TIMECOURSE_HEADER]
    for (condition, observable), series in sorted(medians.items()):
        if observable not in observables:
            continue
        for time in SAMPLE_TIMES:
            value = series[float(time)] + (0.0 if rng is None else float(rng.normal(0.0, sd[condition])))
            lines.append(
                f"{','.join(case)},{condition},{observable},{time},minute,{value!r},µM,{sd[condition]},3,"
                f'"{SIMULATED_SOURCE}",synthetic simulation'
            )
    return "\n".join(lines) + "\n"


@pytest.fixture(scope="module")
def synthetic_esterase(tmp_path_factory: pytest.TempPathFactory, base_registry: FungModRegistry) -> UserDataset:
    root = tmp_path_factory.mktemp("synthetic_esterase")
    directory = _esterase_dataset(root / "dataset", conditions=STARTING_CONDITIONS)
    medians = _simulated_medians(
        directory, base_registry, root / "truth", strain="Esterase source strain E1", substrate="p-nitrophenyl butyrate"
    )
    sd = {condition: max(0.01 * initial, 0.5) for condition, initial in STARTING_CONDITIONS.items()}
    (directory / TIMECOURSE_TABLE).write_text(
        _timecourse_from(medians, case=ESTERASE_CASE, sd=sd, noise_seed=20261006), encoding="utf-8"
    )
    return load_user_dataset(directory, registry=base_registry)


@pytest.fixture(scope="module")
def esterase_fit(synthetic_esterase: UserDataset, base_registry: FungModRegistry) -> UserDatasetFit:
    return fit_user_dataset(
        synthetic_esterase,
        base_registry=base_registry,
        parameters=[(*ESTERASE_CASE, "km"), (*ESTERASE_CASE, "kcat")],
        bounds={(*ESTERASE_CASE, "km"): (10.0, 5000.0, "µM"), "kcat": (1.0, 300.0, "1/min")},
        initial={"km": 1000.0, "kcat": 5.0},  # deliberately far from the truth
        profile_points=11,
    )


def test_synthetic_time_courses_recover_km_and_kcat_within_the_profile_intervals(esterase_fit: UserDatasetFit) -> None:
    quantities = {item.quantity: item for item in esterase_fit.quantities}
    assert esterase_fit.identified
    for quantity, truth in (("km", TRUE_KM), ("kcat", TRUE_KCAT)):
        item = quantities[quantity]
        assert item.identifiability == FIT_IDENTIFIED
        assert item.identifiability_method.startswith("profile likelihood")
        assert item.interval is not None
        low, high = item.interval
        # The identifiability-consistent tolerance: the truth lies in the profile interval around the estimate.
        assert low < item.value < high
        assert low <= truth <= high
        assert abs(item.value - truth) <= high - low
    assert quantities["km"].units == "µM" and quantities["kcat"].units == "1/min"
    assert quantities["km"].initial == 1000.0 and quantities["kcat"].initial == 5.0

    report = esterase_fit.report
    assert report["error_model"] == "sd_weighted"
    assert report["n_observations"] == 48 and report["n_parameters"] == 2
    assert report["residual_degrees_of_freedom"] == 46
    assert report["convergence"]["success"] is True
    assert report["identifiability"]["method"] == "profile_likelihood"
    assert report["identifiability"]["delta_chi_squared_threshold"] == pytest.approx(3.841458820694124)
    assert report["identifiability"]["local_information"]["practical_rank"] == 2
    assert report["conditions"] == ["s50", "s200", "s800"]
    assert report["timecourse_rows"] == list(range(2, 50))
    assert {series["observable"] for series in report["residuals"]} == {"substrate", "product"}
    assert "not validation" in report["claim_boundary"]
    assert report["input_dataset_digest"] == esterase_fit.input_dataset_digest


def test_fitted_dataset_reloads_with_labelled_fitted_rows(
    tmp_path: Path, esterase_fit: UserDatasetFit, synthetic_esterase: UserDataset, base_registry: FungModRegistry
) -> None:
    fitted = esterase_fit.write(tmp_path / "fitted", registry=base_registry)

    assert fitted.dataset_id == "esterase_demo_fitted" == esterase_fit.dataset_id
    assert load_user_dataset(tmp_path / "fitted", registry=base_registry).digest == fitted.digest
    manifest = yaml.safe_load((tmp_path / "fitted" / "user_dataset.yml").read_text(encoding="utf-8"))
    block = manifest["fit"]
    assert block["input_dataset_digest"] == synthetic_esterase.digest
    report_bytes = (tmp_path / "fitted" / "fit_report.json").read_bytes()
    assert block["report_sha256"] == hashlib.sha256(report_bytes).hexdigest()
    assert json.loads(report_bytes)["fitted_dataset_id"] == "esterase_demo_fitted"
    # Every other input table is copied byte for byte.
    for name in ("strains.csv", "enzymes.csv", "enzyme_classes.csv", "substrates.csv", "conditions.csv", TIMECOURSE_TABLE):
        assert (tmp_path / "fitted" / name).read_bytes() == synthetic_esterase._raw_files[name]

    kinetics = _csv_rows(tmp_path / "fitted" / "kinetics.csv")
    fitted_rows = [row for row in kinetics if row["evidence_type"] == FITTED_EVIDENCE_TYPE]
    assert {(row["condition_id"], row["quantity"]) for row in fitted_rows} == {
        (condition, quantity) for condition in STARTING_CONDITIONS for quantity in ("km", "kcat")
    }
    assert not any(row["quantity"] in {"km", "kcat"} and row["evidence_type"] == "estimate" for row in kinetics)
    assert all("not a measurement" in row["source"] and "fit_user_dataset" in row["method"] for row in fitted_rows)

    records = {mapping["record_id"]: mapping for mapping in fitted.records["parameter_records"]}
    km = load_parameter_record_mapping(records["esterase_demo_fitted__strain_e1__carboxylesterase__p_nitrophenyl_butyrate__s200__km"])
    assert km.maturity == USER_DATASET_MATURITY_FITTED
    assert km.allowed_use == PARAMETER_ALLOWED_USE_EXPLORATORY_SCREENING
    assert km.value.is_exact and km.value.value == pytest.approx(esterase_fit.quantities[0].value)
    fit = km.provenance["fungmod_user_dataset"]["fit"]
    assert fit["timecourse_rows"] == list(range(2, 50))
    assert fit["bounds"] == [10.0, 5000.0]
    assert fit["identifiability"] == FIT_IDENTIFIED
    assert fit["objective"].startswith("sum over the time-course observations")
    assert "in-sample" in fit["claim_boundary"] and "scientific mode refuses" in fit["scientific_mode"]
    assert km.provenance["fungmod_user_dataset"]["evidence_type"] == FITTED_EVIDENCE_TYPE
    assert "fit_user_dataset" in str(km.provenance["measurement_method"])

    study = virtual_experiment(
        fungi="Esterase source strain E1",
        substrates="p-nitrophenyl butyrate",
        environments=list(STARTING_CONDITIONS),
        user_data=fitted,
        registry=base_registry,
    )
    assert {report.status for report in study.preflight(mode="exploratory")} == {"modelable"}
    assert "modelable" not in {report.status for report in study.preflight(mode="scientific")}
    with pytest.raises(VirtualExperimentError, match="Scientific simulation requires"):
        study.simulate(mode="scientific", output_dir=tmp_path / "scientific", quicklook=False)

    result = study.simulate(mode="exploratory", n_samples=1, seed=2, output_dir=tmp_path / "run", quicklook=False)
    assert {row["maturity"] for row in result.mechanism_summary()} == {"software_tested_user_fitted_in_sample_unvalidated"}
    assert "user_fitted_exact_value" in {row["parameter_source_class"] for row in result.sampled_parameters()}
    comparison = result.compare_with_timecourses()
    # The fitted dataset carries its own time courses; agreement with them is in-sample and flagged as such.
    assert {row["used_in_fit"] for row in comparison.rows} == {True}
    for summary in comparison.series:
        assert summary["rmse"] < 3.0 * max(0.01 * STARTING_CONDITIONS[summary["series_id"].split("__")[-2]], 0.5)


def test_fit_refuses_without_sd_unless_unweighted_is_chosen(tmp_path: Path, synthetic_esterase: UserDataset, base_registry: FungModRegistry) -> None:
    rows = list(csv.DictReader(synthetic_esterase._raw_files[TIMECOURSE_TABLE].decode("utf-8").splitlines()))
    directory = _copy(
        Path(synthetic_esterase.source_directory),
        tmp_path / "dataset",
        {TIMECOURSE_TABLE: _csv_text([{**row, "sd": ""} for row in rows])},
    )
    dataset = load_user_dataset(directory, registry=base_registry)
    parameters = [(*ESTERASE_CASE, "km"), (*ESTERASE_CASE, "kcat")]
    bounds = {"km": (10.0, 5000.0, "µM"), "kcat": (1.0, 300.0, "1/min")}

    with pytest.raises(UserDataFitError) as excinfo:
        fit_user_dataset(dataset, base_registry=base_registry, parameters=parameters, bounds=bounds, initial={"km": 400.0, "kcat": 10.0})
    assert {issue["column"] for issue in excinfo.value.issues} == {"sd"}
    assert len(excinfo.value.issues) == 48
    assert "error_model='unweighted'" in excinfo.value.issues[0]["message"]

    fit = fit_user_dataset(
        dataset,
        base_registry=base_registry,
        parameters=parameters,
        bounds=bounds,
        initial={"km": 400.0, "kcat": 10.0},
        error_model="unweighted",
    )
    assert fit.report["error_model"] == "unweighted"
    assert "unweighted" in fit.report["objective"]
    assert fit.report["identifiability"]["method"] == "local_information"
    quantities = {item.quantity: item for item in fit.quantities}
    assert quantities["km"].identifiability_method.startswith("local information")
    assert quantities["km"].value == pytest.approx(TRUE_KM, rel=0.15)
    assert quantities["kcat"].value == pytest.approx(TRUE_KCAT, rel=0.15)
    written = fit.write(tmp_path / "fitted", registry=base_registry)
    assert written.manifest["fit"]["error_model"] == "unweighted"


# ---------------------------------------------------------------------------
# (c) A case the time courses cannot identify: saturating substrate only


@pytest.fixture(scope="module")
def saturating_esterase(tmp_path_factory: pytest.TempPathFactory, base_registry: FungModRegistry) -> UserDataset:
    """Initial substrate 20000 µM, more than a hundred times Km: the rate stays at Vmax and Km is not seen."""

    root = tmp_path_factory.mktemp("saturating")
    conditions = {"s20000": 20000.0}
    directory = _esterase_dataset(root / "dataset", conditions=conditions)
    medians = _simulated_medians(
        directory, base_registry, root / "truth", strain="Esterase source strain E1", substrate="p-nitrophenyl butyrate"
    )
    (directory / TIMECOURSE_TABLE).write_text(
        _timecourse_from(medians, case=ESTERASE_CASE, sd={"s20000": 0.5}, observables=("product",), noise_seed=11),
        encoding="utf-8",
    )
    return load_user_dataset(directory, registry=base_registry)


def _saturating_fit(dataset: UserDataset, registry: FungModRegistry, **options: Any) -> UserDatasetFit:
    return fit_user_dataset(
        dataset,
        base_registry=registry,
        parameters=[(*ESTERASE_CASE, "km"), (*ESTERASE_CASE, "kcat")],
        bounds={"km": (10.0, 2000.0, "µM"), "kcat": (1.0, 100.0, "1/min")},
        initial={"km": 500.0, "kcat": 10.0},
        profile_points=7,
        **options,
    )


def test_unidentified_km_refuses_the_fit(saturating_esterase: UserDataset, base_registry: FungModRegistry) -> None:
    with pytest.raises(UserDataFitError) as excinfo:
        _saturating_fit(saturating_esterase, base_registry)

    report = excinfo.value.report
    assert report is not None
    verdicts = {item["quantity"]: item["identifiability"] for item in report["quantities"]}
    assert verdicts["km"] != FIT_IDENTIFIED
    assert verdicts["kcat"] == FIT_IDENTIFIED
    # kcat is identified only through km's bounds (kcat S / (Km + S) is what saturating data see); its bisected
    # profile interval still covers the true value instead of collapsing onto the optimum.
    kcat = next(item for item in report["quantities"] if item["quantity"] == "kcat")
    assert kcat["interval"][0] <= TRUE_KCAT <= kcat["interval"][1]
    assert report["identifiability"]["bisection_steps"] == 10
    assert report["identified"] is False
    assert report["fitted_dataset_id"] is None
    messages = " ".join(issue["message"] for issue in excinfo.value.issues)
    assert "km is" in messages and "allow_unidentified=True" in messages
    assert "kcat is" not in messages


def test_allow_unidentified_writes_labelled_rows(
    tmp_path: Path, saturating_esterase: UserDataset, base_registry: FungModRegistry
) -> None:
    fit = _saturating_fit(saturating_esterase, base_registry, allow_unidentified=True, fitted_dataset_id="saturating_fit")
    assert not fit.identified
    fitted = fit.write(tmp_path / "fitted", registry=base_registry)

    block = fitted.manifest["fit"]
    assert block["allow_unidentified"] is True
    entries = {entry["quantity"]: entry for entry in block["quantities"]}
    assert entries["km"]["identifiability"] != FIT_IDENTIFIED
    assert entries["kcat"]["identifiability"] == FIT_IDENTIFIED
    records = {mapping["record_id"]: mapping for mapping in fitted.records["parameter_records"]}
    km = records["saturating_fit__strain_e1__carboxylesterase__p_nitrophenyl_butyrate__s20000__km"]
    kcat = records["saturating_fit__strain_e1__carboxylesterase__p_nitrophenyl_butyrate__s20000__kcat"]
    assert km["notes"].startswith("NOT IDENTIFIED by the time courses")
    assert km["provenance"]["fungmod_user_dataset"]["fit"]["identifiability"] == entries["km"]["identifiability"]
    assert not kcat["notes"].startswith("NOT IDENTIFIED")
    assert km["maturity"] == kcat["maturity"] == USER_DATASET_MATURITY_FITTED


# ---------------------------------------------------------------------------
# A second, materially different case: Vmax form from a specific activity, with response laws


def test_vmax_form_fit_replaces_the_vmax_route(tmp_path: Path, base_registry: FungModRegistry) -> None:
    directory = _copy(OXIDASE, tmp_path / "dataset")
    medians = _simulated_medians(
        directory, base_registry, tmp_path / "truth", strain="Oxidase source strain L1", substrate="syringaldazine-like phenolic azine"
    )
    case = ("strain_l1", "laccase_like_oxidase", "syringaldazine_like")
    (directory / TIMECOURSE_TABLE).write_text(
        _timecourse_from(medians, case=case, sd={"c50_ph5": 0.25}, noise_seed=5), encoding="utf-8"
    )
    dataset = load_user_dataset(directory, registry=base_registry)

    fit = fit_user_dataset(
        dataset,
        base_registry=base_registry,
        parameters=[(*case, "km"), (*case, "vmax")],
        bounds={"km": (1.0, 500.0, "µM"), "vmax": (0.01, 10.0, "µM/min")},
        initial={"km": 100.0, "vmax": 3.0},
        profile_points=9,
    )

    quantities = {item.quantity: item for item in fit.quantities}
    assert fit.identified
    # The synthetic data come from Km 20 µM and Vmax 12 µmol/min/mg x 0.05 mg/L = 0.6 µM/min.
    for quantity, truth in (("km", 20.0), ("vmax", 0.6)):
        interval = quantities[quantity].interval
        assert interval is not None and interval[0] <= truth <= interval[1]
    fitted = fit.write(tmp_path / "fitted", registry=base_registry)
    kinetics = _csv_rows(tmp_path / "fitted" / "kinetics.csv")
    assert {row["quantity"] for row in kinetics} == {"km", "vmax", "substrate_initial_concentration"}
    assert {row["evidence_type"] for row in kinetics if row["quantity"] in {"km", "vmax"}} == {FITTED_EVIDENCE_TYPE}
    records = {mapping["record_id"]: mapping for mapping in fitted.records["parameter_records"]}
    vmax = records["oxidase_demo_fitted__strain_l1__laccase_like_oxidase__syringaldazine_like__c50_ph5__vmax"]
    assert vmax["maturity"] == USER_DATASET_MATURITY_FITTED
    assert vmax["value"]["units"] == "µM/min"
    # The cardinal laws stay bound; the fitted constants are stated at their reference condition.
    template = next(iter(fitted.records["case_templates"]))
    assert {item["type"] for item in template["process_state_metadata"]["process_modifiers"]} == {
        "temperature_cardinal_rosso",
        "ph_cardinal_rosso",
    }


# ---------------------------------------------------------------------------
# (d) Validation of timecourse.csv and of fit requests


def _literature_with(tmp_path: Path, timecourse: str) -> Path:
    return _copy(LITERATURE, tmp_path / "dataset", {TIMECOURSE_TABLE: timecourse})


_GOOD_ROW = 'os3bglu6_source,beta_glucosidase,cellobiose,c30_ph5,substrate,1,hour,9.5,mM,0.05,3,"lab notebook",HPLC'

TIMECOURSE_VALIDATION_CASES: dict[str, tuple[list[str], tuple[str, int | None, str | None, str]]] = {
    "wrong_dimension": (
        [_GOOD_ROW.replace(",9.5,mM,", ",9.5,1/min,")],
        (TIMECOURSE_TABLE, 2, "units", "not a concentration"),
    ),
    "mass_molar_mismatch": (
        [_GOOD_ROW.replace(",9.5,mM,", ",3.2,g/L,")],
        (TIMECOURSE_TABLE, 2, "units", "mass concentration"),
    ),
    "duplicate_time": (
        [_GOOD_ROW, _GOOD_ROW.replace(",9.5,", ",9.4,")],
        (TIMECOURSE_TABLE, 3, "time", "Rows 2 and 3"),
    ),
    "negative_time": (
        [_GOOD_ROW.replace(",substrate,1,hour,", ",substrate,-1,hour,")],
        (TIMECOURSE_TABLE, 2, "time", "zero or positive"),
    ),
    "undeclared_strain": (
        [_GOOD_ROW.replace("os3bglu6_source,", "strain_x,", 1)],
        (TIMECOURSE_TABLE, 2, "strain_id", "not declared in strains.csv"),
    ),
    "undeclared_condition": (
        [_GOOD_ROW.replace(",c30_ph5,", ",c40_ph5,")],
        (TIMECOURSE_TABLE, 2, "condition_id", "not declared in conditions.csv"),
    ),
    "undeclared_class": (
        [_GOOD_ROW.replace(",beta_glucosidase,", ",cellobiohydrolase_x,")],
        (TIMECOURSE_TABLE, 2, "enzyme_class", "neither a registry enzyme class"),
    ),
    "time_units_not_time": (
        [_GOOD_ROW.replace(",1,hour,", ",1,mM,")],
        (TIMECOURSE_TABLE, 2, "time_units", "time unit"),
    ),
    "non_finite_value": (
        [_GOOD_ROW.replace(",9.5,", ",nan,")],
        (TIMECOURSE_TABLE, 2, "value", "finite number"),
    ),
    "unknown_observable": (
        [_GOOD_ROW.replace(",substrate,", ",biomass,")],
        (TIMECOURSE_TABLE, 2, "observable", "observable must be one of"),
    ),
    "non_positive_sd": (
        [_GOOD_ROW.replace(",0.05,3,", ",0,3,")],
        (TIMECOURSE_TABLE, 2, "sd", "positive"),
    ),
    "mixed_units_in_one_series": (
        [_GOOD_ROW, _GOOD_ROW.replace(",1,hour,9.5,mM,", ",2,hour,9100,uM,")],
        (TIMECOURSE_TABLE, 3, "units", "one series uses one time unit and one value unit"),
    ),
    "missing_method": (
        [_GOOD_ROW.replace(",HPLC", ",")],
        (TIMECOURSE_TABLE, 2, "method", "method is required"),
    ),
}


@pytest.mark.parametrize("case", sorted(TIMECOURSE_VALIDATION_CASES))
def test_invalid_time_courses_report_file_row_and_column(tmp_path: Path, case: str) -> None:
    rows, (file, row, column, message) = TIMECOURSE_VALIDATION_CASES[case]
    directory = _literature_with(tmp_path, "\n".join([TIMECOURSE_HEADER, *rows]) + "\n")

    with pytest.raises(UserDataError) as excinfo:
        load_user_dataset(directory, registry=REGISTRY_INDEX)

    matching = [
        issue
        for issue in excinfo.value.issues
        if issue["file"] == file and issue["row"] == row and issue["column"] == column and message in issue["message"]
    ]
    assert matching, excinfo.value.issues


def test_mass_concentration_message_names_the_case_units(tmp_path: Path) -> None:
    directory = _literature_with(tmp_path, "\n".join([TIMECOURSE_HEADER, _GOOD_ROW.replace(",9.5,mM,", ",3.2,g/L,")]) + "\n")
    with pytest.raises(UserDataError) as excinfo:
        load_user_dataset(directory, registry=REGISTRY_INDEX)
    message = next(issue["message"] for issue in excinfo.value.issues if issue["column"] == "units")
    assert "'mM'" in message and "molar mass" in message


def test_fit_requests_are_validated(tmp_path: Path, synthetic_esterase: UserDataset, base_registry: FungModRegistry) -> None:
    parameters = [(*ESTERASE_CASE, "km"), (*ESTERASE_CASE, "kcat")]
    bounds = {"km": (10.0, 5000.0, "µM"), "kcat": (1.0, 300.0, "1/min")}

    def refused(**changes: Any) -> str:
        options: dict[str, Any] = {"parameters": parameters, "bounds": bounds, "initial": {"km": 400.0, "kcat": 10.0}}
        options.update(changes)
        with pytest.raises(UserDataFitError) as excinfo:
            fit_user_dataset(synthetic_esterase, base_registry=base_registry, **options)
        return " ".join(issue["message"] for issue in excinfo.value.issues)

    assert "no default bounds" in refused(bounds={"km": (10.0, 5000.0, "µM")})
    assert "0 < lower < upper" in refused(bounds={"km": (0.0, 5000.0, "µM"), "kcat": (1.0, 300.0, "1/min")})
    assert "amount per volume" in refused(bounds={"km": (0.01, 5.0, "g/L"), "kcat": (1.0, 300.0, "1/min")})
    assert "1/time" in refused(bounds={"km": (10.0, 5000.0, "µM"), "kcat": (1.0, 300.0, "µM")})
    assert "outside its bounds" in refused(initial={"km": 9000.0, "kcat": 10.0})
    assert "not among" in refused(bounds={**bounds, "vmax": (0.1, 1.0, "µM/min")})
    assert "fit them separately" in refused(parameters=[(*ESTERASE_CASE, "km"), ("strain_e1", "carboxylesterase", "other", "kcat")])
    assert "km with kcat, or km with vmax" in refused(parameters=[(*ESTERASE_CASE, "kcat"), (*ESTERASE_CASE, "vmax")])
    assert "each must appear once" in refused(parameters=[(*ESTERASE_CASE, "enzyme_concentration")])
    assert "no time course" in refused(conditions=["s50", "c99"])
    assert "error_model must be one of" in refused(error_model="poisson")
    assert "No time course for strain" in refused(parameters=[("strain_e1", "carboxylesterase", "unknown_substrate", "km")])
    # The kcat form of this case cannot be fitted as a Vmax.
    assert "kcat form" in refused(parameters=[(*ESTERASE_CASE, "vmax")], bounds={"vmax": (0.1, 10.0, "µM/min")}, initial={"vmax": 1.0})
    # Without initial, the dataset's own exact value is the starting point, recorded as such.


def test_fit_refuses_observations_beyond_the_simulated_duration(
    tmp_path: Path, synthetic_esterase: UserDataset, base_registry: FungModRegistry
) -> None:
    manifest = dict(synthetic_esterase.manifest)
    manifest["simulation"] = {"duration": 45, "units": "minute", "points": 46}
    directory = _copy(
        Path(synthetic_esterase.source_directory),
        tmp_path / "dataset",
        {"user_dataset.yml": yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True)},
    )
    with pytest.raises(UserDataFitError) as excinfo:
        fit_user_dataset(
            str(directory),
            base_registry=base_registry,
            parameters=[(*ESTERASE_CASE, "km"), (*ESTERASE_CASE, "kcat")],
            bounds={"km": (10.0, 5000.0, "µM"), "kcat": (1.0, 300.0, "1/min")},
            initial={"km": 400.0, "kcat": 10.0},
        )
    # Times 50 and 60 minutes of each of the six series lie beyond 45 minutes.
    assert len(excinfo.value.issues) == 12
    assert {issue["column"] for issue in excinfo.value.issues} == {"time"}
    assert all("does not extrapolate" in issue["message"] for issue in excinfo.value.issues)


def test_shared_constants_need_one_temperature_and_ph(tmp_path: Path, base_registry: FungModRegistry) -> None:
    directory = _esterase_dataset(tmp_path / "dataset", conditions={"s50": 50.0, "s200": 200.0})
    (directory / "conditions.csv").write_text(
        "condition_id,temperature,temperature_units,ph,notes\ns50,37,degC,7.5,\ns200,30,degC,7.5,\n", encoding="utf-8"
    )
    rows = [TIMECOURSE_HEADER]
    for condition in ("s50", "s200"):
        for time in (0, 10, 20):
            rows.append(f'{",".join(ESTERASE_CASE)},{condition},product,{time},minute,{time / 10},µM,0.5,3,"{SIMULATED_SOURCE}",x')
    (directory / TIMECOURSE_TABLE).write_text("\n".join(rows) + "\n", encoding="utf-8")
    dataset = load_user_dataset(directory, registry=base_registry)

    with pytest.raises(UserDataFitError) as excinfo:
        fit_user_dataset(
            dataset,
            base_registry=base_registry,
            parameters=[(*ESTERASE_CASE, "kcat")],
            bounds={"kcat": (1.0, 300.0, "1/min")},
        )
    assert {issue["file"] for issue in excinfo.value.issues} == {"conditions.csv"}
    assert "same known temperature and pH" in excinfo.value.issues[0]["message"]

    # One condition at a time is fine, and without initial the fit starts from the dataset's exact value.
    fit = fit_user_dataset(
        dataset,
        base_registry=base_registry,
        parameters=[(*ESTERASE_CASE, "kcat")],
        bounds={"kcat": (1.0, 300.0, "1/min")},
        conditions=["s50"],
        error_model="unweighted",
    )
    assert fit.quantities[0].initial == TRUE_KCAT
    assert fit.quantities[0].initial_source.startswith("kinetics.csv rows")


def test_fitted_rows_need_their_fit_description(
    tmp_path: Path, esterase_fit: UserDatasetFit, base_registry: FungModRegistry
) -> None:
    good = tmp_path / "good"
    esterase_fit.write(good, registry=base_registry)

    def refused(directory: Path) -> list[dict[str, Any]]:
        with pytest.raises(UserDataError) as excinfo:
            load_user_dataset(directory, registry=base_registry)
        return excinfo.value.issues

    # A hand-typed fitted row without a fit block.
    plain = _copy(ESTERASE, tmp_path / "hand_typed")
    kinetics = (plain / "kinetics.csv").read_text(encoding="utf-8").replace(",km,150,,,µM,estimate,,", ",km,150,,,µM,fitted,my own fit,")
    (plain / "kinetics.csv").write_text(kinetics, encoding="utf-8")
    issues = refused(plain)
    assert any(issue["column"] == "evidence_type" and "reserved for rows written by fit_user_dataset" in issue["message"] for issue in issues)

    # A fitted value edited by hand.
    edited = _copy(good, tmp_path / "edited")
    rows = _csv_rows(edited / "kinetics.csv")
    for row in rows:
        if row["evidence_type"] == FITTED_EVIDENCE_TYPE and row["quantity"] == "km":
            row["value"] = "151.0"
    (edited / "kinetics.csv").write_text(_csv_text(rows), encoding="utf-8")
    assert any("not edited by hand" in issue["message"] for issue in refused(edited))

    # A changed fit report.
    report = _copy(good, tmp_path / "report")
    (report / "fit_report.json").write_text("{}\n", encoding="utf-8")
    assert any(issue["column"] == "fit.report_sha256" for issue in refused(report))

    # A fitted row on a quantity that is never fitted.
    concentration = _copy(good, tmp_path / "concentration")
    rows = _csv_rows(concentration / "kinetics.csv")
    for row in rows:
        if row["quantity"] == "enzyme_concentration":
            row["evidence_type"] = FITTED_EVIDENCE_TYPE
    (concentration / "kinetics.csv").write_text(_csv_text(rows), encoding="utf-8")
    assert any("not a fitted quantity" in issue["message"] for issue in refused(concentration))

    # An unidentified entry without allow_unidentified.
    flipped = _copy(good, tmp_path / "flipped")
    manifest = yaml.safe_load((flipped / "user_dataset.yml").read_text(encoding="utf-8"))
    manifest["fit"]["quantities"][0]["identifiability"] = "bounded_above_only"
    (flipped / "user_dataset.yml").write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")
    assert any("allow_unidentified is false" in issue["message"] for issue in refused(flipped))

    # Fits are not chained.
    with pytest.raises(UserDataFitError, match="itself the result of a fit"):
        fit_user_dataset(
            good,
            base_registry=base_registry,
            parameters=[(*ESTERASE_CASE, "km")],
            bounds={"km": (10.0, 5000.0, "µM")},
        )


# ---------------------------------------------------------------------------
# (e) Datasets without time courses are unchanged


def test_datasets_without_time_courses_are_unchanged(base_registry: FungModRegistry) -> None:
    expected = json.loads(SNAPSHOTS.read_text(encoding="utf-8"))
    for fixture in ("esterase_case", "literature_reentry"):
        dataset = load_user_dataset(FIXTURES / fixture, registry=base_registry)
        assert dataset.timecourses == {}
        assert dataset.to_dict()["timecourses"] == {}
        assert dataset.summary()["timecourse_case_ids"] == []
        assert "fit" not in dataset.manifest
        digest = hashlib.sha256(json.dumps(dataset.to_dict()["records"], sort_keys=True).encode("utf-8")).hexdigest()
        assert digest == expected[f"user_data_records_sha256_{fixture}"]


def test_fitted_maturity_has_its_own_mechanism_label() -> None:
    class _Record:
        def __init__(self, maturity: str) -> None:
            self.maturity = maturity

    fitted_and_design: dict[str, Any] = {"km": _Record("user_fitted"), "enzyme": _Record("user_design_value")}
    assert _mechanism_maturity("homogeneous_michaelis_menten", fitted_and_design) == (
        "software_tested_user_fitted_in_sample_unvalidated"
    )
    measured: dict[str, Any] = {"km": _Record("user_measured"), "enzyme": _Record("user_design_value")}
    assert _mechanism_maturity("homogeneous_michaelis_menten", measured) == "software_tested_user_supplied_parameterized"


def test_time_course_api_is_exported() -> None:
    for name in ("compare_with_timecourses", "fit_user_dataset", "UserDatasetFit", "UserDataFitError", "TimecourseComparison"):
        assert name in fungal_model.__all__
    assert issubclass(UserDataFitError, UserDataError)
