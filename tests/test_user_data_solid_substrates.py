"""Solid substrates in user data (USERDATA-008).

A substrate of a user dataset may be one suspended solid polymer stated on a
dry-mass basis (``physical_state`` ``solid_polymer``, ``amount_basis``
``dry_mass``, a g/g yield). It runs the existing homogeneous Michaelis-Menten
law as an apparent bulk law, ``r = kcat E S / (Km + S)`` with every substrate
amount a dry mass per volume and the enzyme a protein mass or an assay activity
per volume, optionally times the existing conversion-dependent reactivity factor
``(S / S0)^n``.

``tests/fixtures/user_data/solid_case`` re-enters the registry's apparent
hydrolysis constants (a FungMod retrospective fit, typed in as estimates) on a
user-defined particulate substrate with design loadings, at two enzyme doses.
The non-cellulose case near the end is a user-defined endo-xylanase-like class on
a user-defined xylan-like solid with illustrative estimates; it tests the generic
route, not a measurement. Other datasets are derived from the fixtures in
temporary directories to test routing and refusals only.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from scipy.integrate import quad
from scipy.special import lambertw

from fungal_model import UserDataError, UserDataset, load_user_dataset, virtual_experiment
from fungal_model.api import VirtualExperimentError
from fungal_model.api.user_data_assembly import UserTablesAssemblyError, assemble_user_tables
from fungal_model.capability import CapabilityResolver, CazymeFamilyMap
from fungal_model.capability.uniprot import parse_uniprot_tsv, resolve_uniprot_proteome
from fungal_model.core.units import Q_
from fungal_model.modifiers.reactivity import KADAM_2004_SOURCE
from fungal_model.registry import FungModRegistry, load_registry
from fungal_model.registry.loaders import load_parameter_record_mapping, load_registry_record_mapping
from fungal_model.registry.records import EnzymeClassRecord, ParameterRecord
from fungal_model.screening import assess_modelability
from fungal_model.screening.case_builder import (
    build_model_config_from_registry_case,
    build_resolved_case_config,
    resolve_registry_case,
)
from fungal_model.workflows import run_configured_model

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"
FIXTURES = ROOT / "tests" / "fixtures" / "user_data"
SOLID = FIXTURES / "solid_case"
GENOME = FIXTURES / "genome_case"
UNIPROT = FIXTURES / "uniprot_case"
LITERATURE = FIXTURES / "literature_reentry"

DATASET = "solid_reentry"
STRAIN = "strain_p1"
CLASS = "cellulase_total_filter_paper_activity"
SUBSTRATE = "particulate_lot_p1"
FUNGUS = f"{DATASET}__{STRAIN}"
SUBSTRATE_ID = f"{DATASET}__{SUBSTRATE}"
COMPATIBILITY_ID = f"{DATASET}__{CLASS}__{SUBSTRATE}__homogeneous_mm"
TEMPLATE_ID = f"{COMPATIBILITY_ID}_template"
CONDITIONS = ("dose_5", "dose_1_25")


def _prefix(condition: str) -> str:
    return f"{DATASET}__{STRAIN}__{CLASS}__{SUBSTRATE}__{condition}__"


# The registry's apparent hydrolysis constants (gelain_hydrolysis_k_h_calibrated and
# gelain_hydrolysis_Kh_calibrated), the fixture's design loadings and the doses.
K_H = 0.018378579847405995  # g / FPU / h
K_M = 16.726013979440346  # g / L
S0 = 20.0  # g / L
DOSE = {"dose_5": 5.0, "dose_1_25": 1.25}  # FPU / g
ENZYME = {condition: dose * S0 for condition, dose in DOSE.items()}  # FPU / L: 100 and 25
# Line numbers of the fixture's kinetics.csv rows (the header is line 1).
ROW = {
    "km": 2,
    "kcat": 3,
    "substrate_initial_concentration": 4,
    "enzyme_dose": 5,
    "reactivity_exponent": 6,
}

# The registry culture-physiology case whose hydrolysis process the fixture re-enters.
CULTURE = {
    "fungus_id": "trichoderma_harzianum_p49p11",
    "substrate_id": "cellulose_celufloc_200",
    "environment_id": "gelain_2020_cellulose_batch_20gl",
}

# SHA-256 of the generated records of the dissolved fixtures, computed with the base
# commit of USERDATA-008 (5ac677e): solid support must leave dissolved datasets unchanged.
DISSOLVED_RECORD_DIGESTS = {
    "esterase_case": "4f92a532f98356be6ac680b4652ac411a975e3c772dd2f0348c590a207ef3464",
    "literature_reentry": "37baa76aaefcbe1d27746720218eafd7712a47ca8c0927245eea597895fce6e1",
    "oxidase_case": "eb82f225a0cd09115afb44b67e0bb2496e7bf11ee7f0960624759b1970f7e322",
    "bgl1a_ph_ionization": "5a5c837fde83d33c1b01fdfd88499eddd4112fbc8a4c3097e6efcaa246af60f1",
}
# The scientific config of the BGL1A re-entry with output directory "<OUTPUT_ROOT>", at the same commit.
BGL1A_SCIENTIFIC_CONFIG_DIGEST = "31f081a3a7d557d375faf62739c8016e6f0540d9187900398c83c9cd78b9c451"

SOLID_SUBSTRATE_HEADER = (
    "substrate_id,registry_substrate,name,substrate_class,physical_state,bond_classes,amount_basis,product,"
    "product_yield,yield_basis,source"
)


@pytest.fixture(scope="module")
def base_registry() -> FungModRegistry:
    return load_registry(REGISTRY_INDEX)


@pytest.fixture(scope="module")
def solid(base_registry: FungModRegistry) -> UserDataset:
    return load_user_dataset(SOLID, registry=base_registry)


# ---------------------------------------------------------------------------
# Helpers


def _copy_fixture(tmp_path: Path, source: Path = SOLID, *, edits: Mapping[str, str | None] | None = None) -> Path:
    target = tmp_path / source.name
    shutil.copytree(source, target)
    for name, text in (edits or {}).items():
        path = target / name
        if text is None:
            path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    return target


def _kinetics_rows(source: Path = SOLID) -> list[dict[str, str]]:
    with (source / "kinetics.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _kinetics_text(rows: list[dict[str, str]]) -> str:
    buffer = io.StringIO()
    columns = list(dict.fromkeys(column for row in rows for column in row))
    writer = csv.DictWriter(buffer, fieldnames=columns, restval="", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def _edited_kinetics(
    *,
    drop: tuple[str, ...] = (),
    change: Mapping[str, Mapping[str, str]] | None = None,
    add: tuple[Mapping[str, str], ...] = (),
) -> str:
    """The fixture's kinetics.csv with quantities dropped, cells changed (every condition) or rows added."""

    rows = [dict(row) for row in _kinetics_rows() if row["quantity"] not in drop]
    for row in rows:
        row.update((change or {}).get(row["quantity"], {}))
    for extra in add:
        rows.append({**{key: "" for key in rows[0]}, **extra})
    return _kinetics_text(rows)


def _case_row(quantity: str, value: str, units: str, *, condition: str = "dose_5", **cells: str) -> dict[str, str]:
    return {
        "strain_id": STRAIN,
        "enzyme_class": CLASS,
        "substrate_id": SUBSTRATE,
        "condition_id": condition,
        "quantity": quantity,
        "value": value,
        "units": units,
        "evidence_type": "design",
        "method": "experimental design",
        "source": "Design note DN-8 p. 4",
        **cells,
    }


def _load(tmp_path: Path, edits: Mapping[str, str | None], source: Path = SOLID) -> UserDataset:
    return load_user_dataset(_copy_fixture(tmp_path, source, edits=edits), registry=REGISTRY_INDEX)


def _issues(tmp_path: Path, edits: Mapping[str, str | None], source: Path = SOLID) -> list[dict[str, Any]]:
    with pytest.raises(UserDataError) as excinfo:
        _load(tmp_path, edits, source)
    return excinfo.value.issues


def _has_issue(issues: list[dict[str, Any]], file: str, row: int | None, column: str | None, fragment: str) -> bool:
    return any(
        (issue["file"], issue["row"], issue["column"]) == (file, row, column) and fragment in issue["message"]
        for issue in issues
    )


def _records(dataset: UserDataset, record_type: str) -> dict[str, Mapping[str, Any]]:
    return {str(mapping["record_id"]): mapping for mapping in dataset.records[record_type]}


def _parameter(dataset: UserDataset, record_id: str) -> ParameterRecord:
    return load_parameter_record_mapping(_records(dataset, "parameter_records")[record_id])


def _series(result: Any, role: str) -> dict[str, tuple[np.ndarray, np.ndarray, str]]:
    """Per environment: times (hour), values and units of one state role of sample 0."""

    collected: dict[str, list[tuple[float, float, str, str]]] = {}
    for row in result.time_series():
        if row["state_role"] == role and row["sample_index"] in (0, "0"):
            collected.setdefault(row["environment_id"], []).append(
                (float(row["time"]), float(row["value"]), row["units"], row["time_units"])
            )
    series: dict[str, tuple[np.ndarray, np.ndarray, str]] = {}
    for environment, rows in collected.items():
        assert {item[3] for item in rows} == {"hour"}
        (units,) = {item[2] for item in rows}
        series[environment] = (np.array([item[0] for item in rows]), np.array([item[1] for item in rows]), units)
    return series


def _lambert_w_substrate(times: np.ndarray, *, vmax: float, km: float, s0: float) -> np.ndarray:
    """Integrated Michaelis-Menten: Km ln(S0/S) + (S0 - S) = V t, so S = Km W((S0/Km) exp((S0 - V t)/Km))."""

    return km * np.real(lambertw((s0 / km) * np.exp((s0 - vmax * times) / km)))


def _reactivity_time(substrate: float, *, vmax: float, km: float, s0: float, exponent: float) -> float:
    """Time to reach ``substrate`` under r = V S/(Km + S) (S/S0)^n, by quadrature of dt = dS / r(S)."""

    value, _error = quad(
        lambda s: (km + s) / (vmax * s * (s / s0) ** exponent), substrate, s0, epsabs=1e-12, epsrel=1e-12, limit=200
    )
    return value


def _simulate(dataset: UserDataset | Path, tmp_path: Path, *, mode: str = "exploratory", environments=CONDITIONS) -> Any:
    study = virtual_experiment(
        fungi=STRAIN, substrates=SUBSTRATE, environments=list(environments), user_data=dataset, registry=REGISTRY_INDEX
    )
    if mode == "scientific":
        return study.simulate(mode="scientific", output_dir=tmp_path / "scientific", quicklook=False)
    return study.simulate(mode="exploratory", n_samples=1, seed=11, output_dir=tmp_path / "exploratory", quicklook=False)


# ---------------------------------------------------------------------------
# (a) Generated records of a solid substrate


def test_solid_substrate_records_carry_the_physical_state_basis_and_apparent_law(solid: UserDataset) -> None:
    substrate = _records(solid, "substrates")[SUBSTRATE_ID]
    assert substrate["physical_state"] == "solid_polymer"
    assert substrate["substrate_class"] == "cellulose_particulate"
    assert "amount_basis dry_mass" in substrate["notes"] and "g/g" in substrate["notes"]
    assert substrate["properties"] == {}

    template = _records(solid, "case_templates")[TEMPLATE_ID]
    assert template["process_type"] == "homogeneous_michaelis_menten"
    assert template["state_roles"] == {
        "substrate": f"{SUBSTRATE}_concentration",
        "product": "solubilized_substrate_mass_concentration",
        "enzyme": f"{CLASS}_concentration",
    }
    metadata = template["process_state_metadata"]
    # Estimates make the template exploratory; the reactivity factor is bound with S0 = the initial-substrate role.
    assert metadata["config_mode"] == "exploratory"
    assert metadata["process_modifiers"] == [
        {
            "type": "substrate_reactivity",
            "substrate_state_role": "substrate",
            "reference_concentration_role": "substrate_initial_concentration",
            "exponent_role": "reactivity_exponent",
        }
    ]
    limitations = " ".join(template["limitations"])
    assert "Apparent homogeneous Michaelis-Menten kinetics on a suspended solid_polymer substrate" in limitations
    assert "Km is an apparent half-saturation constant and not a binding constant" in limitations
    for absent in ("adsorption", "synergy", "product inhibition", "LPMO"):
        assert absent in limitations
    assert KADAM_2004_SOURCE in limitations
    assert any("1 g/g" in note for note in template["validity_notes"])
    assert "g solubilized_substrate_mass per g dry" in template["product_map"]["notes"]
    assert template["stoichiometric_yields"] == {"product": 1.0}

    compatibility = _records(solid, "process_compatibility")[COMPATIBILITY_ID]
    assert compatibility["parameter_roles"] == {
        role: f"{DATASET}__{quantity}__{CLASS}__{SUBSTRATE}"
        for role, quantity in (
            ("km", "km"),
            ("kcat", "kcat"),
            ("substrate_initial_concentration", "substrate_initial_concentration"),
            ("enzyme_initial_concentration", "enzyme_concentration"),
            ("reactivity_exponent", "reactivity_exponent"),
        )
    }
    assert "apparent bulk law" in compatibility["notes"]
    exponent = _parameter(solid, f"{_prefix('dose_5')}reactivity_exponent")
    assert (exponent.value.value, exponent.value.units, exponent.maturity) == (1.0, "dimensionless", "exploratory_prior")


def test_enzyme_dose_gives_one_derived_record_listing_both_rows(solid: UserDataset) -> None:
    ids = set(_records(solid, "parameter_records"))
    assert not any(record_id.endswith("__enzyme_dose") for record_id in ids)
    for condition, expected in ENZYME.items():
        record = _parameter(solid, f"{_prefix(condition)}enzyme_concentration")
        assert record.value.is_exact
        assert record.value.value == pytest.approx(expected, rel=1e-15)
        assert record.value.units == "filter_paper_unit / liter"
        assert record.maturity == "user_design_value"
        user = record.provenance["fungmod_user_dataset"]
        derivation = user["derivation"]
        assert derivation["route"] == "enzyme_dose"
        assert derivation["formula"] == "enzyme_concentration = enzyme_dose x substrate_initial_concentration"
        assert derivation["units_conversion"] == "(FPU/g) x (g/L) -> filter_paper_unit / liter, factor 1 (pint)"
        assert [item["quantity"] for item in derivation["inputs"]] == ["enzyme_dose", "substrate_initial_concentration"]
        rows = [item["row"] for item in derivation["inputs"]]
        assert user["rows"] == rows and rows[0] - rows[1] == 1
        assert "weakest input" in derivation["maturity_rule"]
        # The initial substrate keeps its own record for the initial-substrate role.
        initial = _parameter(solid, f"{_prefix(condition)}substrate_initial_concentration")
        assert (initial.value.value, initial.value.units) == (S0, "g/L")


def test_enzyme_dose_takes_the_weaker_maturity_scales_a_range_and_converts_units(tmp_path: Path) -> None:
    estimate = _load(
        tmp_path / "estimate", {"kinetics.csv": _edited_kinetics(change={"enzyme_dose": {"evidence_type": "estimate"}})}
    )
    record = _parameter(estimate, f"{_prefix('dose_5')}enzyme_concentration")
    assert record.maturity == "exploratory_prior"
    assert record.provenance["exploratory_prior"] is True

    ranged = _load(
        tmp_path / "range",
        {"kinetics.csv": _edited_kinetics(change={"enzyme_dose": {"value": "", "lower": "4", "upper": "6"}})},
    )
    record = _parameter(ranged, f"{_prefix('dose_5')}enzyme_concentration")
    assert (record.value.kind, record.value.lower, record.value.upper) == ("range", 80.0, 120.0)
    assert record.range_interpretation == "user_stated_bounds_not_calibrated_uncertainty"

    per_kilogram = _load(
        tmp_path / "kg",
        {"kinetics.csv": _edited_kinetics(change={"enzyme_dose": {"value": "5000", "units": "FPU/kg"}})},
    )
    record = _parameter(per_kilogram, f"{_prefix('dose_5')}enzyme_concentration")
    assert record.value.units == "filter_paper_unit / liter"
    assert record.value.value == pytest.approx(100.0, rel=1e-12)
    assert "factor 0.001" in record.provenance["fungmod_user_dataset"]["derivation"]["units_conversion"]

    # A protein-mass dose gives a protein-mass concentration (mg/g x g/L = mg/L).
    protein = _load(
        tmp_path / "protein",
        {
            "kinetics.csv": _edited_kinetics(
                change={"enzyme_dose": {"value": "2", "units": "mg/g"}, "kcat": {"value": "0.5", "units": "g/(mg*h)"}}
            )
        },
    )
    record = _parameter(protein, f"{_prefix('dose_5')}enzyme_concentration")
    assert (record.value.value, record.value.units) == (pytest.approx(40.0), "milligram / liter")


# ---------------------------------------------------------------------------
# (b) Parity with the registry culture-physiology hydrolysis process


def test_parity_with_the_registry_culture_hydrolysis_process(base_registry: FungModRegistry, tmp_path: Path) -> None:
    """Same apparent law, k_h, K_h, enzyme and cellulose amounts: the same substrate trajectory.

    The registry case is a whole culture (biomass, enzyme synthesis and loss), so
    parity is not exact by construction there: its enzyme pool changes in time.
    The calibration override hook of the registry case (``value_overrides``) sets
    the cellulase synthesis and loss rates to zero and the initial filter-paper
    activity to the user case's 100 FPU/L; the cellulose state then follows
    dS/dt = -k_h F S / (K_h + S) with F constant, as the user case does without
    a reactivity exponent. Biomass and the other pools do not act on cellulose.
    Both are also compared with the integrated law (Lambert W).
    """

    resolved = resolve_registry_case(registry=base_registry, mode="scientific", **CULTURE)
    culture_config = build_resolved_case_config(
        resolved,
        registry=base_registry,
        output_directory=str(tmp_path / "culture" / "bundle"),
        value_overrides={
            "gelain_hydrolysis_qF": 0.0,
            "gelain_hydrolysis_kF": 0.0,
            "gelain_2020_cellulose_initial_cellulase_activity": ENZYME["dose_5"],
        },
    )
    (hydrolysis,) = [
        item for item in culture_config.to_dict()["processes"] if item["process_type"] == "homogeneous_michaelis_menten"
    ]
    records = {record.parameter_symbol: record for record in resolved.parameter_records.values()}
    k_h = records[hydrolysis["parameters"]["kcat"]].value
    k_m = records[hydrolysis["parameters"]["km"]].value
    assert (k_h.value, k_h.units) == (K_H, "gram / filter_paper_unit / hour")
    assert (k_m.value, k_m.units) == (K_M, "gram / liter")

    path = tmp_path / "culture" / "model_config.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(culture_config.to_dict(), sort_keys=False), encoding="utf-8")
    culture = run_configured_model(path, output_dir=tmp_path / "culture" / "bundle")
    culture_times = np.asarray(culture.time.to("hour").magnitude, dtype=float)
    culture_substrate = np.asarray(culture.states["cellulose_concentration"].to("gram / liter").magnitude, dtype=float)
    assert np.ptp(np.asarray(culture.states["cellulase_activity"].magnitude, dtype=float)) == 0.0

    # The user case (estimates, so the exploratory screen with exact values) runs the same law and values.
    without_reactivity = _load(tmp_path / "user", {"kinetics.csv": _edited_kinetics(drop=("reactivity_exponent",))})
    result = _simulate(without_reactivity, tmp_path, environments=("dose_5",))
    config = yaml.safe_load(Path(result.screen_result.case_results[0].samples[0].config_path).read_text(encoding="utf-8"))
    (process,) = config["processes"]
    assert process["process_type"] == hydrolysis["process_type"]
    assert process["modifiers"] == hydrolysis["modifiers"] == []
    values_by_symbol = {item["symbol"]: item for item in config["parameters"][0]["parameters"]}
    for field, expected in (("kcat", k_h), ("km", k_m)):
        entry = values_by_symbol[process["parameters"][field]]
        assert Q_(entry["value"], entry["units"]).to(expected.units).magnitude == pytest.approx(expected.value, rel=1e-15)
    times, values, units = _series(result, "substrate")[f"{DATASET}__dose_5"]
    user_substrate = np.asarray(Q_(values, units).to("gram / liter").magnitude, dtype=float)
    np.testing.assert_array_equal(times, culture_times)
    assert len(times) == 97
    np.testing.assert_allclose(user_substrate, culture_substrate, rtol=1e-6, atol=1e-7 * S0)
    analytic = _lambert_w_substrate(times, vmax=K_H * ENZYME["dose_5"], km=K_M, s0=S0)
    np.testing.assert_allclose(user_substrate, analytic, rtol=1e-6, atol=1e-7 * S0)
    np.testing.assert_allclose(culture_substrate, analytic, rtol=1e-6, atol=1e-7 * S0)
    assert user_substrate[-1] < 0.01 * S0


# ---------------------------------------------------------------------------
# (c) Analytic checks


def test_integrated_law_at_two_enzyme_levels_without_reactivity(tmp_path: Path) -> None:
    dataset = _load(tmp_path / "data", {"kinetics.csv": _edited_kinetics(drop=("reactivity_exponent",))})
    template = _records(dataset, "case_templates")[TEMPLATE_ID]
    assert "process_modifiers" not in template["process_state_metadata"]
    assert any("No conversion-dependent slowdown is represented" in item for item in template["limitations"])
    result = _simulate(dataset, tmp_path)
    substrates = _series(result, "substrate")
    products = _series(result, "product")
    finals = {}
    for condition, enzyme in ENZYME.items():
        times, values, units = substrates[f"{DATASET}__{condition}"]
        assert units == "gram / liter"
        analytic = _lambert_w_substrate(times, vmax=K_H * enzyme, km=K_M, s0=S0)
        np.testing.assert_allclose(values, analytic, rtol=1e-6, atol=1e-7 * S0)
        # Mass closure with the stated 1 g/g yield: S + P / Y = S0.
        _times, product, product_units = products[f"{DATASET}__{condition}"]
        assert product_units == "gram / liter"
        np.testing.assert_allclose(values + product / 1.0, S0, rtol=1e-9)
        finals[condition] = values[-1]
    # Four times the enzyme leaves less substrate after 96 h; neither level is exhausted at the lower dose.
    assert 0.0 < finals["dose_5"] < finals["dose_1_25"] < S0


@pytest.mark.parametrize("exponent", [1.0, 2.5])
def test_reactivity_factor_matches_an_independent_quadrature(exponent: float, tmp_path: Path) -> None:
    dataset = _load(
        tmp_path / "data",
        {"kinetics.csv": _edited_kinetics(change={"reactivity_exponent": {"value": f"{exponent:g}"}})},
    )
    result = _simulate(dataset, tmp_path)
    substrates = _series(result, "substrate")
    for condition, enzyme in ENZYME.items():
        times, values, _units = substrates[f"{DATASET}__{condition}"]
        vmax = K_H * enzyme
        # The time to reach each simulated value, from t(S) = integral from S to S0 of dS' / r(S').
        reached = np.array(
            [_reactivity_time(value, vmax=vmax, km=K_M, s0=S0, exponent=exponent) for value in values[1:]]
        )
        np.testing.assert_allclose(reached, times[1:], rtol=1e-5, atol=1e-6)
        if exponent == 1.0:
            # n = 1 has a closed form: t(S) = (S0 / V) (Km (1/S - 1/S0) + ln(S0 / S)).
            closed = (S0 / vmax) * (K_M * (1.0 / values[1:] - 1.0 / S0) + np.log(S0 / values[1:]))
            np.testing.assert_allclose(closed, times[1:], rtol=1e-5, atol=1e-6)
        # The factor slows the reaction against the law without it.
        assert np.all(values[1:] > _lambert_w_substrate(times[1:], vmax=vmax, km=K_M, s0=S0))


def test_reactivity_reference_is_the_case_initial_substrate_record(solid: UserDataset, tmp_path: Path) -> None:
    result = _simulate(solid, tmp_path, environments=("dose_5",))
    sample = result.screen_result.case_results[0].samples[0]
    config = yaml.safe_load(Path(sample.config_path).read_text(encoding="utf-8"))
    (process,) = config["processes"]
    (modifier,) = process["modifiers"]
    initial_symbol = f"{DATASET}__substrate_initial_concentration__{CLASS}__{SUBSTRATE}"
    assert modifier == {
        "type": "substrate_reactivity",
        "substrate_state": f"{SUBSTRATE}_concentration",
        "reference_concentration": initial_symbol,
        "exponent": f"{DATASET}__reactivity_exponent__{CLASS}__{SUBSTRATE}",
    }
    (parameter_set,) = config["parameters"]
    values = {item["symbol"]: item for item in parameter_set["parameters"]}
    assert values[initial_symbol]["value"] == config["initial_state"]["states"][f"{SUBSTRATE}_concentration"]["value"]
    assert process["parameters"]["rate_units"] == "gram / liter / second"


# ---------------------------------------------------------------------------
# (d) Fix (a): the assembler reads the declared physical state


def test_assembler_labels_the_substrate_entity_with_its_declared_physical_state(
    solid: UserDataset, base_registry: FungModRegistry, tmp_path: Path
) -> None:
    result = _simulate(solid, tmp_path, environments=("dose_5",))
    config = yaml.safe_load(Path(result.screen_result.case_results[0].samples[0].config_path).read_text(encoding="utf-8"))
    (entity,) = config["entities"]["substrates"]
    assert entity["loader"] == "generic_solid"
    data = entity["data"]
    assert (data["substrate_type"], data["physical_state"], data["default_degradation_model"]) == (
        "generic_solid",
        "solid_polymer",
        "unknown",
    )

    # A dissolved case keeps its labels: the BGL1A scientific config is byte-identical to the base commit.
    bgl1a = load_user_dataset(FIXTURES / "bgl1a_ph_ionization", registry=base_registry)
    dissolved = build_model_config_from_registry_case(
        fungus_id="bgl1a_ph_reentry__bgl1a_source",
        substrate_id="cellobiose",
        environment_id="bgl1a_ph_reentry__c30_ph5",
        registry=bgl1a.overlay(base_registry),
        mode="scientific",
        output_directory="<OUTPUT_ROOT>",
    ).to_dict()
    (entity,) = dissolved["entities"]["substrates"]
    assert (entity["loader"], entity["data"]["physical_state"], entity["data"]["default_degradation_model"]) == (
        "generic_dissolved",
        "dissolved",
        "homogeneous_dissolved",
    )
    assert hashlib.sha256(json.dumps(dissolved, ensure_ascii=False).encode("utf-8")).hexdigest() == (
        BGL1A_SCIENTIFIC_CONFIG_DIGEST
    )


@pytest.mark.parametrize("fixture", sorted(DISSOLVED_RECORD_DIGESTS))
def test_dissolved_datasets_generate_byte_identical_records(fixture: str, base_registry: FungModRegistry) -> None:
    dataset = load_user_dataset(FIXTURES / fixture, registry=base_registry)
    digest = hashlib.sha256(json.dumps(dataset.to_dict()["records"], sort_keys=True).encode("utf-8")).hexdigest()
    assert digest == DISSOLVED_RECORD_DIGESTS[fixture]
    assert {mapping["physical_state"] for mapping in dataset.records["substrates"]} <= {"dissolved"}


def test_a_registry_solid_polymer_substrate_is_referenced_on_a_dry_mass_basis(
    base_registry: FungModRegistry, tmp_path: Path
) -> None:
    """A registry solid is referenced, not copied; its own physical state reaches the assembled entity."""

    edits = {
        "enzymes.csv": "strain_id,enzyme_class,evidence,source\nstrain_p1,EC 3.2.1.176,activity assay,LN-3 p. 1\n",
        "substrates.csv": (
            f"{SOLID_SUBSTRATE_HEADER}\n"
            "film,cellulose_film_generic,,,,,dry_mass,soluble_cellulose_hydrolysis_product,1,g/g,stated basis\n"
        ),
        "kinetics.csv": _kinetics_text(
            [
                {
                    **row,
                    "enzyme_class": "cellobiohydrolase",
                    "substrate_id": "film",
                    "evidence_type": "estimate",
                    "source": "Illustrative values for the routing test; not measurements",
                }
                for row in _kinetics_rows()
                if row["condition_id"] == "dose_5" and row["quantity"] not in {"kcat", "enzyme_dose"}
            ]
            + [
                {
                    **_case_row("kcat", "0.5", "g/(mg*h)"),
                    "enzyme_class": "cellobiohydrolase",
                    "substrate_id": "film",
                    "evidence_type": "estimate",
                },
                {**_case_row("enzyme_concentration", "4", "mg/L"), "enzyme_class": "cellobiohydrolase", "substrate_id": "film"},
            ]
        ),
    }
    dataset = _load(tmp_path / "data", edits)
    assert dataset.records["substrates"] == ()
    template = _records(dataset, "case_templates")[f"{DATASET}__cellobiohydrolase__film__homogeneous_mm_template"]
    assert template["state_roles"]["substrate"] == "cellulose_film_generic_concentration"
    study = virtual_experiment(
        fungi=STRAIN, substrates="cellulose_film_generic", environments="dose_5", user_data=dataset, registry=base_registry
    )
    assert study.preflight(mode="exploratory")[0].status == "modelable"
    result = study.simulate(mode="exploratory", n_samples=1, seed=2, output_dir=tmp_path / "run", quicklook=False)
    config = yaml.safe_load(Path(result.screen_result.case_results[0].samples[0].config_path).read_text(encoding="utf-8"))
    (entity,) = config["entities"]["substrates"]
    assert (entity["loader"], entity["data"]["physical_state"]) == ("generic_solid", "solid_polymer")


# ---------------------------------------------------------------------------
# (e) Fix (b): a namespaced copy of a registry class and its process list


def test_namespaced_copy_lists_the_processes_it_has_records_for_and_the_parent_is_unchanged(
    solid: UserDataset, base_registry: FungModRegistry
) -> None:
    """The reported defect (the copy overwrites the parent's compatible_processes) does not exist.

    The overlay holds the parent registry record unchanged beside a new
    namespaced record; nothing is overwritten. The copy lists exactly the
    process law the dataset generates compatibility records for. Inheriting the
    parent's list would be wrong, not a fix: preflight looks for a compatibility
    record of every listed law on the substrate, so every case of the copy would
    become underparameterized, as the counterfactual below shows.
    """

    parent = base_registry.enzyme_classes[CLASS]
    assert parent.compatible_processes == ("culture_physiology",)
    overlaid = solid.overlay(base_registry)
    assert overlaid.enzyme_classes[CLASS] == parent
    copy = _records(solid, "enzyme_classes")[f"{DATASET}__{CLASS}"]
    assert copy["compatible_processes"] == ["homogeneous_michaelis_menten"]
    assert copy["provenance"]["registry_parent_enzyme_class"] == CLASS
    generated = {mapping["process_type"] for mapping in solid.records["process_compatibility"]}
    assert set(copy["compatible_processes"]) == generated

    report = assess_modelability(
        fungus_id=FUNGUS, substrate_id=SUBSTRATE_ID, environment_id=f"{DATASET}__dose_5", registry=overlaid, mode="exploratory"
    )
    assert report.status == "modelable"

    inherited = load_registry_record_mapping(
        "enzyme_classes", {**copy, "compatible_processes": [*parent.compatible_processes, *copy["compatible_processes"]]}
    )
    assert isinstance(inherited, EnzymeClassRecord)
    counterfactual = FungModRegistry.build(
        registry_id=overlaid.registry_id,
        version=overlaid.version,
        maturity=overlaid.maturity,
        provenance=overlaid.provenance,
        fungi=overlaid.fungi.values(),
        enzyme_classes=(*(item for key, item in overlaid.enzyme_classes.items() if key != inherited.record_id), inherited),
        substrates=overlaid.substrates.values(),
        environments=overlaid.environments.values(),
        process_compatibility=overlaid.process_compatibility.values(),
        parameters=overlaid.parameters.values(),
        case_templates=overlaid.case_templates.values(),
        product_maps=overlaid.product_maps.values(),
    )
    report = assess_modelability(
        fungus_id=FUNGUS,
        substrate_id=SUBSTRATE_ID,
        environment_id=f"{DATASET}__dose_5",
        registry=counterfactual,
        mode="exploratory",
    )
    assert report.status == "underparameterized"
    assert any(item.item_id.endswith(":culture_physiology") for item in report.incompatible)


# ---------------------------------------------------------------------------
# (f) Modes


def test_scientific_mode_needs_measured_literature_or_design_inputs(base_registry: FungModRegistry, tmp_path: Path) -> None:
    # Test-only values that exercise the mode gate; they are not measurements.
    gate = {"evidence_type": "measured", "method": "stated assay method", "source": "Mode-gate values; not a measurement"}
    eligible = _edited_kinetics(change={"km": gate, "kcat": gate, "reactivity_exponent": gate})
    dataset = _load(tmp_path / "eligible", {"kinetics.csv": eligible})
    template = _records(dataset, "case_templates")[TEMPLATE_ID]
    assert template["process_state_metadata"]["config_mode"] == "scientific"
    study = virtual_experiment(fungi=STRAIN, substrates=SUBSTRATE, environments=list(CONDITIONS), user_data=dataset)
    assert [report.status for report in study.preflight(mode="scientific")] == ["modelable", "modelable"]
    result = study.simulate(mode="scientific", output_dir=tmp_path / "scientific", quicklook=False)
    assert set(_series(result, "substrate")) == {f"{DATASET}__{condition}" for condition in CONDITIONS}
    config = build_model_config_from_registry_case(
        fungus_id=FUNGUS,
        substrate_id=SUBSTRATE_ID,
        environment_id=f"{DATASET}__dose_5",
        registry=dataset.overlay(base_registry),
        mode="scientific",
        output_directory=str(tmp_path / "config"),
    )
    assert config.mode == "scientific"

    # One estimate anywhere, the reactivity exponent included, keeps the case exploratory.
    for quantity in ("reactivity_exponent", "enzyme_dose", "km"):
        change = {key: gate for key in ("km", "kcat", "reactivity_exponent") if key != quantity}
        change[quantity] = {"evidence_type": "estimate"}
        weaker = _load(tmp_path / quantity, {"kinetics.csv": _edited_kinetics(change=change)})
        assert _records(weaker, "case_templates")[TEMPLATE_ID]["process_state_metadata"]["config_mode"] == "exploratory"
        weaker_study = virtual_experiment(fungi=STRAIN, substrates=SUBSTRATE, environments="dose_5", user_data=weaker)
        assert weaker_study.preflight(mode="scientific")[0].status != "modelable", quantity
        assert weaker_study.preflight(mode="exploratory")[0].status in {"modelable", "exploratory"}
        with pytest.raises(VirtualExperimentError, match="Scientific simulation requires exact"):
            weaker_study.simulate(mode="scientific", output_dir=tmp_path / f"{quantity}_run", quicklook=False)


def test_the_fixture_runs_in_exploratory_mode_and_is_refused_in_scientific_mode(solid: UserDataset, tmp_path: Path) -> None:
    study = virtual_experiment(fungi=STRAIN, substrates=SUBSTRATE, environments=list(CONDITIONS), user_data=solid)
    assert [report.status for report in study.preflight(mode="exploratory")] == ["modelable", "modelable"]
    with pytest.raises(VirtualExperimentError, match="Scientific simulation requires exact"):
        study.simulate(mode="scientific", output_dir=tmp_path / "scientific", quicklook=False)
    rows = [row for row in _simulate(solid, tmp_path).time_series() if row["state_role"] == "substrate"]
    assert {row["units"] for row in rows} == {"gram / liter"}


# ---------------------------------------------------------------------------
# (g) A non-cellulose case on the same generic route


XYLAN_TABLES = {
    "user_dataset.yml": (
        "dataset_id: xylan_like_demo\ncontributor: FungMod maintainers\ndate: 2026-10-07\n"
        "source: Illustrative estimates for the generic solid-substrate route; not measurements\n"
        "simulation:\n  duration: 48\n  units: hour\n  points: 49\n"
    ),
    "strains.csv": "strain_id,name,scientific_name,aliases\nstrain_x1,Xylan-route strain X1,,\n",
    "enzyme_classes.csv": (
        "class_id,name,ec_number,target_bond_classes,compatible_substrate_classes,source\n"
        "endo_xylanase_like,endo-xylanase-like hydrolase,3.2.1.8,beta_1_4_xylosidic,xylan_insoluble,"
        "Illustrative class for the generic route\n"
    ),
    "enzymes.csv": "strain_id,enzyme_class,evidence,source\nstrain_x1,endo_xylanase_like,activity assay,LN-12 p. 1\n",
    "substrates.csv": (
        f"{SOLID_SUBSTRATE_HEADER}\n"
        "xylan_like_x1,,Insoluble xylan-like polymer X1,xylan_insoluble,solid_polymer,beta_1_4_xylosidic,dry_mass,"
        "solubilized_polymer_mass,1,g/g,Mass-equivalent pool of solubilized polymer\n"
    ),
    "conditions.csv": "condition_id,temperature,temperature_units,ph,notes\nc45_ph6,45,degC,6,\n",
    "kinetics.csv": (
        "strain_id,enzyme_class,substrate_id,condition_id,quantity,value,lower,upper,units,evidence_type,method,source,"
        "sd,replicates\n"
        "strain_x1,endo_xylanase_like,xylan_like_x1,c45_ph6,km,,5,15,g/L,estimate,,LN-12 p. 2 (illustrative),,\n"
        "strain_x1,endo_xylanase_like,xylan_like_x1,c45_ph6,kcat,,0.2,1,g/(mg*h),estimate,,LN-12 p. 2 (illustrative),,\n"
        "strain_x1,endo_xylanase_like,xylan_like_x1,c45_ph6,substrate_initial_concentration,10,,,g/L,design,"
        "experimental design,LN-12 p. 3,,\n"
        "strain_x1,endo_xylanase_like,xylan_like_x1,c45_ph6,enzyme_concentration,0.5,,,mg/L,design,"
        "experimental design,LN-12 p. 3,,\n"
        "strain_x1,endo_xylanase_like,xylan_like_x1,c45_ph6,reactivity_exponent,,0.5,2,dimensionless,estimate,,"
        "LN-12 p. 4 (illustrative),,\n"
    ),
}


def test_a_non_cellulose_class_on_a_non_cellulose_solid_runs_exploratory_only(tmp_path: Path) -> None:
    directory = tmp_path / "xylan_like"
    directory.mkdir()
    for name, text in XYLAN_TABLES.items():
        (directory / name).write_text(text, encoding="utf-8")
    dataset = load_user_dataset(directory, registry=REGISTRY_INDEX)
    substrate = _records(dataset, "substrates")["xylan_like_demo__xylan_like_x1"]
    assert (substrate["physical_state"], substrate["substrate_class"]) == ("solid_polymer", "xylan_insoluble")
    template = _records(dataset, "case_templates")[
        "xylan_like_demo__endo_xylanase_like__xylan_like_x1__homogeneous_mm_template"
    ]
    assert template["process_state_metadata"]["config_mode"] == "exploratory"
    assert template["process_state_metadata"]["process_modifiers"][0]["type"] == "substrate_reactivity"

    study = virtual_experiment(fungi="strain_x1", substrates="xylan_like_x1", environments="c45_ph6", user_data=dataset)
    assert study.preflight(mode="exploratory")[0].status in {"modelable", "exploratory"}
    assert study.preflight(mode="scientific")[0].status != "modelable"
    with pytest.raises(VirtualExperimentError, match="Scientific simulation requires exact"):
        study.simulate(mode="scientific", output_dir=tmp_path / "scientific", quicklook=False)
    result = study.simulate(mode="exploratory", n_samples=4, seed=8, output_dir=tmp_path / "run", quicklook=False)
    rows = result.time_series()
    for sample_id in {row["sample_id"] for row in rows}:
        substrate_values = [float(r["value"]) for r in rows if r["sample_id"] == sample_id and r["state_role"] == "substrate"]
        product_values = [float(r["value"]) for r in rows if r["sample_id"] == sample_id and r["state_role"] == "product"]
        assert substrate_values[0] == pytest.approx(10.0)
        assert 0.0 < substrate_values[-1] < substrate_values[0]
        assert all(later <= earlier + 1e-12 for earlier, later in zip(substrate_values, substrate_values[1:]))
        assert product_values[-1] == pytest.approx(10.0 - substrate_values[-1], rel=1e-6)
    config = yaml.safe_load(Path(result.screen_result.case_results[0].samples[0].config_path).read_text(encoding="utf-8"))
    (entity,) = config["entities"]["substrates"]
    assert (entity["loader"], entity["data"]["physical_state"]) == ("generic_solid", "solid_polymer")
    assert {row["units"] for row in rows if row["state_role"] == "enzyme"} == {"milligram / liter"}


# ---------------------------------------------------------------------------
# (h) Genome and UniProt routes: a cellobiohydrolase is a gap on a solid cellulose substrate


PARTICULATE_ROW = (
    "particulate_lot_g,,Particulate cellulose lot G,cellulose_particulate,solid_polymer,beta_1_4_glycosidic,dry_mass,"
    "solubilized_substrate_mass,1,g/g,Mass-equivalent pool of solubilized substrate"
)


def _with_particulate_substrate(source: Path) -> str:
    """The fixture's substrates.csv with the amount_basis column and one particulate solid."""

    rows = list(csv.DictReader((source / "substrates.csv").read_text(encoding="utf-8").splitlines()))
    lines = [SOLID_SUBSTRATE_HEADER]
    for row in rows:
        row["amount_basis"] = ""
        lines.append(",".join(f'"{row[column]}"' if "," in row[column] else row[column] for column in SOLID_SUBSTRATE_HEADER.split(",")))
    lines.append(PARTICULATE_ROW)
    return "\n".join(lines) + "\n"


def test_a_genome_resolved_cellobiohydrolase_is_a_gap_on_a_solid_substrate(tmp_path: Path) -> None:
    dataset = _load(tmp_path, {"substrates.csv": _with_particulate_substrate(GENOME)}, source=GENOME)
    prefix = "genome_demo__strain_g1__cellobiohydrolase__particulate_lot_g__c30_ph5__"
    note = "; the class was inferred from the dbCAN annotation (families GH7)."
    gaps = {quantity: _parameter(dataset, f"{prefix}{quantity}__gap") for quantity in (
        "km", "kcat", "substrate_initial_concentration", "enzyme_concentration"
    )}
    for record in gaps.values():
        assert record.maturity == "user_dataset_gap"
        assert record.provenance["measurement_request"].endswith(note)
        assert record.provenance["fungmod_user_dataset"]["class_evidence"] == "genome_annotation"
    assert gaps["km"].provenance["measurement_request"] == (
        "Measure km of Cellobiohydrolase from Genome-annotated strain G1 on Particulate cellulose lot G at 30 degC, "
        f"pH 5.0 (dry mass per volume, for example g/L){note}"
    )
    assert gaps["kcat"].provenance["measurement_request"] == (
        "Measure kcat and the enzyme concentration of Cellobiohydrolase from Genome-annotated strain G1 on "
        "Particulate cellulose lot G at 30 degC, pH 5.0 (kcat as substrate mass per time per enzyme amount; the "
        "enzyme as a protein mass or assay activity per volume, or as an enzyme_dose per substrate mass), or Vmax "
        f"(dry mass per volume per time){note}"
    )
    assert gaps["kcat"].provenance["fungmod_user_dataset"]["required_dimension"].startswith("substrate mass per time")
    # cellulase_generic acts on cellulose films only, so it has no case on the particulate substrate.
    assert not any("cellulase_generic__particulate_lot_g" in key for key in _records(dataset, "parameter_records"))
    report = virtual_experiment(
        fungi="strain_g1", substrates="particulate_lot_g", environments="c30_ph5", user_data=dataset
    ).preflight(mode="exploratory")[0]
    assert report.status == "underparameterized"
    assert all(text.endswith(note) for text in report.suggested_experiments)
    assert len(report.suggested_experiments) == 3  # kcat and the enzyme concentration share one request


def test_a_proteome_resolved_cellobiohydrolase_is_a_gap_on_a_solid_substrate(tmp_path: Path) -> None:
    dataset = _load(tmp_path, {"substrates.csv": _with_particulate_substrate(UNIPROT)}, source=UNIPROT)
    record = _parameter(dataset, "uniprot_demo__strain_u1__cellobiohydrolase__particulate_lot_g__c30_ph5__km__gap")
    assert record.provenance["measurement_request"] == (
        "Measure km of Cellobiohydrolase from Proteome-annotated strain U1 on Particulate cellulose lot G at 30 degC, "
        "pH 5.0 (dry mass per volume, for example g/L); the class was inferred from UniProt proteome UP000000000 "
        "(accessions X0TEST05; CAZy families GH7; EC 3.2.1.91; 1 of 1 reviewed in Swiss-Prot)."
    )
    resolved = {item["enzyme_class"]: item for item in dataset.genome_resolved_classes}
    assert resolved["cellobiohydrolase"]["accessions_by_basis"]["cazy_and_ec"] == ["X0TEST05"]


# ---------------------------------------------------------------------------
# (i) Refusals, each naming file, row and column


def _solid_row(**cells: str) -> str:
    base = {
        "substrate_id": "particulate_lot_p1",
        "registry_substrate": "",
        "name": "Particulate cellulose lot P1",
        "substrate_class": "cellulose_particulate",
        "physical_state": "solid_polymer",
        "bond_classes": "beta_1_4_glycosidic",
        "amount_basis": "dry_mass",
        "product": "solubilized_substrate_mass",
        "product_yield": "1",
        "yield_basis": "g/g",
        "source": "stated",
        **cells,
    }
    return f"{SOLID_SUBSTRATE_HEADER}\n" + ",".join(base[column] for column in SOLID_SUBSTRATE_HEADER.split(",")) + "\n"


REFUSALS: dict[str, tuple[dict[str, Any], tuple[str, int | None, str | None, str]]] = {
    "specific_activity on a solid": (
        {"add": (_case_row("specific_activity", "5", "umol/min/mg"), _case_row("enzyme_loading", "2", "mg/L"))},
        ("kinetics.csv", 12, "quantity", "specific_activity is refused on a solid substrate"),
    ),
    "enzyme_loading on a solid": (
        {"add": (_case_row("enzyme_loading", "2", "mg/L"),)},
        ("kinetics.csv", 12, "quantity", "enzyme_loading belongs to the specific_activity route"),
    ),
    "assay_activity on a solid": (
        {
            "add": (
                _case_row(
                    "assay_activity",
                    "3",
                    "U/mL",
                    activity_substrate="particulate_lot_p1",
                    activity_saturating="yes",
                ),
            )
        },
        ("kinetics.csv", 12, "quantity", "a saturating activity is not defined for an interfacial substrate"),
    ),
    "pH-ionization form on a solid": (
        {"add": (_case_row("kcat_limiting", "1", "1/s", evidence_type="estimate"),)},
        ("kinetics.csv", 12, "quantity", "belongs to the pH-ionization form, which is refused on a solid substrate"),
    ),
    "molar km on a solid": (
        {"change": {"km": {"units": "mM"}}},
        ("kinetics.csv", ROW["km"], "units", "are a molar concentration, but the substrate is a solid polymer"),
    ),
    "molar initial substrate on a solid": (
        {"change": {"substrate_initial_concentration": {"units": "mM"}}},
        ("kinetics.csv", ROW["substrate_initial_concentration"], "units", "would need the molar mass of a repeat unit"),
    ),
    "molar vmax on a solid": (
        {"drop": ("kcat", "enzyme_dose"), "add": (_case_row("vmax", "1", "mM/h"),)},
        ("kinetics.csv", 8, "units", "vmax units 'mM/h' are an amount per volume per time"),
    ),
    "molar enzyme on a solid": (
        {"drop": ("enzyme_dose",), "add": (_case_row("enzyme_concentration", "0.001", "mM"),)},
        ("kinetics.csv", 10, "units", "enzyme_concentration units 'mM' are a molar concentration"),
    ),
    "kcat per protein mass with an assay-unit enzyme": (
        {"change": {"kcat": {"value": "0.5", "units": "g/(mg*h)"}}},
        ("kinetics.csv", ROW["kcat"], "units", "do not fit the enzyme concentration"),
    ),
    "kcat per assay unit with a protein-mass dose": (
        {"change": {"enzyme_dose": {"value": "2", "units": "mg/g"}}},
        ("kinetics.csv", ROW["kcat"], "units", "kcat x E has units"),
    ),
    "kcat that is no mass rate per enzyme": (
        {"change": {"kcat": {"units": "g/h"}}},
        ("kinetics.csv", ROW["kcat"], "units", "must be a substrate mass per time per enzyme amount"),
    ),
    "enzyme dose beside an enzyme concentration": (
        {"add": (_case_row("enzyme_concentration", "100", "FPU/L"),)},
        ("kinetics.csv", ROW["enzyme_dose"], "quantity", "both set the enzyme concentration of the case"),
    ),
    "enzyme dose with a ranged initial substrate": (
        {"change": {"substrate_initial_concentration": {"value": "", "lower": "15", "upper": "25"}}},
        ("kinetics.csv", ROW["enzyme_dose"], "quantity", "needs an exact initial substrate concentration"),
    ),
    "enzyme dose in molar units": (
        {"change": {"enzyme_dose": {"units": "umol/g"}}},
        ("kinetics.csv", ROW["enzyme_dose"], "units", "must be an enzyme amount per dry substrate mass"),
    ),
    "dimensioned reactivity exponent": (
        {"change": {"reactivity_exponent": {"units": "g/L"}}},
        ("kinetics.csv", ROW["reactivity_exponent"], "units", "must be dimensionless"),
    ),
    "negative reactivity exponent": (
        {"change": {"reactivity_exponent": {"value": "-1"}}},
        ("kinetics.csv", ROW["reactivity_exponent"], "value", "must be nonnegative"),
    ),
    "surface-law quantity": (
        {"add": (_case_row("adsorption_constant", "0.1", "L/mg", evidence_type="estimate"),)},
        ("kinetics.csv", 12, "quantity", "an adsorption (Langmuir) constant"),
    ),
    "binding-capacity quantity": (
        {"add": (_case_row("binding_capacity", "10", "mg/g", evidence_type="estimate"),)},
        ("kinetics.csv", 12, "quantity", "no rate law of the user-data route reads it"),
    ),
}


@pytest.mark.parametrize("name", sorted(REFUSALS))
def test_refusals_in_kinetics_name_file_row_and_column(name: str, tmp_path: Path) -> None:
    edit, (file, row, column, fragment) = REFUSALS[name]
    issues = _issues(tmp_path, {"kinetics.csv": _edited_kinetics(**edit)})
    assert _has_issue(issues, file, row, column, fragment), issues


SUBSTRATE_REFUSALS: dict[str, tuple[str, tuple[str, int | None, str | None, str]]] = {
    "composite mixed solid": (
        _solid_row(physical_state="mixed_solid"),
        ("substrates.csv", 2, "physical_state", "a composite material"),
    ),
    "composite solid biomass": (
        _solid_row(physical_state="solid_biomass"),
        ("substrates.csv", 2, "physical_state", "composite substrates are refused"),
    ),
    "unknown physical state": (
        _solid_row(physical_state="unknown"),
        ("substrates.csv", 2, "physical_state", "supported states are dissolved or solid_polymer"),
    ),
    "molar yield on a solid": (
        _solid_row(yield_basis="mol/mol"),
        ("substrates.csv", 2, "yield_basis", "yield_basis must be 'g/g' for a solid_polymer substrate"),
    ),
    "missing amount basis on a solid": (
        _solid_row(amount_basis=""),
        ("substrates.csv", 2, "amount_basis", "amount_basis is blank"),
    ),
    "monomer amount basis on a solid": (
        _solid_row(amount_basis="monomer_equivalent"),
        ("substrates.csv", 2, "amount_basis", "must state amount_basis 'dry_mass'"),
    ),
    "surface-area column": (
        f"{SOLID_SUBSTRATE_HEADER},specific_surface_area\n{_solid_row().splitlines()[1]},12\n",
        ("substrates.csv", 1, "specific_surface_area", "is refused: no rate law of the user-data route reads it"),
    ),
    "binding-capacity column": (
        f"{SOLID_SUBSTRATE_HEADER},binding_capacity\n{_solid_row().splitlines()[1]},30\n",
        ("substrates.csv", 1, "binding_capacity", "an enzyme binding capacity"),
    ),
}


@pytest.mark.parametrize("name", sorted(SUBSTRATE_REFUSALS))
def test_refusals_in_substrates_name_file_row_and_column(name: str, tmp_path: Path) -> None:
    text, (file, row, column, fragment) = SUBSTRATE_REFUSALS[name]
    issues = _issues(tmp_path, {"substrates.csv": text})
    assert _has_issue(issues, file, row, column, fragment), issues


def test_dissolved_substrates_refuse_the_solid_only_quantities_and_bases(tmp_path: Path) -> None:
    case = "os3bglu6_source,beta_glucosidase,cellobiose,c30_ph5"
    kinetics = (LITERATURE / "kinetics.csv").read_text(encoding="utf-8") + (
        f"{case},reactivity_exponent,1,,,dimensionless,estimate,,stated,,\n"
        f"{case},enzyme_dose,1,,,mg/g,design,experimental design,stated,,\n"
    )
    issues = _issues(tmp_path / "quantities", {"kinetics.csv": kinetics}, source=LITERATURE)
    lines = len((LITERATURE / "kinetics.csv").read_text(encoding="utf-8").splitlines())
    assert _has_issue(issues, "kinetics.csv", lines + 1, "quantity", "reactivity_exponent applies only to a solid_polymer"), issues
    assert _has_issue(issues, "kinetics.csv", lines + 2, "quantity", "enzyme_dose is an enzyme amount per substrate mass"), issues

    substrates = (LITERATURE / "substrates.csv").read_text(encoding="utf-8").splitlines()
    header = f"{substrates[0]},amount_basis"
    rows = [f"{line},dry_mass" for line in substrates[1:]]
    issues = _issues(tmp_path / "basis", {"substrates.csv": "\n".join([header, *rows]) + "\n"}, source=LITERATURE)
    assert _has_issue(issues, "substrates.csv", 2, "amount_basis", "applies to solid_polymer substrates only"), issues


def test_a_ph_ionization_class_acting_on_a_solid_substrate_is_refused(tmp_path: Path) -> None:
    bgl1a = FIXTURES / "bgl1a_ph_ionization"
    substrates = (bgl1a / "substrates.csv").read_text(encoding="utf-8").splitlines()
    header = f"{substrates[0]},amount_basis"
    solid_row = (
        "solid_glucan,,Solid beta-glucan lot B,cellobiose_solid_test_class,solid_polymer,beta_1_4_glycosidic,"
        "solubilized_substrate_mass,1,g/g,stated,dry_mass"
    )
    # The registry beta-glucosidase class acts only on the cellobiose class; a user class is needed for the solid.
    classes = (
        "class_id,name,ec_number,target_bond_classes,compatible_substrate_classes,source\n"
        "glycosidase_like,glycosidase-like hydrolase,,beta_1_4_glycosidic,cellobiose;cellobiose_solid_test_class,stated\n"
    )
    kinetics = (bgl1a / "kinetics.csv").read_text(encoding="utf-8").replace(",beta_glucosidase,", ",glycosidase_like,")
    enzymes = "strain_id,enzyme_class,evidence,source\nbgl1a_source,glycosidase_like,activity assay,stated\n"
    issues = _issues(
        tmp_path,
        {
            "substrates.csv": "\n".join([header, *(f"{line}," for line in substrates[1:]), solid_row]) + "\n",
            "enzyme_classes.csv": classes,
            "enzymes.csv": enzymes,
            "kinetics.csv": kinetics,
        },
        source=bgl1a,
    )
    assert _has_issue(issues, "substrates.csv", 3, "physical_state", "uses the pH-ionization form in kinetics.csv"), issues


def test_time_courses_of_a_solid_substrate_are_refused(tmp_path: Path) -> None:
    timecourse = (
        "strain_id,enzyme_class,substrate_id,condition_id,observable,time,time_units,value,units,sd,replicates,source,method\n"
        f"{STRAIN},{CLASS},{SUBSTRATE},dose_5,substrate,0,hour,20,g/L,,,LN-8 p. 5,gravimetry\n"
    )
    issues = _issues(tmp_path, {"timecourse.csv": timecourse})
    assert _has_issue(issues, "timecourse.csv", 2, "substrate_id", "time courses of solid substrates are not compared"), issues


def test_assembly_refuses_a_solid_substrate_of_the_user_dataset(solid: UserDataset) -> None:
    with pytest.raises(UserTablesAssemblyError, match="assembled drafts cover dissolved substrates only"):
        assemble_user_tables(
            dataset_id="solid_assembly",
            fungus=STRAIN,
            substrates=[SUBSTRATE],
            conditions=[{"temperature": 29, "temperature_units": "degC", "ph": 5}],
            user_data=solid,
            registry=REGISTRY_INDEX,
        )


# ---------------------------------------------------------------------------
# (j) Registry record


def test_cellobiohydrolase_record_is_categorical_metadata_without_kinetics(base_registry: FungModRegistry) -> None:
    record = base_registry.enzyme_classes["cellobiohydrolase"]
    assert record.ec_number == "3.2.1.91"
    assert {"3.2.1.176", "EC 3.2.1.176"} <= set(record.aliases)
    assert "3.2.1.176" in record.notes and "reducing-end" in record.notes
    assert record.maturity == "literature_metadata"
    assert record.target_bond_classes == ("beta_1_4_glycosidic",)
    assert set(record.compatible_substrate_classes) == {"cellulose_particulate", "cellulose_film_generic"}
    assert record.compatible_processes == ("homogeneous_michaelis_menten",)
    source = record.provenance["source"]
    assert "EC 3.2.1.91" in source and "EC 3.2.1.176" in source and "ExplorEnz" in source
    assert "doi:10.1093/nar/gkab1045" in source and "GH6" in source and "GH7" in source
    assert not any(parameter.enzyme_class == "cellobiohydrolase" for parameter in base_registry.parameters.values())
    assert not any(item.enzyme_class == "cellobiohydrolase" for item in base_registry.process_compatibility.values())
    for absent in ("endoglucanase", "lytic_polysaccharide_monooxygenase"):
        assert absent not in base_registry.enzyme_classes


def test_both_cellobiohydrolase_ec_numbers_resolve_and_a_gh7_endoglucanase_disagrees(
    base_registry: FungModRegistry,
) -> None:
    """EC 3.2.1.91 and its reducing-end alias 3.2.1.176 name the record; GH7 with EC 3.2.1.4 is a disagreement."""

    tsv = (
        "Entry\tEC number\tCAZy\n"
        "X0SOLID1\t3.2.1.91\tGH6;\n"
        "X0SOLID2\t3.2.1.176\tGH7;\n"
        "X0SOLID3\t3.2.1.4\tGH7;\n"
        "X0SOLID4\t3.2.1.4\tGH5;\n"
    )
    resolution = resolve_uniprot_proteome(
        parse_uniprot_tsv(tsv, source="hand-written routing export"),
        capability_resolver=CapabilityResolver(
            family_map=CazymeFamilyMap.load(), registry_enzyme_classes=tuple(sorted(base_registry.enzyme_classes))
        ),
        registry=base_registry,
        organism="Synthetic format-fixture organism",
        proteome_source="hand-written routing export",
        annotation_tool="UniProt",
        annotation_tool_version="routing test",
        annotation_date="not recorded",
    )
    supports = {item.enzyme_class: dict(item.accessions_by_basis) for item in resolution.capabilities}
    assert supports["cellobiohydrolase"]["cazy_and_ec"] == ("X0SOLID1", "X0SOLID2")
    # GH5 and EC 3.2.1.4 name no class that carries an EC number, so they cannot disagree.
    assert supports["cellulase_generic"]["cazy"] == ("X0SOLID4",)
    (disagreement,) = resolution.disagreements
    assert (disagreement.accession, disagreement.contested_classes) == ("X0SOLID3", ("cellobiohydrolase",))

