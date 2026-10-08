"""SURFACE-001: the surface-catalysis registry assembler is template-driven and honest.

The assembler reads every label, text and its geometry from the case template
and its structural fields from the registry records. These tests pin the
assembled configs of the shipped BIO-001 case and the BIO-002 chain to their
digests at e97e8e6 (unchanged), pin the toy surface case's documented
differences field by field, refuse the removed fallbacks (missing geometry,
ambiguous bond class, missing mode metadata and the other template blocks),
and run a materially different, test-only, non-cellulose surface template in
exploratory and scientific mode.

Every record of ``_fixture_registry`` is a test-only, illustrative software
fixture (a polyamide-like film and a hydrolase acting on its amide bonds, with
the amount of repeat units in millimole, the enzyme in gram per litre and the
area in square centimetres); no value is a measurement.
"""

from __future__ import annotations

import csv
import hashlib
import shutil
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
import yaml

from fungal_model import VirtualExperiment
from fungal_model.core.units import Q_
from fungal_model.core.value_spec import ValueSpec
from fungal_model.registry import (
    CaseTemplateRecord,
    EnvironmentRecord,
    EnzymeClassRecord,
    FungModRegistry,
    FungusRecord,
    ParameterRecord,
    ProcessCompatibilityRecord,
    SubstrateRecord,
    load_registry,
)
from fungal_model.registry.records import (
    PARAMETER_ALLOWED_USE_EXPLORATORY,
    PARAMETER_ALLOWED_USE_SCIENTIFIC,
)
from fungal_model.screening import RegistryCaseBuildError, build_model_config_from_registry_case
from fungal_model.screening.case_builder import (
    SURFACE_CATALYSIS_REQUIRED_PROCESS_STATE_METADATA,
    build_registry_process_config_data,
    get_registry_process_assembler,
    select_registry_case_compatibility,
)
from fungal_model.screening.ensemble import _sample_role_records, resolve_screen_role_records, simulate_screen
from fungal_model.screening.modelability import assess_modelability
from fungal_model.workflows import run_configured_model


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"

BIO001 = ("generic_cellulase_source", "cellulose_film_generic", "bio001_cellulose_surface_pilot_environment")
BIO002 = ("generic_cellulase_source", "cellulose_film_generic", "sabiork_reaction_618_selected_conditions")
TOY = ("toy_fungus_alpha", "toy_cellulose_like_solid", "toy_lab_environment")
BIO001_TEMPLATE_ID = "bio001_cellulose_surface_catalysis_template"
TOY_TEMPLATE_ID = "toy_surface_catalysis_registry_template"

# sha256 of yaml.safe_dump(config, sort_keys=False), computed at e97e8e6 (before SURFACE-001).
DIGESTS_AT_E97E8E6 = {
    "bio001_exploratory": "cb118564fa4a1972f530541809be584ebe2f7308938a931f30137f235cdf0186",
    "bio002_chain_exploratory": "84883c4d4d75d168209038c318de3d58dfb4c3d636f926c637cbfbe14414dca0",
    "bio002_chain_toy": "53d6ade969b34fb597ecadc542ec95fe506c7fbe2d24b7c52a50aef9e3c944bc",
    "toy_surface_toy": "f212fc15baebadc610823c959f52051ef58239233dca74d3f1b039488a56f707",
    "toy_surface_exploratory": "ded9795230e2b5fdb36c7c8c4fa3cf34158357368c338a8d2ddd2450f71592ba",
}
# The toy surface case after SURFACE-001 (the documented differences of ``_toy_case_as_at_e97e8e6``).
TOY_DIGESTS_AFTER_SURFACE_001 = {
    "toy_surface_toy": "7ce1c0072e9cb5072137cb8edf6fb2b68a0e4f334b3e315f8c214f5fdeaac539",
    "toy_surface_exploratory": "ffc84a9d721706e94d03ab0ceba15aa3c628a2fbcd07269c9f9b4ee8ad09f045",
}


class _LowerBound:
    """A stand-in random generator: every ranged record is taken at its lower bound."""

    def uniform(self, low: float, high: float) -> float:
        del high
        return low


def _digest(data: Any) -> str:
    return hashlib.sha256(yaml.safe_dump(data, sort_keys=False).encode("utf-8")).hexdigest()


def _screen_config(registry: FungModRegistry, case: tuple[str, str, str]) -> dict[str, Any]:
    """The exploratory screen's config of a case with every ranged record at its lower bound."""

    fungus, substrate, environment = case
    report = assess_modelability(
        fungus_id=fungus, substrate_id=substrate, environment_id=environment, registry=registry, mode="exploratory"
    )
    compatibility = select_registry_case_compatibility(
        registry=registry, fungus_id=fungus, substrate_id=substrate, report=report
    )
    records = resolve_screen_role_records(
        registry=registry,
        compatibility=compatibility,
        fungus_id=fungus,
        substrate_id=substrate,
        environment_id=environment,
        mode="exploratory",
    )
    sampled = _sample_role_records(records, rng=_LowerBound(), sample_index=0)  # type: ignore[arg-type]
    return build_registry_process_config_data(
        registry=registry,
        compatibility=compatibility,
        fungus_id=fungus,
        substrate_id=substrate,
        environment_id=environment,
        parameter_records=sampled,
        output_directory="<OUTPUT_ROOT>",
    )


def _deterministic_config(registry: FungModRegistry, case: tuple[str, str, str], mode: str = "toy") -> dict[str, Any]:
    fungus, substrate, environment = case
    return build_model_config_from_registry_case(
        fungus_id=fungus,
        substrate_id=substrate,
        environment_id=environment,
        registry=registry,
        mode=mode,  # type: ignore[arg-type]
        output_directory="<OUTPUT_ROOT>",
    ).to_dict()


def _toy_registry(tmp_path: Path) -> FungModRegistry:
    """The shipped registry with the toy compatibility bound to the exact toy adsorption record."""

    destination = tmp_path / "data_registry"
    shutil.copytree(ROOT / "data_registry", destination)
    path = destination / "processes" / "process_compatibility.yml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    records = cast(list[dict[str, Any]], data["records"])
    assert records[0]["record_id"] == "toy_cellulase_on_toy_cellulose_like_surface"
    records[0]["required_parameters"] = ["k_surface_exact", "k_ads_exact", "A_surface_exact"]
    records[0]["parameter_roles"] = {
        "surface_rate_constant": "k_surface_exact",
        "adsorption_constant": "k_ads_exact",
        "accessible_surface_area": "A_surface_exact",
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return load_registry(destination / "registry_index.yml")


def _with_template_metadata(
    registry: FungModRegistry,
    template_id: str,
    change: Any,
    **template_fields: Any,
) -> FungModRegistry:
    """A copy of ``registry`` whose template ``template_id`` has ``change`` applied to its process-state metadata."""

    template = registry.case_templates[template_id]
    metadata = deepcopy(dict(template.process_state_metadata))
    change(metadata)
    changed = replace(template, process_state_metadata=metadata, **template_fields)
    return replace(registry, case_templates={**registry.case_templates, template_id: changed})


# ---------------------------------------------------------------------------
# Parity with e97e8e6


def test_bio001_and_bio002_assemble_byte_identically_to_e97e8e6() -> None:
    """The BIO-001 text now read from its template is the text the assembler wrote before, byte for byte."""

    registry = load_registry(REGISTRY_INDEX)
    assert _digest(_screen_config(registry, BIO001)) == DIGESTS_AT_E97E8E6["bio001_exploratory"]
    assert _digest(_screen_config(registry, BIO002)) == DIGESTS_AT_E97E8E6["bio002_chain_exploratory"]
    assert _digest(_deterministic_config(registry, BIO002)) == DIGESTS_AT_E97E8E6["bio002_chain_toy"]


def _toy_case_as_at_e97e8e6(data: dict[str, Any]) -> dict[str, Any]:
    """Undo, field by field, the intended differences of the toy surface case.

    Each difference is a field the removed toy branch wrote from code; the
    template-driven assembler writes the same structure for every template:

    1. ``provenance``: the template's ``config_provenance`` is followed by the
       case identity, ``parameter_record_ids``, ``parameter_value_sources`` and
       its ``notes`` last (the toy branch put ``notes`` after
       ``confidence_level`` and named no records);
    2. ``degradation_products[*].source``: the config provenance source, as for
       BIO-001 (the toy branch wrote none);
    3. the enzyme's ``target_substrate_names``: the case substrate's name (the
       toy branch wrote an empty list);
    4. the enzyme provenance ``measurement_method``: the config provenance's
       (the toy branch wrote "defined benchmark metadata");
    5. parameter ``notes``: the record's notes and role (the toy branch
       appended "Toy/development only."; the toy records' own notes already say
       so).
    """

    data = deepcopy(data)
    provenance = data["provenance"]
    notes = provenance.pop("notes")
    del provenance["parameter_record_ids"], provenance["parameter_value_sources"]
    reordered: dict[str, Any] = {}
    for key, value in provenance.items():
        reordered[key] = value
        if key == "confidence_level":
            reordered["notes"] = notes
    data["provenance"] = reordered
    for product in data["entities"]["substrates"][0]["data"]["degradation_products"]:
        del product["source"]
    enzyme = data["entities"]["enzymes"][0]["data"]
    enzyme["target_substrate_names"] = []
    enzyme["provenance"]["measurement_method"] = "defined benchmark metadata"
    for entry in data["parameters"][0]["parameters"]:
        entry["notes"] = f"{entry['notes']} Toy/development only."
    return data


def test_toy_surface_case_differs_from_e97e8e6_only_in_the_documented_fields(tmp_path: Path) -> None:
    registry = _toy_registry(tmp_path)
    configs = {
        "toy_surface_toy": _deterministic_config(registry, TOY),
        "toy_surface_exploratory": _screen_config(registry, TOY),
    }
    for name, data in configs.items():
        assert _digest(data) == TOY_DIGESTS_AFTER_SURFACE_001[name], name
        assert _digest(_toy_case_as_at_e97e8e6(data)) == DIGESTS_AT_E97E8E6[name], name


def test_toy_surface_case_simulates_as_before(tmp_path: Path) -> None:
    """The toy case's values are unchanged: k_s * theta * A = 1e-6 kg/m2/s * 0.5 * 0.2 m2 over 20 s."""

    data = _deterministic_config(_toy_registry(tmp_path), TOY)
    data["outputs"]["directory"] = str(tmp_path / "bundle")
    path = tmp_path / "toy.yml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    result = run_configured_model(path, output_dir=tmp_path / "bundle")

    substrate = result.state("solid_substrate_amount").to("kilogram").magnitude
    product = result.state("released_product_amount").to("kilogram").magnitude
    expected = 1.0e-6 * (1.0 * 1.0 / (1.0 + 1.0 * 1.0)) * 0.2 * 20.0
    assert substrate[0] - substrate[-1] == pytest.approx(expected, rel=1e-9)
    assert product[-1] == pytest.approx(expected, rel=1e-9)
    assert data["entities"]["geometry"]["data"]["name"] == "toy registry well-mixed 100 mL"


def test_shipped_surface_templates_carry_the_moved_text() -> None:
    """BIO-001 labels, provenance and validity text live in its template, not in code."""

    registry = load_registry(REGISTRY_INDEX)
    metadata = registry.case_templates[BIO001_TEMPLATE_ID].process_state_metadata
    assert metadata["config_provenance"]["bio_milestone"] == "BIO-001"
    assert metadata["enzyme_entity"]["name"] == "Generic cellulase-like enzyme source"
    assert metadata["parameter_entries"]["validity_range"] == "BIO-001 cellulose surface-degradation pilot only"
    assert metadata["product_map_name"] == "BIO-001 cellulose soluble product release map"
    config = _screen_config(registry, BIO001)
    assert config["provenance"]["notes"] == metadata["config_provenance"]["notes"]
    assert config["entities"]["enzymes"][0]["data"]["name"] == metadata["enzyme_entity"]["name"]
    for template_id in (BIO001_TEMPLATE_ID, TOY_TEMPLATE_ID):
        template = registry.case_templates[template_id]
        assert "geometry" in template.process_state_metadata, template_id
        for field in SURFACE_CATALYSIS_REQUIRED_PROCESS_STATE_METADATA:
            assert template.process_state_metadata[field], (template_id, field)


def test_surface_assembler_advertises_template_modes() -> None:
    surface = get_registry_process_assembler("surface_catalysis")
    assert surface is not None
    assert surface.supported_request_modes == ("toy", "scientific")
    assert surface.enforce_template_mode_match
    assert surface.required_process_state_metadata == SURFACE_CATALYSIS_REQUIRED_PROCESS_STATE_METADATA


# ---------------------------------------------------------------------------
# Refusals of the removed fallbacks


def test_missing_geometry_is_refused_and_no_geometry_is_assumed(tmp_path: Path) -> None:
    registry = _with_template_metadata(_toy_registry(tmp_path), TOY_TEMPLATE_ID, lambda metadata: metadata.pop("geometry"))

    with pytest.raises(RegistryCaseBuildError, match="declares no geometry.*reads no geometry"):
        _deterministic_config(registry, TOY)


def test_explicit_null_geometry_assembles_without_a_geometry_entity(tmp_path: Path) -> None:
    registry = _with_template_metadata(
        _toy_registry(tmp_path), TOY_TEMPLATE_ID, lambda metadata: metadata.update({"geometry": None})
    )

    data = _deterministic_config(registry, TOY)

    assert "geometry" not in data["entities"]
    assert list(data["entities"]) == ["substrates", "enzymes", "product_maps"]


@pytest.mark.parametrize(
    ("geometry", "message"),
    [
        ({}, "well-mixed geometry mapping or null"),
        ("100 mL", "well-mixed geometry mapping or null"),
        ({"kind": "geometry", "name": "film", "geometry_type": "film_1d"}, "is not 'well_mixed'"),
    ],
)
def test_malformed_geometry_is_refused(tmp_path: Path, geometry: Any, message: str) -> None:
    registry = _with_template_metadata(
        _toy_registry(tmp_path), TOY_TEMPLATE_ID, lambda metadata: metadata.update({"geometry": geometry})
    )

    with pytest.raises(RegistryCaseBuildError, match=message):
        _deterministic_config(registry, TOY)


@pytest.mark.parametrize("field", SURFACE_CATALYSIS_REQUIRED_PROCESS_STATE_METADATA)
def test_missing_mode_and_label_metadata_is_refused(tmp_path: Path, field: str) -> None:
    registry = _with_template_metadata(_toy_registry(tmp_path), TOY_TEMPLATE_ID, lambda metadata: metadata.pop(field))

    with pytest.raises(RegistryCaseBuildError, match=f"missing explicit process-state metadata.*{field}"):
        _deterministic_config(registry, TOY)


def test_missing_config_mode_is_refused_on_the_screen_path_too() -> None:
    registry = _with_template_metadata(
        load_registry(REGISTRY_INDEX), BIO001_TEMPLATE_ID, lambda metadata: metadata.pop("config_mode")
    )

    with pytest.raises(RegistryCaseBuildError, match="missing explicit process-state metadata.*config_mode"):
        _screen_config(registry, BIO001)


def test_unknown_config_mode_is_refused() -> None:
    registry = _with_template_metadata(
        load_registry(REGISTRY_INDEX), BIO001_TEMPLATE_ID, lambda metadata: metadata.update({"config_mode": "validated"})
    )

    with pytest.raises(RegistryCaseBuildError, match="config_mode 'validated' must be one of"):
        _screen_config(registry, BIO001)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda metadata: metadata.pop("config_provenance"), "requires a 'config_provenance' mapping"),
        (lambda metadata: metadata["config_provenance"].pop("validity_range"), "config_provenance requires.*validity_range"),
        (lambda metadata: metadata["config_provenance"].update({"notes": " padded"}), "config_provenance requires.*notes"),
        (
            lambda metadata: metadata["config_provenance"].update({"registry_id": "elsewhere"}),
            "may not state assembler-written field.*registry_id",
        ),
        (lambda metadata: metadata.pop("substrate_entity"), "requires a 'substrate_entity' mapping"),
        (lambda metadata: metadata["substrate_entity"].pop("product_notes"), "substrate_entity requires.*product_notes"),
        (lambda metadata: metadata["substrate_entity"].update({"crystallinity": "high"}), "unsupported field.*crystallinity"),
        (lambda metadata: metadata.pop("enzyme_entity"), "requires an 'enzyme_entity' mapping"),
        (lambda metadata: metadata["enzyme_entity"].update({"validity_labels": []}), "validity_labels must be a nonempty"),
        (lambda metadata: metadata["enzyme_entity"].pop("name"), "enzyme_entity requires.*name"),
        (lambda metadata: metadata.pop("parameter_entries"), "requires a 'parameter_entries' mapping"),
        (
            lambda metadata: metadata["parameter_entries"].pop("measurement_method"),
            "parameter_entries requires.*measurement_method",
        ),
        (lambda metadata: metadata.update({"config_name": "{organism}"}), "config_name may use only the fields"),
    ],
)
def test_missing_template_text_is_refused_not_defaulted(change: Any, message: str) -> None:
    registry = _with_template_metadata(load_registry(REGISTRY_INDEX), BIO001_TEMPLATE_ID, change)

    with pytest.raises(RegistryCaseBuildError, match=message):
        _screen_config(registry, BIO001)


def test_template_without_limitations_is_refused() -> None:
    registry = _with_template_metadata(
        load_registry(REGISTRY_INDEX), BIO001_TEMPLATE_ID, lambda metadata: None, limitations=()
    )

    with pytest.raises(RegistryCaseBuildError, match="states no limitations"):
        _screen_config(registry, BIO001)


def test_declared_bond_type_must_be_shared_by_substrate_and_enzyme_class() -> None:
    registry = _with_template_metadata(
        load_registry(REGISTRY_INDEX), BIO001_TEMPLATE_ID, lambda metadata: metadata.update({"bond_type": "ester_bond"})
    )

    with pytest.raises(RegistryCaseBuildError, match="bond_type 'ester_bond' is not a bond class shared"):
        _screen_config(registry, BIO001)


def test_ambiguous_bond_class_is_refused_never_chosen() -> None:
    """A substrate with two bond classes that the enzyme class both targets and the template names neither."""

    registry = _fixture_registry(mode="exploratory", enzyme_bonds=(AMIDE, ESTER))

    with pytest.raises(RegistryCaseBuildError, match="share 2 bond classes .*never chosen: declare bond_type"):
        _screen_config(registry, FIXTURE_CASE)


def test_no_shared_bond_class_is_refused() -> None:
    registry = _fixture_registry(mode="exploratory")
    enzyme_class = registry.enzyme_classes[FIXTURE_ENZYME_CLASS]
    registry = replace(
        registry,
        enzyme_classes={FIXTURE_ENZYME_CLASS: replace(enzyme_class, target_bond_classes=("fixture_other_bond",))},
    )
    compatibility = registry.process_compatibility[FIXTURE_COMPATIBILITY]
    records = {record.parameter_symbol: record for record in registry.parameters.values()}
    roles = {role: records[symbol] for role, symbol in compatibility.parameter_roles.items()}

    with pytest.raises(RegistryCaseBuildError, match="share no bond class"):
        build_registry_process_config_data(
            registry=registry,
            compatibility=compatibility,
            fungus_id=FIXTURE_CASE[0],
            substrate_id=FIXTURE_CASE[1],
            environment_id=FIXTURE_CASE[2],
            parameter_records=_sample_role_records(roles, rng=_LowerBound(), sample_index=0),  # type: ignore[arg-type]
            output_directory=None,
        )


def test_dissolved_substrate_is_refused_for_surface_catalysis() -> None:
    registry = _fixture_registry(mode="exploratory")
    substrate = registry.substrates[FIXTURE_SUBSTRATE]
    registry = replace(registry, substrates={FIXTURE_SUBSTRATE: replace(substrate, physical_state="dissolved")})

    with pytest.raises(RegistryCaseBuildError, match="surface catalysis acts on a substrate the record declares solid"):
        _screen_config(registry, FIXTURE_CASE)


def test_toy_template_stays_toy(tmp_path: Path) -> None:
    """A scientific request on the toy template is refused by its config_mode, even with scientific-grade records."""

    registry = _toy_registry(tmp_path)
    promoted = {
        record_id: replace(record, maturity="illustrative_fixture", allowed_use=PARAMETER_ALLOWED_USE_SCIENTIFIC)
        for record_id, record in registry.parameters.items()
        if record.fungus_id == TOY[0] and record.value.is_exact
    }
    registry = replace(registry, parameters={**registry.parameters, **promoted})

    with pytest.raises(RegistryCaseBuildError, match=f"mode 'scientific' disagrees with case template '{TOY_TEMPLATE_ID}'"):
        _deterministic_config(registry, TOY, mode="scientific")


# ---------------------------------------------------------------------------
# A materially different, test-only, non-cellulose surface template

AMIDE = "fixture_amide_bond"
ESTER = "fixture_ester_bond"
FIXTURE_FUNGUS = "fixture_surface_source"
FIXTURE_ENZYME_CLASS = "fixture_polyamide_surface_hydrolase"
FIXTURE_SUBSTRATE = "fixture_polyamide_like_film"
FIXTURE_SUBSTRATE_CLASS = "fixture_polyamide_like"
FIXTURE_ENVIRONMENT = "fixture_surface_environment"
FIXTURE_TEMPLATE = "fixture_polyamide_surface_template"
FIXTURE_COMPATIBILITY = "fixture_polyamide_surface_compatibility"
FIXTURE_CASE = (FIXTURE_FUNGUS, FIXTURE_SUBSTRATE, FIXTURE_ENVIRONMENT)
FIXTURE_SOURCE = "SURFACE-001 test-only software verification fixture; illustrative values, not measurements."

# role: (symbol, exploratory range, scientific exact value, units)
FIXTURE_PARAMETERS: dict[str, tuple[str, tuple[float, float], float, str]] = {
    "surface_rate_constant": ("k_s_fixture_film", (2.0, 4.0), 3.0, "millimole / meter ** 2 / hour"),
    "adsorption_constant": ("K_ads_fixture_film", (0.5, 2.0), 1.0, "liter / gram"),
    "accessible_surface_area": ("A_fixture_film", (40.0, 60.0), 50.0, "centimeter ** 2"),
    "substrate_initial_amount": ("S0_fixture_film", (0.8, 1.2), 1.0, "millimole"),
    "enzyme_initial_concentration": ("E0_fixture_hydrolase", (0.05, 0.2), 0.1, "gram / liter"),
}
FIXTURE_RELEASE_YIELD = 0.5  # one released dimer per two repeat units (illustrative)
FIXTURE_HOURS = 24.0


def _fixture_registry(*, mode: str, enzyme_bonds: tuple[str, ...] = (AMIDE,)) -> FungModRegistry:
    """A test-only registry: a hydrolase on the amide bonds of a polyamide-like film, in other units than BIO-001."""

    provenance = {
        "source": FIXTURE_SOURCE,
        "confidence_level": "illustrative_fixture",
        "notes": "Test-only fixture for SURFACE-001; not literature data and not a biological claim.",
    }
    scientific = mode == "scientific"
    parameters = tuple(
        ParameterRecord(
            record_id=f"{symbol}_record",
            name=f"Illustrative {role.replace('_', ' ')} of the fixture film",
            maturity="illustrative_fixture" if scientific else "exploratory_prior",
            provenance=provenance,
            notes="Test-only illustrative value; not a measurement.",
            parameter_symbol=symbol,
            process_type="surface_catalysis",
            enzyme_class=FIXTURE_ENZYME_CLASS,
            substrate_class=FIXTURE_SUBSTRATE_CLASS,
            fungus_id=FIXTURE_FUNGUS,
            substrate_id=FIXTURE_SUBSTRATE,
            environment_id=FIXTURE_ENVIRONMENT,
            value=(
                ValueSpec(kind="exact", value=exact, units=units, source=FIXTURE_SOURCE, confidence_level="illustrative_fixture")
                if scientific
                else ValueSpec(
                    kind="range",
                    lower=bounds[0],
                    upper=bounds[1],
                    units=units,
                    source=FIXTURE_SOURCE,
                    confidence_level="illustrative_fixture",
                )
            ),
            range_scope="SURFACE-001 software verification",
            range_interpretation="illustrative bounds only",
            allowed_use=PARAMETER_ALLOWED_USE_SCIENTIFIC if scientific else PARAMETER_ALLOWED_USE_EXPLORATORY,
        )
        for role, (symbol, bounds, exact, units) in FIXTURE_PARAMETERS.items()
    )
    template = CaseTemplateRecord(
        record_id=FIXTURE_TEMPLATE,
        name="Test-only polyamide-like film surface-catalysis template",
        maturity="illustrative_fixture",
        provenance=provenance,
        notes="Test-only template proving a non-cellulose surface case assembles from its template alone.",
        case_template_id=FIXTURE_TEMPLATE,
        process_type="surface_catalysis",
        state_roles={
            "substrate": "film_repeat_units_remaining",
            "product": "released_dimer",
            "catalyst": "free_hydrolase",
        },
        initial_state_mapping={
            "substrate": {"parameter_role": "substrate_initial_amount", "units_from_role": "substrate_initial_amount"},
            "product": {"value": 0.0, "units_from_role": "substrate_initial_amount"},
            "catalyst": {
                "parameter_role": "enzyme_initial_concentration",
                "units_from_role": "enzyme_initial_concentration",
            },
        },
        product_map={
            "id": "fixture_film_dimer_release",
            "product_map_type": "stoichiometric",
            "substrate_state_role": "substrate",
            "product_state_role": "product",
            "stoichiometric_yield": FIXTURE_RELEASE_YIELD,
            "notes": "Illustrative: one dimer per two repeat units.",
        },
        stoichiometric_yields={"product": FIXTURE_RELEASE_YIELD},
        time_grid={"start": 0.0, "stop": FIXTURE_HOURS, "points": 25, "units": "hour"},
        observable_roles=("substrate", "product", "catalyst"),
        output_state_roles={
            "substrate": "film_repeat_units_remaining",
            "product": "released_dimer",
            "catalyst": "free_hydrolase",
        },
        process_state_metadata={
            "config_name": "Test-only polyamide-like film surface case {fungus_id} on {substrate_id}",
            "config_mode": mode,
            "config_maturity": mode,
            "accessible_site_pool": "accessible amide bonds of the fixture film surface",
            "product_map_name": "Fixture film repeat units to released dimer",
            # No vessel is claimed: the surface law reads no geometry.
            "geometry": None,
            "config_provenance": {
                "source": FIXTURE_SOURCE,
                "measurement_method": "registry assembly from illustrative fixture values",
                "confidence_level": "illustrative_fixture",
                "validity_range": "SURFACE-001 software verification only",
                "notes": "Test-only polyamide-like surface case; values are illustrative, not measurements.",
            },
            "substrate_entity": {
                "notes": "Test-only polyamide-like film; no crystallinity, porosity or morphology is modelled.",
                "product_notes": "Illustrative released-dimer pool; not a speciation model.",
                "default_degradation_model": "heterogeneous_surface",
            },
            "enzyme_entity": {
                "name": "Fixture polyamide surface hydrolase",
                "validity_labels": ["illustrative_fixture", "surface_catalysis"],
                "notes": "Test-only hydrolase acting on amide bonds; no secretion or inactivation is modelled.",
            },
            "parameter_entries": {
                "measurement_method": "illustrative fixture value",
                "validity_range": "SURFACE-001 software verification only",
            },
        },
        limitations=(
            "Zero order in the substrate until it is exhausted: the accessible area is a constant parameter.",
            "Equilibrium Langmuir coverage of the free enzyme; binding does not deplete the free enzyme.",
        ),
        validity_notes=("Test-only software verification fixture.",),
    )
    compatibility = ProcessCompatibilityRecord(
        record_id=FIXTURE_COMPATIBILITY,
        name="Fixture polyamide surface hydrolase compatibility",
        maturity="illustrative_fixture",
        provenance=provenance,
        notes="Test-only compatibility.",
        enzyme_class=FIXTURE_ENZYME_CLASS,
        substrate_class=FIXTURE_SUBSTRATE_CLASS,
        required_bond_classes=enzyme_bonds,
        process_type="surface_catalysis",
        required_parameters=tuple(symbol for symbol, _, _, _ in FIXTURE_PARAMETERS.values()),
        parameter_roles={role: symbol for role, (symbol, _, _, _) in FIXTURE_PARAMETERS.items()},
        product_map_required=True,
        case_template_id=FIXTURE_TEMPLATE,
    )
    condition = ValueSpec(kind="exact", value=303.15, units="kelvin", source=FIXTURE_SOURCE, confidence_level="illustrative_fixture")
    return FungModRegistry.build(
        registry_id="surface001_fixture_registry",
        version="1.0.0",
        maturity="illustrative_fixture",
        provenance=provenance,
        fungi=(
            FungusRecord(
                record_id=FIXTURE_FUNGUS,
                name="Fixture surface enzyme source",
                maturity="illustrative_fixture",
                provenance=provenance,
                notes="Test-only enzyme source; not an organism claim.",
                enzyme_classes=(FIXTURE_ENZYME_CLASS,),
            ),
        ),
        enzyme_classes=(
            EnzymeClassRecord(
                record_id=FIXTURE_ENZYME_CLASS,
                name="Fixture polyamide surface hydrolase class",
                maturity="illustrative_fixture",
                provenance=provenance,
                notes="Test-only enzyme class.",
                target_bond_classes=enzyme_bonds,
                compatible_substrate_classes=(FIXTURE_SUBSTRATE_CLASS,),
                compatible_processes=("surface_catalysis",),
            ),
        ),
        substrates=(
            SubstrateRecord(
                record_id=FIXTURE_SUBSTRATE,
                name="Test-only polyamide-like film",
                maturity="illustrative_fixture",
                provenance=provenance,
                notes="Test-only solid film with amide and ester bonds.",
                substrate_class=FIXTURE_SUBSTRATE_CLASS,
                physical_state="solid_polymer",
                bond_classes=(AMIDE, ESTER),
                products=("fixture_released_dimer",),
            ),
        ),
        environments=(
            EnvironmentRecord(
                record_id=FIXTURE_ENVIRONMENT,
                name="Fixture surface environment",
                maturity="illustrative_fixture",
                provenance=provenance,
                notes="Test-only condition.",
                conditions={"temperature": condition},
            ),
        ),
        process_compatibility=(compatibility,),
        parameters=parameters,
        case_templates=(template,),
    )


def _expected_consumption(values: dict[str, Any]) -> float:
    """Repeat units consumed over the time grid, in millimole: k_s * theta * A * t (no depletion in range)."""

    coverage = (values["K_ads_fixture_film"] * values["E0_fixture_hydrolase"]).to("dimensionless").magnitude
    theta = coverage / (1.0 + coverage)
    rate = values["k_s_fixture_film"] * theta * values["A_fixture_film"]
    return float((rate * Q_(FIXTURE_HOURS, "hour")).to("millimole").magnitude)


def _config_values(config: dict[str, Any]) -> dict[str, Any]:
    return {
        entry["symbol"]: Q_(float(entry["value"]), entry["units"])
        for entry in config["parameters"][0]["parameters"]
    }


def test_non_cellulose_surface_template_runs_in_exploratory_mode(tmp_path: Path) -> None:
    registry = _fixture_registry(mode="exploratory")

    result = simulate_screen(
        fungus_ids=[FIXTURE_FUNGUS],
        substrate_ids=[FIXTURE_SUBSTRATE],
        environment_ids=[FIXTURE_ENVIRONMENT],
        registry=registry,
        n_samples=3,
        seed=11,
        output_dir=tmp_path / "screen",
        mode="exploratory",
    )

    (case,) = result.case_results
    assert case.process_type == "surface_catalysis"
    assert len(case.samples) == 3 and not case.sample_failures
    for sample in case.samples:
        assert sample.validation_passed
        config = yaml.safe_load(Path(sample.config_path).read_text(encoding="utf-8"))
        assert config["mode"] == "exploratory"
        assert "geometry" not in config["entities"]
        states = config["processes"][0]["states"]
        # The bond class is the one the film carries and the hydrolase targets; the ester bond is not chosen.
        assert states["bond_type"] == AMIDE
        assert states["accessible_site_pool"] == "accessible amide bonds of the fixture film surface"
        assert config["entities"]["enzymes"][0]["data"]["name"] == "Fixture polyamide surface hydrolase"
        assert config["provenance"]["source"] == FIXTURE_SOURCE
        assert config["provenance"]["parameter_record_ids"]["surface_rate_constant"].startswith("k_s_fixture_film_record")
        assert config["entities"]["product_maps"][0]["data"]["products"] == {"released_dimer": FIXTURE_RELEASE_YIELD}
        values = _config_values(config)
        consumed = _expected_consumption(values)
        initial = values["S0_fixture_film"].to("millimole").magnitude
        assert 0.0 < consumed < initial
        remaining = Q_(
            sample.final_states["film_repeat_units_remaining"]["value"],
            sample.final_states["film_repeat_units_remaining"]["units"],
        ).to("millimole").magnitude
        released = Q_(
            sample.final_states["released_dimer"]["value"], sample.final_states["released_dimer"]["units"]
        ).to("millimole").magnitude
        assert initial - remaining == pytest.approx(consumed, rel=1e-6)
        assert released == pytest.approx(FIXTURE_RELEASE_YIELD * consumed, rel=1e-6)


def test_non_cellulose_surface_trajectory_is_linear_in_time(tmp_path: Path) -> None:
    """Zero order in the substrate: the stated limitation, visible in the trajectory."""

    registry = _fixture_registry(mode="scientific")
    data = _deterministic_config(registry, FIXTURE_CASE, mode="scientific")
    data["outputs"]["directory"] = str(tmp_path / "bundle")
    path = tmp_path / "fixture.yml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    result = run_configured_model(path, output_dir=tmp_path / "bundle")

    hours = result.time.to("hour").magnitude
    remaining = result.state("film_repeat_units_remaining").to("millimole").magnitude
    consumed = _expected_consumption(_config_values(data))
    np.testing.assert_allclose(remaining, 1.0 - consumed * hours / FIXTURE_HOURS, rtol=1e-9)


def test_non_cellulose_surface_template_reaches_scientific_mode_only_with_scientific_records(tmp_path: Path) -> None:
    registry = _fixture_registry(mode="scientific")

    data = _deterministic_config(registry, FIXTURE_CASE, mode="scientific")
    assert data["mode"] == "scientific"
    assert data["maturity"] == "scientific"
    data["outputs"]["directory"] = str(tmp_path / "bundle")
    path = tmp_path / "scientific.yml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    result = run_configured_model(path, output_dir=tmp_path / "bundle")
    report = result.validation_report()
    assert report and all(item["passed"] for item in report)

    # A toy request on a scientific template is refused by the template's mode.
    with pytest.raises(RegistryCaseBuildError, match="mode 'toy' disagrees with case template .*'scientific'"):
        _deterministic_config(registry, FIXTURE_CASE, mode="toy")

    # One exploratory record bound to the scientific template is refused at assembly, whatever the caller.
    compatibility = registry.process_compatibility[FIXTURE_COMPATIBILITY]
    records = {record.parameter_symbol: record for record in registry.parameters.values()}
    roles = {role: records[symbol] for role, symbol in compatibility.parameter_roles.items()}
    roles["adsorption_constant"] = replace(
        roles["adsorption_constant"], maturity="exploratory_prior", allowed_use=PARAMETER_ALLOWED_USE_EXPLORATORY
    )
    with pytest.raises(RegistryCaseBuildError, match="not every bound record is exact and scientific-grade"):
        build_registry_process_config_data(
            registry=registry,
            compatibility=compatibility,
            fungus_id=FIXTURE_FUNGUS,
            substrate_id=FIXTURE_SUBSTRATE,
            environment_id=FIXTURE_ENVIRONMENT,
            parameter_records=roles,
            output_directory=None,
        )


def test_scientific_surface_case_runs_through_the_virtual_experiment_api(tmp_path: Path) -> None:
    study = VirtualExperiment.from_registry(
        fungi=FIXTURE_FUNGUS,
        substrates=FIXTURE_SUBSTRATE,
        environments=FIXTURE_ENVIRONMENT,
        registry=_fixture_registry(mode="scientific"),
    )

    result = study.simulate(mode="scientific", output_dir=tmp_path / "study", quicklook=False)

    assert result.screen_result.mode == "scientific"
    (case,) = result.screen_result.case_results
    assert case.process_type == "surface_catalysis" and len(case.samples) == 1
    with (tmp_path / "study" / "case_summary.csv").open(encoding="utf-8", newline="") as handle:
        (row,) = list(csv.DictReader(handle))
    assert (row["process_type"], row["modelability_status"], row["case_status"]) == (
        "surface_catalysis",
        "modelable",
        "simulated",
    )


def test_exploratory_fixture_is_not_modelable_in_scientific_mode() -> None:
    registry = _fixture_registry(mode="exploratory")

    with pytest.raises(RegistryCaseBuildError, match="modelability status"):
        _deterministic_config(registry, FIXTURE_CASE, mode="scientific")
