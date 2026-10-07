"""User-supplied enzyme and kinetics tables as an in-memory registry overlay.

A user directory holds a manifest (``user_dataset.yml``) and CSV tables of
strains, their enzyme classes, substrates, assay conditions and kinetic values.
``load_user_dataset`` validates every table, collects every problem before it
raises, and turns the tables into production registry mappings: one fungus per
strain, one namespaced enzyme class per declared class, one homogeneous
Michaelis-Menten compatibility and case template per compatible class and
substrate pair, one parameter record per kinetics row, and one explicit
unknown parameter record (a gap) for every required role that has no row.

Every generated identifier carries the ``<dataset_id>__`` prefix and every
parameter record carries the reserved ``fungmod_user_dataset`` provenance
namespace (dataset, digest, file and row). Nothing is written to the shared
registry: ``UserDataset.overlay`` returns a new in-memory registry.

Scope: dissolved substrates and homogeneous Michaelis-Menten kinetics in one
of two rate forms per enzyme class and substrate, either ``kcat`` with an
enzyme concentration or a maximum rate ``Vmax`` for the simulated system.
``Vmax`` comes from exactly one route per case: an explicit ``vmax`` row, a
specific activity times an enzyme loading (a derived record whose maturity is
the weaker input's), or an assay activity measured on the case substrate at
saturation. Products are stoichiometric with an explicit mol/mol yield. An
optional ``responses.csv`` binds the parameters of an existing temperature or
pH response law (cardinal temperature, cardinal pH, Arrhenius) to a strain,
enzyme class and substrate; the law enters the generated case template as a
process modifier, and the kinetic constants of that case must be stated at the
law's reference condition.

An optional ``genomes.csv`` points each strain to a dbCAN ``overview.txt``
inside the dataset directory. The annotation is resolved to enzyme classes
with the existing ``CapabilityResolver`` and its curated CAZy family map.
Resolved classes with a registry record join the strain's declared classes
(an explicit ``enzymes.csv`` row wins and keeps both pieces of evidence);
resolved classes without a record and unmapped families are reported, never
turned into records. A genome states which classes a strain can encode, not a
rate: every resolved class without kinetics becomes the usual explicit gaps,
whose measurement requests name the annotation.

A ``genomes.csv`` row may instead point to a UniProtKB TSV export of the
strain's proteome (``annotation_tool`` ``UniProt`` with a release or download
date). Its CAZy cross-references resolve through the same resolver and family
map, its complete EC numbers through the registry's EC lookup, and a protein
whose two annotations name different classes supports neither; see
``fungal_model.capability.uniprot``. The outputs carry ``source_type``
``uniprot_proteome`` and the accessions behind every class.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import MappingProxyType
from typing import Any, TypeVar, cast

import yaml

from fungal_model.capability.dbcan import TOOL_COLUMNS, DbcanOverview, parse_overview
from fungal_model.capability.uniprot import (
    CLAIM_BOUNDARY as UNIPROT_CLAIM_BOUNDARY,
    COMPARISON_RULE as UNIPROT_COMPARISON_RULE,
    ProteomeClassSupport,
    ProteomeResolution,
    UniprotProteome,
    decode_uniprot_tsv,
    parse_uniprot_tsv,
    resolve_uniprot_proteome,
)
from fungal_model.capability.resolution import (
    DIAGNOSTIC,
    POLYSPECIFIC,
    CapabilityResolutionError,
    CapabilityResolver,
    CazymeAnnotation,
    CazymeFamilyMap,
    ResolvedCapability,
    default_family_map_path,
)
from fungal_model.core.provenance import ProvenanceError
from fungal_model.core.units import Q_, units_are_compatible
from fungal_model.kinetics.arrhenius import arrhenius_reference_scaled_rate
from fungal_model.kinetics.cardinal import cardinal_ph_activity, cardinal_temperature_activity
from fungal_model.provenance import USER_DATASET_PROVENANCE_KEY
from fungal_model.registry.loaders import (
    RegistryLoadError,
    RegistryRecordType,
    load_registry,
    load_registry_record_mapping,
)
from fungal_model.registry.records import (
    CASE_TEMPLATE_SCHEMA_VERSION,
    CaseTemplateRecord,
    EnvironmentRecord,
    EnzymeClassRecord,
    FungusRecord,
    PARAMETER_ALLOWED_USE_EXPLORATORY,
    PARAMETER_ALLOWED_USE_EXPLORATORY_SCREENING,
    PARAMETER_ALLOWED_USE_GAP_ANALYSIS_ONLY,
    PARAMETER_ALLOWED_USE_SCIENTIFIC,
    ParameterRecord,
    ProcessCompatibilityRecord,
    RegistryRecord,
    SubstrateRecord,
    parameter_record_is_mode_eligible,
)
from fungal_model.registry.resolver import AmbiguousResolutionError, RegistryResolver, ResolutionError
from fungal_model.registry.store import FungModRegistry, RegistryValidationError
from fungal_model.resources import default_registry_path
from fungal_model.screening.case_builder import (
    HOMOGENEOUS_MM_PARAMETER_ROLES,
    HOMOGENEOUS_MM_VMAX_PARAMETER_ROLES,
)
from fungal_model.screening.template_environment_modifiers import (
    ENVIRONMENT_MODIFIER_CONDITIONS,
    ENVIRONMENT_MODIFIER_TYPES,
)

_RecordT = TypeVar("_RecordT", bound=RegistryRecord)

USER_DATASET_SCHEMA_VERSION = "1"
USER_DATASET_MANIFEST = "user_dataset.yml"
USER_DATASET_PROCESS_TYPE = "homogeneous_michaelis_menten"

USER_DATASET_MATURITY_MEASURED = "user_measured"
USER_DATASET_MATURITY_LITERATURE = "user_reported_literature"
USER_DATASET_MATURITY_DESIGN = "user_design_value"
USER_DATASET_MATURITY_ESTIMATE = "exploratory_prior"
USER_DATASET_MATURITY_GAP = "user_dataset_gap"
USER_DATASET_RECORD_MATURITY = "user_supplied_metadata"
USER_DATASET_PARAMETER_MATURITIES = frozenset(
    {
        USER_DATASET_MATURITY_MEASURED,
        USER_DATASET_MATURITY_LITERATURE,
        USER_DATASET_MATURITY_DESIGN,
    }
)

EVIDENCE_TYPES = ("measured", "literature", "design", "estimate")
RESPONSE_EVIDENCE_TYPES = ("measured", "literature", "estimate")
_EVIDENCE_MATURITY = {
    "measured": USER_DATASET_MATURITY_MEASURED,
    "literature": USER_DATASET_MATURITY_LITERATURE,
    "design": USER_DATASET_MATURITY_DESIGN,
    "estimate": USER_DATASET_MATURITY_ESTIMATE,
}
_EVIDENCE_REQUIRES_METHOD = frozenset({"measured", "literature", "design"})
# Weakest first. A record derived from several user rows, and every parameter
# of one response law, takes the weakest maturity of its inputs.
USER_DATASET_MATURITY_ORDER = (
    USER_DATASET_MATURITY_ESTIMATE,
    USER_DATASET_MATURITY_DESIGN,
    USER_DATASET_MATURITY_LITERATURE,
    USER_DATASET_MATURITY_MEASURED,
)
_MATURITY_ORDER_TEXT = " < ".join(USER_DATASET_MATURITY_ORDER)

KINETIC_QUANTITIES = (
    "km",
    "kcat",
    "substrate_initial_concentration",
    "enzyme_concentration",
    "vmax",
    "specific_activity",
    "enzyme_loading",
    "assay_activity",
)
_QUANTITY_ROLE = {
    "km": "km",
    "kcat": "kcat",
    "substrate_initial_concentration": "substrate_initial_concentration",
    "enzyme_concentration": "enzyme_initial_concentration",
    "vmax": "vmax",
}
_ROLE_QUANTITY = {role: quantity for quantity, role in _QUANTITY_ROLE.items()}
_CONCENTRATION_QUANTITIES = ("substrate_initial_concentration", "km", "enzyme_concentration")
# Quantities that are kinetic constants measured at a condition; a bound
# response law rescales them, so they must be stated at its reference condition.
_KINETIC_CONSTANT_QUANTITIES = frozenset({"km", "kcat", "vmax", "specific_activity", "assay_activity"})
_YIELD_BASIS = "mol/mol"
_UNKNOWN_CELL = "unknown"
_YES = "yes"
_NO = "no"

# Rate forms of homogeneous Michaelis-Menten kinetics and the quantities each
# generates records for, in record order.
RATE_FORM_KCAT = "kcat_enzyme"
RATE_FORM_VMAX = "vmax"
_FORM_QUANTITIES = {
    RATE_FORM_KCAT: tuple(_ROLE_QUANTITY[role] for role in HOMOGENEOUS_MM_PARAMETER_ROLES),
    RATE_FORM_VMAX: tuple(_ROLE_QUANTITY[role] for role in HOMOGENEOUS_MM_VMAX_PARAMETER_ROLES),
}
_KCAT_FORM_QUANTITIES = ("kcat", "enzyme_concentration")
# Routes to Vmax; one case uses exactly one.
VMAX_ROUTES = ("vmax", "specific_activity", "assay_activity")
_VMAX_ROUTE_QUANTITIES = {
    "vmax": ("vmax",),
    "specific_activity": ("specific_activity", "enzyme_loading"),
    "assay_activity": ("assay_activity",),
}
_QUANTITY_VMAX_ROUTE = {
    quantity: route for route, quantities in _VMAX_ROUTE_QUANTITIES.items() for quantity in quantities
}
_VMAX_ROUTE_LABEL = {
    "vmax": "an explicit vmax row",
    "specific_activity": "specific_activity x enzyme_loading",
    "assay_activity": "a saturating assay_activity on the case substrate",
}
_ACTIVITY_COLUMNS = ("activity_substrate", "activity_saturating")
_RETIRED_QUANTITY_HINTS = {
    "enzyme_activity": (
        "quantity 'enzyme_activity' is ambiguous; use specific_activity (amount per time per enzyme mass, "
        "with an enzyme_loading row) or assay_activity (amount per time per volume of the simulated system, "
        "measured on the case substrate at saturation)."
    ),
}

GENOME_TABLE = "genomes.csv"
# Annotation tools whose output ``genomes.csv`` reads; the first token of
# ``annotation_tool`` must name one of them, and the rest is its version.
GENOME_ANNOTATION_TOOLS = ("dbCAN", "UniProt")
_DBCAN_TOOL_PATTERN = re.compile(r"^(?:run_)?dbcan\d*$", re.IGNORECASE)
_UNIPROT_TOOL_PATTERN = re.compile(r"^uniprot(?:kb)?$", re.IGNORECASE)
# The source type of a genomes.csv row read from a UniProtKB TSV export; dbCAN entries keep their earlier form.
UNIPROT_SOURCE_TYPE = "uniprot_proteome"
_UNIPROT_PROTEOME_ID = re.compile(r"\bUP\d+\b")
# Accessions quoted in one measurement request; the provenance lists them all.
_REQUEST_ACCESSION_LIMIT = 10
_GENOME_CLAIM_BOUNDARY = (
    "Enzyme classes inferred from a genome annotation state what the strain can encode, not what it "
    "expresses, secretes or how fast; no rate, kinetic constant or expression level is taken from the genome."
)

_REQUIRED_TABLES = ("strains.csv", "enzymes.csv", "substrates.csv", "conditions.csv", "kinetics.csv")
_OPTIONAL_TABLES = ("enzyme_classes.csv", "responses.csv", GENOME_TABLE)
_TABLE_COLUMNS: Mapping[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "strains.csv": (("strain_id", "name"), ("scientific_name", "aliases")),
    "enzymes.csv": (("strain_id", "enzyme_class", "evidence", "source"), ()),
    "enzyme_classes.csv": (
        ("class_id", "name", "target_bond_classes", "compatible_substrate_classes", "source"),
        ("ec_number",),
    ),
    "substrates.csv": (
        ("substrate_id", "product", "product_yield", "yield_basis", "source"),
        ("registry_substrate", "name", "substrate_class", "physical_state", "bond_classes"),
    ),
    "conditions.csv": (("condition_id", "temperature", "temperature_units", "ph"), ("notes",)),
    "kinetics.csv": (
        ("strain_id", "enzyme_class", "substrate_id", "condition_id", "quantity", "units", "evidence_type", "source"),
        ("value", "lower", "upper", "method", "sd", "replicates", *_ACTIVITY_COLUMNS),
    ),
    "responses.csv": (
        ("strain_id", "enzyme_class", "substrate_id", "law", "parameter", "value", "units", "evidence_type", "source"),
        ("method", "reference_tolerance", "kinetics_at_reference"),
    ),
    GENOME_TABLE: (("strain_id", "annotation_file", "annotation_tool", "source"), ("min_tools_agreeing",)),
}
_TABLES_WITH_ROWS_REQUIRED = ("strains.csv", "enzymes.csv", "substrates.csv", "conditions.csv")
_MANIFEST_FIELDS = frozenset({"dataset_id", "contributor", "date", "source", "notes", "simulation"})
_SIMULATION_FIELDS = frozenset({"duration", "units", "points"})
_USER_SUBSTRATE_FIELDS = ("name", "substrate_class", "physical_state", "bond_classes")

_DATASET_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9]+(?:_[A-Za-z0-9]+)*$")
_CLASS_TOKEN_PATTERN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
_EC_NUMBER_PATTERN = re.compile(r"^\d+\.(?:\d+|-)\.(?:\d+|-)\.(?:n?\d+|-)$")
_TEMPERATURE_UNITS = {"degC": "degC", "kelvin": "kelvin"}
_MOLAR_REFERENCE_UNITS = "mol / liter"
_MASS_REFERENCE_UNITS = "gram / liter"
_RATE_CONSTANT_REFERENCE_UNITS = "1 / second"
_TIME_REFERENCE_UNITS = "second"
_MOLAR_RATE_REFERENCE_UNITS = "mol / liter / second"
_MASS_RATE_REFERENCE_UNITS = "gram / liter / second"
_SPECIFIC_ACTIVITY_REFERENCE_UNITS = "mol / second / gram"
_TEMPERATURE_REFERENCE_UNITS = "kelvin"
_DIMENSIONLESS_REFERENCE_UNITS = "dimensionless"
_MOLAR_ENERGY_REFERENCE_UNITS = "joule / mole"


@dataclass(frozen=True)
class ResponseLawParameter:
    """One parameter of an importable environment-response law."""

    name: str
    label: str
    reference_units: str
    dimension_text: str


@dataclass(frozen=True)
class ResponseLaw:
    """An existing environment-response law that ``responses.csv`` may bind.

    ``law`` is the process-modifier type the case-template machinery already
    implements; ``parameters`` are its template roles, each bound through the
    modifier field ``<name>_role``; ``reference_parameter`` names the parameter
    at whose value the law's activity is one, so kinetic constants scaled by
    the law must be stated there.
    """

    law: str
    label: str
    parameters: tuple[ResponseLawParameter, ...]
    reference_parameter: str
    formula: str

    @property
    def condition(self) -> str:
        return ENVIRONMENT_MODIFIER_CONDITIONS[self.law]

    @property
    def parameter_names(self) -> tuple[str, ...]:
        return tuple(parameter.name for parameter in self.parameters)

    def parameter(self, name: str) -> ResponseLawParameter:
        return next(parameter for parameter in self.parameters if parameter.name == name)


def _temperature_parameter(name: str, label: str) -> ResponseLawParameter:
    return ResponseLawParameter(name, label, _TEMPERATURE_REFERENCE_UNITS, "a temperature (degC or kelvin)")


def _ph_parameter(name: str, label: str) -> ResponseLawParameter:
    return ResponseLawParameter(name, label, _DIMENSIONLESS_REFERENCE_UNITS, "a pH value (units dimensionless)")


RESPONSE_LAWS: Mapping[str, ResponseLaw] = MappingProxyType(
    {
        law.law: law
        for law in (
            ResponseLaw(
                law="temperature_cardinal_rosso",
                label="cardinal temperature law (Rosso CTMI)",
                parameters=(
                    _temperature_parameter("minimum_temperature", "minimum temperature"),
                    _temperature_parameter("optimum_temperature", "optimum temperature"),
                    _temperature_parameter("maximum_temperature", "maximum temperature"),
                ),
                reference_parameter="optimum_temperature",
                formula="rate(T) = rate(T_opt) x gamma_T(T); gamma_T is one at T_opt and zero at and beyond T_min and T_max",
            ),
            ResponseLaw(
                law="ph_cardinal_rosso",
                label="cardinal pH law (Rosso CPM)",
                parameters=(
                    _ph_parameter("minimum_ph", "minimum pH"),
                    _ph_parameter("optimum_ph", "optimum pH"),
                    _ph_parameter("maximum_ph", "maximum pH"),
                ),
                reference_parameter="optimum_ph",
                formula="rate(pH) = rate(pH_opt) x gamma_pH(pH); gamma_pH is one at pH_opt and zero at and beyond pH_min and pH_max",
            ),
            ResponseLaw(
                law="temperature_arrhenius_reference",
                label="Arrhenius reference-temperature law",
                parameters=(
                    ResponseLawParameter(
                        "activation_energy",
                        "activation energy",
                        _MOLAR_ENERGY_REFERENCE_UNITS,
                        "an energy per amount (for example kJ/mol)",
                    ),
                    _temperature_parameter("reference_temperature", "reference temperature"),
                ),
                reference_parameter="reference_temperature",
                formula="rate(T) = rate(T_ref) x exp(-Ea / R x (1/T - 1/T_ref))",
            ),
        )
    }
)

_RECORD_TYPES = (
    "fungi",
    "enzyme_classes",
    "substrates",
    "environments",
    "process_compatibility",
    "case_templates",
    "parameter_records",
)
_IDENTITY_RESOLVERS = {
    "fungi": "resolve_fungus",
    "enzyme_classes": "resolve_enzyme_class",
    "substrates": "resolve_substrate",
    "environments": "resolve_environment",
}


class UserDataError(ValueError):
    """Raised when a user dataset is incomplete, inconsistent, or unsupported.

    ``issues`` lists every problem found, each a mapping with ``file``,
    ``row`` (the spreadsheet line number, or ``None`` for file-level and
    manifest problems), ``column`` (or ``None``) and ``message``.
    """

    def __init__(self, message: str, *, issues: Sequence[Mapping[str, Any]]) -> None:
        self.issues: list[dict[str, Any]] = [dict(issue) for issue in issues]
        lines = "\n".join(f"- {_issue_text(issue)}" for issue in self.issues)
        super().__init__(f"{message} {len(self.issues)} issue(s):\n{lines}" if self.issues else message)


@dataclass(frozen=True)
class UserDataset:
    """A validated user dataset and the registry mappings generated from it.

    ``records`` maps each production record type (``fungi``,
    ``enzyme_classes``, ``substrates``, ``environments``,
    ``process_compatibility``, ``case_templates``, ``parameter_records``) to
    the generated mappings, each accepted by ``load_registry_record_mapping``.
    ``digest`` is the SHA-256 over the manifest, table and annotation-file
    bytes in file-name order; every generated parameter record cites it.

    With a ``genomes.csv``, ``genome_annotations`` describes each annotation
    read (file, digest, tool and version, consensus rule, families),
    ``genome_resolved_classes`` lists the resolved classes with a registry
    record that joined a strain (or matched an explicit ``enzymes.csv`` row),
    ``unmodellable_enzyme_classes`` the resolved classes without a registry
    record (reported, never generated) and ``unmapped_families`` the families
    the CAZy family map assigns to no class. All four are empty without a
    ``genomes.csv``. Entries of a row read from a UniProt export carry
    ``source_type`` ``uniprot_proteome`` and the accessions behind each class
    or family (``accessions``, ``accession_count``); its ``genome_annotations``
    entry also lists the unresolved and partial EC numbers and the proteins
    whose EC numbers and CAZy families disagree. Entries of a dbCAN row keep
    their earlier keys.
    """

    dataset_id: str
    digest: str
    records: Mapping[str, tuple[Mapping[str, Any], ...]]
    source_directory: str = ""
    manifest: Mapping[str, Any] = field(default_factory=dict)
    file_digests: Mapping[str, str] = field(default_factory=dict)
    base_registry_id: str = ""
    genome_annotations: tuple[Mapping[str, Any], ...] = ()
    genome_resolved_classes: tuple[Mapping[str, Any], ...] = ()
    unmodellable_enzyme_classes: tuple[Mapping[str, Any], ...] = ()
    unmapped_families: tuple[Mapping[str, Any], ...] = ()
    _record_objects: Mapping[str, tuple[RegistryRecord, ...]] = field(
        default_factory=dict, repr=False, compare=False
    )
    _base_references: Mapping[tuple[str, str], Mapping[str, Any]] = field(
        default_factory=dict, repr=False, compare=False
    )
    _origins: Mapping[tuple[str, str], tuple[str, int | None, str | None]] = field(
        default_factory=dict, repr=False, compare=False
    )

    def overlay(self, base: FungModRegistry) -> FungModRegistry:
        """Return a new in-memory registry holding ``base`` plus this dataset's records.

        The base registry must contain the registry records the dataset
        references unchanged, and no generated identifier, name or alias may
        collide with a base record. ``base`` itself is not modified.
        """

        issues = _overlay_issues(self, base)
        if issues:
            raise UserDataError(
                f"User dataset {self.dataset_id!r} cannot be overlaid on registry {base.registry_id!r}.",
                issues=issues,
            )
        overlays = base.provenance.get("user_dataset_overlays", [])
        provenance = {
            **dict(base.provenance),
            "user_dataset_overlays": [
                *(overlays if isinstance(overlays, list) else []),
                {
                    "dataset_id": self.dataset_id,
                    "digest": self.digest,
                    "record_counts": {name: len(self.records.get(name, ())) for name in _RECORD_TYPES},
                    "notes": (
                        "In-memory overlay of user-supplied records; nothing is written to "
                        "data_registry and nothing is promoted into the shared registry."
                    ),
                },
            ],
        }
        objects = self._record_objects
        try:
            return FungModRegistry.build(
                registry_id=base.registry_id,
                version=base.version,
                maturity=base.maturity,
                provenance=provenance,
                fungi=(*base.fungi.values(), *_objects_of(objects, "fungi", FungusRecord)),
                enzyme_classes=(
                    *base.enzyme_classes.values(),
                    *_objects_of(objects, "enzyme_classes", EnzymeClassRecord),
                ),
                substrates=(*base.substrates.values(), *_objects_of(objects, "substrates", SubstrateRecord)),
                environments=(
                    *base.environments.values(),
                    *_objects_of(objects, "environments", EnvironmentRecord),
                ),
                process_compatibility=(
                    *base.process_compatibility.values(),
                    *_objects_of(objects, "process_compatibility", ProcessCompatibilityRecord),
                ),
                parameters=(*base.parameters.values(), *_objects_of(objects, "parameter_records", ParameterRecord)),
                case_templates=(
                    *base.case_templates.values(),
                    *_objects_of(objects, "case_templates", CaseTemplateRecord),
                ),
                product_maps=base.product_maps.values(),
            )
        except RegistryValidationError as exc:
            raise UserDataError(
                f"User dataset {self.dataset_id!r} produced records the registry rejected.",
                issues=[_issue(USER_DATASET_MANIFEST, None, None, str(exc))],
            ) from exc

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": "fungmod_user_dataset",
            "schema_version": USER_DATASET_SCHEMA_VERSION,
            "dataset_id": self.dataset_id,
            "digest": self.digest,
            "source_directory": self.source_directory,
            "manifest": _plain(self.manifest),
            "file_digests": dict(self.file_digests),
            "base_registry_id": self.base_registry_id,
            "records": {name: [_plain(mapping) for mapping in self.records.get(name, ())] for name in _RECORD_TYPES},
            **self._genome_lists(),
        }

    def summary(self) -> dict[str, Any]:
        """Return the dataset id, digest, generated record counts and the genome-resolution lists."""

        return {
            "dataset_id": self.dataset_id,
            "digest": self.digest,
            "record_counts": {name: len(self.records.get(name, ())) for name in _RECORD_TYPES},
            **self._genome_lists(),
        }

    def _genome_lists(self) -> dict[str, list[Any]]:
        return {
            "genome_annotations": [_plain(item) for item in self.genome_annotations],
            "genome_resolved_classes": [_plain(item) for item in self.genome_resolved_classes],
            "unmodellable_enzyme_classes": [_plain(item) for item in self.unmodellable_enzyme_classes],
            "unmapped_families": [_plain(item) for item in self.unmapped_families],
        }


def load_user_dataset(
    path: str | Path,
    *,
    registry: str | Path | FungModRegistry | None = None,
) -> UserDataset:
    """Validate a user dataset directory and generate its registry mappings.

    ``registry`` is the base registry used to resolve registry substrates and
    enzyme classes and to refuse colliding identifiers; it defaults to the
    packaged registry. Every problem in the directory is collected before a
    single ``UserDataError`` is raised.
    """

    base = _base_registry(registry)
    directory = Path(path)
    if not directory.is_dir():
        raise UserDataError(
            f"User dataset path {str(directory)!r} is not a directory.",
            issues=[_issue(str(directory), None, None, "Expected a directory holding user_dataset.yml and CSV tables.")],
        )
    issues: list[dict[str, Any]] = []
    raw_files = _read_dataset_files(directory, issues)
    manifest = _parse_manifest(raw_files.get(USER_DATASET_MANIFEST), issues)
    # With a genome table the strain's classes may come from its annotation alone,
    # so enzymes.csv may then hold only its header; every strain still needs a class.
    rows_required = tuple(
        name for name in _TABLES_WITH_ROWS_REQUIRED if not (name == "enzymes.csv" and GENOME_TABLE in raw_files)
    )
    tables = {
        name: _parse_table(name, raw_files[name], issues, rows_required=name in rows_required)
        for name in _TABLE_COLUMNS
        if name in raw_files
    }
    context = _Context(base=base, issues=issues)
    parsed = _parse_rows(tables, context, directory=directory)
    if parsed is not None:
        _cross_validate(parsed, context)
        # Annotation files are inputs like the tables: their bytes enter the digest.
        raw_files = {**raw_files, **parsed.annotation_files}
    digest = _dataset_digest(raw_files)
    dataset_id = str(manifest.get("dataset_id", "")) if manifest else ""
    if issues or parsed is None or manifest is None:
        raise UserDataError(f"User dataset {str(directory)!r} is invalid.", issues=issues)
    generated = _generate_records(
        parsed,
        context,
        dataset_id=dataset_id,
        digest=digest,
        manifest=manifest,
    )
    if issues:
        raise UserDataError(f"User dataset {str(directory)!r} is invalid.", issues=issues)
    genome_report = _genome_report(parsed, dataset_id=dataset_id)
    dataset = UserDataset(
        dataset_id=dataset_id,
        digest=digest,
        records=MappingProxyType({name: tuple(generated.mappings[name]) for name in _RECORD_TYPES}),
        source_directory=str(directory.resolve()),
        manifest=MappingProxyType(dict(manifest)),
        file_digests=MappingProxyType({name: hashlib.sha256(data).hexdigest() for name, data in sorted(raw_files.items())}),
        base_registry_id=base.registry_id,
        genome_annotations=genome_report["genome_annotations"],
        genome_resolved_classes=genome_report["genome_resolved_classes"],
        unmodellable_enzyme_classes=genome_report["unmodellable_enzyme_classes"],
        unmapped_families=genome_report["unmapped_families"],
        _record_objects=MappingProxyType({name: tuple(generated.objects[name]) for name in _RECORD_TYPES}),
        _base_references=MappingProxyType(dict(generated.base_references)),
        _origins=MappingProxyType(dict(generated.origins)),
    )
    dataset.overlay(base)
    return dataset


# ---------------------------------------------------------------------------
# Reading and parsing


@dataclass
class _Context:
    base: FungModRegistry
    issues: list[dict[str, Any]]

    def add(self, file: str, row: int | None, column: str | None, message: str) -> None:
        self.issues.append(_issue(file, row, column, message))


@dataclass(frozen=True)
class _Strain:
    row: int
    strain_id: str
    name: str
    scientific_name: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class _EnzymeClassInfo:
    key: str
    origin: str
    name: str
    ec_number: str
    target_bond_classes: tuple[str, ...]
    compatible_substrate_classes: tuple[str, ...]
    source: str
    row: int | None
    parent_maturity: str = ""


@dataclass(frozen=True)
class _GenomeClassEvidence:
    """The genome-annotation evidence for one enzyme class of one strain."""

    genome_row: int
    annotation_file: str
    annotation_sha256: str
    tool: str
    tool_version: str
    families: tuple[str, ...]
    gene_ids: tuple[str, ...]
    specificity: str
    consensus_rule: str
    source: str

    @property
    def gene_count(self) -> int:
        return len(self.gene_ids)

    @property
    def evidence_text(self) -> str:
        genes = "gene" if self.gene_count == 1 else "genes"
        return f"genome annotation ({self.tool}, {self.gene_count} {genes}, families {', '.join(self.families)})"

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": GENOME_TABLE,
            "row": self.genome_row,
            "evidence": self.evidence_text,
            "source": self.source,
            "annotation_file": self.annotation_file,
            "annotation_sha256": self.annotation_sha256,
            "annotation_tool": self.tool,
            "annotation_tool_version": self.tool_version,
            "families": list(self.families),
            "gene_count": self.gene_count,
            "gene_ids": list(self.gene_ids),
            "specificity": self.specificity,
            "consensus_rule": self.consensus_rule,
            "claim_boundary": _GENOME_CLAIM_BOUNDARY,
        }


@dataclass(frozen=True)
class _ProteomeClassEvidence:
    """The UniProt-proteome evidence for one enzyme class of one strain: the accessions behind it."""

    genome_row: int
    annotation_file: str
    annotation_sha256: str
    tool: str
    tool_version: str
    source: str
    proteome_id: str | None
    organism_id: str
    review_column: bool
    support: ProteomeClassSupport

    @property
    def label(self) -> str:
        if self.proteome_id:
            return f"UniProt proteome {self.proteome_id}"
        return f"UniProt export {self.annotation_file}"

    @property
    def evidence_text(self) -> str:
        count = len(self.support.accessions)
        parts = [f"{count} {'protein' if count == 1 else 'proteins'}"]
        if self.support.families:
            parts.append(f"CAZy families {', '.join(self.support.families)}")
        if self.support.ec_numbers:
            parts.append(f"EC {', '.join(self.support.ec_numbers)}")
        return f"{self.label} ({', '.join(parts)})"

    def request_note(self) -> str:
        """The clause a measurement request ends with: the proteome, the accessions and the evidence."""

        accessions = self.support.accessions
        shown = ", ".join(accessions[:_REQUEST_ACCESSION_LIMIT])
        if len(accessions) > _REQUEST_ACCESSION_LIMIT:
            shown = f"{shown} and {len(accessions) - _REQUEST_ACCESSION_LIMIT} more"
        parts = [f"accessions {shown}"]
        if self.support.families:
            parts.append(f"CAZy families {', '.join(self.support.families)}")
        if self.support.ec_numbers:
            parts.append(f"EC {', '.join(self.support.ec_numbers)}")
        parts.append(
            f"{len(self.support.reviewed_accessions)} of {len(accessions)} reviewed in Swiss-Prot"
            if self.review_column
            else "review status not in the export"
        )
        if self.support.specificity == POLYSPECIFIC:
            parts.append("family membership is polyspecific, so the activity itself needs confirming")
        return f"the class was inferred from {self.label} ({'; '.join(parts)})"

    def to_dict(self) -> dict[str, Any]:
        support = self.support
        return {
            "file": GENOME_TABLE,
            "row": self.genome_row,
            "evidence": self.evidence_text,
            "source": self.source,
            "source_type": UNIPROT_SOURCE_TYPE,
            "annotation_file": self.annotation_file,
            "annotation_sha256": self.annotation_sha256,
            "annotation_tool": self.tool,
            "annotation_tool_version": self.tool_version,
            "proteome_id": self.proteome_id,
            "organism_id": self.organism_id or None,
            "families": list(support.families),
            "ec_numbers": list(support.ec_numbers),
            "accessions": list(support.accessions),
            "accession_count": len(support.accessions),
            "accessions_by_basis": {basis: list(items) for basis, items in support.accessions_by_basis.items()},
            "reviewed_accessions": list(support.reviewed_accessions),
            "specificity": support.specificity,
            "comparison_rule": UNIPROT_COMPARISON_RULE,
            "claim_boundary": UNIPROT_CLAIM_BOUNDARY,
        }


# The genomes.csv evidence of one class: a dbCAN annotation or a UniProt proteome export.
_ClassEvidence = _GenomeClassEvidence | _ProteomeClassEvidence


@dataclass(frozen=True)
class _StrainClass:
    row: int
    strain_id: str
    class_key: str
    evidence: str
    source: str
    # enzymes.csv for an explicit row; genomes.csv for a class the annotation alone declares.
    file: str = "enzymes.csv"
    # Genome evidence, also attached to an explicit row whose class the annotation resolves.
    genome: _ClassEvidence | None = None

    @property
    def genome_only(self) -> bool:
        return self.file == GENOME_TABLE


@dataclass(frozen=True)
class _GenomeAnnotation:
    """One genomes.csv row whose annotation was read and resolved."""

    row: int
    strain_id: str
    annotation_file: str
    annotation_sha256: str
    tool: str
    tool_version: str
    source: str
    min_tools_agreeing: int | None
    consensus_rule: str
    overview: DbcanOverview
    family_genes: Mapping[str, tuple[str, ...]]
    capabilities: tuple[ResolvedCapability, ...]
    unmapped_families: tuple[str, ...]
    family_map_sha256: str
    family_map_sources: tuple[str, ...]

    def genes_for(self, families: Sequence[str]) -> tuple[str, ...]:
        """Genes supporting any of ``families``, in the order of the annotation file."""

        wanted = {gene for family in families for gene in self.family_genes.get(family, ())}
        return tuple(gene.gene_id for gene in self.overview.genes if gene.gene_id in wanted)


@dataclass(frozen=True)
class _ProteomeAnnotation:
    """One genomes.csv row whose UniProt TSV export was read and resolved."""

    row: int
    strain_id: str
    annotation_file: str
    annotation_sha256: str
    tool: str
    tool_version: str
    source: str
    proteome_id: str | None
    proteome: UniprotProteome
    resolution: ProteomeResolution
    family_map_sha256: str
    family_map_sources: tuple[str, ...]

    @property
    def capabilities(self) -> tuple[ProteomeClassSupport, ...]:
        return self.resolution.capabilities

    @property
    def unmapped_families(self) -> tuple[str, ...]:
        return tuple(self.resolution.unmapped_families)


@dataclass(frozen=True)
class _Substrate:
    row: int
    substrate_id: str
    registry_id: str
    name: str
    substrate_class: str
    bond_classes: tuple[str, ...]
    product: str
    product_yield: float
    source: str


@dataclass(frozen=True)
class _Condition:
    row: int
    condition_id: str
    temperature_text: str
    temperature_kelvin: float | None
    temperature_units: str
    ph_text: str
    ph: float | None
    notes: str


@dataclass(frozen=True)
class _Kinetics:
    row: int
    strain_id: str
    class_key: str
    substrate_id: str
    condition_id: str
    quantity: str
    value: float | None
    lower: float | None
    upper: float | None
    units: str
    evidence_type: str
    method: str
    source: str
    sd: float | None
    replicates: int | None
    activity_substrate: str = ""
    activity_saturating: str = ""

    @property
    def case_key(self) -> tuple[str, str, str, str]:
        return (self.strain_id, self.class_key, self.substrate_id, self.condition_id)

    @property
    def pair_key(self) -> tuple[str, str]:
        return (self.class_key, self.substrate_id)

    @property
    def is_exact(self) -> bool:
        return self.value is not None


@dataclass(frozen=True)
class _Response:
    row: int
    strain_id: str
    class_key: str
    substrate_id: str
    law: str
    parameter: str
    value: float
    units: str
    evidence_type: str
    method: str
    source: str
    reference_tolerance: float | None
    kinetics_at_reference: bool

    @property
    def binding_key(self) -> tuple[str, str, str]:
        return (self.strain_id, self.class_key, self.substrate_id)


@dataclass
class _Parsed:
    strains: dict[str, _Strain]
    classes: dict[str, _EnzymeClassInfo]
    strain_classes: list[_StrainClass]
    substrates: dict[str, _Substrate]
    conditions: dict[str, _Condition]
    kinetics: list[_Kinetics]
    responses: list[_Response] = field(default_factory=list)
    # (class, substrate) -> rate form, set by cross-validation; absent when no case started a form.
    pair_forms: dict[tuple[str, str], str] = field(default_factory=dict)
    # (strain, class, substrate) -> law -> parameter -> row, set by cross-validation for valid laws.
    laws: dict[tuple[str, str, str], dict[str, dict[str, _Response]]] = field(default_factory=dict)
    # Resolved genome annotations, the annotation files read (relative path -> bytes), and the
    # genomes.csv row of every strain that has one (also rows that failed validation).
    genomes: list[_GenomeAnnotation | _ProteomeAnnotation] = field(default_factory=list)
    annotation_files: dict[str, bytes] = field(default_factory=dict)
    genome_rows: dict[str, int] = field(default_factory=dict)


@dataclass
class _Generated:
    mappings: dict[str, list[Mapping[str, Any]]]
    objects: dict[str, list[RegistryRecord]]
    base_references: dict[tuple[str, str], Mapping[str, Any]]
    origins: dict[tuple[str, str], tuple[str, int | None, str | None]]


@dataclass(frozen=True)
class _Table:
    name: str
    rows: tuple[tuple[int, dict[str, str]], ...]


def _base_registry(registry: str | Path | FungModRegistry | None) -> FungModRegistry:
    if isinstance(registry, FungModRegistry):
        return registry
    if registry is None:
        return load_registry(default_registry_path())
    return load_registry(Path(registry))


def _read_dataset_files(directory: Path, issues: list[dict[str, Any]]) -> dict[str, bytes]:
    known = {*_REQUIRED_TABLES, *_OPTIONAL_TABLES}
    raw: dict[str, bytes] = {}
    for entry in sorted(directory.iterdir(), key=lambda item: item.name):
        if not entry.is_file():
            continue
        if entry.name == USER_DATASET_MANIFEST or entry.name in known:
            raw[entry.name] = entry.read_bytes()
        elif entry.suffix.lower() == ".csv":
            issues.append(
                _issue(
                    entry.name,
                    None,
                    None,
                    f"Unsupported table {entry.name!r} in this version; supported tables are "
                    f"{', '.join(sorted(known))}. Time-course data and other tables are not imported yet.",
                )
            )
    if USER_DATASET_MANIFEST not in raw:
        issues.append(_issue(USER_DATASET_MANIFEST, None, None, "Required manifest user_dataset.yml is missing."))
    for name in _REQUIRED_TABLES:
        if name not in raw:
            issues.append(_issue(name, None, None, f"Required table {name} is missing."))
    return raw


def _dataset_digest(raw_files: Mapping[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name in sorted(raw_files):
        data = raw_files[name]
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def _parse_manifest(raw: bytes | None, issues: list[dict[str, Any]]) -> dict[str, Any] | None:
    if raw is None:
        return None
    file = USER_DATASET_MANIFEST
    try:
        data = yaml.safe_load(raw.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        issues.append(_issue(file, None, None, f"Manifest is not readable UTF-8 YAML: {exc}"))
        return None
    if not isinstance(data, Mapping):
        issues.append(_issue(file, None, None, "Manifest must be a YAML mapping."))
        return None
    count = len(issues)
    unknown = sorted(str(key) for key in data if str(key) not in _MANIFEST_FIELDS)
    if unknown:
        issues.append(_issue(file, None, None, f"Unsupported manifest field(s): {', '.join(unknown)}."))
    dataset_id = data.get("dataset_id")
    if not isinstance(dataset_id, str) or not _DATASET_ID_PATTERN.fullmatch(dataset_id):
        issues.append(
            _issue(
                file,
                None,
                "dataset_id",
                "dataset_id is required and must be lowercase snake_case (letters, digits, single underscores).",
            )
        )
    for key in ("contributor", "source", "notes"):
        if key in data and not _is_text(data[key]):
            issues.append(_issue(file, None, key, f"{key} must be nonblank text when given."))
    if "date" in data:
        value = data["date"]
        if isinstance(value, date) and not isinstance(value, datetime):
            data = {**data, "date": value.isoformat()}
        elif not isinstance(value, str) or not _is_iso_date(value):
            issues.append(_issue(file, None, "date", "date must be an ISO date (YYYY-MM-DD)."))
    simulation = data.get("simulation")
    if not isinstance(simulation, Mapping):
        issues.append(
            _issue(
                file,
                None,
                "simulation",
                "simulation {duration, units, points} is required; FungMod has no default time grid.",
            )
        )
    else:
        unknown_sim = sorted(str(key) for key in simulation if str(key) not in _SIMULATION_FIELDS)
        if unknown_sim:
            issues.append(
                _issue(file, None, "simulation", f"Unsupported simulation field(s): {', '.join(unknown_sim)}.")
            )
        duration = simulation.get("duration")
        if (
            isinstance(duration, bool)
            or not isinstance(duration, (int, float))
            or not math.isfinite(float(duration))
            or float(duration) <= 0.0
        ):
            issues.append(_issue(file, None, "simulation.duration", "simulation.duration must be a positive number."))
        units = simulation.get("units")
        if not isinstance(units, str) or _unit_dimension_error(units, _TIME_REFERENCE_UNITS) is not None:
            issues.append(
                _issue(file, None, "simulation.units", "simulation.units must be a time unit such as second, minute or hour.")
            )
        points = simulation.get("points")
        if isinstance(points, bool) or not isinstance(points, int) or points < 2:
            issues.append(_issue(file, None, "simulation.points", "simulation.points must be an integer of at least 2."))
    if len(issues) > count:
        return None
    return dict(data)


def _parse_table(name: str, raw: bytes, issues: list[dict[str, Any]], *, rows_required: bool) -> _Table | None:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        issues.append(_issue(name, None, None, f"Table is not UTF-8 text: {exc}"))
        return None
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header_cells = next(reader)
    except StopIteration:
        issues.append(_issue(name, None, None, "Table is empty; a header row is required."))
        return None
    except csv.Error as exc:
        issues.append(_issue(name, 1, None, f"Header row is not valid CSV: {exc}"))
        return None
    header = [cell.strip() for cell in header_cells]
    required, optional = _TABLE_COLUMNS[name]
    count = len(issues)
    duplicates = sorted({column for column in header if header.count(column) > 1})
    if duplicates:
        issues.append(_issue(name, 1, None, f"Duplicate column(s): {', '.join(duplicates)}."))
    unknown = [column for column in header if column not in (*required, *optional)]
    if unknown:
        issues.append(
            _issue(
                name,
                1,
                None,
                f"Unsupported column(s): {', '.join(unknown)}. Supported columns are "
                f"{', '.join((*required, *optional))}.",
            )
        )
    missing = [column for column in required if column not in header]
    if missing:
        issues.append(_issue(name, 1, None, f"Missing required column(s): {', '.join(missing)}."))
    if len(issues) > count:
        return None
    rows: list[tuple[int, dict[str, str]]] = []
    try:
        for cells in reader:
            line = reader.line_num
            if not any(cell.strip() for cell in cells):
                continue
            if len(cells) > len(header):
                issues.append(_issue(name, line, None, "Row has more cells than the header."))
                continue
            values = {column: (cells[index].strip() if index < len(cells) else "") for index, column in enumerate(header)}
            for column in optional:
                values.setdefault(column, "")
            rows.append((line, values))
    except csv.Error as exc:
        issues.append(_issue(name, reader.line_num, None, f"Row is not valid CSV: {exc}"))
        return None
    if rows_required and not rows:
        issues.append(_issue(name, None, None, "Table needs at least one data row."))
    return _Table(name=name, rows=tuple(rows))


def _parse_rows(tables: Mapping[str, _Table | None], context: _Context, *, directory: Path) -> _Parsed | None:
    required_ok = all(tables.get(name) is not None for name in _REQUIRED_TABLES)
    if not required_ok:
        return None
    resolver = RegistryResolver(context.base)
    strains = _parse_strains(_table(tables, "strains.csv"), resolver, context)
    user_classes = _parse_user_classes(tables.get("enzyme_classes.csv"), resolver, context)
    classes: dict[str, _EnzymeClassInfo] = dict(user_classes)
    strain_classes = _parse_strain_classes(_table(tables, "enzymes.csv"), strains, classes, resolver, context)
    # Genome-resolved classes join the declared classes before kinetics and responses are
    # checked, so user kinetics may reference a class the annotation declared.
    genome_table = tables.get(GENOME_TABLE)
    genomes = _GenomeParse()
    if genome_table is not None:
        genomes = _parse_genomes(
            genome_table,
            directory=directory,
            strains=strains,
            classes=classes,
            strain_classes=strain_classes,
            context=context,
        )
    substrates = _parse_substrates(_table(tables, "substrates.csv"), resolver, context)
    conditions = _parse_conditions(_table(tables, "conditions.csv"), resolver, context)
    kinetics = _parse_kinetics(
        _table(tables, "kinetics.csv"),
        strains=strains,
        classes=classes,
        strain_classes=strain_classes,
        substrates=substrates,
        conditions=conditions,
        resolver=resolver,
        context=context,
    )
    responses_table = tables.get("responses.csv")
    responses = (
        []
        if responses_table is None
        else _parse_responses(
            responses_table,
            strains=strains,
            classes=classes,
            strain_classes=strain_classes,
            substrates=substrates,
            resolver=resolver,
            context=context,
        )
    )
    return _Parsed(
        strains=strains,
        classes=classes,
        strain_classes=strain_classes,
        substrates=substrates,
        conditions=conditions,
        kinetics=kinetics,
        responses=responses,
        genomes=genomes.annotations,
        annotation_files=genomes.files,
        genome_rows=genomes.rows,
    )


def _table(tables: Mapping[str, _Table | None], name: str) -> _Table:
    table = tables[name]
    assert table is not None
    return table


def _parse_strains(table: _Table, resolver: RegistryResolver, context: _Context) -> dict[str, _Strain]:
    file = table.name
    strains: dict[str, _Strain] = {}
    terms: dict[str, int] = {}
    for line, row in table.rows:
        strain_id = _required_identifier(row, "strain_id", file=file, line=line, context=context)
        name = _required_text(row, "name", file=file, line=line, context=context)
        aliases = _semicolon_list(row.get("aliases", ""))
        named = (("strain_id", strain_id), ("name", name), *(("aliases", alias) for alias in aliases))
        # A colliding row is still registered so later tables do not report it as undeclared.
        _terms_are_free(named, "fungi", resolver, terms, file=file, line=line, context=context)
        if strain_id is None or name is None:
            continue
        if strain_id in strains:
            context.add(file, line, "strain_id", f"strain_id {strain_id!r} repeats row {strains[strain_id].row}.")
            continue
        strains[strain_id] = _Strain(
            row=line,
            strain_id=strain_id,
            name=name,
            scientific_name=row.get("scientific_name", ""),
            aliases=aliases,
        )
    return strains


def _parse_user_classes(
    table: _Table | None,
    resolver: RegistryResolver,
    context: _Context,
) -> dict[str, _EnzymeClassInfo]:
    if table is None:
        return {}
    file = table.name
    classes: dict[str, _EnzymeClassInfo] = {}
    for line, row in table.rows:
        class_id = _required_identifier(row, "class_id", file=file, line=line, context=context)
        name = _required_text(row, "name", file=file, line=line, context=context)
        source = _required_text(row, "source", file=file, line=line, context=context)
        targets = _class_tokens(row, "target_bond_classes", file=file, line=line, context=context)
        compatible = _class_tokens(row, "compatible_substrate_classes", file=file, line=line, context=context)
        ec_number = row.get("ec_number", "")
        if ec_number and not _EC_NUMBER_PATTERN.fullmatch(ec_number):
            context.add(file, line, "ec_number", f"ec_number {ec_number!r} is not an EC number such as 3.1.1.1.")
        for column, term in (("class_id", class_id), ("name", name)):
            clash = "" if term is None else _registry_clash(resolver, "enzyme_classes", term)
            if clash:
                context.add(
                    file,
                    line,
                    column,
                    f"{term!r} collides with registry enzyme class {clash}; reference the registry class in "
                    "enzymes.csv instead, or choose an identifier and name the registry does not use.",
                )
        if class_id is None or name is None or source is None or targets is None or compatible is None:
            continue
        if class_id in classes:
            context.add(file, line, "class_id", f"class_id {class_id!r} repeats row {classes[class_id].row}.")
            continue
        classes[class_id] = _EnzymeClassInfo(
            key=class_id,
            origin="user",
            name=name,
            ec_number=ec_number,
            target_bond_classes=targets,
            compatible_substrate_classes=compatible,
            source=source,
            row=line,
        )
    return classes


def _resolve_class(
    text: str,
    *,
    classes: dict[str, _EnzymeClassInfo],
    resolver: RegistryResolver,
    file: str,
    line: int,
    context: _Context,
) -> str | None:
    if text in classes and classes[text].origin == "user":
        return text
    try:
        resolved = resolver.resolve_enzyme_class(text)
    except AmbiguousResolutionError as exc:
        context.add(file, line, "enzyme_class", f"enzyme_class {text!r} is ambiguous in the registry: {exc}")
        return None
    except ResolutionError:
        context.add(
            file,
            line,
            "enzyme_class",
            f"enzyme_class {text!r} is neither a registry enzyme class (ID, name, alias or EC number) "
            "nor a class_id defined in enzyme_classes.csv.",
        )
        return None
    return _registry_class_info(resolved.record_id, classes=classes, context=context)


def _registry_class_info(record_id: str, *, classes: dict[str, _EnzymeClassInfo], context: _Context) -> str:
    """Register the class information of registry enzyme class ``record_id`` and return its key."""

    record = context.base.get_enzyme_class(record_id)
    if record.record_id not in classes:
        classes[record.record_id] = _EnzymeClassInfo(
            key=record.record_id,
            origin="registry",
            name=record.name,
            ec_number=record.ec_number,
            target_bond_classes=tuple(record.target_bond_classes),
            compatible_substrate_classes=tuple(record.compatible_substrate_classes),
            source=f"Registry enzyme class {record.record_id}",
            row=None,
            parent_maturity=record.maturity,
        )
    return record.record_id


def _parse_strain_classes(
    table: _Table,
    strains: Mapping[str, _Strain],
    classes: dict[str, _EnzymeClassInfo],
    resolver: RegistryResolver,
    context: _Context,
) -> list[_StrainClass]:
    file = table.name
    seen: dict[tuple[str, str], int] = {}
    output: list[_StrainClass] = []
    for line, row in table.rows:
        strain_id = _required_text(row, "strain_id", file=file, line=line, context=context)
        class_text = _required_text(row, "enzyme_class", file=file, line=line, context=context)
        evidence = _required_text(row, "evidence", file=file, line=line, context=context)
        source = _required_text(row, "source", file=file, line=line, context=context)
        if strain_id is not None and strain_id not in strains:
            context.add(file, line, "strain_id", f"strain_id {strain_id!r} is not declared in strains.csv.")
            strain_id = None
        class_key = (
            None
            if class_text is None
            else _resolve_class(class_text, classes=classes, resolver=resolver, file=file, line=line, context=context)
        )
        if strain_id is None or class_key is None or evidence is None or source is None:
            continue
        key = (strain_id, class_key)
        if key in seen:
            context.add(
                file, line, "enzyme_class", f"Strain {strain_id!r} already declares class {class_key!r} in row {seen[key]}."
            )
            continue
        seen[key] = line
        output.append(_StrainClass(row=line, strain_id=strain_id, class_key=class_key, evidence=evidence, source=source))
    return output


@dataclass
class _GenomeParse:
    annotations: list[_GenomeAnnotation | _ProteomeAnnotation] = field(default_factory=list)
    files: dict[str, bytes] = field(default_factory=dict)
    rows: dict[str, int] = field(default_factory=dict)


def _parse_genomes(
    table: _Table,
    *,
    directory: Path,
    strains: Mapping[str, _Strain],
    classes: dict[str, _EnzymeClassInfo],
    strain_classes: list[_StrainClass],
    context: _Context,
) -> _GenomeParse:
    """Read genomes.csv, resolve each annotation, and merge the classes that have a registry record.

    The annotation is resolved with ``CapabilityResolver`` and the curated CAZy
    family map against the enzyme classes of the base registry. A resolved
    class with a registry record joins the strain's declared classes; an
    explicit ``enzymes.csv`` row for the same class wins and receives the
    genome evidence as well. Classes without a record and families the map
    does not assign stay on the annotation for the dataset report; no record is
    generated for them, and no rate is taken from the annotation. A row whose
    ``annotation_tool`` names UniProt is read by ``_parse_proteome_row``.
    """

    file = table.name
    result = _GenomeParse()
    explicit = {(item.strain_id, item.class_key): index for index, item in enumerate(strain_classes)}
    resolver: CapabilityResolver | None = None
    family_map_sha256 = ""
    for line, row in table.rows:
        strain_id = _reference(row, "strain_id", strains, "strains.csv", file=file, line=line, context=context)
        if strain_id is not None:
            if strain_id in result.rows:
                context.add(
                    file,
                    line,
                    "strain_id",
                    f"Strain {strain_id!r} already has a genome annotation in row {result.rows[strain_id]}; give "
                    "one annotation per strain.",
                )
                strain_id = None
            else:
                result.rows[strain_id] = line
        tool = _genome_tool(row, file=file, line=line, context=context)
        source = _required_text(row, "source", file=file, line=line, context=context)
        if _names_uniprot(row):
            _parse_proteome_row(
                row,
                line=line,
                strain_id=strain_id,
                tool=tool,
                source=source,
                directory=directory,
                strains=strains,
                classes=classes,
                strain_classes=strain_classes,
                explicit=explicit,
                result=result,
                context=context,
            )
            continue
        min_tools = _optional_positive_int(row, "min_tools_agreeing", file=file, line=line, context=context)
        min_tools_value = None if isinstance(min_tools, bool) else min_tools
        relative = _annotation_path(row, directory=directory, file=file, line=line, context=context)
        overview: DbcanOverview | None = None
        if relative is not None:
            data = result.files.get(relative)
            if data is None:
                try:
                    data = (directory / relative).read_bytes()
                except OSError as exc:
                    context.add(file, line, "annotation_file", f"Annotation file {relative!r} cannot be read: {exc}")
                else:
                    result.files[relative] = data
            if data is not None:
                overview = _read_overview(data, relative, file=file, line=line, context=context)
        family_genes: dict[str, tuple[str, ...]] | None = None
        if overview is not None and min_tools is not False:
            family_genes = _consensus_family_genes(
                overview, min_tools_value, relative=relative, file=file, line=line, context=context
            )
        if strain_id is None or tool is None or source is None or relative is None or family_genes is None:
            continue
        assert overview is not None
        if resolver is None:
            try:
                resolver = CapabilityResolver(
                    family_map=CazymeFamilyMap.load(),
                    registry_enzyme_classes=tuple(sorted(context.base.enzyme_classes)),
                )
                family_map_sha256 = hashlib.sha256(default_family_map_path().read_bytes()).hexdigest()
            except (OSError, yaml.YAMLError, CapabilityResolutionError, ProvenanceError) as exc:
                context.add(file, None, None, f"The curated CAZy family map could not be loaded: {exc}")
                return result
        tool_name, tool_version = tool
        try:
            resolution = resolver.resolve(
                CazymeAnnotation(
                    organism=strains[strain_id].name,
                    families=tuple(family_genes),
                    # The user's source column states which genome or proteome was annotated.
                    genome_accession=source,
                    annotation_tool=tool_name,
                    annotation_tool_version=tool_version,
                    # genomes.csv has no date column; this marker never leaves the resolver call.
                    annotation_date="not recorded in genomes.csv",
                )
            )
        except (CapabilityResolutionError, ProvenanceError) as exc:
            context.add(file, line, "annotation_file", f"The annotation could not be resolved: {exc}")
            continue
        annotation = _GenomeAnnotation(
            row=line,
            strain_id=strain_id,
            annotation_file=relative,
            annotation_sha256=hashlib.sha256(result.files[relative]).hexdigest(),
            tool=tool_name,
            tool_version=tool_version,
            source=source,
            min_tools_agreeing=min_tools_value,
            consensus_rule=_consensus_rule_text(overview, min_tools_value, line=line),
            overview=overview,
            family_genes=MappingProxyType(dict(family_genes)),
            capabilities=resolution.capabilities,
            unmapped_families=resolution.unmapped_families,
            family_map_sha256=family_map_sha256,
            family_map_sources=resolver.family_map.sources,
        )
        result.annotations.append(annotation)
        for capability in resolution.capabilities:
            if not capability.modellable:
                continue
            evidence = _GenomeClassEvidence(
                genome_row=line,
                annotation_file=relative,
                annotation_sha256=annotation.annotation_sha256,
                tool=tool_name,
                tool_version=tool_version,
                families=capability.families,
                gene_ids=annotation.genes_for(capability.families),
                specificity=capability.specificity,
                consensus_rule=annotation.consensus_rule,
                source=source,
            )
            key = (strain_id, capability.enzyme_class)
            if key in explicit:
                index = explicit[key]
                strain_classes[index] = replace(strain_classes[index], genome=evidence)
                continue
            class_key = _registry_class_info(capability.enzyme_class, classes=classes, context=context)
            strain_classes.append(
                _StrainClass(
                    row=line,
                    strain_id=strain_id,
                    class_key=class_key,
                    evidence=evidence.evidence_text,
                    source=source,
                    file=GENOME_TABLE,
                    genome=evidence,
                )
            )
    return result


def _genome_tool(row: Mapping[str, str], *, file: str, line: int, context: _Context) -> tuple[str, str] | None:
    """Split ``annotation_tool`` into a supported tool name and the version the user states."""

    text = _required_text(row, "annotation_tool", file=file, line=line, context=context)
    if text is None:
        return None
    parts = text.split(maxsplit=1)
    name = parts[0]
    version = parts[1].strip() if len(parts) > 1 else ""
    uniprot = bool(_UNIPROT_TOOL_PATTERN.fullmatch(name))
    if not (_DBCAN_TOOL_PATTERN.fullmatch(name) or uniprot):
        context.add(
            file,
            line,
            "annotation_tool",
            f"annotation_tool {text!r} is not a supported annotation tool. genomes.csv reads dbCAN overview.txt "
            f"files (tool columns {', '.join(TOOL_COLUMNS)}) and UniProtKB TSV exports; give 'dbCAN' followed by "
            "its version or 'UniProt' followed by the UniProt release or download date, or declare the strain's "
            "enzyme classes in enzymes.csv.",
        )
        return None
    if not version and uniprot:
        context.add(
            file,
            line,
            "annotation_tool",
            f"annotation_tool {text!r} names UniProt without a version; write the UniProt release or the download "
            "date after the name, for example 'UniProt 2026_03' or 'UniProt downloaded 2026-10-01'. The TSV export "
            "does not record it, and a resolution that cannot be traced to a UniProt release is not reproducible.",
        )
        return None
    if not version:
        context.add(
            file,
            line,
            "annotation_tool",
            f"annotation_tool {text!r} names dbCAN without a version; write the version after the tool name, for "
            "example 'dbCAN 4.1.4'. The overview file does not record it, and a resolution that cannot be traced "
            "to a tool version is not reproducible.",
        )
        return None
    return name, version


def _names_uniprot(row: Mapping[str, str]) -> bool:
    """Whether the first token of ``annotation_tool`` names UniProt, whatever the rest of the cell says."""

    parts = row.get("annotation_tool", "").split(maxsplit=1)
    return bool(parts) and bool(_UNIPROT_TOOL_PATTERN.fullmatch(parts[0]))


def _parse_proteome_row(
    row: Mapping[str, str],
    *,
    line: int,
    strain_id: str | None,
    tool: tuple[str, str] | None,
    source: str | None,
    directory: Path,
    strains: Mapping[str, _Strain],
    classes: dict[str, _EnzymeClassInfo],
    strain_classes: list[_StrainClass],
    explicit: Mapping[tuple[str, str], int],
    result: _GenomeParse,
    context: _Context,
) -> None:
    """Read one genomes.csv row that points to a UniProtKB TSV export, resolve it and merge its classes.

    The path rules, the digest and the merge (an explicit ``enzymes.csv`` row
    wins and receives the evidence) are those of a dbCAN row. The proteins are
    resolved by ``resolve_uniprot_proteome`` against the base registry: CAZy
    families through ``CapabilityResolver`` and the curated family map, complete
    EC numbers through the registry's EC lookup. ``min_tools_agreeing`` is
    refused, because a UniProt export has no tool columns.
    """

    file = GENOME_TABLE
    refused = False
    if row.get("min_tools_agreeing", ""):
        context.add(
            file,
            line,
            "min_tools_agreeing",
            "min_tools_agreeing counts agreeing tool columns of a dbCAN overview; a UniProt export has none, so "
            "leave it blank on this row.",
        )
        refused = True
    proteome_id: str | None = None
    if source is not None:
        identifiers = sorted(set(_UNIPROT_PROTEOME_ID.findall(source)))
        if len(identifiers) > 1:
            context.add(
                file,
                line,
                "source",
                f"source names several UniProt proteome identifiers ({', '.join(identifiers)}); one row reads one "
                "proteome, so name only the one exported.",
            )
            refused = True
        proteome_id = identifiers[0] if identifiers else None
    relative = _annotation_path(row, directory=directory, file=file, line=line, context=context)
    proteome: UniprotProteome | None = None
    if relative is not None:
        data = result.files.get(relative)
        if data is None:
            try:
                data = (directory / relative).read_bytes()
            except OSError as exc:
                context.add(file, line, "annotation_file", f"Annotation file {relative!r} cannot be read: {exc}")
            else:
                result.files[relative] = data
        if data is not None:
            label = f"Annotation file {relative!r}"
            try:
                proteome = parse_uniprot_tsv(decode_uniprot_tsv(data, source=label), source=label)
            except CapabilityResolutionError as exc:
                context.add(file, line, "annotation_file", f"{exc} A UniProt row reads a UniProtKB TSV export.")
    if refused or strain_id is None or tool is None or source is None or relative is None or proteome is None:
        return
    try:
        resolver = CapabilityResolver(
            family_map=CazymeFamilyMap.load(),
            registry_enzyme_classes=tuple(sorted(context.base.enzyme_classes)),
        )
        family_map_sha256 = hashlib.sha256(default_family_map_path().read_bytes()).hexdigest()
    except (OSError, yaml.YAMLError, CapabilityResolutionError, ProvenanceError) as exc:
        context.add(file, None, None, f"The curated CAZy family map could not be loaded: {exc}")
        return
    tool_name, tool_version = tool
    try:
        resolution = resolve_uniprot_proteome(
            proteome,
            capability_resolver=resolver,
            registry=context.base,
            organism=strains[strain_id].name,
            proteome_source=source,
            annotation_tool=tool_name,
            annotation_tool_version=tool_version,
            # genomes.csv has no date column; this marker never leaves the resolver call.
            annotation_date="not recorded in genomes.csv",
        )
    except (CapabilityResolutionError, ProvenanceError) as exc:
        context.add(file, line, "annotation_file", f"The UniProt export could not be resolved: {exc}")
        return
    annotation = _ProteomeAnnotation(
        row=line,
        strain_id=strain_id,
        annotation_file=relative,
        annotation_sha256=hashlib.sha256(result.files[relative]).hexdigest(),
        tool=tool_name,
        tool_version=tool_version,
        source=source,
        proteome_id=proteome_id,
        proteome=proteome,
        resolution=resolution,
        family_map_sha256=family_map_sha256,
        family_map_sources=resolver.family_map.sources,
    )
    result.annotations.append(annotation)
    for support in resolution.capabilities:
        if not support.modellable:
            continue
        evidence = _ProteomeClassEvidence(
            genome_row=line,
            annotation_file=relative,
            annotation_sha256=annotation.annotation_sha256,
            tool=tool_name,
            tool_version=tool_version,
            source=source,
            proteome_id=proteome_id,
            organism_id=proteome.organism_id,
            review_column=proteome.has_review_column,
            support=support,
        )
        key = (strain_id, support.enzyme_class)
        if key in explicit:
            index = explicit[key]
            strain_classes[index] = replace(strain_classes[index], genome=evidence)
            continue
        class_key = _registry_class_info(support.enzyme_class, classes=classes, context=context)
        strain_classes.append(
            _StrainClass(
                row=line,
                strain_id=strain_id,
                class_key=class_key,
                evidence=evidence.evidence_text,
                source=source,
                file=GENOME_TABLE,
                genome=evidence,
            )
        )


def _annotation_path(
    row: Mapping[str, str],
    *,
    directory: Path,
    file: str,
    line: int,
    context: _Context,
) -> str | None:
    """Return ``annotation_file`` as a normalised path relative to the dataset directory, or refuse it."""

    text = _required_text(row, "annotation_file", file=file, line=line, context=context)
    if text is None:
        return None
    windows = PureWindowsPath(text)
    if PurePosixPath(text).is_absolute() or windows.drive or windows.root:
        context.add(
            file,
            line,
            "annotation_file",
            f"annotation_file {text!r} is an absolute path; give a path relative to the dataset directory, so the "
            "dataset stays self-contained and its digest covers the file.",
        )
        return None
    if "\\" in text:
        context.add(file, line, "annotation_file", f"annotation_file {text!r} must separate directories with '/'.")
        return None
    parts = [part for part in PurePosixPath(text).parts if part != "."]
    if ".." in parts:
        context.add(
            file,
            line,
            "annotation_file",
            f"annotation_file {text!r} leaves the dataset directory; the annotation file must lie inside it.",
        )
        return None
    relative = "/".join(parts)
    if not relative or relative in {USER_DATASET_MANIFEST, *_TABLE_COLUMNS}:
        context.add(
            file,
            line,
            "annotation_file",
            f"annotation_file {text!r} does not name an annotation file in the dataset directory.",
        )
        return None
    path = directory / relative
    if not path.resolve().is_relative_to(directory.resolve()):
        context.add(
            file,
            line,
            "annotation_file",
            f"annotation_file {text!r} resolves outside the dataset directory (through a symbolic link); the "
            "annotation file must lie inside it.",
        )
        return None
    if not path.is_file():
        reason = "is not a file" if path.exists() else "does not exist"
        context.add(file, line, "annotation_file", f"Annotation file {relative!r} {reason} in the dataset directory.")
        return None
    return relative


def _read_overview(data: bytes, relative: str, *, file: str, line: int, context: _Context) -> DbcanOverview | None:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        context.add(file, line, "annotation_file", f"Annotation file {relative!r} is not UTF-8 text: {exc}")
        return None
    try:
        return parse_overview(text, source=f"Annotation file {relative!r}")
    except CapabilityResolutionError as exc:
        context.add(file, line, "annotation_file", f"{exc} genomes.csv reads dbCAN overview.txt files.")
        return None


def _consensus_family_genes(
    overview: DbcanOverview,
    min_tools: int | None,
    *,
    relative: str | None,
    file: str,
    line: int,
    context: _Context,
) -> dict[str, tuple[str, ...]] | None:
    """Families and their genes under the consensus rule of ``DbcanOverview.family_genes``."""

    try:
        family_genes = overview.family_genes(min_tools_agreeing=min_tools)
    except CapabilityResolutionError as exc:
        context.add(file, line, "min_tools_agreeing", str(exc))
        return None
    if not family_genes:
        context.add(
            file,
            line,
            "min_tools_agreeing",
            f"No CAZy family in {relative!r} is called by at least {min_tools} of the tool columns present "
            f"({', '.join(overview.tool_columns)}); lower min_tools_agreeing or leave it blank.",
        )
        return None
    return family_genes


def _consensus_rule_text(overview: DbcanOverview, min_tools: int | None, *, line: int) -> str:
    columns = ", ".join(overview.tool_columns)
    if min_tools is None:
        return (
            f"a family counts for a gene when any tool column present ({columns}) calls it, the rule of "
            "fungal_model.capability.families_from_overview; min_tools_agreeing is blank"
        )
    return (
        f"a family counts for a gene when at least {min_tools} of the tool columns present ({columns}) call it "
        f"(min_tools_agreeing in {GENOME_TABLE} row {line})"
    )


def _parse_substrates(table: _Table, resolver: RegistryResolver, context: _Context) -> dict[str, _Substrate]:
    file = table.name
    substrates: dict[str, _Substrate] = {}
    registry_rows: dict[str, int] = {}
    for line, row in table.rows:
        substrate_id = _required_identifier(row, "substrate_id", file=file, line=line, context=context)
        product = _required_identifier(row, "product", file=file, line=line, context=context)
        source = _required_text(row, "source", file=file, line=line, context=context)
        product_yield = _required_number(row, "product_yield", file=file, line=line, context=context)
        if product_yield is not None and product_yield <= 0.0:
            context.add(file, line, "product_yield", "product_yield must be positive.")
            product_yield = None
        basis = row.get("yield_basis", "")
        if basis != _YIELD_BASIS:
            context.add(
                file,
                line,
                "yield_basis",
                f"yield_basis must be {_YIELD_BASIS!r}; the yield is always explicit and never inferred.",
            )
        registry_text = row.get("registry_substrate", "")
        if registry_text:
            parsed = _registry_substrate(
                row,
                registry_text=registry_text,
                substrate_id=substrate_id,
                product=product,
                resolver=resolver,
                file=file,
                line=line,
                context=context,
            )
        else:
            parsed = _user_substrate(row, file=file, line=line, context=context)
            named = (("substrate_id", substrate_id), ("name", row.get("name", "") or None))
            _terms_are_free(named, "substrates", resolver, {}, file=file, line=line, context=context)
        if (
            substrate_id is None
            or product is None
            or source is None
            or product_yield is None
            or basis != _YIELD_BASIS
            or parsed is None
        ):
            continue
        registry_id, name, substrate_class, bond_classes = parsed
        if substrate_id in substrates:
            context.add(file, line, "substrate_id", f"substrate_id {substrate_id!r} repeats row {substrates[substrate_id].row}.")
            continue
        if registry_id:
            if registry_id in registry_rows:
                context.add(
                    file,
                    line,
                    "registry_substrate",
                    f"Registry substrate {registry_id!r} is already referenced in row {registry_rows[registry_id]}.",
                )
                continue
            registry_rows[registry_id] = line
        substrates[substrate_id] = _Substrate(
            row=line,
            substrate_id=substrate_id,
            registry_id=registry_id,
            name=name,
            substrate_class=substrate_class,
            bond_classes=bond_classes,
            product=product,
            product_yield=product_yield,
            source=source,
        )
    return substrates


def _registry_substrate(
    row: Mapping[str, str],
    *,
    registry_text: str,
    substrate_id: str | None,
    product: str | None,
    resolver: RegistryResolver,
    file: str,
    line: int,
    context: _Context,
) -> tuple[str, str, str, tuple[str, ...]] | None:
    filled = [column for column in _USER_SUBSTRATE_FIELDS if row.get(column, "")]
    if filled:
        context.add(
            file,
            line,
            filled[0],
            "A row with registry_substrate references the registry record and must leave "
            f"{', '.join(_USER_SUBSTRATE_FIELDS)} blank; the registry record is not copied.",
        )
    try:
        resolved = resolver.resolve_substrate(registry_text)
    except AmbiguousResolutionError as exc:
        context.add(file, line, "registry_substrate", f"registry_substrate {registry_text!r} is ambiguous: {exc}")
        return None
    except ResolutionError:
        context.add(file, line, "registry_substrate", f"registry_substrate {registry_text!r} is not in the registry.")
        return None
    record = context.base.get_substrate(resolved.record_id)
    ok = not filled
    if record.physical_state != "dissolved":
        context.add(
            file,
            line,
            "registry_substrate",
            f"Registry substrate {record.record_id!r} has physical_state {record.physical_state!r}; this "
            "increment supports only dissolved substrates.",
        )
        ok = False
    if product is not None and product not in record.products:
        context.add(
            file,
            line,
            "product",
            f"Registry substrate {record.record_id!r} declares products {list(record.products)}; product "
            f"{product!r} is not among them. Define your own substrate row to state another product.",
        )
        ok = False
    if substrate_id is not None and substrate_id != record.record_id:
        try:
            other = resolver.resolve_substrate(substrate_id)
        except ResolutionError:
            other = None
        if other is not None and other.record_id != record.record_id:
            context.add(
                file,
                line,
                "substrate_id",
                f"substrate_id {substrate_id!r} names registry substrate {other.record_id!r}, not the "
                f"referenced {record.record_id!r}.",
            )
            ok = False
    if not ok:
        return None
    return record.record_id, record.name, record.substrate_class, tuple(record.bond_classes)


def _user_substrate(
    row: Mapping[str, str],
    *,
    file: str,
    line: int,
    context: _Context,
) -> tuple[str, str, str, tuple[str, ...]] | None:
    name = _required_text(row, "name", file=file, line=line, context=context)
    substrate_class = _required_text(row, "substrate_class", file=file, line=line, context=context)
    if substrate_class is not None and not _CLASS_TOKEN_PATTERN.fullmatch(substrate_class):
        context.add(file, line, "substrate_class", "substrate_class must be lowercase snake_case.")
        substrate_class = None
    physical_state = _required_text(row, "physical_state", file=file, line=line, context=context)
    if physical_state is not None and physical_state != "dissolved":
        context.add(
            file,
            line,
            "physical_state",
            f"physical_state {physical_state!r} is not supported; this increment supports only dissolved substrates.",
        )
        physical_state = None
    bonds = _class_tokens(row, "bond_classes", file=file, line=line, context=context)
    if name is None or substrate_class is None or physical_state is None or bonds is None:
        return None
    return "", name, substrate_class, bonds


def _parse_conditions(table: _Table, resolver: RegistryResolver, context: _Context) -> dict[str, _Condition]:
    file = table.name
    conditions: dict[str, _Condition] = {}
    for line, row in table.rows:
        condition_id = _required_identifier(row, "condition_id", file=file, line=line, context=context)
        _terms_are_free(
            (("condition_id", condition_id),), "environments", resolver, {}, file=file, line=line, context=context
        )
        units_text = _required_text(row, "temperature_units", file=file, line=line, context=context)
        if units_text is not None and units_text not in _TEMPERATURE_UNITS:
            context.add(file, line, "temperature_units", "temperature_units must be degC or kelvin.")
            units_text = None
        temperature_text = _required_text(row, "temperature", file=file, line=line, context=context)
        kelvin: float | None = None
        temperature_ok = temperature_text is not None
        if temperature_text is not None and temperature_text != _UNKNOWN_CELL:
            number = _number(temperature_text)
            if number is None:
                context.add(file, line, "temperature", "temperature must be a finite number or the word 'unknown'.")
                temperature_ok = False
            elif units_text is not None:
                kelvin = float(Q_(number, units_text).to("kelvin").magnitude)
                if kelvin <= 0.0:
                    context.add(file, line, "temperature", "temperature must be above absolute zero.")
                    temperature_ok = False
        ph_text = _required_text(row, "ph", file=file, line=line, context=context)
        ph: float | None = None
        ph_ok = ph_text is not None
        if ph_text is not None and ph_text != _UNKNOWN_CELL:
            ph = _number(ph_text)
            if ph is None:
                context.add(file, line, "ph", "ph must be a finite number or the word 'unknown'.")
                ph_ok = False
            elif not 0.0 <= ph <= 14.0:
                context.add(file, line, "ph", f"ph {ph_text} is outside 0 to 14.")
                ph_ok = False
        if condition_id is None or units_text is None or not temperature_ok or not ph_ok:
            continue
        assert temperature_text is not None and ph_text is not None
        if condition_id in conditions:
            context.add(file, line, "condition_id", f"condition_id {condition_id!r} repeats row {conditions[condition_id].row}.")
            continue
        conditions[condition_id] = _Condition(
            row=line,
            condition_id=condition_id,
            temperature_text=temperature_text,
            temperature_kelvin=kelvin,
            temperature_units=units_text,
            ph_text=ph_text,
            ph=ph,
            notes=row.get("notes", ""),
        )
    return conditions


def _parse_kinetics(
    table: _Table,
    *,
    strains: Mapping[str, _Strain],
    classes: dict[str, _EnzymeClassInfo],
    strain_classes: Sequence[_StrainClass],
    substrates: Mapping[str, _Substrate],
    conditions: Mapping[str, _Condition],
    resolver: RegistryResolver,
    context: _Context,
) -> list[_Kinetics]:
    file = table.name
    declared = {(item.strain_id, item.class_key) for item in strain_classes}
    rows: list[_Kinetics] = []
    for line, row in table.rows:
        quantity = _required_text(row, "quantity", file=file, line=line, context=context)
        if quantity is not None and quantity not in KINETIC_QUANTITIES:
            context.add(
                file,
                line,
                "quantity",
                _RETIRED_QUANTITY_HINTS.get(
                    quantity, f"quantity {quantity!r} is not one of {', '.join(KINETIC_QUANTITIES)}."
                ),
            )
            quantity = None
        strain_id = _reference(row, "strain_id", strains, "strains.csv", file=file, line=line, context=context)
        substrate_id = _reference(row, "substrate_id", substrates, "substrates.csv", file=file, line=line, context=context)
        condition_id = _reference(row, "condition_id", conditions, "conditions.csv", file=file, line=line, context=context)
        class_text = _required_text(row, "enzyme_class", file=file, line=line, context=context)
        class_key = (
            None
            if class_text is None
            else _resolve_class(class_text, classes=classes, resolver=resolver, file=file, line=line, context=context)
        )
        if strain_id is not None and class_key is not None and (strain_id, class_key) not in declared:
            context.add(
                file,
                line,
                "enzyme_class",
                f"Strain {strain_id!r} does not declare enzyme class {class_key!r} in enzymes.csv.",
            )
            class_key = None
        if class_key is not None and substrate_id is not None:
            info = classes[class_key]
            substrate = substrates[substrate_id]
            if _shared_bonds(info, substrate) is None:
                context.add(
                    file,
                    line,
                    "substrate_id",
                    f"Enzyme class {class_key!r} cannot act on substrate {substrate_id!r}: substrate class "
                    f"{substrate.substrate_class!r} must be in {list(info.compatible_substrate_classes)} and a bond "
                    f"class in {list(substrate.bond_classes)} must be in {list(info.target_bond_classes)}.",
                )
                substrate_id = None
        units = _required_text(row, "units", file=file, line=line, context=context)
        if units is not None and quantity is not None:
            message = _quantity_units_error(quantity, units)
            if message is not None:
                context.add(file, line, "units", message)
                units = None
        values = _kinetic_values(row, quantity=quantity, file=file, line=line, context=context)
        evidence_type = _required_text(row, "evidence_type", file=file, line=line, context=context)
        if evidence_type is not None and evidence_type not in EVIDENCE_TYPES:
            context.add(file, line, "evidence_type", f"evidence_type must be one of {', '.join(EVIDENCE_TYPES)}.")
            evidence_type = None
        method = row.get("method", "")
        if quantity == "vmax" and not method:
            context.add(
                file,
                line,
                "method",
                "method is required for vmax rows: state how the maximum rate of the simulated system was "
                "obtained (for example an initial-rate fit at saturating substrate in this assay).",
            )
            evidence_type = None
        elif evidence_type in _EVIDENCE_REQUIRES_METHOD and not method:
            context.add(file, line, "method", f"method is required for evidence_type {evidence_type!r}.")
            evidence_type = None
        activity_ok = _activity_columns_ok(
            row,
            quantity=quantity,
            substrate_id=substrate_id,
            file=file,
            line=line,
            context=context,
        )
        source = _required_text(row, "source", file=file, line=line, context=context)
        sd = _optional_nonnegative(row, "sd", file=file, line=line, context=context)
        replicates = _optional_positive_int(row, "replicates", file=file, line=line, context=context)
        if (
            not activity_ok
            or quantity is None
            or strain_id is None
            or class_key is None
            or substrate_id is None
            or condition_id is None
            or units is None
            or values is None
            or evidence_type is None
            or source is None
            or sd is False
            or replicates is False
        ):
            continue
        value, lower, upper = values
        rows.append(
            _Kinetics(
                row=line,
                strain_id=strain_id,
                class_key=class_key,
                substrate_id=substrate_id,
                condition_id=condition_id,
                quantity=quantity,
                value=value,
                lower=lower,
                upper=upper,
                units=units,
                evidence_type=evidence_type,
                method=method,
                source=source,
                sd=sd if isinstance(sd, float) else None,
                replicates=replicates if isinstance(replicates, int) and not isinstance(replicates, bool) else None,
                activity_substrate=row.get("activity_substrate", ""),
                activity_saturating=row.get("activity_saturating", ""),
            )
        )
    return rows


def _parse_responses(
    table: _Table,
    *,
    strains: Mapping[str, _Strain],
    classes: dict[str, _EnzymeClassInfo],
    strain_classes: Sequence[_StrainClass],
    substrates: Mapping[str, _Substrate],
    resolver: RegistryResolver,
    context: _Context,
) -> list[_Response]:
    file = table.name
    declared = {(item.strain_id, item.class_key) for item in strain_classes}
    rows: list[_Response] = []
    for line, row in table.rows:
        strain_id = _reference(row, "strain_id", strains, "strains.csv", file=file, line=line, context=context)
        substrate_id = _reference(row, "substrate_id", substrates, "substrates.csv", file=file, line=line, context=context)
        class_text = _required_text(row, "enzyme_class", file=file, line=line, context=context)
        class_key = (
            None
            if class_text is None
            else _resolve_class(class_text, classes=classes, resolver=resolver, file=file, line=line, context=context)
        )
        if strain_id is not None and class_key is not None and (strain_id, class_key) not in declared:
            context.add(
                file,
                line,
                "enzyme_class",
                f"Strain {strain_id!r} does not declare enzyme class {class_key!r} in enzymes.csv.",
            )
            class_key = None
        if class_key is not None and substrate_id is not None and _shared_bonds(classes[class_key], substrates[substrate_id]) is None:
            context.add(
                file,
                line,
                "substrate_id",
                f"Enzyme class {class_key!r} cannot act on substrate {substrate_id!r}, so no response law can be "
                "bound to that pair.",
            )
            substrate_id = None
        law = _required_text(row, "law", file=file, line=line, context=context)
        if law is not None and law not in RESPONSE_LAWS:
            if law in ENVIRONMENT_MODIFIER_TYPES:
                message = (
                    f"law {law!r} is an environment law FungMod implements, but responses.csv supports only "
                    f"{', '.join(RESPONSE_LAWS)} in this version."
                )
            else:
                message = (
                    f"law {law!r} is not an environment-response law FungMod implements; responses.csv supports "
                    f"{', '.join(RESPONSE_LAWS)}. FungMod does not create new response laws from user tables."
                )
            context.add(file, line, "law", message)
            law = None
        parameter = _required_text(row, "parameter", file=file, line=line, context=context)
        spec: ResponseLawParameter | None = None
        if parameter is not None and law is not None:
            if parameter not in RESPONSE_LAWS[law].parameter_names:
                context.add(
                    file,
                    line,
                    "parameter",
                    f"parameter {parameter!r} is not a parameter of {law}; it takes "
                    f"{', '.join(RESPONSE_LAWS[law].parameter_names)}.",
                )
                parameter = None
            else:
                spec = RESPONSE_LAWS[law].parameter(parameter)
        units = _required_text(row, "units", file=file, line=line, context=context)
        if units is not None and spec is not None:
            error = _unit_dimension_error(units, spec.reference_units)
            if error is not None:
                context.add(
                    file,
                    line,
                    "units",
                    f"{parameter} of {law} must be {spec.dimension_text}; units {units!r} do not fit ({error}).",
                )
                units = None
        value = _required_number(row, "value", file=file, line=line, context=context)
        if value is not None and units is not None and spec is not None:
            problem = _response_value_problem(value, units, spec)
            if problem is not None:
                context.add(file, line, "value", problem)
                value = None
        evidence_type = _required_text(row, "evidence_type", file=file, line=line, context=context)
        if evidence_type is not None and evidence_type not in RESPONSE_EVIDENCE_TYPES:
            context.add(
                file,
                line,
                "evidence_type",
                f"evidence_type must be one of {', '.join(RESPONSE_EVIDENCE_TYPES)}; a response law is "
                "measured, taken from the literature or estimated, not a design choice.",
            )
            evidence_type = None
        method = row.get("method", "")
        if evidence_type in _EVIDENCE_REQUIRES_METHOD and not method:
            context.add(file, line, "method", f"method is required for evidence_type {evidence_type!r}.")
            evidence_type = None
        source = _required_text(row, "source", file=file, line=line, context=context)
        reference_ok, tolerance, at_reference = _reference_columns(
            row,
            law=law,
            parameter=parameter,
            units=units,
            file=file,
            line=line,
            context=context,
        )
        if (
            strain_id is None
            or class_key is None
            or substrate_id is None
            or law is None
            or parameter is None
            or units is None
            or value is None
            or evidence_type is None
            or source is None
            or not reference_ok
        ):
            continue
        rows.append(
            _Response(
                row=line,
                strain_id=strain_id,
                class_key=class_key,
                substrate_id=substrate_id,
                law=law,
                parameter=parameter,
                value=value,
                units=units,
                evidence_type=evidence_type,
                method=method,
                source=source,
                reference_tolerance=tolerance,
                kinetics_at_reference=at_reference,
            )
        )
    return rows


def _response_value_problem(value: float, units: str, spec: ResponseLawParameter) -> str | None:
    if spec.reference_units == _TEMPERATURE_REFERENCE_UNITS:
        if float(Q_(value, units).to(_TEMPERATURE_REFERENCE_UNITS).magnitude) <= 0.0:
            return f"{spec.name} must be above absolute zero."
        return None
    if spec.reference_units == _DIMENSIONLESS_REFERENCE_UNITS:
        ph = float(Q_(value, units).to(_DIMENSIONLESS_REFERENCE_UNITS).magnitude)
        if not 0.0 <= ph <= 14.0:
            return f"{spec.name} {_number_text(value)} is outside pH 0 to 14."
        return None
    if value < 0.0:
        return f"{spec.name} must be nonnegative."
    return None


def _reference_columns(
    row: Mapping[str, str],
    *,
    law: str | None,
    parameter: str | None,
    units: str | None,
    file: str,
    line: int,
    context: _Context,
) -> tuple[bool, float | None, bool]:
    """Read reference_tolerance and kinetics_at_reference, allowed only on a law's reference parameter row."""

    tolerance_text = row.get("reference_tolerance", "")
    marker_text = row.get("kinetics_at_reference", "").lower()
    if not tolerance_text and not marker_text:
        return True, None, False
    if law is None or parameter is None:
        return False, None, False
    reference = RESPONSE_LAWS[law].reference_parameter
    ok = True
    if parameter != reference:
        for column, text in (("reference_tolerance", tolerance_text), ("kinetics_at_reference", marker_text)):
            if text:
                context.add(
                    file,
                    line,
                    column,
                    f"{column} belongs on the {reference} row of {law}, the law's reference condition.",
                )
        return False, None, False
    tolerance: float | None = None
    if tolerance_text:
        tolerance = _number(tolerance_text)
        if tolerance is None or tolerance < 0.0:
            context.add(
                file,
                line,
                "reference_tolerance",
                f"reference_tolerance must be a finite nonnegative number in the row's units ({units or 'units'}).",
            )
            ok = False
    if marker_text not in {"", _YES, _NO}:
        context.add(file, line, "kinetics_at_reference", "kinetics_at_reference must be yes or no when given.")
        ok = False
    return ok, tolerance, marker_text == _YES


def _activity_columns_ok(
    row: Mapping[str, str],
    *,
    quantity: str | None,
    substrate_id: str | None,
    file: str,
    line: int,
    context: _Context,
) -> bool:
    """Check activity_substrate and activity_saturating: required on assay_activity rows, refused elsewhere.

    An assay activity is the maximum rate on the case substrate only when it
    was measured on that substrate at saturating concentration; FungMod does
    not convert an activity between substrates or from a sub-saturating assay.
    """

    substrate_text = row.get("activity_substrate", "")
    saturating_text = row.get("activity_saturating", "").lower()
    if quantity != "assay_activity":
        ok = True
        for column in _ACTIVITY_COLUMNS:
            if row.get(column, "") and quantity is not None:
                context.add(file, line, column, f"{column} applies only to assay_activity rows.")
                ok = False
        return ok
    ok = True
    if not substrate_text:
        context.add(
            file,
            line,
            "activity_substrate",
            "assay_activity rows must state activity_substrate, the substrate_id the activity was measured "
            "on: only an activity measured on the case substrate at saturation is the Vmax on that substrate.",
        )
        ok = False
    elif substrate_id is not None and substrate_text != substrate_id:
        context.add(
            file,
            line,
            "activity_substrate",
            f"The assay activity was measured on {substrate_text!r}, not on the case substrate "
            f"{substrate_id!r}: an activity on another substrate is not the Vmax on this substrate, and FungMod "
            "does not convert activities between substrates. Measure the activity on this substrate at "
            "saturation, or give vmax, or a specific activity and enzyme loading for this substrate.",
        )
        ok = False
    if saturating_text == _NO:
        context.add(
            file,
            line,
            "activity_saturating",
            "The assay activity was not measured at saturating substrate: an activity below saturation is "
            "not the Vmax on this substrate (it depends on the assay substrate concentration through Km), and "
            "FungMod does not extrapolate it. Give an activity measured at saturation, or vmax with its method.",
        )
        ok = False
    elif saturating_text != _YES:
        context.add(
            file,
            line,
            "activity_saturating",
            "activity_saturating must be yes or no; only an activity measured at saturating substrate "
            "(yes) is accepted as the Vmax on the case substrate.",
        )
        ok = False
    return ok


def _kinetic_values(
    row: Mapping[str, str],
    *,
    quantity: str | None,
    file: str,
    line: int,
    context: _Context,
) -> tuple[float | None, float | None, float | None] | None:
    raw = {column: row.get(column, "") for column in ("value", "lower", "upper")}
    if raw["value"] and (raw["lower"] or raw["upper"]):
        context.add(file, line, "value", "Give either value (exact) or lower and upper (range), not both.")
        return None
    if not raw["value"] and not (raw["lower"] and raw["upper"]):
        column = "value" if not (raw["lower"] or raw["upper"]) else ("upper" if raw["lower"] else "lower")
        context.add(file, line, column, "Give either value (exact) or both lower and upper (range).")
        return None
    parsed: dict[str, float] = {}
    ok = True
    for column, text in raw.items():
        if not text:
            continue
        number = _number(text)
        if number is None:
            context.add(file, line, column, f"{column} must be a finite number.")
            ok = False
            continue
        if number < 0.0:
            context.add(file, line, column, f"{column} must be nonnegative.")
            ok = False
            continue
        parsed[column] = number
    if not ok:
        return None
    if "value" in parsed:
        if quantity == "km" and parsed["value"] <= 0.0:
            context.add(file, line, "value", "km must be positive.")
            return None
        return parsed["value"], None, None
    lower, upper = parsed["lower"], parsed["upper"]
    if not lower < upper:
        context.add(file, line, "upper", "lower must be smaller than upper.")
        return None
    if quantity == "km" and lower <= 0.0:
        context.add(file, line, "lower", "km must be positive.")
        return None
    return None, lower, upper


def _quantity_units_error(quantity: str, units: str) -> str | None:
    error = _unit_parse_error(units)
    if error is not None:
        return f"units {units!r} cannot be parsed: {error}"
    if quantity == "kcat":
        if _unit_dimension_error(units, _RATE_CONSTANT_REFERENCE_UNITS) is not None:
            return f"kcat units {units!r} must have the dimension 1/time (for example 1/s or 1/min)."
        return None
    if quantity in {"vmax", "assay_activity"}:
        if units_are_compatible(units, _MOLAR_RATE_REFERENCE_UNITS):
            return None
        if units_are_compatible(units, _MASS_RATE_REFERENCE_UNITS):
            return (
                f"{quantity} units {units!r} are a mass concentration per time; the substrate concentrations "
                f"and the {_YIELD_BASIS} yield are amounts, so this would need a molar mass, which FungMod does "
                "not assume. Use amount per volume per time (for example uM/min or U/mL)."
            )
        return (
            f"{quantity} units {units!r} must be an amount per volume per time (for example uM/min, mM/s or "
            "U/mL, where U is one micromole per minute)."
        )
    if quantity == "specific_activity":
        if units_are_compatible(units, _SPECIFIC_ACTIVITY_REFERENCE_UNITS):
            return None
        return (
            f"specific_activity units {units!r} must be an amount per time per enzyme mass (for example "
            "umol/min/mg or U/mg)."
        )
    if quantity == "enzyme_loading":
        if units_are_compatible(units, _MASS_REFERENCE_UNITS):
            return None
        return (
            f"enzyme_loading units {units!r} must be an enzyme mass per volume (for example mg/L); a molar "
            "enzyme concentration belongs to the kcat form as enzyme_concentration."
        )
    if _concentration_kind(units) is None:
        return (
            f"{quantity} units {units!r} must be a substrate concentration (amount or mass per volume, "
            "for example mM, uM or g/L)."
        )
    return None


def _proteome_without_class(strain_id: str, genome: _ProteomeAnnotation) -> str:
    resolution = genome.resolution
    return (
        f"Strain {strain_id!r} declares no enzyme class in enzymes.csv, and its UniProt export ({GENOME_TABLE} row "
        f"{genome.row}) resolved no enzyme class with a registry record (classes without a record: "
        f"{', '.join(resolution.capabilities_without_model) or 'none'}; unmapped families: "
        f"{', '.join(resolution.unmapped_families) or 'none'}; unresolved EC numbers: "
        f"{', '.join(resolution.unresolved_ec_numbers) or 'none'}; proteins whose EC numbers and CAZy families "
        f"disagree: {', '.join(item.accession for item in resolution.disagreements) or 'none'}). FungMod does not "
        "create enzyme classes from a proteome; declare the strain's classes in enzymes.csv."
    )


def _cross_validate(parsed: _Parsed, context: _Context) -> None:
    declared_strains = {item.strain_id for item in parsed.strain_classes}
    resolved_genomes = {genome.strain_id: genome for genome in parsed.genomes}
    for strain in parsed.strains.values():
        if strain.strain_id in declared_strains:
            continue
        genome = resolved_genomes.get(strain.strain_id)
        if isinstance(genome, _ProteomeAnnotation):
            context.add("strains.csv", strain.row, "strain_id", _proteome_without_class(strain.strain_id, genome))
        elif genome is not None:
            without_record = sorted({item.enzyme_class for item in genome.capabilities if not item.modellable})
            context.add(
                "strains.csv",
                strain.row,
                "strain_id",
                f"Strain {strain.strain_id!r} declares no enzyme class in enzymes.csv, and its genome annotation "
                f"({GENOME_TABLE} row {genome.row}) resolved no enzyme class with a registry record (classes "
                f"without a record: {', '.join(without_record) or 'none'}; unmapped families: "
                f"{', '.join(genome.unmapped_families) or 'none'}). FungMod does not create enzyme classes from a "
                "genome annotation; declare the strain's classes in enzymes.csv.",
            )
        elif strain.strain_id not in parsed.genome_rows:
            # A strain whose genomes.csv row was refused is already reported on that row.
            context.add(
                "strains.csv",
                strain.row,
                "strain_id",
                f"Strain {strain.strain_id!r} declares no enzyme class in enzymes.csv.",
            )
    by_key: dict[tuple[str, str, str, str, str], list[_Kinetics]] = {}
    for row in parsed.kinetics:
        by_key.setdefault((*row.case_key, row.quantity), []).append(row)
    for key, rows in by_key.items():
        if len(rows) < 2:
            continue
        kinds = {"exact" if row.value is not None else "range" for row in rows}
        detail = (
            "an exact value and a range for the same quantity conflict"
            if kinds == {"exact", "range"}
            else "duplicate or conflicting rows for the same quantity"
        )
        row_numbers = ", ".join(str(row.row) for row in rows)
        for row in rows[1:]:
            context.add(
                "kinetics.csv",
                row.row,
                "quantity",
                f"Rows {row_numbers} give {key[4]} for strain {key[0]!r}, class {key[1]!r}, substrate {key[2]!r}, "
                f"condition {key[3]!r}: {detail}.",
            )
    by_case: dict[tuple[str, str, str, str], list[_Kinetics]] = {}
    for row in parsed.kinetics:
        by_case.setdefault(row.case_key, []).append(row)
    for case_key, rows in by_case.items():
        concentration_rows = [row for row in rows if row.quantity in _CONCENTRATION_QUANTITIES]
        kinds = {row.row: _concentration_kind(row.units) for row in concentration_rows}
        molar = [row for row in concentration_rows if kinds[row.row] == "molar"]
        mass = [row for row in concentration_rows if kinds[row.row] == "mass"]
        if molar and mass:
            for row in mass:
                context.add(
                    "kinetics.csv",
                    row.row,
                    "units",
                    f"{row.quantity} in {row.units!r} is a mass concentration while row {molar[0].row} gives "
                    f"{molar[0].quantity} in {molar[0].units!r} (amount per volume); combining them would need a "
                    "molar mass, and FungMod does not convert between molar and mass concentrations.",
                )
        elif mass:
            context.add(
                "kinetics.csv",
                mass[0].row,
                "units",
                f"{mass[0].quantity} in {mass[0].units!r} is a mass concentration, but the product yield is "
                f"{_YIELD_BASIS}; applying it would need molar masses. Use amount-per-volume units (for example mM).",
            )
    _validate_rate_forms(parsed, context)
    _validate_responses(parsed, context)
    _validate_pairs(parsed, context)


def _rows_text(rows: Sequence[Any]) -> str:
    numbers = sorted({int(row.row) for row in rows})
    if len(numbers) == 1:
        return f"row {numbers[0]}"
    return f"rows {', '.join(str(number) for number in numbers)}"


def _case_form_rows(rows: Sequence[_Kinetics]) -> tuple[list[_Kinetics], dict[str, list[_Kinetics]]]:
    """Split a case's rows into kcat-form rows and Vmax-route rows (route name to rows)."""

    kcat_rows = [row for row in rows if row.quantity in _KCAT_FORM_QUANTITIES]
    routes: dict[str, list[_Kinetics]] = {}
    for row in rows:
        route = _QUANTITY_VMAX_ROUTE.get(row.quantity)
        if route is not None:
            routes.setdefault(route, []).append(row)
    return kcat_rows, routes


def _validate_rate_forms(parsed: _Parsed, context: _Context) -> None:
    """Check that each case and each enzyme class and substrate pair uses one rate form.

    A case is one strain, enzyme class, substrate and condition. It uses the
    kcat form (kcat and an enzyme concentration) or the Vmax form, and the
    Vmax form takes exactly one route. All cases of one enzyme class and
    substrate share one generated process, so they share one form. The form of
    a pair is stored in ``parsed.pair_forms``; a pair without any rate row has
    no entry.
    """

    file = "kinetics.csv"
    by_case: dict[tuple[str, str, str, str], list[_Kinetics]] = {}
    for row in parsed.kinetics:
        by_case.setdefault(row.case_key, []).append(row)
    case_forms: dict[tuple[str, str, str, str], str] = {}
    for case_key, rows in by_case.items():
        kcat_rows, routes = _case_form_rows(rows)
        consistent = True
        if kcat_rows and routes:
            kcat_quantities = " and ".join(dict.fromkeys(row.quantity for row in kcat_rows))
            for route_rows in routes.values():
                for row in route_rows:
                    context.add(
                        file,
                        row.row,
                        "quantity",
                        f"Row {row.row} gives {row.quantity} while {_rows_text(kcat_rows)} give {kcat_quantities} "
                        "for the same strain, class, substrate and condition: the kcat form needs kcat and an "
                        "enzyme concentration, the Vmax form needs Vmax and no enzyme concentration. One case uses "
                        "one form, and FungMod does not derive one from the other.",
                    )
            consistent = False
        if len(routes) > 1:
            ordered = sorted(routes.items(), key=lambda item: min(row.row for row in item[1]))
            summary = "; ".join(f"{_rows_text(route_rows)} use {_VMAX_ROUTE_LABEL[route]}" for route, route_rows in ordered)
            for _route, route_rows in ordered[1:]:
                for row in route_rows:
                    context.add(
                        file,
                        row.row,
                        "quantity",
                        "Vmax for one case comes from exactly one route ("
                        f"{', '.join(_VMAX_ROUTE_LABEL[name] for name in VMAX_ROUTES)}); {summary}.",
                    )
            consistent = False
        activity_rows = routes.get("specific_activity", [])
        if consistent and len(activity_rows) == 2 and not any(row.is_exact for row in activity_rows):
            context.add(
                file,
                max(row.row for row in activity_rows),
                "value",
                f"specific_activity and enzyme_loading ({_rows_text(activity_rows)}) are both ranges; their "
                "product is not a uniform range, so FungMod does not form it. Give one of them as an exact value.",
            )
            consistent = False
        if not consistent:
            continue
        if kcat_rows:
            case_forms[case_key] = RATE_FORM_KCAT
        elif routes:
            case_forms[case_key] = RATE_FORM_VMAX
    by_pair: dict[tuple[str, str], dict[str, list[tuple[str, str, str, str]]]] = {}
    for case_key, form in case_forms.items():
        by_pair.setdefault((case_key[1], case_key[2]), {}).setdefault(form, []).append(case_key)
    for pair, forms in by_pair.items():
        if len(forms) == 1:
            parsed.pair_forms[pair] = next(iter(forms))
            continue
        kcat_rows = [row for case_key in forms[RATE_FORM_KCAT] for row in _case_form_rows(by_case[case_key])[0]]
        for case_key in forms[RATE_FORM_VMAX]:
            for route_rows in _case_form_rows(by_case[case_key])[1].values():
                for row in route_rows:
                    context.add(
                        file,
                        row.row,
                        "quantity",
                        f"Enzyme class {pair[0]!r} on substrate {pair[1]!r} uses the kcat form in "
                        f"{_rows_text(kcat_rows)} and the Vmax form in row {row.row}. All strains and conditions "
                        "of one enzyme class and substrate share one generated process (FungMod selects a process "
                        "by enzyme class and substrate class), so they must use one rate form.",
                    )


def _validate_responses(parsed: _Parsed, context: _Context) -> None:
    """Check response-law rows and the reference-condition rule; store valid laws in ``parsed.laws``."""

    file = "responses.csv"
    groups: dict[tuple[str, str, str], dict[str, dict[str, list[_Response]]]] = {}
    for response in parsed.responses:
        groups.setdefault(response.binding_key, {}).setdefault(response.law, {}).setdefault(
            response.parameter, []
        ).append(response)
    valid: dict[tuple[str, str, str], dict[str, dict[str, _Response]]] = {}
    for binding, laws in groups.items():
        where = _binding_text(binding)
        for law_name, parameters in laws.items():
            law = RESPONSE_LAWS[law_name]
            ok = True
            for name, rows in parameters.items():
                for row in rows[1:]:
                    context.add(
                        file,
                        row.row,
                        "parameter",
                        f"{_rows_text(rows)} give {name} of {law_name} for {where}; give each parameter once.",
                    )
                    ok = False
            first_row = min(row.row for rows in parameters.values() for row in rows)
            missing = [name for name in law.parameter_names if name not in parameters]
            if missing:
                context.add(
                    file,
                    first_row,
                    "parameter",
                    f"{law_name} for {where} needs {', '.join(law.parameter_names)}; missing: {', '.join(missing)}.",
                )
                ok = False
            if not ok:
                continue
            chosen = {name: rows[0] for name, rows in parameters.items()}
            problem = _law_domain_problem(law, chosen)
            if problem is not None:
                context.add(
                    file,
                    first_row,
                    "value",
                    f"The {law_name} parameters for {where} ({_rows_text(list(chosen.values()))}) are outside "
                    f"the law's domain: {problem}",
                )
                continue
            valid.setdefault(binding, {})[law_name] = chosen
    for binding, laws in valid.items():
        by_condition: dict[str, list[str]] = {}
        for law_name in laws:
            by_condition.setdefault(RESPONSE_LAWS[law_name].condition, []).append(law_name)
        for condition, names in by_condition.items():
            for law_name in names[1:]:
                context.add(
                    file,
                    min(row.row for row in laws[law_name].values()),
                    "law",
                    f"{_binding_text(binding)} binds {' and '.join(names)} to {condition}; give one law per "
                    "condition, since two laws would both rescale the same rate.",
                )
    _validate_pair_laws(valid, context)
    for binding, laws in valid.items():
        for law_name, chosen in laws.items():
            _validate_reference_condition(parsed, binding, RESPONSE_LAWS[law_name], chosen, context)
    parsed.laws = valid


def _validate_pair_laws(
    valid: Mapping[tuple[str, str, str], Mapping[str, Mapping[str, _Response]]],
    context: _Context,
) -> None:
    """All strains of one enzyme class and substrate share the template, so they must agree on each condition's law."""

    users: dict[tuple[str, str], dict[str, dict[str, list[_Response]]]] = {}
    for binding, laws in valid.items():
        for law_name, chosen in laws.items():
            users.setdefault((binding[1], binding[2]), {}).setdefault(RESPONSE_LAWS[law_name].condition, {}).setdefault(
                law_name, []
            ).extend(chosen.values())
    for pair, by_condition in users.items():
        for condition, laws in by_condition.items():
            if len(laws) < 2:
                continue
            ordered = sorted(laws.items(), key=lambda item: min(row.row for row in item[1]))
            summary = "; ".join(f"{_rows_text(rows)} use {law_name}" for law_name, rows in ordered)
            for _law_name, rows in ordered[1:]:
                context.add(
                    "responses.csv",
                    min(row.row for row in rows),
                    "law",
                    f"Enzyme class {pair[0]!r} on substrate {pair[1]!r} has different {condition} laws for "
                    f"different strains ({summary}). All strains of one enzyme class and substrate share one "
                    "generated case template, so they must use the same law for a condition.",
                )


def _validate_reference_condition(
    parsed: _Parsed,
    binding: tuple[str, str, str],
    law: ResponseLaw,
    chosen: Mapping[str, _Response],
    context: _Context,
) -> None:
    """Refuse kinetic constants that are not stated at the law's reference condition.

    The law multiplies the configured rate by an activity that is one at its
    reference parameter (the optimum of a cardinal law, the reference
    temperature of Arrhenius). Kinetic constants measured elsewhere would be
    rescaled as if they were reference values. A condition matches when it
    equals the reference value exactly, or within the reference row's own
    ``reference_tolerance``; ``kinetics_at_reference = yes`` records the
    user's declaration that the values are reference values.
    """

    reference = chosen[law.reference_parameter]
    rows_by_condition: dict[str, list[_Kinetics]] = {}
    for row in parsed.kinetics:
        if (row.strain_id, row.class_key, row.substrate_id) == binding and row.quantity in _KINETIC_CONSTANT_QUANTITIES:
            rows_by_condition.setdefault(row.condition_id, []).append(row)
    for condition_id in sorted(rows_by_condition):
        condition = parsed.conditions[condition_id]
        rows = rows_by_condition[condition_id]
        current = condition.temperature_kelvin if law.condition == "temperature" else condition.ph
        if current is None:
            context.add(
                "responses.csv",
                reference.row,
                "value",
                f"Condition {condition_id!r} has an unknown {law.condition}, but kinetics.csv {_rows_text(rows)} give "
                f"kinetic constants there for {_binding_text(binding)}, whose rate {law.law} scales with the "
                f"{law.condition}. State the {law.condition} in conditions.csv.",
            )
            continue
        if reference.kinetics_at_reference:
            continue
        # Conditions hold temperatures in kelvin and pH as a plain number, the reference units of the law.
        base_units = law.parameter(law.reference_parameter).reference_units
        stated = float(Q_(current, base_units).to(reference.units).magnitude)
        difference = abs(stated - reference.value)
        tolerance = reference.reference_tolerance
        within = difference == 0.0 if tolerance is None else difference <= tolerance
        if within:
            continue
        tolerance_text = (
            "no reference_tolerance is given"
            if tolerance is None
            else f"reference_tolerance is {_number_text(tolerance)} {reference.units}"
        )
        context.add(
            "responses.csv",
            reference.row,
            "value",
            f"The kinetic constants of {_binding_text(binding)} at condition {condition_id!r} "
            f"({_condition_text(condition)}; kinetics.csv {_rows_text(rows)}) are not at the reference condition "
            f"of {law.law}, {law.reference_parameter} {_number_text(reference.value)} {reference.units} "
            f"(differs by {_number_text(difference)} {reference.units}; {tolerance_text}). The law rescales the "
            f"reference value ({law.formula}), so the kinetic constants it scales must be stated at its reference "
            "condition. State the kinetics at the reference condition, give a reference_tolerance on this row that "
            "covers the difference, or set kinetics_at_reference to yes if the values are already reference values.",
        )


_LAW_CHECK_SOURCE = "FungMod user-data response-law domain check"


def _check_cardinal_temperature(values: Mapping[str, Any]) -> None:
    cardinal_temperature_activity(
        temperature=values["optimum_temperature"],
        minimum_temperature=values["minimum_temperature"],
        optimum_temperature=values["optimum_temperature"],
        maximum_temperature=values["maximum_temperature"],
        source=_LAW_CHECK_SOURCE,
    )


def _check_cardinal_ph(values: Mapping[str, Any]) -> None:
    cardinal_ph_activity(
        ph=values["optimum_ph"],
        minimum_ph=values["minimum_ph"],
        optimum_ph=values["optimum_ph"],
        maximum_ph=values["maximum_ph"],
        source=_LAW_CHECK_SOURCE,
    )


def _check_arrhenius_reference(values: Mapping[str, Any]) -> None:
    arrhenius_reference_scaled_rate(
        reference_rate=Q_(1.0, _DIMENSIONLESS_REFERENCE_UNITS),
        activation_energy=values["activation_energy"],
        temperature=values["reference_temperature"],
        reference_temperature=values["reference_temperature"],
        source=_LAW_CHECK_SOURCE,
    )


# Each check evaluates the implemented law at its reference value, so the law's
# own domain rules (ordering of cardinal values, the CTMI midpoint condition,
# nonnegative activation energy) decide; nothing is re-implemented here.
_LAW_DOMAIN_CHECKS = {
    "temperature_cardinal_rosso": _check_cardinal_temperature,
    "ph_cardinal_rosso": _check_cardinal_ph,
    "temperature_arrhenius_reference": _check_arrhenius_reference,
}


def _law_domain_problem(law: ResponseLaw, chosen: Mapping[str, _Response]) -> str | None:
    values = {
        name: Q_(row.value, row.units).to(law.parameter(name).reference_units) for name, row in chosen.items()
    }
    try:
        _LAW_DOMAIN_CHECKS[law.law](values)
    except ValueError as exc:
        return str(exc)
    return None


def _binding_text(binding: tuple[str, str, str]) -> str:
    return f"strain {binding[0]!r}, enzyme class {binding[1]!r}, substrate {binding[2]!r}"


def _validate_pairs(parsed: _Parsed, context: _Context) -> None:
    for class_key in sorted({item.class_key for item in parsed.strain_classes}):
        info = parsed.classes[class_key]
        by_substrate_class: dict[str, _Substrate] = {}
        for substrate in parsed.substrates.values():
            if _shared_bonds(info, substrate) is None:
                continue
            other = by_substrate_class.get(substrate.substrate_class)
            if other is not None:
                context.add(
                    "substrates.csv",
                    substrate.row,
                    "substrate_class",
                    f"Substrates {other.substrate_id!r} (row {other.row}) and {substrate.substrate_id!r} share "
                    f"substrate class {substrate.substrate_class!r} and are both compatible with enzyme class "
                    f"{class_key!r}. FungMod selects a process by enzyme class and substrate class, so this "
                    "increment needs a distinct substrate class per substrate.",
                )
                continue
            by_substrate_class[substrate.substrate_class] = substrate
            states = _state_names(
                class_key,
                substrate,
                form=parsed.pair_forms.get((class_key, substrate.substrate_id), RATE_FORM_KCAT),
            )
            if len(set(states.values())) != len(states):
                context.add(
                    "substrates.csv",
                    substrate.row,
                    "product",
                    f"Substrate {substrate.substrate_id!r}, product {substrate.product!r} and enzyme class "
                    f"{class_key!r} would share a model state name; rename one of them.",
                )


# ---------------------------------------------------------------------------
# Record generation


def _generate_records(
    parsed: _Parsed,
    context: _Context,
    *,
    dataset_id: str,
    digest: str,
    manifest: Mapping[str, Any],
) -> _Generated:
    generated = _Generated(
        mappings={name: [] for name in _RECORD_TYPES},
        objects={name: [] for name in _RECORD_TYPES},
        base_references={},
        origins={},
    )
    namespace = _Namespace(dataset_id=dataset_id, digest=digest, manifest=manifest)
    used_classes = list(dict.fromkeys(item.class_key for item in parsed.strain_classes))
    for class_key in used_classes:
        info = parsed.classes[class_key]
        if info.origin == "registry":
            generated.base_references[("enzyme_classes", class_key)] = context.base.get_enzyme_class(class_key).to_dict()
    for substrate in parsed.substrates.values():
        if substrate.registry_id:
            generated.base_references[("substrates", substrate.registry_id)] = context.base.get_substrate(
                substrate.registry_id
            ).to_dict()

    for class_key in used_classes:
        _emit(
            generated,
            context,
            "enzyme_classes",
            _enzyme_class_mapping(parsed.classes[class_key], namespace),
            origin=("enzyme_classes.csv", parsed.classes[class_key].row, "class_id")
            if parsed.classes[class_key].origin == "user"
            else (*_first_class_row(parsed, class_key), "enzyme_class"),
        )
    for strain in parsed.strains.values():
        declared = [item for item in parsed.strain_classes if item.strain_id == strain.strain_id]
        _emit(
            generated,
            context,
            "fungi",
            _fungus_mapping(
                strain,
                declared,
                parsed.classes,
                namespace,
                genome_row=parsed.genome_rows.get(strain.strain_id),
            ),
            origin=("strains.csv", strain.row, "strain_id"),
        )
    for substrate in parsed.substrates.values():
        if not substrate.registry_id:
            _emit(
                generated,
                context,
                "substrates",
                _substrate_mapping(substrate, namespace),
                origin=("substrates.csv", substrate.row, "substrate_id"),
            )
    for condition in parsed.conditions.values():
        _emit(
            generated,
            context,
            "environments",
            _environment_mapping(condition, namespace),
            origin=("conditions.csv", condition.row, "condition_id"),
        )

    rows_by_case: dict[tuple[str, str, str, str], dict[str, _Kinetics]] = {}
    for row in parsed.kinetics:
        rows_by_case.setdefault(row.case_key, {})[row.quantity] = row
    pairs: list[tuple[str, _Substrate]] = [
        (class_key, substrate)
        for class_key in used_classes
        for substrate in parsed.substrates.values()
        if _shared_bonds(parsed.classes[class_key], substrate) is not None
    ]
    for class_key, substrate in pairs:
        pair = (class_key, substrate.substrate_id)
        started = pair in parsed.pair_forms
        form = parsed.pair_forms.get(pair, RATE_FORM_KCAT)
        laws = _pair_laws(parsed, pair)
        info = parsed.classes[class_key]
        pair_records: list[ParameterRecord] = []
        for item in parsed.strain_classes:
            if item.class_key != class_key:
                continue
            strain = parsed.strains[item.strain_id]
            strain_laws = parsed.laws.get((strain.strain_id, class_key, substrate.substrate_id), {})
            for condition in parsed.conditions.values():
                case_rows = rows_by_case.get((strain.strain_id, class_key, substrate.substrate_id, condition.condition_id), {})
                case = _CaseContext(
                    strain=strain,
                    info=info,
                    substrate=substrate,
                    condition=condition,
                    namespace=namespace,
                    case_rows=case_rows,
                    form_started=started,
                    laws=tuple(strain_laws),
                    genome=item.genome if item.genome_only else None,
                )
                for quantity in _FORM_QUANTITIES[form]:
                    mapping, origin = _role_mapping(quantity, case)
                    record = _emit(generated, context, "parameter_records", mapping, origin=origin)
                    if isinstance(record, ParameterRecord):
                        pair_records.append(record)
            for law in laws:
                for parameter in law.parameters:
                    response = strain_laws.get(law.law, {}).get(parameter.name)
                    if response is not None:
                        mapping = _response_mapping(
                            response,
                            law=law,
                            law_rows=strain_laws[law.law],
                            strain=strain,
                            info=info,
                            substrate=substrate,
                            namespace=namespace,
                            reference_conditions=_reference_conditions(parsed, response.binding_key),
                        )
                        origin: tuple[str, int | None, str | None] = ("responses.csv", response.row, "parameter")
                    else:
                        mapping = _response_gap_mapping(
                            law,
                            parameter,
                            strain=strain,
                            info=info,
                            substrate=substrate,
                            namespace=namespace,
                            genome=item.genome if item.genome_only else None,
                        )
                        origin = ("responses.csv", None, "parameter")
                    record = _emit(generated, context, "parameter_records", mapping, origin=origin)
                    if isinstance(record, ParameterRecord):
                        pair_records.append(record)
        scientific = bool(pair_records) and all(
            record.value.is_exact and parameter_record_is_mode_eligible(record, mode="scientific")
            for record in pair_records
        )
        _emit(
            generated,
            context,
            "case_templates",
            _template_mapping(info, substrate, namespace, scientific=scientific, form=form, laws=laws),
            origin=("substrates.csv", substrate.row, "substrate_id"),
        )
        _emit(
            generated,
            context,
            "process_compatibility",
            _compatibility_mapping(info, substrate, namespace, form=form, laws=laws),
            origin=("substrates.csv", substrate.row, "substrate_id"),
        )
    return generated


@dataclass(frozen=True)
class _CaseContext:
    """One strain, enzyme class, substrate and condition during record generation."""

    strain: _Strain
    info: _EnzymeClassInfo
    substrate: _Substrate
    condition: _Condition
    namespace: _Namespace
    case_rows: Mapping[str, _Kinetics]
    form_started: bool
    laws: tuple[str, ...]
    # Set when the class of this strain comes from its genome annotation alone.
    genome: _ClassEvidence | None = None


def _pair_laws(parsed: _Parsed, pair: tuple[str, str]) -> tuple[ResponseLaw, ...]:
    """Laws bound by any strain to one enzyme class and substrate, in ``RESPONSE_LAWS`` order."""

    used = {
        law_name
        for binding, laws in parsed.laws.items()
        if (binding[1], binding[2]) == pair
        for law_name in laws
    }
    return tuple(law for name, law in RESPONSE_LAWS.items() if name in used)


def _reference_conditions(parsed: _Parsed, binding: tuple[str, str, str]) -> list[str]:
    """Conditions at which the binding has kinetic constants, all checked against the law's reference."""

    return sorted(
        {
            row.condition_id
            for row in parsed.kinetics
            if (row.strain_id, row.class_key, row.substrate_id) == binding and row.quantity in _KINETIC_CONSTANT_QUANTITIES
        }
    )


def _role_mapping(quantity: str, case: _CaseContext) -> tuple[dict[str, Any], tuple[str, int | None, str | None]]:
    """Return the parameter or gap mapping of one role quantity of a case, with its origin."""

    if quantity == "vmax":
        return _vmax_mapping(case)
    row = case.case_rows.get(quantity)
    if row is not None:
        return _parameter_mapping(row, case=case), ("kinetics.csv", row.row, "quantity")
    return _gap_mapping(quantity, case=case), ("kinetics.csv", None, "quantity")


@dataclass(frozen=True)
class _Namespace:
    dataset_id: str
    digest: str
    manifest: Mapping[str, Any]

    def id(self, *parts: str) -> str:
        return "__".join((self.dataset_id, *parts))

    @property
    def contributor(self) -> str | None:
        value = self.manifest.get("contributor")
        return str(value) if value is not None else None

    @property
    def source(self) -> str:
        value = self.manifest.get("source")
        if _is_text(value):
            return str(value)
        return f"User dataset {self.dataset_id} (per-row sources in its tables)"

    def provenance(self, file: str, row: int | None, **extra: Any) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "digest": self.digest,
            "file": file,
            "row": row,
            "contributor": self.contributor,
            **extra,
        }


def _emit(
    generated: _Generated,
    context: _Context,
    record_type: str,
    mapping: Mapping[str, Any],
    *,
    origin: tuple[str, int | None, str | None],
) -> RegistryRecord | None:
    try:
        record = load_registry_record_mapping(cast(RegistryRecordType, record_type), mapping)
    except (RegistryLoadError, ValueError, TypeError) as exc:
        context.add(origin[0], origin[1], origin[2], f"Generated {record_type} record is invalid: {exc}")
        return None
    generated.mappings[record_type].append(mapping)
    generated.objects[record_type].append(record)
    generated.origins[(record_type, record.record_id)] = origin
    return record


def _first_class_row(parsed: _Parsed, class_key: str) -> tuple[str, int | None]:
    return next(
        ((item.file, item.row) for item in parsed.strain_classes if item.class_key == class_key),
        ("enzymes.csv", None),
    )


def _enzyme_class_mapping(info: _EnzymeClassInfo, namespace: _Namespace) -> dict[str, Any]:
    if info.origin == "registry":
        provenance: dict[str, Any] = {
            "source": f"Registry enzyme class {info.key} attributes reused for user dataset {namespace.dataset_id}",
            "confidence_level": "user_supplied",
            "registry_parent_enzyme_class": info.key,
            "registry_parent_maturity": info.parent_maturity,
            USER_DATASET_PROVENANCE_KEY: namespace.provenance("enzymes.csv", None),
        }
        notes = (
            f"Namespaced copy of registry enzyme class {info.key} for user dataset {namespace.dataset_id}; "
            "bond and substrate-class compatibility come from the registry record, the strain assignment "
            "from the user's enzymes.csv. Restricted to homogeneous Michaelis-Menten kinetics."
        )
    else:
        provenance = {
            "source": info.source,
            "confidence_level": "user_supplied",
            USER_DATASET_PROVENANCE_KEY: namespace.provenance("enzyme_classes.csv", info.row),
        }
        notes = (
            f"User-defined enzyme class {info.key} from dataset {namespace.dataset_id}; "
            "restricted to homogeneous Michaelis-Menten kinetics."
        )
    mapping: dict[str, Any] = {
        "record_id": namespace.id(info.key),
        "name": f"{info.name} ({namespace.dataset_id} user dataset)",
        "maturity": USER_DATASET_RECORD_MATURITY,
        "provenance": provenance,
        "notes": notes,
        "target_bond_classes": list(info.target_bond_classes),
        "compatible_substrate_classes": list(info.compatible_substrate_classes),
        "compatible_processes": [USER_DATASET_PROCESS_TYPE],
    }
    if info.ec_number:
        mapping["ec_number"] = info.ec_number
    return mapping


def _fungus_mapping(
    strain: _Strain,
    declared: Sequence[_StrainClass],
    classes: Mapping[str, _EnzymeClassInfo],
    namespace: _Namespace,
    *,
    genome_row: int | None = None,
) -> dict[str, Any]:
    aliases = list(dict.fromkeys((strain.strain_id, *strain.aliases)))
    class_sources = (
        "come from the user's enzymes.csv"
        if genome_row is None
        else (
            f"come from the user's enzymes.csv and from the genome annotation in {GENOME_TABLE} row {genome_row} "
            "(classes with a registry record only; an explicit enzymes.csv row wins). The annotation shows which "
            "classes the strain can encode, not their expression or rates"
        )
    )
    mapping: dict[str, Any] = {
        "record_id": namespace.id(strain.strain_id),
        "name": strain.name,
        "aliases": aliases,
        "maturity": USER_DATASET_RECORD_MATURITY,
        "provenance": {
            "source": namespace.source,
            "confidence_level": "user_supplied",
            "enzyme_class_evidence": {
                namespace.id(item.class_key): _class_evidence(item, classes) for item in declared
            },
            USER_DATASET_PROVENANCE_KEY: namespace.provenance("strains.csv", strain.row),
        },
        "enzyme_classes": [namespace.id(item.class_key) for item in declared],
        "assimilable_products": [],
        "notes": (
            f"User-supplied strain {strain.strain_id} from dataset {namespace.dataset_id}. Its enzyme classes "
            f"{class_sources}; no growth, secretion or uptake model is implied."
        ),
    }
    if strain.scientific_name:
        mapping["scientific_name"] = strain.scientific_name
    return mapping


def _class_evidence(item: _StrainClass, classes: Mapping[str, _EnzymeClassInfo]) -> dict[str, Any]:
    """The evidence for one declared class: the explicit row or the annotation, and the annotation when both."""

    evidence: dict[str, Any] = {
        "enzyme_class": item.class_key,
        "class_origin": classes[item.class_key].origin,
        "evidence": item.evidence,
        "source": item.source,
        "file": item.file,
        "row": item.row,
    }
    if item.genome is not None:
        evidence["declared_by"] = item.file
        evidence["genome_annotation"] = item.genome.to_dict()
    return evidence


def _substrate_mapping(substrate: _Substrate, namespace: _Namespace) -> dict[str, Any]:
    return {
        "record_id": namespace.id(substrate.substrate_id),
        "name": substrate.name,
        "aliases": [substrate.substrate_id],
        "maturity": USER_DATASET_RECORD_MATURITY,
        "provenance": {
            "source": substrate.source,
            "confidence_level": "user_supplied",
            USER_DATASET_PROVENANCE_KEY: namespace.provenance("substrates.csv", substrate.row),
        },
        "substrate_class": substrate.substrate_class,
        "physical_state": "dissolved",
        "bond_classes": list(substrate.bond_classes),
        "products": [substrate.product],
        "properties": {},
        "notes": f"User-defined dissolved substrate {substrate.substrate_id} from dataset {namespace.dataset_id}.",
    }


def _environment_mapping(condition: _Condition, namespace: _Namespace) -> dict[str, Any]:
    row_source = f"User dataset {namespace.dataset_id}, conditions.csv row {condition.row}"
    if condition.temperature_kelvin is None:
        temperature: dict[str, Any] = {
            "kind": "unknown",
            "units": "kelvin",
            "source": row_source,
            "confidence_level": "user_supplied",
            "notes": "Stated as unknown in conditions.csv.",
        }
    else:
        temperature = {
            "kind": "exact",
            "value": condition.temperature_kelvin,
            "units": "kelvin",
            "source": row_source,
            "confidence_level": "user_supplied",
            "notes": (
                f"Original value {condition.temperature_text} {condition.temperature_units}"
                + (" converted to kelvin." if condition.temperature_units != "kelvin" else ".")
            ),
        }
    if condition.ph is None:
        ph: dict[str, Any] = {
            "kind": "unknown",
            "units": "dimensionless",
            "source": row_source,
            "confidence_level": "user_supplied",
            "notes": "Stated as unknown in conditions.csv.",
        }
    else:
        ph = {
            "kind": "exact",
            "value": condition.ph,
            "units": "dimensionless",
            "source": row_source,
            "confidence_level": "user_supplied",
            "notes": f"Original value {condition.ph_text}.",
        }
    notes = f"User-supplied assay condition {condition.condition_id} from dataset {namespace.dataset_id}."
    if condition.notes:
        notes = f"{notes} {condition.notes}"
    return {
        "record_id": namespace.id(condition.condition_id),
        "name": f"{namespace.dataset_id} condition {condition.condition_id} ({_condition_text(condition)})",
        "aliases": [condition.condition_id],
        "maturity": USER_DATASET_RECORD_MATURITY,
        "provenance": {
            "source": namespace.source,
            "confidence_level": "user_supplied",
            USER_DATASET_PROVENANCE_KEY: namespace.provenance("conditions.csv", condition.row),
        },
        "conditions": {"temperature": temperature, "ph": ph},
        "notes": notes,
    }


def _compatibility_mapping(
    info: _EnzymeClassInfo,
    substrate: _Substrate,
    namespace: _Namespace,
    *,
    form: str,
    laws: Sequence[ResponseLaw],
) -> dict[str, Any]:
    shared = _shared_bonds(info, substrate) or ()
    roles = HOMOGENEOUS_MM_PARAMETER_ROLES if form == RATE_FORM_KCAT else HOMOGENEOUS_MM_VMAX_PARAMETER_ROLES
    symbols = {
        role: _parameter_symbol(namespace, _ROLE_QUANTITY[role], info.key, substrate.substrate_id) for role in roles
    }
    for law in laws:
        for parameter in law.parameters:
            symbols[parameter.name] = _law_symbol(namespace, law, parameter, info.key, substrate.substrate_id)
    return {
        "record_id": namespace.id(info.key, substrate.substrate_id, "homogeneous_mm"),
        "name": f"{info.name} on {substrate.name} homogeneous Michaelis-Menten ({namespace.dataset_id})",
        "maturity": USER_DATASET_RECORD_MATURITY,
        "provenance": {
            "source": namespace.source,
            "confidence_level": "user_supplied",
            USER_DATASET_PROVENANCE_KEY: namespace.provenance("substrates.csv", substrate.row),
        },
        "enzyme_class": namespace.id(info.key),
        "substrate_class": substrate.substrate_class,
        "required_bond_classes": list(shared),
        "process_type": USER_DATASET_PROCESS_TYPE,
        "required_parameters": list(symbols.values()),
        "parameter_roles": dict(symbols),
        "product_map_required": True,
        "case_template_id": _template_id(namespace, info, substrate),
        "notes": (
            f"Homogeneous Michaelis-Menten compatibility generated from user dataset {namespace.dataset_id}; "
            "the enzyme class and substrate share the listed bond classes."
        ),
    }


def _template_id(namespace: _Namespace, info: _EnzymeClassInfo, substrate: _Substrate) -> str:
    return namespace.id(info.key, substrate.substrate_id, "homogeneous_mm_template")


def _template_mapping(
    info: _EnzymeClassInfo,
    substrate: _Substrate,
    namespace: _Namespace,
    *,
    scientific: bool,
    form: str,
    laws: Sequence[ResponseLaw],
) -> dict[str, Any]:
    template_id = _template_id(namespace, info, substrate)
    states = _state_names(info.key, substrate, form=form)
    simulation = namespace.manifest["simulation"]
    mode = "scientific" if scientific else "exploratory"
    yield_value = float(substrate.product_yield)
    initial_state_mapping: dict[str, Any] = {
        "substrate": {
            "parameter_role": "substrate_initial_concentration",
            "units_from_role": "substrate_initial_concentration",
        },
        "product": {"value": 0.0, "units_from_role": "substrate_initial_concentration"},
    }
    if form == RATE_FORM_KCAT:
        initial_state_mapping["enzyme"] = {
            "parameter_role": "enzyme_initial_concentration",
            "units_from_role": "enzyme_initial_concentration",
        }
    observable_roles = [*states, "degradation_rate", "product_release_rate"]
    process_state_metadata: dict[str, Any] = {
        "config_name": (
            f"User dataset {namespace.dataset_id}: {info.name} on {substrate.name} "
            "homogeneous Michaelis-Menten"
        ),
        "config_mode": mode,
        "config_maturity": mode,
        "process_id": namespace.id(info.key, substrate.substrate_id, "homogeneous_mm"),
        "parameter_set_id": namespace.id(info.key, substrate.substrate_id, "parameters"),
        "product_map_name": f"{substrate.name} to {substrate.product} product map ({namespace.dataset_id})",
        "public_path": True,
    }
    if laws:
        process_state_metadata["process_modifiers"] = [
            {"type": law.law, **{f"{parameter.name}_role": parameter.name for parameter in law.parameters}}
            for law in laws
        ]
    rate_limitation = (
        "Homogeneous Michaelis-Menten in the Vmax form: Vmax is a rate for the simulated system and no enzyme "
        "state is represented, so enzyme loss or dilution cannot be simulated."
        if form == RATE_FORM_VMAX
        else None
    )
    law_limitation = (
        "No temperature or pH response law is bound; values apply at their stated condition only."
        if not laws
        else "Response laws from responses.csv scale the rate: "
        + "; ".join(f"{law.law} ({law.formula})" for law in laws)
        + ". Kinetic constants are reference values at each law's reference condition; Km and the "
        "concentrations are not rescaled, and no other condition acts on the rate."
    )
    return {
        "record_id": template_id,
        "case_template_id": template_id,
        "name": f"{info.name} on {substrate.name} homogeneous Michaelis-Menten template ({namespace.dataset_id})",
        "maturity": USER_DATASET_RECORD_MATURITY,
        "provenance": {
            "source": namespace.source,
            "confidence_level": "user_supplied",
            USER_DATASET_PROVENANCE_KEY: namespace.provenance(
                "user_dataset.yml",
                None,
                substrate_row=substrate.row,
                config_mode_rule=(
                    "scientific only when every parameter record bound to this template is exact and "
                    "scientific-eligible; otherwise exploratory"
                ),
            ),
        },
        "schema_version": CASE_TEMPLATE_SCHEMA_VERSION,
        "process_type": USER_DATASET_PROCESS_TYPE,
        "state_roles": dict(states),
        "initial_state_mapping": initial_state_mapping,
        "product_map": {
            "id": namespace.id(info.key, substrate.substrate_id, "product_map"),
            "product_map_type": "stoichiometric",
            "substrate_state_role": "substrate",
            "product_state_role": "product",
            "stoichiometric_yield": yield_value,
            "notes": (
                f"User-stated yield {_number_text(yield_value)} mol {substrate.product} per mol "
                f"{substrate.substrate_id} (substrates.csv row {substrate.row})."
            ),
        },
        "stoichiometric_yields": {"product": yield_value},
        "time_grid": {
            "start": 0.0,
            "stop": float(simulation["duration"]),
            "points": int(simulation["points"]),
            "units": str(simulation["units"]),
            "notes": f"From the simulation block of user dataset {namespace.dataset_id}.",
        },
        "observable_roles": observable_roles,
        "output_state_roles": dict(states),
        "process_state_metadata": process_state_metadata,
        "limitations": [
            f"Dissolved homogeneous Michaelis-Menten kinetics from user dataset {namespace.dataset_id}.",
            "This is an enzyme-kinetics case, not a whole-fungus growth, secretion or uptake model.",
            law_limitation,
            *([rate_limitation] if rate_limitation is not None else []),
        ],
        "validity_notes": [
            f"Values come from user dataset {namespace.dataset_id} (sha256 {namespace.digest}); "
            "FungMod did not check them against an external source.",
            f"Product formation uses the user-stated yield of {_number_text(yield_value)} mol/mol.",
        ],
        "notes": (
            f"Assembly template generated from user dataset {namespace.dataset_id} for enzyme class "
            f"{info.key} on substrate {substrate.substrate_id}."
        ),
    }


def _parameter_mapping(
    row: _Kinetics,
    *,
    case: _CaseContext,
    role_quantity: str | None = None,
    route: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Map one kinetics row to a parameter record of ``role_quantity`` (the row's own quantity by default).

    ``route`` carries the provenance of a row re-expressed as another role
    (an assay activity used as Vmax); it is added under the dataset namespace.
    """

    strain, info, substrate, condition, namespace = (
        case.strain,
        case.info,
        case.substrate,
        case.condition,
        case.namespace,
    )
    quantity = role_quantity or row.quantity
    exact = row.value is not None
    allowed_use = _allowed_use(row.evidence_type, exact=exact)
    maturity = _EVIDENCE_MATURITY[row.evidence_type]
    confidence = _confidence(row.evidence_type)
    value: dict[str, Any] = {
        "kind": "exact" if exact else "range",
        "units": row.units,
        "source": row.source,
        "confidence_level": confidence,
        "notes": _row_value_notes(row, namespace),
    }
    if exact:
        value["value"] = row.value
    else:
        value["lower"] = row.lower
        value["upper"] = row.upper
    extra: dict[str, Any] = {} if route is None else {"vmax_route": dict(route)}
    provenance: dict[str, Any] = {
        "source": row.source,
        "confidence_level": confidence,
        "measurement_method": row.method or "user estimate without a stated method",
        "validity_range": _validity_range(condition, case.laws),
        USER_DATASET_PROVENANCE_KEY: namespace.provenance(
            "kinetics.csv",
            row.row,
            source=row.source,
            method=row.method or None,
            evidence_type=row.evidence_type,
            sd=row.sd,
            replicates=row.replicates,
            condition_id=condition.condition_id,
            **extra,
        ),
    }
    if row.evidence_type == "estimate":
        provenance["exploratory_prior"] = True
    if route is None:
        name = (
            f"{_QUANTITY_LABEL[quantity]} for {info.name} from {strain.name} on {substrate.name} at "
            f"{condition.condition_id} ({namespace.dataset_id})"
        )
        notes = (
            f"User-supplied {row.quantity} from dataset {namespace.dataset_id} (kinetics.csv row {row.row}); "
            f"evidence type {row.evidence_type}."
        )
    else:
        name = (
            f"{_QUANTITY_LABEL[quantity]} from a saturating {row.quantity} for {info.name} from {strain.name} on "
            f"{substrate.name} at {condition.condition_id} ({namespace.dataset_id})"
        )
        notes = (
            f"User-supplied {row.quantity} from dataset {namespace.dataset_id} (kinetics.csv row {row.row}) used "
            f"as {quantity}: {route['rule']} Evidence type {row.evidence_type}."
        )
    mapping: dict[str, Any] = {
        "record_id": namespace.id(
            strain.strain_id, info.key, substrate.substrate_id, condition.condition_id, quantity
        ),
        "name": name,
        "maturity": maturity,
        "provenance": provenance,
        "notes": notes,
        **_selectors(namespace, strain, info, substrate, condition, quantity),
        "value": value,
        "allowed_use": allowed_use,
    }
    if not exact:
        mapping["range_scope"] = "user_supplied_range"
        mapping["range_interpretation"] = (
            "user_supplied_exploratory_prior_not_literature_curated"
            if row.evidence_type == "estimate"
            else "user_stated_bounds_not_calibrated_uncertainty"
        )
    return mapping


def _allowed_use(evidence_type: str, *, exact: bool) -> str:
    if evidence_type == "estimate":
        return PARAMETER_ALLOWED_USE_EXPLORATORY
    if exact:
        return PARAMETER_ALLOWED_USE_SCIENTIFIC
    return PARAMETER_ALLOWED_USE_EXPLORATORY_SCREENING


def _confidence(evidence_type: str) -> str:
    return "exploratory_assumption" if evidence_type == "estimate" else _EVIDENCE_MATURITY[evidence_type]


def _weakest_evidence(evidence_types: Sequence[str]) -> str:
    """Return the evidence type of lowest maturity in ``USER_DATASET_MATURITY_ORDER``."""

    return min(evidence_types, key=lambda item: USER_DATASET_MATURITY_ORDER.index(_EVIDENCE_MATURITY[item]))


_ASSAY_VMAX_RULE = (
    "an activity measured on the case substrate at saturating substrate concentration, stated per volume of "
    "the simulated system, is the maximum rate Vmax of that system."
)


def _vmax_mapping(case: _CaseContext) -> tuple[dict[str, Any], tuple[str, int | None, str | None]]:
    """Map the Vmax role of a case from its single route, or to a gap when no route is complete."""

    rows = case.case_rows
    explicit = rows.get("vmax")
    if explicit is not None:
        return _parameter_mapping(explicit, case=case), ("kinetics.csv", explicit.row, "quantity")
    assay = rows.get("assay_activity")
    if assay is not None:
        route = {
            "route": "assay_activity",
            "activity_substrate": assay.activity_substrate,
            "activity_saturating": True,
            "rule": _ASSAY_VMAX_RULE[0].upper() + _ASSAY_VMAX_RULE[1:],
        }
        mapping = _parameter_mapping(assay, case=case, role_quantity="vmax", route=route)
        return mapping, ("kinetics.csv", assay.row, "quantity")
    activity, loading = rows.get("specific_activity"), rows.get("enzyme_loading")
    if activity is not None and loading is not None:
        return _derived_vmax_mapping(activity, loading, case=case), ("kinetics.csv", activity.row, "quantity")
    return _gap_mapping("vmax", case=case), ("kinetics.csv", None, "quantity")


def _derived_vmax_mapping(activity: _Kinetics, loading: _Kinetics, *, case: _CaseContext) -> dict[str, Any]:
    """Vmax = specific activity x enzyme loading, converted with pint, as a derived parameter record.

    The maturity is the weaker input's. When one input is a range and the
    other exact, the product is the range scaled by the exact value, which is
    again uniform; two ranges are refused during validation.
    """

    strain, info, substrate, condition, namespace = (
        case.strain,
        case.info,
        case.substrate,
        case.condition,
        case.namespace,
    )
    product_units = Q_(1.0, activity.units) * Q_(1.0, loading.units)
    units = str(product_units.to_reduced_units().units)
    factor = float(product_units.to(units).magnitude)
    evidence_type = _weakest_evidence((activity.evidence_type, loading.evidence_type))
    maturity = _EVIDENCE_MATURITY[evidence_type]
    confidence = _confidence(evidence_type)
    exact = activity.is_exact and loading.is_exact
    source = activity.source if activity.source == loading.source else f"{activity.source}; {loading.source}"
    value: dict[str, Any] = {
        "kind": "exact" if exact else "range",
        "units": units,
        "source": source,
        "confidence_level": confidence,
        "notes": (
            f"Derived in user dataset {namespace.dataset_id} as specific_activity (kinetics.csv row "
            f"{activity.row}) x enzyme_loading (row {loading.row}); ({activity.units}) x ({loading.units}) "
            f"converted to {units} with factor {_number_text(factor)}."
        ),
    }
    if exact:
        assert activity.value is not None and loading.value is not None
        value["value"] = activity.value * loading.value * factor
    else:
        ranged, fixed = (activity, loading) if activity.value is None else (loading, activity)
        assert ranged.lower is not None and ranged.upper is not None and fixed.value is not None
        value["lower"] = ranged.lower * fixed.value * factor
        value["upper"] = ranged.upper * fixed.value * factor
    derivation = {
        "route": "specific_activity",
        "formula": "vmax = specific_activity x enzyme_loading",
        "units_conversion": f"({activity.units}) x ({loading.units}) -> {units}, factor {_number_text(factor)} (pint)",
        "maturity_rule": f"weakest input in the order {_MATURITY_ORDER_TEXT}",
        "inputs": [_input_summary(activity), _input_summary(loading)],
    }
    method = (
        f"Derived: vmax = specific_activity x enzyme_loading from kinetics.csv rows {activity.row} and "
        f"{loading.row} (pint unit conversion)"
    )
    provenance: dict[str, Any] = {
        "source": source,
        "confidence_level": confidence,
        "measurement_method": method,
        "validity_range": _validity_range(condition, case.laws),
        USER_DATASET_PROVENANCE_KEY: namespace.provenance(
            "kinetics.csv",
            None,
            rows=[activity.row, loading.row],
            source=source,
            method=method,
            evidence_type=evidence_type,
            sd=None,
            replicates=None,
            condition_id=condition.condition_id,
            derivation=derivation,
        ),
    }
    if evidence_type == "estimate":
        provenance["exploratory_prior"] = True
    mapping: dict[str, Any] = {
        "record_id": namespace.id(strain.strain_id, info.key, substrate.substrate_id, condition.condition_id, "vmax"),
        "name": (
            f"Vmax from specific activity and enzyme loading for {info.name} from {strain.name} on "
            f"{substrate.name} at {condition.condition_id} ({namespace.dataset_id})"
        ),
        "maturity": maturity,
        "provenance": provenance,
        "notes": (
            f"Derived Vmax in dataset {namespace.dataset_id}: specific_activity (kinetics.csv row {activity.row}) "
            f"x enzyme_loading (row {loading.row}); maturity {maturity} is the weaker input's."
        ),
        **_selectors(namespace, strain, info, substrate, condition, "vmax"),
        "value": value,
        "allowed_use": _allowed_use(evidence_type, exact=exact),
    }
    if not exact:
        mapping["range_scope"] = "user_supplied_range"
        mapping["range_interpretation"] = (
            "user_supplied_exploratory_prior_not_literature_curated"
            if evidence_type == "estimate"
            else "user_stated_bounds_not_calibrated_uncertainty"
        )
    return mapping


def _input_summary(row: _Kinetics) -> dict[str, Any]:
    return {
        "file": "kinetics.csv",
        "row": row.row,
        "quantity": row.quantity,
        "value": row.value,
        "lower": row.lower,
        "upper": row.upper,
        "units": row.units,
        "evidence_type": row.evidence_type,
        "maturity": _EVIDENCE_MATURITY[row.evidence_type],
        "method": row.method or None,
        "source": row.source,
        "sd": row.sd,
        "replicates": row.replicates,
    }


def _gap_mapping(quantity: str, *, case: _CaseContext) -> dict[str, Any]:
    strain, info, substrate, condition, namespace = (
        case.strain,
        case.info,
        case.substrate,
        case.condition,
        case.namespace,
    )
    units = _gap_units(quantity, case.case_rows)
    dimension = _GAP_DIMENSION.get(quantity, "substrate concentration (amount per volume)")
    units_text = units if units is not None else _GAP_UNITS_TEXT.get(quantity, "concentration units")
    request = _measurement_request(quantity, case=case, units_text=units_text)
    notes = f"No kinetics.csv row gives {quantity} for this case in dataset {namespace.dataset_id}."
    if units is None:
        notes = f"{notes} The value requires the dimension {dimension}."
    return {
        "record_id": namespace.id(
            strain.strain_id, info.key, substrate.substrate_id, condition.condition_id, quantity, "gap"
        ),
        "name": f"Missing {_QUANTITY_LABEL[quantity]} for {info.name} from {strain.name} on {substrate.name} at "
        f"{condition.condition_id} ({namespace.dataset_id})",
        "maturity": USER_DATASET_MATURITY_GAP,
        "provenance": {
            "source": f"User dataset {namespace.dataset_id} gap analysis",
            "confidence_level": "missing_from_user_dataset",
            "measurement_request": request,
            USER_DATASET_PROVENANCE_KEY: namespace.provenance(
                "kinetics.csv",
                None,
                evidence_type="gap",
                quantity=quantity,
                condition_id=condition.condition_id,
                required_dimension=dimension,
                **_genome_gap_provenance(case.genome),
            ),
        },
        "notes": notes,
        **_selectors(namespace, strain, info, substrate, condition, quantity),
        "value": {
            "kind": "unknown",
            "units": units,
            "source": f"User dataset {namespace.dataset_id} gap analysis",
            "confidence_level": "missing_from_user_dataset",
            "notes": notes,
        },
        "allowed_use": PARAMETER_ALLOWED_USE_GAP_ANALYSIS_ONLY,
    }


_GAP_DIMENSION = {
    "kcat": "1/time",
    "vmax": "concentration per time (amount per volume per time)",
}
_GAP_UNITS_TEXT = {
    "kcat": "units of 1/time",
    "vmax": "concentration per time",
}


_QUANTITY_LABEL = {
    "km": "km",
    "kcat": "kcat",
    "substrate_initial_concentration": "initial substrate concentration",
    "enzyme_concentration": "enzyme concentration",
    "vmax": "Vmax",
}


def _genome_gap_provenance(genome: _ClassEvidence | None) -> dict[str, Any]:
    if genome is None:
        return {}
    return {"class_evidence": "genome_annotation", "genome_annotation": genome.to_dict()}


def _with_genome_note(request: str, genome: _ClassEvidence | None) -> str:
    """Say in a measurement request that the class rests on a genome annotation, not on a measurement."""

    if genome is None:
        return request
    if isinstance(genome, _ProteomeClassEvidence):
        return f"{request.rstrip('.')}; {genome.request_note()}."
    families = ", ".join(genome.families)
    specificity = (
        ""
        if genome.specificity == DIAGNOSTIC
        else "; family membership is polyspecific, so the activity itself needs confirming"
    )
    return (
        f"{request.rstrip('.')}; the class was inferred from the {genome.tool} annotation "
        f"(families {families}{specificity})."
    )


def _measurement_request(quantity: str, *, case: _CaseContext, units_text: str) -> str:
    return _with_genome_note(_measurement_request_text(quantity, case=case, units_text=units_text), case.genome)


def _measurement_request_text(quantity: str, *, case: _CaseContext, units_text: str) -> str:
    strain, info, substrate, condition = case.strain, case.info, case.substrate, case.condition
    where = _condition_text(condition)
    if quantity in _KCAT_FORM_QUANTITIES and not case.form_started:
        return (
            f"Measure kcat and the enzyme concentration of {info.name} from {strain.name} on {substrate.name} "
            f"at {where}, or Vmax (or a specific activity and enzyme loading)."
        )
    if quantity == "vmax":
        activity, loading = case.case_rows.get("specific_activity"), case.case_rows.get("enzyme_loading")
        if activity is not None and loading is None:
            return (
                f"Measure or specify the enzyme loading (enzyme mass per volume) of {info.name} from {strain.name} "
                f"in the {substrate.name} assay at {where} to derive Vmax from the specific activity in "
                f"kinetics.csv row {activity.row}."
            )
        if loading is not None and activity is None:
            return (
                f"Measure the specific activity (amount per time per enzyme mass) of {info.name} from "
                f"{strain.name} on {substrate.name} at {where} to derive Vmax with the enzyme loading in "
                f"kinetics.csv row {loading.row}."
            )
        return (
            f"Measure Vmax of {info.name} from {strain.name} on {substrate.name} at {where} ({units_text}), "
            "or a specific activity and enzyme loading."
        )
    if quantity in {"km", "kcat"}:
        return f"Measure {quantity} of {info.name} from {strain.name} on {substrate.name} at {where} ({units_text})."
    if quantity == "substrate_initial_concentration":
        return (
            f"Specify the initial {substrate.name} concentration for {info.name} from {strain.name} "
            f"at {where} ({units_text})."
        )
    return (
        f"Measure or specify the {info.name} concentration from {strain.name} in the {substrate.name} assay "
        f"at {where} ({units_text})."
    )


def _response_mapping(
    response: _Response,
    *,
    law: ResponseLaw,
    law_rows: Mapping[str, _Response],
    strain: _Strain,
    info: _EnzymeClassInfo,
    substrate: _Substrate,
    namespace: _Namespace,
    reference_conditions: Sequence[str],
) -> dict[str, Any]:
    """Map one responses.csv row to an exact, condition-independent law parameter record.

    Every parameter of one law takes the weakest maturity among the law's rows,
    so one estimated parameter makes the whole law an exploratory prior.
    Temperatures are stored in kelvin with the original value in the notes.
    """

    spec = law.parameter(response.parameter)
    evidence_type = _weakest_evidence([row.evidence_type for row in law_rows.values()])
    maturity = _EVIDENCE_MATURITY[evidence_type]
    confidence = _confidence(evidence_type)
    if spec.reference_units == _TEMPERATURE_REFERENCE_UNITS:
        stored_value = float(Q_(response.value, response.units).to(_TEMPERATURE_REFERENCE_UNITS).magnitude)
        stored_units = _TEMPERATURE_REFERENCE_UNITS
        conversion = (
            f" Original value {_number_text(response.value)} {response.units} converted to kelvin."
            if response.units != _TEMPERATURE_REFERENCE_UNITS
            else ""
        )
    else:
        stored_value, stored_units, conversion = response.value, response.units, ""
    rows_text = _rows_text(list(law_rows.values()))
    notes = (
        f"User-supplied {response.parameter} of {law.law} from dataset {namespace.dataset_id} (responses.csv row "
        f"{response.row}); evidence type {response.evidence_type}; law maturity {maturity} (weakest of {rows_text}).{conversion}"
    )
    extra: dict[str, Any] = {}
    if response.parameter == law.reference_parameter:
        extra["reference_condition"] = {
            "rule": (
                "kinetic constants of this strain, enzyme class and substrate must be stated at this reference "
                "value, exactly or within the row's reference_tolerance, or be declared reference values"
            ),
            "kinetics_conditions": list(reference_conditions),
            "reference_tolerance": response.reference_tolerance,
            "tolerance_units": response.units if response.reference_tolerance is not None else None,
            "kinetics_at_reference_declared": response.kinetics_at_reference,
        }
    provenance: dict[str, Any] = {
        "source": response.source,
        "confidence_level": confidence,
        "measurement_method": response.method or "user estimate without a stated method",
        "validity_range": (
            f"{law.label} for {info.name} from {strain.name} on {substrate.name}: {law.formula}; it applies at "
            "every condition of the case and rescales the reference kinetic constants."
        ),
        USER_DATASET_PROVENANCE_KEY: namespace.provenance(
            "responses.csv",
            response.row,
            source=response.source,
            method=response.method or None,
            evidence_type=response.evidence_type,
            law=law.law,
            parameter=response.parameter,
            original_value=response.value,
            original_units=response.units,
            law_rows=sorted(row.row for row in law_rows.values()),
            law_maturity_rule=f"weakest row of the law in the order {_MATURITY_ORDER_TEXT}",
            **extra,
        ),
    }
    if evidence_type == "estimate":
        provenance["exploratory_prior"] = True
    return {
        "record_id": namespace.id(strain.strain_id, info.key, substrate.substrate_id, law.law, response.parameter),
        "name": (
            f"{spec.label} of the {law.label} for {info.name} from {strain.name} on {substrate.name} "
            f"({namespace.dataset_id})"
        ),
        "maturity": maturity,
        "provenance": provenance,
        "notes": notes,
        **_law_selectors(namespace, law, spec, strain, info, substrate),
        "value": {
            "kind": "exact",
            "value": stored_value,
            "units": stored_units,
            "source": response.source,
            "confidence_level": confidence,
            "notes": notes,
        },
        "allowed_use": _allowed_use(evidence_type, exact=True),
    }


def _response_gap_mapping(
    law: ResponseLaw,
    parameter: ResponseLawParameter,
    *,
    strain: _Strain,
    info: _EnzymeClassInfo,
    substrate: _Substrate,
    namespace: _Namespace,
    genome: _ClassEvidence | None = None,
) -> dict[str, Any]:
    request = _with_genome_note(
        f"Measure the {parameter.label} of the {law.label} for {info.name} from {strain.name} on {substrate.name} "
        f"({parameter.dimension_text}); responses.csv binds this law to {info.name} on {substrate.name} for "
        "another strain.",
        genome,
    )
    notes = (
        f"No responses.csv row gives {parameter.name} of {law.law} for this strain in dataset "
        f"{namespace.dataset_id}; the value requires {parameter.dimension_text}."
    )
    return {
        "record_id": namespace.id(
            strain.strain_id, info.key, substrate.substrate_id, law.law, parameter.name, "gap"
        ),
        "name": (
            f"Missing {parameter.label} of the {law.label} for {info.name} from {strain.name} on "
            f"{substrate.name} ({namespace.dataset_id})"
        ),
        "maturity": USER_DATASET_MATURITY_GAP,
        "provenance": {
            "source": f"User dataset {namespace.dataset_id} gap analysis",
            "confidence_level": "missing_from_user_dataset",
            "measurement_request": request,
            USER_DATASET_PROVENANCE_KEY: namespace.provenance(
                "responses.csv",
                None,
                evidence_type="gap",
                law=law.law,
                parameter=parameter.name,
                required_dimension=parameter.dimension_text,
                **_genome_gap_provenance(genome),
            ),
        },
        "notes": notes,
        **_law_selectors(namespace, law, parameter, strain, info, substrate),
        "value": {
            "kind": "unknown",
            "units": None,
            "source": f"User dataset {namespace.dataset_id} gap analysis",
            "confidence_level": "missing_from_user_dataset",
            "notes": notes,
        },
        "allowed_use": PARAMETER_ALLOWED_USE_GAP_ANALYSIS_ONLY,
    }


def _law_selectors(
    namespace: _Namespace,
    law: ResponseLaw,
    parameter: ResponseLawParameter,
    strain: _Strain,
    info: _EnzymeClassInfo,
    substrate: _Substrate,
) -> dict[str, Any]:
    """Selectors of a law parameter: like kinetics, but valid at every environment of the case."""

    return {
        "parameter_symbol": _law_symbol(namespace, law, parameter, info.key, substrate.substrate_id),
        "process_type": USER_DATASET_PROCESS_TYPE,
        "enzyme_class": namespace.id(info.key),
        "substrate_class": substrate.substrate_class,
        "fungus_id": namespace.id(strain.strain_id),
        "substrate_id": substrate.registry_id or namespace.id(substrate.substrate_id),
        "environment_id": None,
    }


def _law_symbol(
    namespace: _Namespace,
    law: ResponseLaw,
    parameter: ResponseLawParameter,
    class_key: str,
    substrate_id: str,
) -> str:
    return namespace.id(law.law, parameter.name, class_key, substrate_id)


def _selectors(
    namespace: _Namespace,
    strain: _Strain,
    info: _EnzymeClassInfo,
    substrate: _Substrate,
    condition: _Condition,
    quantity: str,
) -> dict[str, Any]:
    return {
        "parameter_symbol": _parameter_symbol(namespace, quantity, info.key, substrate.substrate_id),
        "process_type": USER_DATASET_PROCESS_TYPE,
        "enzyme_class": namespace.id(info.key),
        "substrate_class": substrate.substrate_class,
        "fungus_id": namespace.id(strain.strain_id),
        "substrate_id": substrate.registry_id or namespace.id(substrate.substrate_id),
        "environment_id": namespace.id(condition.condition_id),
    }


def _parameter_symbol(namespace: _Namespace, quantity: str, class_key: str, substrate_id: str) -> str:
    return namespace.id(quantity, class_key, substrate_id)


def _gap_units(quantity: str, case_rows: Mapping[str, _Kinetics]) -> str | None:
    if quantity in _GAP_DIMENSION:
        return None
    for other in _CONCENTRATION_QUANTITIES:
        row = case_rows.get(other)
        if row is not None:
            return row.units
    return None


def _row_value_notes(row: _Kinetics, namespace: _Namespace) -> str:
    parts = [f"User dataset {namespace.dataset_id}, kinetics.csv row {row.row}; evidence type {row.evidence_type}."]
    if row.sd is not None:
        parts.append(f"Reported standard deviation {_number_text(row.sd)} {row.units} (kept as provenance, not sampled).")
    if row.replicates is not None:
        parts.append(f"Replicates: {row.replicates}.")
    return " ".join(parts)


def _validity_range(condition: _Condition, laws: Sequence[str] = ()) -> str:
    if not laws:
        return (
            f"Condition {condition.condition_id}: {_condition_text(condition)}; "
            "no temperature or pH response law is attached."
        )
    return (
        f"Condition {condition.condition_id}: {_condition_text(condition)}; the response law(s) "
        f"{', '.join(laws)} from responses.csv rescale the rate away from their reference condition."
    )


def _condition_text(condition: _Condition) -> str:
    temperature = (
        "unknown temperature"
        if condition.temperature_kelvin is None
        else f"{condition.temperature_text} {condition.temperature_units}"
    )
    ph = "unknown pH" if condition.ph is None else f"pH {condition.ph_text}"
    return f"{temperature}, {ph}"


def _state_names(class_key: str, substrate: _Substrate, *, form: str) -> dict[str, str]:
    substrate_key = substrate.registry_id or substrate.substrate_id
    names = {
        "substrate": f"{substrate_key}_concentration",
        "product": f"{substrate.product}_concentration",
    }
    if form == RATE_FORM_KCAT:
        names["enzyme"] = f"{class_key}_concentration"
    return names


def _shared_bonds(info: _EnzymeClassInfo, substrate: _Substrate) -> tuple[str, ...] | None:
    if substrate.substrate_class not in info.compatible_substrate_classes:
        return None
    shared = tuple(sorted(set(substrate.bond_classes).intersection(info.target_bond_classes)))
    return shared or None


_UNMODELLABLE_REASON = (
    "no enzyme-class record in the base registry; FungMod does not create one from a genome annotation, so no "
    "case, gap or measurement request is generated for this class"
)
_UNMAPPED_REASON = "the curated CAZy family map assigns no enzyme class to this family"
_PROTEOME_UNMODELLABLE_REASON = (
    "no enzyme-class record in the base registry; FungMod does not create one from a proteome annotation, so no "
    "case, gap or measurement request is generated for this class"
)


def _genome_report(parsed: _Parsed, *, dataset_id: str) -> dict[str, tuple[Mapping[str, Any], ...]]:
    """The dataset-level genome lists: annotations read, classes resolved, classes without a record, unmapped families."""

    annotations: list[Mapping[str, Any]] = []
    resolved: list[Mapping[str, Any]] = []
    unmodellable: list[Mapping[str, Any]] = []
    unmapped: list[Mapping[str, Any]] = []
    declared = {(item.strain_id, item.class_key): item for item in parsed.strain_classes}
    for genome in parsed.genomes:
        if isinstance(genome, _ProteomeAnnotation):
            annotations.append(_proteome_annotation_entry(genome))
            entries = _proteome_class_entries(genome, declared, dataset_id=dataset_id)
            resolved.extend(entries["resolved"])
            unmodellable.extend(entries["unmodellable"])
            unmapped.extend(entries["unmapped"])
            continue
        annotations.append(
            {
                "strain_id": genome.strain_id,
                "file": GENOME_TABLE,
                "row": genome.row,
                "annotation_file": genome.annotation_file,
                "annotation_sha256": genome.annotation_sha256,
                "annotation_tool": genome.tool,
                "annotation_tool_version": genome.tool_version,
                "source": genome.source,
                "tool_columns": list(genome.overview.tool_columns),
                "min_tools_agreeing": genome.min_tools_agreeing,
                "consensus_rule": genome.consensus_rule,
                "gene_rows": len(genome.overview.genes),
                "family_gene_counts": {family: len(genes) for family, genes in genome.family_genes.items()},
                "family_map": {
                    "file": default_family_map_path().name,
                    "sha256": genome.family_map_sha256,
                    "sources": list(genome.family_map_sources),
                },
                "claim_boundary": _GENOME_CLAIM_BOUNDARY,
            }
        )
        for capability in genome.capabilities:
            entry: dict[str, Any] = {
                "strain_id": genome.strain_id,
                "enzyme_class": capability.enzyme_class,
                "families": list(capability.families),
                "gene_count": len(genome.genes_for(capability.families)),
                "specificity": capability.specificity,
                "genomes_row": genome.row,
            }
            if not capability.modellable:
                unmodellable.append({**entry, "reason": _UNMODELLABLE_REASON})
                continue
            item = declared[(genome.strain_id, capability.enzyme_class)]
            assert item.genome is not None
            resolved.append(
                {
                    **entry,
                    "record_id": "__".join((dataset_id, capability.enzyme_class)),
                    "declared_by": item.file,
                    "enzymes_row": None if item.genome_only else item.row,
                    "evidence": item.genome.evidence_text,
                    "source": genome.source,
                }
            )
        for family in genome.unmapped_families:
            unmapped.append(
                {
                    "strain_id": genome.strain_id,
                    "family": family,
                    "gene_count": len(genome.family_genes.get(family, ())),
                    "genomes_row": genome.row,
                    "reason": _UNMAPPED_REASON,
                }
            )
    return {
        "genome_annotations": tuple(annotations),
        "genome_resolved_classes": tuple(resolved),
        "unmodellable_enzyme_classes": tuple(unmodellable),
        "unmapped_families": tuple(unmapped),
    }


def _proteome_annotation_entry(genome: _ProteomeAnnotation) -> dict[str, Any]:
    """The ``genome_annotations`` entry of a UniProt export, with its unresolved and partial EC numbers."""

    proteome, resolution = genome.proteome, genome.resolution.to_dict()
    return {
        "strain_id": genome.strain_id,
        "file": GENOME_TABLE,
        "row": genome.row,
        "source_type": UNIPROT_SOURCE_TYPE,
        "annotation_file": genome.annotation_file,
        "annotation_sha256": genome.annotation_sha256,
        "annotation_tool": genome.tool,
        "annotation_tool_version": genome.tool_version,
        "source": genome.source,
        "proteome_id": genome.proteome_id,
        "organism": proteome.organism or None,
        "organism_id": proteome.organism_id or None,
        "read_columns": list(proteome.read_columns),
        "ignored_columns": list(proteome.ignored_columns),
        "entry_rows": len(proteome.entries),
        "review_counts": proteome.review_counts(),
        "protein_counts": resolution["protein_counts"],
        "family_accession_counts": {family: len(items) for family, items in proteome.family_accessions().items()},
        "ec_accession_counts": {ec: len(items) for ec, items in proteome.ec_accessions().items()},
        "unresolved_ec_numbers": resolution["unresolved_ec_numbers"],
        "partial_ec_numbers": resolution["partial_ec_numbers"],
        "ec_cazy_disagreements": resolution["ec_cazy_disagreements"],
        "ec_comparable_classes": resolution["ec_comparable_classes"],
        "comparison_rule": resolution["comparison_rule"],
        "family_map": {
            "file": default_family_map_path().name,
            "sha256": genome.family_map_sha256,
            "sources": list(genome.family_map_sources),
        },
        "claim_boundary": UNIPROT_CLAIM_BOUNDARY,
    }


def _proteome_class_entries(
    genome: _ProteomeAnnotation,
    declared: Mapping[tuple[str, str], _StrainClass],
    *,
    dataset_id: str,
) -> dict[str, list[Mapping[str, Any]]]:
    """The resolved, unmodellable and unmapped entries of a UniProt export, each with its accessions."""

    entries: dict[str, list[Mapping[str, Any]]] = {"resolved": [], "unmodellable": [], "unmapped": []}
    for support in genome.capabilities:
        entry: dict[str, Any] = {
            "strain_id": genome.strain_id,
            "enzyme_class": support.enzyme_class,
            "source_type": UNIPROT_SOURCE_TYPE,
            "families": list(support.families),
            "ec_numbers": list(support.ec_numbers),
            "accessions": list(support.accessions),
            "accession_count": len(support.accessions),
            "accessions_by_basis": {basis: list(items) for basis, items in support.accessions_by_basis.items()},
            "reviewed_accessions": list(support.reviewed_accessions),
            "specificity": support.specificity,
            "genomes_row": genome.row,
        }
        if not support.modellable:
            entries["unmodellable"].append({**entry, "reason": _PROTEOME_UNMODELLABLE_REASON})
            continue
        item = declared[(genome.strain_id, support.enzyme_class)]
        assert item.genome is not None
        entries["resolved"].append(
            {
                **entry,
                "record_id": "__".join((dataset_id, support.enzyme_class)),
                "declared_by": item.file,
                "enzymes_row": None if item.genome_only else item.row,
                "evidence": item.genome.evidence_text,
                "source": genome.source,
            }
        )
    for family, accessions in genome.resolution.unmapped_families.items():
        entries["unmapped"].append(
            {
                "strain_id": genome.strain_id,
                "family": family,
                "source_type": UNIPROT_SOURCE_TYPE,
                "accessions": list(accessions),
                "accession_count": len(accessions),
                "genomes_row": genome.row,
                "reason": _UNMAPPED_REASON,
            }
        )
    return entries


# ---------------------------------------------------------------------------
# Overlay checks


def _overlay_issues(dataset: UserDataset, base: FungModRegistry) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    stores: Mapping[str, Mapping[str, Any]] = {
        "fungi": base.fungi,
        "enzyme_classes": base.enzyme_classes,
        "substrates": base.substrates,
        "environments": base.environments,
        "process_compatibility": base.process_compatibility,
        "case_templates": base.case_templates,
        "parameter_records": base.parameters,
    }
    for (record_type, record_id), snapshot in dataset._base_references.items():
        current = stores[record_type].get(record_id)
        if current is None or current.to_dict() != dict(snapshot):
            issues.append(
                _issue(
                    USER_DATASET_MANIFEST,
                    None,
                    None,
                    f"The dataset references registry {record_type} record {record_id!r}, which is missing or "
                    "different in this base registry; reload the dataset against it.",
                )
            )
    resolver = RegistryResolver(base)
    for record_type in _RECORD_TYPES:
        terms: dict[str, str] = {}
        for record in dataset._record_objects.get(record_type, ()):
            file, row, column = dataset._origins.get((record_type, record.record_id), (USER_DATASET_MANIFEST, None, None))
            if record.record_id in stores[record_type]:
                issues.append(
                    _issue(file, row, column, f"Generated {record_type} id {record.record_id!r} already exists in the registry.")
                )
            if record_type not in _IDENTITY_RESOLVERS:
                continue
            for term in _identity_terms(record):
                term_column = "name" if term == record.name else column
                normalized = " ".join(term.casefold().split())
                other = terms.get(normalized)
                if other is not None and other != record.record_id:
                    issues.append(
                        _issue(
                            file,
                            row,
                            term_column,
                            f"{term!r} names both {other!r} and {record.record_id!r} in this dataset; names and "
                            "aliases must be unique.",
                        )
                    )
                terms[normalized] = record.record_id
                clash = _registry_clash(resolver, record_type, term)
                if clash:
                    issues.append(
                        _issue(
                            file,
                            row,
                            term_column,
                            f"{term!r} collides with registry {record_type} {clash}; use an identifier, name and "
                            "aliases that the registry does not already use.",
                        )
                    )
    return issues


def _identity_terms(record: RegistryRecord) -> tuple[str, ...]:
    values = (record.record_id, record.name, record.display_name, *record.aliases)
    return tuple(dict.fromkeys(value.strip() for value in values if value and value.strip()))


def _terms_are_free(
    named: Sequence[tuple[str, str | None]],
    record_type: str,
    resolver: RegistryResolver,
    seen: dict[str, int],
    *,
    file: str,
    line: int,
    context: _Context,
) -> bool:
    """Refuse identifiers, names and aliases already used by the registry or by an earlier row."""

    free = True
    for column, term in named:
        if term is None:
            continue
        clash = _registry_clash(resolver, record_type, term)
        if clash:
            context.add(
                file,
                line,
                column,
                f"{term!r} collides with registry {record_type} {clash}; choose an identifier, name and aliases "
                "the registry does not already use.",
            )
            free = False
        normalized = " ".join(term.casefold().split())
        earlier = seen.get(normalized)
        if earlier is not None and earlier != line:
            context.add(file, line, column, f"{term!r} is already used in row {earlier}; names and aliases must be unique.")
            free = False
        seen.setdefault(normalized, line)
    return free


def _registry_clash(resolver: RegistryResolver, record_type: str, term: str) -> str:
    resolve = getattr(resolver, _IDENTITY_RESOLVERS[record_type])
    try:
        resolved = resolve(term)
    except AmbiguousResolutionError as exc:
        return ", ".join(repr(candidate.record_id) for candidate in exc.candidates)
    except ResolutionError:
        return ""
    return repr(resolved.record_id)


# ---------------------------------------------------------------------------
# Cell helpers


def _issue(file: str, row: int | None, column: str | None, message: str) -> dict[str, Any]:
    return {"file": file, "row": row, "column": column, "message": message}


def _issue_text(issue: Mapping[str, Any]) -> str:
    location = str(issue.get("file", ""))
    if issue.get("row") is not None:
        location = f"{location} row {issue['row']}"
    if issue.get("column"):
        location = f"{location} column {issue['column']}"
    return f"{location}: {issue.get('message', '')}"


def _required_text(row: Mapping[str, str], column: str, *, file: str, line: int, context: _Context) -> str | None:
    value = row.get(column, "")
    if not value:
        context.add(file, line, column, f"{column} is required.")
        return None
    return value


def _required_identifier(row: Mapping[str, str], column: str, *, file: str, line: int, context: _Context) -> str | None:
    value = _required_text(row, column, file=file, line=line, context=context)
    if value is not None and not _IDENTIFIER_PATTERN.fullmatch(value):
        context.add(
            file,
            line,
            column,
            f"{column} {value!r} must use letters and digits joined by single underscores.",
        )
        return None
    return value


def _required_number(row: Mapping[str, str], column: str, *, file: str, line: int, context: _Context) -> float | None:
    value = _required_text(row, column, file=file, line=line, context=context)
    if value is None:
        return None
    number = _number(value)
    if number is None:
        context.add(file, line, column, f"{column} must be a finite number.")
    return number


def _reference(
    row: Mapping[str, str],
    column: str,
    declared: Mapping[str, Any],
    table: str,
    *,
    file: str,
    line: int,
    context: _Context,
) -> str | None:
    value = _required_text(row, column, file=file, line=line, context=context)
    if value is not None and value not in declared:
        context.add(file, line, column, f"{column} {value!r} is not declared in {table}.")
        return None
    return value


def _optional_nonnegative(
    row: Mapping[str, str], column: str, *, file: str, line: int, context: _Context
) -> float | None | bool:
    text = row.get(column, "")
    if not text:
        return None
    number = _number(text)
    if number is None or number < 0.0:
        context.add(file, line, column, f"{column} must be a finite nonnegative number when given.")
        return False
    return number


def _optional_positive_int(
    row: Mapping[str, str], column: str, *, file: str, line: int, context: _Context
) -> int | None | bool:
    text = row.get(column, "")
    if not text:
        return None
    try:
        number = int(text)
    except ValueError:
        number = 0
    if number < 1:
        context.add(file, line, column, f"{column} must be a positive integer when given.")
        return False
    return number


def _class_tokens(
    row: Mapping[str, str], column: str, *, file: str, line: int, context: _Context
) -> tuple[str, ...] | None:
    text = _required_text(row, column, file=file, line=line, context=context)
    if text is None:
        return None
    tokens = _semicolon_list(text)
    bad = [token for token in tokens if not _CLASS_TOKEN_PATTERN.fullmatch(token)]
    if not tokens or bad:
        context.add(file, line, column, f"{column} must be semicolon-separated lowercase snake_case classes.")
        return None
    return tokens


def _semicolon_list(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item.strip() for item in text.split(";") if item.strip()))


def _number(text: str) -> float | None:
    try:
        number = float(text)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _number_text(value: float) -> str:
    return f"{value:g}"


def _unit_parse_error(units: str) -> str | None:
    try:
        Q_(1.0, units)
    except Exception as exc:  # pint raises several unrelated exception types for bad strings
        return str(exc) or type(exc).__name__
    return None


def _unit_dimension_error(units: str, reference: str) -> str | None:
    error = _unit_parse_error(units)
    if error is not None:
        return error
    if not units_are_compatible(units, reference):
        return f"{units!r} is not compatible with {reference!r}"
    return None


def _concentration_kind(units: str) -> str | None:
    if _unit_parse_error(units) is not None:
        return None
    if units_are_compatible(units, _MOLAR_REFERENCE_UNITS):
        return "molar"
    if units_are_compatible(units, _MASS_REFERENCE_UNITS):
        return "mass"
    return None


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _objects_of(
    objects: Mapping[str, tuple[RegistryRecord, ...]],
    name: str,
    kind: type[_RecordT],
) -> tuple[_RecordT, ...]:
    return tuple(record for record in objects.get(name, ()) if isinstance(record, kind))


__all__ = [
    "EVIDENCE_TYPES",
    "GENOME_ANNOTATION_TOOLS",
    "UNIPROT_SOURCE_TYPE",
    "GENOME_TABLE",
    "KINETIC_QUANTITIES",
    "RATE_FORM_KCAT",
    "RATE_FORM_VMAX",
    "RESPONSE_EVIDENCE_TYPES",
    "RESPONSE_LAWS",
    "ResponseLaw",
    "ResponseLawParameter",
    "USER_DATASET_MANIFEST",
    "USER_DATASET_MATURITY_DESIGN",
    "USER_DATASET_MATURITY_ESTIMATE",
    "USER_DATASET_MATURITY_GAP",
    "USER_DATASET_MATURITY_LITERATURE",
    "USER_DATASET_MATURITY_MEASURED",
    "USER_DATASET_MATURITY_ORDER",
    "USER_DATASET_PARAMETER_MATURITIES",
    "USER_DATASET_RECORD_MATURITY",
    "USER_DATASET_SCHEMA_VERSION",
    "UserDataError",
    "UserDataset",
    "VMAX_ROUTES",
    "load_user_dataset",
]
