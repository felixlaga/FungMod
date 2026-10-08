"""Temperature and pH response laws inside enzyme networks (NETWORK-003).

A ``responses.csv`` row names a strain, an enzyme class and a substrate; in a
dataset with an ``enzyme_network`` block that is the network process of that
class on that pool. The law binds to that process exactly as it binds to a
single-class case: through the existing environment modifier of the
composition builder, with the kinetic constants (and, in a network, the
process's ``ki``) required at the law's reference condition, law records valid
at every environment (so the law reaches ``EnvironmentGrid`` conditions), and
``active_response_model`` reported. A process without a law keeps the
constants of its rows' condition, and its template says so.

``tests/fixtures/user_data/network_chain_laws`` is the ``network_chain`` network
(a soluble polymer-like pool cut into an oligomer-like pool, cut into a
monomer-like product) with a cardinal temperature and a cardinal pH law on the
first class and an Arrhenius law on the second. The materially different case
is derived in a temporary directory from ``network_solid_chain``: a cardinal pH
law on the class that cuts a cellulose-like solid (g/L) into a dissolved
disaccharide-like pool (mmol/L through a stated yield), while the competitively
inhibited second class carries no law. Every value is an illustrative estimate.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import shutil
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from fungal_model import UserDataError, UserDataset, environment_grid, load_user_dataset, virtual_experiment
from fungal_model.api import VirtualExperimentError
from fungal_model.api.user_data import USER_DATASET_MATURITY_GAP
from fungal_model.cli import EXIT_OK, EXIT_USAGE, main
from fungal_model.provenance import USER_DATASET_PROVENANCE_KEY
from fungal_model.registry import load_registry
from fungal_model.registry.loaders import load_parameter_record_mapping
from fungal_model.registry.records import PARAMETER_ALLOWED_USE_EXPLORATORY, PARAMETER_ALLOWED_USE_GAP_ANALYSIS_ONLY
from fungal_model.screening.case_builder import (
    build_registry_process_config_data,
    get_registry_process_assembler,
    select_registry_case_compatibility,
)
from fungal_model.screening.ensemble import _sample_role_records, resolve_screen_role_records
from fungal_model.screening.modelability import assess_modelability

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"
FIXTURES = ROOT / "tests" / "fixtures" / "user_data"
LAWS = FIXTURES / "network_chain_laws"
CHAIN = FIXTURES / "network_chain"
SOLID_CHAIN = FIXTURES / "network_solid_chain"
OXIDASE = FIXTURES / "oxidase_case"

LAWS_ID = "network_chain_laws"
DEPOLYMERASE = "depolymerase_like"
OLIGOMER_HYDROLASE = "oligomer_hydrolase_like"
PROCESS_A = f"{LAWS_ID}__{DEPOLYMERASE}__polymer_p1__homogeneous_mm"
PROCESS_B = f"{LAWS_ID}__{OLIGOMER_HYDROLASE}__oligomer_o1__homogeneous_mm"
SOLID_ID = "network_solid_chain"
CUTTER = "solid_cutter_like"
HYDROLASE = "dimer_hydrolase_like"
SOLID_PROCESS_A = f"{SOLID_ID}__{CUTTER}__solid_c3__homogeneous_mm"
SOLID_PROCESS_B = f"{SOLID_ID}__{HYDROLASE}__dimer_d3__homogeneous_mm"

# The chain's constants at their reference condition (30 degC, pH 5): mM and mM/min.
KM_A, VMAX_A = 2.0, 30.0 * 0.002
KM_B, VMAX_B = 1.0, 60.0 * 0.001
S0, Y1, Y2 = 5.0, 4.0, 2.0
# The laws of the fixture: CTMI (degC), CPM and Arrhenius (J/mol, degC).
T_MIN, T_OPT, T_MAX = 5.0, 30.0, 45.0
PH_MIN, PH_OPT, PH_MAX = 3.0, 5.0, 8.0
ACTIVATION_ENERGY, T_REF = 50000.0, 30.0
GAS_CONSTANT = 8.31446261815324  # J/(mol K), exact in the 2019 SI (N_A x k_B)
# The solid chain's constants (g/L, g/L/h, mmol/g, mM, mM/h) and the pH law derived for it.
SOLID_S0, SOLID_KM_A, SOLID_VMAX_A = 10.0, 8.0, 0.02 * 20.0
SOLID_YIELD, SOLID_Y2 = 3.0838, 2.0
SOLID_KM_B, SOLID_VMAX_B, SOLID_KI_B = 1.2, 50.0 * 0.00002 * 3600.0, 3.0
SOLID_PH_MIN, SOLID_PH_OPT, SOLID_PH_MAX = 3.0, 5.0, 7.5

# SHA-256 of json.dumps(to_dict()["records"], sort_keys=True) and of yaml.safe_dump(config, sort_keys=False) (ranged
# records at their lower bounds, output directory "<OUTPUT_ROOT>") of the NETWORK-002 fixtures, computed with the base
# commit of NETWORK-003 (b8e3abe): a network without responses.csv generates and assembles exactly as before. The
# earlier fixtures and the shipped registry cases are pinned by tests/test_user_data_network_cross_basis.py.
NETWORK_002_RECORD_DIGESTS = {
    "network_solid_chain": "89a983b30d7517d5e50cace7ca3723c47b208c6667ed4f2d3cc46fa0151e10a6",
    "network_solid_parallel": "ca5e8ad5685453f283cf72d4547b05b7d6f12f52eea72667ec6a94c24a831104",
}
NETWORK_002_CONFIG_DIGESTS = {
    "network_solid_chain": {
        "network_solid_chain__strain_s3|network_solid_chain__solid_c3|network_solid_chain__c45_ph5|exploratory": (
            "b3079cd82f2e8be3e31016f54ddd829d066c31d6119c658af796ee0b28ad828b"
        ),
    },
    "network_solid_parallel": {
        "network_solid_parallel__strain_r4|network_solid_parallel__solid_k4|network_solid_parallel__c37_ph6|exploratory": (
            "3daa37f475efd3b2b69aec6a0e335c403a15836fcbe42a75fb4aa630734124ab"
        ),
    },
}

RESPONSES_HEADER = (
    "strain_id",
    "enzyme_class",
    "substrate_id",
    "law",
    "parameter",
    "value",
    "units",
    "evidence_type",
    "method",
    "source",
    "reference_tolerance",
    "kinetics_at_reference",
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


def _response(class_key: str, substrate: str, law: str, parameter: str, value: str, units: str, **cells: str) -> dict[str, str]:
    strain = cells.pop("strain_id", "strain_n1")
    return {
        "strain_id": strain,
        "enzyme_class": class_key,
        "substrate_id": substrate,
        "law": law,
        "parameter": parameter,
        "value": value,
        "units": units,
        "evidence_type": "estimate",
        "source": "Illustrative test note NW-3 p. 1",
        **cells,
    }


def _responses(*rows: Mapping[str, str]) -> str:
    return _csv_text(rows, RESPONSES_HEADER)


def _laws_responses(change: Mapping[tuple[str, str], Mapping[str, str]] | None = None) -> list[dict[str, str]]:
    """The fixture's responses.csv rows with cells of (law, parameter) rows replaced."""

    return [{**row, **(change or {}).get((row["law"], row["parameter"]), {})} for row in _rows(LAWS, "responses.csv")]


def _manifest(source: Path, **changes: Any) -> str:
    data = yaml.safe_load((source / "user_dataset.yml").read_text(encoding="utf-8"))
    for key, value in changes.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    return yaml.safe_dump(data, sort_keys=False)


def _parameter_records(dataset: UserDataset) -> dict[str, Mapping[str, Any]]:
    return {str(item["record_id"]): item for item in dataset.records["parameter_records"]}


def _series(result: Any) -> dict[tuple[str, str], tuple[np.ndarray, np.ndarray, str]]:
    """(environment id, state role or rate key) -> (times, values, units) of sample 0."""

    series: dict[tuple[str, str], list[tuple[float, float, str]]] = {}
    for row in result.time_series():
        if row["sample_index"] != "0":
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


def _conditions(result: Any) -> dict[str, tuple[float, float, set[str]]]:
    """Environment id -> (temperature in degC, pH, environment_effect_status values) of the simulated cases."""

    found: dict[str, tuple[float, float, set[str]]] = {}
    for row in result.time_series():
        environment = row["environment_id"]
        temperature, ph, statuses = found.get(environment, (float(row["temperature_C"]), float(row["ph"]), set()))
        statuses.add(row["environment_effect_status"])
        found[environment] = (temperature, ph, statuses)
    return found


def _simulate(tmp_path: Path, user_data: Path | UserDataset, *, fungus: str, substrate: str, environments: Any) -> Any:
    study = virtual_experiment(
        fungi=[fungus], substrates=[substrate], environments=environments, registry=REGISTRY_INDEX, user_data=user_data
    )
    return study.simulate(mode="exploratory", n_samples=1, seed=1, output_dir=tmp_path, quicklook=False)


def _cli(capsys: pytest.CaptureFixture[str], *args: str | Path) -> tuple[int, str, str]:
    code = main([str(arg) for arg in args])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _ctmi(temperature: float, minimum: float = T_MIN, optimum: float = T_OPT, maximum: float = T_MAX) -> float:
    """Rosso et al. (1993) cardinal temperature model with inflection, computed here, not imported."""

    if temperature <= minimum or temperature >= maximum:
        return 0.0
    numerator = (temperature - maximum) * (temperature - minimum) ** 2
    denominator = (optimum - minimum) * (
        (optimum - minimum) * (temperature - optimum) - (optimum - maximum) * (optimum + minimum - 2.0 * temperature)
    )
    return numerator / denominator


def _cpm(ph: float, minimum: float = PH_MIN, optimum: float = PH_OPT, maximum: float = PH_MAX) -> float:
    """Rosso et al. (1995) cardinal pH model, computed here, not imported."""

    if ph <= minimum or ph >= maximum:
        return 0.0
    numerator = (ph - minimum) * (ph - maximum)
    return numerator / (numerator - (ph - optimum) ** 2)


def _arrhenius(temperature: float) -> float:
    return math.exp(-ACTIVATION_ENERGY / GAS_CONSTANT * (1.0 / (temperature + 273.15) - 1.0 / (T_REF + 273.15)))


@pytest.fixture(scope="module")
def laws() -> UserDataset:
    return load_user_dataset(LAWS, registry=REGISTRY_INDEX)


@pytest.fixture(scope="module")
def grid_run(tmp_path_factory: pytest.TempPathFactory) -> Any:
    return _simulate(
        tmp_path_factory.mktemp("network_laws_grid"),
        LAWS,
        fungus="strain_n1",
        substrate="polymer_p1",
        environments=environment_grid(temperature_C=[30, 37], ph=[5.0, 5.5]),
    )


def _solid_ph_law(tmp_path: Path) -> Path:
    responses = _responses(
        _response(CUTTER, "solid_c3", "ph_cardinal_rosso", "minimum_ph", "3", "dimensionless", strain_id="strain_s3"),
        _response(CUTTER, "solid_c3", "ph_cardinal_rosso", "optimum_ph", "5", "dimensionless", strain_id="strain_s3"),
        _response(CUTTER, "solid_c3", "ph_cardinal_rosso", "maximum_ph", "7.5", "dimensionless", strain_id="strain_s3"),
    )
    return _copy_fixture(tmp_path, SOLID_CHAIN, edits={"responses.csv": responses})


# ---------------------------------------------------------------------------
# What the laws generate


def test_each_law_binds_to_the_process_of_its_class_and_pool(laws: UserDataset) -> None:
    (network,) = laws.enzyme_networks
    assert [(item["enzyme_class"], item["pool"], item["response_laws"]) for item in network["processes"]] == [
        (DEPOLYMERASE, "polymer_p1", ["temperature_cardinal_rosso", "ph_cardinal_rosso"]),
        (OLIGOMER_HYDROLASE, "oligomer_o1", ["temperature_arrhenius_reference"]),
    ]
    (template,) = laws.records["case_templates"]
    processes = {item["id"]: item for item in template["process_state_metadata"]["process_templates"]}
    # The existing environment modifiers, as in single-class templates, with the network's per-process roles.
    assert processes[PROCESS_A]["modifiers"] == [
        {
            "type": "temperature_cardinal_rosso",
            "minimum_temperature_role": f"temperature_cardinal_rosso__minimum_temperature__{DEPOLYMERASE}__polymer_p1",
            "optimum_temperature_role": f"temperature_cardinal_rosso__optimum_temperature__{DEPOLYMERASE}__polymer_p1",
            "maximum_temperature_role": f"temperature_cardinal_rosso__maximum_temperature__{DEPOLYMERASE}__polymer_p1",
        },
        {
            "type": "ph_cardinal_rosso",
            "minimum_ph_role": f"ph_cardinal_rosso__minimum_ph__{DEPOLYMERASE}__polymer_p1",
            "optimum_ph_role": f"ph_cardinal_rosso__optimum_ph__{DEPOLYMERASE}__polymer_p1",
            "maximum_ph_role": f"ph_cardinal_rosso__maximum_ph__{DEPOLYMERASE}__polymer_p1",
        },
    ]
    assert processes[PROCESS_B]["modifiers"] == [
        {
            "type": "temperature_arrhenius_reference",
            "activation_energy_role": (
                f"temperature_arrhenius_reference__activation_energy__{OLIGOMER_HYDROLASE}__oligomer_o1"
            ),
            "reference_temperature_role": (
                f"temperature_arrhenius_reference__reference_temperature__{OLIGOMER_HYDROLASE}__oligomer_o1"
            ),
        }
    ]
    (compatibility,) = laws.records["process_compatibility"]
    law_roles = {role for role in compatibility["parameter_roles"] if "rosso" in role or "arrhenius" in role}
    assert len(law_roles) == 8
    assert all(
        compatibility["parameter_roles"][role] == f"{LAWS_ID}__network__polymer_p1__{role}" for role in law_roles
    )


def test_law_records_are_the_single_class_records_valid_at_every_environment(laws: UserDataset) -> None:
    records = _parameter_records(laws)
    role = f"temperature_cardinal_rosso__optimum_temperature__{DEPOLYMERASE}__polymer_p1"
    optimum = load_parameter_record_mapping(records[f"{LAWS_ID}__network__polymer_p1__strain_n1__{role}"])
    assert (optimum.value.value, optimum.value.units) == (pytest.approx(303.15), "kelvin")
    assert "Original value 30 degC converted to kelvin" in optimum.notes
    assert optimum.environment_id is None, "a law applies at every environment, EnvironmentGrid conditions included"
    assert optimum.parameter_symbol == f"{LAWS_ID}__network__polymer_p1__{role}"
    assert (optimum.process_type, optimum.enzyme_class) == ("enzyme_network", None)
    assert optimum.fungus_id == f"{LAWS_ID}__strain_n1"
    assert optimum.maturity == "exploratory_prior"
    assert optimum.allowed_use == PARAMETER_ALLOWED_USE_EXPLORATORY
    user = optimum.provenance[USER_DATASET_PROVENANCE_KEY]
    assert (user["file"], user["row"], user["law"], user["parameter"]) == (
        "responses.csv",
        3,
        "temperature_cardinal_rosso",
        "optimum_temperature",
    )
    assert user["reference_condition"]["kinetics_conditions"] == ["c30_ph5"]
    assert user["enzyme_network"] == {
        "entry_substrate": "polymer_p1",
        "role": role,
        "enzyme_class": f"{LAWS_ID}__{DEPOLYMERASE}",
        "pool": "polymer_p1",
    }
    energy = records[
        f"{LAWS_ID}__network__polymer_p1__strain_n1__temperature_arrhenius_reference__activation_energy__"
        f"{OLIGOMER_HYDROLASE}__oligomer_o1"
    ]
    assert (energy["value"]["value"], energy["value"]["units"]) == (50.0, "kJ/mol")
    # The kinetic constants of a process with a law say that the law rescales them away from its reference.
    km = records[f"{LAWS_ID}__network__polymer_p1__strain_n1__c30_ph5__km__{DEPOLYMERASE}__polymer_p1"]
    assert "temperature_cardinal_rosso, ph_cardinal_rosso from responses.csv rescale the rate" in km["provenance"][
        "validity_range"
    ]
    initial = records[f"{LAWS_ID}__network__polymer_p1__strain_n1__c30_ph5__substrate_initial_concentration"]
    assert "no temperature or pH response law is attached" in initial["provenance"]["validity_range"]


def test_the_template_says_which_process_each_law_scales(laws: UserDataset, tmp_path: Path) -> None:
    (template,) = laws.records["case_templates"]
    limitations = template["limitations"]
    assert "no temperature or pH response law is bound" not in " ".join(limitations)
    assert "This is an enzyme-kinetics case, not a whole-fungus growth, secretion or uptake model." in limitations
    assert any(
        text.startswith("Response laws from responses.csv scale the rate of Depolymerase-like class N1 on Soluble")
        and "no condition other than pH and temperature acts on it" in text
        for text in limitations
    )
    assert any(
        text.startswith("Response laws from responses.csv scale the rate of Oligomer hydrolase-like class N1")
        and "temperature_arrhenius_reference" in text
        for text in limitations
    )
    # A network without responses keeps the earlier limitation, word for word.
    (plain,) = load_user_dataset(CHAIN, registry=REGISTRY_INDEX).records["case_templates"]
    assert plain["limitations"][4] == (
        "This is an enzyme-kinetics case, not a whole-fungus growth, secretion or uptake model; no temperature or pH "
        "response law is bound, so the values apply at the condition of their rows only."
    )
    # A process without a law in a network with laws keeps its rows' condition, and says so.
    solid = load_user_dataset(_solid_ph_law(tmp_path), registry=REGISTRY_INDEX)
    (solid_template,) = solid.records["case_templates"]
    assert (
        "No temperature or pH response law is bound to Dimer hydrolase-like class S3 on Disaccharide-like pool D3: its "
        "constants apply at the condition of their rows only"
    ) in " ".join(solid_template["limitations"])


@pytest.mark.parametrize("fixture", sorted(NETWORK_002_RECORD_DIGESTS))
def test_networks_without_responses_generate_and_assemble_as_before(fixture: str) -> None:
    dataset = load_user_dataset(FIXTURES / fixture, registry=REGISTRY_INDEX)
    digest = hashlib.sha256(json.dumps(dataset.to_dict()["records"], sort_keys=True).encode("utf-8")).hexdigest()
    assert digest == NETWORK_002_RECORD_DIGESTS[fixture]
    assert all(process["response_laws"] == [] for item in dataset.enzyme_networks for process in item["processes"])
    registry = dataset.overlay(load_registry(REGISTRY_INDEX))
    digests: dict[str, str] = {}
    for fungus in (item["record_id"] for item in dataset.records["fungi"]):
        for substrate in (item["record_id"] for item in dataset.records["substrates"]):
            for environment in (item["record_id"] for item in dataset.records["environments"]):
                report = assess_modelability(
                    fungus_id=fungus, substrate_id=substrate, environment_id=environment, registry=registry, mode="exploratory"
                )
                if report.status not in {"modelable", "exploratory"}:
                    continue
                compatibility = select_registry_case_compatibility(
                    registry=registry, fungus_id=fungus, substrate_id=substrate, report=report
                )
                assert get_registry_process_assembler(compatibility.process_type) is not None
                records = resolve_screen_role_records(
                    registry=registry,
                    compatibility=compatibility,
                    fungus_id=fungus,
                    substrate_id=substrate,
                    environment_id=environment,
                    mode="exploratory",
                )
                records = _sample_role_records(records, rng=_LowerBound(), sample_index=0)  # type: ignore[arg-type]
                data = build_registry_process_config_data(
                    registry=registry,
                    compatibility=compatibility,
                    fungus_id=fungus,
                    substrate_id=substrate,
                    environment_id=environment,
                    parameter_records=records,
                    output_directory="<OUTPUT_ROOT>",
                )
                text = yaml.safe_dump(data, sort_keys=False)
                digests[f"{fungus}|{substrate}|{environment}|exploratory"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert digests == NETWORK_002_CONFIG_DIGESTS[fixture]


class _LowerBound:
    """A stand-in random generator: every ranged record is taken at its lower bound."""

    def uniform(self, low: float, high: float) -> float:
        del high
        return low


# ---------------------------------------------------------------------------
# Simulation: each process rate is its own law times its own modifiers


def test_each_process_rate_is_its_own_law_times_its_modifiers_on_the_grid(grid_run: Any) -> None:
    series = _series(grid_run)
    conditions = _conditions(grid_run)
    assert {(temperature, ph) for temperature, ph, _statuses in conditions.values()} == {
        (30.0, 5.0),
        (30.0, 5.5),
        (37.0, 5.0),
        (37.0, 5.5),
    }
    for environment, (temperature, ph, statuses) in conditions.items():
        assert statuses == {"active_response_model"}
        _, polymer, _ = series[(environment, "substrate")]
        _, oligomer, _ = series[(environment, "intermediate_1")]
        _, monomer, _ = series[(environment, "product")]
        rate_a = series[(environment, f"process_rate.{PROCESS_A}")][1]
        rate_b = series[(environment, f"process_rate.{PROCESS_B}")][1]
        factor_a = _ctmi(temperature) * _cpm(ph)
        factor_b = _arrhenius(temperature)
        assert 0.0 < factor_a <= 1.0 + 1e-12 and factor_b > 0.0
        np.testing.assert_allclose(rate_a, VMAX_A * polymer / (KM_A + polymer) * factor_a, rtol=1e-9, atol=1e-15)
        np.testing.assert_allclose(rate_b, VMAX_B * oligomer / (KM_B + oligomer) * factor_b, rtol=1e-9, atol=1e-15)
        # The laws change rates only: the closure through the yields holds at every output time.
        np.testing.assert_allclose(Y1 * Y2 * polymer + Y2 * oligomer + monomer, Y1 * Y2 * S0, rtol=1e-9)
    # At 37 degC both temperature laws move the rates away from their reference values, in opposite directions.
    assert _ctmi(37.0) < 1.0 < _arrhenius(37.0)
    assert _cpm(5.5) < 1.0


def test_the_reference_condition_reproduces_the_network_without_laws(grid_run: Any, tmp_path: Path) -> None:
    plain = _series(_simulate(tmp_path, CHAIN, fungus="strain_n1", substrate="polymer_p1", environments=["c30_ph5"]))
    series = _series(grid_run)
    reference = next(environment for environment, (t, ph, _s) in _conditions(grid_run).items() if (t, ph) == (30.0, 5.0))
    for role in ("substrate", "intermediate_1", "product"):
        times, expected, units = plain[("network_chain__c30_ph5", role)]
        other_times, actual, other_units = series[(reference, role)]
        assert units == other_units
        np.testing.assert_allclose(other_times, times)
        # Every factor is one at the reference condition (up to rounding of the cardinal formula).
        np.testing.assert_allclose(actual, expected, rtol=1e-7, atol=1e-10)


def test_the_case_reports_each_law_and_the_process_it_scales(grid_run: Any) -> None:
    response = grid_run.screen_result.case_results[0].environment_response
    assert response["status"] == "active_response_model"
    assert sorted((law["process_id"], law["law"]) for law in response["laws"]) == sorted(
        [
            (PROCESS_A, "temperature_cardinal_rosso"),
            (PROCESS_A, "ph_cardinal_rosso"),
            (PROCESS_B, "temperature_arrhenius_reference"),
        ]
    )
    assert set(response["conditions"]) == {"temperature", "ph"}
    limitations = " ".join(row["limitation"] for row in grid_run.limitations())
    assert "Environment response is active for ph, temperature" in limitations
    assert "Response laws from responses.csv scale the rate of Oligomer hydrolase-like class N1" in limitations


def test_a_ph_law_on_the_solid_of_a_cross_basis_network(tmp_path: Path) -> None:
    """Materially different case: a pH law on the class that cuts a solid in g/L, none on the inhibited dimer step."""

    result = _simulate(
        tmp_path / "run",
        _solid_ph_law(tmp_path / "data"),
        fungus="strain_s3",
        substrate="solid_c3",
        environments=environment_grid(temperature_C=[45], ph=[4.0, 5.0, 6.0]),
    )
    series = _series(result)
    remaining: dict[float, float] = {}
    for environment, (temperature, ph, statuses) in _conditions(result).items():
        assert temperature == 45.0 and statuses == {"active_response_model"}
        _, solid, solid_units = series[(environment, "substrate")]
        _, dimer, dimer_units = series[(environment, "intermediate_1")]
        _, monomer, _ = series[(environment, "product")]
        assert (solid_units, dimer_units) == ("gram / liter", "millimole / liter")
        rate_a = series[(environment, f"process_rate.{SOLID_PROCESS_A}")][1]
        rate_b = series[(environment, f"process_rate.{SOLID_PROCESS_B}")][1]
        factor = _cpm(ph, SOLID_PH_MIN, SOLID_PH_OPT, SOLID_PH_MAX)
        np.testing.assert_allclose(rate_a, SOLID_VMAX_A * solid / (SOLID_KM_A + solid) * factor, rtol=1e-9, atol=1e-15)
        # The dimer step has no law: its own competitive law at its rows' constants, whatever the pH.
        np.testing.assert_allclose(
            rate_b,
            SOLID_VMAX_B * dimer / (SOLID_KM_B * (1.0 + monomer / SOLID_KI_B) + dimer),
            rtol=1e-9,
            atol=1e-15,
        )
        total = SOLID_Y2 * SOLID_YIELD * solid + SOLID_Y2 * dimer + monomer
        np.testing.assert_allclose(total, SOLID_Y2 * SOLID_YIELD * SOLID_S0, rtol=1e-9)
        remaining[ph] = float(solid[-1])
    assert _cpm(4.0, SOLID_PH_MIN, SOLID_PH_OPT, SOLID_PH_MAX) == pytest.approx(7.0 / 9.0)
    assert remaining[5.0] < remaining[6.0] < remaining[4.0], "the optimum degrades fastest, as the law says"
    response = result.screen_result.case_results[0].environment_response
    assert [(law["process_id"], law["law"]) for law in response["laws"]] == [(SOLID_PROCESS_A, "ph_cardinal_rosso")]


def test_a_one_class_network_with_laws_equals_the_single_class_case(tmp_path: Path) -> None:
    """The oxidase case's two laws in a network of one class: the same records, laws and trajectories on a grid."""

    manifest = _manifest(OXIDASE, enzyme_network={"entry_substrates": ["syringaldazine_like"]})
    network = _load(tmp_path / "network", OXIDASE, {"user_dataset.yml": manifest})
    assert network.enzyme_networks[0]["processes"][0]["response_laws"] == [
        "temperature_cardinal_rosso",
        "ph_cardinal_rosso",
    ]
    grid = environment_grid(temperature_C=[20, 50, 65], ph=[4.0, 5.0])
    kwargs = {"fungus": "strain_l1", "substrate": "syringaldazine_like", "environments": grid}
    single = _series(_simulate(tmp_path / "single_run", OXIDASE, **kwargs))
    networked = _series(_simulate(tmp_path / "network_run", network, **kwargs))
    environments = {key[0] for key in single}
    assert len(environments) == 6
    for environment in environments:
        for role in ("substrate", "product"):
            times, expected, units = single[(environment, role)]
            other_times, actual, other_units = networked[(environment, role)]
            assert units == other_units
            np.testing.assert_allclose(other_times, times)
            # The same law and laws, integrated by the composed config instead of the single-process one.
            np.testing.assert_allclose(actual, expected, rtol=1e-7, atol=1e-9 * 50.0)


# ---------------------------------------------------------------------------
# Modes and gaps


def test_measured_laws_and_kinetics_make_the_network_scientific_until_one_law_row_is_an_estimate(tmp_path: Path) -> None:
    measured = {"evidence_type": "measured", "method": "illustrative measurement for the test"}
    kinetics = (LAWS / "kinetics.csv").read_text(encoding="utf-8").replace(
        ",estimate,illustrative estimate,", ",measured,illustrative measurement for the test,"
    )
    responses = _csv_text([{**row, **measured} for row in _laws_responses()], RESPONSES_HEADER)
    dataset = _load(tmp_path / "measured", LAWS, {"kinetics.csv": kinetics, "responses.csv": responses})
    (template,) = dataset.records["case_templates"]
    assert template["process_state_metadata"]["config_mode"] == "scientific"
    grid = environment_grid(temperature_C=[37], ph=[5.0])
    study = virtual_experiment(
        fungi=["strain_n1"], substrates=["polymer_p1"], environments=grid, registry=REGISTRY_INDEX, user_data=dataset
    )
    (report,) = study.preflight(mode="scientific")
    assert report.status == "modelable", report.to_dict()
    study.simulate(mode="scientific", output_dir=tmp_path / "scientific", quicklook=False)
    manifest = json.loads((tmp_path / "scientific" / "output_manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_label"] == "scientific_exact_unvalidated"

    one_estimate = _csv_text(
        [
            {**row, **({} if (row["law"], row["parameter"]) == ("ph_cardinal_rosso", "optimum_ph") else measured)}
            for row in _laws_responses()
        ],
        RESPONSES_HEADER,
    )
    weak = _load(tmp_path / "weak", LAWS, {"kinetics.csv": kinetics, "responses.csv": one_estimate})
    records = _parameter_records(weak)
    for parameter in ("minimum_ph", "optimum_ph", "maximum_ph"):
        role = f"ph_cardinal_rosso__{parameter}__{DEPOLYMERASE}__polymer_p1"
        assert records[f"{LAWS_ID}__network__polymer_p1__strain_n1__{role}"]["maturity"] == "exploratory_prior"
    assert weak.records["case_templates"][0]["process_state_metadata"]["config_mode"] == "exploratory"
    weak_study = virtual_experiment(
        fungi=["strain_n1"], substrates=["polymer_p1"], environments=grid, registry=REGISTRY_INDEX, user_data=weak
    )
    assert weak_study.preflight(mode="scientific")[0].status != "modelable"
    with pytest.raises(VirtualExperimentError, match="Scientific simulation requires exact"):
        weak_study.simulate(mode="scientific", output_dir=tmp_path / "blocked", quicklook=False)


def test_the_fixture_is_exploratory_only(laws: UserDataset) -> None:
    study = virtual_experiment(
        fungi=["strain_n1"], substrates=["polymer_p1"], environments=["c30_ph5"], registry=REGISTRY_INDEX, user_data=laws
    )
    assert study.preflight(mode="exploratory")[0].status == "modelable"
    assert study.preflight(mode="scientific")[0].status != "modelable"


def test_a_strain_without_the_laws_another_strain_binds_gets_law_gaps(tmp_path: Path) -> None:
    strains = (LAWS / "strains.csv").read_text(encoding="utf-8") + "strain_n2,Illustrative network strain N2,,\n"
    enzymes = (LAWS / "enzymes.csv").read_text(encoding="utf-8") + "".join(
        f"strain_n2,{class_key},assumed secreted activity (illustrative),Illustrative test note NW-3 p. 2\n"
        for class_key in (DEPOLYMERASE, OLIGOMER_HYDROLASE)
    )
    kinetics = (LAWS / "kinetics.csv").read_text(encoding="utf-8")
    kinetics += "".join(line.replace("strain_n1,", "strain_n2,", 1) + "\n" for line in kinetics.splitlines()[1:])
    dataset = _load(
        tmp_path, LAWS, {"strains.csv": strains, "enzymes.csv": enzymes, "kinetics.csv": kinetics}
    )
    records = _parameter_records(dataset)
    role = f"temperature_arrhenius_reference__activation_energy__{OLIGOMER_HYDROLASE}__oligomer_o1"
    gap = records[f"{LAWS_ID}__network__polymer_p1__strain_n2__{role}__gap"]
    assert gap["maturity"] == USER_DATASET_MATURITY_GAP
    assert gap["allowed_use"] == PARAMETER_ALLOWED_USE_GAP_ANALYSIS_ONLY
    assert gap["environment_id"] is None
    assert gap["provenance"]["measurement_request"] == (
        "Measure the activation energy of the Arrhenius reference-temperature law for Oligomer hydrolase-like class N1 "
        "from Illustrative network strain N2 on Oligomer-like pool O1 (an energy per amount (for example kJ/mol)); "
        "responses.csv binds this law to Oligomer hydrolase-like class N1 on Oligomer-like pool O1 for another strain."
    )
    gaps = [record_id for record_id, item in records.items() if item["maturity"] == USER_DATASET_MATURITY_GAP]
    assert len(gaps) == 8 and all("__strain_n2__" in record_id for record_id in gaps)
    grid = environment_grid(temperature_C=[37], ph=[5.0])
    reports = {
        strain: virtual_experiment(
            fungi=[strain], substrates=["polymer_p1"], environments=grid, registry=REGISTRY_INDEX, user_data=dataset
        ).preflight(mode="exploratory")[0]
        for strain in ("strain_n1", "strain_n2")
    }
    assert reports["strain_n1"].status == "modelable"
    assert reports["strain_n2"].status == "underparameterized"
    assert any("activation energy" in text for text in reports["strain_n2"].suggested_experiments)


# ---------------------------------------------------------------------------
# Refusals: the single-class rules, applied to network processes


def test_kinetics_not_at_the_reference_condition_are_refused(tmp_path: Path) -> None:
    responses = _csv_text(
        _laws_responses({("temperature_cardinal_rosso", "optimum_temperature"): {"value": "35"}}), RESPONSES_HEADER
    )
    issues = _issues(tmp_path, LAWS, {"responses.csv": responses})
    assert _has_issue(issues, "responses.csv", 3, "value", "The law rescales the reference value")
    assert _has_issue(issues, "responses.csv", 3, "value", f"strain 'strain_n1', enzyme class '{DEPOLYMERASE}'")
    tolerated = _csv_text(
        _laws_responses(
            {("temperature_cardinal_rosso", "optimum_temperature"): {"value": "32", "reference_tolerance": "2"}}
        ),
        RESPONSES_HEADER,
    )
    assert _load(tmp_path / "tolerance", LAWS, {"responses.csv": tolerated}).enzyme_networks


def test_a_ki_not_at_the_reference_condition_is_refused(tmp_path: Path) -> None:
    """In a network the process's Ki is one of the constants a law needs at its reference condition."""

    conditions = (SOLID_CHAIN / "conditions.csv").read_text(encoding="utf-8") + "c40_ph5,40,degC,5.0,Illustrative\n"
    rows = _rows(SOLID_CHAIN, "kinetics.csv")
    ki = next(row for row in rows if row["quantity"] == "ki")
    kinetics = _csv_text([*rows, {**ki, "condition_id": "c40_ph5"}], list(rows[0]))
    responses = _responses(
        _response(HYDROLASE, "dimer_d3", "temperature_arrhenius_reference", "activation_energy", "50", "kJ/mol", strain_id="strain_s3"),
        _response(HYDROLASE, "dimer_d3", "temperature_arrhenius_reference", "reference_temperature", "45", "degC", strain_id="strain_s3"),
    )
    edits = {"conditions.csv": conditions, "kinetics.csv": kinetics, "responses.csv": responses}
    issues = _issues(tmp_path, SOLID_CHAIN, edits)
    assert _has_issue(issues, "responses.csv", 3, "value", f"at condition 'c40_ph5' (40 degC, pH 5.0; kinetics.csv row {len(rows) + 2})")
    # The same Ki row at the reference condition only is accepted.
    accepted = _load(tmp_path / "accepted", SOLID_CHAIN, {"responses.csv": responses})
    assert accepted.enzyme_networks[0]["processes"][1]["response_laws"] == ["temperature_arrhenius_reference"]


@pytest.mark.parametrize(
    ("rows", "row", "column", "message"),
    [
        pytest.param(
            [
                _response(DEPOLYMERASE, "polymer_p1", "temperature_arrhenius_reference", "activation_energy", "40", "kJ/mol"),
                _response(DEPOLYMERASE, "polymer_p1", "temperature_arrhenius_reference", "reference_temperature", "30", "degC"),
            ],
            10,
            "law",
            "give one law per condition",
            id="two_temperature_laws_on_one_process",
        ),
        pytest.param(
            [_response(DEPOLYMERASE, "oligomer_o1", "temperature_cardinal_rosso", "minimum_temperature", "5", "degC")],
            10,
            "substrate_id",
            "cannot act on substrate 'oligomer_o1'",
            id="a_pool_the_class_does_not_act_on",
        ),
        pytest.param(
            [_response("other_cutter_like", "polymer_p1", "temperature_cardinal_rosso", "minimum_temperature", "5", "degC")],
            10,
            "enzyme_class",
            "does not declare enzyme class 'other_cutter_like'",
            id="a_class_that_is_no_member",
        ),
        pytest.param(
            [_response(DEPOLYMERASE, "polymer_p1", "oxygen_monod", "oxygen_half_saturation", "0.1", "mM")],
            10,
            "law",
            "supports only",
            id="a_law_responses_csv_does_not_bind",
        ),
    ],
)
def test_network_law_refusals(tmp_path: Path, rows: list[dict[str, str]], row: int, column: str, message: str) -> None:
    classes = (LAWS / "enzyme_classes.csv").read_text(encoding="utf-8") + (
        "other_cutter_like,Other cutter-like class N3,,unrelated_like_bond,unrelated_like,Illustrative class no strain declares\n"
    )
    responses = _csv_text([*_laws_responses(), *rows], RESPONSES_HEADER)
    issues = _issues(tmp_path, LAWS, {"responses.csv": responses, "enzyme_classes.csv": classes})
    assert _has_issue(issues, "responses.csv", row, column, message), issues


def test_strains_of_one_process_must_share_its_law(tmp_path: Path) -> None:
    strains = (LAWS / "strains.csv").read_text(encoding="utf-8") + "strain_n2,Illustrative network strain N2,,\n"
    enzymes = (LAWS / "enzymes.csv").read_text(encoding="utf-8") + "".join(
        f"strain_n2,{class_key},assumed secreted activity (illustrative),Illustrative test note NW-3 p. 2\n"
        for class_key in (DEPOLYMERASE, OLIGOMER_HYDROLASE)
    )
    kinetics = (LAWS / "kinetics.csv").read_text(encoding="utf-8")
    kinetics += "".join(line.replace("strain_n1,", "strain_n2,", 1) + "\n" for line in kinetics.splitlines()[1:])
    responses = _csv_text(
        [
            *_laws_responses(),
            _response(DEPOLYMERASE, "polymer_p1", "temperature_arrhenius_reference", "activation_energy", "40", "kJ/mol", strain_id="strain_n2"),
            _response(DEPOLYMERASE, "polymer_p1", "temperature_arrhenius_reference", "reference_temperature", "30", "degC", strain_id="strain_n2"),
        ],
        RESPONSES_HEADER,
    )
    edits = {"strains.csv": strains, "enzymes.csv": enzymes, "kinetics.csv": kinetics, "responses.csv": responses}
    issues = _issues(tmp_path, LAWS, edits)
    assert _has_issue(issues, "responses.csv", 10, "law", "has different temperature laws for different strains")


def test_a_law_needs_the_condition_it_reads(tmp_path: Path) -> None:
    conditions = "condition_id,temperature,temperature_units,ph,notes\nc30_ph5,unknown,degC,5.0,Temperature not recorded\n"
    issues = _issues(tmp_path, LAWS, {"conditions.csv": conditions})
    assert _has_issue(issues, "responses.csv", 3, "value", "Condition 'c30_ph5' has an unknown temperature")


# ---------------------------------------------------------------------------
# Command line


def test_check_data_lists_the_laws_of_each_network_process(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = _cli(capsys, "check-data", LAWS, "--registry", REGISTRY_INDEX)
    assert code == EXIT_OK, err
    assert "enzyme class             pool         rate form  competitive inhibitor  response laws" in out
    assert (
        "depolymerase_like        polymer_p1   kcat       none                   "
        "temperature_cardinal_rosso, ph_cardinal_rosso"
    ) in out
    assert "oligomer_hydrolase_like  oligomer_o1  kcat       none                   temperature_arrhenius_reference" in out
    # A network without laws prints the earlier table.
    code, out, err = _cli(capsys, "check-data", CHAIN, "--registry", REGISTRY_INDEX)
    assert code == EXIT_OK, err
    assert "response laws" not in out


def test_check_data_reports_a_law_refusal(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    responses = _csv_text(
        _laws_responses({("temperature_cardinal_rosso", "optimum_temperature"): {"value": "35"}}), RESPONSES_HEADER
    )
    dataset = _copy_fixture(tmp_path, LAWS, edits={"responses.csv": responses})
    code, _out, err = _cli(capsys, "check-data", dataset, "--registry", REGISTRY_INDEX)
    assert code == EXIT_USAGE
    assert "responses.csv:3:value: The kinetic constants of strain 'strain_n1'" in err


def test_run_simulates_the_network_on_a_temperature_grid(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code, out, err = _cli(
        capsys,
        "run",
        "--user-data",
        LAWS,
        "--fungus",
        "strain_n1",
        "--substrate",
        "polymer_p1",
        "--temperature-c",
        "30",
        "--temperature-c",
        "37",
        "--ph",
        "5",
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
    assert "Simulated 2 case(s) in exploratory mode" in out
    assert out.count(
        "environment effect: active_response_model (ph:ph_cardinal_rosso;temperature:temperature_cardinal_rosso;"
        "temperature:temperature_arrhenius_reference)"
    ) == 2
    with (tmp_path / "run" / "time_series_long.csv").open(encoding="utf-8", newline="") as handle:
        statuses = {row["environment_effect_status"] for row in csv.DictReader(handle)}
    assert statuses == {"active_response_model"}
