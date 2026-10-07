"""One compatibility record per case, from preflight to tables (FIX-SELECT-001).

When a fungus lists several enzyme classes that act on one substrate, the
modelability preflight evaluates every compatible process record and selects
one. Config assembly, the exploratory and scientific screens and the result
tables must build the case from exactly that record, whatever order the
classes are listed in. Every record built here is a labelled software-test
fixture: the values are illustrative, not measurements or literature data.
"""

from __future__ import annotations

import csv
import itertools
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

import pytest
import yaml

from fungal_model import VirtualExperiment, load_user_dataset
from fungal_model.api.result_tables import write_standard_tables
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
    PARAMETER_ALLOWED_USE_GAP_ANALYSIS_ONLY,
    PARAMETER_ALLOWED_USE_SCIENTIFIC,
)
from fungal_model.screening import (
    ModelabilityReport,
    RegistryCaseBuildError,
    assess_modelability,
    build_model_config_from_registry_case,
)
from fungal_model.screening.case_builder import select_registry_case_compatibility

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"
ESTERASE_FIXTURE = ROOT / "tests" / "fixtures" / "user_data" / "esterase_case"

PROCESS_TYPE = "homogeneous_michaelis_menten"
FUNGUS_ID = "test_only_two_class_source"
SUBSTRATE_ID = "test_only_dissolved_ester"
SUBSTRATE_CLASS = "test_only_ester_class"
BOND_CLASS = "test_only_ester_bond"
ENVIRONMENT_ID = "test_only_assay_environment"
CLASS_A = "test_only_esterase_a"
CLASS_B = "test_only_esterase_b"
TEST_SOURCE = "FungMod FIX-SELECT-001 software test fixture; illustrative values, not measurements"
TEST_PROVENANCE = {
    "source": TEST_SOURCE,
    "confidence_level": "testing",
    "notes": "Test-only record for case class selection; not scientific data.",
}
ROLES = ("km", "kcat", "substrate_initial_concentration", "enzyme_initial_concentration")
UNITS = {
    "km": "mM",
    "kcat": "1 / second",
    "substrate_initial_concentration": "mM",
    "enzyme_initial_concentration": "mM",
}
# Class A lacks kcat (an explicit unknown); class B is complete. Test-only values.
VALUES: dict[str, dict[str, float | None]] = {
    CLASS_A: {
        "km": 0.8,
        "kcat": None,
        "substrate_initial_concentration": 5.0,
        "enzyme_initial_concentration": 0.001,
    },
    CLASS_B: {
        "km": 0.5,
        "kcat": 2.0,
        "substrate_initial_concentration": 5.0,
        "enzyme_initial_concentration": 0.001,
    },
}


@pytest.fixture(scope="module")
def base_registry() -> FungModRegistry:
    return load_registry(REGISTRY_INDEX)


# ---------------------------------------------------------------------------
# Two classes on one dissolved substrate, in either listing order


@pytest.mark.parametrize("listing", [(CLASS_A, CLASS_B), (CLASS_B, CLASS_A)], ids=["a_first", "b_first"])
@pytest.mark.parametrize("mode", ["scientific", "exploratory"])
def test_preflight_selects_the_complete_class_and_records_it(
    base_registry: FungModRegistry, listing: tuple[str, str], mode: Any
) -> None:
    registry = _two_class_registry(base_registry, listing=listing)

    report = assess_modelability(
        fungus_id=FUNGUS_ID,
        substrate_id=SUBSTRATE_ID,
        environment_id=ENVIRONMENT_ID,
        registry=registry,
        mode=mode,
    )

    assert report.status == "modelable"
    assert report.selected_compatibility_id == _compatibility_id(CLASS_B)
    assert report.selected_enzyme_class == CLASS_B
    assert report.required_parameters == tuple(_symbol(CLASS_B, role) for role in ROLES)
    assert report.to_dict()["selected_compatibility_id"] == _compatibility_id(CLASS_B)
    assert report.to_dict()["selected_enzyme_class"] == CLASS_B
    selected = select_registry_case_compatibility(
        registry=registry, fungus_id=FUNGUS_ID, substrate_id=SUBSTRATE_ID, report=report
    )
    assert selected.record_id == _compatibility_id(CLASS_B)


@pytest.mark.parametrize("listing", [(CLASS_A, CLASS_B), (CLASS_B, CLASS_A)], ids=["a_first", "b_first"])
def test_config_assembly_uses_the_class_the_preflight_selected(
    base_registry: FungModRegistry, listing: tuple[str, str]
) -> None:
    registry = _two_class_registry(base_registry, listing=listing)

    config = build_model_config_from_registry_case(
        fungus_id=FUNGUS_ID,
        substrate_id=SUBSTRATE_ID,
        environment_id=ENVIRONMENT_ID,
        registry=registry,
        mode="scientific",
    )

    provenance = config.to_dict()["provenance"]
    assert provenance["process_compatibility_id"] == _compatibility_id(CLASS_B)
    assert provenance["case_template_id"] == _template_id(CLASS_B)
    assert provenance["parameter_record_ids"] == {role: _record_id(CLASS_B, role) for role in ROLES}


@pytest.mark.parametrize("listing", [(CLASS_A, CLASS_B), (CLASS_B, CLASS_A)], ids=["a_first", "b_first"])
@pytest.mark.parametrize("mode", ["exploratory", "scientific"])
def test_screens_and_tables_use_the_class_the_preflight_selected(
    base_registry: FungModRegistry, tmp_path: Path, listing: tuple[str, str], mode: Any
) -> None:
    registry = _two_class_registry(base_registry, listing=listing)
    experiment = VirtualExperiment.from_registry(
        fungi=FUNGUS_ID, substrates=SUBSTRATE_ID, environments=ENVIRONMENT_ID, registry=registry
    )
    sampling = {"n_samples": 2, "seed": 7} if mode == "exploratory" else {}

    result = experiment.simulate(mode=mode, output_dir=tmp_path / mode, quicklook=False, **sampling)

    (preflight,) = result.preflight_reports
    (case,) = result.screen_result.case_results
    b_records = {_record_id(CLASS_B, role) for role in ROLES}
    a_records = {_record_id(CLASS_A, role) for role in ROLES}
    for sample in case.samples:
        provenance = yaml.safe_load(Path(sample.config_path).read_text(encoding="utf-8"))["provenance"]
        assert provenance["process_compatibility_id"] == _compatibility_id(CLASS_B)
        assert set(provenance["parameter_record_ids"].values()) == {
            _sampled_id(record_id, sample.sample_index, mode) for record_id in b_records
        }
    provenance_rows = _rows(tmp_path / mode / "provenance_table.csv")
    compatibility_rows = [row["record_id"] for row in provenance_rows if row["record_type"] == "process_compatibility"]
    template_rows = [row["record_id"] for row in provenance_rows if row["record_type"] == "case_template"]
    parameter_rows = {row["record_id"] for row in provenance_rows if row["record_type"] == "parameter"}
    assert compatibility_rows == [_compatibility_id(CLASS_B)]
    assert template_rows == [_template_id(CLASS_B)]
    assert parameter_rows == b_records
    sampled = {row["source_record_id"] for row in _rows(tmp_path / mode / "sampled_parameters.csv")}
    assert sampled == b_records
    mechanism = _rows(tmp_path / mode / "mechanism_summary.csv")[0]
    assert mechanism["configured_by"] == _template_id(CLASS_B)
    tables = {path.name: path.read_text(encoding="utf-8") for path in (tmp_path / mode).glob("*.csv")}
    assert not any(record_id in text for text in tables.values() for record_id in a_records)
    # Class A's record is listed only as an assessed candidate in the preflight items.
    assert {name for name, text in tables.items() if _compatibility_id(CLASS_A) in text} == {
        "modelability_items.csv"
    }
    assert preflight.selected_compatibility_id == _compatibility_id(CLASS_B)
    assert case.modelability_report.selected_compatibility_id == _compatibility_id(CLASS_B)


def test_tables_refuse_a_preflight_report_that_selected_another_record(
    base_registry: FungModRegistry, tmp_path: Path
) -> None:
    registry = _two_class_registry(base_registry, listing=(CLASS_A, CLASS_B))
    experiment = VirtualExperiment.from_registry(
        fungi=FUNGUS_ID, substrates=SUBSTRATE_ID, environments=ENVIRONMENT_ID, registry=registry
    )
    result = experiment.simulate(mode="scientific", output_dir=tmp_path / "run", quicklook=False)
    (preflight,) = result.preflight_reports
    mismatched = replace(
        preflight, selected_compatibility_id=_compatibility_id(CLASS_A), selected_enzyme_class=CLASS_A
    )

    with pytest.raises(RegistryCaseBuildError, match="selected process compatibility record") as error:
        write_standard_tables(
            screen_result=result.screen_result,
            registry=registry,
            preflight_reports=(mismatched,),
            output_dir=tmp_path / "tables",
        )

    assert _compatibility_id(CLASS_A) in str(error.value)
    assert _compatibility_id(CLASS_B) in str(error.value)


# ---------------------------------------------------------------------------
# Reports without a recorded selection, and reports that do not fit the case


def test_hand_built_report_without_selection_is_refused_when_ambiguous(base_registry: FungModRegistry) -> None:
    registry = _two_class_registry(base_registry, listing=(CLASS_A, CLASS_B))
    assessed = assess_modelability(
        fungus_id=FUNGUS_ID,
        substrate_id=SUBSTRATE_ID,
        environment_id=ENVIRONMENT_ID,
        registry=registry,
        mode="scientific",
    )
    hand_built = _hand_built_report(assessed)

    with pytest.raises(RegistryCaseBuildError, match="does not name its selected process compatibility") as error:
        select_registry_case_compatibility(
            registry=registry, fungus_id=FUNGUS_ID, substrate_id=SUBSTRATE_ID, report=hand_built
        )

    message = str(error.value)
    assert "2 candidate records" in message
    for enzyme_class in (CLASS_A, CLASS_B):
        assert _compatibility_id(enzyme_class) in message
        assert f"enzyme class {enzyme_class}" in message


def test_hand_built_report_without_selection_keeps_the_single_candidate(base_registry: FungModRegistry) -> None:
    dataset = load_user_dataset(ESTERASE_FIXTURE, registry=base_registry)
    registry = dataset.overlay(base_registry)
    fungus, substrate, environment = (
        "esterase_demo__strain_e1",
        "esterase_demo__p_nitrophenyl_butyrate",
        "esterase_demo__c37_ph7_5",
    )
    assessed = assess_modelability(
        fungus_id=fungus, substrate_id=substrate, environment_id=environment, registry=registry
    )

    selected = select_registry_case_compatibility(
        registry=registry, fungus_id=fungus, substrate_id=substrate, report=_hand_built_report(assessed)
    )

    assert selected.record_id == assessed.selected_compatibility_id


def test_report_without_any_compatible_record_is_refused(base_registry: FungModRegistry) -> None:
    report = assess_modelability(
        fungus_id="toy_fungus_alpha",
        substrate_id="cellobiose",
        environment_id="toy_lab_environment",
        registry=base_registry,
    )
    assert report.status == "unsupported"
    assert report.selected_compatibility_id is None
    assert report.selected_enzyme_class is None

    with pytest.raises(RegistryCaseBuildError, match="selects no process compatibility record"):
        select_registry_case_compatibility(
            registry=base_registry, fungus_id="toy_fungus_alpha", substrate_id="cellobiose", report=report
        )


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"selected_compatibility_id": "test_only_absent_record"}, "this registry does not hold"),
        ({"selected_enzyme_class": CLASS_A}, f"names enzyme class '{CLASS_A}'"),
        ({"selected_compatibility_id": "beta_glucosidase_cellobiose_homogeneous_mm"}, "not a standalone"),
        ({"required_processes": ("surface_catalysis",)}, "not among the report's required processes"),
        ({"fungus_id": "toy_fungus_alpha"}, "cannot select the process compatibility record"),
    ],
)
def test_report_whose_selection_does_not_fit_the_case_is_refused(
    base_registry: FungModRegistry, changes: dict[str, Any], match: str
) -> None:
    registry = _two_class_registry(base_registry, listing=(CLASS_A, CLASS_B))
    report = assess_modelability(
        fungus_id=FUNGUS_ID,
        substrate_id=SUBSTRATE_ID,
        environment_id=ENVIRONMENT_ID,
        registry=registry,
        mode="scientific",
    )

    with pytest.raises(RegistryCaseBuildError, match=match):
        select_registry_case_compatibility(
            registry=registry, fungus_id=FUNGUS_ID, substrate_id=SUBSTRATE_ID, report=replace(report, **changes)
        )


# ---------------------------------------------------------------------------
# Non-specific case: a user dataset with two classes on one substrate


def test_user_dataset_strain_with_two_classes_follows_the_preflight_in_each_mode(
    base_registry: FungModRegistry, tmp_path: Path
) -> None:
    """Class A has estimates only, class B literature-style values (both illustrative).

    Scientific mode rejects A's exploratory priors and selects B; exploratory
    mode can use either. Every consumer follows the preflight of its own mode.
    """

    dataset_dir = _two_class_user_dataset(tmp_path)
    registry = load_user_dataset(dataset_dir, registry=base_registry).overlay(base_registry)
    fungus = "two_class_demo__strain_t1"
    substrate = "two_class_demo__p_nitrophenyl_acetate"
    environment = "two_class_demo__c30_ph7"
    compat = {
        key: f"two_class_demo__{key}__p_nitrophenyl_acetate__homogeneous_mm"
        for key in ("esterase_a", "esterase_b")
    }
    assert registry.get_fungus(fungus).enzyme_classes == ("two_class_demo__esterase_a", "two_class_demo__esterase_b")

    config = build_model_config_from_registry_case(
        fungus_id=fungus, substrate_id=substrate, environment_id=environment, registry=registry, mode="scientific"
    )
    assert config.to_dict()["provenance"]["process_compatibility_id"] == compat["esterase_b"]
    scientific = assess_modelability(
        fungus_id=fungus, substrate_id=substrate, environment_id=environment, registry=registry, mode="scientific"
    )
    assert scientific.status == "modelable"
    assert scientific.selected_compatibility_id == compat["esterase_b"]
    assert scientific.selected_enzyme_class == "two_class_demo__esterase_b"

    exploratory = assess_modelability(
        fungus_id=fungus, substrate_id=substrate, environment_id=environment, registry=registry, mode="exploratory"
    )
    assert exploratory.status == "modelable"
    assert exploratory.selected_compatibility_id in compat.values()

    experiment = VirtualExperiment.from_registry(
        fungi=fungus, substrates=substrate, environments=environment, registry=registry
    )
    runs: tuple[tuple[Literal["scientific", "exploratory"], ModelabilityReport, dict[str, int]], ...] = (
        ("scientific", scientific, {}),
        ("exploratory", exploratory, {"n_samples": 2, "seed": 3}),
    )
    for mode, report, sampling in runs:
        output = tmp_path / f"run_{mode}"
        result = experiment.simulate(mode=mode, output_dir=output, quicklook=False, **sampling)
        (case,) = result.screen_result.case_results
        assert case.modelability_report.selected_compatibility_id == report.selected_compatibility_id
        for sample in case.samples:
            provenance = yaml.safe_load(Path(sample.config_path).read_text(encoding="utf-8"))["provenance"]
            assert provenance["process_compatibility_id"] == report.selected_compatibility_id
        compatibility_rows = [
            row["record_id"]
            for row in _rows(output / "provenance_table.csv")
            if row["record_type"] == "process_compatibility"
        ]
        assert compatibility_rows == [report.selected_compatibility_id]
        selected_class = str(report.selected_enzyme_class).removeprefix("two_class_demo__")
        assert {row["source_record_id"] for row in _rows(output / "sampled_parameters.csv")} == {
            f"two_class_demo__strain_t1__{selected_class}__p_nitrophenyl_acetate__c30_ph7__{quantity}"
            for quantity in ("km", "kcat", "substrate_initial_concentration", "enzyme_concentration")
        }


# ---------------------------------------------------------------------------
# Shipped registry: the recorded selection is the one assembly used before


def test_every_shipped_case_selects_the_single_record_assembly_used_before(base_registry: FungModRegistry) -> None:
    """Shipped cases have one candidate record each, so the fix changes no shipped selection."""

    selected_cases = 0
    for fungus, substrate, environment, mode in itertools.product(
        sorted(base_registry.fungi),
        sorted(base_registry.substrates),
        sorted(base_registry.environments),
        ("scientific", "exploratory", "toy"),
    ):
        report = assess_modelability(
            fungus_id=fungus, substrate_id=substrate, environment_id=environment, registry=base_registry, mode=mode
        )
        if report.selected_compatibility_id is None:
            assert not report.candidate_processes
            continue
        selected_cases += 1
        recorded = select_registry_case_compatibility(
            registry=base_registry, fungus_id=fungus, substrate_id=substrate, report=report
        )
        previous = select_registry_case_compatibility(
            registry=base_registry, fungus_id=fungus, substrate_id=substrate, report=_hand_built_report(report)
        )
        assert recorded.record_id == previous.record_id == report.selected_compatibility_id
        assert recorded.enzyme_class == report.selected_enzyme_class
        assert report.required_processes == (recorded.process_type,)
    assert selected_cases > 0


# ---------------------------------------------------------------------------
# Helpers


def _hand_built_report(report: ModelabilityReport) -> ModelabilityReport:
    """A report built by hand as before FIX-SELECT-001: no selected-record fields."""

    return ModelabilityReport(
        fungus_id=report.fungus_id,
        substrate_id=report.substrate_id,
        environment_id=report.environment_id,
        mode=report.mode,
        status=report.status,
        known=report.known,
        uncertain=report.uncertain,
        missing=report.missing,
        incompatible=report.incompatible,
        required_processes=report.required_processes,
        candidate_processes=report.candidate_processes,
        required_parameters=report.required_parameters,
        suggested_experiments=report.suggested_experiments,
        assumptions=report.assumptions,
    )


def _compatibility_id(enzyme_class: str) -> str:
    return f"{enzyme_class}_homogeneous_mm"


def _template_id(enzyme_class: str) -> str:
    return f"{enzyme_class}_homogeneous_mm_template"


def _symbol(enzyme_class: str, role: str) -> str:
    return f"{enzyme_class}__{role}"


def _record_id(enzyme_class: str, role: str) -> str:
    return f"{enzyme_class}__{role}__record"


def _sampled_id(record_id: str, sample_index: int, mode: str) -> str:
    return f"{record_id}_sample_{sample_index}" if mode == "exploratory" else record_id


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _two_class_registry(base: FungModRegistry, *, listing: tuple[str, str]) -> FungModRegistry:
    """Copy of the shipped registry plus test-only records for one two-class case."""

    enzyme_classes = tuple(
        EnzymeClassRecord(
            record_id=enzyme_class,
            name=f"Test-only esterase {enzyme_class[-1].upper()}",
            maturity="software_test_fixture",
            provenance=TEST_PROVENANCE,
            notes="Test-only enzyme class; not biological data.",
            target_bond_classes=(BOND_CLASS,),
            compatible_substrate_classes=(SUBSTRATE_CLASS,),
            compatible_processes=(PROCESS_TYPE,),
        )
        for enzyme_class in (CLASS_A, CLASS_B)
    )
    fungus = FungusRecord(
        record_id=FUNGUS_ID,
        name="Test-only two-class enzyme source",
        maturity="software_test_fixture",
        provenance=TEST_PROVENANCE,
        notes="Test-only enzyme source listing two classes that act on one substrate.",
        enzyme_classes=listing,
    )
    substrate = SubstrateRecord(
        record_id=SUBSTRATE_ID,
        name="Test-only dissolved ester",
        maturity="software_test_fixture",
        provenance=TEST_PROVENANCE,
        notes="Test-only dissolved substrate; not scientific data.",
        substrate_class=SUBSTRATE_CLASS,
        physical_state="dissolved",
        bond_classes=(BOND_CLASS,),
        products=("test_only_acid",),
    )
    environment = EnvironmentRecord(
        record_id=ENVIRONMENT_ID,
        name="Test-only assay environment",
        maturity="software_test_fixture",
        provenance=TEST_PROVENANCE,
        notes="Test-only environment; not empirical data.",
        conditions={
            "temperature": ValueSpec(
                kind="exact",
                value=303.15,
                units="kelvin",
                source=TEST_SOURCE,
                confidence_level="testing",
                notes="Test-only condition.",
            )
        },
    )
    compatibilities = tuple(_compatibility(enzyme_class) for enzyme_class in (CLASS_A, CLASS_B))
    templates = tuple(_template(enzyme_class) for enzyme_class in (CLASS_A, CLASS_B))
    parameters = tuple(
        _parameter(enzyme_class, role) for enzyme_class in (CLASS_A, CLASS_B) for role in ROLES
    )
    return FungModRegistry.build(
        registry_id=base.registry_id,
        version=base.version,
        maturity=base.maturity,
        provenance={**dict(base.provenance), "notes": "Test-only copy for FIX-SELECT-001; not a shipped registry."},
        fungi=(*base.fungi.values(), fungus),
        enzyme_classes=(*base.enzyme_classes.values(), *enzyme_classes),
        substrates=(*base.substrates.values(), substrate),
        environments=(*base.environments.values(), environment),
        process_compatibility=(*base.process_compatibility.values(), *compatibilities),
        parameters=(*base.parameters.values(), *parameters),
        case_templates=(*base.case_templates.values(), *templates),
        product_maps=base.product_maps.values(),
    )


def _compatibility(enzyme_class: str) -> ProcessCompatibilityRecord:
    return ProcessCompatibilityRecord(
        record_id=_compatibility_id(enzyme_class),
        name=f"{enzyme_class} on the test-only dissolved ester",
        maturity="software_test_fixture",
        provenance=TEST_PROVENANCE,
        notes="Test-only compatibility record.",
        enzyme_class=enzyme_class,
        substrate_class=SUBSTRATE_CLASS,
        required_bond_classes=(BOND_CLASS,),
        process_type=PROCESS_TYPE,
        required_parameters=tuple(_symbol(enzyme_class, role) for role in ROLES),
        parameter_roles={role: _symbol(enzyme_class, role) for role in ROLES},
        product_map_required=True,
        case_template_id=_template_id(enzyme_class),
    )


def _template(enzyme_class: str) -> CaseTemplateRecord:
    states = {
        "substrate": "test_only_ester_concentration",
        "product": "test_only_acid_concentration",
        "enzyme": f"{enzyme_class}_concentration",
    }
    return CaseTemplateRecord(
        record_id=_template_id(enzyme_class),
        name=f"{enzyme_class} test-only homogeneous Michaelis-Menten template",
        maturity="software_test_fixture",
        provenance=TEST_PROVENANCE,
        notes="Test-only assembly template.",
        case_template_id=_template_id(enzyme_class),
        process_type=PROCESS_TYPE,
        state_roles=dict(states),
        initial_state_mapping={
            "substrate": {
                "parameter_role": "substrate_initial_concentration",
                "units_from_role": "substrate_initial_concentration",
            },
            "product": {"value": 0.0, "units_from_role": "substrate_initial_concentration"},
            "enzyme": {
                "parameter_role": "enzyme_initial_concentration",
                "units_from_role": "enzyme_initial_concentration",
            },
        },
        product_map={
            "id": f"{enzyme_class}_product_map",
            "product_map_type": "stoichiometric",
            "substrate_state_role": "substrate",
            "product_state_role": "product",
            "stoichiometric_yield": 1.0,
            "notes": "Test-only one-to-one yield.",
        },
        stoichiometric_yields={"product": 1.0},
        time_grid={"start": 0.0, "stop": 600.0, "points": 31, "units": "second"},
        observable_roles=("substrate", "product", "enzyme", "degradation_rate", "product_release_rate"),
        output_state_roles=dict(states),
        process_state_metadata={
            "config_name": f"{enzyme_class} test-only case",
            "config_mode": "scientific",
            "config_maturity": "scientific",
            "process_id": f"{enzyme_class}_homogeneous_mm",
            "parameter_set_id": f"{enzyme_class}_parameters",
            "product_map_name": f"{enzyme_class} test-only product map",
        },
        limitations=("Test-only homogeneous Michaelis-Menten fixture; no biological claim.",),
        validity_notes=("Valid only for software tests of case class selection.",),
    )


def _parameter(enzyme_class: str, role: str) -> ParameterRecord:
    value = VALUES[enzyme_class][role]
    unknown = value is None
    return ParameterRecord(
        record_id=_record_id(enzyme_class, role),
        name=f"Test-only {role} for {enzyme_class}",
        maturity="software_test_fixture",
        provenance=TEST_PROVENANCE,
        notes="Test-only value; not a measurement." if not unknown else "Test-only explicit unknown.",
        parameter_symbol=_symbol(enzyme_class, role),
        process_type=PROCESS_TYPE,
        enzyme_class=enzyme_class,
        substrate_class=SUBSTRATE_CLASS,
        fungus_id=FUNGUS_ID,
        substrate_id=SUBSTRATE_ID,
        environment_id=ENVIRONMENT_ID,
        value=ValueSpec(
            kind="unknown" if unknown else "exact",
            value=value,
            units=UNITS[role],
            source=TEST_SOURCE,
            # Not "testing": the scientific run validator reserves that label for toy data,
            # and class B must run in scientific mode. The record is still test-only.
            confidence_level="missing_from_test_fixture" if unknown else "test_only_illustrative_value",
            notes="Test-only value; not scientific data.",
        ),
        allowed_use=PARAMETER_ALLOWED_USE_GAP_ANALYSIS_ONLY if unknown else PARAMETER_ALLOWED_USE_SCIENTIFIC,
    )


def _two_class_user_dataset(tmp_path: Path) -> Path:
    source = "FungMod FIX-SELECT-001 user-data test fixture; illustrative values, not measurements"
    directory = tmp_path / "two_class_dataset"
    directory.mkdir()
    files = {
        "user_dataset.yml": (
            "dataset_id: two_class_demo\n"
            "contributor: FungMod maintainers\n"
            "date: 2026-10-07\n"
            f"source: {source}\n"
            "notes: Test-only strain with two esterase classes on one substrate.\n"
            "simulation:\n  duration: 30\n  units: minute\n  points: 31\n"
        ),
        "strains.csv": "strain_id,name,scientific_name,aliases\nstrain_t1,Two-class test strain T1,,\n",
        "enzyme_classes.csv": (
            "class_id,name,ec_number,target_bond_classes,compatible_substrate_classes,source\n"
            f'esterase_a,esterase A,3.1.1.1,carboxylic_ester,acetyl_ester,"{source}"\n'
            f'esterase_b,esterase B,3.1.1.1,carboxylic_ester,acetyl_ester,"{source}"\n'
        ),
        "enzymes.csv": (
            "strain_id,enzyme_class,evidence,source\n"
            f'strain_t1,esterase_a,genome annotation,"{source}"\n'
            f'strain_t1,esterase_b,proteome entry,"{source}"\n'
        ),
        "substrates.csv": (
            "substrate_id,registry_substrate,name,substrate_class,physical_state,bond_classes,product,"
            "product_yield,yield_basis,source\n"
            "p_nitrophenyl_acetate,,p-nitrophenyl acetate,acetyl_ester,dissolved,carboxylic_ester,"
            f'p_nitrophenol,1,mol/mol,"{source}"\n'
        ),
        "conditions.csv": (
            "condition_id,temperature,temperature_units,ph,notes\nc30_ph7,30,degC,7.0,Test-only assay condition\n"
        ),
    }
    kinetics = [
        "strain_id,enzyme_class,substrate_id,condition_id,quantity,value,lower,upper,units,evidence_type,method,"
        "source,sd,replicates"
    ]
    for enzyme_class, evidence, method, km, kcat in (
        ("esterase_a", "estimate", "", 300, 40),
        ("esterase_b", "literature", "test-only stated method", 120, 15),
    ):
        for quantity, value, units, row_evidence, row_method in (
            ("km", km, "µM", evidence, method),
            ("kcat", kcat, "1/min", evidence, method),
            ("substrate_initial_concentration", 200, "µM", "design", "test-only assay design"),
            ("enzyme_concentration", 0.05, "µM", "design", "test-only assay design"),
        ):
            kinetics.append(
                f"strain_t1,{enzyme_class},p_nitrophenyl_acetate,c30_ph7,{quantity},{value},,,{units},"
                f'{row_evidence},{row_method},"{source}",,'
            )
    files["kinetics.csv"] = "\n".join(kinetics) + "\n"
    for name, text in files.items():
        (directory / name).write_text(text, encoding="utf-8")
    return directory
