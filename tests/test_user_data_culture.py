"""Fungal cultures in user data (USERDATA-009).

An optional ``culture.csv`` binds the registry's existing ``culture_physiology``
composition to a strain growing on one solid substrate: substrate consumption by
one enzyme pool (``k_h E S / (K_h + S)``) with an explicit biomass yield and a
closure ledger, first-order biomass loss, and for every enzyme pool
biomass-proportional, substrate-induced synthesis and first-order loss. No new
numerics: the generated template runs the assembler and process laws of the
registry case.

``tests/fixtures/user_data/culture_reentry`` re-enters the shipped
*T. harzianum* P49P11 registry case (FungMod's retrospective fit as estimates,
the deposited initial conditions as literature), and its trajectories equal the
registry case's. ``tests/fixtures/user_data/culture_estimates`` is a user-defined
fungus on a user-defined xylan-like solid with one protein-mass pool, every value
an illustrative estimate: the materially different, non-specific case. Other
datasets are derived from the two fixtures in temporary directories to test
gaps, routing and refusals only.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from fungal_model import UserDataError, UserDataset, VirtualExperiment, load_user_dataset, virtual_experiment
from fungal_model.api import VirtualExperimentError
from fungal_model.api.user_data import (
    CULTURE_QUANTITIES,
    CULTURE_TABLE,
    USER_DATASET_CULTURE_PROCESS_TYPE,
    USER_DATASET_MATURITY_ESTIMATE,
    USER_DATASET_MATURITY_GAP,
    USER_DATASET_MATURITY_LITERATURE,
)
from fungal_model.api.user_data_assembly import UserTablesAssemblyError, assemble_user_tables
from fungal_model.cli import EXIT_NOT_RUNNABLE, EXIT_OK, EXIT_USAGE, main
from fungal_model.registry import FungModRegistry, load_registry
from fungal_model.screening import RegistryCaseBuildError, assess_modelability
from fungal_model.screening.case_builder import (
    build_model_config_from_registry_case,
    build_registry_process_config_data,
    select_registry_case_compatibility,
)
from fungal_model.screening.culture_physiology import build_culture_physiology_config_data
from fungal_model.screening.ensemble import resolve_screen_role_records

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"
FIXTURES = ROOT / "tests" / "fixtures" / "user_data"
REENTRY = FIXTURES / "culture_reentry"
ESTIMATES = FIXTURES / "culture_estimates"

DATASET = "culture_reentry"
STRAIN = "strain_h1"
CLASS = "cellulase_total_filter_paper_activity"
BG = "beta_glucosidase"
SUBSTRATE = "particulate_lot_h1"
CONDITIONS = ("load_10", "load_20", "load_30")
FUNGUS = f"{DATASET}__{STRAIN}"
SUBSTRATE_ID = f"{DATASET}__{SUBSTRATE}"
TEMPLATE_ID = f"{DATASET}__{CLASS}__{SUBSTRATE}__culture_template"
COMPATIBILITY_ID = f"{DATASET}__{CLASS}__{SUBSTRATE}__culture_physiology"

# The shipped registry case the fixture re-enters.
REGISTRY_FUNGUS = "trichoderma_harzianum_p49p11"
REGISTRY_SUBSTRATE = "cellulose_celufloc_200"
REGISTRY_ENVIRONMENT = {condition: f"gelain_2020_cellulose_batch_{condition[5:]}gl" for condition in CONDITIONS}
REGISTRY_TEMPLATE_ID = "trichoderma_harzianum_cellulose_culture_template"
LOADING = {"load_10": 10.0, "load_20": 20.0, "load_30": 30.0}
X0 = 0.3990672957214788  # g / L, gelain_2020_cellulose_initial_biomass

# SHA-256 of yaml.safe_dump(config.to_dict(), sort_keys=False) of the shipped culture case in scientific mode with
# output directory "<OUTPUT_ROOT>", computed with the base commit of USERDATA-009 (be50dd1): generalising the
# culture assembler must leave the shipped case byte-identical.
SHIPPED_CONFIG_DIGESTS = {
    "load_10": "d8c1d6f644281b5bb213f094fb216b1648bcaa68f508bb43cada80f788101cb8",
    "load_20": "fbba53d18e27963de781abc931c9020ebb6c6b36adceea486c60981ad40fa6e5",
    "load_30": "76d68cd900d1854b002c5c77c4bcbc2ad13ab2a862fa81273ecb613d63098789",
}
# SHA-256 of the generated records (json.dumps(dataset.to_dict()["records"], sort_keys=True)) of the earlier
# fixtures at the same base commit: the culture route must leave every dataset without culture.csv unchanged.
# genome_case and uniprot_case were recomputed on REGISTRY-002 (7d09e65) alone, whose new endo_xylanase,
# glucoamylase and chitinase records resolve in those two fixtures; the culture route leaves them unchanged too.
EARLIER_RECORD_DIGESTS = {
    "esterase_case": "4f92a532f98356be6ac680b4652ac411a975e3c772dd2f0348c590a207ef3464",
    "literature_reentry": "37baa76aaefcbe1d27746720218eafd7712a47ca8c0927245eea597895fce6e1",
    "oxidase_case": "eb82f225a0cd09115afb44b67e0bb2496e7bf11ee7f0960624759b1970f7e322",
    "bgl1a_ph_ionization": "5a5c837fde83d33c1b01fdfd88499eddd4112fbc8a4c3097e6efcaa246af60f1",
    "solid_case": "9b1eecb8cd6820ec7c1c27f17bff9d4820e5679c0350a77c3caba1ced2215e83",
    "genome_case": "f13786fee336d8c58e9dc5d052e1b138158ade98d268cd6b0788ed6b5a8b118e",
    "uniprot_case": "8ec0dfbf50881d866a00b0392149a1dd60cd8260ac3acdd771e5b7d71a5b6532",
}

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


@pytest.fixture(scope="module")
def base_registry() -> FungModRegistry:
    return load_registry(REGISTRY_INDEX)


@pytest.fixture(scope="module")
def reentry(base_registry: FungModRegistry) -> UserDataset:
    return load_user_dataset(REENTRY, registry=base_registry)


@pytest.fixture(scope="module")
def estimates(base_registry: FungModRegistry) -> UserDataset:
    return load_user_dataset(ESTIMATES, registry=base_registry)


# ---------------------------------------------------------------------------
# Helpers


def _copy_fixture(tmp_path: Path, source: Path = REENTRY, *, edits: Mapping[str, str | None] | None = None) -> Path:
    target = tmp_path / source.name
    shutil.copytree(source, target)
    for name, text in (edits or {}).items():
        path = target / name
        if text is None:
            path.unlink()
        else:
            path.write_text(text, encoding="utf-8")
    return target


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
    source: Path = REENTRY,
    *,
    drop: Sequence[tuple[str, str]] = (),
    change: Mapping[tuple[str, str], Mapping[str, str]] | None = None,
    add: Sequence[Mapping[str, str]] = (),
    conditions: Sequence[str] | None = None,
) -> str:
    """The fixture's culture.csv with (quantity, pool) roles dropped or changed at every condition, rows added."""

    rows = []
    for row in _rows(source, CULTURE_TABLE):
        key = (row["quantity"], row["enzyme_class"])
        if key in drop or (conditions is not None and row["condition_id"] not in conditions):
            continue
        rows.append({**row, **(change or {}).get(key, {})})
    rows.extend({**{column: "" for column in CULTURE_HEADER}, **extra} for extra in add)
    return _csv_text(rows, CULTURE_HEADER)


def _culture_row(
    quantity: str, value: str, units: str, *, pool: str = "", condition: str = "load_10", **cells: str
) -> dict[str, str]:
    return {
        "strain_id": STRAIN,
        "substrate_id": SUBSTRATE,
        "condition_id": condition,
        "quantity": quantity,
        "enzyme_class": pool,
        "value": value,
        "units": units,
        "evidence_type": "design",
        "method": "experimental design",
        "source": "Test note TN-9",
        **cells,
    }


def _line(source: Path, quantity: str, pool: str = "", condition: str = "load_10") -> int:
    """The spreadsheet line of a fixture culture.csv row (the header is line 1)."""

    for index, row in enumerate(_rows(source, CULTURE_TABLE), start=2):
        if (row["quantity"], row["enzyme_class"], row["condition_id"]) == (quantity, pool, condition):
            return index
    raise AssertionError((quantity, pool, condition))


def _text_line(text: str, quantity: str, pool: str = "", condition: str = "load_10") -> int:
    """The spreadsheet line of a row of an edited culture.csv text."""

    for index, row in enumerate(csv.DictReader(io.StringIO(text)), start=2):
        if (row["quantity"], row["enzyme_class"], row["condition_id"]) == (quantity, pool, condition):
            return index
    raise AssertionError((quantity, pool, condition))


def _load(tmp_path: Path, edits: Mapping[str, str | None], source: Path = REENTRY) -> UserDataset:
    return load_user_dataset(_copy_fixture(tmp_path, source, edits=edits), registry=REGISTRY_INDEX)


def _issues(tmp_path: Path, edits: Mapping[str, str | None], source: Path = REENTRY) -> list[dict[str, Any]]:
    with pytest.raises(UserDataError) as excinfo:
        _load(tmp_path, edits, source)
    return excinfo.value.issues


def _has_issue(issues: Sequence[Mapping[str, Any]], file: str, row: int | None, column: str | None, text: str) -> bool:
    return any(
        issue["file"] == file and issue["row"] == row and issue["column"] == column and text in issue["message"]
        for issue in issues
    )


def _trajectories(result: Any) -> dict[tuple[str, str], tuple[np.ndarray, np.ndarray, str]]:
    """(environment id, state role) -> (times, values, units) of the simulated states of a one-sample run."""

    series: dict[tuple[str, str], list[tuple[float, float, str]]] = {}
    for row in result.time_series():
        if row["source"] != "simulation_state" or row["sample_index"] != "0":
            continue
        series.setdefault((row["environment_id"], row["state_role"]), []).append(
            (float(row["time"]), float(row["value"]), row["units"])
        )
    return {
        key: (np.array([item[0] for item in items]), np.array([item[1] for item in items]), items[0][2])
        for key, items in series.items()
    }


def _record(dataset: UserDataset, record_id: str) -> Mapping[str, Any]:
    (record,) = [item for item in dataset.records["parameter_records"] if item["record_id"] == record_id]
    return record


def _cli(capsys: pytest.CaptureFixture[str], *args: str | Path) -> tuple[int, str, str]:
    code = main([str(arg) for arg in args])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# ---------------------------------------------------------------------------
# The culture form and its records


def test_reentry_binds_every_role_of_one_culture_model(reentry: UserDataset) -> None:
    assert reentry.summary()["record_counts"] == {
        "fungi": 1,
        "enzyme_classes": 2,
        "substrates": 1,
        "environments": 3,
        "process_compatibility": 1,
        "case_templates": 1,
        "parameter_records": 39,
    }
    (compatibility,) = reentry.records["process_compatibility"]
    assert compatibility["record_id"] == COMPATIBILITY_ID
    assert compatibility["process_type"] == USER_DATASET_CULTURE_PROCESS_TYPE == "culture_physiology"
    assert compatibility["enzyme_class"] == f"{DATASET}__{CLASS}"
    assert compatibility["case_template_id"] == TEMPLATE_ID
    assert set(compatibility["parameter_roles"]) == {
        "initial_substrate",
        "initial_biomass",
        "biomass_yield",
        "biomass_loss_rate",
        "induction_half_saturation",
        "hydrolysis_capacity",
        "hydrolysis_half_saturation",
        *(
            f"{quantity}__{pool}"
            for pool in (CLASS, BG)
            for quantity in (
                "initial_enzyme_concentration",
                "specific_production_rate",
                "enzyme_loss_rate",
            )
        ),
    }
    (template,) = reentry.records["case_templates"]
    assert template["process_type"] == "culture_physiology"
    assert template["state_roles"]["enzyme"] == f"{CLASS}_concentration"
    assert template["state_roles"]["enzyme_beta_glucosidase"] == "beta_glucosidase_concentration"
    metadata = template["process_state_metadata"]
    assert metadata["config_mode"] == "exploratory", "estimates keep the case exploratory"
    assert metadata["geometry"] is None
    assert [item["id"] for item in metadata["process_templates"]] == [
        "substrate_consumption",
        "biomass_loss",
        f"enzyme_synthesis__{CLASS}",
        f"enzyme_loss__{CLASS}",
        "enzyme_synthesis__beta_glucosidase",
        "enzyme_loss__beta_glucosidase",
    ]
    assert [item["process_type"] for item in metadata["process_templates"]] == [
        "homogeneous_michaelis_menten",
        "first_order",
        "proportional_synthesis",
        "first_order",
        "proportional_synthesis",
        "first_order",
    ]
    classes = {item["record_id"]: item for item in reentry.records["enzyme_classes"]}
    assert classes[f"{DATASET}__{CLASS}"]["compatible_processes"] == ["culture_physiology"]
    # The beta-glucosidase pool acts on no modelled state here; its class keeps the enzyme-assay law elsewhere.
    assert classes[f"{DATASET}__{BG}"]["compatible_processes"] == ["homogeneous_michaelis_menten"]
    (fungus,) = reentry.records["fungi"]
    assert "culture cases" in fungus["notes"] and "no other growth" in fungus["notes"]
    assert reentry.cultures[0]["enzyme_pools"] == [CLASS, BG]
    assert reentry.cultures[0]["rows"] == list(range(2, 41))
    assert reentry.summary()["cultures"] == [
        {"strain_id": STRAIN, "substrate_id": SUBSTRATE, "enzyme_class": CLASS, "enzyme_pools": [CLASS, BG]}
    ]
    json.dumps(reentry.to_dict())


def test_record_maturity_follows_evidence_type(reentry: UserDataset) -> None:
    """Estimates are exploratory priors, literature rows user-reported literature; assay pools keep assay units."""

    prefix = f"{DATASET}__{STRAIN}__{SUBSTRATE}__load_20__culture__"
    capacity = _record(reentry, f"{prefix}hydrolysis_capacity")
    assert capacity["maturity"] == USER_DATASET_MATURITY_ESTIMATE
    assert capacity["allowed_use"] == "exploratory_simulation_only_not_literature_curated"
    assert capacity["provenance"]["exploratory_prior"] is True
    assert capacity["value"] == {
        **capacity["value"],
        "kind": "exact",
        "value": 0.018378579847405995,
        "units": "g/FPU/h",
    }
    assert capacity["provenance"]["fungmod_user_dataset"]["file"] == CULTURE_TABLE
    assert capacity["provenance"]["fungmod_user_dataset"]["row"] == _line(
        REENTRY, "hydrolysis_capacity", CLASS, "load_20"
    )
    biomass = _record(reentry, f"{prefix}initial_biomass")
    assert biomass["maturity"] == USER_DATASET_MATURITY_LITERATURE
    assert biomass["allowed_use"] == "scientific_or_exploratory_when_all_other_inputs_are_valid"
    pool = _record(reentry, f"{prefix}initial_enzyme_concentration__{BG}")
    assert pool["value"]["units"] == "BGU/L"
    assert pool["parameter_symbol"] == (f"{DATASET}__culture__initial_enzyme_concentration__{BG}__{CLASS}__{SUBSTRATE}")
    assert pool["environment_id"] == f"{DATASET}__load_20" and pool["fungus_id"] == FUNGUS


# ---------------------------------------------------------------------------
# Parity with the shipped registry case


@pytest.fixture(scope="module")
def parity_runs(tmp_path_factory: pytest.TempPathFactory) -> tuple[Any, Any]:
    output = tmp_path_factory.mktemp("culture_parity")
    user = virtual_experiment(
        fungi=[STRAIN],
        substrates=[SUBSTRATE],
        environments=list(CONDITIONS),
        registry=REGISTRY_INDEX,
        user_data=REENTRY,
    ).simulate(mode="exploratory", n_samples=1, seed=11, output_dir=output / "user", quicklook=False)
    registry = VirtualExperiment.from_registry(
        fungi=[REGISTRY_FUNGUS],
        substrates=[REGISTRY_SUBSTRATE],
        environments=[REGISTRY_ENVIRONMENT[condition] for condition in CONDITIONS],
        registry=REGISTRY_INDEX,
    ).simulate(mode="scientific", output_dir=output / "registry", quicklook=False)
    return user, registry


@pytest.mark.parametrize("condition", CONDITIONS)
def test_reentry_trajectories_equal_the_registry_case(parity_runs: tuple[Any, Any], condition: str) -> None:
    user, registry = parity_runs
    actual, expected = _trajectories(user), _trajectories(registry)
    roles = {
        "substrate",
        "biomass",
        "enzyme",
        "enzyme_beta_glucosidase",
        "ledger_unassimilated_substrate",
        "ledger_biomass_loss",
    }
    environment = f"{DATASET}__{condition}"
    assert {role for env, role in actual if env == environment} == roles
    for role in roles:
        times, values, units = actual[(environment, role)]
        reference_times, reference, reference_units = expected[(REGISTRY_ENVIRONMENT[condition], role)]
        assert units == reference_units, role
        np.testing.assert_array_equal(times, reference_times)
        scale = float(np.max(np.abs(reference)))
        np.testing.assert_allclose(values, reference, rtol=1e-9, atol=1e-12 * scale, err_msg=f"{condition}:{role}")
    # The re-entered culture closes the same dry-mass balance: substrate + biomass + both ledgers = S0 + X0.
    closure = sum(actual[(environment, role)][1] for role in roles if not role.startswith("enzyme"))
    np.testing.assert_allclose(closure, LOADING[condition] + X0, rtol=1e-9)
    assert actual[(environment, "substrate")][1][-1] < 1e-3 * LOADING[condition]


def test_reentry_assembles_the_registry_composition(base_registry: FungModRegistry) -> None:
    """The generated template assembles the registry template's process laws with the same values, role by role."""

    dataset = load_user_dataset(REENTRY, registry=base_registry)
    overlay = dataset.overlay(base_registry)
    environment = f"{DATASET}__load_20"
    report = assess_modelability(
        fungus_id=FUNGUS, substrate_id=SUBSTRATE_ID, environment_id=environment, registry=overlay, mode="exploratory"
    )
    assert report.status == "modelable" and report.selected_compatibility_id == COMPATIBILITY_ID
    compatibility = select_registry_case_compatibility(
        registry=overlay, fungus_id=FUNGUS, substrate_id=SUBSTRATE_ID, report=report
    )
    records = resolve_screen_role_records(
        registry=overlay,
        compatibility=compatibility,
        fungus_id=FUNGUS,
        substrate_id=SUBSTRATE_ID,
        environment_id=environment,
        mode="exploratory",
    )
    user = build_registry_process_config_data(
        registry=overlay,
        compatibility=compatibility,
        fungus_id=FUNGUS,
        substrate_id=SUBSTRATE_ID,
        environment_id=environment,
        parameter_records=records,
        output_directory=None,
    )
    shipped = build_model_config_from_registry_case(
        fungus_id=REGISTRY_FUNGUS,
        substrate_id=REGISTRY_SUBSTRATE,
        environment_id=REGISTRY_ENVIRONMENT["load_20"],
        registry=base_registry,
        mode="scientific",
    ).raw

    def by_role(data: Mapping[str, Any]) -> list[tuple[str, dict[str, str], dict[str, Any]]]:
        roles = {state: role for role, state in data["case_template"]["state_roles"].items()}
        values = {item["symbol"]: (item["value"], item["units"]) for item in data["parameters"][0]["parameters"]}
        return [
            (
                process["process_type"],
                {field: roles[state] for field, state in process["states"].items()},
                {
                    field: values.get(symbol, symbol)
                    for field, symbol in process["parameters"].items()
                    if field != "rate_units"
                },
            )
            for process in data["processes"]
        ]

    def magnitudes(items: list[tuple[str, dict[str, str], dict[str, Any]]]) -> list[Any]:
        from fungal_model.core.units import Q_

        return [
            (
                kind,
                states,
                {
                    field: Q_(*value).to_base_units().magnitude if isinstance(value, tuple) else value
                    for field, value in parameters.items()
                },
            )
            for kind, states, parameters in items
        ]

    user_processes, shipped_processes = magnitudes(by_role(user)), magnitudes(by_role(shipped))
    assert [item[:2] for item in user_processes] == [item[:2] for item in shipped_processes]
    for (_kind, _states, actual), (_kind2, _states2, expected) in zip(user_processes, shipped_processes, strict=True):
        assert actual.keys() == expected.keys()
        for field, value in expected.items():
            assert actual[field] == pytest.approx(value, rel=1e-15), field
    user_map = user["entities"]["product_maps"][0]["data"]
    shipped_map = shipped["entities"]["product_maps"][0]["data"]
    roles_user = {state: role for role, state in user["case_template"]["state_roles"].items()}
    roles_shipped = {state: role for role, state in shipped["case_template"]["state_roles"].items()}
    assert {roles_user[state]: value for state, value in user_map["products"].items()} == {
        roles_shipped[state]: value for state, value in shipped_map["products"].items()
    }
    assert sorted(roles_user[state] for state in user["validators"][1]["conserved_weights"]) == sorted(
        roles_shipped[state] for state in shipped["validators"][1]["conserved_weights"]
    )
    # The user case claims no vessel; its rate units follow the states of the case.
    assert "geometry" not in user["entities"] and "geometry" in shipped["entities"]
    rate_units = {
        process["id"]: process["parameters"]["rate_units"]
        for process in user["processes"]
        if "rate_units" in process["parameters"]
    }
    assert set(rate_units) == {
        "substrate_consumption",
        f"enzyme_synthesis__{CLASS}",
        "enzyme_synthesis__beta_glucosidase",
    }
    # The records' own units (before sampling) per hour, the dataset's time unit.
    assert rate_units["substrate_consumption"] == "(g/L) / hour"
    assert rate_units[f"enzyme_synthesis__{CLASS}"] == "(FPU/L) / hour"
    assert rate_units["enzyme_synthesis__beta_glucosidase"] == "(BGU/L) / hour"


@pytest.mark.parametrize("condition", CONDITIONS)
def test_shipped_case_assembles_byte_identically(base_registry: FungModRegistry, condition: str) -> None:
    config = build_model_config_from_registry_case(
        fungus_id=REGISTRY_FUNGUS,
        substrate_id=REGISTRY_SUBSTRATE,
        environment_id=REGISTRY_ENVIRONMENT[condition],
        registry=base_registry,
        mode="scientific",
        output_directory="<OUTPUT_ROOT>",
    )
    text = yaml.safe_dump(config.to_dict(), sort_keys=False)
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == SHIPPED_CONFIG_DIGESTS[condition]


@pytest.mark.parametrize("fixture", sorted(EARLIER_RECORD_DIGESTS))
def test_datasets_without_culture_generate_the_same_records(fixture: str) -> None:
    dataset = load_user_dataset(FIXTURES / fixture, registry=REGISTRY_INDEX)
    assert dataset.cultures == ()
    digest = hashlib.sha256(json.dumps(dataset.to_dict()["records"], sort_keys=True).encode("utf-8")).hexdigest()
    assert digest == EARLIER_RECORD_DIGESTS[fixture]


def test_assembler_generalisation_is_explicit(base_registry: FungModRegistry) -> None:
    """rate_units_from_state_role and an explicit null geometry are the only additions, and both are checked."""

    template = base_registry.get_case_template(REGISTRY_TEMPLATE_ID)
    (compatibility,) = base_registry.get_process_compatibility(
        enzyme_class=CLASS, substrate_class="cellulose_particulate", process_type="culture_physiology"
    )
    records = {
        role: base_registry.get_parameter_records(parameter_symbol=symbol)[0]
        for role, symbol in compatibility.parameter_roles.items()
        if role != "initial_substrate"
    }
    records["initial_substrate"] = base_registry.get_parameter_records(
        parameter_symbol=compatibility.parameter_roles["initial_substrate"],
        environment_id=REGISTRY_ENVIRONMENT["load_10"],
    )[0]
    kwargs = dict(
        registry=base_registry,
        compatibility=compatibility,
        substrate=base_registry.get_substrate(REGISTRY_SUBSTRATE),
        fungus_id=REGISTRY_FUNGUS,
        substrate_id=REGISTRY_SUBSTRATE,
        environment_id=REGISTRY_ENVIRONMENT["load_10"],
        parameter_records=records,
        output_directory=None,
    )
    metadata = dict(template.process_state_metadata)
    processes = [dict(item) for item in metadata["process_templates"]]

    derived = [dict(item) for item in processes]
    derived[2] = {**derived[2], "fixed_parameters": {}, "rate_units_from_state_role": "enzyme"}
    data = build_culture_physiology_config_data(
        case_template=replace(template, process_state_metadata={**metadata, "process_templates": derived}), **kwargs
    )
    assert data["processes"][2]["parameters"]["rate_units"] == "(filter_paper_unit / liter) / hour"

    both = [dict(item) for item in processes]
    both[2] = {**both[2], "rate_units_from_state_role": "enzyme"}
    with pytest.raises(RegistryCaseBuildError, match="both fixed rate_units and rate_units_from_state_role"):
        build_culture_physiology_config_data(
            case_template=replace(template, process_state_metadata={**metadata, "process_templates": both}), **kwargs
        )
    unknown = [dict(item) for item in processes]
    unknown[2] = {**unknown[2], "fixed_parameters": {}, "rate_units_from_state_role": "pool_without_state"}
    with pytest.raises(RegistryCaseBuildError, match="undeclared state role 'pool_without_state'"):
        build_culture_physiology_config_data(
            case_template=replace(template, process_state_metadata={**metadata, "process_templates": unknown}), **kwargs
        )

    without_geometry = build_culture_physiology_config_data(
        case_template=replace(template, process_state_metadata={**metadata, "geometry": None}), **kwargs
    )
    assert "geometry" not in without_geometry["entities"]
    missing = {key: value for key, value in metadata.items() if key != "geometry"}
    with pytest.raises(RegistryCaseBuildError, match="requires explicit geometry metadata"):
        build_culture_physiology_config_data(case_template=replace(template, process_state_metadata=missing), **kwargs)
    with pytest.raises(RegistryCaseBuildError, match="requires explicit geometry metadata"):
        build_culture_physiology_config_data(
            case_template=replace(template, process_state_metadata={**metadata, "geometry": {}}), **kwargs
        )


# ---------------------------------------------------------------------------
# Modes and the non-specific case


def test_estimates_culture_runs_exploratory_and_is_refused_in_scientific_mode(
    estimates: UserDataset, tmp_path: Path
) -> None:
    (template,) = estimates.records["case_templates"]
    assert template["process_state_metadata"]["config_mode"] == "exploratory"
    assert estimates.cultures[0]["enzyme_pools"] == ["endo_xylanase_like"]
    study = virtual_experiment(
        fungi=["strain_x1"],
        substrates=["xylan_lot_x1"],
        environments=["c25"],
        registry=REGISTRY_INDEX,
        user_data=ESTIMATES,
    )
    (report,) = study.preflight(mode="scientific")
    assert report.status == "underparameterized"
    with pytest.raises(VirtualExperimentError, match="Scientific simulation requires"):
        study.simulate(mode="scientific", output_dir=tmp_path / "scientific")
    result = study.simulate(
        mode="exploratory", n_samples=2, seed=4, output_dir=tmp_path / "exploratory", quicklook=False
    )
    series = _trajectories(result)
    environment = "culture_estimates__c25"
    assert {role for _env, role in series} == {
        "substrate",
        "biomass",
        "enzyme",
        "ledger_unassimilated_substrate",
        "ledger_biomass_loss",
    }
    substrate = series[(environment, "substrate")][1]
    biomass = series[(environment, "biomass")][1]
    pool_times, pool, pool_units = series[(environment, "enzyme")]
    assert pool_units == "milligram / liter", "a protein-mass pool stays a protein mass"
    assert substrate[0] == 15.0 and substrate[-1] < 0.01 * 15.0
    assert biomass.max() > 0.2 and pool.max() > 1.0
    closure = sum(
        series[(environment, role)][1]
        for role in ("substrate", "biomass", "ledger_unassimilated_substrate", "ledger_biomass_loss")
    )
    np.testing.assert_allclose(closure, 15.2, rtol=1e-9)
    (mechanism,) = [row for row in result.mechanism_summary() if row["mechanism_id"] == "culture_physiology"][:1]
    assert mechanism["maturity"] == "software_tested_exploratory_parameterized"
    assert "Enzyme pools keep the units of their parameter records" in mechanism["limitations"]
    assert "retrospective" not in mechanism["limitations"]
    categories = {row["category"] for row in result.limitations()}
    assert "retrospective_calibration" not in categories and "exploratory_prior" in categories
    assert len(pool_times) == 121


def test_measured_culture_runs_in_scientific_mode(tmp_path: Path) -> None:
    """Measured values make the template scientific; the run states exactness, not validation."""

    culture = _culture(ESTIMATES)
    culture = culture.replace(",estimate,illustrative estimate,", ",measured,illustrative measurement for the test,")
    dataset = _load(tmp_path, {CULTURE_TABLE: culture}, ESTIMATES)
    (template,) = dataset.records["case_templates"]
    assert template["process_state_metadata"]["config_mode"] == "scientific"
    study = virtual_experiment(
        fungi=["strain_x1"],
        substrates=["xylan_lot_x1"],
        environments=["c25"],
        registry=REGISTRY_INDEX,
        user_data=dataset,
    )
    (report,) = study.preflight(mode="scientific")
    assert report.status == "modelable", report.to_dict()
    result = study.simulate(mode="scientific", output_dir=tmp_path / "scientific", quicklook=False)
    manifest = json.loads((tmp_path / "scientific" / "output_manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_label"] == "scientific_exact_unvalidated"
    (mechanism,) = [row for row in result.mechanism_summary() if row["mechanism_id"] == "culture_physiology"]
    assert mechanism["maturity"] == "software_tested_user_supplied_parameterized"
    # One estimate is enough to keep the case exploratory: the weakest input wins.
    weakened = culture.replace(
        "biomass_yield,,0.35,,,g/g,measured,illustrative measurement for the test,",
        "biomass_yield,,0.35,,,g/g,estimate,illustrative estimate,",
    )
    weak = _load(tmp_path / "weak", {CULTURE_TABLE: weakened}, ESTIMATES)
    assert weak.records["case_templates"][0]["process_state_metadata"]["config_mode"] == "exploratory"


def test_ranges_are_sampled_in_exploratory_mode(tmp_path: Path) -> None:
    culture = _culture(
        ESTIMATES,
        change={("biomass_yield", ""): {"value": "", "lower": "0.3", "upper": "0.4"}},
    )
    dataset = _load(tmp_path, {CULTURE_TABLE: culture}, ESTIMATES)
    record = _record(dataset, "culture_estimates__strain_x1__xylan_lot_x1__c25__culture__biomass_yield")
    assert record["value"]["kind"] == "range" and record["range_scope"] == "user_supplied_range"
    result = virtual_experiment(
        fungi=["strain_x1"],
        substrates=["xylan_lot_x1"],
        environments=["c25"],
        registry=REGISTRY_INDEX,
        user_data=dataset,
    ).simulate(mode="exploratory", n_samples=3, seed=2, output_dir=tmp_path / "run", quicklook=False)
    sampled = [
        row
        for row in result.sampled_parameters()
        if row["symbol"].endswith("biomass_yield__endo_xylanase_like__xylan_lot_x1")
    ]
    values = [float(row["sampled_value"]) for row in sampled]
    assert len(values) == 3 and len(set(values)) == 3 and all(0.3 <= value <= 0.4 for value in values)


# ---------------------------------------------------------------------------
# Gaps


def test_missing_roles_become_gaps_with_plain_measurement_requests(tmp_path: Path) -> None:
    culture = _culture(drop=(("biomass_yield", ""), ("specific_production_rate", BG), ("initial_biomass", "")))
    dataset = _load(tmp_path, {CULTURE_TABLE: culture})
    prefix = f"{DATASET}__{STRAIN}__{SUBSTRATE}__load_20__culture__"
    gap = _record(dataset, f"{prefix}biomass_yield__gap")
    assert gap["maturity"] == USER_DATASET_MATURITY_GAP and gap["value"]["kind"] == "unknown"
    assert gap["provenance"]["measurement_request"] == (
        "Measure the biomass yield of Culture re-entry strain H1 on Particulate cellulose lot H1 (registry culture "
        "substrate re-entered) at condition load_20 (29 degC, pH 5.0): grams of biomass dry mass formed per gram of "
        "dry Particulate cellulose lot H1 (registry culture substrate re-entered) consumed (g/g, dimensionless)."
    )
    production = _record(dataset, f"{prefix}specific_production_rate__{BG}__gap")
    assert production["provenance"]["measurement_request"] == (
        "Measure the specific production rate of beta-glucosidase by Culture re-entry strain H1 growing on "
        "Particulate cellulose lot H1 (registry culture substrate re-entered) at condition load_20 (29 degC, pH 5.0): "
        "enzyme produced per biomass dry mass per time at inducing substrate levels (amount of the pool per biomass "
        "dry mass per time; the pool is stated in BGU/L, culture.csv row "
        f"{_text_line(culture, 'initial_enzyme_concentration', BG, 'load_20')})."
    )
    assert production["provenance"]["fungmod_user_dataset"]["enzyme_pool"] == f"{DATASET}__{BG}"
    # The initial biomass must share the substrate's units, so its gap carries them; nothing else is guessed.
    assert _record(dataset, f"{prefix}initial_biomass__gap")["value"]["units"] == "g/L"
    assert production["value"]["units"] is None
    study = virtual_experiment(
        fungi=[STRAIN], substrates=[SUBSTRATE], environments=["load_20"], registry=REGISTRY_INDEX, user_data=dataset
    )
    (report,) = study.preflight(mode="exploratory")
    assert report.status == "underparameterized"
    assert gap["provenance"]["measurement_request"] in report.suggested_experiments
    assert len(report.suggested_experiments) == 3


def test_a_condition_without_rows_and_a_strain_without_rows_are_gap_cases(tmp_path: Path) -> None:
    conditions = (REENTRY / "conditions.csv").read_text(encoding="utf-8") + "load_40,29,degC,5.0,Not measured\n"
    strains = (REENTRY / "strains.csv").read_text(encoding="utf-8") + "strain_h2,Culture strain H2 without rows,,\n"
    enzymes = (
        (REENTRY / "enzymes.csv").read_text(encoding="utf-8")
        + f"strain_h2,{CLASS},filter-paper activity (test),Test note TN-9\n"
        + f"strain_h2,{BG},beta-glucosidase activity (test),Test note TN-9\n"
    )
    dataset = _load(tmp_path, {"conditions.csv": conditions, "strains.csv": strains, "enzymes.csv": enzymes})
    gaps = [item for item in dataset.records["parameter_records"] if item["maturity"] == USER_DATASET_MATURITY_GAP]
    assert len(gaps) == 13 + 4 * 13, "load_40 of strain_h1, and every condition of strain_h2"
    request = _record(dataset, f"{DATASET}__{STRAIN}__{SUBSTRATE}__load_40__culture__biomass_loss_rate__gap")[
        "provenance"
    ]["measurement_request"]
    assert "culture.csv states values of this culture only at load_10" in request
    assert "does not reuse values stated at another condition" in request
    entries = {item["strain_id"]: item for item in dataset.cultures}
    assert entries["strain_h2"]["rows"] == [] and entries["strain_h2"]["enzyme_pools"] == [CLASS, BG]


def test_culture_beside_a_gap_case_runs_partially(tmp_path: Path) -> None:
    conditions = (ESTIMATES / "conditions.csv").read_text(encoding="utf-8") + "c30,30,degC,6.0,Not measured\n"
    dataset = _load(tmp_path, {"conditions.csv": conditions}, ESTIMATES)
    study = virtual_experiment(
        fungi=["strain_x1"],
        substrates=["xylan_lot_x1"],
        environments=["c25", "c30"],
        registry=REGISTRY_INDEX,
        user_data=dataset,
    )
    with pytest.raises(VirtualExperimentError):
        study.simulate(mode="exploratory", n_samples=1, seed=1, output_dir=tmp_path / "refused")
    result = study.simulate(
        mode="exploratory", n_samples=1, seed=1, output_dir=tmp_path / "partial", blocked="report", quicklook=False
    )
    assert result.partial_run
    (blocked,) = result.blocked_cases()
    assert blocked["environment_id"] == "culture_estimates__c30"
    assert any(
        "biomass yield of Illustrative culture strain X1" in request for request in blocked["suggested_experiments"]
    )
    with (tmp_path / "partial" / "case_summary.csv").open(encoding="utf-8", newline="") as handle:
        statuses = {row["environment_id"]: row["case_status"] for row in csv.DictReader(handle)}
    assert statuses == {"culture_estimates__c25": "simulated", "culture_estimates__c30": "not_simulated"}


# ---------------------------------------------------------------------------
# Refusals


SOLID_HEADER = (REENTRY / "substrates.csv").read_text(encoding="utf-8").splitlines()[0]


@pytest.mark.parametrize(
    ("change", "column", "message"),
    [
        (("biomass_yield", "", "g/L"), "units", "biomass_yield units 'g/L' must be dimensionless"),
        (("biomass_loss_rate", "", "g/L"), "units", "must have the dimension 1/time"),
        (("enzyme_loss_rate", CLASS, "FPU/L"), "units", "must have the dimension 1/time"),
        (("induction_half_saturation", "", "mmol/L"), "units", "are a molar concentration, but a culture's substrate"),
        (("hydrolysis_half_saturation", CLASS, "1/h"), "units", "must be a dry mass of the substrate per volume"),
        (("substrate_initial_concentration", "", "mol/L"), "units", "are a molar concentration"),
        (("initial_biomass", "", "1/h"), "units", "must be a biomass dry mass per volume"),
        (("initial_enzyme_concentration", CLASS, "umol/L"), "units", "are a molar concentration; an enzyme pool"),
        (("initial_enzyme_concentration", CLASS, "g"), "units", "must be a protein mass per volume"),
        (
            ("hydrolysis_capacity", CLASS, "g/L"),
            "units",
            "hydrolysis_capacity units 'g/L' must be a substrate dry mass",
        ),
        (
            ("specific_production_rate", CLASS, "FPU/L"),
            "units",
            "must be an enzyme amount per biomass dry mass per time",
        ),
        (("biomass_loss_rate", "", "not_a_unit"), "units", "cannot be parsed"),
    ],
)
def test_units_of_the_wrong_dimension_are_refused(
    tmp_path: Path, change: tuple[str, str, str], column: str, message: str
) -> None:
    quantity, pool, units = change
    issues = _issues(tmp_path, {CULTURE_TABLE: _culture(change={(quantity, pool): {"units": units}})})
    assert _has_issue(issues, CULTURE_TABLE, _line(REENTRY, quantity, pool), column, message), issues


@pytest.mark.parametrize(
    ("change", "column", "message"),
    [
        (
            ("hydrolysis_capacity", CLASS, "g/mg/h"),
            "units",
            "do not fit the consuming pool 'cellulase_total_filter_paper_activity'",
        ),
        (
            ("specific_production_rate", CLASS, "mg/g/h"),
            "units",
            "do not fit pool 'cellulase_total_filter_paper_activity'",
        ),
        (("specific_production_rate", BG, "FPU/g/h"), "units", "do not fit pool 'beta_glucosidase'"),
        (("initial_biomass", "", "mg/L"), "units", "whose states share one unit"),
    ],
)
def test_units_of_a_case_are_checked_together(
    tmp_path: Path, change: tuple[str, str, str], column: str, message: str
) -> None:
    """A pool in assay units is never paired with a rate per protein mass, nor a pool with another pool's unit."""

    quantity, pool, units = change
    issues = _issues(tmp_path, {CULTURE_TABLE: _culture(change={(quantity, pool): {"units": units}})})
    assert _has_issue(issues, CULTURE_TABLE, _line(REENTRY, quantity, pool), column, message), issues


@pytest.mark.parametrize(
    ("change", "column", "message"),
    [
        (("biomass_yield", "", {"value": "1.2"}), "value", "biomass_yield must not exceed 1 g/g"),
        (("biomass_yield", "", {"value": "0"}), "value", "biomass_yield must be positive"),
        (("induction_half_saturation", "", {"value": "0"}), "value", "induction_half_saturation must be positive"),
        (("biomass_loss_rate", "", {"value": "-1"}), "value", "value must be nonnegative"),
        (("biomass_yield", "", {"enzyme_class": CLASS}), "enzyme_class", "belongs to the culture as a whole"),
        (("enzyme_loss_rate", CLASS, {"enzyme_class": ""}), "enzyme_class", "belongs to one enzyme pool"),
        (("enzyme_loss_rate", CLASS, {"enzyme_class": "no_such_class"}), "enzyme_class", "is neither a registry"),
        (("biomass_yield", "", {"evidence_type": "fitted"}), "evidence_type", "fits no culture constant"),
        (("biomass_yield", "", {"evidence_type": "guess"}), "evidence_type", "evidence_type must be one of"),
        (("biomass_yield", "", {"evidence_type": "literature", "method": ""}), "method", "method is required"),
        (("biomass_yield", "", {"quantity": "km"}), "quantity", "belongs to the enzyme-assay forms of kinetics.csv"),
        (("biomass_yield", "", {"quantity": "mu_max"}), "quantity", "is not a culture quantity"),
        (("hydrolysis_capacity", CLASS, {"enzyme_class": BG}), "enzyme_class", "belongs to the pool that consumes"),
    ],
)
def test_malformed_culture_rows_are_refused(
    tmp_path: Path, change: tuple[str, str, Mapping[str, str]], column: str, message: str
) -> None:
    quantity, pool, cells = change
    issues = _issues(tmp_path, {CULTURE_TABLE: _culture(change={(quantity, pool): cells})})
    assert _has_issue(issues, CULTURE_TABLE, _line(REENTRY, quantity, pool), column, message), issues


def test_a_culture_on_a_dissolved_substrate_is_refused(tmp_path: Path) -> None:
    substrates = (
        (REENTRY / "substrates.csv").read_text(encoding="utf-8")
        + "dissolved_d1,,Dissolved test substrate D1,soluble_test_class,dissolved,beta_1_4_glycosidic,,product_d1,1,"
        "mol/mol,Test note TN-9\n"
    )
    culture = _culture(add=[_culture_row("biomass_yield", "0.4", "g/g", substrate_id="dissolved_d1")])
    issues = _issues(tmp_path, {"substrates.csv": substrates, CULTURE_TABLE: culture})
    assert _has_issue(
        issues,
        CULTURE_TABLE,
        41,
        "substrate_id",
        "a culture needs a solid_polymer substrate with amount_basis 'dry_mass'",
    ), issues


def test_mixing_the_culture_with_enzyme_assay_forms_is_refused(tmp_path: Path) -> None:
    kinetics = (REENTRY / "kinetics.csv").read_text(
        encoding="utf-8"
    ) + f"{STRAIN},{CLASS},{SUBSTRATE},load_10,km,16.7,,,g/L,estimate,re-entered,Test note TN-9\n"
    issues = _issues(tmp_path, {"kinetics.csv": kinetics})
    assert _has_issue(issues, "kinetics.csv", 2, "substrate_id", "has a culture on substrate 'particulate_lot_h1'"), (
        issues
    )
    assert any("keep the assay kinetics in a separate dataset" in issue["message"] for issue in issues)
    # The same pair from another strain: the pair runs one process.
    strains = (REENTRY / "strains.csv").read_text(encoding="utf-8") + "strain_h2,Assay strain H2,,\n"
    enzymes = (
        (REENTRY / "enzymes.csv").read_text(encoding="utf-8")
        + f"strain_h2,{CLASS},filter-paper activity (test),Test note TN-9\n"
        + f"strain_h2,{BG},beta-glucosidase activity (test),Test note TN-9\n"
    )
    other = (REENTRY / "kinetics.csv").read_text(encoding="utf-8") + (
        f"strain_h2,{CLASS},{SUBSTRATE},load_10,km,16.7,,,g/L,estimate,re-entered,Test note TN-9\n"
    )
    issues = _issues(tmp_path / "pair", {"strains.csv": strains, "enzymes.csv": enzymes, "kinetics.csv": other})
    assert _has_issue(issues, "kinetics.csv", 2, "enzyme_class", "uses the culture form"), issues


def test_a_culture_class_runs_the_culture_form_on_every_substrate(tmp_path: Path) -> None:
    """A culture class acts on two solids and a dissolved substrate: an unstarted solid becomes a gap culture,
    assay kinetics of the class are refused, and so is the dissolved substrate."""

    classes = "class_id,name,target_bond_classes,compatible_substrate_classes,source\n" + (
        "consumer_c1,Consuming pool C1,beta_1_4_glycosidic,solid_test_a;solid_test_b;soluble_test_c,Test note TN-9\n"
    )
    estimates_rows = _rows(ESTIMATES, CULTURE_TABLE)
    culture_rows = [
        {
            **row,
            "strain_id": "strain_c1",
            "substrate_id": "solid_a",
            "enzyme_class": "consumer_c1" if row["enzyme_class"] else "",
        }
        for row in estimates_rows
    ]
    base = {
        "strains.csv": "strain_id,name\nstrain_c1,Test strain C1\n",
        "enzymes.csv": "strain_id,enzyme_class,evidence,source\nstrain_c1,consumer_c1,test,Test note TN-9\n",
        "enzyme_classes.csv": classes,
        CULTURE_TABLE: _csv_text(culture_rows, CULTURE_HEADER),
    }
    substrate_rows = (
        f"{SOLID_HEADER}\n"
        "solid_a,,Solid test A,solid_test_a,solid_polymer,beta_1_4_glycosidic,dry_mass,product_a,1,g/g,Test note TN-9\n"
        "solid_b,,Solid test B,solid_test_b,solid_polymer,beta_1_4_glycosidic,dry_mass,product_b,1,g/g,Test note TN-9\n"
    )
    dataset = _load(tmp_path / "unstarted", {**base, "substrates.csv": substrate_rows}, ESTIMATES)
    pairs = {(item["substrate_id"], tuple(item["enzyme_pools"]), tuple(item["rows"])) for item in dataset.cultures}
    assert ("solid_b", ("consumer_c1",), ()) in pairs, "an unstarted substrate of a culture class is a gap culture"
    assert {item["process_type"] for item in dataset.records["process_compatibility"]} == {"culture_physiology"}

    kinetics = (
        "strain_id,enzyme_class,substrate_id,condition_id,quantity,value,lower,upper,units,evidence_type,method,source\n"
        "strain_c1,consumer_c1,solid_b,c25,km,5,,,g/L,estimate,test,Test note TN-9\n"
    )
    issues = _issues(
        tmp_path / "mixed", {**base, "substrates.csv": substrate_rows, "kinetics.csv": kinetics}, ESTIMATES
    )
    assert _has_issue(
        issues, "kinetics.csv", 2, "enzyme_class", "runs the culture form on all of its substrates or on none"
    ), issues

    dissolved = substrate_rows + (
        "soluble_c,,Soluble test C,soluble_test_c,dissolved,beta_1_4_glycosidic,,product_c,1,mol/mol,Test note TN-9\n"
    )
    issues = _issues(tmp_path / "dissolved", {**base, "substrates.csv": dissolved}, ESTIMATES)
    assert _has_issue(issues, "substrates.csv", 4, "physical_state", "a culture needs a solid_polymer substrate"), (
        issues
    )


def test_time_courses_and_response_laws_of_a_culture_are_refused(tmp_path: Path) -> None:
    timecourse = (
        "strain_id,enzyme_class,substrate_id,condition_id,observable,time,time_units,value,units,source,method\n"
        f"{STRAIN},{CLASS},{SUBSTRATE},load_10,substrate,0,h,10,g/L,Test note TN-9,dry weight\n"
    )
    issues = _issues(tmp_path / "timecourse", {"timecourse.csv": timecourse})
    assert _has_issue(
        issues, "timecourse.csv", 2, "substrate_id", "time courses of culture cases are not compared or fitted"
    ), issues
    responses = (
        "strain_id,enzyme_class,substrate_id,law,parameter,value,units,evidence_type,method,source\n"
        f"{STRAIN},{CLASS},{SUBSTRATE},temperature_cardinal_rosso,minimum_temperature,10,degC,literature,fit,TN-9\n"
        f"{STRAIN},{CLASS},{SUBSTRATE},temperature_cardinal_rosso,optimum_temperature,29,degC,literature,fit,TN-9\n"
        f"{STRAIN},{CLASS},{SUBSTRATE},temperature_cardinal_rosso,maximum_temperature,40,degC,literature,fit,TN-9\n"
    )
    issues = _issues(tmp_path / "responses", {"responses.csv": responses})
    for row in (2, 3, 4):
        assert _has_issue(
            issues, "responses.csv", row, "law", "response laws are not bound to culture cases in this version"
        ), issues


def test_pools_must_be_consuming_pools_and_declared_classes(tmp_path: Path) -> None:
    # No pool acting on the substrate: only the beta-glucosidase pool and culture-level rows.
    only_bg = _culture(drop=tuple((quantity, CLASS) for quantity in CULTURE_QUANTITIES))
    issues = _issues(tmp_path / "none", {CULTURE_TABLE: only_bg})
    assert _has_issue(
        issues, CULTURE_TABLE, 2, "enzyme_class", "names no enzyme pool whose class acts on the substrate"
    ), issues

    # Two pools acting on the substrate consume it in parallel (CULTURE-002, tests/test_user_data_culture_pools.py):
    # the second pool's roles without rows are explicit gaps, and the shared consumption roles become per pool.
    enzymes = (REENTRY / "enzymes.csv").read_text(encoding="utf-8") + (
        f"{STRAIN},cellobiohydrolase,cellobiohydrolase activity (test),Test note TN-9\n"
    )
    two = _culture(add=[_culture_row("enzyme_loss_rate", "0.01", "1/h", pool="cellobiohydrolase")])
    dataset = _load(tmp_path / "two", {"enzymes.csv": enzymes, CULTURE_TABLE: two})
    assert dataset.cultures[0]["consuming_pools"] == [CLASS, "cellobiohydrolase"]
    gap = _record(
        dataset, f"{DATASET}__{STRAIN}__{SUBSTRATE}__load_10__culture__hydrolysis_capacity__cellobiohydrolase__gap"
    )
    assert gap["maturity"] == USER_DATASET_MATURITY_GAP
    assert _record(dataset, f"{DATASET}__{STRAIN}__{SUBSTRATE}__load_10__culture__hydrolysis_capacity__{CLASS}")[
        "value"
    ]["kind"] == "exact"

    # A second class acting on the substrate, declared but not a pool: the case would have two models.
    issues = _issues(tmp_path / "declared", {"enzymes.csv": enzymes})
    assert _has_issue(
        issues, "enzymes.csv", 4, "enzyme_class", "does not choose between a culture and an enzyme-assay"
    ), issues
    assert _has_issue(
        issues, "enzymes.csv", 4, "enzyme_class", "To make 'cellobiohydrolase' a consuming pool of the culture"
    ), issues

    # A strain that declares the consuming class runs the culture and must declare every pool.
    strains = (REENTRY / "strains.csv").read_text(encoding="utf-8") + "strain_h2,Culture strain H2,,\n"
    without_bg = (REENTRY / "enzymes.csv").read_text(encoding="utf-8") + f"strain_h2,{CLASS},test,Test note TN-9\n"
    issues = _issues(tmp_path / "pools", {"strains.csv": strains, "enzymes.csv": without_bg})
    assert _has_issue(
        issues,
        CULTURE_TABLE,
        _line(REENTRY, "initial_enzyme_concentration", BG),
        "enzyme_class",
        "strain 'strain_h2' declares 'cellulase_total_filter_paper_activity' (enzymes.csv row 4) but not "
        "'beta_glucosidase'",
    ), issues

    # A pool the strain does not declare, and a duplicate role.
    undeclared = _culture(add=[_culture_row("enzyme_loss_rate", "0.01", "1/h", pool="cellulase_generic")])
    issues = _issues(tmp_path / "undeclared", {CULTURE_TABLE: undeclared})
    assert _has_issue(issues, CULTURE_TABLE, 41, "enzyme_class", "does not declare enzyme class 'cellulase_generic'"), (
        issues
    )
    duplicate = _culture(add=[_culture_row("biomass_yield", "0.5", "g/g")])
    issues = _issues(tmp_path / "duplicate", {CULTURE_TABLE: duplicate})
    assert _has_issue(issues, CULTURE_TABLE, 41, "quantity", "duplicate or conflicting rows for one role"), issues


def test_every_culture_quantity_has_a_role_label_and_request(reentry: UserDataset, tmp_path: Path) -> None:
    """Dropping every row of one condition gives one gap per role, each with a request naming the role."""

    conditions = (REENTRY / "conditions.csv").read_text(encoding="utf-8") + "load_40,29,degC,5.0,Not measured\n"
    dataset = _load(tmp_path, {"conditions.csv": conditions})
    requests = {
        item["provenance"]["fungmod_user_dataset"]["quantity"]: item["provenance"]["measurement_request"]
        for item in dataset.records["parameter_records"]
        if item["maturity"] == USER_DATASET_MATURITY_GAP and item["environment_id"] == f"{DATASET}__load_40"
    }
    assert set(requests) == set(CULTURE_QUANTITIES)
    for fragment in (
        "initial Particulate cellulose lot H1",
        "initial biomass dry mass concentration (the inoculum)",
        "biomass yield of Culture re-entry strain H1",
        "first-order biomass loss rate",
        "half-saturates the induction of enzyme production",
        "consumption capacity of Total cellulase (filter-paper activity)",
        "runs at half its maximum",
        "specific production rate of",
        "first-order loss rate of",
    ):
        assert any(fragment in request for request in requests.values()), fragment


# ---------------------------------------------------------------------------
# Assembly route and command line


def test_assembly_refuses_the_culture_substrate_with_a_clear_message() -> None:
    with pytest.raises(UserTablesAssemblyError, match="culture.csv has a culture on it"):
        assemble_user_tables(
            dataset_id="culture_draft",
            fungus=STRAIN,
            substrates=[SUBSTRATE],
            conditions=[{"temperature": 29, "temperature_units": "degC", "ph": 5.0}],
            user_data=REENTRY,
            registry=REGISTRY_INDEX,
        )


def test_check_data_lists_the_culture(capsys: pytest.CaptureFixture[str], reentry: UserDataset) -> None:
    code, out, err = _cli(capsys, "check-data", REENTRY, "--registry", REGISTRY_INDEX)
    assert code == EXIT_OK, err
    assert f"Digest: {reentry.digest}" in out
    assert "Kinetic values: 39; gaps: 0" in out
    assert "Cultures (culture.csv; the strain grows on the substrate and secretes its enzyme pools" in out
    assert f"strain_h1  {SUBSTRATE}  {CLASS}" in out
    assert f"{CLASS}, {BG}  2-40" in out


def test_check_data_reports_culture_refusals(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    dataset = _copy_fixture(tmp_path, edits={CULTURE_TABLE: _culture(change={("biomass_yield", ""): {"units": "g/L"}})})
    code, _out, err = _cli(capsys, "check-data", dataset, "--registry", REGISTRY_INDEX)
    assert code == EXIT_USAGE
    assert (
        f"culture.csv:{_line(REENTRY, 'biomass_yield')}:units: biomass_yield units 'g/L' must be dimensionless" in err
    )


def test_run_simulates_the_culture_from_the_command_line(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    selection = ("--user-data", REENTRY, "--fungus", STRAIN, "--substrate", SUBSTRATE, "--environment", "load_10")
    code, out, err = _cli(
        capsys,
        "run",
        *selection,
        "--mode",
        "exploratory",
        "--samples",
        "1",
        "--seed",
        "3",
        "--output",
        tmp_path / "run",
        "--no-plots",
    )
    assert code == EXIT_OK, err
    assert "Simulated 1 case(s) in exploratory mode" in out
    assert "time_to_50_percent_substrate_degradation" in out
    assert (tmp_path / "run" / "output_manifest.json").exists()
    code, out, err = _cli(capsys, "run", *selection, "--mode", "scientific", "--output", tmp_path / "scientific")
    assert code == EXIT_NOT_RUNNABLE
    assert "underparameterized" in out
    assert not (tmp_path / "scientific").exists() or not any((tmp_path / "scientific").iterdir())


def _estimates_run(directory: Path, output: Path) -> Any:
    return virtual_experiment(
        fungi=["strain_x1"],
        substrates=["xylan_lot_x1"],
        environments=["c25"],
        registry=REGISTRY_INDEX,
        user_data=directory,
    ).simulate(mode="exploratory", n_samples=1, seed=4, output_dir=output, quicklook=False)


@pytest.mark.parametrize(("value", "units"), [("350", "mg/g"), ("35", "percent")])
def test_a_biomass_yield_in_scaled_dimensionless_units_is_a_plain_fraction(
    tmp_path: Path, value: str, units: str
) -> None:
    """350 mg/g and 35 percent are 0.35 g/g: the bound and the product-map coefficient use the converted value."""

    edited = _copy_fixture(
        tmp_path / "scaled",
        ESTIMATES,
        edits={
            CULTURE_TABLE: _culture(ESTIMATES, change={("biomass_yield", ""): {"value": value, "units": units}})
        },
    )
    reference = _trajectories(_estimates_run(ESTIMATES, tmp_path / "reference"))
    scaled = _trajectories(_estimates_run(edited, tmp_path / "scaled_run"))
    assert reference.keys() == scaled.keys()
    for key, (times, values, state_units) in reference.items():
        np.testing.assert_array_equal(scaled[key][0], times)
        np.testing.assert_allclose(scaled[key][1], values, rtol=1e-9, atol=1e-12)
        assert scaled[key][2] == state_units


def test_a_biomass_yield_above_one_in_scaled_units_is_refused(tmp_path: Path) -> None:
    culture = _culture(ESTIMATES, change={("biomass_yield", ""): {"value": "1200", "units": "mg/g"}})
    issues = _issues(tmp_path, {CULTURE_TABLE: culture}, source=ESTIMATES)
    assert _has_issue(
        issues, CULTURE_TABLE, _line(ESTIMATES, "biomass_yield", condition="c25"), "value", "must not exceed 1 g/g"
    )


def test_a_small_biomass_yield_in_mg_per_g_is_not_read_as_grams_per_gram(tmp_path: Path) -> None:
    """0.5 mg/g passes the bound either way; it must act as 0.0005 g/g, never as 0.5 g/g."""

    def run(value: str, units: str, name: str) -> dict[tuple[str, str], tuple[np.ndarray, np.ndarray, str]]:
        change = {("biomass_yield", ""): {"value": value, "units": units}}
        edited = _copy_fixture(tmp_path / name, ESTIMATES, edits={CULTURE_TABLE: _culture(ESTIMATES, change=change)})
        return _trajectories(_estimates_run(edited, tmp_path / f"{name}_run"))

    milligrams = run("0.5", "mg/g", "milligrams")
    grams = run("0.0005", "g/g", "grams")
    misread = run("0.5", "g/g", "misread")
    environment = "culture_estimates__c25"
    np.testing.assert_allclose(
        milligrams[(environment, "biomass")][1], grams[(environment, "biomass")][1], rtol=1e-9, atol=1e-12
    )
    assert not np.allclose(milligrams[(environment, "biomass")][1], misread[(environment, "biomass")][1])
