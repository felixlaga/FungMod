"""pH-ionization kinetics in user data (USERDATA-006).

The third rate form of a user (class, substrate) pair binds the existing
``ph_ionization_michaelis_menten`` process law: kcat(pH) = kcat_limiting /
f_es(pH) and Km(pH) = km_limiting f_e(pH) / f_es(pH), with the diprotic factors
f(pH) = (10^(pK_lower - pH) + 1)(10^(pH - pK_upper) + 1).

``tests/fixtures/user_data/bgl1a_ph_ionization`` re-enters the published
SABIO-RK entry 38522 law (BGL1A, Tsukada et al. 2008) from the registry records
as user ``literature`` rows with ``design`` concentrations equal to the
registry case's exploratory loadings. The non-specific case at the end is a
user-defined phosphatase-like class on a user-defined aryl phosphate with
illustrative estimates; it tests the generic route, not a measurement. The
converter tests run on the frozen Reaction 618 snapshot; two derive a modified
copy of entry 38522 in a temporary directory to test routing only.
"""

from __future__ import annotations

import copy
import csv
import dataclasses
import json
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from scipy.integrate import solve_ivp

from fungal_model import UserDataError, UserDataset, environment_grid, load_user_dataset, virtual_experiment
from fungal_model.api import VirtualExperimentError
from fungal_model.api.user_data import PH_IONIZATION_QUANTITIES, RATE_FORM_PH_IONIZATION, REVIEW_MARKER
from fungal_model.api.user_data_sources import (
    PH_IONIZATION_LAW_PARAMETERS,
    UserTablesSourceError,
    user_tables_from_sabiork,
)
from fungal_model.core.units import Q_
from fungal_model.core.value_spec import ValueSpec
from fungal_model.kinetics import EnvironmentalValidityWarning
from fungal_model.registry import FungModRegistry, load_registry
from fungal_model.registry.loaders import load_parameter_record_mapping
from fungal_model.registry.records import ParameterRecord
from fungal_model.screening.case_builder import (
    PH_IONIZATION_MM_PARAMETER_ROLES,
    RegistryCaseBuildError,
    build_model_config_from_registry_case,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"
FIXTURES = ROOT / "tests" / "fixtures" / "user_data"
BGL1A = FIXTURES / "bgl1a_ph_ionization"
SNAPSHOTS = FIXTURES / "assembled_config_snapshots.json"
RAW_EXPORT = (
    ROOT
    / "data"
    / "kinetic_records"
    / "sabiork"
    / "case_001_reaction_618_beta_glucosidase"
    / "raw"
    / "kinlaw_entries_reaction_618.json"
)

REGISTRY_FUNGUS = "phanerochaete_chrysosporium_k3"
REGISTRY_ENVIRONMENT = "tsukada_2008_bgl1a_assay_30c_ph5"
REGISTRY_COMPATIBILITY = "phanerochaete_bgl1a_cellobiose_ph_ionization_mm"
DATASET = "bgl1a_ph_reentry"
FUNGUS = f"{DATASET}__bgl1a_source"
ENVIRONMENT = f"{DATASET}__c30_ph5"
PREFIX = f"{DATASET}__bgl1a_source__beta_glucosidase__cellobiose__c30_ph5__"
TEMPLATE_ID = f"{DATASET}__beta_glucosidase__cellobiose__ph_ionization_mm_template"
COMPATIBILITY_ID = f"{DATASET}__beta_glucosidase__cellobiose__ph_ionization_mm"
PROCESS_TYPE = "ph_ionization_michaelis_menten"
# Line numbers of the fixture's kinetics.csv rows (the header is line 1).
ROW = {
    "kcat_limiting": 2,
    "km_limiting": 3,
    "pk_free_lower": 4,
    "pk_free_upper": 5,
    "pk_complex_lower": 6,
    "pk_complex_upper": 7,
    "ph_min": 8,
    "ph_max": 9,
    "substrate_initial_concentration": 10,
    "enzyme_concentration": 11,
}

# Entry 38522 constants and the fixture's design loadings, for the independent law below.
K0, KM0, PKE1, PKE2, PKES1, PKES2 = 1.81, 6.8, 4.4, 7.7, 4.1, 7.6
S0, E0 = 5.0, 1.0e-3  # mM


@pytest.fixture(scope="module")
def base_registry() -> FungModRegistry:
    return load_registry(REGISTRY_INDEX)


@pytest.fixture(scope="module")
def bgl1a(base_registry: FungModRegistry) -> UserDataset:
    return load_user_dataset(BGL1A, registry=base_registry)


# ---------------------------------------------------------------------------
# Helpers


def _ionization_factor(ph: float, lower: float, upper: float) -> float:
    return (10.0 ** (lower - ph) + 1.0) * (10.0 ** (ph - upper) + 1.0)


def _rate(ph: float, *, enzyme: float = E0, substrate: float = S0) -> float:
    """Initial rate of the diprotic law, written out here from its published form (mM/s)."""

    f_e = _ionization_factor(ph, PKE1, PKE2)
    f_es = _ionization_factor(ph, PKES1, PKES2)
    kcat = K0 / f_es
    km = KM0 * f_e / f_es
    return enzyme * kcat * substrate / (km + substrate)


def _copy_fixture(tmp_path: Path, source: Path = BGL1A, *, edits: Mapping[str, str | None] | None = None) -> Path:
    target = tmp_path / source.name
    shutil.copytree(source, target)
    for name, text in (edits or {}).items():
        path = target / name
        if text is None:
            path.unlink()
        else:
            path.write_text(text, encoding="utf-8")
    return target


def _set_cell(directory: Path, table: str, row: int, column: str, value: str) -> None:
    path = directory / table
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[row - 2][column] = value
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _append_rows(directory: Path, table: str, *lines: str) -> None:
    path = directory / table
    path.write_text(path.read_text(encoding="utf-8") + "".join(f"{line}\n" for line in lines), encoding="utf-8")


def _records(dataset: UserDataset, record_type: str) -> dict[str, Mapping[str, Any]]:
    return {str(mapping["record_id"]): mapping for mapping in dataset.records[record_type]}


def _parameter(dataset: UserDataset, record_id: str) -> ParameterRecord:
    return load_parameter_record_mapping(_records(dataset, "parameter_records")[record_id])


def _issues(directory: Path) -> list[dict[str, Any]]:
    with pytest.raises(UserDataError) as error:
        load_user_dataset(directory, registry=REGISTRY_INDEX)
    return error.value.issues


def _series(result: Any, role: str) -> dict[str, list[tuple[float, float]]]:
    series: dict[str, list[tuple[float, float]]] = {}
    for row in result.time_series():
        if row["state_role"] == role and row["sample_index"] in (0, "0"):
            series.setdefault(row["environment_id"], []).append((float(row["time"]), float(row["value"])))
    return series


def _solver_tolerances(result: Any) -> tuple[float, float]:
    sample = result.screen_result.case_results[0].samples[0]
    settings = json.loads((Path(sample.output_directory) / "solver_settings.json").read_text(encoding="utf-8"))
    return float(settings["solver_settings"]["rtol"]), float(settings["solver_settings"]["atol"])


# ---------------------------------------------------------------------------
# (a) The registry BGL1A law re-entered as user literature rows


def test_fixture_rows_are_the_registry_bgl1a_records_role_by_role(
    bgl1a: UserDataset, base_registry: FungModRegistry
) -> None:
    registry_roles = base_registry.process_compatibility[REGISTRY_COMPATIBILITY].parameter_roles
    user_roles = _records(bgl1a, "process_compatibility")[COMPATIBILITY_ID]["parameter_roles"]
    assert tuple(user_roles) == tuple(registry_roles) == PH_IONIZATION_MM_PARAMETER_ROLES
    records_by_symbol = {record.parameter_symbol: record for record in base_registry.parameters.values()}
    user_records = {
        mapping["parameter_symbol"]: load_parameter_record_mapping(mapping)
        for mapping in bgl1a.records["parameter_records"]
    }
    for role in PH_IONIZATION_MM_PARAMETER_ROLES:
        registry_record = records_by_symbol[registry_roles[role]]
        user_record = user_records[user_roles[role]]
        assert user_record.value.kind == registry_record.value.kind == "exact", role
        assert Q_(user_record.value.value, user_record.value.units).to(registry_record.value.units).magnitude == (
            pytest.approx(registry_record.value.value, rel=1e-12)
        ), role
        expected = "user_design_value" if role.endswith("_initial_concentration") else "user_reported_literature"
        assert user_record.maturity == expected, role
        assert user_record.process_type == PROCESS_TYPE
        assert user_record.environment_id == ENVIRONMENT


def test_generated_records_bind_the_ph_ionization_assembler(bgl1a: UserDataset) -> None:
    (enzyme_class,) = bgl1a.records["enzyme_classes"]
    assert enzyme_class["compatible_processes"] == [PROCESS_TYPE]
    assert "Restricted to pH-ionization Michaelis-Menten kinetics" in enzyme_class["notes"]
    compatibility = _records(bgl1a, "process_compatibility")[COMPATIBILITY_ID]
    assert compatibility["process_type"] == PROCESS_TYPE
    assert compatibility["case_template_id"] == TEMPLATE_ID
    expected_symbols = {
        "turnover": "kcat_limiting",
        "michaelis_constant": "km_limiting",
        "free_enzyme_lower_pk": "pk_free_lower",
        "free_enzyme_upper_pk": "pk_free_upper",
        "complex_lower_pk": "pk_complex_lower",
        "complex_upper_pk": "pk_complex_upper",
        "minimum_ph": "ph_min",
        "maximum_ph": "ph_max",
        "substrate_initial_concentration": "substrate_initial_concentration",
        "enzyme_initial_concentration": "enzyme_concentration",
    }
    assert compatibility["parameter_roles"] == {
        role: f"{DATASET}__{quantity}__beta_glucosidase__cellobiose" for role, quantity in expected_symbols.items()
    }
    template = _records(bgl1a, "case_templates")[TEMPLATE_ID]
    assert template["process_type"] == PROCESS_TYPE
    assert template["state_roles"] == {
        "substrate": "cellobiose_concentration",
        "product": "beta_D_glucose_concentration",
        "enzyme": "beta_glucosidase_concentration",
    }
    assert template["initial_state_mapping"]["enzyme"]["parameter_role"] == "enzyme_initial_concentration"
    metadata = template["process_state_metadata"]
    assert metadata["config_mode"] == "scientific"
    assert metadata["process_id"] == COMPATIBILITY_ID
    assert "process_modifiers" not in metadata
    limitations = " ".join(template["limitations"])
    assert "kcat(pH) = kcat_limiting / f_es(pH)" in limitations
    assert "not the kcat or Km at any one pH" in limitations
    assert any("ph_min to ph_max" in note for note in template["validity_notes"])
    record = _parameter(bgl1a, f"{PREFIX}kcat_limiting")
    assert record.provenance["fungmod_user_dataset"]["sd"] == 0.05
    assert "diprotic pH-ionization law" in record.provenance["validity_range"]
    assert set(PH_IONIZATION_QUANTITIES) <= {key.rsplit("__", 1)[1] for key in _records(bgl1a, "parameter_records")}


def test_reentered_law_reproduces_the_registry_bgl1a_trajectory(bgl1a: UserDataset, tmp_path: Path) -> None:
    """Same law, constants, loadings, time grid and Tsukada pH 5 assay: the same substrate trajectory.

    The registry case is exploratory only (its loadings are exploratory priors),
    so it runs one exploratory sample of exact values; the user case is
    scientific-eligible (literature constants, design loadings) and runs in
    scientific mode.
    """

    registry_study = virtual_experiment(
        fungi=REGISTRY_FUNGUS, substrates="cellobiose", environments=REGISTRY_ENVIRONMENT, registry=REGISTRY_INDEX
    )
    assert registry_study.preflight(mode="scientific")[0].status == "underparameterized"
    registry_result = registry_study.simulate(
        mode="exploratory", n_samples=1, seed=1, output_dir=tmp_path / "registry", quicklook=False
    )
    user_study = virtual_experiment(fungi="bgl1a_source", substrates="cellobiose", environments="c30_ph5", user_data=bgl1a)
    report = user_study.preflight(mode="scientific")[0]
    assert report.status == "modelable"
    assert report.required_processes == (PROCESS_TYPE,)
    user_result = user_study.simulate(mode="scientific", output_dir=tmp_path / "user", quicklook=False)
    rtol, atol = _solver_tolerances(user_result)
    assert (rtol, atol) == _solver_tolerances(registry_result)

    for role in ("substrate", "product"):
        (registry_series,) = _series(registry_result, role).values()
        (user_series,) = _series(user_result, role).values()
        assert len(user_series) == len(registry_series) == 145
        for (time_a, value_a), (time_b, value_b) in zip(user_series, registry_series, strict=True):
            assert time_a == time_b
            assert value_a == pytest.approx(value_b, rel=rtol, abs=atol)
    rows = [row for row in user_result.time_series() if row["state_role"] == "substrate"]
    assert {row["environment_effect_status"] for row in rows} == {"active_response_model"}
    assert {row["environment_response_model"] for row in rows} == {"ph:ph_ionization_michaelis_menten"}
    assert {row["units"] for row in rows} == {"millimolar"}

    # Independent check: the law integrated here, outside FungMod, at pH 5.
    (user_series,) = _series(user_result, "substrate").values()
    times = np.array([time for time, _value in user_series])
    reference = solve_ivp(
        lambda _t, y: [-_rate(5.0, substrate=y[0])], (times[0], times[-1]), [S0], t_eval=times, rtol=1e-10, atol=1e-12
    )
    np.testing.assert_allclose([value for _time, value in user_series], reference.y[0], rtol=1e-4, atol=1e-6)


def test_assembled_process_matches_the_registry_case_structure(
    bgl1a: UserDataset, base_registry: FungModRegistry, tmp_path: Path
) -> None:
    user_config = build_model_config_from_registry_case(
        fungus_id=FUNGUS,
        substrate_id="cellobiose",
        environment_id=ENVIRONMENT,
        registry=bgl1a.overlay(base_registry),
        mode="scientific",
        output_directory=str(tmp_path / "user"),
    ).to_dict()
    # The registry case assembles only through the exploratory screen; its config is in the snapshot.
    registry_config = json.loads(SNAPSHOTS.read_text(encoding="utf-8"))["bgl1a_ph5"]
    (user_process,) = user_config["processes"]
    (registry_process,) = registry_config["processes"]
    assert user_process["process_type"] == registry_process["process_type"] == PROCESS_TYPE
    assert set(user_process["parameters"]) == set(registry_process["parameters"])
    assert Q_(1.0, user_process["parameters"]["rate_units"]).to(registry_process["parameters"]["rate_units"]).magnitude == (
        pytest.approx(1.0)
    )
    assert user_process["modifiers"] == registry_process["modifiers"] == []
    assert set(user_process["states"]) == set(registry_process["states"]) == {"substrate", "product", "enzyme"}
    conditions = user_config["entities"]["environment"]["data"]["conditions"]
    assert set(conditions) == {"ph"} and conditions["ph"]["value"] == 5.0
    assert conditions["ph"] == {**registry_config["entities"]["environment"]["data"]["conditions"]["ph"], **{
        key: conditions["ph"][key] for key in ("source", "confidence_level", "notes")
    }}
    response = user_config["provenance"]["environment_response"]
    assert response["status"] == "active_response_model"
    assert set(response["conditions"]) == {"ph"}


def test_a_missing_role_of_a_started_pair_is_an_explicit_gap_with_a_request(tmp_path: Path) -> None:
    directory = _copy_fixture(tmp_path)
    lines = (directory / "kinetics.csv").read_text(encoding="utf-8").splitlines(keepends=True)
    (directory / "kinetics.csv").write_text(
        "".join(line for line in lines if ",pk_free_upper," not in line and ",ph_max," not in line), encoding="utf-8"
    )
    dataset = load_user_dataset(directory, registry=REGISTRY_INDEX)
    gap = _parameter(dataset, f"{PREFIX}pk_free_upper__gap")
    assert (gap.value.kind, gap.maturity, gap.process_type) == ("unknown", "user_dataset_gap", PROCESS_TYPE)
    assert gap.provenance["fungmod_user_dataset"]["required_dimension"] == "dimensionless"
    request = gap.provenance["measurement_request"]
    assert request.startswith("Measure the upper pK of the free enzyme (pk_free_upper) of beta-glucosidase")
    assert "pH series at the temperature of condition c30_ph5 (30 degC)" in request
    ph_max = _parameter(dataset, f"{PREFIX}ph_max__gap")
    assert "State the highest pH of the pH series" in ph_max.provenance["measurement_request"]
    assert _records(dataset, "case_templates")[TEMPLATE_ID]["process_state_metadata"]["config_mode"] == "exploratory"
    study = virtual_experiment(fungi="bgl1a_source", substrates="cellobiose", environments="c30_ph5", user_data=dataset)
    report = study.preflight(mode="exploratory")[0]
    assert report.status == "underparameterized"
    assert {item.item_id for item in report.missing} == {
        f"{DATASET}__pk_free_upper__beta_glucosidase__cellobiose",
        f"{DATASET}__ph_max__beta_glucosidase__cellobiose",
    }
    assert request in report.suggested_experiments


# ---------------------------------------------------------------------------
# (b) pH dependence over an EnvironmentGrid


def test_ph_grid_initial_rates_follow_the_ionization_factors(bgl1a: UserDataset, tmp_path: Path) -> None:
    grid = (4.0, 5.0, 6.0, 7.0, 8.0)
    study = virtual_experiment(
        fungi="bgl1a_source",
        substrates="cellobiose",
        environments=environment_grid(temperature_C=[30.0], ph=list(grid)),
        user_data=bgl1a,
    )
    assert [report.status for report in study.preflight(mode="scientific")] == ["modelable"] * len(grid)
    result = study.simulate(mode="scientific", output_dir=tmp_path / "grid", quicklook=False)
    rates: dict[float, float] = {}
    for row in result.time_series():
        assert row["environment_effect_status"] == "active_response_model"
        if row["state_role"] == "process_rate" and int(row["time_index"]) == 0:
            rates[float(row["ph"])] = float(row["value"])
    assert set(rates) == set(grid)
    # The ratio of initial rates is the law's own pH dependence at the common loadings.
    for ph in grid:
        assert rates[ph] / rates[5.0] == pytest.approx(_rate(ph) / _rate(5.0), rel=1e-9), ph
    assert rates[5.0] == pytest.approx(_rate(5.0), rel=1e-9)
    assert max(rates, key=rates.__getitem__) == 6.0
    # The factors differ by more than the solver tolerance, so the test resolves the law.
    assert len({round(rate, 12) for rate in rates.values()}) == len(grid)


def test_grid_ph_outside_the_fitted_range_warns_like_the_registry_case(bgl1a: UserDataset, tmp_path: Path) -> None:
    study = virtual_experiment(
        fungi="bgl1a_source",
        substrates="cellobiose",
        environments=environment_grid(temperature_C=[30.0], ph=[9.0]),
        user_data=bgl1a,
    )
    with pytest.warns(EnvironmentalValidityWarning, match="above pH 8.0"):
        study.simulate(mode="exploratory", n_samples=1, seed=1, output_dir=tmp_path / "ph9", quicklook=False)


# ---------------------------------------------------------------------------
# (c) Refusals


def _kinetics_line(quantity: str, value: str, units: str, *, strain: str = "bgl1a_source", lower: str = "", upper: str = "") -> str:
    return (
        f"{strain},beta_glucosidase,cellobiose,c30_ph5,{quantity},{value},{lower},{upper},{units},estimate,,"
        '"illustrative refusal probe, not a measurement",,'
    )


@pytest.mark.parametrize(
    ("edit", "expected"),
    [
        pytest.param(
            ("conditions.csv", 2, "ph", "4.5 to 5.5"),
            ("conditions.csv", 2, "ph", "ph must be a finite number or the word 'unknown'"),
            id="ranged_ph_condition",
        ),
        pytest.param(
            ("conditions.csv", 2, "ph", "unknown"),
            ("conditions.csv", 2, "ph", "has an unknown pH, but kinetics.csv rows 2"),
            id="unknown_ph_condition",
        ),
        pytest.param(
            ("conditions.csv", 2, "ph", "9.0"),
            ("conditions.csv", 2, "ph", "has pH 9.0, outside the pH range 4 to 8"),
            id="ph_outside_fitted_range",
        ),
        pytest.param(
            ("kinetics.csv", ROW["pk_free_lower"], "value", "7.9"),
            ("kinetics.csv", ROW["pk_free_upper"], "value", "pk_free_lower (7.9, row 4) must lie below pk_free_upper"),
            id="free_pk_order",
        ),
        pytest.param(
            ("kinetics.csv", ROW["pk_complex_upper"], "value", "4.1"),
            ("kinetics.csv", ROW["pk_complex_upper"], "value", "lower ionization of the enzyme-substrate complex"),
            id="complex_pk_equal",
        ),
        pytest.param(
            ("kinetics.csv", ROW["ph_min"], "value", "8.5"),
            ("kinetics.csv", ROW["ph_max"], "value", "ph_min (8.5, row 8) must be smaller than ph_max (8, row 9)"),
            id="ph_min_above_ph_max",
        ),
        pytest.param(
            ("kinetics.csv", ROW["ph_max"], "value", "15"),
            ("kinetics.csv", ROW["ph_max"], "value", "ph_max 15 is outside pH 0 to 14"),
            id="ph_max_off_scale",
        ),
        pytest.param(
            ("kinetics.csv", ROW["pk_free_lower"], "units", "mM"),
            ("kinetics.csv", ROW["pk_free_lower"], "units", "must be dimensionless"),
            id="pk_units",
        ),
        pytest.param(
            ("kinetics.csv", ROW["pk_free_lower"], "value", "nan"),
            ("kinetics.csv", ROW["pk_free_lower"], "value", "value must be a finite number"),
            id="pk_not_finite",
        ),
        pytest.param(
            ("kinetics.csv", ROW["kcat_limiting"], "units", "mM"),
            ("kinetics.csv", ROW["kcat_limiting"], "units", "kcat_limiting units 'mM' must have the dimension 1/time"),
            id="kcat_limiting_units",
        ),
    ],
)
def test_ph_ionization_refusals_name_file_row_column_and_reason(
    tmp_path: Path, edit: tuple[str, int, str, str], expected: tuple[str, int, str, str]
) -> None:
    directory = _copy_fixture(tmp_path)
    _set_cell(directory, *edit)
    issues = _issues(directory)
    file, row, column, text = expected
    matching = [issue for issue in issues if (issue["file"], issue["row"], issue["column"]) == (file, row, column)]
    assert matching, issues
    assert any(text in issue["message"] for issue in matching), matching


def test_ph_range_bounds_are_exact_and_pk_ranges_must_not_overlap(tmp_path: Path) -> None:
    directory = _copy_fixture(tmp_path)
    _set_cell(directory, "kinetics.csv", ROW["ph_min"], "value", "")
    _set_cell(directory, "kinetics.csv", ROW["ph_min"], "lower", "3.5")
    _set_cell(directory, "kinetics.csv", ROW["ph_min"], "upper", "4.5")
    _set_cell(directory, "kinetics.csv", ROW["pk_complex_lower"], "value", "")
    _set_cell(directory, "kinetics.csv", ROW["pk_complex_lower"], "lower", "4.0")
    _set_cell(directory, "kinetics.csv", ROW["pk_complex_lower"], "upper", "7.7")
    issues = {(issue["row"], issue["column"]): issue["message"] for issue in _issues(directory)}
    assert "exact value, not a range" in issues[(ROW["ph_min"], "lower")]
    message = issues[(ROW["pk_complex_upper"], "value")]
    assert "pk_complex_lower (4 to 7.7, row 6) must lie below pk_complex_upper (7.6, row 7)" in message
    assert "every sampled pair is ordered" in message

    # Non-overlapping ranges are accepted and sampled.
    _set_cell(directory, "kinetics.csv", ROW["ph_min"], "value", "4")
    _set_cell(directory, "kinetics.csv", ROW["ph_min"], "lower", "")
    _set_cell(directory, "kinetics.csv", ROW["ph_min"], "upper", "")
    _set_cell(directory, "kinetics.csv", ROW["pk_complex_lower"], "upper", "4.2")
    dataset = load_user_dataset(directory, registry=REGISTRY_INDEX)
    record = _parameter(dataset, f"{PREFIX}pk_complex_lower")
    assert (record.value.kind, record.value.lower, record.value.upper) == ("range", 4.0, 4.2)
    assert _records(dataset, "case_templates")[TEMPLATE_ID]["process_state_metadata"]["config_mode"] == "exploratory"


def test_mixed_rate_forms_are_refused_in_a_case_and_across_strains(tmp_path: Path) -> None:
    in_case = _copy_fixture(tmp_path / "case")
    _append_rows(in_case, "kinetics.csv", _kinetics_line("kcat", "1.2", "1/s"))
    (issue,) = [issue for issue in _issues(in_case) if issue["row"] == 12]
    assert issue["column"] == "quantity"
    assert "Row 12 gives kcat while rows 2, 3, 4, 5, 6, 7, 8, 9 give the pH-ionization quantities" in issue["message"]
    assert "one case uses one form" in issue["message"]

    vmax_case = _copy_fixture(tmp_path / "vmax")
    _append_rows(vmax_case, "kinetics.csv", _kinetics_line("vmax", "0.001", "mM/s").replace(",estimate,,", ",estimate,stated,"))
    assert any(issue["row"] == 12 and "pH-ionization" in issue["message"] for issue in _issues(vmax_case))

    across = _copy_fixture(tmp_path / "strains")
    _append_rows(across, "strains.csv", "second_source,Second beta-glucosidase source,,")
    _append_rows(across, "enzymes.csv", 'second_source,beta_glucosidase,activity assay,"illustrative, not a measurement"')
    _append_rows(
        across,
        "kinetics.csv",
        _kinetics_line("kcat", "1.2", "1/s", strain="second_source"),
        _kinetics_line("km", "6", "mM", strain="second_source"),
    )
    issues = _issues(across)
    # The kcat form comes first in the message; the rows of the other form are the ones flagged.
    assert [issue["row"] for issue in issues] == [ROW[quantity] for quantity in PH_IONIZATION_QUANTITIES]
    assert issues[0]["message"].startswith(
        "Enzyme class 'beta_glucosidase' on substrate 'cellobiose' uses the kcat form in row 12 and the "
        "pH-ionization form in row 2."
    )
    assert "must use one rate form" in issues[0]["message"]


def test_a_cardinal_ph_law_on_an_ionization_pair_is_refused_as_double_counting(tmp_path: Path) -> None:
    header = (
        "strain_id,enzyme_class,substrate_id,law,parameter,value,units,evidence_type,method,source,"
        "reference_tolerance,kinetics_at_reference"
    )
    binding = "bgl1a_source,beta_glucosidase,cellobiose"
    source = '"illustrative refusal probe, not a measurement"'
    ph_law = "\n".join(
        (
            header,
            f"{binding},ph_cardinal_rosso,minimum_ph,3,dimensionless,estimate,,{source},,",
            f"{binding},ph_cardinal_rosso,optimum_ph,5,dimensionless,estimate,,{source},,",
            f"{binding},ph_cardinal_rosso,maximum_ph,9,dimensionless,estimate,,{source},,",
        )
    )
    issues = _issues(_copy_fixture(tmp_path / "ph", edits={"responses.csv": ph_law + "\n"}))
    (issue,) = issues
    assert (issue["file"], issue["row"], issue["column"]) == ("responses.csv", 2, "law")
    assert "ph_cardinal_rosso binds a ph response" in issue["message"]
    assert "would count the ph effect twice" in issue["message"]

    # A temperature law is not double-counting: it binds as a process modifier, and the
    # limiting constants must be stated at its reference temperature.
    temperature_law = "\n".join(
        (
            header,
            f"{binding},temperature_cardinal_rosso,minimum_temperature,5,degC,estimate,,{source},,",
            f"{binding},temperature_cardinal_rosso,optimum_temperature,30,degC,estimate,,{source},,",
            f"{binding},temperature_cardinal_rosso,maximum_temperature,50,degC,estimate,,{source},,",
        )
    )
    dataset = load_user_dataset(
        _copy_fixture(tmp_path / "temperature", edits={"responses.csv": temperature_law + "\n"}), registry=REGISTRY_INDEX
    )
    template = _records(dataset, "case_templates")[TEMPLATE_ID]
    assert template["process_state_metadata"]["process_modifiers"][0]["type"] == "temperature_cardinal_rosso"
    assert "the pK values, the fitted pH range and the concentrations are not rescaled" in " ".join(
        template["limitations"]
    )
    off_reference = temperature_law.replace(",optimum_temperature,30,", ",optimum_temperature,35,")
    issues = _issues(_copy_fixture(tmp_path / "off", edits={"responses.csv": off_reference + "\n"}))
    assert any("are not at the reference condition" in issue["message"] for issue in issues), issues


def test_ranged_ph_reaching_assembly_is_refused_by_the_process_law_check(
    bgl1a: UserDataset, base_registry: FungModRegistry
) -> None:
    """A user condition cannot be a pH range (conditions.csv takes one number or unknown), and
    an EnvironmentGrid pH is always one number. Should an environment with a pH range reach the
    case anyway, assembly refuses it through PROCESS_ENVIRONMENT_CONDITIONS."""

    overlay = bgl1a.overlay(base_registry)
    environment = overlay.get_environment(ENVIRONMENT)
    ranged = dataclasses.replace(
        environment,
        record_id=f"{DATASET}__ranged_ph_probe",
        name="ranged pH probe",
        aliases=(),
        conditions={
            **environment.conditions,
            "ph": ValueSpec(kind="range", lower=4.0, upper=6.0, units="dimensionless", source="probe", confidence_level="user_supplied"),
        },
    )
    copies = [
        dataclasses.replace(record, record_id=f"{record.record_id}__probe", environment_id=ranged.record_id)
        for record in overlay.parameters.values()
        if record.environment_id == ENVIRONMENT
    ]
    registry = FungModRegistry.build(
        registry_id=overlay.registry_id,
        version=overlay.version,
        maturity=overlay.maturity,
        provenance=overlay.provenance,
        fungi=overlay.fungi.values(),
        enzyme_classes=overlay.enzyme_classes.values(),
        substrates=overlay.substrates.values(),
        environments=(*overlay.environments.values(), ranged),
        process_compatibility=overlay.process_compatibility.values(),
        parameters=(*overlay.parameters.values(), *copies),
        case_templates=overlay.case_templates.values(),
        product_maps=overlay.product_maps.values(),
    )
    with pytest.raises(RegistryCaseBuildError, match="requires exact environment condition 'ph'.*kind 'range'"):
        build_model_config_from_registry_case(
            fungus_id=FUNGUS, substrate_id="cellobiose", environment_id=ranged.record_id, registry=registry, mode="scientific"
        )


# ---------------------------------------------------------------------------
# (d) The SABIO-RK converter drafts entry 38522 in the pH-ionization form


def _fill_manifest(directory: Path, *, duration: float = 14400, units: str = "second", points: int = 145) -> None:
    path = directory / "user_dataset.yml"
    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    manifest["contributor"] = "Test reviewer"
    manifest["simulation"] = {"duration": duration, "units": units, "points": points}
    path.write_text(yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _raw_entry_38522() -> dict[str, Any]:
    data = json.loads(RAW_EXPORT.read_text(encoding="utf-8"))
    return next(entry for entry in data["data"] if entry["id"] == 38522)


def test_entry_38522_is_drafted_in_the_ph_ionization_form_and_loads_once_reviewed(
    bgl1a: UserDataset, tmp_path: Path
) -> None:
    draft = user_tables_from_sabiork(
        "618",
        dataset_id="entry_38522_draft",
        entry_ids=["38522"],
        design={
            "substrate_initial_concentration": {"value": S0, "units": "mM"},
            "enzyme_concentration": {"value": E0, "units": "mM"},
        },
    )
    assert draft.converted_entry_ids == ("38522",)
    rows = {row["quantity"]: row for row in draft.kinetics}
    assert list(rows) == [*PH_IONIZATION_QUANTITIES, "substrate_initial_concentration", "enzyme_concentration"]
    assert not {"km", "kcat"} & set(rows)
    raw = {item["name"]: item for item in _raw_entry_38522()["kineticlaw"]["parameter"]}
    for name, (_kind, quantity) in PH_IONIZATION_LAW_PARAMETERS.items():
        assert float(rows[quantity]["value"]) == raw[name]["start_value"], name
        assert float(rows[quantity]["sd"]) == raw[name]["standard_deviation"], name
        assert rows[quantity]["evidence_type"] == "literature"
        assert f"parameter {name}" in rows[quantity]["method"]
    assert (rows["kcat_limiting"]["units"], rows["km_limiting"]["units"]) == ("s^(-1)", "mM")
    assert {rows[quantity]["units"] for quantity in PH_IONIZATION_QUANTITIES[2:]} == {"dimensionless"}
    # The entry states its pH range (the law's pH variable runs from 4 to 8), so the range is not a review field.
    assert (rows["ph_min"]["value"], rows["ph_max"]["value"]) == ("4", "8")
    assert (raw["pH"]["start_value"], raw["pH"]["end_value"]) == (4, 8)
    assert "pH range of the law's pH variable" in rows["ph_min"]["method"]
    # The condition pH is a range in SABIO-RK and stays a review field, as before.
    (condition,) = draft.conditions
    assert condition["ph"].startswith(f"{REVIEW_MARKER} SABIO-RK gives pH 4 to 8, a range")
    assert "inside ph_min to ph_max" in condition["ph"]
    assert {(item["file"], item["column"]) for item in draft.review_fields} == {
        ("user_dataset.yml", "contributor"),
        ("user_dataset.yml", "simulation.duration"),
        ("user_dataset.yml", "simulation.units"),
        ("user_dataset.yml", "simulation.points"),
        ("conditions.csv", "ph"),
    }
    assert not any(item["parameter_type"] == "pKa" for item in draft.not_converted_parameters)
    section = draft.review.split("## pH-ionization laws", 1)[1].split("\n## ", 1)[0]
    assert "| 38522 | Michaelis-Menten (pH-dependent) | pKe1 = 4.4, pKe2 = 7.7, pKes1 = 4.1, pKes2 = 7.6 | pH-ionization form |" in section
    assert "not importable" not in draft.review

    directory = tmp_path / "draft"
    draft.write(directory)
    with pytest.raises(UserDataError, match="unfilled review fields"):
        load_user_dataset(directory)
    _fill_manifest(directory)
    _set_cell(directory, "conditions.csv", 2, "ph", "5.0")
    dataset = load_user_dataset(directory)
    prefix = "entry_38522_draft__phanerochaete_chrysosporium_in_escherichia_coli_rosetta_de3__beta_glucosidase__cellobiose__c30_ph4_to_8__"
    for quantity in PH_IONIZATION_QUANTITIES:
        record = _parameter(dataset, f"{prefix}{quantity}")
        assert record.process_type == PROCESS_TYPE
        assert record.maturity == "user_reported_literature"
        assert record.value.value == _parameter(bgl1a, f"{PREFIX}{quantity}").value.value

    trajectories = []
    for fungi, environments, user_data, label in (
        ("phanerochaete_chrysosporium_in_escherichia_coli_rosetta_de3", "c30_ph4_to_8", dataset, "drafted"),
        ("bgl1a_source", "c30_ph5", bgl1a, "fixture"),
    ):
        study = virtual_experiment(fungi=fungi, substrates="cellobiose", environments=environments, user_data=user_data)
        assert study.preflight(mode="scientific")[0].status == "modelable"
        result = study.simulate(mode="scientific", output_dir=tmp_path / label, quicklook=False)
        (series,) = _series(result, "substrate").values()
        trajectories.append(series)
    assert trajectories[0] == pytest.approx(trajectories[1], rel=1e-12)


def test_entry_38522_without_design_leaves_the_loadings_as_gaps(tmp_path: Path) -> None:
    draft = user_tables_from_sabiork("618", dataset_id="entry_38522_draft", entry_ids=["38522"])
    assert {item["parameter"] for item in draft.not_converted_parameters} == {"S", "E"}
    directory = tmp_path / "draft"
    draft.write(directory)
    _fill_manifest(directory)
    _set_cell(directory, "conditions.csv", 2, "ph", "6.5")
    study = virtual_experiment(
        fungi="phanerochaete_chrysosporium_in_escherichia_coli_rosetta_de3",
        substrates="cellobiose",
        environments="c30_ph4_to_8",
        user_data=directory,
    )
    report = study.preflight(mode="exploratory")[0]
    assert report.status == "underparameterized"
    assert {item.item_id.split("__")[1] for item in report.missing} == {
        "substrate_initial_concentration",
        "enzyme_concentration",
    }
    assert any("Specify the initial Cellobiose concentration" in text for text in report.suggested_experiments)


def _modified_export(tmp_path: Path, change: Any) -> Path:
    data = json.loads(RAW_EXPORT.read_text(encoding="utf-8"))
    entry = copy.deepcopy(next(item for item in data["data"] if item["id"] == 38522))
    change(entry)
    data["data"] = [entry]
    data["meta"] = {**data.get("meta", {}), "note": "modified copy of entry 38522 for a converter routing test"}
    path = tmp_path / "export" / "kinlaw_entries_modified.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_converter_lists_a_ph_law_of_another_form_and_reviews_a_missing_ph_range(tmp_path: Path) -> None:
    def other_formula(entry: dict[str, Any]) -> None:
        entry["kineticlaw"]["formula"] = entry["kineticlaw"]["formula"].replace("(10^(pH-pKe2)+1)", "1")

    export = _modified_export(tmp_path / "formula", other_formula)
    with pytest.raises(UserTablesSourceError, match="not the diprotic pH-ionization law FungMod implements"):
        user_tables_from_sabiork(export, dataset_id="other_formula")

    def no_range(entry: dict[str, Any]) -> None:
        for parameter in entry["kineticlaw"]["parameter"]:
            if parameter["name"] == "pH":
                parameter["end_value"] = None
        entry["experimental_conditions"]["envvar_ph"]["end_value"] = None

    draft = user_tables_from_sabiork(_modified_export(tmp_path / "range", no_range), dataset_id="no_range")
    rows = {row["quantity"]: row for row in draft.kinetics}
    for quantity in ("ph_min", "ph_max"):
        assert rows[quantity]["value"].startswith(REVIEW_MARKER)
        assert "SABIO-RK states no pH range for this entry" in rows[quantity]["value"]
    assert ("kinetics.csv", "value") in {(item["file"], item["column"]) for item in draft.review_fields}
    (condition,) = draft.conditions
    assert condition["ph"] == "4"


def test_converter_keeps_the_kcat_form_where_the_class_already_uses_it() -> None:
    draft = user_tables_from_sabiork("618", dataset_id="mixed", entry_ids=["38521", "38522"])
    assert draft.converted_entry_ids == ("38521",)
    (listed,) = draft.not_converted
    assert listed["entry_id"] == "38522"
    assert "uses the kcat or Vmax form on substrate 'cellobiose' in EntryIDs 38521" in listed["reason"]
    assert {row["quantity"] for row in draft.kinetics} >= {"km", "kcat"}
    assert not set(PH_IONIZATION_QUANTITIES) & {row["quantity"] for row in draft.kinetics}


# ---------------------------------------------------------------------------
# (e) Non-specific: a user-defined class and substrate with estimates


SOURCE = '"FungMod pH-ionization route probe; illustrative estimates, not measurements"'
CASE = "strain_p1,acid_phosphatase_like,aryl_phosphate_s1,c37_ph5"
PHOSPHATASE_TABLES = {
    "user_dataset.yml": (
        "dataset_id: phosphatase_demo\n"
        "contributor: FungMod maintainers\n"
        "date: 2026-10-06\n"
        "source: Illustrative estimates for the user-data pH-ionization route; not measurements.\n"
        "simulation:\n  duration: 1\n  units: hour\n  points: 61\n"
    ),
    "strains.csv": "strain_id,name,scientific_name,aliases\nstrain_p1,Phosphatase source strain P1,,\n",
    "enzyme_classes.csv": (
        "class_id,name,ec_number,target_bond_classes,compatible_substrate_classes,source\n"
        f"acid_phosphatase_like,acid phosphatase-like enzyme,3.1.3.2,phosphomonoester,aryl_phosphate;alkyl_phosphate,{SOURCE}\n"
    ),
    "enzymes.csv": f"strain_id,enzyme_class,evidence,source\nstrain_p1,acid_phosphatase_like,activity assay,{SOURCE}\n",
    "substrates.csv": (
        "substrate_id,registry_substrate,name,substrate_class,physical_state,bond_classes,product,product_yield,"
        "yield_basis,source\n"
        f"aryl_phosphate_s1,,model aryl phosphate monoester,aryl_phosphate,dissolved,phosphomonoester,aryl_alcohol_p1,1,"
        f"mol/mol,{SOURCE}\n"
    ),
    "conditions.csv": "condition_id,temperature,temperature_units,ph,notes\nc37_ph5,37,degC,5.0,\n",
    "kinetics.csv": "\n".join(
        (
            "strain_id,enzyme_class,substrate_id,condition_id,quantity,value,lower,upper,units,evidence_type,method,source,sd,replicates",
            f"{CASE},kcat_limiting,,20,40,1/s,estimate,,{SOURCE},,",
            f"{CASE},km_limiting,0.3,,,mM,estimate,,{SOURCE},,",
            f"{CASE},pk_free_lower,3.6,,,dimensionless,estimate,,{SOURCE},,",
            f"{CASE},pk_free_upper,6.2,,,dimensionless,estimate,,{SOURCE},,",
            f"{CASE},pk_complex_lower,,3.0,3.4,dimensionless,estimate,,{SOURCE},,",
            f"{CASE},pk_complex_upper,6.6,,,dimensionless,estimate,,{SOURCE},,",
            f"{CASE},ph_min,3,,,dimensionless,estimate,,{SOURCE},,",
            f"{CASE},ph_max,7,,,dimensionless,estimate,,{SOURCE},,",
            f"{CASE},substrate_initial_concentration,1,,,mM,estimate,,{SOURCE},,",
            f"{CASE},enzyme_concentration,0.01,,,uM,estimate,,{SOURCE},,",
        )
    )
    + "\n",
}
SECOND_SUBSTRATE = (
    f"alkyl_phosphate_s2,,model alkyl phosphate monoester,alkyl_phosphate,dissolved,phosphomonoester,alkanol_p2,1,"
    f"mol/mol,{SOURCE}"
)


def _phosphatase(tmp_path: Path, **edits: str) -> Path:
    directory = tmp_path / "phosphatase_demo"
    directory.mkdir(parents=True)
    for name, text in {**PHOSPHATASE_TABLES, **edits}.items():
        (directory / name).write_text(text, encoding="utf-8")
    return directory


def test_user_defined_class_and_substrate_run_the_ionization_form_in_exploratory_mode(tmp_path: Path) -> None:
    dataset = load_user_dataset(_phosphatase(tmp_path), registry=REGISTRY_INDEX)
    template_id = "phosphatase_demo__acid_phosphatase_like__aryl_phosphate_s1__ph_ionization_mm_template"
    template = _records(dataset, "case_templates")[template_id]
    assert template["process_type"] == PROCESS_TYPE
    assert template["process_state_metadata"]["config_mode"] == "exploratory"
    record = _parameter(dataset, "phosphatase_demo__strain_p1__acid_phosphatase_like__aryl_phosphate_s1__c37_ph5__kcat_limiting")
    assert (record.value.kind, record.maturity, record.provenance["exploratory_prior"]) == ("range", "exploratory_prior", True)

    study = virtual_experiment(
        fungi="strain_p1",
        substrates="model aryl phosphate monoester",
        environments=environment_grid(temperature_C=[37.0], ph=[3.5, 5.0, 6.5]),
        user_data=dataset,
    )
    assert [report.status for report in study.preflight(mode="exploratory")] == ["exploratory"] * 3
    with pytest.raises(VirtualExperimentError, match="Scientific simulation requires exact"):
        study.simulate(mode="scientific", output_dir=tmp_path / "blocked", quicklook=False)
    result = study.simulate(mode="exploratory", n_samples=4, seed=17, output_dir=tmp_path / "run", quicklook=False)
    sampled = {row["role"]: row["parameter_source_class"] for row in result.sampled_parameters()}
    assert set(sampled) == set(PH_IONIZATION_MM_PARAMETER_ROLES)
    assert set(sampled.values()) == {"user_supplied_exploratory_prior"}
    substrate: dict[tuple[str, str], list[float]] = {}
    for row in result.time_series():
        assert row["environment_effect_status"] == "active_response_model"
        if row["state_role"] == "substrate":
            substrate.setdefault((row["environment_id"], str(row["sample_index"])), []).append(float(row["value"]))
    assert len(substrate) == 3 * 4
    for values in substrate.values():
        assert values[0] == pytest.approx(1.0)
        assert values[-1] < values[0]
        assert all(later <= earlier + 1e-12 for earlier, later in zip(values, values[1:]))
    # The sampled pK pair of the complex stays ordered in every sample.
    sampled_pk = {
        (row["environment_id"], row["sample_index"], row["role"]): float(row["sampled_value"])
        for row in result.sampled_parameters()
        if row["role"] in {"complex_lower_pk", "complex_upper_pk"}
    }
    lower = [value for key, value in sampled_pk.items() if key[2] == "complex_lower_pk"]
    assert len(lower) == 3 * 4 and all(3.0 <= value <= 3.4 for value in lower)
    assert len(set(lower)) > 1
    assert all(value < sampled_pk[(key[0], key[1], "complex_upper_pk")] for key, value in sampled_pk.items() if key[2] == "complex_lower_pk")


def test_an_unstarted_pair_of_an_ionization_class_takes_the_ionization_form(tmp_path: Path) -> None:
    substrates = PHOSPHATASE_TABLES["substrates.csv"] + SECOND_SUBSTRATE + "\n"
    dataset = load_user_dataset(_phosphatase(tmp_path, **{"substrates.csv": substrates}), registry=REGISTRY_INDEX)
    (enzyme_class,) = dataset.records["enzyme_classes"]
    assert enzyme_class["compatible_processes"] == [PROCESS_TYPE]
    compatibilities = _records(dataset, "process_compatibility")
    assert {mapping["process_type"] for mapping in compatibilities.values()} == {PROCESS_TYPE}
    gap = _parameter(
        dataset, "phosphatase_demo__strain_p1__acid_phosphatase_like__alkyl_phosphate_s2__c37_ph5__pk_free_lower__gap"
    )
    request = gap.provenance["measurement_request"]
    assert request == (
        "Measure the lower pK of the free enzyme (pk_free_lower) of acid phosphatase-like enzyme from Phosphatase "
        "source strain P1 on model alkyl phosphate monoester (dimensionless) by fitting the diprotic pH-ionization "
        "law to initial rates over a pH series at the temperature of condition c37_ph5 (37 degC)."
    )
    # The started pair is unaffected: the class lists one process law, found on both substrates.
    study = virtual_experiment(
        fungi="strain_p1", substrates="model aryl phosphate monoester", environments="c37_ph5", user_data=dataset
    )
    report = study.preflight(mode="exploratory")[0]
    assert report.status == "exploratory"
    assert not report.incompatible


def test_a_class_mixing_the_ionization_form_with_another_form_is_refused(tmp_path: Path) -> None:
    substrates = PHOSPHATASE_TABLES["substrates.csv"] + SECOND_SUBSTRATE + "\n"
    second = "strain_p1,acid_phosphatase_like,alkyl_phosphate_s2,c37_ph5"
    kinetics = PHOSPHATASE_TABLES["kinetics.csv"] + "\n".join(
        (
            f"{second},km,0.5,,,mM,estimate,,{SOURCE},,",
            f"{second},kcat,10,,,1/s,estimate,,{SOURCE},,",
        )
    ) + "\n"
    issues = _issues(_phosphatase(tmp_path, **{"substrates.csv": substrates, "kinetics.csv": kinetics}))
    (issue,) = issues
    assert (issue["file"], issue["row"], issue["column"]) == ("kinetics.csv", 2, "quantity")
    assert "uses the pH-ionization form on substrate 'aryl_phosphate_s1'" in issue["message"]
    assert "'alkyl_phosphate_s2' (kcat form)" in issue["message"]
    assert "on all of its substrates or on none" in issue["message"]


def test_rate_form_constant_is_public() -> None:
    assert RATE_FORM_PH_IONIZATION == "ph_ionization"
    assert PH_IONIZATION_QUANTITIES == (
        "kcat_limiting",
        "km_limiting",
        "pk_free_lower",
        "pk_free_upper",
        "pk_complex_lower",
        "pk_complex_upper",
        "ph_min",
        "ph_max",
    )
