"""Enzyme-network links across amount bases through a stated, unit-bearing yield (NETWORK-002).

A solid pool (dry mass per volume) releases a dissolved pool (amount per
volume), or a molar final product, only through a yield the user states in
``substrates.csv`` (``yield_basis`` an amount of product per dry mass, for
example ``mmol/g``, with its own ``yield_evidence_type``). The yield becomes a
parameter record bound to the release coefficient; the homogeneous
Michaelis-Menten process forms that product in its own units through the
coefficient's units, which the compiled core converts once at build time; the
closure ledger weighs the solid through the yield.

``tests/fixtures/user_data/network_solid_chain`` is a user-defined strain whose
two user-defined classes degrade a cellulose-like solid through a dissolved
disaccharide-like pool to a monomer-like product (g/L -> mmol/L, competitive
inhibition by the product). ``tests/fixtures/user_data/network_solid_parallel``
is the materially different case: two user-defined classes in parallel on a
chitin-like solid (kcat and Vmax forms) releasing the final product in umol/L.
Every value of both is an illustrative estimate; other datasets are derived from
them in temporary directories to test modes, analytic limits and refusals only.
The first tests exercise the generic core with artificial states only.
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
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
import yaml

from fungal_model import UserDataError, UserDataset, load_user_dataset, virtual_experiment
from fungal_model.api import VirtualExperimentError
from fungal_model.api.result_tables import _final_product_yield
from fungal_model.api.user_data import USER_DATASET_MATURITY_ESTIMATE
from fungal_model.cli import EXIT_OK, EXIT_USAGE, main
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_
from fungal_model.core.validators import conserved_weight
from fungal_model.io.model_config import load_model_config
from fungal_model.io.registries import load_stoichiometric_product_map
from fungal_model.processes import (
    HomogeneousMichaelisMentenProcess,
    ModelBuilder,
    ProcessRegistry,
    ProductReleaseMap,
)
from fungal_model.processes.factories import (
    HomogeneousMichaelisMentenFactory,
    PHIonizationMichaelisMentenFactory,
    ProcessBuildContext,
    SubstrateTransglycosylationFactory,
    SurfaceCatalysisFactory,
)
from fungal_model.processes.transglycosylation import TRANSGLYCOSYLATION_MATURITY
from fungal_model.registry import load_registry
from fungal_model.registry.loaders import load_registry_record_mapping
from fungal_model.registry.records import PARAMETER_ALLOWED_USE_EXPLORATORY, CaseTemplateRecord
from fungal_model.screening import RegistryCaseBuildError
from fungal_model.screening.case_builder import (
    build_registry_process_config_data,
    get_registry_process_assembler,
    select_registry_case_compatibility,
)
from fungal_model.screening.ensemble import _sample_role_records, resolve_screen_role_records
from fungal_model.screening.enzyme_network import build_enzyme_network_config_data
from fungal_model.screening.modelability import assess_modelability
from fungal_model.solvers import ProcessODESolver, RunRequest
from fungal_model.workflows.configured_inputs import ConfiguredInputLoader
from fungal_model.workflows.configured_processes import ConfiguredProcessAssembler

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"
FIXTURES = ROOT / "tests" / "fixtures" / "user_data"
CHAIN = FIXTURES / "network_solid_chain"
PARALLEL = FIXTURES / "network_solid_parallel"

CHAIN_ID = "network_solid_chain"
CUTTER = "solid_cutter_like"
HYDROLASE = "dimer_hydrolase_like"
PROCESS_A = f"{CHAIN_ID}__{CUTTER}__solid_c3__homogeneous_mm"
PROCESS_B = f"{CHAIN_ID}__{HYDROLASE}__dimer_d3__homogeneous_mm"
CHAIN_ENVIRONMENT = f"{CHAIN_ID}__c45_ph5"
PARALLEL_ID = "network_solid_parallel"
ENDO = "endo_cutter_like"
EXO = "exo_cutter_like"
PROCESS_PA = f"{PARALLEL_ID}__{ENDO}__solid_k4__homogeneous_mm"
PROCESS_PB = f"{PARALLEL_ID}__{EXO}__solid_k4__homogeneous_mm"
PARALLEL_ENVIRONMENT = f"{PARALLEL_ID}__c37_ph6"

# The fixtures' constants in the units the analytic checks use (every one an illustrative estimate).
CHAIN_S0, CHAIN_KM_A, CHAIN_VMAX_A = 10.0, 8.0, 0.02 * 20.0  # g/L, g/L, g/L/h (kcat 0.02 g/(mg h) x E 20 mg/L)
CHAIN_YIELD = 3.0838  # mmol/g, the stated unit-bearing yield of the solid
CHAIN_Y2 = 2.0  # mol/mol
CHAIN_KM_B, CHAIN_VMAX_B, CHAIN_KI_B = 1.2, 50.0 * 0.00002 * 3600.0, 3.0  # mM, mM/h (kcat 50 1/s x E 0.00002 mM), mM
PAR_S0, PAR_YIELD = 2.0, 2460.6  # g/L, umol/g
PAR_KM_A, PAR_VMAX_A = 20.0, 0.004 * 25.0  # g/L, g/L/h (kcat 0.004 g/(mg h) x E 25 mg/L)
PAR_KM_B, PAR_VMAX_B = 40.0, 0.05  # g/L, g/L/h

SUBSTRATES_HEADER = (
    "substrate_id",
    "registry_substrate",
    "name",
    "substrate_class",
    "physical_state",
    "bond_classes",
    "amount_basis",
    "product",
    "product_yield",
    "yield_basis",
    "source",
    "yield_evidence_type",
    "yield_method",
)

# SHA-256 of json.dumps(dataset.to_dict()["records"], sort_keys=True) of every earlier fixture, computed with the
# base commit of NETWORK-002 (56c8df4): a dataset without a unit-bearing yield generates the same records.
EARLIER_RECORD_DIGESTS = {
    "bgl1a_ph_ionization": "5a5c837fde83d33c1b01fdfd88499eddd4112fbc8a4c3097e6efcaa246af60f1",
    "culture_estimates": "4cc4a3de85c4c74c83abf95d7f1bd9cbe72916db52d6800cdffadd0a094743f0",
    "culture_reentry": "013ebc0dd3decea7b8952e54636b48977e1767c9b1ef732cfed3b1fc48d2c698",
    "esterase_case": "4f92a532f98356be6ac680b4652ac411a975e3c772dd2f0348c590a207ef3464",
    "genome_case": "f13786fee336d8c58e9dc5d052e1b138158ade98d268cd6b0788ed6b5a8b118e",
    "literature_reentry": "37baa76aaefcbe1d27746720218eafd7712a47ca8c0927245eea597895fce6e1",
    "network_chain": "3b773a4f56a973c4db62a074fa705ae6ffdd1135f9e8866e065161c9e35560f7",
    "network_parallel": "b3b3d6684948bb153bd1c98337d0890ffafb40c3e862774a63111cde03de241d",
    "oxidase_case": "eb82f225a0cd09115afb44b67e0bb2496e7bf11ee7f0960624759b1970f7e322",
    "solid_case": "9b1eecb8cd6820ec7c1c27f17bff9d4820e5679c0350a77c3caba1ced2215e83",
    "uniprot_case": "8ec0dfbf50881d866a00b0392149a1dd60cd8260ac3acdd771e5b7d71a5b6532",
}
# SHA-256 of yaml.safe_dump(config data, sort_keys=False) of every assembled case (fungus|substrate|environment|mode)
# of the shipped registry and of every earlier fixture, built as the screen builds a sample (ranged records taken at
# their lower bounds, so no random stream is involved) with output directory "<OUTPUT_ROOT>", computed with the same
# base commit: the generalised core and composition builder assemble every existing case byte-identically.
EARLIER_CONFIG_DIGESTS: dict[str, dict[str, str]] = {
    "bgl1a_ph_ionization": {
        "bgl1a_ph_reentry__bgl1a_source|cellobiose|bgl1a_ph_reentry__c30_ph5|exploratory": (
            "9d3542a5760fac70215586137b59d4ce95c2e6f4c3d5898700e7e2f0cf3502ed"
        ),
        "bgl1a_ph_reentry__bgl1a_source|cellobiose|bgl1a_ph_reentry__c30_ph5|scientific": (
            "1524835a1e88c67dc773e4181b1282652e0e7a5ae9aaf4fd765e19767be1e943"
        ),
    },
    "culture_estimates": {
        "culture_estimates__strain_x1|culture_estimates__xylan_lot_x1|culture_estimates__c25|exploratory": (
            "416c9446efde1a7e180ecdaa9fa785cfa74961a436f8d9742bf3146acf4c84f4"
        ),
    },
    "culture_reentry": {
        "culture_reentry__strain_h1|culture_reentry__particulate_lot_h1|culture_reentry__load_10|exploratory": (
            "fac77d2babf2834a38bc172cccbecbbb780e04e4b951c292ae3d9a3998f2aac8"
        ),
        "culture_reentry__strain_h1|culture_reentry__particulate_lot_h1|culture_reentry__load_20|exploratory": (
            "eb1747878afc12fb6c963664fe3880033578c50ea04314b3843f434f44dcfdd4"
        ),
        "culture_reentry__strain_h1|culture_reentry__particulate_lot_h1|culture_reentry__load_30|exploratory": (
            "3633da1c5ed41d65c55b9a0ee5c62ec7ca0d91848be9d9bbbc7b7cc24fbbb8d7"
        ),
    },
    "esterase_case": {
        "esterase_demo__strain_e1|esterase_demo__p_nitrophenyl_butyrate|esterase_demo__c37_ph7_5|exploratory": (
            "6e74d3672b607518adeca589a0a21a007b6c1a1e35a421c914176a88378d1df0"
        ),
    },
    "literature_reentry": {
        "reaction_618_reentry__os3bglu6_source|cellobiose|reaction_618_reentry__c30_ph5|exploratory": (
            "c06d5a75ff9e12d392ebc9ee3cf1cc0cb6f3919e0b456c5d21b94a541e1a2026"
        ),
        "reaction_618_reentry__os3bglu6_source|cellobiose|reaction_618_reentry__c30_ph5|scientific": (
            "4ed3d04a9f91810c8ef628cd42b89e2d442afc79a45f876ea6e78ba34096ed71"
        ),
    },
    "network_chain": {
        "network_chain__strain_n1|network_chain__polymer_p1|network_chain__c30_ph5|exploratory": (
            "4b9eb683318ff017beac5f8b2a6ad22fb908f16f30e47dc54008c1c6f4f65b95"
        ),
    },
    "network_parallel": {
        "network_parallel__strain_q2|network_parallel__ester_s2|network_parallel__c25_ph7|exploratory": (
            "83cc0c26b191593cd4aefc53d7e3d0acf9b8e2f0490f2156f04f67a0c27f3c78"
        ),
    },
    "oxidase_case": {
        "oxidase_demo__strain_l1|oxidase_demo__syringaldazine_like|oxidase_demo__c50_ph5|exploratory": (
            "5437dcb9e87762e2059ed56d8626a3c01d65852c0728ce1b2f373af809c93c0d"
        ),
    },
    "registry": {
        "generic_cellulase_source|cellulose_film_generic|bio001_cellulose_surface_pilot_environment|exploratory": (
            "cb118564fa4a1972f530541809be584ebe2f7308938a931f30137f235cdf0186"
        ),
        "generic_cellulase_source|cellulose_film_generic|sabiork_reaction_618_selected_conditions|exploratory": (
            "84883c4d4d75d168209038c318de3d58dfb4c3d636f926c637cbfbe14414dca0"
        ),
        "phanerochaete_chrysosporium_k3|cellobiose|bio001_cellulose_surface_pilot_environment|exploratory": (
            "698329f9d0d13066eaec93549ceb1aa6f88e22f9a8f5a9acb9a351e1d3ba2da9"
        ),
        "phanerochaete_chrysosporium_k3|cellobiose|gelain_2020_cellulose_batch_10gl|exploratory": (
            "e30cfed526825f5fb8f5ca679e6ab32c386ff83e6b7dd64369043292487126b0"
        ),
        "phanerochaete_chrysosporium_k3|cellobiose|gelain_2020_cellulose_batch_20gl|exploratory": (
            "d0f53c8c4e453f09bc7e19a901b9704978467a9bd6dc1501828022a66feed280"
        ),
        "phanerochaete_chrysosporium_k3|cellobiose|gelain_2020_cellulose_batch_30gl|exploratory": (
            "46504c4b359bd7fb548a44631194df3f5e53e08e75dc13340d2833243fcbf62e"
        ),
        "phanerochaete_chrysosporium_k3|cellobiose|sabiork_reaction_618_selected_conditions|exploratory": (
            "33ba2e79b600a2e3072843df56d2faa37d0c166bbbf33237050f48209007d679"
        ),
        "phanerochaete_chrysosporium_k3|cellobiose|tsukada_2008_bgl1a_assay_30c_ph4|exploratory": (
            "a22594935ca0e86379d2d2b253934082567325e5d0b41e75119f3ba208eb707b"
        ),
        "phanerochaete_chrysosporium_k3|cellobiose|tsukada_2008_bgl1a_assay_30c_ph5|exploratory": (
            "3f60e221716ed29213f3de5a0642bffe3acca5f3d7cb18d13be9c5b4cd051f19"
        ),
        "phanerochaete_chrysosporium_k3|cellobiose|tsukada_2008_bgl1a_assay_30c_ph6|exploratory": (
            "3ebbce3dc987d84419d0538af0cd54ad2b8f2c77bab5f676cc305fa1c228e64a"
        ),
        "phanerochaete_chrysosporium_k3|cellobiose|tsukada_2008_bgl1a_assay_30c_ph7|exploratory": (
            "1e7a24ee6ee93029a05f8c380480a22dec70fdb02be7c8eb6e55e98330e2ae2c"
        ),
        "phanerochaete_chrysosporium_k3|cellobiose|tsukada_2008_bgl1a_assay_30c_ph8|exploratory": (
            "ade0fdf0c76e1d6d1f5a438abaf27b3b24ca4c5173cf0988fda98dd51c2e6214"
        ),
        "sabiork_beta_glucosidase_source|cellobiose|sabiork_reaction_618_selected_conditions|exploratory": (
            "2ea0232fde2312438732a20dfa169f3b60bc06c9f2055586559e1f5cfd5de421"
        ),
        "trichoderma_harzianum_p49p11|cellulose_celufloc_200|gelain_2020_cellulose_batch_10gl|exploratory": (
            "2bb0cb46a5ce0499da5778fc33ea686c7299a4125062a6acaf31014e1b434046"
        ),
        "trichoderma_harzianum_p49p11|cellulose_celufloc_200|gelain_2020_cellulose_batch_10gl|scientific": (
            "d8c1d6f644281b5bb213f094fb216b1648bcaa68f508bb43cada80f788101cb8"
        ),
        "trichoderma_harzianum_p49p11|cellulose_celufloc_200|gelain_2020_cellulose_batch_20gl|exploratory": (
            "84601f54e45c74b6473730eedda74b69a54e3b981b2f3f06184171131a7f56df"
        ),
        "trichoderma_harzianum_p49p11|cellulose_celufloc_200|gelain_2020_cellulose_batch_20gl|scientific": (
            "fbba53d18e27963de781abc931c9020ebb6c6b36adceea486c60981ad40fa6e5"
        ),
        "trichoderma_harzianum_p49p11|cellulose_celufloc_200|gelain_2020_cellulose_batch_30gl|exploratory": (
            "e91ac6cf970354351984b2eebbcceff14ec2d8f56da0921e8d86fffc4d70fa47"
        ),
        "trichoderma_harzianum_p49p11|cellulose_celufloc_200|gelain_2020_cellulose_batch_30gl|scientific": (
            "76d68cd900d1854b002c5c77c4bcbc2ad13ab2a862fa81273ecb613d63098789"
        ),
    },
    "solid_case": {
        "solid_reentry__strain_p1|solid_reentry__particulate_lot_p1|solid_reentry__dose_1_25|exploratory": (
            "82a8f47255864e73e870062a4bd404d101035bda6e74f2ca64b39cf044d64809"
        ),
        "solid_reentry__strain_p1|solid_reentry__particulate_lot_p1|solid_reentry__dose_5|exploratory": (
            "703b49aac174e0907e3d22423f563bad75ed44e78406f8adb9f89c847d73546a"
        ),
    },
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


def _substrates(source: Path, changes: Mapping[str, Mapping[str, str]], *, add: Sequence[Mapping[str, str]] = ()) -> str:
    """The fixture's substrates.csv with cells of rows (by substrate_id) replaced and rows added."""

    rows = [{**row, **changes.get(row["substrate_id"], {})} for row in _rows(source, "substrates.csv")]
    rows.extend(dict(item) for item in add)
    return _csv_text(rows, SUBSTRATES_HEADER)


def _kinetics(source: Path, *, change: Mapping[str, str] | None = None, quantity_values: Mapping[tuple[str, str], str] | None = None) -> str:
    """The fixture's kinetics.csv with every row's cells replaced by ``change`` and chosen values replaced."""

    rows = _rows(source, "kinetics.csv")
    header = list(rows[0])
    edited = []
    for row in rows:
        row = {**row, **(change or {})}
        key = (row["enzyme_class"], row["quantity"])
        if quantity_values and key in quantity_values:
            row["value"] = quantity_values[key]
        edited.append(row)
    return _csv_text(edited, header)


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


def _same_units(actual: str, expected: str) -> bool:
    """The same unit, whatever order the unit formatter writes several denominators in."""

    return Q_(1.0, actual).to(expected).magnitude == pytest.approx(1.0, rel=1e-12)


def _parameter(symbol: str, value: float, units: str) -> Parameter:
    return Parameter(
        name=f"artificial {symbol}",
        symbol=symbol,
        value=value,
        units=units,
        uncertainty=0.0,
        source="Artificial unit-bearing coefficient benchmark value; no physical claim.",
        confidence_level="testing",
        notes="Used only to test the compiled core.",
        measurement_method="defined benchmark value",
    )


def _compiled_sample(result: Any) -> tuple[Any, np.ndarray]:
    """The compiled model and initial state vector of the first sample's assembled config."""

    config = load_model_config(Path(result.screen_result.case_results[0].samples[0].config_path))
    inputs = ConfiguredInputLoader().load(config)
    model = ConfiguredProcessAssembler().assemble(config, inputs).model
    request = RunRequest(initial_state=inputs.initial_state, t_span=inputs.t_span, t_eval=inputs.t_eval)
    compiled = ProcessODESolver(model).compile(request)
    vector = np.array(
        [
            float(inputs.initial_state[name].to(units).magnitude)
            for name, units in zip(compiled.state_names, compiled.state_units, strict=True)
        ]
    )
    return compiled, vector


@pytest.fixture(scope="module")
def chain() -> UserDataset:
    return load_user_dataset(CHAIN, registry=REGISTRY_INDEX)


@pytest.fixture(scope="module")
def parallel() -> UserDataset:
    return load_user_dataset(PARALLEL, registry=REGISTRY_INDEX)


@pytest.fixture(scope="module")
def chain_run(tmp_path_factory: pytest.TempPathFactory) -> Any:
    return _simulate(
        tmp_path_factory.mktemp("solid_chain"), CHAIN, fungus="strain_s3", substrate="solid_c3", environments=["c45_ph5"]
    )


@pytest.fixture(scope="module")
def parallel_run(tmp_path_factory: pytest.TempPathFactory) -> Any:
    return _simulate(
        tmp_path_factory.mktemp("solid_parallel"),
        PARALLEL,
        fungus="strain_r4",
        substrate="solid_k4",
        environments=["c37_ph6"],
    )


# ---------------------------------------------------------------------------
# The generic core: a unit-bearing product coefficient (artificial states, no fixture)


def _release_model(*, product_units: str, coefficient_units: str = "millimole / gram") -> Any:
    process = HomogeneousMichaelisMentenProcess(
        name="artificial solid release",
        substrate_state="X",
        km_symbol="km_x",
        vmax_symbol="vmax_x",
        rate_units="gram / liter / hour",
        substrate_units="gram / liter",
        product_coefficients={"Y": 3.0},
        product_coefficient_units={"Y": coefficient_units},
        product_state_units={"Y": product_units},
    )
    return ModelBuilder(
        process_library=ProcessRegistry([process]),
        requested_processes=("homogeneous_michaelis_menten",),
        parameters=ParameterSet(
            [_parameter("km_x", 5.0, "gram / liter"), _parameter("vmax_x", 0.4, "gram / liter / hour")]
        ),
    ).assemble()


def _release_request(product_units: str) -> RunRequest:
    return RunRequest(
        initial_state={"X": Q_(2.0, "gram / liter"), "Y": Q_(0.0, product_units)},
        t_span=(Q_(0.0, "hour"), Q_(20.0, "hour")),
        t_eval=Q_(np.linspace(0.0, 20.0, 21), "hour"),
    )


@pytest.mark.parametrize(("product_units", "column"), [("millimolar", 3.0), ("micromolar", 3000.0)])
def test_a_unit_bearing_coefficient_forms_its_product_in_the_products_own_units(product_units: str, column: float) -> None:
    """3 mmol/g times a rate in g/L/h is 3 mM/h of product: the compiled column is converted once, at build time."""

    model = _release_model(product_units=product_units)
    (process,) = model.processes
    assert {spec.name: spec.units for spec in process.changed_state_variables} == {
        "X": "gram / liter",
        "Y": product_units,
    }
    contribution = process.contributions(Q_(2.0, "gram / liter / hour"))["Y"]
    assert contribution.to(f"{product_units} / hour").magnitude == pytest.approx(2.0 * column, rel=1e-12)
    compiled = ProcessODESolver(model).compile(_release_request(product_units))
    np.testing.assert_allclose(compiled.stoichiometry[:, 0], [-1.0, column], rtol=1e-12)
    result = ProcessODESolver(model).run(_release_request(product_units))
    released = result.state("X").magnitude
    formed = result.state("Y").magnitude
    # Mass to mole through the stated coefficient at every output time: Y = c (X0 - X).
    np.testing.assert_allclose(formed, column * (2.0 - released), rtol=1e-9, atol=1e-12)
    # The substrate follows the integrated Michaelis-Menten law, untouched by the product's units.
    times = np.linspace(0.0, 20.0, 21)
    np.testing.assert_allclose(5.0 * np.log(2.0 / released) + (2.0 - released), 0.4 * times, rtol=1e-6, atol=1e-8)


def test_a_unit_bearing_coefficient_is_refused_without_a_matching_product_dimension() -> None:
    with pytest.raises(ValueError, match="is not an amount in the product's units"):
        _release_model(product_units="gram / liter")
    with pytest.raises(ValueError, match="is not an amount in the product's units"):
        _release_model(product_units="millimolar", coefficient_units="gram / millimole")
    with pytest.raises(ValueError, match="needs its own state units"):
        HomogeneousMichaelisMentenProcess(
            name="artificial release without product units",
            substrate_state="X",
            km_symbol="km_x",
            vmax_symbol="vmax_x",
            rate_units="gram / liter / hour",
            substrate_units="gram / liter",
            product_coefficients={"Y": 3.0},
            product_coefficient_units={"Y": "millimole / gram"},
        )
    with pytest.raises(ValueError, match="pure-number coefficients and are formed in the substrate's units"):
        HomogeneousMichaelisMentenProcess(
            name="artificial release with stray product units",
            substrate_state="X",
            km_symbol="km_x",
            vmax_symbol="vmax_x",
            rate_units="gram / liter / hour",
            substrate_units="gram / liter",
            product_coefficients={"Y": 3.0},
            product_state_units={"Y": "millimolar"},
        )


def test_a_product_map_with_coefficient_units_is_explicit_and_refused_where_coefficients_are_pure_numbers() -> None:
    data = {
        "reactants": {"X": 1.0},
        "products": {"Y": 3.0, "Z": 0.5},
        "coefficient_units": {"Y": "millimole / gram"},
        "provenance": {"source": "artificial"},
    }
    product_map = load_stoichiometric_product_map(data)
    assert product_map.coefficient_units == {"Y": "millimole / gram"}
    assert product_map.to_dict()["coefficient_units"] == {"Y": "millimole / gram"}
    # A pure-number map serialises exactly as before.
    assert "coefficient_units" not in ProductReleaseMap(reactants={"X": 1.0}, products={"Y": 2.0}).to_dict()
    assert product_map.signed_coefficient("Z") == 0.5
    with pytest.raises(ValueError, match="carry units"):
        product_map.signed_coefficient("Y")
    with pytest.raises(ValueError, match="carry units"):
        product_map.validate_weight_conservation({"X": 1.0, "Y": 1.0, "Z": 1.0})
    for units, message in (
        ("g/g", "are dimensionless"),
        ("not_a_unit", "cannot be parsed"),
        (" ", "explicit unit text"),
    ):
        with pytest.raises(ValueError, match=message):
            ProductReleaseMap(reactants={"X": 1.0}, products={"Y": 2.0}, coefficient_units={"Y": units})
    with pytest.raises(ValueError, match="must name product states"):
        ProductReleaseMap(reactants={"X": 1.0}, products={"Y": 2.0}, coefficient_units={"W": "mmol/g"})
    # Factories whose processes form products as pure-number multiples report the map as incompatible.
    context = ProcessBuildContext(
        state_units={"X": "gram / liter", "Y": "millimolar", "Z": "gram / liter", "E": "milligram / liter"},
        product_maps={"release": product_map},
    )
    surface = SimpleNamespace(
        id="artificial surface",
        states={"substrate": "X", "catalyst": "E"},
        parameters={"adsorption_constant": "k_ads", "surface_rate_constant": "k_s", "accessible_surface_area": "a"},
        product_map="release",
        modifiers=(),
    )
    assert "product_map.coefficient_units" in SurfaceCatalysisFactory().can_build(context, surface).incompatible_entities
    ionization = SimpleNamespace(
        id="artificial ionization",
        states={"substrate": "X", "enzyme": "E"},
        parameters={
            name: name
            for name in (
                "turnover",
                "michaelis_constant",
                "free_enzyme_lower_pk",
                "free_enzyme_upper_pk",
                "complex_lower_pk",
                "complex_upper_pk",
                "rate_units",
            )
        },
        product_map="release",
        modifiers=(),
    )
    decision = PHIonizationMichaelisMentenFactory().can_build(context, ionization)
    assert "product_map.coefficient_units" in decision.incompatible_entities
    transglycosylation = SimpleNamespace(
        id="artificial transglycosylation",
        states={"substrate": "X", "enzyme": "E"},
        parameters={
            name: name
            for name in (
                "hydrolysis_km",
                "transglycosylation_km",
                "hydrolysis_kcat",
                "transglycosylation_kcat",
                "rate_units",
            )
        },
        product_map="release",
        modifiers=(),
        raw={"branch": "hydrolysis", "primary_source": "artificial", "maturity": TRANSGLYCOSYLATION_MATURITY},
    )
    decision = SubstrateTransglycosylationFactory().can_build(context, transglycosylation)
    assert "product_map.coefficient_units" in decision.incompatible_entities
    homogeneous = SimpleNamespace(
        id="artificial homogeneous",
        states={"substrate": "X"},
        parameters={"km": "km_x", "vmax": "vmax_x", "rate_units": "gram / liter / hour"},
        product_map="release",
        modifiers=(),
    )
    assert HomogeneousMichaelisMentenFactory().can_build(context, homogeneous).can_build


def test_sbml_export_refuses_a_unit_bearing_coefficient() -> None:
    pytest.importorskip("libsbml")
    from fungal_model.standards.sbml import SbmlExportError, to_sbml

    model = _release_model(product_units="millimolar")
    with pytest.raises(SbmlExportError, match="unit-bearing product coefficient"):
        to_sbml(model, initial_state={"X": Q_(2.0, "gram / liter"), "Y": Q_(0.0, "millimolar")})


def test_conserved_weights_may_carry_units() -> None:
    assert conserved_weight(2.0) == 2.0
    quantity: Any = conserved_weight({"value": 6.0, "units": "mmol/g"})
    assert not isinstance(quantity, float)
    assert quantity.to("millimole / gram").magnitude == pytest.approx(6.0)
    with pytest.raises(ValueError, match="exactly value and units"):
        conserved_weight({"value": 6.0})


def test_final_product_yield_keeps_its_units_across_bases() -> None:
    """Same units: the plain ratio, dimensionless, as before; across bases the pint quotient with its units."""

    assert _final_product_yield(5.0, "millimolar", 10.0, "millimolar") == (0.5, "dimensionless")
    assert _final_product_yield(5.0, "", 10.0, "millimolar") == (0.5, "dimensionless")
    value, units = _final_product_yield(500.0, "micromolar", 1.0, "millimolar")
    assert (value, units) == (pytest.approx(0.5), "dimensionless")
    value, units = _final_product_yield(59.0, "millimole / liter", 10.0, "gram / liter")
    assert (value, units) == (pytest.approx(5.9), "millimole / gram")


def test_initial_state_units_from_several_roles_are_validated_on_the_template() -> None:
    template = {
        "record_id": "artificial_units_template",
        "case_template_id": "artificial_units_template",
        "name": "Artificial template",
        "maturity": "exploratory_metadata",
        "provenance": {"source": "artificial", "confidence_level": "testing"},
        "schema_version": "1",
        "process_type": "enzyme_network",
        "state_roles": {"substrate": "x", "product": "y"},
        "initial_state_mapping": {
            "substrate": {"parameter_role": "x0", "units_from_role": "x0"},
            "product": {"value": 0.0, "units_from_roles": ["x0"]},
        },
        "product_map": {
            "id": "release",
            "product_map_type": "stoichiometric",
            "substrate_state_role": "substrate",
            "product_state_role": "product",
            "stoichiometric_yield": 1.0,
        },
        "stoichiometric_yields": {"product": 1.0},
        "time_grid": {"start": 0.0, "stop": 1.0, "points": 2, "units": "hour"},
        "observable_roles": ["substrate", "product"],
        "output_state_roles": {"substrate": "x", "product": "y"},
        "process_state_metadata": {},
        "limitations": ["Artificial template for a validation test."],
        "validity_notes": ["No scientific use."],
        "notes": "Artificial template exercising initial-state units validation only.",
    }
    with pytest.raises(Exception, match="units_from_roles must list at least two parameter roles"):
        load_registry_record_mapping("case_templates", template)
    both = json.loads(json.dumps(template))
    both["initial_state_mapping"]["product"] = {"value": 0.0, "units": "mM", "units_from_roles": ["x0", "y0"]}
    with pytest.raises(Exception, match="exactly one of units, units_from_role or units_from_roles"):
        load_registry_record_mapping("case_templates", both)
    good = json.loads(json.dumps(template))
    good["initial_state_mapping"]["product"] = {"value": 0.0, "units_from_roles": ["x0", "y0"]}
    record = load_registry_record_mapping("case_templates", good)
    assert isinstance(record, CaseTemplateRecord)
    assert record.initial_state_mapping["product"]["units_from_roles"] == ["x0", "y0"]


# ---------------------------------------------------------------------------
# What a cross-basis network generates


def test_the_solid_links_to_the_dissolved_pool_only_through_its_stated_yield(chain: UserDataset) -> None:
    (network,) = chain.enzyme_networks
    assert network["pools"] == ["solid_c3", "dimer_d3"]
    assert network["product"] == "monomer_m3"
    assert [
        (link["substrate_id"], link["releases"], link["yield"], link["yield_basis"], link["yield_evidence_type"])
        for link in network["links"]
    ] == [
        ("solid_c3", "dimer_d3", CHAIN_YIELD, "mmol/g", "estimate"),
        ("dimer_d3", "monomer_m3", CHAIN_Y2, "mol/mol", None),
    ]
    assert [(item["enzyme_class"], item["pool"], item["rate_form"], item["inhibitor"]) for item in network["processes"]] == [
        (CUTTER, "solid_c3", "kcat", None),
        (HYDROLASE, "dimer_d3", "kcat", "monomer_m3"),
    ]


def test_the_yield_is_a_parameter_record_with_its_own_evidence(chain: UserDataset) -> None:
    records = {item["record_id"]: item for item in chain.records["parameter_records"]}
    record = records[f"{CHAIN_ID}__network__solid_c3__strain_s3__c45_ph5__product_yield__solid_c3"]
    assert record["parameter_symbol"] == f"{CHAIN_ID}__network__solid_c3__product_yield__solid_c3"
    assert record["value"]["kind"] == "exact"
    assert (record["value"]["value"], record["value"]["units"]) == (CHAIN_YIELD, "mmol/g")
    assert record["maturity"] == USER_DATASET_MATURITY_ESTIMATE
    assert record["allowed_use"] == PARAMETER_ALLOWED_USE_EXPLORATORY
    assert record["provenance"]["exploratory_prior"] is True
    assert record["provenance"]["measurement_method"].startswith("computed by the user as 1000 / 324.28 mmol/g")
    dataset = record["provenance"]["fungmod_user_dataset"]
    assert (dataset["file"], dataset["row"], dataset["evidence_type"]) == ("substrates.csv", 2, "estimate")
    assert dataset["enzyme_network"] == {
        "entry_substrate": "solid_c3",
        "role": "product_yield__solid_c3",
        "enzyme_class": None,
        "pool": "solid_c3",
    }
    assert "never derived by FungMod" in record["notes"]
    (compatibility,) = chain.records["process_compatibility"]
    assert compatibility["parameter_roles"]["product_yield__solid_c3"] == record["parameter_symbol"]


def test_the_template_binds_the_yield_and_weighs_the_solid_through_it(chain: UserDataset) -> None:
    (template,) = chain.records["case_templates"]
    metadata = template["process_state_metadata"]
    assert metadata["config_mode"] == "exploratory"
    maps = {item["id"]: item for item in metadata["product_maps"]}
    assert [(item["reactants"], item["products"]) for item in maps.values()] == [
        ({"substrate": 1.0}, {"intermediate_1": {"parameter_role": "product_yield__solid_c3"}}),
        ({"intermediate_1": 1.0}, {"product": CHAIN_Y2}),
    ]
    # 2 x 3.0838 mmol/g x S + 2 D + M: the weight of the solid carries the yield's units.
    assert metadata["conservation"]["state_weights"] == {
        "product": 1.0,
        "intermediate_1": 2.0,
        "substrate": {"value": pytest.approx(2.0 * CHAIN_YIELD), "units": "mmol/g"},
    }
    roles = ["substrate_initial_concentration", "product_yield__solid_c3"]
    assert template["initial_state_mapping"]["intermediate_1"] == {"value": 0.0, "units_from_roles": roles}
    assert template["initial_state_mapping"]["product"] == {"value": 0.0, "units_from_roles": roles}
    loaders = {item["data"]["name"]: item["loader"] for item in metadata["entities"]["substrates"]}
    assert loaders == {"Cellulose-like solid C3": "generic_solid", "Disaccharide-like pool D3": "generic_dissolved"}
    limitations = " ".join(template["limitations"])
    assert "Basis change from Cellulose-like solid C3 (dry mass per volume) to Disaccharide-like pool D3" in limitations
    assert "did not derive it from a molar mass" in limitations
    assert "then amount per volume through its stated yield of 3.0838 mmol/g" in limitations
    assert any("through the stated yield" in note for note in template["validity_notes"])


def test_the_yield_evidence_sets_the_mode_like_any_other_input(tmp_path: Path) -> None:
    """Measured kinetics with a literature yield reach scientific mode; the same kinetics with an estimated yield do not."""

    measured = _kinetics(CHAIN, change={"evidence_type": "measured", "method": "illustrative assay design"})
    literature = _substrates(
        CHAIN,
        {"solid_c3": {"yield_evidence_type": "literature", "yield_method": "computed from tabulated molar masses"}},
    )
    dataset = _load(tmp_path / "literature", CHAIN, {"kinetics.csv": measured, "substrates.csv": literature})
    (template,) = dataset.records["case_templates"]
    assert template["process_state_metadata"]["config_mode"] == "scientific"
    estimated = _load(tmp_path / "estimate", CHAIN, {"kinetics.csv": measured})
    (template,) = estimated.records["case_templates"]
    assert template["process_state_metadata"]["config_mode"] == "exploratory", "the estimated yield alone keeps it exploratory"
    records = [item for item in estimated.records["parameter_records"] if item["maturity"] == USER_DATASET_MATURITY_ESTIMATE]
    assert [item["parameter_symbol"] for item in records] == [f"{CHAIN_ID}__network__solid_c3__product_yield__solid_c3"]


@pytest.mark.parametrize("fixture", sorted(EARLIER_RECORD_DIGESTS))
def test_datasets_without_a_unit_bearing_yield_generate_the_same_records(fixture: str) -> None:
    dataset = load_user_dataset(FIXTURES / fixture, registry=REGISTRY_INDEX)
    digest = hashlib.sha256(json.dumps(dataset.to_dict()["records"], sort_keys=True).encode("utf-8")).hexdigest()
    assert digest == EARLIER_RECORD_DIGESTS[fixture]


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


@pytest.mark.parametrize("group", sorted(EARLIER_CONFIG_DIGESTS))
def test_every_existing_case_assembles_byte_identically(group: str) -> None:
    """The shipped registry cases and every earlier fixture's cases assemble exactly as at the base commit."""

    base = load_registry(REGISTRY_INDEX)
    if group == "registry":
        digests = _config_digests(base, sorted(base.fungi), sorted(base.substrates), sorted(base.environments))
    else:
        dataset = load_user_dataset(FIXTURES / group, registry=REGISTRY_INDEX)
        registry = dataset.overlay(base)
        # The dataset's own substrates and the registry substrates its rows reference.
        substrates = [item["record_id"] for item in dataset.records["substrates"]] + [
            record_id for record_type, record_id in dataset._base_references if record_type == "substrates"
        ]
        digests = _config_digests(
            registry,
            [item["record_id"] for item in dataset.records["fungi"]],
            substrates,
            [item["record_id"] for item in dataset.records["environments"]],
        )
    assert digests == EARLIER_CONFIG_DIGESTS[group]


# ---------------------------------------------------------------------------
# Simulation and analytic checks


def test_the_chain_runs_in_each_pools_own_units_and_closes_through_the_yield(chain_run: Any) -> None:
    series = _series(chain_run)
    times, solid, solid_units = series[(CHAIN_ENVIRONMENT, "substrate")]
    _, dimer, dimer_units = series[(CHAIN_ENVIRONMENT, "intermediate_1")]
    _, monomer, monomer_units = series[(CHAIN_ENVIRONMENT, "product")]
    assert solid_units == "gram / liter"
    # g/L x mmol/g, simplified by pint: the pools after the basis change are amounts per volume.
    assert dimer_units == monomer_units == "millimole / liter"
    assert solid[0] == CHAIN_S0 and dimer[0] == 0.0 and monomer[0] == 0.0
    # Mass to mole balance through the stated yield at every output time: 2 Y S + 2 D + M = 2 Y S0.
    total = CHAIN_Y2 * CHAIN_YIELD * solid + CHAIN_Y2 * dimer + monomer
    np.testing.assert_allclose(total, CHAIN_Y2 * CHAIN_YIELD * CHAIN_S0, rtol=1e-9)
    # The solid process runs in g/L/h on the dry mass; the dimer process in mM/h with competitive inhibition.
    rate_a = series[(CHAIN_ENVIRONMENT, f"process_rate.{PROCESS_A}")]
    rate_b = series[(CHAIN_ENVIRONMENT, f"process_rate.{PROCESS_B}")]
    assert _same_units(rate_a[2], "gram / liter / hour")
    assert _same_units(rate_b[2], "millimole / liter / hour")
    np.testing.assert_allclose(rate_a[1], CHAIN_VMAX_A * solid / (CHAIN_KM_A + solid), rtol=1e-9, atol=1e-15)
    np.testing.assert_allclose(
        rate_b[1],
        CHAIN_VMAX_B * dimer / (CHAIN_KM_B * (1.0 + monomer / CHAIN_KI_B) + dimer),
        rtol=1e-9,
        atol=1e-15,
    )
    np.testing.assert_allclose(series[(CHAIN_ENVIRONMENT, "degradation_rate")][1], rate_a[1], rtol=1e-9, atol=1e-15)
    np.testing.assert_allclose(
        series[(CHAIN_ENVIRONMENT, "product_release_rate")][1], CHAIN_Y2 * rate_b[1], rtol=1e-9, atol=1e-15
    )
    assert np.all(dimer >= 0.0) and dimer.max() > 0.0
    assert times[-1] == 96.0


def test_initial_dimer_formation_is_the_solid_rate_times_the_yield(chain_run: Any) -> None:
    """The compiled stoichiometric column carries the yield: dD/dt(0) = Y Vmax S0 / (Km + S0), in mM/h."""

    compiled, vector = _compiled_sample(chain_run)
    index = {name: position for position, name in enumerate(compiled.state_names)}
    column = {process.name: process.stoichiometry for process in compiled.processes}[PROCESS_A]
    assert column[index["solid_c3_concentration"]] == -1.0
    assert column[index["dimer_d3_concentration"]] == pytest.approx(CHAIN_YIELD, rel=1e-12)
    assert dict(zip(compiled.state_names, compiled.state_units, strict=True))["dimer_d3_concentration"] == (
        "millimole / liter"
    )
    derivative = compiled.rhs(0.0, vector)
    initial_rate = CHAIN_VMAX_A * CHAIN_S0 / (CHAIN_KM_A + CHAIN_S0)
    assert derivative[index["solid_c3_concentration"]] == pytest.approx(-initial_rate, rel=1e-12)
    assert derivative[index["dimer_d3_concentration"]] == pytest.approx(CHAIN_YIELD * initial_rate, rel=1e-12)
    assert derivative[index["monomer_m3_concentration"]] == 0.0


def test_the_chain_outputs_carry_the_right_units_and_an_honest_ledger(chain_run: Any) -> None:
    metrics = {row["metric"]: row for row in chain_run.final_metrics()}
    assert metrics["final_product_formed"]["units"] == "millimole / liter"
    assert _same_units(metrics["maximum_product_release_rate"]["units"], "millimole / liter / hour")
    assert _same_units(metrics["maximum_substrate_depletion_rate"]["units"], "gram / liter / hour")
    # Product formed per initial solid is an amount per dry mass, never labelled dimensionless.
    assert metrics["final_product_yield"]["units"] == "millimole / gram"
    assert float(metrics["final_product_yield"]["value"]) == pytest.approx(
        float(metrics["final_product_formed"]["value"]) / CHAIN_S0, rel=1e-12
    )
    output = Path(chain_run.output_directory)
    with (output / "conservation_diagnostics.csv").open(encoding="utf-8", newline="") as handle:
        (row,) = list(csv.DictReader(handle))
    assert row["validator_id"] == "network_pool_balance" and row["status"] == "evaluated"
    assert row["units"] == "millimole / liter"
    weighted = json.loads(row["weighted_states"])
    assert weighted["solid_c3_concentration"] == {"units": "mmol/g", "value": pytest.approx(2.0 * CHAIN_YIELD)}
    assert float(row["initial_conserved_total"]) == pytest.approx(CHAIN_Y2 * CHAIN_YIELD * CHAIN_S0, rel=1e-12)
    assert float(row["relative_max_absolute_drift"]) < 1e-9
    (report_path,) = output.rglob("validation_report.json")
    (balance,) = [item for item in json.loads(report_path.read_text(encoding="utf-8")) if item["name"] == "mass_balance"]
    assert balance["passed"] is True and balance["details"]["units"] == "millimole / liter"
    limitations = " ".join(row["limitation"] for row in chain_run.limitations())
    assert "Basis change from Cellulose-like solid C3 (dry mass per volume)" in limitations
    assert "the conservation check sums every pool in the final product's units through the stated yield" in limitations


def test_two_classes_on_a_solid_release_a_molar_product_through_the_yield(parallel_run: Any) -> None:
    """Materially different case: parallel kcat and Vmax classes, umol/g, a final product in umol/L."""

    series = _series(parallel_run)
    _, solid, solid_units = series[(PARALLEL_ENVIRONMENT, "substrate")]
    _, dimer, dimer_units = series[(PARALLEL_ENVIRONMENT, "product")]
    assert (solid_units, dimer_units) == ("gram / liter", "micromole / liter")
    # P = Y (S0 - S) at every output time, in umol/L from g/L.
    np.testing.assert_allclose(dimer, PAR_YIELD * (PAR_S0 - solid), rtol=1e-9, atol=1e-9)
    rate_a = series[(PARALLEL_ENVIRONMENT, f"process_rate.{PROCESS_PA}")][1]
    rate_b = series[(PARALLEL_ENVIRONMENT, f"process_rate.{PROCESS_PB}")][1]
    np.testing.assert_allclose(rate_a, PAR_VMAX_A * solid / (PAR_KM_A + solid), rtol=1e-9, atol=1e-15)
    np.testing.assert_allclose(rate_b, PAR_VMAX_B * solid / (PAR_KM_B + solid), rtol=1e-9, atol=1e-15)
    np.testing.assert_allclose(series[(PARALLEL_ENVIRONMENT, "degradation_rate")][1], rate_a + rate_b, rtol=1e-9)
    # The release rate is the summed solid rate times the yield at every output time, the first (t = 0) included.
    release = series[(PARALLEL_ENVIRONMENT, "product_release_rate")]
    assert _same_units(release[2], "micromole / liter / hour")
    np.testing.assert_allclose(release[1], PAR_YIELD * (rate_a + rate_b), rtol=1e-9)
    initial = PAR_VMAX_A * PAR_S0 / (PAR_KM_A + PAR_S0) + PAR_VMAX_B * PAR_S0 / (PAR_KM_B + PAR_S0)
    assert release[1][0] == pytest.approx(PAR_YIELD * initial, rel=1e-12)
    metrics = {row["metric"]: row for row in parallel_run.final_metrics()}
    assert metrics["final_product_yield"]["units"] == "micromole / gram"
    assert float(metrics["final_product_yield"]["value"]) == pytest.approx(PAR_YIELD * (1.0 - solid[-1] / PAR_S0), rel=1e-9)


def test_the_first_order_regime_of_the_parallel_solid_network(tmp_path: Path) -> None:
    """With S0 far below both Km: S = S0 exp(-(Va/Ka + Vb/Kb) t) and P = Y S0 (1 - exp(...)) in umol/L."""

    s0 = 0.002
    kinetics = _kinetics(PARALLEL, quantity_values={(ENDO, "substrate_initial_concentration"): "0.002", (EXO, "substrate_initial_concentration"): "0.002"})
    dataset = _load(tmp_path / "data", PARALLEL, {"kinetics.csv": kinetics})
    result = _simulate(tmp_path / "run", dataset, fungus="strain_r4", substrate="solid_k4", environments=["c37_ph6"])
    series = _series(result)
    times, solid, _ = series[(PARALLEL_ENVIRONMENT, "substrate")]
    dimer = series[(PARALLEL_ENVIRONMENT, "product")][1]
    rate_constant = PAR_VMAX_A / PAR_KM_A + PAR_VMAX_B / PAR_KM_B
    np.testing.assert_allclose(solid, s0 * np.exp(-rate_constant * times), rtol=1e-3)
    np.testing.assert_allclose(dimer, PAR_YIELD * s0 * (1.0 - np.exp(-rate_constant * times)), rtol=1e-3, atol=1e-9)


def test_a_reactivity_factor_on_the_solid_composes_with_the_unit_bearing_release(tmp_path: Path) -> None:
    """The modifier wraps the solid process; its products keep their own units and the closure still holds."""

    kinetics = (CHAIN / "kinetics.csv").read_text(encoding="utf-8") + (
        "strain_s3,solid_cutter_like,solid_c3,c45_ph5,reactivity_exponent,1,,,dimensionless,estimate,"
        "illustrative estimate,Illustrative test note XB-1 p. 6,\n"
    )
    dataset = _load(tmp_path / "data", CHAIN, {"kinetics.csv": kinetics})
    result = _simulate(tmp_path / "run", dataset, fungus="strain_s3", substrate="solid_c3", environments=["c45_ph5"])
    series = _series(result)
    solid = series[(CHAIN_ENVIRONMENT, "substrate")][1]
    dimer, dimer_units = series[(CHAIN_ENVIRONMENT, "intermediate_1")][1:]
    monomer = series[(CHAIN_ENVIRONMENT, "product")][1]
    assert dimer_units == "millimole / liter"
    rate_a = series[(CHAIN_ENVIRONMENT, f"process_rate.{PROCESS_A}")][1]
    np.testing.assert_allclose(
        rate_a, CHAIN_VMAX_A * solid / (CHAIN_KM_A + solid) * (solid / CHAIN_S0), rtol=1e-9, atol=1e-15
    )
    total = CHAIN_Y2 * CHAIN_YIELD * solid + CHAIN_Y2 * dimer + monomer
    np.testing.assert_allclose(total, CHAIN_Y2 * CHAIN_YIELD * CHAIN_S0, rtol=1e-9)


# ---------------------------------------------------------------------------
# The composition builder: a unit-bearing coefficient and weights are checked, never trusted


def _builder_kwargs(dataset: UserDataset) -> tuple[Any, dict[str, Any]]:
    registry = dataset.overlay(load_registry(REGISTRY_INDEX))
    compatibility = registry.process_compatibility[f"{CHAIN_ID}__{CUTTER}__solid_c3__enzyme_network"]
    template = registry.get_case_template(compatibility.case_template_id)
    case = {
        "fungus_id": f"{CHAIN_ID}__strain_s3",
        "substrate_id": f"{CHAIN_ID}__solid_c3",
        "environment_id": CHAIN_ENVIRONMENT,
    }
    records = resolve_screen_role_records(registry=registry, compatibility=compatibility, mode="exploratory", **case)
    return template, {
        "registry": registry,
        "compatibility": compatibility,
        "substrate": registry.get_substrate(case["substrate_id"]),
        "parameter_records": records,
        "output_directory": None,
        **case,
    }


def test_the_composition_builder_checks_the_ledger_through_the_unit_bearing_yield(chain: UserDataset) -> None:
    template, kwargs = _builder_kwargs(chain)
    data = build_enzyme_network_config_data(case_template=template, **kwargs)
    (release,) = [item for item in data["entities"]["product_maps"] if item["id"].endswith("__solid_c3__release_map")]
    assert release["data"]["coefficient_units"] == {"dimer_d3_concentration": "mmol/g"}
    assert release["data"]["coefficient_bindings"] == {
        "dimer_d3_concentration": {
            "parameter_symbol": f"{CHAIN_ID}__network__solid_c3__product_yield__solid_c3",
            "complement": False,
        }
    }
    (other,) = [item for item in data["entities"]["product_maps"] if item["id"].endswith("__dimer_d3__release_map")]
    assert "coefficient_units" not in other["data"]
    (balance,) = [item for item in data["validators"] if item["validator_type"] == "mass_balance"]
    assert balance["conserved_weights"]["solid_c3_concentration"] == {"value": pytest.approx(2.0 * CHAIN_YIELD), "units": "mmol/g"}
    initial = data["initial_state"]["states"]
    assert initial["dimer_d3_concentration"]["units"] == initial["monomer_m3_concentration"]["units"] == "millimole / liter"
    metadata = dict(template.process_state_metadata)

    def with_conservation(weights: Mapping[str, Any]) -> Any:
        return replace(template, process_state_metadata={**metadata, "conservation": {**metadata["conservation"], "state_weights": weights}})

    weights = dict(metadata["conservation"]["state_weights"])
    with pytest.raises(RegistryCaseBuildError, match="is inconsistent for product map"):
        build_enzyme_network_config_data(
            case_template=with_conservation({**weights, "substrate": {"value": 2.0 * CHAIN_YIELD + 1.0, "units": "mmol/g"}}),
            **kwargs,
        )
    with pytest.raises(RegistryCaseBuildError, match="not the ledger's dimension"):
        build_enzyme_network_config_data(
            case_template=with_conservation({**weights, "substrate": 2.0 * CHAIN_YIELD}), **kwargs
        )
    maps = [dict(item) for item in metadata["product_maps"]]
    maps[0] = {**maps[0], "products": {"intermediate_1": {"complement_of_parameter_role": "product_yield__solid_c3"}}}
    with pytest.raises(RegistryCaseBuildError, match="a complement needs a dimensionless fraction"):
        build_enzyme_network_config_data(
            case_template=replace(template, process_state_metadata={**metadata, "product_maps": maps}), **kwargs
        )
    maps = [dict(item) for item in metadata["product_maps"]]
    maps[0] = {**maps[0], "reactants": {"substrate": {"parameter_role": "product_yield__solid_c3"}}, "products": {"intermediate_1": 1.0}}
    with pytest.raises(RegistryCaseBuildError, match="reactant coefficients are pure numbers"):
        build_enzyme_network_config_data(
            case_template=replace(template, process_state_metadata={**metadata, "product_maps": maps}), **kwargs
        )


# ---------------------------------------------------------------------------
# Refusals


def test_a_unit_bearing_yield_of_the_wrong_dimension_is_refused(tmp_path: Path) -> None:
    for index, basis in enumerate(("mmol/L", "g/mmol", "1/h", "parsec")):
        issues = _issues(tmp_path / str(index), CHAIN, {"substrates.csv": _substrates(CHAIN, {"solid_c3": {"yield_basis": basis}})})
        assert _has_issue(issues, "substrates.csv", 2, "yield_basis", f"{basis!r} is not such an amount per mass"), basis
        # The refused basis is reported once; its evidence columns are not judged on top of it.
        assert not [issue for issue in issues if issue["column"] in {"yield_evidence_type", "yield_method"}], issues


def test_a_cross_basis_link_without_a_unit_bearing_yield_is_refused(tmp_path: Path) -> None:
    substrates = _substrates(
        CHAIN, {"solid_c3": {"product_yield": "0.5", "yield_basis": "g/g", "yield_evidence_type": "", "yield_method": ""}}
    )
    issues = _issues(tmp_path, CHAIN, {"substrates.csv": substrates})
    assert _has_issue(issues, "substrates.csv", 2, "yield_basis", "needs a unit-bearing yield")


def test_a_unit_bearing_yield_on_a_same_basis_link_is_refused(tmp_path: Path) -> None:
    """Between two solid pools the yield is a pure g/g number; an amount per mass there would be ambiguous."""

    substrates = _substrates(
        CHAIN,
        {
            "dimer_d3": {
                "physical_state": "solid_polymer",
                "amount_basis": "dry_mass",
                "product_yield": "0.9",
                "yield_basis": "g/g",
            }
        },
    )
    issues = _issues(tmp_path, CHAIN, {"substrates.csv": substrates})
    assert _has_issue(issues, "substrates.csv", 2, "yield_basis", "takes the pure-number yield of that basis (g/g)")


def test_a_unit_bearing_yield_outside_a_network_is_refused(tmp_path: Path) -> None:
    manifest = yaml.safe_load((CHAIN / "user_dataset.yml").read_text(encoding="utf-8"))
    del manifest["enzyme_network"]
    substrates = _substrates(CHAIN, {}, add=())
    kinetics = "\n".join(
        line for line in (CHAIN / "kinetics.csv").read_text(encoding="utf-8").splitlines() if "dimer_hydrolase_like" not in line
    ) + "\n"
    issues = _issues(
        tmp_path,
        CHAIN,
        {"user_dataset.yml": yaml.safe_dump(manifest, sort_keys=False), "substrates.csv": substrates, "kinetics.csv": kinetics},
    )
    assert _has_issue(issues, "substrates.csv", 2, "yield_basis", "in network datasets only")


def test_a_unit_bearing_yield_needs_its_evidence_and_others_take_none(tmp_path: Path) -> None:
    cases = (
        ({"solid_c3": {"yield_evidence_type": ""}}, 2, "yield_evidence_type", "yield_evidence_type is blank"),
        ({"solid_c3": {"yield_evidence_type": "design"}}, 2, "yield_evidence_type", "is 'design'"),
        ({"solid_c3": {"yield_evidence_type": "measured", "yield_method": ""}}, 2, "yield_method", "needs yield_method"),
        ({"dimer_d3": {"yield_evidence_type": "literature"}}, 3, "yield_evidence_type", "applies to a unit-bearing yield only"),
        ({"dimer_d3": {"yield_method": "computed"}}, 3, "yield_method", "applies to a unit-bearing yield only"),
    )
    for index, (changes, row, column, text) in enumerate(cases):
        issues = _issues(tmp_path / str(index), CHAIN, {"substrates.csv": _substrates(CHAIN, changes)})
        assert _has_issue(issues, "substrates.csv", row, column, text), (changes, issues)


def test_a_dissolved_row_takes_no_unit_bearing_yield(tmp_path: Path) -> None:
    substrates = _substrates(CHAIN, {"dimer_d3": {"yield_basis": "g/mmol", "yield_evidence_type": "estimate"}})
    issues = _issues(tmp_path, CHAIN, {"substrates.csv": substrates})
    assert _has_issue(issues, "substrates.csv", 3, "yield_basis", "yield_basis must be 'mol/mol'")


# ---------------------------------------------------------------------------
# Command line


def test_check_data_lists_the_yield_and_its_evidence(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = _cli(capsys, "check-data", CHAIN, "--registry", REGISTRY_INDEX)
    assert code == EXIT_OK
    assert "from solid_c3: solid_c3 -> dimer_d3 (3.0838 mmol/g, estimate), dimer_d3 -> monomer_m3 (2 mol/mol)" in out


def test_check_data_names_a_refused_yield_by_file_row_and_column(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    directory = _copy_fixture(tmp_path, CHAIN, edits={"substrates.csv": _substrates(CHAIN, {"solid_c3": {"yield_basis": "g/mmol"}})})
    code, _, err = _cli(capsys, "check-data", directory, "--registry", REGISTRY_INDEX)
    assert code == EXIT_USAGE
    assert "substrates.csv:2:yield_basis:" in err


def test_fungmod_run_simulates_the_cross_basis_network(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = _cli(
        capsys,
        "run",
        "--user-data",
        CHAIN,
        "--registry",
        REGISTRY_INDEX,
        "--fungus",
        "strain_s3",
        "--substrate",
        "solid_c3",
        "--environment",
        "c45_ph5",
        "--mode",
        "exploratory",
        "--samples",
        "2",
        "--seed",
        "1",
        "--output",
        tmp_path / "run",
        "--no-plots",
    )
    assert code == EXIT_OK, err
    assert "final_product_formed" in out and "millimole / liter" in out
    assert "final_product_yield" in out and "millimole / gram" in out


def test_an_estimated_yield_keeps_measured_kinetics_out_of_scientific_mode(tmp_path: Path) -> None:
    """The preflight and the run treat the yield like any other input: an estimate refuses scientific mode."""

    measured = _kinetics(CHAIN, change={"evidence_type": "measured", "method": "illustrative assay design"})
    literature = _substrates(
        CHAIN,
        {"solid_c3": {"yield_evidence_type": "literature", "yield_method": "computed from tabulated molar masses"}},
    )
    for name, edits, status in (
        ("estimate", {"kinetics.csv": measured}, "underparameterized"),
        ("literature", {"kinetics.csv": measured, "substrates.csv": literature}, "modelable"),
    ):
        dataset = _load(tmp_path / name, CHAIN, edits)
        study = virtual_experiment(
            fungi=["strain_s3"], substrates=["solid_c3"], environments=["c45_ph5"], registry=REGISTRY_INDEX, user_data=dataset
        )
        (report,) = study.preflight(mode="scientific")
        assert report.status == status, (name, report.to_dict())
        if status == "modelable":
            study.simulate(mode="scientific", output_dir=tmp_path / name / "run", quicklook=False)
            manifest = json.loads((tmp_path / name / "run" / "output_manifest.json").read_text(encoding="utf-8"))
            assert manifest["run_label"] == "scientific_exact_unvalidated"
        else:
            with pytest.raises(VirtualExperimentError, match="Scientific simulation requires"):
                study.simulate(mode="scientific", output_dir=tmp_path / name / "run")


def test_numbers_of_the_fixtures_are_consistent() -> None:
    """The stated yields are the user's arithmetic, recorded in yield_method; FungMod only reads them."""

    assert CHAIN_YIELD == pytest.approx(1000.0 / 324.28, abs=5e-5)
    assert PAR_YIELD == pytest.approx(1e6 / 406.4, abs=0.05)
    assert math.isclose(CHAIN_VMAX_B, 3.6)
