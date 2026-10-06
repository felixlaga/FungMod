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

Scope of this increment: dissolved substrates, enzyme-explicit homogeneous
Michaelis-Menten kinetics (``km``, ``kcat``, initial substrate and enzyme
concentrations), stoichiometric products with an explicit mol/mol yield, and
conditions stated as temperature and pH without any response law.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any, TypeVar, cast

import yaml

from fungal_model.core.units import Q_, units_are_compatible
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
from fungal_model.screening.case_builder import HOMOGENEOUS_MM_PARAMETER_ROLES

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
_EVIDENCE_MATURITY = {
    "measured": USER_DATASET_MATURITY_MEASURED,
    "literature": USER_DATASET_MATURITY_LITERATURE,
    "design": USER_DATASET_MATURITY_DESIGN,
    "estimate": USER_DATASET_MATURITY_ESTIMATE,
}
_EVIDENCE_REQUIRES_METHOD = frozenset({"measured", "literature", "design"})

KINETIC_QUANTITIES = ("km", "kcat", "substrate_initial_concentration", "enzyme_concentration")
_QUANTITY_ROLE = {
    "km": "km",
    "kcat": "kcat",
    "substrate_initial_concentration": "substrate_initial_concentration",
    "enzyme_concentration": "enzyme_initial_concentration",
}
_UNSUPPORTED_RATE_QUANTITIES = frozenset({"vmax", "enzyme_activity"})
_CONCENTRATION_QUANTITIES = ("substrate_initial_concentration", "km", "enzyme_concentration")
_YIELD_BASIS = "mol/mol"
_UNKNOWN_CELL = "unknown"

_REQUIRED_TABLES = ("strains.csv", "enzymes.csv", "substrates.csv", "conditions.csv", "kinetics.csv")
_OPTIONAL_TABLES = ("enzyme_classes.csv",)
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
        ("value", "lower", "upper", "method", "sd", "replicates"),
    ),
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
    ``digest`` is the SHA-256 over the manifest and table bytes in file-name
    order; every generated parameter record cites it.
    """

    dataset_id: str
    digest: str
    records: Mapping[str, tuple[Mapping[str, Any], ...]]
    source_directory: str = ""
    manifest: Mapping[str, Any] = field(default_factory=dict)
    file_digests: Mapping[str, str] = field(default_factory=dict)
    base_registry_id: str = ""
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
    digest = _dataset_digest(raw_files)
    manifest = _parse_manifest(raw_files.get(USER_DATASET_MANIFEST), issues)
    tables = {name: _parse_table(name, raw_files[name], issues) for name in _TABLE_COLUMNS if name in raw_files}
    context = _Context(base=base, issues=issues)
    parsed = _parse_rows(tables, context)
    if parsed is not None:
        _cross_validate(parsed, context)
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
    dataset = UserDataset(
        dataset_id=dataset_id,
        digest=digest,
        records=MappingProxyType({name: tuple(generated.mappings[name]) for name in _RECORD_TYPES}),
        source_directory=str(directory.resolve()),
        manifest=MappingProxyType(dict(manifest)),
        file_digests=MappingProxyType({name: hashlib.sha256(data).hexdigest() for name, data in sorted(raw_files.items())}),
        base_registry_id=base.registry_id,
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
class _StrainClass:
    row: int
    strain_id: str
    class_key: str
    evidence: str
    source: str


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

    @property
    def case_key(self) -> tuple[str, str, str, str]:
        return (self.strain_id, self.class_key, self.substrate_id, self.condition_id)


@dataclass
class _Parsed:
    strains: dict[str, _Strain]
    classes: dict[str, _EnzymeClassInfo]
    strain_classes: list[_StrainClass]
    substrates: dict[str, _Substrate]
    conditions: dict[str, _Condition]
    kinetics: list[_Kinetics]


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
                    f"{', '.join(sorted(known))}. Response laws, time-course responses and other "
                    "tables are not imported yet.",
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


def _parse_table(name: str, raw: bytes, issues: list[dict[str, Any]]) -> _Table | None:
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
    if name in _TABLES_WITH_ROWS_REQUIRED and not rows:
        issues.append(_issue(name, None, None, "Table needs at least one data row."))
    return _Table(name=name, rows=tuple(rows))


def _parse_rows(tables: Mapping[str, _Table | None], context: _Context) -> _Parsed | None:
    required_ok = all(tables.get(name) is not None for name in _REQUIRED_TABLES)
    if not required_ok:
        return None
    resolver = RegistryResolver(context.base)
    strains = _parse_strains(_table(tables, "strains.csv"), resolver, context)
    user_classes = _parse_user_classes(tables.get("enzyme_classes.csv"), resolver, context)
    classes: dict[str, _EnzymeClassInfo] = dict(user_classes)
    strain_classes = _parse_strain_classes(_table(tables, "enzymes.csv"), strains, classes, resolver, context)
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
    return _Parsed(
        strains=strains,
        classes=classes,
        strain_classes=strain_classes,
        substrates=substrates,
        conditions=conditions,
        kinetics=kinetics,
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
    record = context.base.get_enzyme_class(resolved.record_id)
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
            if quantity in _UNSUPPORTED_RATE_QUANTITIES:
                context.add(
                    file,
                    line,
                    "quantity",
                    f"quantity {quantity!r} is not supported yet: this increment needs kcat and an enzyme "
                    "concentration; vmax and enzyme activity units are not supported and are never converted.",
                )
            else:
                context.add(
                    file, line, "quantity", f"quantity {quantity!r} is not one of {', '.join(KINETIC_QUANTITIES)}."
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
        if evidence_type in _EVIDENCE_REQUIRES_METHOD and not method:
            context.add(file, line, "method", f"method is required for evidence_type {evidence_type!r}.")
            evidence_type = None
        source = _required_text(row, "source", file=file, line=line, context=context)
        sd = _optional_nonnegative(row, "sd", file=file, line=line, context=context)
        replicates = _optional_positive_int(row, "replicates", file=file, line=line, context=context)
        if (
            quantity is None
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
            )
        )
    return rows


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
    if _concentration_kind(units) is None:
        return (
            f"{quantity} units {units!r} must be a substrate concentration (amount or mass per volume, "
            "for example mM, uM or g/L)."
        )
    return None


def _cross_validate(parsed: _Parsed, context: _Context) -> None:
    declared_strains = {item.strain_id for item in parsed.strain_classes}
    for strain in parsed.strains.values():
        if strain.strain_id not in declared_strains:
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
    _validate_pairs(parsed, context)


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
            states = _state_names(class_key, substrate)
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
            else ("enzymes.csv", _first_class_row(parsed, class_key), "enzyme_class"),
        )
    for strain in parsed.strains.values():
        declared = [item for item in parsed.strain_classes if item.strain_id == strain.strain_id]
        _emit(
            generated,
            context,
            "fungi",
            _fungus_mapping(strain, declared, parsed.classes, namespace),
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
        pair_records: list[ParameterRecord] = []
        for item in parsed.strain_classes:
            if item.class_key != class_key:
                continue
            strain = parsed.strains[item.strain_id]
            for condition in parsed.conditions.values():
                case_rows = rows_by_case.get((strain.strain_id, class_key, substrate.substrate_id, condition.condition_id), {})
                for quantity in KINETIC_QUANTITIES:
                    row = case_rows.get(quantity)
                    if row is not None:
                        mapping = _parameter_mapping(
                            row,
                            strain=strain,
                            info=parsed.classes[class_key],
                            substrate=substrate,
                            condition=condition,
                            namespace=namespace,
                        )
                        origin: tuple[str, int | None, str | None] = ("kinetics.csv", row.row, "quantity")
                    else:
                        mapping = _gap_mapping(
                            quantity,
                            case_rows=case_rows,
                            strain=strain,
                            info=parsed.classes[class_key],
                            substrate=substrate,
                            condition=condition,
                            namespace=namespace,
                        )
                        origin = ("kinetics.csv", None, "quantity")
                    record = _emit(generated, context, "parameter_records", mapping, origin=origin)
                    if isinstance(record, ParameterRecord):
                        pair_records.append(record)
        scientific = bool(pair_records) and all(
            record.value.is_exact and parameter_record_is_mode_eligible(record, mode="scientific")
            for record in pair_records
        )
        info = parsed.classes[class_key]
        _emit(
            generated,
            context,
            "case_templates",
            _template_mapping(info, substrate, namespace, scientific=scientific),
            origin=("substrates.csv", substrate.row, "substrate_id"),
        )
        _emit(
            generated,
            context,
            "process_compatibility",
            _compatibility_mapping(info, substrate, namespace),
            origin=("substrates.csv", substrate.row, "substrate_id"),
        )
    return generated


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


def _first_class_row(parsed: _Parsed, class_key: str) -> int | None:
    return next((item.row for item in parsed.strain_classes if item.class_key == class_key), None)


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
) -> dict[str, Any]:
    aliases = list(dict.fromkeys((strain.strain_id, *strain.aliases)))
    mapping: dict[str, Any] = {
        "record_id": namespace.id(strain.strain_id),
        "name": strain.name,
        "aliases": aliases,
        "maturity": USER_DATASET_RECORD_MATURITY,
        "provenance": {
            "source": namespace.source,
            "confidence_level": "user_supplied",
            "enzyme_class_evidence": {
                namespace.id(item.class_key): {
                    "enzyme_class": item.class_key,
                    "class_origin": classes[item.class_key].origin,
                    "evidence": item.evidence,
                    "source": item.source,
                    "file": "enzymes.csv",
                    "row": item.row,
                }
                for item in declared
            },
            USER_DATASET_PROVENANCE_KEY: namespace.provenance("strains.csv", strain.row),
        },
        "enzyme_classes": [namespace.id(item.class_key) for item in declared],
        "assimilable_products": [],
        "notes": (
            f"User-supplied strain {strain.strain_id} from dataset {namespace.dataset_id}. Its enzyme classes "
            "come from the user's enzymes.csv; no growth, secretion or uptake model is implied."
        ),
    }
    if strain.scientific_name:
        mapping["scientific_name"] = strain.scientific_name
    return mapping


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


def _compatibility_mapping(info: _EnzymeClassInfo, substrate: _Substrate, namespace: _Namespace) -> dict[str, Any]:
    shared = _shared_bonds(info, substrate) or ()
    symbols = {
        role: _parameter_symbol(namespace, quantity, info.key, substrate.substrate_id)
        for quantity, role in _QUANTITY_ROLE.items()
    }
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
        "required_parameters": [symbols[role] for role in HOMOGENEOUS_MM_PARAMETER_ROLES],
        "parameter_roles": {role: symbols[role] for role in HOMOGENEOUS_MM_PARAMETER_ROLES},
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
) -> dict[str, Any]:
    template_id = _template_id(namespace, info, substrate)
    states = _state_names(info.key, substrate)
    simulation = namespace.manifest["simulation"]
    mode = "scientific" if scientific else "exploratory"
    yield_value = float(substrate.product_yield)
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
        "initial_state_mapping": {
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
        "observable_roles": ["substrate", "product", "enzyme", "degradation_rate", "product_release_rate"],
        "output_state_roles": dict(states),
        "process_state_metadata": {
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
        },
        "limitations": [
            f"Dissolved homogeneous Michaelis-Menten kinetics from user dataset {namespace.dataset_id}.",
            "This is an enzyme-kinetics case, not a whole-fungus growth, secretion or uptake model.",
            "No temperature or pH response law is bound; values apply at their stated condition only.",
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
    strain: _Strain,
    info: _EnzymeClassInfo,
    substrate: _Substrate,
    condition: _Condition,
    namespace: _Namespace,
) -> dict[str, Any]:
    exact = row.value is not None
    if row.evidence_type == "estimate":
        allowed_use = PARAMETER_ALLOWED_USE_EXPLORATORY
    elif exact:
        allowed_use = PARAMETER_ALLOWED_USE_SCIENTIFIC
    else:
        allowed_use = PARAMETER_ALLOWED_USE_EXPLORATORY_SCREENING
    maturity = _EVIDENCE_MATURITY[row.evidence_type]
    confidence = "exploratory_assumption" if row.evidence_type == "estimate" else maturity
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
    provenance: dict[str, Any] = {
        "source": row.source,
        "confidence_level": confidence,
        "measurement_method": row.method or "user estimate without a stated method",
        "validity_range": _validity_range(condition),
        USER_DATASET_PROVENANCE_KEY: namespace.provenance(
            "kinetics.csv",
            row.row,
            source=row.source,
            method=row.method or None,
            evidence_type=row.evidence_type,
            sd=row.sd,
            replicates=row.replicates,
            condition_id=condition.condition_id,
        ),
    }
    if row.evidence_type == "estimate":
        provenance["exploratory_prior"] = True
    mapping: dict[str, Any] = {
        "record_id": namespace.id(
            strain.strain_id, info.key, substrate.substrate_id, condition.condition_id, row.quantity
        ),
        "name": f"{_QUANTITY_LABEL[row.quantity]} for {info.name} from {strain.name} on {substrate.name} at "
        f"{condition.condition_id} ({namespace.dataset_id})",
        "maturity": maturity,
        "provenance": provenance,
        "notes": (
            f"User-supplied {row.quantity} from dataset {namespace.dataset_id} (kinetics.csv row {row.row}); "
            f"evidence type {row.evidence_type}."
        ),
        **_selectors(namespace, strain, info, substrate, condition, row.quantity),
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


def _gap_mapping(
    quantity: str,
    *,
    case_rows: Mapping[str, _Kinetics],
    strain: _Strain,
    info: _EnzymeClassInfo,
    substrate: _Substrate,
    condition: _Condition,
    namespace: _Namespace,
) -> dict[str, Any]:
    units = _gap_units(quantity, case_rows)
    dimension = "1/time" if quantity == "kcat" else "substrate concentration (amount per volume)"
    units_text = units if units is not None else (
        "units of 1/time" if quantity == "kcat" else "concentration units"
    )
    request = _measurement_request(quantity, strain=strain, info=info, substrate=substrate, condition=condition, units_text=units_text)
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


_QUANTITY_LABEL = {
    "km": "km",
    "kcat": "kcat",
    "substrate_initial_concentration": "initial substrate concentration",
    "enzyme_concentration": "enzyme concentration",
}


def _measurement_request(
    quantity: str,
    *,
    strain: _Strain,
    info: _EnzymeClassInfo,
    substrate: _Substrate,
    condition: _Condition,
    units_text: str,
) -> str:
    where = _condition_text(condition)
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
    if quantity == "kcat":
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


def _validity_range(condition: _Condition) -> str:
    return (
        f"Condition {condition.condition_id}: {_condition_text(condition)}; "
        "no temperature or pH response law is attached."
    )


def _condition_text(condition: _Condition) -> str:
    temperature = (
        "unknown temperature"
        if condition.temperature_kelvin is None
        else f"{condition.temperature_text} {condition.temperature_units}"
    )
    ph = "unknown pH" if condition.ph is None else f"pH {condition.ph_text}"
    return f"{temperature}, {ph}"


def _state_names(class_key: str, substrate: _Substrate) -> dict[str, str]:
    substrate_key = substrate.registry_id or substrate.substrate_id
    return {
        "substrate": f"{substrate_key}_concentration",
        "product": f"{substrate.product}_concentration",
        "enzyme": f"{class_key}_concentration",
    }


def _shared_bonds(info: _EnzymeClassInfo, substrate: _Substrate) -> tuple[str, ...] | None:
    if substrate.substrate_class not in info.compatible_substrate_classes:
        return None
    shared = tuple(sorted(set(substrate.bond_classes).intersection(info.target_bond_classes)))
    return shared or None


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
    "KINETIC_QUANTITIES",
    "USER_DATASET_MANIFEST",
    "USER_DATASET_MATURITY_DESIGN",
    "USER_DATASET_MATURITY_ESTIMATE",
    "USER_DATASET_MATURITY_GAP",
    "USER_DATASET_MATURITY_LITERATURE",
    "USER_DATASET_MATURITY_MEASURED",
    "USER_DATASET_PARAMETER_MATURITIES",
    "USER_DATASET_RECORD_MATURITY",
    "USER_DATASET_SCHEMA_VERSION",
    "UserDataError",
    "UserDataset",
    "load_user_dataset",
]
