"""Several enzyme classes acting together in user data (USERDATA-010).

An ``enzyme_network`` block in ``user_dataset.yml`` turns every case of a
dataset into a network: every declared enzyme class that acts on a pool of the
network runs its own homogeneous Michaelis-Menten process (kcat or Vmax form),
processes on one pool add their rates, and a pool released by one process is
the substrate of the next where a substrate's ``substrates.csv`` product equals
another ``substrate_id``. A ``ki`` row with an ``inhibitor`` binds the existing
competitive-inhibition modifier. No new numerics: the compiled core already sums
the processes of a model on shared states.

``tests/fixtures/user_data/network_chain`` is a user-defined strain whose two
user-defined classes degrade a soluble polymer-like substrate through an
oligomer-like pool to a monomer-like product. ``tests/fixtures/user_data/
network_parallel`` is the materially different case: two user-defined classes in
parallel on one dissolved ester-like substrate, one in the kcat and one in the
Vmax form, one of them competitively inhibited by the released product. Every
value of both is an illustrative estimate. Other datasets are derived from them
(or from earlier fixtures) in temporary directories to test gaps, analytic
limits and refusals only.
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

from fungal_model import UserDataError, UserDataset, load_user_dataset, virtual_experiment
from fungal_model.api import VirtualExperimentError
from fungal_model.api.user_data import (
    COMPETITIVE_INHIBITION_LAW_MATURITY,
    COMPETITIVE_INHIBITION_LAW_SOURCE,
    USER_DATASET_MATURITY_GAP,
    USER_DATASET_NETWORK_PROCESS_TYPE,
)
from fungal_model.api.user_data_assembly import UserTablesAssemblyError, assemble_user_tables
from fungal_model.cli import EXIT_OK, EXIT_PARTIAL, EXIT_USAGE, main
from fungal_model.registry import load_registry
from fungal_model.screening import RegistryCaseBuildError
from fungal_model.screening.case_builder import get_registry_process_assembler
from fungal_model.screening.culture_physiology import build_culture_physiology_config_data
from fungal_model.screening.ensemble import resolve_screen_role_records
from fungal_model.screening.enzyme_network import ENZYME_NETWORK_PROCESS_TYPE, build_enzyme_network_config_data

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"
FIXTURES = ROOT / "tests" / "fixtures" / "user_data"
CHAIN = FIXTURES / "network_chain"
PARALLEL = FIXTURES / "network_parallel"

# SHA-256 of json.dumps(dataset.to_dict()["records"], sort_keys=True) of every earlier fixture, computed with the base
# commit of USERDATA-010 (67c8a74): a dataset without enzyme_network must generate the same records.
EARLIER_RECORD_DIGESTS = {
    "esterase_case": "4f92a532f98356be6ac680b4652ac411a975e3c772dd2f0348c590a207ef3464",
    "literature_reentry": "37baa76aaefcbe1d27746720218eafd7712a47ca8c0927245eea597895fce6e1",
    "oxidase_case": "eb82f225a0cd09115afb44b67e0bb2496e7bf11ee7f0960624759b1970f7e322",
    "bgl1a_ph_ionization": "5a5c837fde83d33c1b01fdfd88499eddd4112fbc8a4c3097e6efcaa246af60f1",
    "solid_case": "9b1eecb8cd6820ec7c1c27f17bff9d4820e5679c0350a77c3caba1ced2215e83",
    "genome_case": "f13786fee336d8c58e9dc5d052e1b138158ade98d268cd6b0788ed6b5a8b118e",
    "uniprot_case": "8ec0dfbf50881d866a00b0392149a1dd60cd8260ac3acdd771e5b7d71a5b6532",
    "culture_reentry": "013ebc0dd3decea7b8952e54636b48977e1767c9b1ef732cfed3b1fc48d2c698",
    "culture_estimates": "4cc4a3de85c4c74c83abf95d7f1bd9cbe72916db52d6800cdffadd0a094743f0",
}

CHAIN_ID = "network_chain"
DEPOLYMERASE = "depolymerase_like"
OLIGOMER_HYDROLASE = "oligomer_hydrolase_like"
PROCESS_A = f"{CHAIN_ID}__{DEPOLYMERASE}__polymer_p1__homogeneous_mm"
PROCESS_B = f"{CHAIN_ID}__{OLIGOMER_HYDROLASE}__oligomer_o1__homogeneous_mm"
PARALLEL_ID = "network_parallel"
CLEAVER_A = "cleaver_a_like"
CLEAVER_B = "cleaver_b_like"
PROCESS_PA = f"{PARALLEL_ID}__{CLEAVER_A}__ester_s2__homogeneous_mm"
PROCESS_PB = f"{PARALLEL_ID}__{CLEAVER_B}__ester_s2__homogeneous_mm"

# The fixtures' constants, in the units the analytic checks use.
CHAIN_KM_A, CHAIN_VMAX_A = 2.0, 30.0 * 0.002  # mM, mM/min (kcat 30 1/min x E 0.002 mM)
CHAIN_KM_B, CHAIN_VMAX_B = 1.0, 60.0 * 0.001  # mM, mM/min
CHAIN_S0, CHAIN_Y1, CHAIN_Y2 = 5.0, 4.0, 2.0  # mM, mol/mol, mol/mol
PAR_KM_A, PAR_VMAX_A, PAR_KI_A = 400.0, 2.0 * 60.0 * 0.5, 200.0  # uM, uM/h (kcat 2 1/min x E 0.5 uM), uM
PAR_KM_B, PAR_VMAX_B = 50.0, 0.5 * 60.0  # uM, uM/h (vmax 0.5 uM/min)

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
    "inhibitor",
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


def _kinetics(
    source: Path,
    *,
    drop: Sequence[tuple[str, str]] = (),
    change: Mapping[tuple[str, str], Mapping[str, str]] | None = None,
    add: Sequence[Mapping[str, str]] = (),
) -> str:
    """The fixture's kinetics.csv with (class, quantity) rows dropped or changed and rows added."""

    rows = []
    for row in _rows(source, "kinetics.csv"):
        key = (row["enzyme_class"], row["quantity"])
        if key in drop:
            continue
        rows.append({**row, **(change or {}).get(key, {})})
    rows.extend({**{column: "" for column in KINETICS_HEADER}, **extra} for extra in add)
    return _csv_text(rows, KINETICS_HEADER)


def _row(source: Path, class_key: str, template_quantity: str, **cells: str) -> dict[str, str]:
    """A copy of the fixture's (class, quantity) row with cells replaced."""

    (row,) = [
        item
        for item in _rows(source, "kinetics.csv")
        if (item["enzyme_class"], item["quantity"]) == (class_key, template_quantity)
    ]
    return {**row, **cells}


def _line(source: Path, class_key: str, quantity: str, condition: str | None = None) -> int:
    for index, row in enumerate(_rows(source, "kinetics.csv"), start=2):
        if (row["enzyme_class"], row["quantity"]) == (class_key, quantity) and condition in (None, row["condition_id"]):
            return index
    raise AssertionError((class_key, quantity))


def _manifest(source: Path, **changes: Any) -> str:
    data = yaml.safe_load((source / "user_dataset.yml").read_text(encoding="utf-8"))
    for key, value in changes.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    return yaml.safe_dump(data, sort_keys=False)


def _series(result: Any) -> dict[tuple[str, str], tuple[np.ndarray, np.ndarray, str]]:
    """(environment id, state or role key) -> (times, values, units) of sample 0.

    Simulated states are keyed by state role, process rates by ``process_rate.<id>``
    and state rates by their observable name.
    """

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


def _simulate(
    tmp_path: Path,
    user_data: Path | UserDataset,
    *,
    fungus: str,
    substrate: str,
    environments: Sequence[str],
    **kwargs: Any,
) -> Any:
    study = virtual_experiment(
        fungi=[fungus],
        substrates=[substrate],
        environments=list(environments),
        registry=REGISTRY_INDEX,
        user_data=user_data,
    )
    options: dict[str, Any] = {"mode": "exploratory", "n_samples": 1, "seed": 1, "quicklook": False}
    options.update(kwargs)
    return study.simulate(output_dir=tmp_path, **options)


def _cli(capsys: pytest.CaptureFixture[str], *args: str | Path) -> tuple[int, str, str]:
    code = main([str(arg) for arg in args])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.fixture(scope="module")
def chain() -> UserDataset:
    return load_user_dataset(CHAIN, registry=REGISTRY_INDEX)


@pytest.fixture(scope="module")
def parallel() -> UserDataset:
    return load_user_dataset(PARALLEL, registry=REGISTRY_INDEX)


@pytest.fixture(scope="module")
def chain_run(tmp_path_factory: pytest.TempPathFactory) -> Any:
    return _simulate(
        tmp_path_factory.mktemp("chain"), CHAIN, fungus="strain_n1", substrate="polymer_p1", environments=["c30_ph5"]
    )


@pytest.fixture(scope="module")
def parallel_run(tmp_path_factory: pytest.TempPathFactory) -> Any:
    return _simulate(
        tmp_path_factory.mktemp("parallel"),
        PARALLEL,
        fungus="strain_q2",
        substrate="ester_s2",
        environments=["c25_ph7"],
    )


# ---------------------------------------------------------------------------
# What a network dataset generates


def test_chain_links_pools_only_through_explicit_products(chain: UserDataset) -> None:
    (network,) = chain.enzyme_networks
    assert network["entry_substrate"] == "polymer_p1"
    assert network["pools"] == ["polymer_p1", "oligomer_o1"]
    assert network["product"] == "monomer_m1"
    assert [(link["substrate_id"], link["releases"], link["yield"], link["yield_basis"]) for link in network["links"]] == [
        ("polymer_p1", "oligomer_o1", 4.0, "mol/mol"),
        ("oligomer_o1", "monomer_m1", 2.0, "mol/mol"),
    ]
    assert [(item["enzyme_class"], item["pool"], item["rate_form"], item["inhibitor"]) for item in network["processes"]] == [
        (DEPOLYMERASE, "polymer_p1", "kcat", None),
        (OLIGOMER_HYDROLASE, "oligomer_o1", "kcat", None),
    ]
    assert network["process_compatibility_ids"] == [f"{CHAIN_ID}__{DEPOLYMERASE}__polymer_p1__enzyme_network"]
    assert chain.summary()["enzyme_networks"] == [
        {
            "entry_substrate": "polymer_p1",
            "pools": ["polymer_p1", "oligomer_o1"],
            "product": "monomer_m1",
            "enzyme_classes": [DEPOLYMERASE, OLIGOMER_HYDROLASE],
        }
    ]
    # No single-class pair is generated: every class lists the network process type only.
    assert {item["record_id"] for item in chain.records["process_compatibility"]} == {
        f"{CHAIN_ID}__{DEPOLYMERASE}__polymer_p1__enzyme_network"
    }
    assert {tuple(item["compatible_processes"]) for item in chain.records["enzyme_classes"]} == {
        (USER_DATASET_NETWORK_PROCESS_TYPE,)
    }
    assert USER_DATASET_NETWORK_PROCESS_TYPE == ENZYME_NETWORK_PROCESS_TYPE == "enzyme_network"


def test_chain_template_composes_one_process_per_class(chain: UserDataset) -> None:
    (template,) = chain.records["case_templates"]
    assert template["process_type"] == ENZYME_NETWORK_PROCESS_TYPE
    assert template["state_roles"] == {
        "substrate": "polymer_p1_concentration",
        "intermediate_1": "oligomer_o1_concentration",
        "product": "monomer_m1_concentration",
        f"enzyme_{DEPOLYMERASE}": f"{DEPOLYMERASE}_concentration",
        f"enzyme_{OLIGOMER_HYDROLASE}": f"{OLIGOMER_HYDROLASE}_concentration",
    }
    metadata = template["process_state_metadata"]
    assert metadata["config_mode"] == "exploratory", "estimates keep the template exploratory"
    processes = {item["id"]: item for item in metadata["process_templates"]}
    assert set(processes) == {PROCESS_A, PROCESS_B}
    assert processes[PROCESS_A]["enzyme_class"] == f"{CHAIN_ID}__{DEPOLYMERASE}"
    assert processes[PROCESS_A]["state_roles"] == {
        "substrate": "substrate",
        "product": "intermediate_1",
        "enzyme": f"enzyme_{DEPOLYMERASE}",
    }
    assert processes[PROCESS_B]["state_roles"]["substrate"] == "intermediate_1"
    assert processes[PROCESS_B]["state_roles"]["product"] == "product"
    maps = {item["id"]: item for item in metadata["product_maps"]}
    assert [(item["reactants"], item["products"]) for item in maps.values()] == [
        ({"substrate": 1.0}, {"intermediate_1": 4.0}),
        ({"intermediate_1": 1.0}, {"product": 2.0}),
    ]
    # Closure weights from the stated yields: 8 P + 2 O + M is conserved.
    assert metadata["conservation"]["state_weights"] == {"product": 1.0, "intermediate_1": 2.0, "substrate": 8.0}
    assert template["initial_state_mapping"]["intermediate_1"] == {
        "value": 0.0,
        "units_from_role": "substrate_initial_concentration",
    }
    limitations = " ".join(template["limitations"])
    assert "act additively and independently" in limitations
    assert "No competition between classes for substrate binding or adsorption sites, no synergy" in limitations
    assert "No product inhibition is represented for Depolymerase-like class N1" in limitations
    assert "No product inhibition is represented for Oligomer hydrolase-like class N1" in limitations


def test_chain_records_are_selected_per_case_and_name_class_and_pool(chain: UserDataset) -> None:
    records = {item["record_id"]: item for item in chain.records["parameter_records"]}
    assert len(records) == 7
    km = records[f"{CHAIN_ID}__network__polymer_p1__strain_n1__c30_ph5__km__{OLIGOMER_HYDROLASE}__oligomer_o1"]
    assert km["parameter_symbol"] == f"{CHAIN_ID}__network__polymer_p1__km__{OLIGOMER_HYDROLASE}__oligomer_o1"
    assert km["process_type"] == ENZYME_NETWORK_PROCESS_TYPE
    assert km["enzyme_class"] is None, "one network serves every class acting on its entry"
    assert km["substrate_id"] == f"{CHAIN_ID}__polymer_p1"
    assert km["environment_id"] == f"{CHAIN_ID}__c30_ph5"
    assert km["value"] == {
        "kind": "exact",
        "units": "mM",
        "source": "Illustrative test note NW-1 p. 4",
        "confidence_level": "exploratory_assumption",
        "notes": km["value"]["notes"],
        "value": 1.0,
    }
    network = km["provenance"]["fungmod_user_dataset"]["enzyme_network"]
    assert network == {
        "entry_substrate": "polymer_p1",
        "role": f"km__{OLIGOMER_HYDROLASE}__oligomer_o1",
        "enzyme_class": f"{CHAIN_ID}__{OLIGOMER_HYDROLASE}",
        "pool": "oligomer_o1",
    }
    assert km["provenance"]["fungmod_user_dataset"]["row"] == 6
    initial = records[f"{CHAIN_ID}__network__polymer_p1__strain_n1__c30_ph5__substrate_initial_concentration"]
    assert initial["provenance"]["fungmod_user_dataset"]["enzyme_network"]["enzyme_class"] is None
    (compatibility,) = chain.records["process_compatibility"]
    assert set(compatibility["parameter_roles"]) == {
        "substrate_initial_concentration",
        f"km__{DEPOLYMERASE}__polymer_p1",
        f"kcat__{DEPOLYMERASE}__polymer_p1",
        f"enzyme_initial_concentration__{DEPOLYMERASE}",
        f"km__{OLIGOMER_HYDROLASE}__oligomer_o1",
        f"kcat__{OLIGOMER_HYDROLASE}__oligomer_o1",
        f"enzyme_initial_concentration__{OLIGOMER_HYDROLASE}",
    }


@pytest.mark.parametrize("fixture", sorted(EARLIER_RECORD_DIGESTS))
def test_datasets_without_a_network_generate_the_same_records(fixture: str) -> None:
    dataset = load_user_dataset(FIXTURES / fixture, registry=REGISTRY_INDEX)
    assert dataset.enzyme_networks == ()
    digest = hashlib.sha256(json.dumps(dataset.to_dict()["records"], sort_keys=True).encode("utf-8")).hexdigest()
    assert digest == EARLIER_RECORD_DIGESTS[fixture]


def test_the_network_assembler_is_registered_without_new_numerics() -> None:
    assembler = get_registry_process_assembler(ENZYME_NETWORK_PROCESS_TYPE)
    assert assembler is not None
    assert assembler.required_state_roles == ("substrate", "product")
    assert assembler.required_parameter_roles == ()


def test_the_composition_builder_binds_existing_modifiers_and_refuses_incomplete_ones(parallel: UserDataset) -> None:
    """The generalised composition builder binds the competitive law from roles and refuses what is missing."""

    registry = parallel.overlay(load_registry(REGISTRY_INDEX))
    compatibility = registry.process_compatibility[f"{PARALLEL_ID}__{CLEAVER_A}__ester_s2__enzyme_network"]
    template = registry.get_case_template(compatibility.case_template_id)
    case = {
        "fungus_id": f"{PARALLEL_ID}__strain_q2",
        "substrate_id": f"{PARALLEL_ID}__ester_s2",
        "environment_id": f"{PARALLEL_ID}__c25_ph7",
    }
    records = resolve_screen_role_records(registry=registry, compatibility=compatibility, mode="exploratory", **case)
    kwargs: dict[str, Any] = {
        "registry": registry,
        "compatibility": compatibility,
        "substrate": registry.get_substrate(case["substrate_id"]),
        "parameter_records": records,
        "output_directory": None,
        **case,
    }
    data = build_enzyme_network_config_data(case_template=template, **kwargs)
    assert data["case_template"]["process_enzyme_classes"] == {
        PROCESS_PA: f"{PARALLEL_ID}__{CLEAVER_A}",
        PROCESS_PB: f"{PARALLEL_ID}__{CLEAVER_B}",
    }
    assert [item["id"] for item in data["validators"]] == ["non_negative_network_states", "network_pool_balance"]
    (modifier,) = data["processes"][0]["modifiers"]
    assert modifier == {
        "type": "competitive_inhibition",
        "substrate_state": "ester_s2_concentration",
        "inhibitor_state": "acid_a2_concentration",
        "michaelis_constant": f"{PARALLEL_ID}__network__ester_s2__km__{CLEAVER_A}__ester_s2",
        "inhibition_constant": f"{PARALLEL_ID}__network__ester_s2__ki__{CLEAVER_A}__ester_s2",
        "primary_source": COMPETITIVE_INHIBITION_LAW_SOURCE,
        "maturity": COMPETITIVE_INHIBITION_LAW_MATURITY,
    }
    metadata = dict(template.process_state_metadata)

    def with_first_process(**changes: Any) -> Any:
        processes = [dict(item) for item in metadata["process_templates"]]
        processes[0] = {**processes[0], **changes}
        return replace(template, process_state_metadata={**metadata, "process_templates": processes})

    unsourced = [{**metadata["process_templates"][0]["modifiers"][0], "primary_source": " "}]
    with pytest.raises(RegistryCaseBuildError, match="requires canonical nonblank 'primary_source' text"):
        build_enzyme_network_config_data(case_template=with_first_process(modifiers=unsourced), **kwargs)
    with pytest.raises(RegistryCaseBuildError, match="enzyme_class must be canonical nonblank text"):
        build_enzyme_network_config_data(case_template=with_first_process(enzyme_class=""), **kwargs)
    with pytest.raises(RegistryCaseBuildError, match="must use process_type='culture_physiology'"):
        build_culture_physiology_config_data(case_template=template, **kwargs)


# ---------------------------------------------------------------------------
# Simulation and analytic checks


def test_chain_runs_and_conserves_the_stated_yields(chain_run: Any) -> None:
    series = _series(chain_run)
    environment = f"{CHAIN_ID}__c30_ph5"
    times, polymer, units = series[(environment, "substrate")]
    oligomer = series[(environment, "intermediate_1")][1]
    monomer = series[(environment, "product")][1]
    assert units == "millimolar"
    assert polymer[0] == CHAIN_S0 and oligomer[0] == 0.0 and monomer[0] == 0.0
    # Every pool is in the entry's units, and 8 P + 2 O + M = 8 S0 at every output time.
    total = CHAIN_Y1 * CHAIN_Y2 * polymer + CHAIN_Y2 * oligomer + monomer
    np.testing.assert_allclose(total, CHAIN_Y1 * CHAIN_Y2 * CHAIN_S0, rtol=1e-9)
    # The intermediate accumulates while the depolymerase outpaces the oligomer hydrolase, then declines.
    peak = int(np.argmax(oligomer))
    assert 0 < peak < len(times) - 1 and oligomer[-1] < oligomer[peak]
    assert monomer[-1] > 0.9 * CHAIN_Y1 * CHAIN_Y2 * CHAIN_S0
    metrics = {row["metric"]: row for row in chain_run.final_metrics()}
    # Threshold times and the depletion rate refer to the entry, product formation to the final product.
    assert float(metrics["final_substrate_remaining"]["value"]) == pytest.approx(polymer[-1], rel=1e-12)
    assert float(metrics["final_product_formed"]["value"]) == pytest.approx(monomer[-1], rel=1e-12)
    assert float(metrics["maximum_substrate_depletion_rate"]["value"]) == pytest.approx(
        CHAIN_VMAX_A * CHAIN_S0 / (CHAIN_KM_A + CHAIN_S0), rel=1e-9
    )
    thresholds = {row["metric"]: row for row in chain_run.threshold_times()}
    assert thresholds["time_to_50_percent_substrate_degradation"]["status"] == "computed"


def test_chain_process_rates_are_each_classs_own_law(chain_run: Any) -> None:
    series = _series(chain_run)
    environment = f"{CHAIN_ID}__c30_ph5"
    polymer = series[(environment, "substrate")][1]
    oligomer = series[(environment, "intermediate_1")][1]
    rate_a = series[(environment, f"process_rate.{PROCESS_A}")]
    rate_b = series[(environment, f"process_rate.{PROCESS_B}")]
    assert rate_a[2] == rate_b[2] == "millimolar / minute"
    np.testing.assert_allclose(rate_a[1], CHAIN_VMAX_A * polymer / (CHAIN_KM_A + polymer), rtol=1e-9, atol=1e-15)
    np.testing.assert_allclose(rate_b[1], CHAIN_VMAX_B * oligomer / (CHAIN_KM_B + oligomer), rtol=1e-9, atol=1e-15)
    # The state rates are the stoichiometric sums of the process rates.
    np.testing.assert_allclose(series[(environment, "degradation_rate")][1], rate_a[1], rtol=1e-9, atol=1e-15)
    np.testing.assert_allclose(
        series[(environment, "product_release_rate")][1], CHAIN_Y2 * rate_b[1], rtol=1e-9, atol=1e-15
    )


def test_chain_outputs_name_every_process_and_its_class(chain_run: Any) -> None:
    rows = chain_run.mechanism_summary()
    # The network row, then one process-law row per process (schema 2.2.0 mechanism kinds, no new kind).
    assert [row["mechanism_kind"] for row in rows] == ["process_law"] * 3
    assert [row["mechanism_id"] for row in rows] == [ENZYME_NETWORK_PROCESS_TYPE, PROCESS_A, PROCESS_B]
    assert "additively and independently" in rows[0]["limitations"]
    processes = {row["mechanism_id"]: row for row in rows[1:]}
    assert processes[PROCESS_A]["mechanism_family"] == "generic homogeneous Michaelis-Menten process"
    assert processes[PROCESS_A]["configured_by"] == f"{CHAIN_ID}__{DEPOLYMERASE}"
    assert processes[PROCESS_B]["configured_by"] == f"{CHAIN_ID}__{OLIGOMER_HYDROLASE}"
    assert "substrate:oligomer_o1_concentration" in processes[PROCESS_B]["state_variables"]
    assert f"km:{CHAIN_ID}__network__polymer_p1__km__{OLIGOMER_HYDROLASE}__oligomer_o1" in processes[PROCESS_B]["parameters"]
    limitations = [row["limitation"] for row in chain_run.limitations()]
    assert any("Parallel enzyme classes on one pool act additively and independently" in text for text in limitations)
    assert any(text.startswith("This is an enzyme network of well-mixed Michaelis-Menten") for text in limitations)
    conservation = {row["validator_id"]: row for row in chain_run.conservation_diagnostics()}
    assert float(conservation["network_pool_balance"]["initial_conserved_total"]) == pytest.approx(40.0)
    solver = chain_run.solver_diagnostics()
    assert solver, "the network runs on the compiled core with its diagnostics"


def test_parallel_classes_add_their_rates(parallel_run: Any) -> None:
    series = _series(parallel_run)
    environment = f"{PARALLEL_ID}__c25_ph7"
    substrate = series[(environment, "substrate")][1]
    product = series[(environment, "product")][1]
    rate_a = series[(environment, f"process_rate.{PROCESS_PA}")][1]
    rate_b = series[(environment, f"process_rate.{PROCESS_PB}")][1]
    np.testing.assert_allclose(series[(environment, "degradation_rate")][1], rate_a + rate_b, rtol=1e-9, atol=1e-15)
    np.testing.assert_allclose(substrate + product, 1000.0, rtol=1e-9)
    # The Vmax-form class has no enzyme state; the kcat-form class keeps its own.
    assert (environment, f"enzyme_{CLEAVER_A}") in series and (environment, f"enzyme_{CLEAVER_B}") not in series
    np.testing.assert_allclose(rate_b, PAR_VMAX_B * substrate / (PAR_KM_B + substrate), rtol=1e-9, atol=1e-15)


def test_competitive_inhibition_follows_the_modifier_formula(parallel_run: Any) -> None:
    series = _series(parallel_run)
    environment = f"{PARALLEL_ID}__c25_ph7"
    substrate = series[(environment, "substrate")][1]
    product = series[(environment, "product")][1]
    rate_a = series[(environment, f"process_rate.{PROCESS_PA}")][1]
    expected = PAR_VMAX_A * substrate / (PAR_KM_A * (1.0 + product / PAR_KI_A) + substrate)
    np.testing.assert_allclose(rate_a, expected, rtol=1e-9, atol=1e-15)
    # At time zero there is no product, so the inhibited rate is the plain Michaelis-Menten rate.
    assert rate_a[0] == pytest.approx(PAR_VMAX_A * 1000.0 / (PAR_KM_A + 1000.0), rel=1e-12)
    modifier = [row for row in parallel_run.mechanism_summary() if row["mechanism_id"] == "competitive_inhibition"]
    assert len(modifier) == 1
    assert modifier[0]["configured_by"] == PROCESS_PA
    assert modifier[0]["maturity"] == COMPETITIVE_INHIBITION_LAW_MATURITY
    assert modifier[0]["equation_or_law"] == "rate_multiplier = (K_m + S) / (K_m * (1 + I / K_i) + S)"
    assert json.loads(modifier[0]["provenance"])["primary_source"] == COMPETITIVE_INHIBITION_LAW_SOURCE
    limitations = " ".join(row["limitation"] for row in parallel_run.limitations())
    assert "Competitive product inhibition of Ester cleaver A-like class Q2 on Ester-like substrate S2 by acid_a2" in limitations
    assert "No product inhibition is represented for Ester cleaver B-like class Q2" in limitations
    assert "Processes in the Vmax form (cleaver_b_like on ester_s2)" in limitations


def test_a_stronger_inhibitor_slows_degradation_as_the_law_says(tmp_path: Path) -> None:
    """Without ki, with Ki 200 uM and with Ki 20 uM the substrate left at the end increases in that order."""

    finals = {}
    for label, edits in (
        ("none", {"kinetics.csv": _kinetics(PARALLEL, drop=[(CLEAVER_A, "ki")])}),
        ("ki_200", {}),
        ("ki_20", {"kinetics.csv": _kinetics(PARALLEL, change={(CLEAVER_A, "ki"): {"value": "20"}})}),
    ):
        dataset = _load(tmp_path / label, PARALLEL, edits)
        result = _simulate(tmp_path / f"{label}_run", dataset, fungus="strain_q2", substrate="ester_s2", environments=["c25_ph7"])
        series = _series(result)
        environment = f"{PARALLEL_ID}__c25_ph7"
        substrate = series[(environment, "substrate")][1]
        product = series[(environment, "product")][1]
        rate_a = series[(environment, f"process_rate.{PROCESS_PA}")][1]
        ki = {"none": math.inf, "ki_200": 200.0, "ki_20": 20.0}[label]
        expected = PAR_VMAX_A * substrate / (PAR_KM_A * (1.0 + product / ki) + substrate)
        np.testing.assert_allclose(rate_a, expected, rtol=1e-9, atol=1e-15)
        finals[label] = substrate[-1]
        if label == "none":
            (template,) = dataset.records["case_templates"]
            processes = template["process_state_metadata"]["process_templates"]
            assert all("modifiers" not in item for item in processes), "missing Ki is no inhibition term"
    assert finals["none"] < finals["ki_200"] < finals["ki_20"]


def test_parallel_first_order_regime_is_the_sum_of_the_first_order_constants(tmp_path: Path) -> None:
    """With S0 far below both Km, S(t) = S0 exp(-(Vmax_A/Km_A + Vmax_B/Km_B) t)."""

    s0 = 0.01  # uM, at most 2e-4 of either Km
    kinetics = _kinetics(
        PARALLEL,
        drop=[(CLEAVER_A, "ki")],
        change={
            (CLEAVER_A, "substrate_initial_concentration"): {"value": str(s0)},
            (CLEAVER_B, "substrate_initial_concentration"): {"value": str(s0)},
        },
    )
    dataset = _load(tmp_path, PARALLEL, {"kinetics.csv": kinetics})
    result = _simulate(tmp_path / "run", dataset, fungus="strain_q2", substrate="ester_s2", environments=["c25_ph7"])
    times, substrate, _units = _series(result)[(f"{PARALLEL_ID}__c25_ph7", "substrate")]
    rate = PAR_VMAX_A / PAR_KM_A + PAR_VMAX_B / PAR_KM_B  # 1/h
    window = times <= 4.0
    np.testing.assert_allclose(substrate[window], s0 * np.exp(-rate * times[window]), rtol=2e-3)


def test_a_one_class_network_equals_the_single_class_case(tmp_path: Path) -> None:
    """A network of one class runs the same Michaelis-Menten law as the single-class route: no new numerics."""

    source = FIXTURES / "esterase_case"
    manifest = _manifest(source, enzyme_network={"entry_substrates": ["p_nitrophenyl_butyrate"]})
    network = _load(tmp_path / "network", source, {"user_dataset.yml": manifest})
    assert network.enzyme_networks[0]["processes"][0]["enzyme_class"] == "carboxylesterase"
    kwargs = {"fungus": "strain_e1", "substrate": "p_nitrophenyl_butyrate", "environments": ["c37_ph7_5"]}
    single = _series(_simulate(tmp_path / "single_run", source, **kwargs))
    networked = _series(_simulate(tmp_path / "network_run", network, **kwargs))
    single_environment = "esterase_demo__c37_ph7_5"
    for role in ("substrate", "product"):
        times, expected, units = single[(single_environment, role)]
        other_times, actual, other_units = networked[(single_environment, role)]
        assert units == other_units
        np.testing.assert_allclose(other_times, times)
        np.testing.assert_allclose(actual, expected, rtol=1e-7, atol=1e-9 * 200.0)


def test_solid_classes_in_parallel_with_a_reactivity_factor(tmp_path: Path) -> None:
    """Two classes on one suspended solid (dry-mass basis): rates add, and one carries (S / S0)^n."""

    directory = tmp_path / "solid_network"
    directory.mkdir()
    files = {
        "user_dataset.yml": yaml.safe_dump(
            {
                "dataset_id": "solid_network",
                "contributor": "FungMod maintainers",
                "source": "Illustrative estimates for two user-defined classes on one user-defined solid",
                "simulation": {"duration": 48, "units": "hour", "points": 49},
                "enzyme_network": {"entry_substrates": ["solid_lot_l3"]},
            },
            sort_keys=False,
        ),
        "strains.csv": "strain_id,name,scientific_name,aliases\nstrain_l3,Illustrative solid-network strain L3,,\n",
        "enzyme_classes.csv": (
            "class_id,name,ec_number,target_bond_classes,compatible_substrate_classes,source\n"
            "solid_cleaver_c_like,Solid cleaver C-like class L3,,solid_bond_like,solid_like,Illustrative class\n"
            "solid_cleaver_d_like,Solid cleaver D-like class L3,,solid_bond_like,solid_like,Illustrative class\n"
        ),
        "enzymes.csv": (
            "strain_id,enzyme_class,evidence,source\n"
            "strain_l3,solid_cleaver_c_like,assumed activity (illustrative),Illustrative test note NW-3\n"
            "strain_l3,solid_cleaver_d_like,assumed activity (illustrative),Illustrative test note NW-3\n"
        ),
        "substrates.csv": (
            "substrate_id,registry_substrate,name,substrate_class,physical_state,bond_classes,amount_basis,product,"
            "product_yield,yield_basis,source\n"
            "solid_lot_l3,,Solid-like lot L3,solid_like,solid_polymer,solid_bond_like,dry_mass,soluble_mass_l3,1,g/g,"
            "Illustrative test note NW-3\n"
        ),
        "conditions.csv": "condition_id,temperature,temperature_units,ph,notes\nc35,35,degC,5.5,Illustrative\n",
        "kinetics.csv": (
            "strain_id,enzyme_class,substrate_id,condition_id,quantity,value,lower,upper,units,evidence_type,method,source\n"
            "strain_l3,solid_cleaver_c_like,solid_lot_l3,c35,km,10,,,g/L,estimate,illustrative estimate,NW-3\n"
            "strain_l3,solid_cleaver_c_like,solid_lot_l3,c35,kcat,0.5,,,g/(mg*h),estimate,illustrative estimate,NW-3\n"
            "strain_l3,solid_cleaver_c_like,solid_lot_l3,c35,enzyme_concentration,0.2,,,mg/L,estimate,illustrative "
            "estimate,NW-3\n"
            "strain_l3,solid_cleaver_c_like,solid_lot_l3,c35,substrate_initial_concentration,20,,,g/L,estimate,"
            "illustrative estimate,NW-3\n"
            "strain_l3,solid_cleaver_c_like,solid_lot_l3,c35,reactivity_exponent,1,,,dimensionless,estimate,"
            "illustrative estimate,NW-3\n"
            "strain_l3,solid_cleaver_d_like,solid_lot_l3,c35,km,5,,,g/L,estimate,illustrative estimate,NW-3\n"
            "strain_l3,solid_cleaver_d_like,solid_lot_l3,c35,vmax,0.2,,,g/L/h,estimate,illustrative estimate,NW-3\n"
        ),
    }
    for name, text in files.items():
        (directory / name).write_text(text, encoding="utf-8")
    dataset = load_user_dataset(directory, registry=REGISTRY_INDEX)
    (network,) = dataset.enzyme_networks
    assert [(item["enzyme_class"], item["rate_form"], item["reactivity_factor"]) for item in network["processes"]] == [
        ("solid_cleaver_c_like", "kcat", True),
        ("solid_cleaver_d_like", "Vmax", False),
    ]
    result = _simulate(tmp_path / "run", dataset, fungus="strain_l3", substrate="solid_lot_l3", environments=["c35"])
    series = _series(result)
    environment = "solid_network__c35"
    substrate, units = series[(environment, "substrate")][1], series[(environment, "substrate")][2]
    product = series[(environment, "product")][1]
    assert units == "gram / liter"
    rate_c = series[(environment, "process_rate.solid_network__solid_cleaver_c_like__solid_lot_l3__homogeneous_mm")][1]
    rate_d = series[(environment, "process_rate.solid_network__solid_cleaver_d_like__solid_lot_l3__homogeneous_mm")][1]
    np.testing.assert_allclose(rate_c, 0.1 * substrate / (10.0 + substrate) * (substrate / 20.0), rtol=1e-9, atol=1e-15)
    np.testing.assert_allclose(rate_d, 0.2 * substrate / (5.0 + substrate), rtol=1e-9, atol=1e-15)
    np.testing.assert_allclose(series[(environment, "degradation_rate")][1], rate_c + rate_d, rtol=1e-9, atol=1e-15)
    np.testing.assert_allclose(substrate + product, 20.0, rtol=1e-9)
    assert any("Conversion-dependent reactivity" in row["limitation"] for row in result.limitations())


def test_measured_values_make_the_network_scientific(tmp_path: Path) -> None:
    kinetics = (CHAIN / "kinetics.csv").read_text(encoding="utf-8").replace(
        ",estimate,illustrative estimate,", ",measured,illustrative measurement for the test,"
    )
    dataset = _load(tmp_path, CHAIN, {"kinetics.csv": kinetics})
    (template,) = dataset.records["case_templates"]
    assert template["process_state_metadata"]["config_mode"] == "scientific"
    study = virtual_experiment(
        fungi=["strain_n1"], substrates=["polymer_p1"], environments=["c30_ph5"], registry=REGISTRY_INDEX, user_data=dataset
    )
    (report,) = study.preflight(mode="scientific")
    assert report.status == "modelable", report.to_dict()
    study.simulate(mode="scientific", output_dir=tmp_path / "scientific", quicklook=False)
    manifest = json.loads((tmp_path / "scientific" / "output_manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_label"] == "scientific_exact_unvalidated"
    # One estimate anywhere in the network keeps it exploratory.
    weak = kinetics.replace(
        "km,1,,,mM,measured,illustrative measurement for the test,", "km,1,,,mM,estimate,illustrative estimate,"
    )
    weak_dataset = _load(tmp_path / "weak", CHAIN, {"kinetics.csv": weak})
    assert weak_dataset.records["case_templates"][0]["process_state_metadata"]["config_mode"] == "exploratory"


def test_the_fixtures_are_exploratory_only(tmp_path: Path) -> None:
    study = virtual_experiment(
        fungi=["strain_q2"], substrates=["ester_s2"], environments=["c25_ph7"], registry=REGISTRY_INDEX, user_data=PARALLEL
    )
    (report,) = study.preflight(mode="scientific")
    assert report.status == "underparameterized"
    with pytest.raises(VirtualExperimentError, match="Scientific simulation requires"):
        study.simulate(mode="scientific", output_dir=tmp_path / "scientific")


# ---------------------------------------------------------------------------
# Gaps


def test_a_class_without_kinetics_is_a_gap_that_blocks_the_network(tmp_path: Path) -> None:
    kinetics = _kinetics(CHAIN, drop=[(OLIGOMER_HYDROLASE, "kcat"), (OLIGOMER_HYDROLASE, "enzyme_concentration")])
    dataset = _load(tmp_path, CHAIN, {"kinetics.csv": kinetics})
    gaps = {
        item["record_id"]: item for item in dataset.records["parameter_records"] if item["maturity"] == USER_DATASET_MATURITY_GAP
    }
    assert set(gaps) == {
        f"{CHAIN_ID}__network__polymer_p1__strain_n1__c30_ph5__kcat__{OLIGOMER_HYDROLASE}__oligomer_o1__gap",
        f"{CHAIN_ID}__network__polymer_p1__strain_n1__c30_ph5__enzyme_initial_concentration__{OLIGOMER_HYDROLASE}__gap",
    }
    # The single-class route's request, naming the class and the pool it acts on; km alone starts no rate form.
    assert {item["provenance"]["measurement_request"] for item in gaps.values()} == {
        "Measure kcat and the enzyme concentration of Oligomer hydrolase-like class N1 from Illustrative network "
        "strain N1 on Oligomer-like pool O1 at 30 degC, pH 5.0, or Vmax (or a specific activity and enzyme loading)."
    }
    study = virtual_experiment(
        fungi=["strain_n1"], substrates=["polymer_p1"], environments=["c30_ph5"], registry=REGISTRY_INDEX, user_data=dataset
    )
    (report,) = study.preflight(mode="exploratory")
    assert report.status == "underparameterized", "a class the strain has is never silently left out"
    assert any("Oligomer hydrolase-like class N1" in text for text in report.suggested_experiments)


def test_a_condition_without_rows_is_a_gap_case_beside_a_runnable_one(tmp_path: Path) -> None:
    conditions = (CHAIN / "conditions.csv").read_text(encoding="utf-8") + "c40_ph5,40,degC,5.0,Not measured\n"
    dataset = _load(tmp_path, CHAIN, {"conditions.csv": conditions})
    gap = next(
        item
        for item in dataset.records["parameter_records"]
        if item["record_id"] == f"{CHAIN_ID}__network__polymer_p1__strain_n1__c40_ph5__substrate_initial_concentration__gap"
    )
    assert gap["provenance"]["measurement_request"].startswith(
        "Specify the initial Soluble polymer-like substrate P1 concentration of the enzyme network of Illustrative "
        "network strain N1 at 40 degC, pH 5.0"
    )
    result = _simulate(
        tmp_path / "run",
        dataset,
        fungus="strain_n1",
        substrate="polymer_p1",
        environments=["c30_ph5", "c40_ph5"],
        blocked="report",
    )
    assert result.partial_run
    (blocked,) = result.blocked_cases()
    assert blocked["environment_id"] == f"{CHAIN_ID}__c40_ph5"
    assert any("does not reuse kinetics" in text for text in blocked["suggested_experiments"])


def test_a_ki_stated_for_one_condition_is_a_gap_at_another(tmp_path: Path) -> None:
    rows = [row for row in _rows(PARALLEL, "kinetics.csv") if row["quantity"] != "ki"]
    other = [{**row, "condition_id": "c30_ph7"} for row in rows]
    kinetics = _csv_text([*_rows(PARALLEL, "kinetics.csv"), *other], KINETICS_HEADER)
    conditions = (PARALLEL / "conditions.csv").read_text(encoding="utf-8") + "c30_ph7,30,degC,7.0,Illustrative\n"
    dataset = _load(tmp_path, PARALLEL, {"kinetics.csv": kinetics, "conditions.csv": conditions})
    gap = next(
        item
        for item in dataset.records["parameter_records"]
        if item["record_id"] == f"{PARALLEL_ID}__network__ester_s2__strain_q2__c30_ph7__ki__{CLEAVER_A}__ester_s2__gap"
    )
    assert gap["provenance"]["measurement_request"] == (
        "Measure the competitive inhibition constant Ki of Ester cleaver A-like class Q2 from Illustrative "
        "parallel-network strain Q2 on Ester-like substrate S2 by acid_a2 at 30 degC, pH 7.0 (amount of the "
        "inhibiting product per volume, for example mM), for example from initial rates at several Ester-like "
        "substrate S2 and acid_a2 concentrations."
    )


# ---------------------------------------------------------------------------
# Refusals


def test_a_cycle_of_products_is_refused(tmp_path: Path) -> None:
    substrates = (CHAIN / "substrates.csv").read_text(encoding="utf-8").replace(
        "oligomer_like,dissolved,inner_glycosidic_like,monomer_m1,2,", "oligomer_like,dissolved,inner_glycosidic_like,polymer_p1,0.25,"
    )
    issues = _issues(tmp_path, CHAIN, {"substrates.csv": substrates})
    assert _has_issue(issues, "substrates.csv", 3, "product", "the links form a cycle")
    assert _has_issue(issues, "substrates.csv", 3, "product", "polymer_p1 -> oligomer_o1 -> polymer_p1")


def test_an_ambiguous_product_is_refused(tmp_path: Path) -> None:
    substrates = (CHAIN / "substrates.csv").read_text(encoding="utf-8").replace(
        "inner_glycosidic_like,monomer_m1,2,", "inner_glycosidic_like,cellobiose,2,"
    ) + "cb_pool,cellobiose,,,,,beta_D_glucose,2,mol/mol,Illustrative registry reference\n"
    issues = _issues(tmp_path, CHAIN, {"substrates.csv": substrates})
    assert _has_issue(
        issues, "substrates.csv", 3, "product", "is the registry substrate of substrates.csv row 4 (substrate_id 'cb_pool')"
    )


def test_a_link_across_amount_bases_is_refused(tmp_path: Path) -> None:
    """Without a unit-bearing yield (NETWORK-002) a solid still links to a dissolved pool on no basis; never the reverse."""

    header = "substrate_id,registry_substrate,name,substrate_class,physical_state,bond_classes,amount_basis,product,product_yield,yield_basis,source\n"
    substrates = header + (
        "polymer_p1,,Soluble polymer-like substrate P1,soluble_polymer_like,solid_polymer,inner_glycosidic_like,dry_mass,"
        "oligomer_o1,1.1,g/g,Illustrative\n"
        "oligomer_o1,,Oligomer-like pool O1,oligomer_like,dissolved,inner_glycosidic_like,,monomer_m1,2,mol/mol,Illustrative\n"
    )
    issues = _issues(tmp_path, CHAIN, {"substrates.csv": substrates})
    assert _has_issue(issues, "substrates.csv", 2, "yield_basis", "needs a unit-bearing yield that converts the dry mass")
    assert _has_issue(issues, "substrates.csv", 2, "yield_basis", "FungMod never derives it from a molar mass")
    reverse = header + (
        "polymer_p1,,Soluble polymer-like substrate P1,soluble_polymer_like,dissolved,inner_glycosidic_like,,"
        "oligomer_o1,4,mol/mol,Illustrative\n"
        "oligomer_o1,,Oligomer-like pool O1,oligomer_like,solid_polymer,inner_glycosidic_like,dry_mass,monomer_m1,2,g/g,"
        "Illustrative\n"
    )
    issues = _issues(tmp_path / "reverse", CHAIN, {"substrates.csv": reverse})
    assert _has_issue(issues, "substrates.csv", 2, "product", "forming a solid from a dissolved pool is not supported")


def test_a_class_on_two_pools_of_one_network_is_refused(tmp_path: Path) -> None:
    classes = (CHAIN / "enzyme_classes.csv").read_text(encoding="utf-8").replace(
        "inner_glycosidic_like,oligomer_like,", "inner_glycosidic_like,oligomer_like;soluble_polymer_like,"
    )
    issues = _issues(tmp_path, CHAIN, {"enzyme_classes.csv": classes})
    assert _has_issue(issues, "enzymes.csv", 3, "enzyme_class", "competes for its active site")


def test_strains_with_different_member_classes_are_refused(tmp_path: Path) -> None:
    strains = (CHAIN / "strains.csv").read_text(encoding="utf-8") + "strain_n2,Illustrative network strain N2,,\n"
    enzymes = (CHAIN / "enzymes.csv").read_text(encoding="utf-8") + "strain_n2,depolymerase_like,assumed,Note\n"
    issues = _issues(tmp_path, CHAIN, {"strains.csv": strains, "enzymes.csv": enzymes})
    assert _has_issue(issues, "strains.csv", 3, "strain_id", "but not oligomer_hydrolase_like")


def test_inputs_of_an_intermediate_pool_are_refused(tmp_path: Path) -> None:
    initial = _row(CHAIN, OLIGOMER_HYDROLASE, "km", quantity="substrate_initial_concentration", value="3")
    issues = _issues(tmp_path, CHAIN, {"kinetics.csv": _kinetics(CHAIN, add=[initial])})
    assert _has_issue(issues, "kinetics.csv", 9, "quantity", "is an intermediate pool of an enzyme network")


def test_an_intermediate_listed_as_an_entry_starts_its_own_network(tmp_path: Path) -> None:
    initial = _row(CHAIN, OLIGOMER_HYDROLASE, "km", quantity="substrate_initial_concentration", value="3")
    manifest = _manifest(CHAIN, enzyme_network={"entry_substrates": ["polymer_p1", "oligomer_o1"]})
    dataset = _load(tmp_path, CHAIN, {"kinetics.csv": _kinetics(CHAIN, add=[initial]), "user_dataset.yml": manifest})
    assert [item["pools"] for item in dataset.enzyme_networks] == [["polymer_p1", "oligomer_o1"], ["oligomer_o1"]]
    result = _simulate(tmp_path / "run", dataset, fungus="strain_n1", substrate="oligomer_o1", environments=["c30_ph5"])
    series = _series(result)
    environment = f"{CHAIN_ID}__c30_ph5"
    assert series[(environment, "substrate")][1][0] == 3.0
    assert {key for _env, key in series if key.startswith("process_rate.")} == {f"process_rate.{PROCESS_B}"}


def test_disagreeing_initial_concentrations_of_an_entry_are_refused(tmp_path: Path) -> None:
    kinetics = _kinetics(PARALLEL, change={(CLEAVER_B, "substrate_initial_concentration"): {"value": "900"}})
    issues = _issues(tmp_path, PARALLEL, {"kinetics.csv": kinetics})
    line = _line(PARALLEL, CLEAVER_B, "substrate_initial_concentration")
    assert _has_issue(issues, "kinetics.csv", line, "value", "give different initial concentrations of 'ester_s2'")


@pytest.mark.parametrize(
    ("cells", "column", "message"),
    [
        ({"inhibitor": "ester_s2"}, "inhibitor", "is not a pool the enzyme network releases downstream of 'ester_s2'"),
        ({"inhibitor": ""}, "inhibitor", "ki rows must name their inhibitor"),
        ({"units": "g/L"}, "units", "ki units 'g/L' are a mass concentration"),
        ({"units": "1/min"}, "units", "must be an amount of the inhibiting product per volume"),
        ({"value": "0"}, "value", "ki must be positive"),
    ],
)
def test_malformed_ki_rows_are_refused(tmp_path: Path, cells: Mapping[str, str], column: str, message: str) -> None:
    issues = _issues(tmp_path, PARALLEL, {"kinetics.csv": _kinetics(PARALLEL, change={(CLEAVER_A, "ki"): cells})})
    assert _has_issue(issues, "kinetics.csv", _line(PARALLEL, CLEAVER_A, "ki"), column, message), issues


def test_an_inhibitor_on_another_row_is_refused(tmp_path: Path) -> None:
    kinetics = _kinetics(PARALLEL, change={(CLEAVER_A, "km"): {"inhibitor": "acid_a2"}})
    issues = _issues(tmp_path, PARALLEL, {"kinetics.csv": kinetics})
    assert _has_issue(issues, "kinetics.csv", _line(PARALLEL, CLEAVER_A, "km"), "inhibitor", "applies only to ki rows")


def test_two_inhibitors_of_one_process_are_refused(tmp_path: Path) -> None:
    rows = _rows(CHAIN, "kinetics.csv")
    other = [{**row, "condition_id": "c40_ph5"} for row in rows]
    ki = {
        **{column: "" for column in KINETICS_HEADER},
        "strain_id": "strain_n1",
        "enzyme_class": DEPOLYMERASE,
        "substrate_id": "polymer_p1",
        "quantity": "ki",
        "value": "1",
        "units": "mM",
        "evidence_type": "estimate",
        "source": "NW-1",
    }
    kinetics = _csv_text(
        [*rows, *other, {**ki, "condition_id": "c30_ph5", "inhibitor": "oligomer_o1"}, {**ki, "condition_id": "c40_ph5", "inhibitor": "monomer_m1"}],
        KINETICS_HEADER,
    )
    conditions = (CHAIN / "conditions.csv").read_text(encoding="utf-8") + "c40_ph5,40,degC,5.0,Illustrative\n"
    issues = _issues(tmp_path, CHAIN, {"kinetics.csv": kinetics, "conditions.csv": conditions})
    assert _has_issue(issues, "kinetics.csv", 17, "inhibitor", "One process takes one competitive inhibitor")


def test_ki_outside_a_network_and_on_a_solid_is_refused(tmp_path: Path) -> None:
    source = FIXTURES / "esterase_case"
    rows = _rows(source, "kinetics.csv")
    header = (*rows[0].keys(), "inhibitor")
    ki = {**rows[0], "quantity": "ki", "value": "100", "inhibitor": "p_nitrophenol"}
    issues = _issues(tmp_path / "single", source, {"kinetics.csv": _csv_text([*rows, ki], header)})
    assert _has_issue(issues, "kinetics.csv", 6, "quantity", "supports in network datasets only")
    solid = FIXTURES / "solid_case"
    solid_rows = _rows(solid, "kinetics.csv")
    solid_ki = {**solid_rows[0], "quantity": "ki", "value": "1", "units": "g/L", "inhibitor": "solubilized_substrate_mass"}
    solid_issues = _issues(
        tmp_path / "solid", solid, {"kinetics.csv": _csv_text([*solid_rows, solid_ki], (*solid_rows[0].keys(), "inhibitor"))}
    )
    assert _has_issue(solid_issues, "kinetics.csv", len(solid_rows) + 2, "quantity", "ki is refused on a solid substrate")


def test_the_ph_ionization_form_is_refused_in_a_network(tmp_path: Path) -> None:
    source = FIXTURES / "bgl1a_ph_ionization"
    manifest = _manifest(source, enzyme_network={"entry_substrates": ["cellobiose"]})
    issues = _issues(tmp_path, source, {"user_dataset.yml": manifest})
    assert any("runs the pH-ionization form on 'cellobiose'" in issue["message"] for issue in issues)


def test_tables_not_combined_with_networks_are_refused(tmp_path: Path) -> None:
    source = FIXTURES / "oxidase_case"
    substrate = _rows(source, "substrates.csv")[0]["substrate_id"]
    manifest = _manifest(source, enzyme_network={"entry_substrates": [substrate]})
    issues = _issues(tmp_path, source, {"user_dataset.yml": manifest})
    assert _has_issue(issues, "responses.csv", None, None, "responses.csv is not combined with enzyme_network")
    culture = FIXTURES / "culture_estimates"
    culture_issues = _issues(
        tmp_path / "culture", culture, {"user_dataset.yml": _manifest(culture, enzyme_network={"entry_substrates": ["xylan_lot_x1"]})}
    )
    assert _has_issue(culture_issues, "culture.csv", None, None, "culture.csv is not combined with enzyme_network")


@pytest.mark.parametrize(
    ("block", "column", "message"),
    [
        (True, "enzyme_network", "enzyme_network must be a mapping with entry_substrates"),
        ({"entry_substrates": []}, "enzyme_network.entry_substrates", "must be a nonempty list"),
        ({"entry_substrates": ["polymer_p1", "polymer_p1"]}, "enzyme_network.entry_substrates", "more than once"),
        ({"entry_substrates": ["polymer_p1"], "classes": ["x"]}, "enzyme_network", "Unsupported enzyme_network field"),
        ({"entry_substrates": ["nope"]}, "enzyme_network.entry_substrates", "Entry substrate 'nope' is not a substrate_id"),
    ],
)
def test_malformed_network_blocks_are_refused(tmp_path: Path, block: Any, column: str, message: str) -> None:
    issues = _issues(tmp_path, CHAIN, {"user_dataset.yml": _manifest(CHAIN, enzyme_network=block)})
    assert _has_issue(issues, "user_dataset.yml", None, column, message), issues


def test_a_substrate_in_no_network_is_refused(tmp_path: Path) -> None:
    manifest = _manifest(CHAIN, enzyme_network={"entry_substrates": ["oligomer_o1"]})
    initial = _row(CHAIN, OLIGOMER_HYDROLASE, "km", quantity="substrate_initial_concentration", value="3")
    issues = _issues(tmp_path, CHAIN, {"user_dataset.yml": manifest, "kinetics.csv": _kinetics(CHAIN, add=[initial])})
    assert _has_issue(issues, "substrates.csv", 2, "substrate_id", "is part of no enzyme network")


def test_assembly_refuses_a_network_dataset() -> None:
    with pytest.raises(UserTablesAssemblyError, match="declares enzyme networks"):
        assemble_user_tables(
            dataset_id="drafted_network",
            fungus="strain_n1",
            substrates=["polymer_p1"],
            conditions=[{"temperature": 30, "temperature_units": "degC", "ph": 5}],
            user_data=CHAIN,
        )


# ---------------------------------------------------------------------------
# Command line


def test_check_data_lists_the_network(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = _cli(capsys, "check-data", PARALLEL, "--registry", REGISTRY_INDEX)
    assert code == EXIT_OK, err
    assert "Enzyme networks (user_dataset.yml enzyme_network" in out
    assert "from ester_s2: ester_s2 -> acid_a2 (1 mol/mol); strains strain_q2" in out
    assert "cleaver_a_like  ester_s2  kcat       acid_a2" in out


def test_check_data_reports_network_refusals(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    kinetics = _kinetics(PARALLEL, change={(CLEAVER_A, "ki"): {"inhibitor": "ester_s2"}})
    dataset = _copy_fixture(tmp_path, PARALLEL, edits={"kinetics.csv": kinetics})
    code, _out, err = _cli(capsys, "check-data", dataset, "--registry", REGISTRY_INDEX)
    assert code == EXIT_USAGE
    assert f"kinetics.csv:{_line(PARALLEL, CLEAVER_A, 'ki')}:inhibitor: inhibitor 'ester_s2' is not a pool" in err


def test_run_simulates_the_network_from_the_command_line(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    code, out, err = _cli(
        capsys,
        "run",
        "--user-data",
        CHAIN,
        "--fungus",
        "strain_n1",
        "--substrate",
        "polymer_p1",
        "--environment",
        "c30_ph5",
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
    with (tmp_path / "run" / "mechanism_summary.csv").open(encoding="utf-8", newline="") as handle:
        kinds = [row["mechanism_kind"] for row in csv.DictReader(handle)]
    assert kinds == ["process_law", "process_law", "process_law"]


def test_run_reports_a_blocked_network_case(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    conditions = (CHAIN / "conditions.csv").read_text(encoding="utf-8") + "c40_ph5,40,degC,5.0,Not measured\n"
    dataset = _copy_fixture(tmp_path, CHAIN, edits={"conditions.csv": conditions})
    code, out, err = _cli(
        capsys,
        "run",
        "--user-data",
        dataset,
        "--fungus",
        "strain_n1",
        "--substrate",
        "polymer_p1",
        "--condition",
        "c30_ph5",
        "--condition",
        "c40_ph5",
        "--runnable-only",
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
    assert code == EXIT_PARTIAL, err
    assert "not simulated" in out
