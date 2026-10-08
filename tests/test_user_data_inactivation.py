"""First-order enzyme inactivation in user data (USERDATA-011).

A ``kinetics.csv`` row of quantity ``inactivation_rate`` (1/time, at the row's
condition) binds the existing ``first_order`` process law to the enzyme state of
its case, ``dE/dt = -k_d E``; the ``thermal_inactivation`` law of
``responses.csv`` (``activation_energy`` and ``reference_temperature``) binds the
existing ``thermal_inactivation`` process law instead, ``k_d(T) = k_d(T_ref)
exp(-E_d / R (1/T - 1/T_ref))``. Single-class cases (the enzyme-kinetics
assembler gains a declared loss process of its enzyme state) and every member of
an enzyme network (each class's enzyme state decays by its own constant) take
it; the Vmax form has no enzyme state and a culture pool already has its own
first-order loss (``enzyme_loss_rate``), so both are refused. Without a row the
enzyme state is not lost: never a default constant.

``tests/fixtures/user_data/inactivation_case`` is a user-defined amide
hydrolase-like class on a dissolved amide-like substrate (kcat form, constant
``k_d``). ``tests/fixtures/user_data/inactivation_network`` is the materially
different case: two user-defined cutter-like classes in parallel on a
particulate polymer-like solid (dry-mass basis, protein-mass enzymes), one of
them losing activity through the Arrhenius law, the other stable. Every value of
both is an illustrative estimate; other datasets are derived from them and from
earlier fixtures in temporary directories to test modes, analytic limits and
refusals only.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from scipy.special import lambertw

from fungal_model import UserDataError, UserDataset, environment_grid, load_user_dataset, virtual_experiment
from fungal_model.api.user_data import (
    FIT_IDENTIFIED,
    INACTIVATION_LAW,
    INACTIVATION_RATE_QUANTITY,
    LAW_SCALES_INACTIVATION,
    RESPONSE_LAWS,
    USER_DATASET_MATURITY_ESTIMATE,
    USER_DATASET_MATURITY_GAP,
)
from fungal_model.api.user_data_assembly import assemble_user_tables
from fungal_model.api.user_data_fit import UserDataFitError, fit_user_dataset
from fungal_model.cli import EXIT_OK, EXIT_USAGE, main
from fungal_model.processes import ProcessLibrary
from fungal_model.registry import load_registry
from fungal_model.registry.records import CaseTemplateRecord
from fungal_model.screening import RegistryCaseBuildError
from fungal_model.screening.case_builder import (
    ENZYME_INACTIVATION_PROCESS_LAWS,
    ENZYME_INACTIVATION_TEMPLATE_KEY,
    build_registry_process_config_data,
    get_registry_process_assembler,
    select_registry_case_compatibility,
)
from fungal_model.screening.ensemble import _sample_role_records, resolve_screen_role_records
from fungal_model.screening.modelability import assess_modelability

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"
FIXTURES = ROOT / "tests" / "fixtures" / "user_data"
CASE = FIXTURES / "inactivation_case"
NETWORK = FIXTURES / "inactivation_network"

CASE_ID = "inactivation_demo"
HYDROLASE = "amide_hydrolase_like"
CASE_PROCESS = f"{CASE_ID}__{HYDROLASE}__amide_a1__homogeneous_mm"
CASE_LOSS = f"{CASE_ID}__{HYDROLASE}__amide_a1__enzyme_inactivation"
CASE_SYMBOL = f"{CASE_ID}__inactivation_rate__{HYDROLASE}__amide_a1"
NETWORK_ID = "inactivation_network"
FAST = "fast_cutter_w7"
STABLE = "stable_cutter_w7"
NETWORK_LOSS = f"{NETWORK_ID}__{FAST}__solid_w7__enzyme_inactivation"

GAS_CONSTANT = 8.31446261815324  # J/(mol K), the exact SI value
# The fixtures' constants (every one an illustrative estimate) in minutes and mM, or hours and g/L.
KM, KCAT, S0, E0, KD = 4.0, 60.0, 0.5, 0.001, 0.3 / 60.0  # mM, 1/min, mM, mM, 1/min (0.3 1/h)
FAST_KM, FAST_KCAT, FAST_E0, FAST_KD = 8.0, 0.05, 10.0, 0.1  # g/L, g/(mg h), mg/L, 1/h at 55 degC
STABLE_KM, STABLE_KCAT, STABLE_E0 = 15.0, 0.01, 10.0  # g/L, g/(mg h), mg/L
SOLID_S0, FAST_ENERGY, FAST_TREF = 20.0, 200000.0, 55.0  # g/L, J/mol, degC

KINETICS_HEADER = (
    "strain_id",
    "enzyme_class",
    "substrate_id",
    "condition_id",
    "quantity",
    "value",
    "lower",
    "upper",
    "units",
    "evidence_type",
    "method",
    "source",
)
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

# SHA-256 of json.dumps(dataset.to_dict()["records"], sort_keys=True) of every earlier fixture, and of
# json.dumps({case: sha256(yaml.safe_dump(config data, sort_keys=False))}, sort_keys=True) of every assembled case of
# each fixture and of the shipped registry (built as the screen builds a sample, ranges at their lower bounds, output
# directory "<OUTPUT_ROOT>"), computed at commit 6567464 before USERDATA-011: a dataset without inactivation_rate rows
# or the thermal_inactivation law generates the same records and assembles the same configs.
RECORDS_6567464 = {
    "bgl1a_ph_ionization": "5a5c837fde83d33c1b01fdfd88499eddd4112fbc8a4c3097e6efcaa246af60f1",
    "culture_estimates": "4cc4a3de85c4c74c83abf95d7f1bd9cbe72916db52d6800cdffadd0a094743f0",
    "culture_parallel_pools": "05ba8367546f2596d7a588c9a70a6f97c5a9ab188aa083787e34532a2fc7cf13",
    "culture_reentry": "013ebc0dd3decea7b8952e54636b48977e1767c9b1ef732cfed3b1fc48d2c698",
    "culture_shared_pools": "6a94798465e19c666fb23081a496496d30b126c0030dbb3d1e8d21d8edb3014e",
    "esterase_case": "4f92a532f98356be6ac680b4652ac411a975e3c772dd2f0348c590a207ef3464",
    "genome_case": "f13786fee336d8c58e9dc5d052e1b138158ade98d268cd6b0788ed6b5a8b118e",
    "literature_reentry": "37baa76aaefcbe1d27746720218eafd7712a47ca8c0927245eea597895fce6e1",
    "network_chain": "3b773a4f56a973c4db62a074fa705ae6ffdd1135f9e8866e065161c9e35560f7",
    "network_chain_laws": "d97eee9fe864e32fbbf3ed7d4bec21f73aa4a5135025d25fc77a95522e367219",
    "network_parallel": "b3b3d6684948bb153bd1c98337d0890ffafb40c3e862774a63111cde03de241d",
    "network_solid_chain": "89a983b30d7517d5e50cace7ca3723c47b208c6667ed4f2d3cc46fa0151e10a6",
    "network_solid_parallel": "ca5e8ad5685453f283cf72d4547b05b7d6f12f52eea72667ec6a94c24a831104",
    "oxidase_case": "eb82f225a0cd09115afb44b67e0bb2496e7bf11ee7f0960624759b1970f7e322",
    "solid_case": "9b1eecb8cd6820ec7c1c27f17bff9d4820e5679c0350a77c3caba1ced2215e83",
    "uniprot_case": "8ec0dfbf50881d866a00b0392149a1dd60cd8260ac3acdd771e5b7d71a5b6532",
}
CONFIGS_6567464 = {
    "bgl1a_ph_ionization": "4dbfba77c737ff6400b5cc07f113247648f6c87f991c0c2537fc3c6d4a688cd5",
    "culture_estimates": "9f69462fec7695038bdcc1d7327718664534156fdf502b5d6b239ca073fd7641",
    "culture_parallel_pools": "7a565b382b9336832d3cb3e0820a00280713f4c22d0fff10bc6eb123cedb5c5d",
    "culture_reentry": "683fd6db1b9a8a732cb640f9d554151241a60bd29bf01b73ad0303e907a40e94",
    "culture_shared_pools": "d196a998f6d0b7499ffa3bf80f0b88a073c5670699c0abb35a4d7655a06e67b5",
    "esterase_case": "5eaed3b4fa639410259b226da3e09df5996bf588cc050a7f9b7e48f98a468fd7",
    "genome_case": "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
    "literature_reentry": "438434de530704e3675c91d5d5bca72330ec16b9c00e24eb10647094ae957dce",
    "network_chain": "3421a199222262f45ecff0fb600277a5a12f95b0928eeb52c68fa994f8076360",
    "network_chain_laws": "c8c5e21c6e11212bcc49119e98940d65f481a049734be36054ba0e4ec03bf671",
    "network_parallel": "fe40b4cde1da186ad103b4f577dd3a3531b983ef3dbdf89a786bfcbbfba45863",
    "network_solid_chain": "3c1624ec631fe75d8ca92794ecbe0a2190327167c777147fda30dc762fa81e41",
    "network_solid_parallel": "dc34a6fbdf3d714ada504344f7ab0ad0e1b257978d9895ed0d82de79300b0117",
    "oxidase_case": "69f6f66b2632b0e431ef242535400f6e9b5d82ec8e9bf6b46381070e11cf6d04",
    "registry": "deba79df4c336b969d7fd86b52ccddec92d7b2fc48592ed15d166bb4414ec2b4",
    "solid_case": "741dfce4d32789fe5c6301d7c8b4c670a6033861ae18945c14787ae1a544b1ba",
    "uniprot_case": "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
}


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


def _with_rows(source: Path, name: str, *rows: Mapping[str, str], drop: Sequence[str] = ()) -> str:
    """A table of ``source`` with ``rows`` appended and every row whose quantity is in ``drop`` removed."""

    with (source / name).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        header = list(reader.fieldnames or ())
        existing = [row for row in reader if row.get("quantity") not in drop]
    for row in rows:
        header.extend(column for column in row if column not in header)
    return _csv_text([*existing, *rows], header)


def _kinetic(**fields: str) -> dict[str, str]:
    row = {
        "strain_id": "strain_v1",
        "enzyme_class": HYDROLASE,
        "substrate_id": "amide_a1",
        "condition_id": "c40_ph6",
        "quantity": INACTIVATION_RATE_QUANTITY,
        "value": "0.3",
        "units": "1/h",
        "evidence_type": "estimate",
        "method": "illustrative estimate",
        "source": "Illustrative test note IV-1 p. 9",
    }
    row.update(fields)
    return row


def _law(parameter: str, value: str, units: str, **fields: str) -> dict[str, str]:
    row = {
        "strain_id": "strain_v1",
        "enzyme_class": HYDROLASE,
        "substrate_id": "amide_a1",
        "law": INACTIVATION_LAW,
        "parameter": parameter,
        "value": value,
        "units": units,
        "evidence_type": "estimate",
        "source": "Illustrative test note IV-1 p. 9",
    }
    row.update(fields)
    return row


def _series(result: Any) -> dict[tuple[str, int, str], tuple[np.ndarray, np.ndarray, str]]:
    """(environment id, sample index, state role or rate key) -> (times, values, units)."""

    series: dict[tuple[str, int, str], list[tuple[float, float, str]]] = {}
    for row in result.time_series():
        if row["source"] == "simulation_state":
            key = row["state_role"]
        elif row["source"] in {"simulation_process_rate", "simulation_state_rate"}:
            key = row["state"]
        else:
            continue
        series.setdefault((row["environment_id"], int(row["sample_index"]), key), []).append(
            (float(row["time"]), float(row["value"]), row["units"])
        )
    return {
        key: (np.array([item[0] for item in items]), np.array([item[1] for item in items]), items[0][2])
        for key, items in series.items()
    }


def _temperatures(result: Any) -> dict[str, float]:
    return {row["environment_id"]: float(row["temperature_C"]) for row in result.time_series()}


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


def _arrhenius(temperature_c: float, energy: float, reference_c: float) -> float:
    """exp(-E/R (1/T - 1/T_ref)), computed here, not imported."""

    return math.exp(-energy / GAS_CONSTANT * (1.0 / (temperature_c + 273.15) - 1.0 / (reference_c + 273.15)))


def _michaelis_menten_with_decay(times: np.ndarray, *, s0: float, km: float, kcat: float, e0: float, kd: float) -> np.ndarray:
    """The exact substrate of dS/dt = -kcat E0 exp(-kd t) S / (Km + S): Km ln(S/S0) + S - S0 = -tau(t).

    tau(t) = kcat E0 (1 - exp(-kd t)) / kd is the enzyme's integrated activity; the implicit solution is solved with
    the Lambert W function, S = Km W((S0 / Km) exp((S0 - tau) / Km)).
    """

    tau = kcat * e0 * (1.0 - np.exp(-kd * times)) / kd
    return km * np.real(lambertw((s0 / km) * np.exp((s0 - tau) / km)))


@pytest.fixture(scope="module")
def case() -> UserDataset:
    return load_user_dataset(CASE, registry=REGISTRY_INDEX)


@pytest.fixture(scope="module")
def network() -> UserDataset:
    return load_user_dataset(NETWORK, registry=REGISTRY_INDEX)


@pytest.fixture(scope="module")
def case_run(tmp_path_factory: pytest.TempPathFactory) -> Any:
    return _simulate(
        tmp_path_factory.mktemp("inactivation_case"), CASE, fungus="strain_v1", substrate="amide_a1", environments=["c40_ph6"]
    )


@pytest.fixture(scope="module")
def network_grid(tmp_path_factory: pytest.TempPathFactory) -> Any:
    return _simulate(
        tmp_path_factory.mktemp("inactivation_network"),
        NETWORK,
        fungus="strain_w7",
        substrate="solid_w7",
        environments=environment_grid(temperature_C=[50, 55, 60], ph=[5.0]),
    )


# ---------------------------------------------------------------------------
# The quantity, the law and the generated records


def test_the_inactivation_law_is_the_existing_process_law_of_the_enzyme_state() -> None:
    law = RESPONSE_LAWS[INACTIVATION_LAW]
    assert law.scales == LAW_SCALES_INACTIVATION
    assert law.parameter_names == ("activation_energy", "reference_temperature")
    assert law.reference_parameter == "reference_temperature"
    assert law.reads == "temperature"
    # It rescales no catalytic constant, so it carries none to another condition.
    assert law.condition == ""
    factories = frozenset(ProcessLibrary.default_foundation().factory_types())
    assert set(ENZYME_INACTIVATION_PROCESS_LAWS) == {"first_order", INACTIVATION_LAW}
    assert set(ENZYME_INACTIVATION_PROCESS_LAWS) <= factories


def test_an_inactivation_rate_binds_the_first_order_law_to_the_enzyme_state(case: UserDataset) -> None:
    (template,) = case.records["case_templates"]
    (compatibility,) = case.records["process_compatibility"]
    assert template["process_type"] == "homogeneous_michaelis_menten"
    declared = template["process_state_metadata"][ENZYME_INACTIVATION_TEMPLATE_KEY]
    assert declared["process_id"] == CASE_LOSS
    assert declared["process_type"] == "first_order"
    assert declared["parameter_roles"] == {"rate_constant": "inactivation_rate"}
    assert "dE/dt = -k_d E" in declared["assumptions"][0]
    assert compatibility["parameter_roles"]["inactivation_rate"] == CASE_SYMBOL
    assert CASE_SYMBOL in compatibility["required_parameters"]
    (record,) = [item for item in case.records["parameter_records"] if item["parameter_symbol"] == CASE_SYMBOL]
    assert record["value"] == {
        "kind": "exact",
        "units": "1/h",
        "source": "Illustrative test note IV-1 p. 4",
        "confidence_level": "exploratory_assumption",
        "notes": record["value"]["notes"],
        "value": 0.3,
    }
    assert record["maturity"] == USER_DATASET_MATURITY_ESTIMATE
    assert record["environment_id"] == f"{CASE_ID}__c40_ph6"
    assert record["process_type"] == "homogeneous_michaelis_menten"
    assert "which no temperature law rescales" in record["provenance"]["validity_range"]
    limitations = " ".join(template["limitations"])
    assert "Enzyme inactivation of Amide hydrolase-like class V1" in limitations
    assert "E(t) = E0 exp(-k_d t)" in limitations
    assert "assumed constant" not in limitations
    assert case.to_dict()["enzyme_inactivation"] == [
        {
            "enzyme_class": HYDROLASE,
            "substrate_id": "amide_a1",
            "law": "first_order",
            "process_id": CASE_LOSS,
            "case_template_ids": [f"{CASE_ID}__{HYDROLASE}__amide_a1__homogeneous_mm_template"],
            "kinetics_rows": [6],
            "responses_rows": [],
        }
    ]


def test_the_assembled_case_runs_the_loss_after_the_michaelis_menten_process(case: UserDataset) -> None:
    registry = case.overlay(load_registry(REGISTRY_INDEX))
    fungus, substrate, environment = f"{CASE_ID}__strain_v1", f"{CASE_ID}__amide_a1", f"{CASE_ID}__c40_ph6"
    report = assess_modelability(
        fungus_id=fungus, substrate_id=substrate, environment_id=environment, registry=registry, mode="exploratory"
    )
    assert report.status == "modelable"
    compatibility = select_registry_case_compatibility(registry=registry, fungus_id=fungus, substrate_id=substrate, report=report)
    records = resolve_screen_role_records(
        registry=registry,
        compatibility=compatibility,
        fungus_id=fungus,
        substrate_id=substrate,
        environment_id=environment,
        mode="exploratory",
    )
    data = build_registry_process_config_data(
        registry=registry,
        compatibility=compatibility,
        fungus_id=fungus,
        substrate_id=substrate,
        environment_id=environment,
        parameter_records=records,
        output_directory=None,
    )
    main_process, loss = data["processes"]
    assert main_process["id"] == CASE_PROCESS
    assert loss == {
        "id": CASE_LOSS,
        "process_type": "first_order",
        "states": {"source": main_process["states"]["enzyme"]},
        "parameters": {"rate_constant": CASE_SYMBOL},
        "modifiers": [],
        "output_state_roles": main_process["output_state_roles"],
        "assumptions": loss["assumptions"],
    }
    # A constant loss reads no condition: no environment entity, and the summary stays metadata only.
    assert "environment" not in data["entities"]
    assert data["provenance"]["environment_response"]["status"] == "metadata_only"


# ---------------------------------------------------------------------------
# Analytic checks of a single-class case


def test_enzyme_and_substrate_follow_the_exact_solution_at_every_output_time(case_run: Any) -> None:
    series = _series(case_run)
    environment = f"{CASE_ID}__c40_ph6"
    times, enzyme, units = series[(environment, 0, "enzyme")]
    assert units == "millimolar"
    assert times[-1] == 480.0 and len(times) == 97
    np.testing.assert_allclose(enzyme, E0 * np.exp(-KD * times), rtol=1e-8)
    _t, substrate, _u = series[(environment, 0, "substrate")]
    _t, product, _u = series[(environment, 0, "product")]
    expected = _michaelis_menten_with_decay(times, s0=S0, km=KM, kcat=KCAT, e0=E0, kd=KD)
    np.testing.assert_allclose(substrate, expected, rtol=1e-6)
    np.testing.assert_allclose(substrate + product, S0, rtol=1e-9)
    # The loss process runs at k_d E (per second, the process's own rate units) and the degradation at kcat E S/(Km + S).
    _t, loss, loss_units = series[(environment, 0, f"process_rate.{CASE_LOSS}")]
    assert loss_units == "millimolar / second"
    np.testing.assert_allclose(loss, (KD / 60.0) * enzyme, rtol=1e-9)
    _t, degradation, _u = series[(environment, 0, "degradation_rate")]
    np.testing.assert_allclose(degradation, KCAT * enzyme * substrate / (KM + substrate), rtol=1e-6)
    # Without inactivation almost no substrate would remain; with it the integrated activity caps the conversion.
    stable = _michaelis_menten_with_decay(times, s0=S0, km=KM, kcat=KCAT, e0=E0, kd=1e-12)
    assert substrate[-1] > 50.0 * stable[-1]


def test_the_first_order_regime_follows_the_closed_form(tmp_path: Path) -> None:
    """S << Km: S(t) = S0 exp(-(kcat E0 / Km)(1 - exp(-k_d t)) / k_d), within S0 / Km of the full law."""

    s0 = 0.0004  # mM, S0 / Km = 1e-4
    kinetics = _csv_text(
        [
            {**row, "value": str(s0)} if row["quantity"] == "substrate_initial_concentration" else row
            for row in _rows(CASE, "kinetics.csv")
        ],
        KINETICS_HEADER,
    )
    result = _simulate(
        tmp_path / "run",
        _copy_fixture(tmp_path, CASE, edits={"kinetics.csv": kinetics}),
        fungus="strain_v1",
        substrate="amide_a1",
        environments=["c40_ph6"],
    )
    times, substrate, _u = _series(result)[(f"{CASE_ID}__c40_ph6", 0, "substrate")]
    closed = s0 * np.exp(-(KCAT * E0 / KM) * (1.0 - np.exp(-KD * times)) / KD)
    np.testing.assert_allclose(substrate, closed, rtol=1.5 * s0 / KM)
    # The plateau is the integrated activity kcat E0 / (Km k_d), not complete conversion.
    assert substrate[-1] / s0 == pytest.approx(math.exp(-(KCAT * E0 / KM) * (1.0 - math.exp(-KD * 480.0)) / KD), rel=2e-4)


def test_the_mechanism_and_limitation_tables_name_the_loss(case_run: Any) -> None:
    rows = case_run.mechanism_summary()
    assert [(row["mechanism_kind"], row["mechanism_id"]) for row in rows] == [
        ("process_law", "homogeneous_michaelis_menten"),
        ("process_law", CASE_LOSS),
    ]
    loss = rows[1]
    assert loss["mechanism_family"] == "generic first-order loss of one state"
    assert loss["equation_or_law"] == "dX/dt = -k * X"
    assert loss["configured_by"] == CASE_PROCESS
    assert loss["parameters"] == f"rate_constant:{CASE_SYMBOL}"
    assert loss["state_variables"] == f"source:{HYDROLASE}_concentration"
    assert f"inactivation_rate:{CASE_SYMBOL}" in rows[0]["parameters"]
    limitations = " ".join(row["limitation"] for row in case_run.limitations())
    assert "Enzyme inactivation of Amide hydrolase-like class V1" in limitations


def test_a_range_is_sampled_and_each_sample_decays_by_its_own_constant(tmp_path: Path) -> None:
    kinetics = _with_rows(
        CASE, "kinetics.csv", _kinetic(value="", lower="0.2", upper="0.4"), drop=(INACTIVATION_RATE_QUANTITY,)
    )
    result = _simulate(
        tmp_path / "run",
        _copy_fixture(tmp_path, CASE, edits={"kinetics.csv": kinetics}),
        fungus="strain_v1",
        substrate="amide_a1",
        environments=["c40_ph6"],
        n_samples=3,
        seed=5,
    )
    sampled = {
        int(row["sample_index"]): (float(row["sampled_value"]), row["units"])
        for row in result.sampled_parameters()
        if row["role"] == "inactivation_rate"
    }
    assert sorted(sampled) == [0, 1, 2]
    series = _series(result)
    for index, (value, units) in sampled.items():
        assert units == "1 / hour" and 0.2 <= value <= 0.4
        times, enzyme, _u = series[(f"{CASE_ID}__c40_ph6", index, "enzyme")]
        np.testing.assert_allclose(enzyme, E0 * np.exp(-(value / 60.0) * times), rtol=1e-8)


def test_a_fit_to_time_courses_runs_the_decaying_enzyme(tmp_path: Path) -> None:
    """Time courses of the exact solution with k_d recover kcat: the fitted model loses its enzyme too."""

    times = np.arange(0.0, 481.0, 40.0)
    substrate = _michaelis_menten_with_decay(times, s0=S0, km=KM, kcat=KCAT, e0=E0, kd=KD)
    lines = ["strain_id,enzyme_class,substrate_id,condition_id,observable,time,time_units,value,units,sd,replicates,source,method"]
    lines.extend(
        f"strain_v1,{HYDROLASE},amide_a1,c40_ph6,substrate,{time:g},minute,{float(value)!r},mM,0.002,3,"
        "synthetic: exact solution with first-order enzyme inactivation; not a measurement,analytic solution"
        for time, value in zip(times, substrate, strict=True)
    )
    dataset = _load(tmp_path, CASE, {"timecourse.csv": "\n".join(lines) + "\n"})
    fit = fit_user_dataset(
        dataset,
        base_registry=REGISTRY_INDEX,
        parameters=[("strain_v1", HYDROLASE, "amide_a1", "kcat")],
        bounds={"kcat": (1.0, 300.0, "1/min")},
        initial={"kcat": 20.0},
        profile_points=7,
    )
    (item,) = fit.quantities
    assert item.identifiability == FIT_IDENTIFIED
    assert item.value == pytest.approx(KCAT, rel=1e-6)
    with pytest.raises(UserDataFitError, match="km, kcat, vmax"):
        fit_user_dataset(
            dataset,
            base_registry=REGISTRY_INDEX,
            parameters=[("strain_v1", HYDROLASE, "amide_a1", INACTIVATION_RATE_QUANTITY)],
            bounds={INACTIVATION_RATE_QUANTITY: (0.01, 1.0, "1/h")},
        )


# ---------------------------------------------------------------------------
# Gaps, the rest of the dataset, and modes


def test_a_second_strain_without_the_row_gets_a_gap_never_a_default(tmp_path: Path) -> None:
    strains = (CASE / "strains.csv").read_text(encoding="utf-8") + "strain_v2,Hydrolase source strain V2,,\n"
    enzymes = (CASE / "enzymes.csv").read_text(encoding="utf-8") + (
        f"strain_v2,{HYDROLASE},activity assay,Illustrative test note IV-1 p. 1\n"
    )
    second = [
        {**row, "strain_id": "strain_v2"}
        for row in _rows(CASE, "kinetics.csv")
        if row["quantity"] != INACTIVATION_RATE_QUANTITY
    ]
    kinetics = _with_rows(CASE, "kinetics.csv", *second)
    dataset = _load(tmp_path, CASE, {"strains.csv": strains, "enzymes.csv": enzymes, "kinetics.csv": kinetics})
    (gap,) = [item for item in dataset.records["parameter_records"] if item["maturity"] == USER_DATASET_MATURITY_GAP]
    assert gap["record_id"] == f"{CASE_ID}__strain_v2__{HYDROLASE}__amide_a1__c40_ph6__inactivation_rate__gap"
    assert gap["parameter_symbol"] == CASE_SYMBOL
    assert gap["value"]["kind"] == "unknown"
    request = gap["provenance"]["measurement_request"]
    assert request.startswith("Measure the first-order inactivation rate constant k_d of Amide hydrolase-like class V1")
    assert "units of 1/time" in request
    registry = dataset.overlay(load_registry(REGISTRY_INDEX))
    statuses = {
        strain: assess_modelability(
            fungus_id=f"{CASE_ID}__{strain}",
            substrate_id=f"{CASE_ID}__amide_a1",
            environment_id=f"{CASE_ID}__c40_ph6",
            registry=registry,
            mode="exploratory",
        ).status
        for strain in ("strain_v1", "strain_v2")
    }
    assert statuses == {"strain_v1": "modelable", "strain_v2": "underparameterized"}


def test_other_enzyme_states_of_the_dataset_say_they_are_not_lost(tmp_path: Path) -> None:
    classes = (CASE / "enzyme_classes.csv").read_text(encoding="utf-8") + (
        "ester_hydrolase_like,Ester hydrolase-like class V1,,ester_like_bond,ester_like,Illustrative class\n"
    )
    enzymes = (CASE / "enzymes.csv").read_text(encoding="utf-8") + (
        "strain_v1,ester_hydrolase_like,activity assay,Illustrative test note IV-1 p. 1\n"
    )
    substrates = (CASE / "substrates.csv").read_text(encoding="utf-8") + (
        "ester_e1,,Dissolved ester-like substrate E1,ester_like,dissolved,ester_like_bond,alcohol_v1,1,mol/mol,Illustrative\n"
    )
    second = [
        {**row, "enzyme_class": "ester_hydrolase_like", "substrate_id": "ester_e1"}
        for row in _rows(CASE, "kinetics.csv")
        if row["quantity"] != INACTIVATION_RATE_QUANTITY
    ]
    edits = {
        "enzyme_classes.csv": classes,
        "enzymes.csv": enzymes,
        "substrates.csv": substrates,
        "kinetics.csv": _with_rows(CASE, "kinetics.csv", *second),
    }
    dataset = _load(tmp_path, CASE, edits)
    templates = {item["record_id"]: item for item in dataset.records["case_templates"]}
    other = templates[f"{CASE_ID}__ester_hydrolase_like__ester_e1__homogeneous_mm_template"]
    assert ENZYME_INACTIVATION_TEMPLATE_KEY not in other["process_state_metadata"]
    assert other["limitations"][-1] == (
        "Enzyme activity assumed constant over the run for Ester hydrolase-like class V1 on Dissolved ester-like "
        "substrate E1: kinetics.csv gives no inactivation_rate for it, so its enzyme state has no inactivation term "
        "(FungMod applies no default constant)."
    )
    assert [item["enzyme_class"] for item in dataset.enzyme_inactivation] == [HYDROLASE]


@pytest.mark.parametrize("fixture", sorted(RECORDS_6567464))
def test_earlier_fixtures_generate_the_records_of_6567464(fixture: str) -> None:
    dataset = load_user_dataset(FIXTURES / fixture, registry=REGISTRY_INDEX)
    digest = hashlib.sha256(json.dumps(dataset.to_dict()["records"], sort_keys=True).encode("utf-8")).hexdigest()
    assert digest == RECORDS_6567464[fixture]
    assert dataset.enzyme_inactivation == ()
    assert all(
        process["enzyme_inactivation"] is None for item in dataset.enzyme_networks for process in item["processes"]
    )


class _LowerBound:
    """A stand-in random generator: every ranged record is taken at its lower bound."""

    def uniform(self, low: float, high: float) -> float:
        del high
        return low


def _config_digests(registry: Any, fungi: Sequence[str], substrates: Sequence[str], environments: Sequence[str]) -> dict[str, str]:
    digests: dict[str, str] = {}
    for fungus in fungi:
        for substrate in substrates:
            for environment in environments:
                for mode in ("exploratory", "scientific"):
                    report = assess_modelability(
                        fungus_id=fungus, substrate_id=substrate, environment_id=environment, registry=registry, mode=mode
                    )
                    if report.status not in ({"modelable"} if mode == "scientific" else {"modelable", "exploratory"}):
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
                        mode=mode,
                    )
                    if mode != "scientific":
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
                    digests[f"{fungus}|{substrate}|{environment}|{mode}"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return digests


@pytest.mark.parametrize("group", sorted(CONFIGS_6567464))
def test_earlier_cases_assemble_the_configs_of_6567464(group: str) -> None:
    base = load_registry(REGISTRY_INDEX)
    if group == "registry":
        digests = _config_digests(base, sorted(base.fungi), sorted(base.substrates), sorted(base.environments))
    else:
        dataset = load_user_dataset(FIXTURES / group, registry=REGISTRY_INDEX)
        substrates = [item["record_id"] for item in dataset.records["substrates"]] + [
            record_id for record_type, record_id in dataset._base_references if record_type == "substrates"
        ]
        digests = _config_digests(
            dataset.overlay(base),
            [item["record_id"] for item in dataset.records["fungi"]],
            substrates,
            [item["record_id"] for item in dataset.records["environments"]],
        )
    assert hashlib.sha256(json.dumps(digests, sort_keys=True).encode("utf-8")).hexdigest() == CONFIGS_6567464[group]


def test_measured_rows_make_the_case_scientific_until_one_is_an_estimate(tmp_path: Path) -> None:
    measured = _csv_text(
        [
            {**row, "evidence_type": "measured", "method": "initial-rate assay"}
            for row in _rows(CASE, "kinetics.csv")
        ],
        KINETICS_HEADER,
    )
    dataset = _load(tmp_path / "measured", CASE, {"kinetics.csv": measured})
    (template,) = dataset.records["case_templates"]
    assert template["process_state_metadata"]["config_mode"] == "scientific"
    study = virtual_experiment(
        fungi=["strain_v1"], substrates=["amide_a1"], environments=["c40_ph6"], registry=REGISTRY_INDEX, user_data=dataset
    )
    (report,) = study.preflight(mode="scientific")
    assert report.status == "modelable"
    weakest = _csv_text(
        [
            {**row, "evidence_type": "measured", "method": "initial-rate assay"}
            if row["quantity"] != INACTIVATION_RATE_QUANTITY
            else row
            for row in _rows(CASE, "kinetics.csv")
        ],
        KINETICS_HEADER,
    )
    estimated = _load(tmp_path / "estimate", CASE, {"kinetics.csv": weakest})
    (template,) = estimated.records["case_templates"]
    assert template["process_state_metadata"]["config_mode"] == "exploratory", "the estimated k_d alone keeps it exploratory"


# ---------------------------------------------------------------------------
# The Arrhenius law of the inactivation constant, in a network on a solid


def test_the_network_binds_the_thermal_law_to_one_member_only(network: UserDataset) -> None:
    (template,) = network.records["case_templates"]
    processes = template["process_state_metadata"]["process_templates"]
    assert [item["id"] for item in processes] == [
        f"{NETWORK_ID}__{FAST}__solid_w7__homogeneous_mm",
        f"{NETWORK_ID}__{STABLE}__solid_w7__homogeneous_mm",
        NETWORK_LOSS,
    ]
    loss = processes[-1]
    assert loss["process_type"] == INACTIVATION_LAW
    assert loss["state_roles"] == {"active": f"enzyme_{FAST}"}
    assert loss["parameter_roles"] == {
        "reference_rate_constant": f"inactivation_rate__{FAST}__solid_w7",
        "inactivation_energy": f"thermal_inactivation__activation_energy__{FAST}__solid_w7",
        "reference_temperature": f"thermal_inactivation__reference_temperature__{FAST}__solid_w7",
    }
    assert "modifiers" not in processes[0], "the law scales the inactivation constant, not the catalytic rate"
    (entry,) = network.enzyme_networks
    assert [(item["enzyme_class"], item["response_laws"], item["enzyme_inactivation"]) for item in entry["processes"]] == [
        (FAST, [], INACTIVATION_LAW),
        (STABLE, [], None),
    ]
    limitations = template["limitations"]
    assert any(text.startswith("Enzyme inactivation of Fast cutter-like class W7") for text in limitations)
    assert any(text.startswith("Enzyme activity assumed constant over the run for Stable cutter-like class W7") for text in limitations)
    assert any("only its inactivation constant changes" in text for text in limitations)
    records = {item["parameter_symbol"]: item for item in network.records["parameter_records"]}
    reference = records[f"{NETWORK_ID}__network__solid_w7__thermal_inactivation__reference_temperature__{FAST}__solid_w7"]
    assert reference["value"]["value"] == pytest.approx(328.15) and reference["value"]["units"] == "kelvin"
    assert reference["environment_id"] is None, "a law applies at every environment, EnvironmentGrid conditions included"
    assert "inactivation_rate of this strain" in reference["provenance"]["fungmod_user_dataset"]["reference_condition"]["rule"]
    energy = records[f"{NETWORK_ID}__network__solid_w7__thermal_inactivation__activation_energy__{FAST}__solid_w7"]
    assert energy["value"]["value"] == 200.0 and energy["value"]["units"] == "kJ/mol"
    assert "not the catalytic constants" in energy["provenance"]["validity_range"]


def test_each_enzyme_decays_by_its_own_law_at_every_temperature_of_the_grid(network_grid: Any) -> None:
    series = _series(network_grid)
    temperatures = _temperatures(network_grid)
    assert sorted(temperatures.values()) == [50.0, 55.0, 60.0]
    final: dict[float, float] = {}
    for environment, temperature in temperatures.items():
        times, fast, units = series[(environment, 0, f"enzyme_{FAST}")]
        assert units == "milligram / liter" and times[-1] == 48.0
        kd = FAST_KD * _arrhenius(temperature, FAST_ENERGY, FAST_TREF)
        np.testing.assert_allclose(fast, FAST_E0 * np.exp(-kd * times), rtol=1e-5, atol=1e-9 * FAST_E0)
        _t, stable, _u = series[(environment, 0, f"enzyme_{STABLE}")]
        np.testing.assert_allclose(stable, STABLE_E0, rtol=1e-12)
        _t, substrate, _u = series[(environment, 0, "substrate")]
        _t, product, _u = series[(environment, 0, "product")]
        np.testing.assert_allclose(substrate + product, SOLID_S0, rtol=1e-9)
        # Each Michaelis-Menten process runs at kcat E S / (Km + S) with its own enzyme; the degradation adds them.
        _t, rate_fast, _u = series[(environment, 0, f"process_rate.{NETWORK_ID}__{FAST}__solid_w7__homogeneous_mm")]
        _t, rate_stable, _u = series[(environment, 0, f"process_rate.{NETWORK_ID}__{STABLE}__solid_w7__homogeneous_mm")]
        np.testing.assert_allclose(rate_fast, FAST_KCAT * fast * substrate / (FAST_KM + substrate), rtol=1e-9, atol=1e-15)
        np.testing.assert_allclose(rate_stable, STABLE_KCAT * stable * substrate / (STABLE_KM + substrate), rtol=1e-9)
        _t, degradation, _u = series[(environment, 0, "degradation_rate")]
        np.testing.assert_allclose(degradation, rate_fast + rate_stable, rtol=1e-6, atol=1e-12)
        final[temperature] = float(substrate[-1])
    # The catalytic constants are not rescaled: a hotter run loses its fast enzyme sooner and degrades less.
    assert final[50.0] < final[55.0] < final[60.0]


def test_the_case_reports_the_thermal_law_as_its_temperature_response(network_grid: Any) -> None:
    response = network_grid.screen_result.case_results[0].environment_response
    assert response["conditions"] == {
        "temperature": {
            "status": "active_response_model",
            "laws": [{"process_id": NETWORK_LOSS, "law": INACTIVATION_LAW, "binding": "process_law"}],
        }
    }
    rows = [row for row in network_grid.mechanism_summary() if row["mechanism_id"] == NETWORK_LOSS]
    assert rows and all(row["configured_by"] == f"{NETWORK_ID}__{FAST}" for row in rows)
    assert all(row["mechanism_family"] == "generic first-order thermal inactivation with an Arrhenius rate constant" for row in rows)
    assert all(row["limitations"].startswith("Irreversible first-order loss with an Arrhenius-scaled constant") for row in rows)


def test_a_rate_law_and_the_inactivation_law_compose_on_one_pair(tmp_path: Path) -> None:
    """Both read the temperature; the Arrhenius rate law scales kcat, the inactivation law k_d, and their roles differ."""

    responses = _csv_text(
        [
            _law("activation_energy", "40", "kJ/mol", law="temperature_arrhenius_reference"),
            _law("reference_temperature", "40", "degC", law="temperature_arrhenius_reference"),
            _law("activation_energy", "150", "kJ/mol"),
            _law("reference_temperature", "40", "degC"),
        ],
        RESPONSES_HEADER,
    )
    dataset = _load(tmp_path, CASE, {"responses.csv": responses})
    (compatibility,) = dataset.records["process_compatibility"]
    assert {
        role: symbol
        for role, symbol in compatibility["parameter_roles"].items()
        if "energy" in role or "temperature" in role
    } == {
        "activation_energy": f"{CASE_ID}__temperature_arrhenius_reference__activation_energy__{HYDROLASE}__amide_a1",
        "reference_temperature": f"{CASE_ID}__temperature_arrhenius_reference__reference_temperature__{HYDROLASE}__amide_a1",
        "thermal_inactivation__activation_energy": f"{CASE_ID}__thermal_inactivation__activation_energy__{HYDROLASE}__amide_a1",
        "thermal_inactivation__reference_temperature": (
            f"{CASE_ID}__thermal_inactivation__reference_temperature__{HYDROLASE}__amide_a1"
        ),
    }
    (template,) = dataset.records["case_templates"]
    assert [item["type"] for item in template["process_state_metadata"]["process_modifiers"]] == [
        "temperature_arrhenius_reference"
    ]
    result = _simulate(
        tmp_path / "run",
        dataset,
        fungus="strain_v1",
        substrate="amide_a1",
        environments=environment_grid(temperature_C=[35, 45], ph=[6.0]),
    )
    series = _series(result)
    for environment, temperature in _temperatures(result).items():
        times, enzyme, _u = series[(environment, 0, "enzyme")]
        kd = KD * _arrhenius(temperature, 150000.0, 40.0)
        np.testing.assert_allclose(enzyme, E0 * np.exp(-kd * times), rtol=1e-6)
        _t, substrate, _u = series[(environment, 0, "substrate")]
        kcat = KCAT * _arrhenius(temperature, 40000.0, 40.0)
        np.testing.assert_allclose(
            substrate, _michaelis_menten_with_decay(times, s0=S0, km=KM, kcat=kcat, e0=E0, kd=kd), rtol=1e-5
        )


def test_an_inactivation_rate_within_the_reference_tolerance_is_rescaled_by_the_law(tmp_path: Path) -> None:
    responses = _csv_text(
        [_law("activation_energy", "150", "kJ/mol"), _law("reference_temperature", "41", "degC", reference_tolerance="1")],
        RESPONSES_HEADER,
    )
    result = _simulate(
        tmp_path / "run",
        _copy_fixture(tmp_path, CASE, edits={"responses.csv": responses}),
        fungus="strain_v1",
        substrate="amide_a1",
        environments=["c40_ph6"],
    )
    times, enzyme, _u = _series(result)[(f"{CASE_ID}__c40_ph6", 0, "enzyme")]
    # The row is taken as the reference value at 41 degC, so the case at 40 degC runs slightly slower.
    kd = KD * _arrhenius(40.0, 150000.0, 41.0)
    assert kd < KD
    np.testing.assert_allclose(enzyme, E0 * np.exp(-kd * times), rtol=1e-8)


def test_an_assembled_draft_keeps_the_rows_and_carries_no_kinetics_by_the_thermal_law(tmp_path: Path) -> None:
    """The law scales k_d only, so it never carries kcat or Km to another temperature of a draft."""

    laws = _csv_text([_law("activation_energy", "150", "kJ/mol"), _law("reference_temperature", "40", "degC")], RESPONSES_HEADER)
    dataset = _copy_fixture(tmp_path, CASE, edits={"responses.csv": laws})
    cases: dict[float, Mapping[str, Any]] = {}
    for temperature in (40.0, 45.0):
        draft = assemble_user_tables(
            dataset_id=f"draft_{int(temperature)}",
            fungus="strain_v1",
            substrates=["amide_a1"],
            conditions=[{"condition_id": f"c{int(temperature)}", "temperature": temperature, "temperature_units": "degC", "ph": 6}],
            user_data=dataset,
            registry=REGISTRY_INDEX,
        )
        tables = draft.tables()
        assert [row["quantity"] for row in tables["kinetics.csv"]][-1] == INACTIVATION_RATE_QUANTITY
        assert [row["law"] for row in tables["responses.csv"]] == [INACTIVATION_LAW, INACTIVATION_LAW]
        (cases[temperature],) = draft.to_dict()["assembly"]["cases"]
    assert (cases[40.0]["kinetics_status"], cases[40.0]["condition_route"]) == ("user_data", "same_condition")
    assert (cases[45.0]["kinetics_status"], cases[45.0]["condition_route"]) == ("gap", "none")


# ---------------------------------------------------------------------------
# Other rate forms and materials: the same loss of whatever enzyme state the case has


def test_a_ph_ionization_case_loses_its_enzyme_by_the_same_law(tmp_path: Path) -> None:
    source = FIXTURES / "bgl1a_ph_ionization"
    (first,) = [row for row in _rows(source, "kinetics.csv") if row["quantity"] == "enzyme_concentration"]
    row = {**first, "quantity": INACTIVATION_RATE_QUANTITY, "value": "0.5", "units": "1/h", "sd": ""}
    dataset = _load(tmp_path, source, {"kinetics.csv": _with_rows(source, "kinetics.csv", row)})
    (template,) = dataset.records["case_templates"]
    assert template["process_type"] == "ph_ionization_michaelis_menten"
    assert template["process_state_metadata"][ENZYME_INACTIVATION_TEMPLATE_KEY]["process_type"] == "first_order"
    result = _simulate(
        tmp_path / "run", dataset, fungus="bgl1a_source", substrate="cellobiose", environments=[first["condition_id"]]
    )
    ((key, (times, enzyme, units)),) = [(key, value) for key, value in _series(result).items() if key[2] == "enzyme"]
    assert units == "millimolar" and times[-1] == 14400.0
    np.testing.assert_allclose(enzyme, float(first["value"]) * np.exp(-(0.5 / 3600.0) * times), rtol=1e-6)
    assert [row["mechanism_id"] for row in result.mechanism_summary()][:2] == [
        "ph_ionization_michaelis_menten",
        f"{dataset.dataset_id}__beta_glucosidase__cellobiose__enzyme_inactivation",
    ]


def test_an_enzyme_in_assay_units_on_a_solid_decays_in_its_own_units(tmp_path: Path) -> None:
    """The solid_case fixture states its enzyme as a dose in FPU per gram; the derived FPU/L pool decays at k_d."""

    source = FIXTURES / "solid_case"
    rows = [
        _kinetic(
            strain_id="strain_p1",
            enzyme_class="cellulase_total_filter_paper_activity",
            substrate_id="particulate_lot_p1",
            condition_id=condition,
            value="0.02",
        )
        for condition in ("dose_5", "dose_1_25")
    ]
    dataset = _load(tmp_path, source, {"kinetics.csv": _with_rows(source, "kinetics.csv", *rows)})
    result = _simulate(
        tmp_path / "run", dataset, fungus="strain_p1", substrate="particulate_lot_p1", environments=["dose_5", "dose_1_25"]
    )
    series = _series(result)
    doses = {"dose_5": 5.0, "dose_1_25": 1.25}
    for environment, dose in doses.items():
        times, enzyme, units = series[(f"{dataset.dataset_id}__{environment}", 0, "enzyme")]
        assert units in {"filter_paper_unit / liter", "FPU / liter"}
        np.testing.assert_allclose(enzyme, dose * SOLID_S0 * np.exp(-0.02 * times), rtol=1e-8)


# ---------------------------------------------------------------------------
# Refusals


@pytest.mark.parametrize(
    ("row", "column", "message"),
    [
        pytest.param({"units": "mM"}, "units", "must have the dimension 1/time", id="molar"),
        pytest.param({"units": "h"}, "units", "A half-life is not a rate constant", id="half_life"),
        pytest.param({"value": "-0.3"}, "value", "value must be nonnegative", id="negative"),
        pytest.param({"evidence_type": "fitted"}, "evidence_type", "inactivation_rate is not a fitted quantity", id="fitted"),
    ],
)
def test_an_inactivation_rate_row_is_checked(tmp_path: Path, row: dict[str, str], column: str, message: str) -> None:
    kinetics = _with_rows(CASE, "kinetics.csv", _kinetic(**row), drop=(INACTIVATION_RATE_QUANTITY,))
    issues = _issues(tmp_path, CASE, {"kinetics.csv": kinetics})
    assert _has_issue(issues, "kinetics.csv", 6, column, message), issues


def test_two_rows_for_one_case_are_refused(tmp_path: Path) -> None:
    kinetics = _with_rows(CASE, "kinetics.csv", _kinetic(value="0.4"))
    issues = _issues(tmp_path, CASE, {"kinetics.csv": kinetics})
    assert _has_issue(issues, "kinetics.csv", 7, "quantity", "duplicate or conflicting rows for the same quantity"), issues


def test_the_vmax_form_has_no_enzyme_state_to_lose(tmp_path: Path) -> None:
    source = FIXTURES / "oxidase_case"
    row = _kinetic(strain_id="strain_l1", enzyme_class="laccase_like_oxidase", substrate_id="syringaldazine_like", condition_id="c50_ph5")
    laws = _with_rows(
        source,
        "responses.csv",
        {**_law("activation_energy", "150", "kJ/mol"), "strain_id": "strain_l1", "enzyme_class": "laccase_like_oxidase", "substrate_id": "syringaldazine_like"},
        {**_law("reference_temperature", "50", "degC"), "strain_id": "strain_l1", "enzyme_class": "laccase_like_oxidase", "substrate_id": "syringaldazine_like"},
    )
    issues = _issues(tmp_path, source, {"kinetics.csv": _with_rows(source, "kinetics.csv", row), "responses.csv": laws})
    assert _has_issue(issues, "kinetics.csv", 6, "quantity", "uses the Vmax form, which has no enzyme state"), issues
    assert _has_issue(issues, "responses.csv", 8, "law", "thermal_inactivation scales the first-order inactivation"), issues


def test_a_culture_pool_keeps_its_own_loss_rate(tmp_path: Path) -> None:
    source = FIXTURES / "culture_estimates"
    (pool,) = {row["enzyme_class"] for row in _rows(source, "culture.csv") if row["enzyme_class"]}
    (substrate,) = _rows(source, "substrates.csv")
    row = _kinetic(
        strain_id="strain_x1", enzyme_class=pool, substrate_id=substrate["substrate_id"], condition_id="c25", value="0.01"
    )
    issues = _issues(tmp_path, source, {"kinetics.csv": _with_rows(source, "kinetics.csv", row)})
    assert _has_issue(issues, "kinetics.csv", 2, "quantity", "FungMod adds no second loss law to a culture pool"), issues
    assert _has_issue(issues, "kinetics.csv", 2, "quantity", "enzyme_loss_rate in culture.csv"), issues
    laws = _csv_text(
        [
            {**_law(name, value, units), "strain_id": "strain_x1", "enzyme_class": pool, "substrate_id": substrate["substrate_id"]}
            for name, value, units in (("activation_energy", "150", "kJ/mol"), ("reference_temperature", "25", "degC"))
        ],
        RESPONSES_HEADER,
    )
    issues = _issues(tmp_path / "law", source, {"responses.csv": laws})
    assert _has_issue(issues, "responses.csv", 2, "law", "a culture pool is lost at its own enzyme_loss_rate"), issues


@pytest.mark.parametrize(
    ("rows", "row", "column", "message"),
    [
        pytest.param(
            (("activation_energy", "150", "kJ/mol", {}), ("reference_temperature", "50", "degC", {})),
            3,
            "value",
            "is not at the reference temperature of thermal_inactivation",
            id="off_reference",
        ),
        pytest.param(
            (("activation_energy", "-5", "kJ/mol", {}), ("reference_temperature", "40", "degC", {})),
            2,
            "value",
            "activation_energy must be nonnegative",
            id="negative_energy",
        ),
        pytest.param(
            (("activation_energy", "150", "kJ/mol", {}),),
            2,
            "parameter",
            "needs activation_energy, reference_temperature; missing: reference_temperature",
            id="missing_reference",
        ),
        pytest.param(
            (("minimum_temperature", "10", "degC", {}),),
            2,
            "parameter",
            "not a parameter of thermal_inactivation",
            id="bounds",
        ),
        pytest.param(
            (("activation_energy", "150", "J"), ("reference_temperature", "40", "degC", {})),
            2,
            "units",
            "must be an energy per amount",
            id="energy_units",
        ),
    ],
)
def test_the_thermal_law_is_checked(tmp_path: Path, rows: Any, row: int, column: str, message: str) -> None:
    laws = _csv_text([_law(name, value, units) for name, value, units, *_rest in rows], RESPONSES_HEADER)
    issues = _issues(tmp_path, CASE, {"responses.csv": laws})
    assert _has_issue(issues, "responses.csv", row, column, message), issues


def test_an_unknown_temperature_cannot_carry_a_rate_the_law_scales(tmp_path: Path) -> None:
    conditions = "condition_id,temperature,temperature_units,ph,notes\nc40_ph6,unknown,degC,6,\n"
    laws = _csv_text([_law("activation_energy", "150", "kJ/mol"), _law("reference_temperature", "40", "degC")], RESPONSES_HEADER)
    issues = _issues(tmp_path, CASE, {"conditions.csv": conditions, "responses.csv": laws})
    assert _has_issue(issues, "responses.csv", 3, "value", "has an unknown temperature, but kinetics.csv row 6 give the inactivation_rate"), issues


# ---------------------------------------------------------------------------
# The assembler's declared loss process


def _resolved_case(dataset: UserDataset, fungus: str, substrate: str, environment: str) -> tuple[Any, Any, Any, CaseTemplateRecord]:
    registry = dataset.overlay(load_registry(REGISTRY_INDEX))
    report = assess_modelability(
        fungus_id=fungus, substrate_id=substrate, environment_id=environment, registry=registry, mode="exploratory"
    )
    compatibility = select_registry_case_compatibility(registry=registry, fungus_id=fungus, substrate_id=substrate, report=report)
    records = resolve_screen_role_records(
        registry=registry,
        compatibility=compatibility,
        fungus_id=fungus,
        substrate_id=substrate,
        environment_id=environment,
        mode="exploratory",
    )
    return registry, compatibility, records, registry.get_case_template(compatibility.case_template_id)


def _build(registry: Any, compatibility: Any, records: Any, template: CaseTemplateRecord, metadata: Mapping[str, Any]) -> Any:
    changed = replace(template, process_state_metadata={**template.process_state_metadata, **metadata})
    return build_registry_process_config_data(
        registry=registry,
        compatibility=compatibility,
        fungus_id=compatibility_fungus(records),
        substrate_id=compatibility_substrate(records),
        environment_id=compatibility_environment(records),
        parameter_records=records,
        output_directory=None,
        case_template=changed,
    )


def compatibility_fungus(records: Mapping[str, Any]) -> str:
    return str(next(record.fungus_id for record in records.values() if record.fungus_id))


def compatibility_substrate(records: Mapping[str, Any]) -> str:
    return str(next(record.substrate_id for record in records.values() if record.substrate_id))


def compatibility_environment(records: Mapping[str, Any]) -> str:
    return str(next(record.environment_id for record in records.values() if record.environment_id))


@pytest.mark.parametrize(
    ("change", "message"),
    [
        pytest.param({"process_type": "mass_action"}, "is not a law the enzyme state can be lost through", id="law"),
        pytest.param({"parameter_roles": {"rate_constant": "inactivation_rate", "extra": "km"}}, "must bind exactly rate_constant", id="roles"),
        pytest.param({"parameter_roles": {"rate_constant": "no_such_role"}}, "references unresolved role 'no_such_role'", id="unresolved"),
        pytest.param({"assumptions": []}, "must declare at least one explicit assumption", id="assumptions"),
        pytest.param({"process_id": CASE_PROCESS}, "distinct from the template's process_id", id="same_id"),
        pytest.param({"inactive_state": "x"}, "unsupported field(s): inactive_state", id="field"),
    ],
)
def test_the_assembler_refuses_a_malformed_declaration(case: UserDataset, change: dict[str, Any], message: str) -> None:
    registry, compatibility, records, template = _resolved_case(
        case, f"{CASE_ID}__strain_v1", f"{CASE_ID}__amide_a1", f"{CASE_ID}__c40_ph6"
    )
    declared = {**template.process_state_metadata[ENZYME_INACTIVATION_TEMPLATE_KEY], **change}
    with pytest.raises(RegistryCaseBuildError, match="enzyme_inactivation") as excinfo:
        _build(registry, compatibility, records, template, {ENZYME_INACTIVATION_TEMPLATE_KEY: declared})
    assert message in str(excinfo.value)


def test_the_assembler_refuses_a_loss_on_a_role_set_without_an_enzyme() -> None:
    oxidase = load_user_dataset(FIXTURES / "oxidase_case", registry=REGISTRY_INDEX)
    registry, compatibility, records, template = _resolved_case(
        oxidase, "oxidase_demo__strain_l1", "oxidase_demo__syringaldazine_like", "oxidase_demo__c50_ph5"
    )
    declared = {
        "process_id": "a_loss",
        "process_type": "first_order",
        "parameter_roles": {"rate_constant": "km"},
        "assumptions": ["A test-only declaration on the Vmax role set."],
    }
    with pytest.raises(RegistryCaseBuildError, match="has no enzyme state"):
        _build(registry, compatibility, records, template, {ENZYME_INACTIVATION_TEMPLATE_KEY: declared})


# ---------------------------------------------------------------------------
# Command line


def test_check_data_lists_the_inactivation_and_reports_a_refusal(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code, out, err = _cli(capsys, "check-data", NETWORK, "--registry", REGISTRY_INDEX)
    assert code == EXIT_OK, err
    assert (
        "Enzyme inactivation (kinetics.csv inactivation_rate, responses.csv thermal_inactivation; every other enzyme "
        "state is not lost): 1"
    ) in out
    assert "fast_cutter_w7  solid_w7   thermal_inactivation  6                  2, 3" in out
    code, out, _err = _cli(capsys, "check-data", FIXTURES / "esterase_case", "--registry", REGISTRY_INDEX)
    assert code == EXIT_OK and "Enzyme inactivation" not in out
    kinetics = _with_rows(CASE, "kinetics.csv", _kinetic(units="mM"), drop=(INACTIVATION_RATE_QUANTITY,))
    dataset = _copy_fixture(tmp_path, CASE, edits={"kinetics.csv": kinetics})
    code, _out, err = _cli(capsys, "check-data", dataset, "--registry", REGISTRY_INDEX)
    assert code == EXIT_USAGE
    assert "kinetics.csv:6:units: inactivation_rate units 'mM' must have the dimension 1/time" in err


def test_run_simulates_the_decaying_enzyme(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code, out, err = _cli(
        capsys,
        "run",
        "--user-data",
        NETWORK,
        "--fungus",
        "strain_w7",
        "--substrate",
        "solid_w7",
        "--temperature-c",
        "50",
        "--temperature-c",
        "60",
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
    assert out.count("environment effect: active_response_model (temperature:thermal_inactivation)") == 2
    with (tmp_path / "run" / "time_series_long.csv").open(encoding="utf-8", newline="") as handle:
        roles = {row["state_role"] for row in csv.DictReader(handle) if row["source"] == "simulation_state"}
    assert {f"enzyme_{FAST}", f"enzyme_{STABLE}", "substrate", "product"} <= roles
    code, out, err = _cli(
        capsys,
        "run",
        "--user-data",
        CASE,
        "--fungus",
        "strain_v1",
        "--substrate",
        "amide_a1",
        "--environment",
        "c40_ph6",
        "--mode",
        "exploratory",
        "--samples",
        "1",
        "--seed",
        "2",
        "--output",
        tmp_path / "case",
        "--no-plots",
    )
    assert code == EXIT_OK, err
    assert "Simulated 1 case(s) in exploratory mode" in out
