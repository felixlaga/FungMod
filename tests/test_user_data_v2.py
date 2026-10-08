"""Vmax, activity and environment responses in user data (USERDATA-002)."""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
import yaml

from fungal_model import UserDataError, UserDataset, environment_grid, load_user_dataset, virtual_experiment
from fungal_model.api import VirtualExperimentError
from fungal_model.api.user_data import (
    LAW_SCALES_RATE,
    RESPONSE_LAWS,
    USER_DATASET_MATURITY_ORDER,
    VMAX_ROUTES,
)
from fungal_model.core.units import Q_
from fungal_model.provenance import USER_DATASET_PROVENANCE_KEY
from fungal_model.registry import FungModRegistry, load_registry
from fungal_model.registry.loaders import load_parameter_record_mapping
from fungal_model.registry.records import (
    PARAMETER_ALLOWED_USE_EXPLORATORY,
    PARAMETER_ALLOWED_USE_GAP_ANALYSIS_ONLY,
    PARAMETER_ALLOWED_USE_SCIENTIFIC,
    ParameterRecord,
    ProcessCompatibilityRecord,
)
from fungal_model.screening.case_builder import (
    HOMOGENEOUS_MM_PARAMETER_ROLES,
    HOMOGENEOUS_MM_VMAX_PARAMETER_ROLES,
    RegistryCaseBuildError,
    build_model_config_from_registry_case,
    get_registry_process_assembler,
)
from fungal_model.screening.ensemble import simulate_screen
from fungal_model.screening.parameter_resolution import _MODIFIER_COMPATIBILITY_ROLE_BY_FIELD
from fungal_model.screening.template_environment_modifiers import ENVIRONMENT_MODIFIER_TYPES

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_INDEX = ROOT / "data_registry" / "registry_index.yml"
FIXTURES = ROOT / "tests" / "fixtures" / "user_data"
OXIDASE = FIXTURES / "oxidase_case"
LITERATURE = FIXTURES / "literature_reentry"
SNAPSHOTS = FIXTURES / "assembled_config_snapshots.json"

SOURCE = "FungMod user-data import fixture; illustrative values, not measurements"
FUNGUS = "oxidase_demo__strain_l1"
SUBSTRATE = "oxidase_demo__syringaldazine_like"
PREFIX = "oxidase_demo__strain_l1__laccase_like_oxidase__syringaldazine_like__"
VMAX_ID = f"{PREFIX}c50_ph5__vmax"
TEMPLATE_ID = "oxidase_demo__laccase_like_oxidase__syringaldazine_like__homogeneous_mm_template"
COMPATIBILITY_ID = "oxidase_demo__laccase_like_oxidase__syringaldazine_like__homogeneous_mm"
PROCESS_ID = "oxidase_demo__laccase_like_oxidase__syringaldazine_like__homogeneous_mm"

CASE = "strain_l1,laccase_like_oxidase,syringaldazine_like,c50_ph5"
KINETICS_HEADER = (
    "strain_id,enzyme_class,substrate_id,condition_id,quantity,value,lower,upper,units,evidence_type,method,"
    "source,sd,replicates,activity_substrate,activity_saturating"
)
BINDING = "strain_l1,laccase_like_oxidase,syringaldazine_like"
RESPONSES_HEADER = (
    "strain_id,enzyme_class,substrate_id,law,parameter,value,units,evidence_type,method,source,"
    "reference_tolerance,kinetics_at_reference"
)

# Cardinal values of the fixture (degC and pH), used to compute the laws independently.
T_MIN, T_OPT, T_MAX = 10.0, 50.0, 70.0
PH_MIN, PH_OPT, PH_MAX = 3.0, 5.0, 8.0
GAS_CONSTANT = 8.31446261815324  # J/(mol K), exact in the 2019 SI (N_A x k_B)


@pytest.fixture(scope="module")
def base_registry() -> FungModRegistry:
    return load_registry(REGISTRY_INDEX)


@pytest.fixture(scope="module")
def oxidase(base_registry: FungModRegistry) -> UserDataset:
    return load_user_dataset(OXIDASE, registry=base_registry)


# ---------------------------------------------------------------------------
# Table builders


def _kinetics_row(
    quantity: str,
    value: str = "",
    units: str = "",
    *,
    lower: str = "",
    upper: str = "",
    evidence: str = "estimate",
    method: str = "",
    activity_substrate: str = "",
    activity_saturating: str = "",
    case: str = CASE,
) -> str:
    return (
        f'{case},{quantity},{value},{lower},{upper},{units},{evidence},{method},"{SOURCE}",,,'
        f"{activity_substrate},{activity_saturating}"
    )


KM = _kinetics_row("km", "20", "µM")
S0 = _kinetics_row("substrate_initial_concentration", "50", "µM")
SPECIFIC_ACTIVITY = _kinetics_row("specific_activity", "12", "µmol/min/mg")
LOADING = _kinetics_row("enzyme_loading", "0.05", "mg/L")


def _kinetics(*rows: str) -> str:
    return "\n".join((KINETICS_HEADER, *rows)) + "\n"


def _response_row(
    law: str,
    parameter: str,
    value: str,
    units: str,
    *,
    evidence: str = "estimate",
    method: str = "",
    tolerance: str = "",
    at_reference: str = "",
    binding: str = BINDING,
) -> str:
    return f'{binding},{law},{parameter},{value},{units},{evidence},{method},"{SOURCE}",{tolerance},{at_reference}'


def _cardinal_temperature(
    minimum: str = "10", optimum: str = "50", maximum: str = "70", units: str = "degC", **kwargs: Any
) -> list[str]:
    law = "temperature_cardinal_rosso"
    return [
        _response_row(law, "minimum_temperature", minimum, units, **{k: v for k, v in kwargs.items() if k in {"evidence", "method", "binding"}}),
        _response_row(law, "optimum_temperature", optimum, units, **kwargs),
        _response_row(law, "maximum_temperature", maximum, units, **{k: v for k, v in kwargs.items() if k in {"evidence", "method", "binding"}}),
    ]


def _cardinal_ph(**kwargs: Any) -> list[str]:
    law = "ph_cardinal_rosso"
    return [
        _response_row(law, "minimum_ph", "3", "dimensionless", **kwargs),
        _response_row(law, "optimum_ph", "5", "dimensionless", **kwargs),
        _response_row(law, "maximum_ph", "8", "dimensionless", **kwargs),
    ]


def _responses(*rows: str) -> str:
    return "\n".join((RESPONSES_HEADER, *rows)) + "\n"


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


def _load(tmp_path: Path, edits: Mapping[str, str | None], *, source: Path = OXIDASE) -> UserDataset:
    return load_user_dataset(_copy_fixture(tmp_path, source, edits=edits), registry=REGISTRY_INDEX)


def _records(dataset: UserDataset, record_type: str) -> dict[str, Mapping[str, Any]]:
    return {str(mapping["record_id"]): mapping for mapping in dataset.records[record_type]}


def _parameter(dataset: UserDataset, record_id: str) -> ParameterRecord:
    return load_parameter_record_mapping(_records(dataset, "parameter_records")[record_id])


# ---------------------------------------------------------------------------
# Independent response-law formulas (published forms, computed here, not imported)


def _ctmi(temperature: float, minimum: float, optimum: float, maximum: float) -> float:
    """Rosso et al. (1993) cardinal temperature model with inflection."""

    if temperature <= minimum or temperature >= maximum:
        return 0.0
    numerator = (temperature - maximum) * (temperature - minimum) ** 2
    denominator = (optimum - minimum) * (
        (optimum - minimum) * (temperature - optimum) - (optimum - maximum) * (optimum + minimum - 2.0 * temperature)
    )
    return numerator / denominator


def _cpm(ph: float, minimum: float, optimum: float, maximum: float) -> float:
    """Rosso et al. (1995) cardinal pH model."""

    if ph <= minimum or ph >= maximum:
        return 0.0
    numerator = (ph - minimum) * (ph - maximum)
    return numerator / (numerator - (ph - optimum) ** 2)


# ---------------------------------------------------------------------------
# Part A: Vmax routes


def test_derived_vmax_is_specific_activity_times_enzyme_loading(oxidase: UserDataset) -> None:
    record = _parameter(oxidase, VMAX_ID)
    expected = (Q_(12.0, "µmol/min/mg") * Q_(0.05, "mg/L")).to("µM/min")
    assert record.value.is_exact
    assert Q_(record.value.value, record.value.units).to("µM/min").magnitude == pytest.approx(expected.magnitude, rel=1e-12)
    assert expected.magnitude == pytest.approx(0.6)
    assert record.parameter_symbol == "oxidase_demo__vmax__laccase_like_oxidase__syringaldazine_like"
    assert record.maturity == "exploratory_prior"
    assert record.allowed_use == PARAMETER_ALLOWED_USE_EXPLORATORY
    assert record.provenance["exploratory_prior"] is True

    user = record.provenance[USER_DATASET_PROVENANCE_KEY]
    assert user["rows"] == [4, 5]
    derivation = user["derivation"]
    assert derivation["route"] == "specific_activity"
    assert derivation["formula"] == "vmax = specific_activity x enzyme_loading"
    assert [(item["row"], item["quantity"], item["value"], item["units"]) for item in derivation["inputs"]] == [
        (4, "specific_activity", 12.0, "µmol/min/mg"),
        (5, "enzyme_loading", 0.05, "mg/L"),
    ]
    assert all(item["source"] == SOURCE for item in derivation["inputs"])
    assert " < ".join(USER_DATASET_MATURITY_ORDER) in derivation["maturity_rule"]

    # The two input rows are carried in provenance only, never as parameter records of their own.
    assert not any("specific_activity" in key or "enzyme_loading" in key for key in _records(oxidase, "parameter_records"))


def test_maturity_order_is_estimate_design_literature_measured() -> None:
    assert USER_DATASET_MATURITY_ORDER == (
        "exploratory_prior",
        "user_design_value",
        "user_reported_literature",
        "user_measured",
    )


@pytest.mark.parametrize(
    ("activity_evidence", "loading_evidence", "maturity", "allowed_use"),
    [
        ("measured", "design", "user_design_value", PARAMETER_ALLOWED_USE_SCIENTIFIC),
        ("literature", "measured", "user_reported_literature", PARAMETER_ALLOWED_USE_SCIENTIFIC),
        ("measured", "measured", "user_measured", PARAMETER_ALLOWED_USE_SCIENTIFIC),
        ("measured", "estimate", "exploratory_prior", PARAMETER_ALLOWED_USE_EXPLORATORY),
    ],
)
def test_derived_vmax_takes_the_weaker_input_maturity(
    tmp_path: Path,
    activity_evidence: str,
    loading_evidence: str,
    maturity: str,
    allowed_use: str,
) -> None:
    def method(evidence: str) -> str:
        return "" if evidence == "estimate" else "stated assay method"

    kinetics = _kinetics(
        KM,
        S0,
        _kinetics_row("specific_activity", "12", "µmol/min/mg", evidence=activity_evidence, method=method(activity_evidence)),
        _kinetics_row("enzyme_loading", "0.05", "mg/L", evidence=loading_evidence, method=method(loading_evidence)),
    )
    record = _parameter(_load(tmp_path, {"kinetics.csv": kinetics}), VMAX_ID)
    assert record.maturity == maturity
    assert record.allowed_use == allowed_use
    assert record.provenance.get("exploratory_prior", False) is (maturity == "exploratory_prior")


def test_derived_vmax_from_one_range_scales_the_range_exactly(tmp_path: Path) -> None:
    kinetics = _kinetics(KM, S0, _kinetics_row("specific_activity", units="µmol/min/mg", lower="10", upper="14"), LOADING)
    record = _parameter(_load(tmp_path, {"kinetics.csv": kinetics}), VMAX_ID)
    assert record.value.kind == "range"
    assert Q_(record.value.lower, record.value.units).to("µM/min").magnitude == pytest.approx(0.5)
    assert Q_(record.value.upper, record.value.units).to("µM/min").magnitude == pytest.approx(0.7)
    assert record.range_scope == "user_supplied_range"


def test_saturating_assay_activity_on_the_case_substrate_becomes_vmax(tmp_path: Path) -> None:
    kinetics = _kinetics(
        KM,
        S0,
        _kinetics_row("assay_activity", "0.6", "U/L", activity_substrate="syringaldazine_like", activity_saturating="yes"),
    )
    dataset = _load(tmp_path, {"kinetics.csv": kinetics})
    record = _parameter(dataset, VMAX_ID)
    assert (record.value.value, record.value.units) == (0.6, "U/L")
    assert Q_(record.value.value, record.value.units).to("µM/min").magnitude == pytest.approx(0.6)
    route = record.provenance[USER_DATASET_PROVENANCE_KEY]["vmax_route"]
    assert route["route"] == "assay_activity"
    assert route["activity_substrate"] == "syringaldazine_like"
    assert route["activity_saturating"] is True
    assert record.provenance[USER_DATASET_PROVENANCE_KEY]["row"] == 4


def test_explicit_vmax_row_with_its_method_is_the_vmax_record(tmp_path: Path) -> None:
    kinetics = _kinetics(KM, S0, _kinetics_row("vmax", "0.6", "µM/min", method="initial-rate fit at 1 mM"))
    record = _parameter(_load(tmp_path, {"kinetics.csv": kinetics}), VMAX_ID)
    assert (record.value.value, record.value.units) == (0.6, "µM/min")
    assert record.provenance["measurement_method"] == "initial-rate fit at 1 mM"
    assert "vmax_route" not in record.provenance[USER_DATASET_PROVENANCE_KEY]


def test_vmax_form_generates_no_enzyme_state(oxidase: UserDataset) -> None:
    compatibility = _records(oxidase, "process_compatibility")[COMPATIBILITY_ID]
    law_roles = [
        "minimum_temperature",
        "optimum_temperature",
        "maximum_temperature",
        "minimum_ph",
        "optimum_ph",
        "maximum_ph",
    ]
    assert list(compatibility["parameter_roles"]) == [*HOMOGENEOUS_MM_VMAX_PARAMETER_ROLES, *law_roles]
    assert compatibility["required_parameters"] == list(compatibility["parameter_roles"].values())

    template = _records(oxidase, "case_templates")[TEMPLATE_ID]
    assert set(template["state_roles"]) == {"substrate", "product"}
    assert set(template["initial_state_mapping"]) == {"substrate", "product"}
    assert "enzyme" not in template["observable_roles"]
    assert any("Vmax form" in item for item in template["limitations"])


# ---------------------------------------------------------------------------
# Generic assembler: one alternative role set, shipped cases unchanged


def test_homogeneous_assembler_selects_the_role_set_a_compatibility_binds(base_registry: FungModRegistry) -> None:
    assembler = get_registry_process_assembler("homogeneous_michaelis_menten")
    assert assembler is not None
    shipped = base_registry.process_compatibility["beta_glucosidase_cellobiose_homogeneous_mm"]
    assert assembler.role_set_for(shipped).name == "primary"
    assert assembler.parameter_roles_for(shipped) == HOMOGENEOUS_MM_PARAMETER_ROLES
    assert assembler.role_set_for(shipped).state_roles == ("substrate", "product", "enzyme")

    def compatibility(roles: Sequence[str]) -> ProcessCompatibilityRecord:
        return ProcessCompatibilityRecord(
            record_id="role_set_probe",
            name="role set probe",
            maturity="testing",
            provenance={},
            notes="",
            enzyme_class="any_class",
            substrate_class="any_substrate_class",
            process_type="homogeneous_michaelis_menten",
            parameter_roles={role: f"{role}_symbol" for role in roles},
        )

    vmax = assembler.role_set_for(compatibility(HOMOGENEOUS_MM_VMAX_PARAMETER_ROLES))
    assert (vmax.name, vmax.parameter_roles, vmax.state_roles) == (
        "vmax",
        HOMOGENEOUS_MM_VMAX_PARAMETER_ROLES,
        ("substrate", "product"),
    )
    # Incomplete bindings keep the primary set, so missing-role errors still name the primary roles.
    assert assembler.role_set_for(compatibility(("km", "substrate_initial_concentration"))).name == "primary"
    with pytest.raises(RegistryCaseBuildError, match="more than one complete"):
        assembler.role_set_for(compatibility((*HOMOGENEOUS_MM_PARAMETER_ROLES, "vmax")))
    for process_type in ("surface_catalysis", "ph_ionization_michaelis_menten", "culture_physiology"):
        other = get_registry_process_assembler(process_type)
        assert other is not None and other.alternative_role_sets == ()


def _normalized(value: Any, root: str) -> Any:
    if isinstance(value, dict):
        return {key: _normalized(item, root) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalized(item, root) for item in value]
    if isinstance(value, str) and root in value:
        # Paths under the temporary output root use the platform separator;
        # the snapshot stores them with forward slashes.
        return value.replace(root, "<OUTPUT_ROOT>").replace("\\", "/")
    return value


def test_shipped_and_v1_cases_assemble_byte_identically(base_registry: FungModRegistry) -> None:
    """Assembled configs match a snapshot taken from the code before USERDATA-002.

    The snapshot holds the parsed config mappings (key order preserved) of the
    shipped Reaction 618 and BGL1A cases assembled through the exploratory
    screen, the scientific config of the USERDATA-001 literature re-entry, and
    SHA-256 digests of the records generated from both USERDATA-001 fixtures.
    """

    expected = json.loads(SNAPSHOTS.read_text(encoding="utf-8"))
    cases = {
        "reaction_618": ("sabiork_beta_glucosidase_source", "cellobiose", "sabiork_reaction_618_selected_conditions"),
        "bgl1a_ph5": ("phanerochaete_chrysosporium_k3", "cellobiose", "tsukada_2008_bgl1a_assay_30c_ph5"),
    }
    actual: dict[str, Any] = {}
    for name, (fungus_id, substrate_id, environment_id) in cases.items():
        with tempfile.TemporaryDirectory() as tmp:
            result = simulate_screen(
                fungus_ids=[fungus_id],
                substrate_ids=[substrate_id],
                environment_ids=[environment_id],
                registry=base_registry,
                n_samples=1,
                seed=20261006,
                output_dir=tmp,
                mode="exploratory",
            )
            config_path = Path(result.case_results[0].samples[0].config_path)
            actual[name] = _normalized(yaml.safe_load(config_path.read_text(encoding="utf-8")), tmp)
    literature = load_user_dataset(LITERATURE, registry=base_registry)
    actual["user_data_literature_reentry_scientific"] = build_model_config_from_registry_case(
        fungus_id="reaction_618_reentry__os3bglu6_source",
        substrate_id="cellobiose",
        environment_id="reaction_618_reentry__c30_ph5",
        registry=literature.overlay(base_registry),
        mode="scientific",
        output_directory="<OUTPUT_ROOT>",
    ).to_dict()
    for fixture in ("esterase_case", "literature_reentry"):
        dataset = load_user_dataset(FIXTURES / fixture, registry=base_registry)
        actual[f"user_data_records_sha256_{fixture}"] = hashlib.sha256(
            json.dumps(dataset.to_dict()["records"], sort_keys=True).encode("utf-8")
        ).hexdigest()

    assert set(actual) == set(expected)
    for name in expected:
        assert json.dumps(actual[name], ensure_ascii=False) == json.dumps(expected[name], ensure_ascii=False), name


# ---------------------------------------------------------------------------
# Vmax form against the kcat form on the literature re-entry


def _vmax_literature_kinetics() -> str:
    lines = (LITERATURE / "kinetics.csv").read_text(encoding="utf-8").splitlines()
    kept = [line for line in lines if ",kcat," not in line and ",enzyme_concentration," not in line]
    kept.append(
        "os3bglu6_source,beta_glucosidase,cellobiose,c30_ph5,vmax,1.3e-4,,,mM/s,design,"
        '"kcat x enzyme concentration of this re-entry (0.13 1/s x 0.001 mM)",'
        "Virtual assay design for this re-entry; not reported by SABIO-RK,,"
    )
    return "\n".join(kept) + "\n"


def _scientific_run(dataset_dir: Path | UserDataset, output: Path) -> tuple[dict[str, list[float]], float, float]:
    study = virtual_experiment(fungi="Os3BGlu6 source", substrates="cellobiose", environments="c30_ph5", user_data=dataset_dir)
    assert study.preflight(mode="scientific")[0].status == "modelable"
    result = study.simulate(mode="scientific", output_dir=output, quicklook=False)
    sample = result.screen_result.case_results[0].samples[0]
    settings = json.loads((Path(sample.output_directory) / "solver_settings.json").read_text())["solver_settings"]
    series: dict[str, list[float]] = {}
    for row in result.time_series():
        if row["state_role"] in {"substrate", "product"}:
            assert row["units"] == "millimolar"
            series.setdefault(row["state_role"], []).append(float(row["value"]))
    return series, float(settings["rtol"]), float(settings["atol"])


def test_vmax_form_reproduces_the_kcat_form_when_vmax_is_kcat_times_enzyme(tmp_path: Path) -> None:
    vmax_dir = _copy_fixture(tmp_path / "vmax", LITERATURE, edits={"kinetics.csv": _vmax_literature_kinetics()})
    vmax_dataset = load_user_dataset(vmax_dir, registry=REGISTRY_INDEX)
    record = _parameter(vmax_dataset, "reaction_618_reentry__os3bglu6_source__beta_glucosidase__cellobiose__c30_ph5__vmax")
    assert Q_(record.value.value, record.value.units).to("mM/s").magnitude == pytest.approx(
        (Q_(0.13, "1/s") * Q_(1e-3, "mM")).to("mM/s").magnitude
    )
    template = _records(vmax_dataset, "case_templates")[
        "reaction_618_reentry__beta_glucosidase__cellobiose__homogeneous_mm_template"
    ]
    assert template["process_state_metadata"]["config_mode"] == "scientific"

    config = build_model_config_from_registry_case(
        fungus_id="reaction_618_reentry__os3bglu6_source",
        substrate_id="cellobiose",
        environment_id="reaction_618_reentry__c30_ph5",
        registry=vmax_dataset.overlay(load_registry(REGISTRY_INDEX)),
        mode="scientific",
        output_directory=str(tmp_path / "config"),
    ).to_dict()
    process = config["processes"][0]
    assert set(process["states"]) == {"substrate", "product"}
    assert set(process["parameters"]) == {"km", "vmax", "rate_units"}
    assert set(config["initial_state"]["states"]) == {"cellobiose_concentration", "beta_D_glucose_concentration"}

    kcat_series, rtol, atol = _scientific_run(LITERATURE, tmp_path / "kcat_run")
    vmax_series, vmax_rtol, vmax_atol = _scientific_run(vmax_dataset, tmp_path / "vmax_run")
    assert (vmax_rtol, vmax_atol) == (rtol, atol)
    s0 = kcat_series["substrate"][0]
    assert kcat_series["substrate"][-1] < 0.9 * s0
    for state in ("substrate", "product"):
        assert len(kcat_series[state]) == len(vmax_series[state]) == 61
        for kcat_value, vmax_value in zip(kcat_series[state], vmax_series[state], strict=True):
            # One local error bound of the solver at the largest state magnitude.
            assert abs(kcat_value - vmax_value) <= atol + rtol * 2.0 * s0


# ---------------------------------------------------------------------------
# Part B: response laws through the case template


def test_oxidase_laws_bind_through_the_template_modifier_mechanism(oxidase: UserDataset) -> None:
    template = _records(oxidase, "case_templates")[TEMPLATE_ID]
    assert template["process_state_metadata"]["process_modifiers"] == [
        {
            "type": "temperature_cardinal_rosso",
            "minimum_temperature_role": "minimum_temperature",
            "optimum_temperature_role": "optimum_temperature",
            "maximum_temperature_role": "maximum_temperature",
        },
        {
            "type": "ph_cardinal_rosso",
            "minimum_ph_role": "minimum_ph",
            "optimum_ph_role": "optimum_ph",
            "maximum_ph_role": "maximum_ph",
        },
    ]
    assert template["process_state_metadata"]["config_mode"] == "exploratory"
    optimum = _parameter(oxidase, f"{PREFIX}temperature_cardinal_rosso__optimum_temperature")
    assert (optimum.value.value, optimum.value.units) == (pytest.approx(323.15), "kelvin")
    assert "Original value 50 degC" in optimum.notes
    assert optimum.environment_id is None
    assert optimum.fungus_id == FUNGUS
    user = optimum.provenance[USER_DATASET_PROVENANCE_KEY]
    assert (user["file"], user["row"], user["law"], user["parameter"]) == (
        "responses.csv",
        3,
        "temperature_cardinal_rosso",
        "optimum_temperature",
    )
    assert user["reference_condition"]["kinetics_conditions"] == ["c50_ph5"]
    for law, parameters in (
        ("temperature_cardinal_rosso", ("minimum_temperature", "optimum_temperature", "maximum_temperature")),
        ("ph_cardinal_rosso", ("minimum_ph", "optimum_ph", "maximum_ph")),
    ):
        for parameter in parameters:
            record = _parameter(oxidase, f"{PREFIX}{law}__{parameter}")
            assert record.maturity == "exploratory_prior"
            assert record.allowed_use == PARAMETER_ALLOWED_USE_EXPLORATORY
            assert record.value.source == SOURCE


def test_oxidase_exploratory_simulation_runs_and_scientific_mode_is_refused(
    oxidase: UserDataset,
    tmp_path: Path,
) -> None:
    study = virtual_experiment(
        fungi="Oxidase source strain L1",
        substrates="syringaldazine_like",
        environments="c50_ph5",
        user_data=oxidase,
    )
    assert study.preflight(mode="exploratory")[0].status == "modelable"
    assert study.preflight(mode="scientific")[0].status != "modelable"
    with pytest.raises(VirtualExperimentError, match="Scientific simulation requires exact"):
        study.simulate(mode="scientific", output_dir=tmp_path / "blocked", quicklook=False)

    result = study.simulate(mode="exploratory", n_samples=2, seed=11, output_dir=tmp_path / "run", quicklook=False)
    rows = result.time_series()
    substrate = [float(row["value"]) for row in rows if row["state_role"] == "substrate" and row["sample_index"] in (0, "0")]
    product = [float(row["value"]) for row in rows if row["state_role"] == "product" and row["sample_index"] in (0, "0")]
    assert substrate[0] == pytest.approx(50.0)
    assert substrate[-1] < 0.9 * substrate[0]
    assert all(later <= earlier + 1e-9 for earlier, later in itertools.pairwise(substrate))
    assert product[-1] == pytest.approx(substrate[0] - substrate[-1], rel=1e-6)
    assert {row["environment_effect_status"] for row in rows} == {"active_response_model"}
    sampled = {row["role"]: row["parameter_source_class"] for row in result.sampled_parameters()}
    assert set(sampled) == {*HOMOGENEOUS_MM_VMAX_PARAMETER_ROLES, "minimum_temperature", "optimum_temperature",
                            "maximum_temperature", "minimum_ph", "optimum_ph", "maximum_ph"}
    assert set(sampled.values()) == {"user_supplied_exploratory_prior"}


def _initial_rates_and_losses(result: Any) -> tuple[dict[str, float], dict[str, float], dict[str, Any]]:
    rates: dict[str, float] = {}
    losses: dict[str, dict[int, float]] = {}
    statuses: dict[str, set[str]] = {}
    conditions: dict[str, Any] = {}
    for row in result.time_series():
        environment = row["environment_id"]
        statuses.setdefault(environment, set()).add(row["environment_effect_status"])
        conditions[environment] = (row["temperature_C"], row["ph"])
        if row["state_role"] == "process_rate" and int(row["time_index"]) == 0:
            rates[environment] = float(row["value"])
        if row["state_role"] == "substrate":
            losses.setdefault(environment, {})[int(row["time_index"])] = float(row["value"])
    loss = {environment: values[0] - values[max(values)] for environment, values in losses.items()}
    assert all(status == {"active_response_model"} for status in statuses.values()), statuses
    return rates, loss, conditions


def test_temperature_grid_follows_the_cardinal_temperature_law(oxidase: UserDataset, tmp_path: Path) -> None:
    study = virtual_experiment(
        fungi="strain_l1",
        substrates="syringaldazine_like",
        environments=environment_grid(temperature_C=[20, 50, 65], ph=[5.0]),
        user_data=oxidase,
    )
    assert [report.status for report in study.preflight(mode="exploratory")] == ["modelable"] * 3
    result = study.simulate(mode="exploratory", n_samples=1, seed=7, output_dir=tmp_path / "grid", quicklook=False)
    rates, loss, conditions = _initial_rates_and_losses(result)
    by_temperature = {float(conditions[environment][0]): environment for environment in rates}
    assert set(by_temperature) == {20.0, 50.0, 65.0}

    fastest = max(loss, key=loss.__getitem__)
    assert float(conditions[fastest][0]) == 50.0
    reference = rates[by_temperature[50.0]]
    assert reference == pytest.approx((0.6 / 60.0) * 50.0 / (20.0 + 50.0), rel=1e-9)  # Vmax S0 / (Km + S0) in uM/s
    for temperature in (20.0, 65.0):
        expected = _ctmi(temperature, T_MIN, T_OPT, T_MAX)
        assert 0.0 < expected < 1.0
        assert rates[by_temperature[temperature]] / reference == pytest.approx(expected, rel=1e-9)
    assert _ctmi(20.0, T_MIN, T_OPT, T_MAX) == pytest.approx(0.15625)

    response = result.screen_result.case_results[0].environment_response
    assert response["status"] == "active_response_model"
    assert {law["law"] for law in response["laws"]} == {"temperature_cardinal_rosso", "ph_cardinal_rosso"}


def test_ph_grid_follows_the_cardinal_ph_law(oxidase: UserDataset, tmp_path: Path) -> None:
    study = virtual_experiment(
        fungi="strain_l1",
        substrates="syringaldazine_like",
        environments=environment_grid(temperature_C=[50], ph=[4.0, 5.0, 6.5]),
        user_data=oxidase,
    )
    result = study.simulate(mode="exploratory", n_samples=1, seed=7, output_dir=tmp_path / "ph", quicklook=False)
    rates, loss, conditions = _initial_rates_and_losses(result)
    by_ph = {float(conditions[environment][1]): environment for environment in rates}
    reference = rates[by_ph[5.0]]
    assert max(loss, key=loss.__getitem__) == by_ph[5.0]
    for ph in (4.0, 6.5):
        assert rates[by_ph[ph]] / reference == pytest.approx(_cpm(ph, PH_MIN, PH_OPT, PH_MAX), rel=1e-9)


def test_arrhenius_law_binds_and_scales_with_the_reference_temperature(tmp_path: Path) -> None:
    responses = _responses(
        _response_row("temperature_arrhenius_reference", "activation_energy", "50", "kJ/mol"),
        _response_row("temperature_arrhenius_reference", "reference_temperature", "50", "degC"),
    )
    dataset = _load(tmp_path, {"responses.csv": responses})
    template = _records(dataset, "case_templates")[TEMPLATE_ID]
    assert template["process_state_metadata"]["process_modifiers"] == [
        {
            "type": "temperature_arrhenius_reference",
            "activation_energy_role": "activation_energy",
            "reference_temperature_role": "reference_temperature",
        }
    ]
    study = virtual_experiment(
        fungi="strain_l1",
        substrates="syringaldazine_like",
        environments=environment_grid(temperature_C=[30, 50], ph=[5.0]),
        user_data=dataset,
    )
    result = study.simulate(mode="exploratory", n_samples=1, seed=7, output_dir=tmp_path / "arrhenius", quicklook=False)
    rates, _loss, conditions = _initial_rates_and_losses(result)
    by_temperature = {float(conditions[environment][0]): environment for environment in rates}
    expected = math.exp(-50000.0 / GAS_CONSTANT * (1.0 / 303.15 - 1.0 / 323.15))
    assert rates[by_temperature[30.0]] / rates[by_temperature[50.0]] == pytest.approx(expected, rel=1e-6)


def test_measured_kinetics_and_laws_reach_scientific_mode_until_one_law_row_is_an_estimate(tmp_path: Path) -> None:
    measured = {"evidence": "measured", "method": "stated assay method"}
    kinetics = _kinetics(
        _kinetics_row("km", "20", "µM", **measured),
        _kinetics_row("substrate_initial_concentration", "50", "µM", evidence="design", method="experimental design"),
        _kinetics_row("specific_activity", "12", "µmol/min/mg", **measured),
        _kinetics_row("enzyme_loading", "0.05", "mg/L", evidence="design", method="experimental design"),
    )
    all_measured = _responses(*_cardinal_temperature(**measured), *_cardinal_ph(**measured))
    scientific = _load(tmp_path / "a", {"kinetics.csv": kinetics, "responses.csv": all_measured})
    template = _records(scientific, "case_templates")[TEMPLATE_ID]
    assert template["process_state_metadata"]["config_mode"] == "scientific"
    assert _parameter(scientific, VMAX_ID).maturity == "user_design_value"
    assert _parameter(scientific, f"{PREFIX}ph_cardinal_rosso__optimum_ph").maturity == "user_measured"
    study = virtual_experiment(fungi="strain_l1", substrates="syringaldazine_like", environments="c50_ph5", user_data=scientific)
    assert study.preflight(mode="scientific")[0].status == "modelable"

    one_estimate = _responses(
        *_cardinal_temperature(**measured),
        _response_row("ph_cardinal_rosso", "minimum_ph", "3", "dimensionless", **measured),
        _response_row("ph_cardinal_rosso", "optimum_ph", "5", "dimensionless"),
        _response_row("ph_cardinal_rosso", "maximum_ph", "8", "dimensionless", **measured),
    )
    mixed = _load(tmp_path / "b", {"kinetics.csv": kinetics, "responses.csv": one_estimate})
    for parameter in ("minimum_ph", "optimum_ph", "maximum_ph"):
        record = _parameter(mixed, f"{PREFIX}ph_cardinal_rosso__{parameter}")
        assert record.maturity == "exploratory_prior"
        assert record.allowed_use == PARAMETER_ALLOWED_USE_EXPLORATORY
    assert _parameter(mixed, f"{PREFIX}temperature_cardinal_rosso__optimum_temperature").maturity == "user_measured"
    assert _records(mixed, "case_templates")[TEMPLATE_ID]["process_state_metadata"]["config_mode"] == "exploratory"
    study = virtual_experiment(fungi="strain_l1", substrates="syringaldazine_like", environments="c50_ph5", user_data=mixed)
    assert study.preflight(mode="scientific")[0].status != "modelable"
    with pytest.raises(VirtualExperimentError, match="Scientific simulation requires exact"):
        study.simulate(mode="scientific", output_dir=tmp_path / "blocked", quicklook=False)


def test_without_responses_grid_conditions_stay_labelled_context(tmp_path: Path) -> None:
    dataset = _load(tmp_path, {"responses.csv": None})
    template = _records(dataset, "case_templates")[TEMPLATE_ID]
    assert "process_modifiers" not in template["process_state_metadata"]
    assert "No temperature or pH response law is bound" in " ".join(template["limitations"])
    study = virtual_experiment(
        fungi="strain_l1",
        substrates="syringaldazine_like",
        environments=environment_grid(temperature_C=[20, 50], ph=[5.0]),
        user_data=dataset,
    )
    result = study.simulate(mode="exploratory", n_samples=1, seed=7, output_dir=tmp_path / "grid", quicklook=False)
    rows = result.time_series()
    assert {row["environment_effect_status"] for row in rows} == {"metadata_only"}
    rates = {row["environment_id"]: float(row["value"]) for row in rows if row["state_role"] == "process_rate" and int(row["time_index"]) == 0}
    assert len(set(rates.values())) == 1


def test_reference_tolerance_or_declaration_admits_kinetics_off_the_optimum(tmp_path: Path) -> None:
    within = _load(
        tmp_path / "tolerance",
        {"responses.csv": _responses(*_cardinal_temperature(optimum="48", tolerance="2"), *_cardinal_ph())},
    )
    reference = _parameter(within, f"{PREFIX}temperature_cardinal_rosso__optimum_temperature")
    condition = reference.provenance[USER_DATASET_PROVENANCE_KEY]["reference_condition"]
    assert (condition["reference_tolerance"], condition["tolerance_units"]) == (2.0, "degC")
    assert condition["kinetics_at_reference_declared"] is False

    declared = _load(
        tmp_path / "declared",
        {"responses.csv": _responses(*_cardinal_temperature(optimum="45", at_reference="yes"), *_cardinal_ph())},
    )
    reference = _parameter(declared, f"{PREFIX}temperature_cardinal_rosso__optimum_temperature")
    assert reference.provenance[USER_DATASET_PROVENANCE_KEY]["reference_condition"]["kinetics_at_reference_declared"] is True


# ---------------------------------------------------------------------------
# Refusals


REFUSAL_CASES: dict[str, tuple[dict[str, str | None], tuple[str, int | None, str | None, str]]] = {
    "assay_activity_on_another_substrate": (
        {
            "kinetics.csv": _kinetics(
                KM,
                S0,
                _kinetics_row("assay_activity", "2", "U/mL", activity_substrate="p_nitrophenyl_glycoside", activity_saturating="yes"),
            )
        },
        ("kinetics.csv", 4, "activity_substrate", "not the Vmax on this substrate"),
    ),
    "assay_activity_not_saturating": (
        {
            "kinetics.csv": _kinetics(
                KM,
                S0,
                _kinetics_row("assay_activity", "2", "U/mL", activity_substrate="syringaldazine_like", activity_saturating="no"),
            )
        },
        ("kinetics.csv", 4, "activity_saturating", "not the Vmax on this substrate"),
    ),
    "assay_activity_without_substrate": (
        {"kinetics.csv": _kinetics(KM, S0, _kinetics_row("assay_activity", "2", "U/mL", activity_saturating="yes"))},
        ("kinetics.csv", 4, "activity_substrate", "must state activity_substrate"),
    ),
    "activity_column_on_another_row": (
        {"kinetics.csv": _kinetics(KM, S0, SPECIFIC_ACTIVITY, _kinetics_row("enzyme_loading", "0.05", "mg/L", activity_saturating="yes"))},
        ("kinetics.csv", 5, "activity_saturating", "applies only to assay_activity rows"),
    ),
    "mixed_vmax_routes": (
        {"kinetics.csv": _kinetics(KM, S0, SPECIFIC_ACTIVITY, LOADING, _kinetics_row("vmax", "0.6", "µM/min", method="fit"))},
        ("kinetics.csv", 6, "quantity", "exactly one route"),
    ),
    "kcat_and_enzyme_with_vmax": (
        {
            "kinetics.csv": _kinetics(
                KM,
                S0,
                SPECIFIC_ACTIVITY,
                LOADING,
                _kinetics_row("kcat", "30", "1/min"),
                _kinetics_row("enzyme_concentration", "0.05", "µM"),
            )
        },
        ("kinetics.csv", 4, "quantity", "needs kcat and an enzyme concentration"),
    ),
    "both_derivation_inputs_ranges": (
        {
            "kinetics.csv": _kinetics(
                KM,
                S0,
                _kinetics_row("specific_activity", units="µmol/min/mg", lower="10", upper="14"),
                _kinetics_row("enzyme_loading", units="mg/L", lower="0.04", upper="0.06"),
            )
        },
        ("kinetics.csv", 5, "value", "not a uniform range"),
    ),
    "vmax_without_method": (
        {"kinetics.csv": _kinetics(KM, S0, _kinetics_row("vmax", "0.6", "µM/min"))},
        ("kinetics.csv", 4, "method", "method is required for vmax rows"),
    ),
    "vmax_in_mass_units": (
        {"kinetics.csv": _kinetics(KM, S0, _kinetics_row("vmax", "0.6", "mg/L/min", method="fit"))},
        ("kinetics.csv", 4, "units", "molar mass"),
    ),
    "specific_activity_per_volume": (
        {"kinetics.csv": _kinetics(KM, S0, _kinetics_row("specific_activity", "12", "µmol/min/L"), LOADING)},
        ("kinetics.csv", 4, "units", "per enzyme mass"),
    ),
    "enzyme_activity_quantity": (
        {"kinetics.csv": _kinetics(KM, S0, _kinetics_row("enzyme_activity", "12", "U/mL"))},
        ("kinetics.csv", 4, "quantity", "use specific_activity"),
    ),
    "law_missing_parameter": (
        {"responses.csv": _responses(*_cardinal_temperature()[:2], *_cardinal_ph())},
        ("responses.csv", 2, "parameter", "missing: maximum_temperature"),
    ),
    "law_minimum_not_below_optimum": (
        {"responses.csv": _responses(*_cardinal_temperature(minimum="55"), *_cardinal_ph())},
        ("responses.csv", 2, "value", "minimum < optimum < maximum"),
    ),
    "law_optimum_below_ctmi_midpoint": (
        {"responses.csv": _responses(*_cardinal_temperature(optimum="35"), *_cardinal_ph())},
        ("responses.csv", 2, "value", "CTMI requires"),
    ),
    "law_ph_in_temperature_units": (
        {
            "responses.csv": _responses(
                *_cardinal_temperature(),
                _response_row("ph_cardinal_rosso", "minimum_ph", "3", "dimensionless"),
                _response_row("ph_cardinal_rosso", "optimum_ph", "5", "degC"),
                _response_row("ph_cardinal_rosso", "maximum_ph", "8", "dimensionless"),
            )
        },
        ("responses.csv", 6, "units", "pH value"),
    ),
    "law_temperature_without_units": (
        {"responses.csv": _responses(*_cardinal_temperature(units="dimensionless"), *_cardinal_ph())},
        ("responses.csv", 2, "units", "a temperature"),
    ),
    "kinetics_not_at_the_reference_condition": (
        {"responses.csv": _responses(*_cardinal_temperature(optimum="45"), *_cardinal_ph())},
        ("responses.csv", 3, "value", "The law rescales the reference value"),
    ),
    "kinetics_outside_the_stated_tolerance": (
        {"responses.csv": _responses(*_cardinal_temperature(optimum="45", tolerance="2"), *_cardinal_ph())},
        ("responses.csv", 3, "value", "reference_tolerance is 2 degC"),
    ),
    "tolerance_on_a_non_reference_row": (
        {
            "responses.csv": _responses(
                _response_row("temperature_cardinal_rosso", "minimum_temperature", "10", "degC", tolerance="1"),
                *_cardinal_temperature()[1:],
                *_cardinal_ph(),
            )
        },
        ("responses.csv", 2, "reference_tolerance", "belongs on the optimum_temperature row"),
    ),
    "unknown_law": (
        {"responses.csv": _responses(_response_row("temperature_magic", "optimum_temperature", "50", "degC"))},
        ("responses.csv", 2, "law", "not an environment-response law FungMod implements"),
    ),
    "implemented_law_not_importable": (
        {"responses.csv": _responses(_response_row("oxygen_monod", "oxygen_half_saturation", "0.1", "mM"))},
        ("responses.csv", 2, "law", "supports only"),
    ),
    "unknown_law_parameter": (
        {"responses.csv": _responses(_response_row("ph_cardinal_rosso", "ph_width", "1", "dimensionless"))},
        ("responses.csv", 2, "parameter", "not a parameter of ph_cardinal_rosso"),
    ),
    "two_temperature_laws": (
        {
            "responses.csv": _responses(
                *_cardinal_temperature(),
                _response_row("temperature_arrhenius_reference", "activation_energy", "50", "kJ/mol"),
                _response_row("temperature_arrhenius_reference", "reference_temperature", "50", "degC"),
            )
        },
        ("responses.csv", 5, "law", "one law per condition"),
    ),
    "response_as_design_value": (
        {"responses.csv": _responses(*_cardinal_temperature(evidence="design", method="chosen"))},
        ("responses.csv", 2, "evidence_type", "not a design choice"),
    ),
    "duplicate_law_parameter": (
        {"responses.csv": _responses(*_cardinal_temperature(), _cardinal_temperature()[0])},
        ("responses.csv", 5, "parameter", "give each parameter once"),
    ),
}


@pytest.mark.parametrize("case", sorted(REFUSAL_CASES))
def test_refusals_report_file_row_column_and_reason(tmp_path: Path, case: str) -> None:
    edits, (file, row, column, message) = REFUSAL_CASES[case]
    dataset_dir = _copy_fixture(tmp_path, OXIDASE, edits=edits)

    with pytest.raises(UserDataError) as excinfo:
        load_user_dataset(dataset_dir, registry=REGISTRY_INDEX)

    issues = excinfo.value.issues
    matching = [
        issue
        for issue in issues
        if issue["file"] == file and issue["row"] == row and issue["column"] == column and message in issue["message"]
    ]
    assert matching, issues


def test_reference_refusal_explains_the_rescaling(tmp_path: Path) -> None:
    edits = REFUSAL_CASES["kinetics_not_at_the_reference_condition"][0]
    with pytest.raises(UserDataError) as excinfo:
        load_user_dataset(_copy_fixture(tmp_path, OXIDASE, edits=edits), registry=REGISTRY_INDEX)
    message = next(issue["message"] for issue in excinfo.value.issues if issue["file"] == "responses.csv")
    assert "condition 'c50_ph5' (50 degC, pH 5.0" in message
    assert "optimum_temperature 45 degC" in message
    assert "differs by 5 degC" in message
    assert "rate(T) = rate(T_opt) x gamma_T(T)" in message


# ---------------------------------------------------------------------------
# Gaps


def test_gap_requests_name_both_rate_forms_when_no_form_was_started(tmp_path: Path) -> None:
    dataset = _load(tmp_path, {"kinetics.csv": _kinetics(KM, S0)})
    expected = (
        "Measure kcat and the enzyme concentration of laccase-like oxidase from Oxidase source strain L1 on "
        "syringaldazine-like phenolic azine at 50 degC, pH 5.0, or Vmax (or a specific activity and enzyme loading)."
    )
    for quantity in ("kcat", "enzyme_concentration"):
        gap = _parameter(dataset, f"{PREFIX}c50_ph5__{quantity}__gap")
        assert gap.allowed_use == PARAMETER_ALLOWED_USE_GAP_ANALYSIS_ONLY
        assert gap.provenance["measurement_request"] == expected

    study = virtual_experiment(fungi="strain_l1", substrates="syringaldazine_like", environments="c50_ph5", user_data=dataset)
    report = study.preflight(mode="exploratory")[0]
    assert report.status == "underparameterized"
    assert report.suggested_experiments == (expected,)


def test_vmax_gap_names_the_missing_input_of_the_started_route(tmp_path: Path) -> None:
    dataset = _load(tmp_path, {"kinetics.csv": _kinetics(KM, S0, SPECIFIC_ACTIVITY)})
    gap = _parameter(dataset, f"{PREFIX}c50_ph5__vmax__gap")
    assert gap.value.is_unknown
    assert gap.value.units is None
    assert "concentration per time" in gap.notes
    request = gap.provenance["measurement_request"]
    assert request.startswith("Measure or specify the enzyme loading (enzyme mass per volume) of laccase-like oxidase")
    assert request.endswith("to derive Vmax from the specific activity in kinetics.csv row 4.")
    assert not any(record_id.endswith("__kcat__gap") for record_id in _records(dataset, "parameter_records"))


def test_second_strain_without_responses_gets_law_gaps_and_must_share_the_rate_form(tmp_path: Path) -> None:
    strains = (OXIDASE / "strains.csv").read_text(encoding="utf-8") + "strain_l2,Oxidase source strain L2,,\n"
    enzymes = (OXIDASE / "enzymes.csv").read_text(encoding="utf-8") + f'strain_l2,laccase_like_oxidase,activity assay,"{SOURCE}"\n'
    second = "strain_l2,laccase_like_oxidase,syringaldazine_like,c50_ph5"
    vmax_rows = (
        _kinetics_row("km", "25", "µM", case=second),
        _kinetics_row("substrate_initial_concentration", "50", "µM", case=second),
        _kinetics_row("vmax", "0.4", "µM/min", method="initial-rate fit", case=second),
    )
    dataset = _load(
        tmp_path / "gaps",
        {
            "strains.csv": strains,
            "enzymes.csv": enzymes,
            "kinetics.csv": _kinetics(KM, S0, SPECIFIC_ACTIVITY, LOADING, *vmax_rows),
        },
    )
    law_gap = _parameter(
        dataset,
        "oxidase_demo__strain_l2__laccase_like_oxidase__syringaldazine_like__temperature_cardinal_rosso__optimum_temperature__gap",
    )
    assert law_gap.value.is_unknown
    assert law_gap.environment_id is None
    assert law_gap.provenance["measurement_request"] == (
        "Measure the optimum temperature of the cardinal temperature law (Rosso CTMI) for laccase-like oxidase from "
        "Oxidase source strain L2 on syringaldazine-like phenolic azine (a temperature (degC or kelvin)); "
        "responses.csv binds this law to laccase-like oxidase on syringaldazine-like phenolic azine for another strain."
    )
    report = virtual_experiment(
        fungi="strain_l2", substrates="syringaldazine_like", environments="c50_ph5", user_data=dataset
    ).preflight(mode="exploratory")[0]
    assert report.status == "underparameterized"
    assert {item.item_id for item in report.missing} == {
        f"oxidase_demo__{law}__{parameter}__laccase_like_oxidase__syringaldazine_like"
        for law, parameters in (
            ("temperature_cardinal_rosso", ("minimum_temperature", "optimum_temperature", "maximum_temperature")),
            ("ph_cardinal_rosso", ("minimum_ph", "optimum_ph", "maximum_ph")),
        )
        for parameter in parameters
    }

    kcat_rows = (
        _kinetics_row("km", "25", "µM", case=second),
        _kinetics_row("kcat", "30", "1/min", case=second),
        _kinetics_row("enzyme_concentration", "0.05", "µM", case=second),
    )
    with pytest.raises(UserDataError) as excinfo:
        _load(
            tmp_path / "forms",
            {
                "strains.csv": strains,
                "enzymes.csv": enzymes,
                "kinetics.csv": _kinetics(KM, S0, SPECIFIC_ACTIVITY, LOADING, *kcat_rows),
            },
        )
    assert any(
        issue["file"] == "kinetics.csv" and issue["column"] == "quantity" and "must use one rate form" in issue["message"]
        for issue in excinfo.value.issues
    ), excinfo.value.issues


# ---------------------------------------------------------------------------
# Laws are existing template modifiers, not new ones


def test_importable_laws_are_existing_template_modifiers_with_their_roles() -> None:
    # The laws that scale the catalytic rate; the law that scales the enzyme's inactivation constant is the existing
    # thermal_inactivation process law (USERDATA-011, tests/test_user_data_inactivation.py).
    rate_laws = {name: law for name, law in RESPONSE_LAWS.items() if law.scales == LAW_SCALES_RATE}
    assert set(RESPONSE_LAWS) - set(rate_laws) == {"thermal_inactivation"}
    assert set(rate_laws) <= ENVIRONMENT_MODIFIER_TYPES
    assert VMAX_ROUTES == ("vmax", "specific_activity", "assay_activity")
    for name, law in rate_laws.items():
        fields = _MODIFIER_COMPATIBILITY_ROLE_BY_FIELD[name]
        for parameter in law.parameters:
            assert fields[f"{parameter.name}_role"] == parameter.name
        assert law.reference_parameter in law.parameter_names
