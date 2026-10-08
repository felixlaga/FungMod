"""User-supplied enzyme and kinetics tables as an in-memory registry overlay.

A user directory holds a manifest (``user_dataset.yml``) and CSV tables of
strains, their enzyme classes, substrates, assay conditions and kinetic values.
``load_user_dataset`` validates every table, collects every problem before it
raises, and turns the tables into production registry mappings: one fungus per
strain, one namespaced enzyme class per declared class, one Michaelis-Menten
compatibility and case template per compatible class and substrate pair, one
parameter record per kinetics row, and one explicit unknown parameter record (a
gap) for every required role that has no row.

Every generated identifier carries the ``<dataset_id>__`` prefix and every
parameter record carries the reserved ``fungmod_user_dataset`` provenance
namespace (dataset, digest, file and row). Nothing is written to the shared
registry: ``UserDataset.overlay`` returns a new in-memory registry.

Scope: dissolved substrates and Michaelis-Menten kinetics in one of three rate
forms per enzyme class and substrate: ``kcat`` with an enzyme concentration, a
maximum rate ``Vmax`` for the simulated system, or the diprotic pH-ionization
form (a pH-independent limiting turnover and Michaelis constant, the two pK
values of the free enzyme and of the enzyme-substrate complex, the pH range of
the fit, and an enzyme concentration), which binds the existing
``ph_ionization_michaelis_menten`` process law so that the rate follows the
environment pH. ``Vmax`` comes from exactly one route per case: an explicit
``vmax`` row, a specific activity times an enzyme loading (a derived record
whose maturity is the weaker input's), or an assay activity measured on the
case substrate at saturation. Products are stoichiometric with an explicit
mol/mol yield.

A substrate may instead be a single suspended solid polymer
(``physical_state`` ``solid_polymer`` with ``amount_basis`` ``dry_mass``):
every substrate-side amount is then a dry mass per volume, the product yield
is g/g, and the same homogeneous Michaelis-Menten law runs as an apparent bulk
saturation law (kcat form, with the enzyme as a protein mass or an assay
activity per volume and kcat checked by pint against both, or an explicit
Vmax). An ``enzyme_dose`` per substrate mass times the case's initial
substrate concentration gives the enzyme concentration as one derived record,
and an optional ``reactivity_exponent`` binds the existing conversion-dependent
``substrate_reactivity`` modifier, ``(S / S0)^n`` with ``S0`` the case's own
initial-substrate record. The activity routes to Vmax and the pH-ionization
form are refused on solids, and so are composite substrates, molar amounts and
adsorption or surface-area inputs, which no implemented law of this route
consumes. An optional ``responses.csv`` binds the parameters of an
existing temperature or pH response law (cardinal temperature, cardinal pH,
Arrhenius) to a strain, enzyme class and substrate; the law enters the
generated case template as a process modifier, and the kinetic constants of
that case must be stated at the law's reference condition. A pH law on a
pH-ionization pair is refused, since the ionization law already reads the pH.
In an enzyme-network dataset a row binds the law, by the same rules, to the
network process of its class on its pool (whose ``ki`` must then also be stated
at the reference condition); the law scales that process's rate only, and a
process without a law keeps the constants of its rows' condition.

A ``kinetics.csv`` row of quantity ``inactivation_rate`` (1/time, at the row's
condition) binds the existing ``first_order`` process law to the enzyme state
of its case, ``dE/dt = -k_d E``: in a single-class case the enzyme-kinetics
template declares the loss process (``enzyme_inactivation``), and in an enzyme
network each class's enzyme state decays by its own constant. The
``thermal_inactivation`` law of ``responses.csv`` (an activation energy and the
reference temperature at which ``inactivation_rate`` is stated) binds the
existing ``thermal_inactivation`` process law instead, so ``k_d`` follows the
Arrhenius law in the environment temperature; it scales no catalytic constant.
All cases of one enzyme class and substrate share the loss process (a case
without the row gets an explicit gap); without any row the enzyme state is not
lost and no default constant is applied. The Vmax form (no enzyme state) and
culture pools (which keep their own ``enzyme_loss_rate``) refuse it.

An optional ``culture.csv`` binds the existing ``culture_physiology``
composition to a strain growing on one solid substrate: the substrate is
consumed by the strain's enzyme pools that act on it, each by its own
``k_h E S / (K_h + S)`` (several such pools act in parallel and their rates add,
with no competition for sites and no synergy), and every consumed gram is
turned into biomass dry mass with the culture's one explicit yield, the
remainder booked to a closure ledger; biomass is lost at a first-order rate;
every enzyme pool of the culture is produced in proportion to biomass, induced
by the substrate with one shared half-saturation constant, and lost at its own
first-order rate. A row gives one role of one culture (strain, substrate,
condition): a culture-level quantity with ``enzyme_class`` blank, or a quantity
of one enzyme pool with its class. The pools are the classes the rows name;
those that act on the substrate (at least one) consume it, the others are
produced and lost only. Pools stay in their own units (a protein mass or an
assay activity per volume), the substrate and the biomass are dry masses per
volume in one unit, and a culture needs a ``solid_polymer`` substrate on a
dry-mass basis. One culture model serves every strain that declares one of its
consuming classes; each role of each strain and condition is a parameter
record or an explicit gap. A culture is never mixed with the enzyme-assay
forms of ``kinetics.csv`` for the same strain and substrate nor combined with
an enzyme network (no uptake law for a released soluble pool exists), carries
no response law and no time course in this version, and runs the existing
process laws with no new numerics.

An optional ``enzyme_network`` block in the manifest (``entry_substrates``)
makes every case of the dataset an enzyme network instead of the one class the
preflight selects: every declared class of the strain that acts on a pool of
the network runs its own homogeneous Michaelis-Menten process (kcat or Vmax
form) through the existing ``enzyme_network`` composition, processes on one
pool add their rates, and a pool released by one class is the substrate of the
next only where a substrate's ``substrates.csv`` product equals another
``substrate_id``, with the stated yield. Intermediate pools and the final product
start at zero. A ``ki`` row naming an ``inhibitor`` (a pool released downstream
of its own) binds the existing provenance-bound competitive-inhibition modifier
to that process; without one the process has no inhibition term. A solid pool
(dry mass per volume) releases a dissolved pool (amount per volume), or a molar
final product, only through a unit-bearing yield the user states in
``yield_basis`` (an amount of product per dry mass, for example ``mmol/g``)
with its own ``yield_evidence_type``: it becomes a parameter record that sets
the mode like any other input and binds the release coefficient, the pools
after it are reported in the entry's units times the yield's units, and the
closure is computed through it. FungMod never derives such a yield from a molar
mass. Cycles, ambiguous products, links across bases without a unit-bearing
yield (and every link from a dissolved pool to a solid one), a class on two
pools of one network and strains with different member classes are refused;
classes act additively and independently, with no synergy or competition for
sites. Every class of a network dataset runs in its networks only, so the
records of a dataset without the block are unchanged.

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

An optional ``timecourse.csv`` holds measured substrate remaining and product
formed over time for declared cases. Time courses are validated (references,
units of the case's kind, finite values, nonnegative times, one row per time)
and kept on ``UserDataset.timecourses``; they never become registry records.
``fungal_model.api.user_data_fit`` compares simulations with them and fits
kinetic constants to them; a fitted value returns as a ``kinetics.csv`` row of
evidence type ``fitted`` (maturity ``user_fitted``, exploratory screening
only), accepted only together with the manifest ``fit`` block and the fit
report that describe it.

A table cell or manifest value that begins with ``REVIEW:`` is an unfilled
review field left by a drafted dataset (for example tables drafted from a
public kinetics source). Such a dataset is refused, naming every review field,
before any other table is interpreted.
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
from fungal_model.core.units import ASSAY_BASE_UNITS, Q_, units_are_compatible
from fungal_model.kinetics.arrhenius import arrhenius_reference_scaled_rate
from fungal_model.kinetics.cardinal import cardinal_ph_activity, cardinal_temperature_activity
from fungal_model.kinetics.inactivation import arrhenius_inactivation_rate_constant
from fungal_model.modifiers.reactivity import KADAM_2004_SOURCE, SUBSTRATE_REACTIVITY_MODIFIER_TYPE
from fungal_model.processes.inactivation import THERMAL_INACTIVATION_PROCESS_TYPE
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
    ENZYME_INACTIVATION_PROCESS_LAWS,
    ENZYME_INACTIVATION_TEMPLATE_KEY,
    HOMOGENEOUS_MM_PARAMETER_ROLES,
    HOMOGENEOUS_MM_VMAX_PARAMETER_ROLES,
    PH_IONIZATION_MM_PARAMETER_ROLES,
    PH_IONIZATION_MM_PROCESS_TYPE,
)
from fungal_model.screening.culture_physiology import (
    COMPETITIVE_INHIBITION_MODIFIER_TYPE,
    CULTURE_PHYSIOLOGY_PROCESS_TYPE,
)
from fungal_model.screening.enzyme_network import ENZYME_NETWORK_PROCESS_TYPE
from fungal_model.screening.template_environment_modifiers import (
    ENVIRONMENT_MODIFIER_CONDITIONS,
    ENVIRONMENT_MODIFIER_TYPES,
    PROCESS_ENVIRONMENT_CONDITIONS,
)

_RecordT = TypeVar("_RecordT", bound=RegistryRecord)

USER_DATASET_SCHEMA_VERSION = "1"
USER_DATASET_MANIFEST = "user_dataset.yml"
USER_DATASET_PROCESS_TYPE = "homogeneous_michaelis_menten"
# The process law of the pH-ionization rate form; it reads the environment pH itself.
USER_DATASET_PH_IONIZATION_PROCESS_TYPE = PH_IONIZATION_MM_PROCESS_TYPE
# The process law a culture.csv culture runs: the registry's culture_physiology composition.
USER_DATASET_CULTURE_PROCESS_TYPE = CULTURE_PHYSIOLOGY_PROCESS_TYPE
# The process type of an enzyme network: several enzyme classes acting together on a chain of pools.
USER_DATASET_NETWORK_PROCESS_TYPE = ENZYME_NETWORK_PROCESS_TYPE

USER_DATASET_MATURITY_MEASURED = "user_measured"
USER_DATASET_MATURITY_LITERATURE = "user_reported_literature"
USER_DATASET_MATURITY_DESIGN = "user_design_value"
USER_DATASET_MATURITY_ESTIMATE = "exploratory_prior"
USER_DATASET_MATURITY_GAP = "user_dataset_gap"
# A kinetic constant fitted by ``fit_user_dataset`` to the dataset's own time courses.
USER_DATASET_MATURITY_FITTED = "user_fitted"
USER_DATASET_RECORD_MATURITY = "user_supplied_metadata"
USER_DATASET_PARAMETER_MATURITIES = frozenset(
    {
        USER_DATASET_MATURITY_MEASURED,
        USER_DATASET_MATURITY_LITERATURE,
        USER_DATASET_MATURITY_DESIGN,
        USER_DATASET_MATURITY_FITTED,
    }
)

FITTED_EVIDENCE_TYPE = "fitted"
EVIDENCE_TYPES = ("measured", "literature", "design", "estimate", FITTED_EVIDENCE_TYPE)
RESPONSE_EVIDENCE_TYPES = ("measured", "literature", "estimate")
_EVIDENCE_MATURITY = {
    "measured": USER_DATASET_MATURITY_MEASURED,
    "literature": USER_DATASET_MATURITY_LITERATURE,
    "design": USER_DATASET_MATURITY_DESIGN,
    "estimate": USER_DATASET_MATURITY_ESTIMATE,
    FITTED_EVIDENCE_TYPE: USER_DATASET_MATURITY_FITTED,
}
_EVIDENCE_REQUIRES_METHOD = frozenset({"measured", "literature", "design", FITTED_EVIDENCE_TYPE})
# Kinetic constants ``fit_user_dataset`` can fit, and so the only quantities a ``fitted`` row may carry.
FITTABLE_QUANTITIES = ("km", "kcat", "vmax")
FIT_ERROR_MODELS = ("sd_weighted", "unweighted")
FIT_IDENTIFIED = "identified"
FIT_NOT_IDENTIFIED = "not_identified_within_bounds"
# The one-sided classes reuse the names of ``fungal_model.calibration.bayesian``.
FIT_IDENTIFIABILITY_CLASSES = (FIT_IDENTIFIED, "bounded_above_only", "bounded_below_only", FIT_NOT_IDENTIFIED)
_FIT_BLOCK_FIELDS = frozenset(
    {
        "kind",
        "method",
        "objective",
        "error_model",
        "input_dataset_id",
        "input_dataset_digest",
        "report_file",
        "report_sha256",
        "case",
        "conditions",
        "timecourse_rows",
        "quantities",
        "allow_unidentified",
        "claim_boundary",
    }
)
_FIT_QUANTITY_FIELDS = frozenset(
    {"quantity", "value", "units", "bounds", "initial", "identifiability", "identifiability_method", "interval"}
)
FIT_BLOCK_KIND = "fungmod_user_dataset_fit"
_FITTED_SCIENTIFIC_BOUNDARY = (
    "A fitted value is estimated from the dataset's own time courses; agreement with those time courses is "
    "in-sample by construction and is not independent evidence, so the record is limited to exploratory "
    "screening and scientific mode refuses it."
)
# Weakest first. A record derived from several user rows, and every parameter
# of one response law, takes the weakest maturity of its inputs.
USER_DATASET_MATURITY_ORDER = (
    USER_DATASET_MATURITY_ESTIMATE,
    USER_DATASET_MATURITY_DESIGN,
    USER_DATASET_MATURITY_LITERATURE,
    USER_DATASET_MATURITY_MEASURED,
)
_MATURITY_ORDER_TEXT = " < ".join(USER_DATASET_MATURITY_ORDER)

# Physical states a substrate of a user dataset may have. A dissolved substrate
# is stated in amounts per volume with a mol/mol yield; a solid polymer is one
# suspended polymer stated on a dry-mass basis (mass per volume) with a g/g
# yield, and runs the same Michaelis-Menten law as an apparent bulk law.
PHYSICAL_STATE_DISSOLVED = "dissolved"
PHYSICAL_STATE_SOLID_POLYMER = "solid_polymer"
SUBSTRATE_PHYSICAL_STATES = (PHYSICAL_STATE_DISSOLVED, PHYSICAL_STATE_SOLID_POLYMER)
AMOUNT_BASIS_DRY_MASS = "dry_mass"
# The amount basis each physical state requires in substrates.csv (blank: amounts per volume).
_AMOUNT_BASIS = MappingProxyType({PHYSICAL_STATE_DISSOLVED: "", PHYSICAL_STATE_SOLID_POLYMER: AMOUNT_BASIS_DRY_MASS})
_SOLID_YIELD_BASIS = "g/g"
# A unit-bearing yield (enzyme networks only): an amount of a dissolved product per dry mass of the solid that
# releases it, stated by the user in yield_basis (for example mmol/g) with its own evidence type and method. Its
# dimension is checked with pint against this reference; FungMod never derives it from a molar mass.
_UNIT_BEARING_YIELD_REFERENCE_UNITS = "mol / gram"
YIELD_EVIDENCE_COLUMN = "yield_evidence_type"
YIELD_METHOD_COLUMN = "yield_method"
YIELD_EVIDENCE_TYPES = ("measured", "literature", "estimate")
# The kinetics-free parameter role of a unit-bearing yield in a network template: product_yield__<pool>.
NETWORK_YIELD_QUANTITY = "product_yield"
# Physical states of the registry vocabulary that describe composite materials (several polymer fractions).
_COMPOSITE_PHYSICAL_STATES = frozenset({"mixed_solid", "solid_biomass"})
# The template role of the exponent n of the conversion-dependent reactivity factor (S / S0)^n.
REACTIVITY_EXPONENT_ROLE = "reactivity_exponent"

KINETIC_QUANTITIES = (
    "km",
    "kcat",
    "substrate_initial_concentration",
    "enzyme_concentration",
    "vmax",
    "specific_activity",
    "enzyme_loading",
    "assay_activity",
    "kcat_limiting",
    "km_limiting",
    "pk_free_lower",
    "pk_free_upper",
    "pk_complex_lower",
    "pk_complex_upper",
    "ph_min",
    "ph_max",
    "enzyme_dose",
    "reactivity_exponent",
    "ki",
    "inactivation_rate",
)
# The quantities only the pH-ionization rate form has; its enzyme concentration
# and initial substrate are shared with the kcat form. The roles are those of the
# ``ph_ionization_michaelis_menten`` assembler: kcat(pH) = kcat_limiting / f_es(pH)
# and Km(pH) = km_limiting x f_e(pH) / f_es(pH), so the limiting constants are
# the plateau values of the fit, not the kcat or Km at any one pH.
PH_IONIZATION_QUANTITIES = (
    "kcat_limiting",
    "km_limiting",
    "pk_free_lower",
    "pk_free_upper",
    "pk_complex_lower",
    "pk_complex_upper",
    "ph_min",
    "ph_max",
)
_QUANTITY_ROLE = {
    "km": "km",
    "kcat": "kcat",
    "substrate_initial_concentration": "substrate_initial_concentration",
    "enzyme_concentration": "enzyme_initial_concentration",
    "vmax": "vmax",
    "kcat_limiting": "turnover",
    "km_limiting": "michaelis_constant",
    "pk_free_lower": "free_enzyme_lower_pk",
    "pk_free_upper": "free_enzyme_upper_pk",
    "pk_complex_lower": "complex_lower_pk",
    "pk_complex_upper": "complex_upper_pk",
    "ph_min": "minimum_ph",
    "ph_max": "maximum_ph",
    "reactivity_exponent": REACTIVITY_EXPONENT_ROLE,
    "inactivation_rate": "inactivation_rate",
}
_ROLE_QUANTITY = {role: quantity for quantity, role in _QUANTITY_ROLE.items()}
_CONCENTRATION_QUANTITIES = ("substrate_initial_concentration", "km", "enzyme_concentration", "km_limiting")
# Quantities that are kinetic constants measured at a condition; a bound
# response law rescales them, so they must be stated at its reference condition.
_KINETIC_CONSTANT_QUANTITIES = frozenset(
    {"km", "kcat", "vmax", "specific_activity", "assay_activity", "kcat_limiting", "km_limiting"}
)
# The constants a bound response law requires at its reference condition: the kinetic constants and, in an enzyme
# network, the competitive inhibition constant of the process (like Km, a constant of the rate at that condition).
_LAW_REFERENCE_QUANTITIES = _KINETIC_CONSTANT_QUANTITIES | {"ki"}
# The two ionizations of the diprotic law: (lower pK, upper pK, what ionizes).
_PK_PAIRS = (
    ("pk_free_lower", "pk_free_upper", "free enzyme"),
    ("pk_complex_lower", "pk_complex_upper", "enzyme-substrate complex"),
)
# The pH range over which the law was fitted; exact values only, never sampled.
_PH_RANGE_QUANTITIES = ("ph_min", "ph_max")
_DIMENSIONLESS_QUANTITIES = frozenset({*(name for pair in _PK_PAIRS for name in pair[:2]), *_PH_RANGE_QUANTITIES})
_RATE_CONSTANT_QUANTITIES = frozenset({"kcat", "kcat_limiting"})
_POSITIVE_QUANTITIES = frozenset({"km", "km_limiting", "ki"})
_PH_SCALE = (0.0, 14.0)
_YIELD_BASIS = "mol/mol"
_YIELD_BASIS_BY_STATE = MappingProxyType(
    {PHYSICAL_STATE_DISSOLVED: _YIELD_BASIS, PHYSICAL_STATE_SOLID_POLYMER: _SOLID_YIELD_BASIS}
)
_UNKNOWN_CELL = "unknown"
# A cell or manifest value starting with this marker is a field a drafted
# dataset left for a person to decide; it is refused until it is replaced.
REVIEW_MARKER = "REVIEW:"
_REVIEW_ISSUE_PREFIX = "Unfilled review field"
_YES = "yes"
_NO = "no"

# Rate forms of homogeneous Michaelis-Menten kinetics and the quantities each
# generates records for, in record order.
RATE_FORM_KCAT = "kcat_enzyme"
RATE_FORM_VMAX = "vmax"
RATE_FORM_PH_IONIZATION = "ph_ionization"
_FORM_ROLES = {
    RATE_FORM_KCAT: HOMOGENEOUS_MM_PARAMETER_ROLES,
    RATE_FORM_VMAX: HOMOGENEOUS_MM_VMAX_PARAMETER_ROLES,
    RATE_FORM_PH_IONIZATION: PH_IONIZATION_MM_PARAMETER_ROLES,
}
_FORM_QUANTITIES = {form: tuple(_ROLE_QUANTITY[role] for role in roles) for form, roles in _FORM_ROLES.items()}
_FORM_PROCESS_TYPE = {
    RATE_FORM_KCAT: USER_DATASET_PROCESS_TYPE,
    RATE_FORM_VMAX: USER_DATASET_PROCESS_TYPE,
    RATE_FORM_PH_IONIZATION: USER_DATASET_PH_IONIZATION_PROCESS_TYPE,
}
# Forms in the order a pair-level conflict names them: the first present is the reference.
_FORM_ORDER = (RATE_FORM_KCAT, RATE_FORM_VMAX, RATE_FORM_PH_IONIZATION)
_FORM_LABEL = {RATE_FORM_KCAT: "kcat", RATE_FORM_VMAX: "Vmax", RATE_FORM_PH_IONIZATION: "pH-ionization"}
# Forms with an explicit enzyme state.
_ENZYME_FORMS = frozenset({RATE_FORM_KCAT, RATE_FORM_PH_IONIZATION})
_PROCESS_LABEL = {
    USER_DATASET_PROCESS_TYPE: "homogeneous Michaelis-Menten",
    USER_DATASET_PH_IONIZATION_PROCESS_TYPE: "pH-ionization Michaelis-Menten",
    USER_DATASET_CULTURE_PROCESS_TYPE: "culture physiology",
    USER_DATASET_NETWORK_PROCESS_TYPE: "enzyme network",
}
_PROCESS_SENTENCE_LABEL = {
    USER_DATASET_PROCESS_TYPE: "Homogeneous Michaelis-Menten",
    USER_DATASET_PH_IONIZATION_PROCESS_TYPE: "pH-ionization Michaelis-Menten",
}
_PROCESS_ID_SUFFIX = {
    USER_DATASET_PROCESS_TYPE: "homogeneous_mm",
    USER_DATASET_PH_IONIZATION_PROCESS_TYPE: "ph_ionization_mm",
}
_KCAT_FORM_QUANTITIES = ("kcat", "enzyme_concentration")
# Rows that start the kcat form of a case: an enzyme dose sets its enzyme concentration.
_KCAT_FORM_ROW_QUANTITIES = (*_KCAT_FORM_QUANTITIES, "enzyme_dose")
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
# The competitive inhibition constant of a process in an enzyme network, and the column naming its inhibitor: the
# substrate_id of a pool the network forms downstream of the row's substrate, or the network's final product.
INHIBITION_CONSTANT_QUANTITY = "ki"
INHIBITOR_COLUMN = "inhibitor"
# The law ``ki`` binds is the existing provenance-bound competitive-inhibition modifier (BIO-003). Its primary source
# is the law provenance FungMod records for that modifier (foundation_progress/proposals/
# BIO_003_COMPETITIVE_INHIBITION.yml); it supports the equation, not any user's Ki, which keeps its own row source.
COMPETITIVE_INHIBITION_LAW_SOURCE = "https://pubmed.ncbi.nlm.nih.gov/7985803/"
COMPETITIVE_INHIBITION_LAW_MATURITY = "literature_backed_software_tested"
COMPETITIVE_INHIBITION_EQUATION = "rate x (Km + S) / (Km (1 + I / Ki) + S), i.e. Vmax S / (Km (1 + I / Ki) + S)"
# First-order inactivation of the enzyme state of a case (USERDATA-011): kinetics.csv gives the constant k_d of
# dE/dt = -k_d E at the row's condition, which binds the existing first_order process law to the enzyme state. The
# Arrhenius pair of the existing thermal_inactivation process law (an activation energy and the reference temperature
# of k_d) comes from responses.csv and binds that law instead. Without either the enzyme state is not lost.
INACTIVATION_RATE_QUANTITY = "inactivation_rate"
INACTIVATION_LAW = THERMAL_INACTIVATION_PROCESS_TYPE
_FIRST_ORDER_LOSS = "first_order"
# What a responses.csv law scales: the catalytic rate (a process modifier) or the inactivation constant (a process law).
LAW_SCALES_RATE = "rate"
LAW_SCALES_INACTIVATION = "inactivation"
# The manifest switch of enzyme networks: entry_substrates lists the substrates each network starts from.
NETWORK_MANIFEST_FIELD = "enzyme_network"
NETWORK_ENTRY_FIELD = "entry_substrates"
_NETWORK_FIELDS = frozenset({NETWORK_ENTRY_FIELD})
_RETIRED_QUANTITY_HINTS = {
    "enzyme_activity": (
        "quantity 'enzyme_activity' is ambiguous; use specific_activity (amount per time per enzyme mass, "
        "with an enzyme_loading row) or assay_activity (amount per time per volume of the simulated system, "
        "measured on the case substrate at saturation)."
    ),
}
# Inputs of adsorption and surface rate laws (Langmuir coverage, binding capacity,
# accessible area). No law of the user-data route reads them yet, so they are
# refused rather than stored unused: as kinetics.csv quantities and as
# substrates.csv columns. Each maps to what it describes.
_SURFACE_LAW_QUANTITIES = MappingProxyType(
    {
        "adsorption_constant": "an adsorption (Langmuir) constant",
        "adsorption_dissociation_constant": "an adsorption dissociation constant",
        "binding_capacity": "an enzyme binding capacity",
        "accessible_surface_area": "an accessible surface area",
        "specific_surface_area": "a specific surface area",
        "surface_rate_constant": "a surface rate constant",
    }
)
_SURFACE_LAW_SUBSTRATE_COLUMNS = MappingProxyType(
    {
        "specific_surface_area": "a specific surface area",
        "accessible_surface_area": "an accessible surface area",
        "surface_area": "a surface area",
        "binding_capacity": "an enzyme binding capacity",
        "adsorption_capacity": "an enzyme adsorption capacity",
        "crystallinity_index": "a crystallinity index",
        "particle_size": "a particle size",
        "accessible_fraction": "an accessible fraction",
    }
)
_SURFACE_LAW_LIMIT = (
    "no rate law of the user-data route reads it in this version: a solid substrate runs the apparent "
    "Michaelis-Menten law on its dry mass per volume (km with kcat and an enzyme concentration or enzyme_dose, or "
    "vmax, and optionally reactivity_exponent). Adsorption, binding capacity and surface area enter with the law "
    "that consumes them (a Langmuir surface law is a later increment), and FungMod does not store a value no law "
    "uses."
)
# Quantities refused on a solid substrate, with the reason.
_SOLID_REFUSED_QUANTITIES = MappingProxyType(
    {
        "specific_activity": (
            "specific_activity is refused on a solid substrate: an activity in amount per time per enzyme mass "
            "would need the molar mass of a repeat unit of the polymer, which FungMod does not assume, and in "
            "substrate mass per time per enzyme mass it is the kcat of the kcat form with a protein-mass enzyme "
            "concentration. Give kcat (for example g/(mg h)) with enzyme_concentration or enzyme_dose, or vmax."
        ),
        "enzyme_loading": (
            "enzyme_loading belongs to the specific_activity route to Vmax, which is refused on a solid substrate; "
            "give the enzyme as enzyme_concentration (protein mass or assay activity per volume) or as enzyme_dose "
            "per substrate mass, with kcat."
        ),
        "assay_activity": (
            "assay_activity is refused on a solid substrate: a saturating activity is not defined for an "
            "interfacial substrate, and an assay activity (for example FPU) is not a rate in substrate units. "
            "Give the activity as an enzyme concentration in assay units per volume with kcat, or give vmax."
        ),
        "ki": (
            "ki is refused on a solid substrate: the competitive-inhibition law (Km + S) / (Km (1 + I / Ki) + S) "
            "describes an inhibitor competing for the binding site of a dissolved substrate, while the Km of the "
            "apparent law on a solid is a half-saturation constant, not a binding constant, and its products are "
            "lumped dry-mass pools. No product inhibition is bound on a solid substrate in this version."
        ),
        **{
            quantity: (
                f"{quantity} belongs to the pH-ionization form, which is refused on a solid substrate: the diprotic "
                "law makes Km a function of the ionization of a dissolved enzyme-substrate complex, while the Km of "
                "the apparent law on a solid is a half-saturation constant, not a binding constant. Use the kcat or "
                "Vmax form, with a cardinal pH law in responses.csv if the rate depends on pH."
            )
            for quantity in PH_IONIZATION_QUANTITIES
        },
    }
)
# Quantities that only a solid substrate on a dry-mass basis can carry, with the reason.
_SOLID_ONLY_QUANTITIES = MappingProxyType(
    {
        "enzyme_dose": (
            "enzyme_dose is an enzyme amount per substrate mass and applies only to a solid_polymer substrate on a "
            "dry-mass basis; give a dissolved substrate's enzyme as enzyme_concentration."
        ),
        "reactivity_exponent": (
            "reactivity_exponent applies only to a solid_polymer substrate: the conversion-dependent reactivity "
            "factor (S / S0)^n describes the remaining material of a particulate substrate becoming less "
            "accessible, which is not a property of a dissolved substrate."
        ),
    }
)

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

TIMECOURSE_TABLE = "timecourse.csv"
# Measured observables of a time course and the case-template state role each one measures.
TIMECOURSE_OBSERVABLES = ("substrate", "product")

CULTURE_TABLE = "culture.csv"
# Quantities of a culture as a whole (enzyme_class blank) ...
CULTURE_LEVEL_QUANTITIES = (
    "substrate_initial_concentration",
    "initial_biomass",
    "biomass_yield",
    "biomass_loss_rate",
    "induction_half_saturation",
)
# ... of the enzyme pool that consumes the substrate (enzyme_class: that pool's class) ...
CULTURE_CONSUMPTION_QUANTITIES = ("hydrolysis_capacity", "hydrolysis_half_saturation")
# ... and of every enzyme pool (enzyme_class: the pool's class).
CULTURE_POOL_QUANTITIES = ("initial_enzyme_concentration", "specific_production_rate", "enzyme_loss_rate")
CULTURE_QUANTITIES = (*CULTURE_LEVEL_QUANTITIES, *CULTURE_CONSUMPTION_QUANTITIES, *CULTURE_POOL_QUANTITIES)
# culture.csv carries measured, literature, design and estimated values; fit_user_dataset fits no culture constant.
CULTURE_EVIDENCE_TYPES = ("measured", "literature", "design", "estimate")
# The template role each culture-level and consumption quantity binds; a pool quantity binds "<quantity>__<class>".
_CULTURE_ROLE = MappingProxyType(
    {
        "substrate_initial_concentration": "initial_substrate",
        "initial_biomass": "initial_biomass",
        "biomass_yield": "biomass_yield",
        "biomass_loss_rate": "biomass_loss_rate",
        "induction_half_saturation": "induction_half_saturation",
        "hydrolysis_capacity": "hydrolysis_capacity",
        "hydrolysis_half_saturation": "hydrolysis_half_saturation",
    }
)
# Culture quantities that must be positive (half-saturation constants and the yield); the others may be zero.
_CULTURE_POSITIVE_QUANTITIES = frozenset({"induction_half_saturation", "hydrolysis_half_saturation", "biomass_yield"})
_CULTURE_RATE_CONSTANT_QUANTITIES = frozenset({"biomass_loss_rate", "enzyme_loss_rate"})
_CULTURE_DRY_MASS_QUANTITIES = frozenset(
    {"substrate_initial_concentration", "induction_half_saturation", "hydrolysis_half_saturation"}
)

_REQUIRED_TABLES = ("strains.csv", "enzymes.csv", "substrates.csv", "conditions.csv", "kinetics.csv")
_OPTIONAL_TABLES = ("enzyme_classes.csv", "responses.csv", GENOME_TABLE, TIMECOURSE_TABLE, CULTURE_TABLE)
_TABLE_COLUMNS: Mapping[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "strains.csv": (("strain_id", "name"), ("scientific_name", "aliases")),
    "enzymes.csv": (("strain_id", "enzyme_class", "evidence", "source"), ()),
    "enzyme_classes.csv": (
        ("class_id", "name", "target_bond_classes", "compatible_substrate_classes", "source"),
        ("ec_number",),
    ),
    "substrates.csv": (
        ("substrate_id", "product", "product_yield", "yield_basis", "source"),
        (
            "registry_substrate",
            "name",
            "substrate_class",
            "physical_state",
            "bond_classes",
            "amount_basis",
            YIELD_EVIDENCE_COLUMN,
            YIELD_METHOD_COLUMN,
        ),
    ),
    "conditions.csv": (("condition_id", "temperature", "temperature_units", "ph"), ("notes",)),
    "kinetics.csv": (
        ("strain_id", "enzyme_class", "substrate_id", "condition_id", "quantity", "units", "evidence_type", "source"),
        ("value", "lower", "upper", "method", "sd", "replicates", *_ACTIVITY_COLUMNS, INHIBITOR_COLUMN),
    ),
    "responses.csv": (
        ("strain_id", "enzyme_class", "substrate_id", "law", "parameter", "value", "units", "evidence_type", "source"),
        ("method", "reference_tolerance", "kinetics_at_reference"),
    ),
    GENOME_TABLE: (("strain_id", "annotation_file", "annotation_tool", "source"), ("min_tools_agreeing",)),
    TIMECOURSE_TABLE: (
        (
            "strain_id",
            "enzyme_class",
            "substrate_id",
            "condition_id",
            "observable",
            "time",
            "time_units",
            "value",
            "units",
            "source",
            "method",
        ),
        ("sd", "replicates"),
    ),
    CULTURE_TABLE: (
        ("strain_id", "substrate_id", "condition_id", "quantity", "units", "evidence_type", "source"),
        ("enzyme_class", "value", "lower", "upper", "method", "sd", "replicates"),
    ),
}
# Columns a table refuses with a specific reason instead of the generic unsupported-column message.
_REFUSED_COLUMNS: Mapping[str, Mapping[str, str]] = MappingProxyType({"substrates.csv": _SURFACE_LAW_SUBSTRATE_COLUMNS})
_TABLES_WITH_ROWS_REQUIRED = ("strains.csv", "enzymes.csv", "substrates.csv", "conditions.csv")
_MANIFEST_FIELDS = frozenset(
    {"dataset_id", "contributor", "date", "source", "notes", "simulation", "fit", NETWORK_MANIFEST_FIELD}
)
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
# Enzyme amounts a solid case may use: a protein mass, or an activity in one of
# the registry's assay units (never converted to protein mass or molarity).
_ENZYME_ASSAY_UNITS = ASSAY_BASE_UNITS


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

    A law that scales the catalytic rate (``scales`` ``rate``) is the
    process-modifier type ``law`` the case-template machinery already
    implements; ``parameters`` are its template roles, each bound through the
    modifier field ``<name>_role``; ``reference_parameter`` names the parameter
    at whose value the law's activity is one, so kinetic constants scaled by
    the law must be stated there. A law that scales the enzyme's first-order
    inactivation constant (``scales`` ``inactivation``) is the existing process
    law ``law`` that then replaces the first-order loss of the enzyme state; the
    ``inactivation_rate`` it scales must be stated at its reference parameter.
    """

    law: str
    label: str
    parameters: tuple[ResponseLawParameter, ...]
    reference_parameter: str
    formula: str
    scales: str = LAW_SCALES_RATE

    @property
    def reads(self) -> str:
        """The environment condition the law reads."""

        if self.scales == LAW_SCALES_RATE:
            return ENVIRONMENT_MODIFIER_CONDITIONS[self.law]
        return PROCESS_ENVIRONMENT_CONDITIONS[self.law][0]

    @property
    def condition(self) -> str:
        """The condition through which the law rescales the catalytic rate of a case.

        Empty for a law that scales the inactivation constant: it carries no
        catalytic constant to another condition.
        """

        return self.reads if self.scales == LAW_SCALES_RATE else ""

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
            ResponseLaw(
                law=INACTIVATION_LAW,
                label="Arrhenius law of the first-order inactivation constant",
                parameters=(
                    ResponseLawParameter(
                        "activation_energy",
                        "activation energy of inactivation",
                        _MOLAR_ENERGY_REFERENCE_UNITS,
                        "an energy per amount (for example kJ/mol)",
                    ),
                    _temperature_parameter("reference_temperature", "reference temperature of the inactivation rate"),
                ),
                reference_parameter="reference_temperature",
                formula="k_d(T) = k_d(T_ref) x exp(-E_d / R x (1/T - 1/T_ref))",
                scales=LAW_SCALES_INACTIVATION,
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
class TimecoursePoint:
    """One observation of a user time course: one ``timecourse.csv`` row."""

    row: int
    time: float
    value: float
    sd: float | None
    replicates: int | None
    source: str
    method: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": TIMECOURSE_TABLE,
            "row": self.row,
            "time": self.time,
            "value": self.value,
            "sd": self.sd,
            "replicates": self.replicates,
            "source": self.source,
            "method": self.method,
        }


@dataclass(frozen=True)
class UserTimecourse:
    """The observations of one observable of one case, in one time unit and one value unit.

    A case is one strain, enzyme class, substrate and condition; ``case_id``
    is the generated identifier ``<dataset_id>__<strain>__<class>__<substrate>__<condition>``,
    and ``fungus_id``, ``enzyme_class_id``, ``substrate_record_id`` and
    ``environment_id`` are the generated (or referenced registry) record ids a
    virtual experiment simulates. ``observable`` is ``substrate`` (substrate
    remaining) or ``product`` (product formed since time zero). Points are
    sorted by time. Time courses are observations, never registry records.
    """

    case_id: str
    strain_id: str
    class_key: str
    substrate_id: str
    condition_id: str
    fungus_id: str
    enzyme_class_id: str
    substrate_record_id: str
    environment_id: str
    observable: str
    time_units: str
    units: str
    points: tuple[TimecoursePoint, ...]

    @property
    def series_id(self) -> str:
        return f"{self.case_id}__{self.observable}"

    @property
    def rows(self) -> tuple[int, ...]:
        return tuple(point.row for point in self.points)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "series_id": self.series_id,
            "strain_id": self.strain_id,
            "enzyme_class": self.class_key,
            "substrate_id": self.substrate_id,
            "condition_id": self.condition_id,
            "fungus_id": self.fungus_id,
            "enzyme_class_id": self.enzyme_class_id,
            "substrate_record_id": self.substrate_record_id,
            "environment_id": self.environment_id,
            "observable": self.observable,
            "time_units": self.time_units,
            "units": self.units,
            "points": [point.to_dict() for point in self.points],
        }


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

    With a ``timecourse.csv``, ``timecourses`` maps each generated case id to
    the case's ``UserTimecourse`` series (one per observable); it is empty
    without one. Time courses are kept beside the records and never become
    registry records. A dataset written by ``fit_user_dataset`` carries the
    fit description under ``manifest["fit"]``.

    With a ``culture.csv``, ``cultures`` lists one entry per strain and culture
    substrate: the strain, the substrate, the (first) consuming enzyme class,
    every consuming pool, the enzyme pools in template order, the generated
    fungus, substrate, template and compatibility ids, and the culture.csv rows
    of that strain (none for a strain whose culture cases are all gaps). It is
    empty without one.

    With an ``enzyme_network`` block in the manifest, ``enzyme_networks`` lists
    one entry per entry substrate: its chain of pools, the final product, the
    links with their yields, the processes (enzyme class, pool, rate form,
    process id, competitive inhibitor if a ki row binds one, the responses.csv
    laws bound to it, the loss law of its enzyme state), the member classes,
    the strains, and the generated template and compatibility ids. It is empty
    without the block.

    ``enzyme_inactivation`` lists one entry per enzyme class and substrate
    whose enzyme state is lost by first-order inactivation (an
    ``inactivation_rate`` row in kinetics.csv, or the ``thermal_inactivation``
    law in responses.csv): the class, the substrate, the process law
    (``first_order`` or ``thermal_inactivation``), the generated process and
    template ids, and the rows behind it. It is empty when no row binds one;
    every other enzyme state of the dataset is then not lost.
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
    timecourses: Mapping[str, tuple[UserTimecourse, ...]] = field(default_factory=dict)
    cultures: tuple[Mapping[str, Any], ...] = ()
    enzyme_networks: tuple[Mapping[str, Any], ...] = ()
    enzyme_inactivation: tuple[Mapping[str, Any], ...] = ()
    # The bytes of every input file (tables, manifest, annotation and fit-report files) by relative
    # path, and the parsed rows; ``fit_user_dataset`` writes its copies of the dataset from them.
    _raw_files: Mapping[str, bytes] = field(default_factory=dict, repr=False, compare=False)
    _parsed: Any = field(default=None, repr=False, compare=False)
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
            "timecourses": {
                case_id: [item.to_dict() for item in series] for case_id, series in self.timecourses.items()
            },
            "cultures": [_plain(item) for item in self.cultures],
            "enzyme_networks": [_plain(item) for item in self.enzyme_networks],
            "enzyme_inactivation": [_plain(item) for item in self.enzyme_inactivation],
        }

    def summary(self) -> dict[str, Any]:
        """Return the dataset id, digest, generated record counts, genome-resolution lists, time-course cases,
        cultures and enzyme networks."""

        return {
            "dataset_id": self.dataset_id,
            "digest": self.digest,
            "record_counts": {name: len(self.records.get(name, ())) for name in _RECORD_TYPES},
            **self._genome_lists(),
            "timecourse_case_ids": list(self.timecourses),
            "cultures": [
                {key: item[key] for key in ("strain_id", "substrate_id", "enzyme_class", "enzyme_pools")}
                for item in self.cultures
            ],
            "enzyme_networks": [
                {key: _plain(item[key]) for key in ("entry_substrate", "pools", "product", "enzyme_classes")}
                for item in self.enzyme_networks
            ],
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
    if any(str(issue["message"]).startswith(_REVIEW_ISSUE_PREFIX) for issue in issues):
        # A drafted dataset is interpreted only after a person has filled every review field.
        raise UserDataError(
            f"User dataset {str(directory)!r} still has unfilled review fields (cells or manifest values "
            f"beginning with {REVIEW_MARKER!r}).",
            issues=issues,
        )
    context = _Context(base=base, issues=issues)
    parsed = _parse_rows(tables, context, directory=directory)
    if parsed is not None:
        parsed.network_entries = _network_entry_ids(manifest)
        _cross_validate(parsed, context)
        # Annotation files are inputs like the tables: their bytes enter the digest.
        raw_files = {**raw_files, **parsed.annotation_files}
        # So is the report of a fit, which the fitted rows' provenance cites.
        raw_files = {**raw_files, **_validate_fit_block(parsed, manifest, directory=directory, context=context)}
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
        timecourses=_timecourse_series(parsed, dataset_id=dataset_id),
        cultures=_culture_report(parsed, dataset_id=dataset_id),
        enzyme_networks=_network_report(parsed, dataset_id=dataset_id),
        enzyme_inactivation=_inactivation_report(parsed, dataset_id=dataset_id),
        _raw_files=MappingProxyType(dict(raw_files)),
        _parsed=parsed,
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
    physical_state: str = PHYSICAL_STATE_DISSOLVED
    amount_basis: str = ""
    # A unit-bearing yield (an amount of product per dry mass, as written in yield_basis) with its evidence type
    # and method; blank for the pure-number yield of the row's physical state (g/g or mol/mol).
    yield_units: str = ""
    yield_evidence_type: str = ""
    yield_method: str = ""

    @property
    def is_solid(self) -> bool:
        return self.physical_state != PHYSICAL_STATE_DISSOLVED

    @property
    def yield_basis(self) -> str:
        return self.yield_units or _YIELD_BASIS_BY_STATE[self.physical_state]


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
    # The pool a ki row names as its competitive inhibitor; blank on every other row.
    inhibitor: str = ""

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


@dataclass(frozen=True)
class _TimecourseRow:
    row: int
    strain_id: str
    class_key: str
    substrate_id: str
    condition_id: str
    observable: str
    time: float
    time_units: str
    value: float
    units: str
    sd: float | None
    replicates: int | None
    source: str
    method: str

    @property
    def case_key(self) -> tuple[str, str, str, str]:
        return (self.strain_id, self.class_key, self.substrate_id, self.condition_id)

    @property
    def series_key(self) -> tuple[str, str, str, str, str]:
        return (*self.case_key, self.observable)


@dataclass(frozen=True)
class _CultureRow:
    """One culture.csv row: one role of the culture of a strain on a substrate at a condition."""

    row: int
    strain_id: str
    substrate_id: str
    condition_id: str
    quantity: str
    # The enzyme pool of a pool or consumption quantity; blank for a culture-level quantity.
    class_key: str
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
    def culture_key(self) -> tuple[str, str]:
        return (self.strain_id, self.substrate_id)

    @property
    def role_key(self) -> tuple[str, str]:
        return (self.quantity, self.class_key)

    @property
    def is_exact(self) -> bool:
        return self.value is not None


@dataclass(frozen=True)
class _CulturePair:
    """The culture model of the consuming enzyme classes on one substrate, shared by every strain declaring one.

    ``class_key`` is the first consuming class (it names the model's template);
    ``consumers`` every pool whose class acts on the substrate and consumes it,
    in culture.csv row order (empty means ``class_key`` alone); ``pools`` the
    enzyme pools in template order, the consuming classes first; ``pool_rows``
    the culture.csv row that first named each pool (``None`` for a model no
    culture.csv row starts, whose only pools are its consuming classes).
    """

    class_key: str
    substrate_id: str
    pools: tuple[str, ...]
    pool_rows: Mapping[str, int | None]
    consumers: tuple[str, ...] = ()

    @property
    def started(self) -> bool:
        return any(row is not None for row in self.pool_rows.values())

    @property
    def consuming_pools(self) -> tuple[str, ...]:
        return self.consumers or (self.class_key,)

    @property
    def several(self) -> bool:
        """Several pools consume the substrate in parallel (CULTURE-002); one keeps every USERDATA-009 identifier."""

        return len(self.consuming_pools) > 1


@dataclass(frozen=True)
class _NetworkProcess:
    """One enzyme class consuming one pool of a network, in its pair's rate form."""

    class_key: str
    pool: str
    form: str
    # The pool whose state competitively inhibits this process (a ki row names it); blank without inhibition.
    inhibitor: str = ""
    # Whether the process binds the conversion-dependent reactivity factor (a solid entry pool only).
    reactive: bool = False
    # The responses.csv laws bound to this class on this pool (by any strain of the network), in RESPONSE_LAWS order;
    # each enters the process template as its environment modifier. Empty: the constants hold at their rows' condition.
    # Only laws that scale the rate; the inactivation law is the process law of ``inactivation``.
    laws: tuple[str, ...] = ()
    # The process law through which this class's enzyme state is lost (USERDATA-011): "first_order" with the
    # inactivation_rate of kinetics.csv, the thermal_inactivation law of responses.csv, or blank (not lost).
    inactivation: str = ""


@dataclass(frozen=True)
class _Network:
    """The enzyme network that starts from one entry substrate.

    ``pools`` are the substrate_ids of the chain, the entry first: each pool's
    substrates.csv product is the next pool. ``product`` is the product of the
    last pool, which is no substrate of the dataset: the network's final product.
    ``classes`` are the member classes in declaration order and ``strains`` the
    strains that declare them; ``entry_rows`` maps (strain, condition) to the
    kinetics.csv row of the entry's initial concentration.
    """

    entry: str
    pools: tuple[str, ...]
    product: str
    processes: tuple[_NetworkProcess, ...]
    classes: tuple[str, ...]
    strains: tuple[str, ...]
    entry_rows: Mapping[tuple[str, str], _Kinetics]

    # The pools whose release into the next pool (or the final product) uses a unit-bearing yield: at most one,
    # a solid pool releasing an amount per volume (set from the substrates when the network is built).
    unit_bearing_yield_pools: tuple[str, ...] = ()

    def downstream(self, pool: str) -> tuple[str, ...]:
        """The pools released after ``pool``, the final product last."""

        return (*self.pools[self.pools.index(pool) + 1 :], self.product)

    def converted(self, pool: str) -> bool:
        """Whether ``pool`` (a pool of the network or its final product) lies after a unit-bearing yield."""

        if not self.unit_bearing_yield_pools:
            return False
        conversion = self.pools.index(self.unit_bearing_yield_pools[0])
        position = len(self.pools) if pool == self.product else self.pools.index(pool)
        return position > conversion


@dataclass
class _Parsed:
    strains: dict[str, _Strain]
    classes: dict[str, _EnzymeClassInfo]
    strain_classes: list[_StrainClass]
    substrates: dict[str, _Substrate]
    conditions: dict[str, _Condition]
    kinetics: list[_Kinetics]
    responses: list[_Response] = field(default_factory=list)
    timecourses: list[_TimecourseRow] = field(default_factory=list)
    # (class, substrate) -> rate form, set by cross-validation; absent when no case started a form.
    pair_forms: dict[tuple[str, str], str] = field(default_factory=dict)
    # Enzyme classes whose started pairs all use the pH-ionization form; their unstarted pairs use it too.
    ionization_classes: set[str] = field(default_factory=set)
    # (class, substrate) pairs on a solid substrate whose cases bind the conversion-dependent reactivity factor.
    reactivity_pairs: set[tuple[str, str]] = field(default_factory=set)
    # (strain, class, substrate) -> law -> parameter -> row, set by cross-validation for valid laws.
    laws: dict[tuple[str, str, str], dict[str, dict[str, _Response]]] = field(default_factory=dict)
    # Resolved genome annotations, the annotation files read (relative path -> bytes), and the
    # genomes.csv row of every strain that has one (also rows that failed validation).
    genomes: list[_GenomeAnnotation | _ProteomeAnnotation] = field(default_factory=list)
    annotation_files: dict[str, bytes] = field(default_factory=dict)
    genome_rows: dict[str, int] = field(default_factory=dict)
    culture_rows: list[_CultureRow] = field(default_factory=list)
    # Set by cross-validation: the culture models by (consuming class, substrate), the classes that run the
    # culture form, and the consuming class of every (strain, substrate) culture culture.csv starts.
    culture_pairs: dict[tuple[str, str], _CulturePair] = field(default_factory=dict)
    culture_classes: set[str] = field(default_factory=set)
    cultured: dict[tuple[str, str], str] = field(default_factory=dict)
    # The manifest's network entry substrates (empty without enzyme_network, None when the manifest was unreadable),
    # and, set by cross-validation, the enzyme network of every valid entry.
    network_entries: tuple[str, ...] | None = None
    networks: dict[str, _Network] = field(default_factory=dict)
    # (class, substrate) -> the process law through which the pair's enzyme state is lost ("first_order" or
    # "thermal_inactivation"), set by cross-validation for pairs with inactivation_rate rows or the inactivation law.
    inactivation_pairs: dict[tuple[str, str], str] = field(default_factory=dict)

    @property
    def network_dataset(self) -> bool:
        return bool(self.network_entries)


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
                    f"{', '.join(sorted(known))}. Other tables are not imported.",
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
    reviewed = _review_marker_paths(data)
    for path, text in reviewed.items():
        issues.append(_review_issue(file, None, path, text))
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
    if "fit" in data and not isinstance(data["fit"], Mapping):
        issues.append(
            _issue(file, None, "fit", "fit must be the mapping fit_user_dataset writes to describe a fit.")
        )
    if NETWORK_MANIFEST_FIELD in data:
        issues.extend(_network_manifest_issues(data[NETWORK_MANIFEST_FIELD], file=file))
    if "date" in data:
        value = data["date"]
        if isinstance(value, date) and not isinstance(value, datetime):
            data = {**data, "date": value.isoformat()}
        elif not isinstance(value, str) or not _is_iso_date(value):
            issues.append(_issue(file, None, "date", "date must be an ISO date (YYYY-MM-DD)."))
    simulation = data.get("simulation")
    if not isinstance(simulation, Mapping):
        if "simulation" in reviewed:
            return None
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
        # A field still holding a review marker is reported once, as unfilled, above.
        duration = simulation.get("duration")
        if "simulation.duration" not in reviewed and (
            isinstance(duration, bool)
            or not isinstance(duration, (int, float))
            or not math.isfinite(float(duration))
            or float(duration) <= 0.0
        ):
            issues.append(_issue(file, None, "simulation.duration", "simulation.duration must be a positive number."))
        units = simulation.get("units")
        if "simulation.units" not in reviewed and (
            not isinstance(units, str) or _unit_dimension_error(units, _TIME_REFERENCE_UNITS) is not None
        ):
            issues.append(
                _issue(file, None, "simulation.units", "simulation.units must be a time unit such as second, minute or hour.")
            )
        points = simulation.get("points")
        if "simulation.points" not in reviewed and (
            isinstance(points, bool) or not isinstance(points, int) or points < 2
        ):
            issues.append(_issue(file, None, "simulation.points", "simulation.points must be an integer of at least 2."))
    if len(issues) > count:
        return None
    return dict(data)


def _network_manifest_issues(value: Any, *, file: str) -> list[dict[str, Any]]:
    """Check the shape of the enzyme_network block: a mapping with a nonempty list of distinct substrate ids."""

    field_name = NETWORK_MANIFEST_FIELD
    if not isinstance(value, Mapping):
        return [
            _issue(
                file,
                None,
                field_name,
                f"{field_name} must be a mapping with {NETWORK_ENTRY_FIELD}: the substrate_ids each enzyme network "
                "starts from.",
            )
        ]
    issues: list[dict[str, Any]] = []
    unknown = sorted(str(key) for key in value if str(key) not in _NETWORK_FIELDS)
    if unknown:
        issues.append(_issue(file, None, field_name, f"Unsupported {field_name} field(s): {', '.join(unknown)}."))
    entries = value.get(NETWORK_ENTRY_FIELD)
    column = f"{field_name}.{NETWORK_ENTRY_FIELD}"
    if (
        not isinstance(entries, list)
        or not entries
        or any(not isinstance(item, str) or not _IDENTIFIER_PATTERN.fullmatch(item) for item in entries)
    ):
        issues.append(
            _issue(
                file,
                None,
                column,
                f"{NETWORK_ENTRY_FIELD} must be a nonempty list of substrate_ids of substrates.csv; each names a "
                "substrate an enzyme network starts from.",
            )
        )
    else:
        repeated = sorted({item for item in entries if entries.count(item) > 1})
        if repeated:
            issues.append(_issue(file, None, column, f"{NETWORK_ENTRY_FIELD} lists {', '.join(repeated)} more than once."))
    return issues


def _network_entry_ids(manifest: Mapping[str, Any] | None) -> tuple[str, ...] | None:
    """The entry substrates of the manifest's networks: empty without a network, ``None`` for an unread manifest."""

    if manifest is None:
        return None
    block = manifest.get(NETWORK_MANIFEST_FIELD)
    if not isinstance(block, Mapping):
        return ()
    return tuple(str(item) for item in block.get(NETWORK_ENTRY_FIELD, ()))


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
    refused = _REFUSED_COLUMNS.get(name, {})
    for column in unknown:
        if column in refused:
            issues.append(
                _issue(name, 1, column, f"Column {column!r} ({refused[column]}) is refused: {_SURFACE_LAW_LIMIT}")
            )
    unknown = [column for column in unknown if column not in refused]
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
            for column, text in values.items():
                if text.startswith(REVIEW_MARKER):
                    issues.append(_review_issue(name, line, column, text))
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
    culture_table = tables.get(CULTURE_TABLE)
    culture_rows = (
        []
        if culture_table is None
        else _parse_culture(
            culture_table,
            strains=strains,
            classes=classes,
            strain_classes=strain_classes,
            substrates=substrates,
            conditions=conditions,
            resolver=resolver,
            context=context,
        )
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
    timecourse_table = tables.get(TIMECOURSE_TABLE)
    timecourses = (
        []
        if timecourse_table is None
        else _parse_timecourses(
            timecourse_table,
            strains=strains,
            classes=classes,
            strain_classes=strain_classes,
            substrates=substrates,
            conditions=conditions,
            kinetics=kinetics,
            resolver=resolver,
            context=context,
            cultured={row.culture_key: row.row for row in reversed(culture_rows)},
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
        timecourses=timecourses,
        genomes=genomes.annotations,
        annotation_files=genomes.files,
        genome_rows=genomes.rows,
        culture_rows=culture_rows,
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
        # The bases follow the physical state: the parsed one, else the one the row states.
        state = parsed[4] if parsed is not None else row.get("physical_state", "")
        bases_ok = _substrate_bases_ok(row, state, file=file, line=line, context=context)
        yield_units = _unit_bearing_yield_units(row, state)
        if not _yield_evidence_ok(row, unit_bearing=bool(yield_units), file=file, line=line, context=context):
            bases_ok = False
        if (
            substrate_id is None
            or product is None
            or source is None
            or product_yield is None
            or not bases_ok
            or parsed is None
        ):
            continue
        registry_id, name, substrate_class, bond_classes, physical_state = parsed
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
            physical_state=physical_state,
            amount_basis=_AMOUNT_BASIS[physical_state],
            yield_units=yield_units,
            yield_evidence_type=row.get(YIELD_EVIDENCE_COLUMN, "") if yield_units else "",
            yield_method=row.get(YIELD_METHOD_COLUMN, "") if yield_units else "",
        )
    return substrates


def _unit_bearing_yield_units(row: Mapping[str, str], state: str) -> str:
    """The yield_basis of a solid row when it is an amount of product per dry mass (a unit-bearing yield), else blank."""

    basis = row.get("yield_basis", "")
    if state != PHYSICAL_STATE_SOLID_POLYMER or not basis or basis == _SOLID_YIELD_BASIS:
        return ""
    if _unit_dimension_error(basis, _UNIT_BEARING_YIELD_REFERENCE_UNITS) is not None:
        return ""
    return basis


def _yield_evidence_ok(row: Mapping[str, str], *, unit_bearing: bool, file: str, line: int, context: _Context) -> bool:
    """A unit-bearing yield states its evidence type (and a method for measured or literature values); no other row.

    The pure-number yields (g/g, mol/mol) stay template constants that do not
    set the mode, as before, so their rows leave both columns blank.
    """

    evidence = row.get(YIELD_EVIDENCE_COLUMN, "")
    method = row.get(YIELD_METHOD_COLUMN, "")
    if not unit_bearing and row.get("yield_basis", "") not in _YIELD_BASIS_BY_STATE.values():
        # The yield_basis itself is refused (with the reason) by the basis check; its evidence is not judged.
        return True
    if not unit_bearing:
        filled = [column for column, value in ((YIELD_EVIDENCE_COLUMN, evidence), (YIELD_METHOD_COLUMN, method)) if value]
        for column in filled:
            context.add(
                file,
                line,
                column,
                f"{column} applies to a unit-bearing yield only (an amount of product per dry mass of a solid, for "
                "example mmol/g, on an enzyme-network link). A g/g or mol/mol yield is a template constant that does "
                "not set the mode in this version; leave the column blank.",
            )
        return not filled
    if evidence not in YIELD_EVIDENCE_TYPES:
        stated = "is blank" if not evidence else f"is {evidence!r}"
        context.add(
            file,
            line,
            YIELD_EVIDENCE_COLUMN,
            f"{YIELD_EVIDENCE_COLUMN} {stated}, but the unit-bearing yield {row.get('product_yield', '')} "
            f"{row.get('yield_basis', '')} is a stated input like a kinetic value: give one of "
            f"{', '.join(YIELD_EVIDENCE_TYPES)} (an estimate keeps every case that uses it exploratory).",
        )
        return False
    if evidence in _EVIDENCE_REQUIRES_METHOD and not method:
        context.add(
            file,
            line,
            YIELD_METHOD_COLUMN,
            f"A {evidence} unit-bearing yield needs {YIELD_METHOD_COLUMN}: how it was measured or obtained (for "
            "example the molar masses you used to compute it); FungMod never computes it for you.",
        )
        return False
    return True


def _substrate_bases_ok(row: Mapping[str, str], state: str, *, file: str, line: int, context: _Context) -> bool:
    """Check yield_basis and amount_basis against the substrate's physical state.

    A dissolved substrate is stated in amounts per volume (``amount_basis``
    blank) with a mol/mol yield. A solid polymer is stated on a dry-mass basis
    (``amount_basis`` ``dry_mass``) with a g/g yield: grams of product per gram
    of dry substrate consumed. The yield is always explicit and never inferred,
    and no basis is converted to another. With a state that is not supported
    (reported elsewhere) only the yield basis is checked against the supported
    ones.
    """

    basis = row.get("yield_basis", "")
    amount_basis = row.get("amount_basis", "")
    if state not in SUBSTRATE_PHYSICAL_STATES:
        if basis not in _YIELD_BASIS_BY_STATE.values():
            context.add(
                file,
                line,
                "yield_basis",
                f"yield_basis must be {_YIELD_BASIS!r} for a dissolved substrate or {_SOLID_YIELD_BASIS!r} for a "
                "solid_polymer substrate; the yield is always explicit and never inferred.",
            )
            return False
        return True
    ok = True
    if state == PHYSICAL_STATE_DISSOLVED:
        if basis != _YIELD_BASIS:
            context.add(
                file,
                line,
                "yield_basis",
                f"yield_basis must be {_YIELD_BASIS!r}; the yield is always explicit and never inferred.",
            )
            ok = False
        if amount_basis:
            context.add(
                file,
                line,
                "amount_basis",
                f"amount_basis {amount_basis!r} applies to solid_polymer substrates only; a dissolved substrate is "
                "stated in amounts per volume, so leave amount_basis blank.",
            )
            ok = False
        return ok
    if basis != _SOLID_YIELD_BASIS and not _unit_bearing_yield_units(row, state):
        context.add(
            file,
            line,
            "yield_basis",
            f"yield_basis must be {_SOLID_YIELD_BASIS!r} for a {state} substrate: grams of product per gram of dry "
            "substrate consumed. A molar yield on a solid polymer would need the molar mass of a repeat unit, which "
            "FungMod does not assume; the yield is always explicit and never inferred. In an enzyme network, a solid "
            "may instead state an amount of product per dry mass (for example mmol/g) to release a dissolved pool; "
            f"{basis!r} is not such an amount per mass.",
        )
        ok = False
    expected = _AMOUNT_BASIS[state]
    if amount_basis != expected:
        stated = "is blank" if not amount_basis else f"is {amount_basis!r}"
        context.add(
            file,
            line,
            "amount_basis",
            f"amount_basis {stated}, but a {state} substrate must state amount_basis {expected!r}: its amounts are "
            "dry mass per volume (for example g/L). No other basis (monomer equivalents, moles of repeat units) is "
            "supported in this version.",
        )
        ok = False
    return ok


def _physical_state_problem(state: str, *, what: str) -> str | None:
    """Why a physical state is not supported for a user-dataset substrate, or None when it is."""

    if state in SUBSTRATE_PHYSICAL_STATES:
        return None
    supported = " or ".join(SUBSTRATE_PHYSICAL_STATES)
    if state in _COMPOSITE_PHYSICAL_STATES:
        return (
            f"{what} has physical_state {state!r}, a composite material: its polymer fractions, their bonds and "
            "their accessibility would need a composition model, which user data does not support, so composite "
            f"substrates are refused. Supported states are {supported} (one polymer)."
        )
    return f"{what} has physical_state {state!r}; supported states are {supported}."


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
) -> tuple[str, str, str, tuple[str, ...], str] | None:
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
    problem = _physical_state_problem(record.physical_state, what=f"Registry substrate {record.record_id!r}")
    if problem is not None:
        context.add(file, line, "registry_substrate", problem)
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
    return record.record_id, record.name, record.substrate_class, tuple(record.bond_classes), record.physical_state


def _user_substrate(
    row: Mapping[str, str],
    *,
    file: str,
    line: int,
    context: _Context,
) -> tuple[str, str, str, tuple[str, ...], str] | None:
    name = _required_text(row, "name", file=file, line=line, context=context)
    substrate_class = _required_text(row, "substrate_class", file=file, line=line, context=context)
    if substrate_class is not None and not _CLASS_TOKEN_PATTERN.fullmatch(substrate_class):
        context.add(file, line, "substrate_class", "substrate_class must be lowercase snake_case.")
        substrate_class = None
    physical_state = _required_text(row, "physical_state", file=file, line=line, context=context)
    if physical_state is not None:
        problem = _physical_state_problem(physical_state, what=f"Substrate in row {line}")
        if problem is not None:
            context.add(file, line, "physical_state", problem)
            physical_state = None
    bonds = _class_tokens(row, "bond_classes", file=file, line=line, context=context)
    if name is None or substrate_class is None or physical_state is None or bonds is None:
        return None
    return "", name, substrate_class, bonds, physical_state


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
                _unsupported_quantity_text(quantity),
            )
            quantity = None
        strain_id = _reference(row, "strain_id", strains, "strains.csv", file=file, line=line, context=context)
        substrate_id = _reference(row, "substrate_id", substrates, "substrates.csv", file=file, line=line, context=context)
        condition_id = _reference(row, "condition_id", conditions, "conditions.csv", file=file, line=line, context=context)
        # Whether the row's substrate is a solid decides which quantities and units it may carry.
        solid = substrate_id is not None and substrates[substrate_id].is_solid
        if quantity is not None and substrate_id is not None:
            refusal = (_SOLID_REFUSED_QUANTITIES if solid else _SOLID_ONLY_QUANTITIES).get(quantity)
            if refusal is not None:
                state = substrates[substrate_id].physical_state
                context.add(file, line, "quantity", f"Substrate {substrate_id!r} is {state}: {refusal}")
                quantity = None
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
            message = _quantity_units_error(quantity, units, solid=solid)
            if message is not None:
                context.add(file, line, "units", message)
                units = None
        values = _kinetic_values(row, quantity=quantity, file=file, line=line, context=context)
        evidence_type = _required_text(row, "evidence_type", file=file, line=line, context=context)
        if evidence_type is not None and evidence_type not in EVIDENCE_TYPES:
            context.add(file, line, "evidence_type", f"evidence_type must be one of {', '.join(EVIDENCE_TYPES)}.")
            evidence_type = None
        if evidence_type == FITTED_EVIDENCE_TYPE and quantity is not None:
            if quantity not in FITTABLE_QUANTITIES:
                context.add(
                    file,
                    line,
                    "evidence_type",
                    f"evidence_type {FITTED_EVIDENCE_TYPE!r} is written by fit_user_dataset for "
                    f"{', '.join(FITTABLE_QUANTITIES)} only; {quantity} is not a fitted quantity.",
                )
                evidence_type = None
            elif values is not None and values[0] is None:
                context.add(
                    file,
                    line,
                    "value",
                    f"A {FITTED_EVIDENCE_TYPE!r} row holds the exact fitted value; a range is not a fit result.",
                )
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
        inhibitor_ok = _inhibitor_column_ok(row, quantity=quantity, file=file, line=line, context=context)
        source = _required_text(row, "source", file=file, line=line, context=context)
        sd = _optional_nonnegative(row, "sd", file=file, line=line, context=context)
        replicates = _optional_positive_int(row, "replicates", file=file, line=line, context=context)
        if (
            not activity_ok
            or not inhibitor_ok
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
                inhibitor=row.get(INHIBITOR_COLUMN, ""),
            )
        )
    return rows


def _inhibitor_column_ok(
    row: Mapping[str, str],
    *,
    quantity: str | None,
    file: str,
    line: int,
    context: _Context,
) -> bool:
    """Check the inhibitor column: required on ki rows (a pool id), refused on every other row."""

    text = row.get(INHIBITOR_COLUMN, "")
    if quantity != INHIBITION_CONSTANT_QUANTITY:
        if text and quantity is not None:
            context.add(file, line, INHIBITOR_COLUMN, f"{INHIBITOR_COLUMN} applies only to ki rows.")
            return False
        return True
    if not text:
        context.add(
            file,
            line,
            INHIBITOR_COLUMN,
            "ki rows must name their inhibitor: the substrate_id of a pool the enzyme network forms downstream of the "
            "row's substrate, or the network's final product as written in substrates.csv. FungMod does not guess "
            "which product inhibits.",
        )
        return False
    if not _IDENTIFIER_PATTERN.fullmatch(text):
        context.add(
            file,
            line,
            INHIBITOR_COLUMN,
            f"inhibitor {text!r} must be an identifier (letters, digits and single underscores), the id of a pool.",
        )
        return False
    return True


def _parse_culture(
    table: _Table,
    *,
    strains: Mapping[str, _Strain],
    classes: dict[str, _EnzymeClassInfo],
    strain_classes: Sequence[_StrainClass],
    substrates: Mapping[str, _Substrate],
    conditions: Mapping[str, _Condition],
    resolver: RegistryResolver,
    context: _Context,
) -> list[_CultureRow]:
    """Read culture.csv: one role of the culture of a strain on a solid substrate at a condition per row.

    A culture-level quantity leaves ``enzyme_class`` blank; a quantity of an
    enzyme pool names the pool's class, which the strain must declare. The
    substrate must be a ``solid_polymer`` on a dry-mass basis, because the
    culture closes one dry-mass balance over substrate, biomass and two
    ledgers. Units are checked with pint against the dimension of the role;
    pools stay a protein mass or an assay activity and are never converted.
    Which pool consumes the substrate, and the units of a case taken together,
    are checked in ``_validate_cultures``.
    """

    file = table.name
    declared = {(item.strain_id, item.class_key) for item in strain_classes}
    rows: list[_CultureRow] = []
    for line, row in table.rows:
        quantity = _required_text(row, "quantity", file=file, line=line, context=context)
        if quantity is not None and quantity not in CULTURE_QUANTITIES:
            context.add(file, line, "quantity", _unsupported_culture_quantity_text(quantity))
            quantity = None
        strain_id = _reference(row, "strain_id", strains, "strains.csv", file=file, line=line, context=context)
        substrate_id = _reference(row, "substrate_id", substrates, "substrates.csv", file=file, line=line, context=context)
        condition_id = _reference(row, "condition_id", conditions, "conditions.csv", file=file, line=line, context=context)
        if substrate_id is not None and not substrates[substrate_id].is_solid:
            substrate = substrates[substrate_id]
            context.add(
                file,
                line,
                "substrate_id",
                f"Substrate {substrate_id!r} is {substrate.physical_state} (substrates.csv row {substrate.row}); a "
                f"culture needs a {PHYSICAL_STATE_SOLID_POLYMER} substrate with amount_basis "
                f"{AMOUNT_BASIS_DRY_MASS!r}. The culture model closes one dry-mass balance over the substrate, the "
                "biomass and two closure ledgers in one mass unit, and the biomass yield is grams of biomass per gram "
                "of dry substrate; an amount of a dissolved substrate would need a molar mass, which FungMod does not "
                "assume.",
            )
            substrate_id = None
        class_text = row.get("enzyme_class", "")
        class_key: str | None = ""
        if quantity is not None and quantity in CULTURE_LEVEL_QUANTITIES:
            if class_text:
                context.add(
                    file,
                    line,
                    "enzyme_class",
                    f"{quantity} belongs to the culture as a whole; leave enzyme_class blank. Only the quantities of "
                    f"an enzyme pool ({', '.join((*CULTURE_CONSUMPTION_QUANTITIES, *CULTURE_POOL_QUANTITIES))}) "
                    "name the pool's class.",
                )
                class_key = None
        elif quantity is not None:
            if not class_text:
                context.add(
                    file,
                    line,
                    "enzyme_class",
                    f"{quantity} belongs to one enzyme pool of the culture; give the pool's enzyme class (a class "
                    "the strain declares in enzymes.csv or genomes.csv).",
                )
                class_key = None
            else:
                class_key = _resolve_class(
                    class_text, classes=classes, resolver=resolver, file=file, line=line, context=context
                )
                if strain_id is not None and class_key is not None and (strain_id, class_key) not in declared:
                    context.add(
                        file,
                        line,
                        "enzyme_class",
                        f"Strain {strain_id!r} does not declare enzyme class {class_key!r} in enzymes.csv or "
                        "genomes.csv; a culture's enzyme pools are classes the strain declares.",
                    )
                    class_key = None
        units = _required_text(row, "units", file=file, line=line, context=context)
        if units is not None and quantity is not None:
            message = _culture_units_error(quantity, units)
            if message is not None:
                context.add(file, line, "units", message)
                units = None
        values = _kinetic_values(row, quantity=None, file=file, line=line, context=context)
        if values is not None and quantity is not None:
            values = _culture_value_bounds(
                values, quantity=quantity, units=units, file=file, line=line, context=context
            )
        evidence_type = _required_text(row, "evidence_type", file=file, line=line, context=context)
        if evidence_type == FITTED_EVIDENCE_TYPE:
            context.add(
                file,
                line,
                "evidence_type",
                f"evidence_type {FITTED_EVIDENCE_TYPE!r} is written by fit_user_dataset to kinetics.csv only; it "
                "fits no culture constant. State the value's origin: one of "
                f"{', '.join(CULTURE_EVIDENCE_TYPES)}.",
            )
            evidence_type = None
        elif evidence_type is not None and evidence_type not in CULTURE_EVIDENCE_TYPES:
            context.add(
                file, line, "evidence_type", f"evidence_type must be one of {', '.join(CULTURE_EVIDENCE_TYPES)}."
            )
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
            or substrate_id is None
            or condition_id is None
            or class_key is None
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
            _CultureRow(
                row=line,
                strain_id=strain_id,
                substrate_id=substrate_id,
                condition_id=condition_id,
                quantity=quantity,
                class_key=class_key,
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


def _unsupported_culture_quantity_text(quantity: str) -> str:
    """Why a culture.csv quantity is refused: a kinetics.csv quantity, or unknown."""

    supported = (
        f"culture.csv quantities are {', '.join(CULTURE_LEVEL_QUANTITIES)} (the culture as a whole, enzyme_class "
        f"blank) and {', '.join((*CULTURE_CONSUMPTION_QUANTITIES, *CULTURE_POOL_QUANTITIES))} (one enzyme pool, "
        "enzyme_class given)."
    )
    if quantity in KINETIC_QUANTITIES:
        return (
            f"quantity {quantity!r} belongs to the enzyme-assay forms of kinetics.csv, not to a culture; {supported}"
        )
    return f"quantity {quantity!r} is not a culture quantity; {supported}"


def _culture_units_error(quantity: str, units: str) -> str | None:
    """Check the dimension of a culture.csv value with pint; pools stay a protein mass or an assay activity."""

    error = _unit_parse_error(units)
    if error is not None:
        return f"units {units!r} cannot be parsed: {error}"
    if quantity == "biomass_yield":
        if _unit_dimension_error(units, _DIMENSIONLESS_REFERENCE_UNITS) is None:
            return None
        return (
            f"biomass_yield units {units!r} must be dimensionless (write g/g or dimensionless): grams of biomass dry "
            "mass formed per gram of dry substrate consumed."
        )
    if quantity in _CULTURE_RATE_CONSTANT_QUANTITIES:
        if _unit_dimension_error(units, _RATE_CONSTANT_REFERENCE_UNITS) is None:
            return None
        return f"{quantity} units {units!r} must have the dimension 1/time (for example 1/h): it is a first-order loss rate."
    if quantity in _CULTURE_DRY_MASS_QUANTITIES:
        kind = _concentration_kind(units)
        if kind == "mass":
            return None
        if kind == "molar":
            return (
                f"{quantity} units {units!r} are a molar concentration, but a culture's substrate is a solid polymer "
                "on a dry-mass basis: give a dry mass per volume (for example g/L). A molar amount of a polymer would "
                "need the molar mass of a repeat unit, which FungMod does not assume."
            )
        return f"{quantity} units {units!r} must be a dry mass of the substrate per volume (for example g/L)."
    if quantity == "initial_biomass":
        if _concentration_kind(units) == "mass":
            return None
        return (
            f"initial_biomass units {units!r} must be a biomass dry mass per volume (for example g/L): the culture "
            "closes one dry-mass balance over the substrate, the biomass and two closure ledgers."
        )
    if quantity == "initial_enzyme_concentration":
        if _is_enzyme_amount_per(units, "liter"):
            return None
        if _concentration_kind(units) == "molar":
            return (
                f"initial_enzyme_concentration units {units!r} are a molar concentration; an enzyme pool of a "
                "culture is a protein mass per volume (for example mg/L) or an assay activity per volume (for example "
                "FPU/L), and FungMod does not convert between them or to moles."
            )
        return (
            f"initial_enzyme_concentration units {units!r} must be a protein mass per volume (for example mg/L) or "
            f"an assay activity per volume in one of the registry's assay units ({', '.join(_ENZYME_ASSAY_UNITS)}, "
            "for example FPU/L)."
        )
    if quantity == "hydrolysis_capacity":
        if units_are_compatible(units, _RATE_CONSTANT_REFERENCE_UNITS) or any(
            units_are_compatible(units, f"gram / second / {assay}") for assay in _ENZYME_ASSAY_UNITS
        ):
            return None
        return (
            f"hydrolysis_capacity units {units!r} must be a substrate dry mass per time per unit of the consuming "
            "pool: per protein mass (for example g/(mg h), which is 1/time) or per assay unit (for example "
            "g/(FPU h)), so that k_h x E is a dry mass per volume per time."
        )
    if quantity == "specific_production_rate":
        if units_are_compatible(units, _RATE_CONSTANT_REFERENCE_UNITS) or any(
            units_are_compatible(units, f"{assay} / gram / second") for assay in _ENZYME_ASSAY_UNITS
        ):
            return None
        return (
            f"specific_production_rate units {units!r} must be an enzyme amount per biomass dry mass per time: a "
            "protein mass (for example mg/(g h), which is 1/time) or an assay activity (for example FPU/(g h))."
        )
    return None


def _culture_value_bounds(
    values: tuple[float | None, float | None, float | None],
    *,
    quantity: str,
    units: str | None,
    file: str,
    line: int,
    context: _Context,
) -> tuple[float | None, float | None, float | None] | None:
    """Refuse a zero half-saturation constant or yield, and a biomass yield above one.

    The biomass yield is judged as a plain fraction: 400 mg/g is 0.4 g/g, so its
    bound is checked after converting the stated units with pint.
    """

    value, lower, upper = values
    smallest = value if value is not None else lower
    largest = value if value is not None else upper
    if quantity == "biomass_yield" and units is not None and largest is not None:
        largest = float(Q_(largest, units).to("dimensionless").magnitude)
    column = "value" if value is not None else "lower"
    if quantity in _CULTURE_POSITIVE_QUANTITIES and smallest is not None and smallest <= 0.0:
        context.add(file, line, column, f"{quantity} must be positive.")
        return None
    if quantity == "biomass_yield" and largest is not None and largest > 1.0:
        context.add(
            file,
            line,
            "value" if value is not None else "upper",
            "biomass_yield must not exceed 1 g/g: the consumed substrate not retained as biomass, 1 - Y, is booked "
            "to the closure ledger and cannot be negative.",
        )
        return None
    return values


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


def _parse_timecourses(
    table: _Table,
    *,
    strains: Mapping[str, _Strain],
    classes: dict[str, _EnzymeClassInfo],
    strain_classes: Sequence[_StrainClass],
    substrates: Mapping[str, _Substrate],
    conditions: Mapping[str, _Condition],
    kinetics: Sequence[_Kinetics],
    resolver: RegistryResolver,
    context: _Context,
    cultured: Mapping[tuple[str, str], int] | None = None,
) -> list[_TimecourseRow]:
    """Read timecourse.csv: substrate remaining or product formed over time in declared cases.

    Every reference must be declared, and the enzyme class must be declared for
    the strain and able to act on the substrate. Times are finite, zero or
    positive, in a time unit; values are finite concentrations in amount per
    volume, the kind of the case's state units (the mol/mol yield works on
    amounts, so a mass concentration would need a molar mass). ``sd`` is
    positive when given, in the row's units. One series (case and observable)
    uses one time unit and one value unit and lists each time once. A strain
    and substrate with a culture in ``culture.csv`` (``cultured``: the first
    culture row of each) have culture cases, whose time courses are refused.
    """

    file = table.name
    declared = {(item.strain_id, item.class_key) for item in strain_classes}
    cultured = cultured or {}
    case_rows: dict[tuple[str, str, str, str], _Kinetics] = {}
    for kinetic in kinetics:
        if kinetic.quantity in _CONCENTRATION_QUANTITIES:
            case_rows.setdefault(kinetic.case_key, kinetic)
    rows: list[_TimecourseRow] = []
    for line, row in table.rows:
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
                f"Strain {strain_id!r} does not declare enzyme class {class_key!r} in enzymes.csv or genomes.csv.",
            )
            class_key = None
        if class_key is not None and substrate_id is not None and _shared_bonds(classes[class_key], substrates[substrate_id]) is None:
            context.add(
                file,
                line,
                "substrate_id",
                f"Enzyme class {class_key!r} cannot act on substrate {substrate_id!r}, so no simulated case can "
                "produce this time course.",
            )
            substrate_id = None
        if substrate_id is not None and strain_id is not None and (strain_id, substrate_id) in cultured:
            context.add(
                file,
                line,
                "substrate_id",
                f"Strain {strain_id!r} has a culture on substrate {substrate_id!r} ({CULTURE_TABLE} row "
                f"{cultured[(strain_id, substrate_id)]}), so its cases on that substrate are culture cases: time "
                "courses of culture cases are not compared or fitted in this version (the comparison reads the "
                "substrate and the product of an enzyme-assay case; the biomass, enzyme pools and closure ledgers of "
                "a culture are not observables of the comparison, and no culture constant is fitted). Simulate the "
                "culture and compare it outside FungMod, or leave its rows out of timecourse.csv.",
            )
            substrate_id = None
        if substrate_id is not None and substrates[substrate_id].is_solid:
            context.add(
                file,
                line,
                "substrate_id",
                f"Substrate {substrate_id!r} is {substrates[substrate_id].physical_state}: time courses of solid "
                "substrates are not compared or fitted in this version (the comparison and the fit read amounts per "
                "volume with a mol/mol yield). Simulate the solid case and compare it outside FungMod, or leave its "
                "rows out of timecourse.csv.",
            )
            substrate_id = None
        observable = _required_text(row, "observable", file=file, line=line, context=context)
        if observable is not None and observable not in TIMECOURSE_OBSERVABLES:
            context.add(
                file,
                line,
                "observable",
                f"observable must be one of {', '.join(TIMECOURSE_OBSERVABLES)} (substrate remaining or product "
                "formed since time zero).",
            )
            observable = None
        time = _required_number(row, "time", file=file, line=line, context=context)
        if time is not None and time < 0.0:
            context.add(file, line, "time", "time must be zero or positive; time zero is the start of the assay.")
            time = None
        time_units = _required_text(row, "time_units", file=file, line=line, context=context)
        if time_units is not None and _unit_dimension_error(time_units, _TIME_REFERENCE_UNITS) is not None:
            context.add(
                file, line, "time_units", f"time_units {time_units!r} must be a time unit such as second, minute or hour."
            )
            time_units = None
        value = _required_number(row, "value", file=file, line=line, context=context)
        units = _required_text(row, "units", file=file, line=line, context=context)
        if units is not None:
            case_row = (
                None
                if strain_id is None or class_key is None or substrate_id is None or condition_id is None
                else case_rows.get((strain_id, class_key, substrate_id, condition_id))
            )
            problem = _timecourse_units_problem(units, case_row)
            if problem is not None:
                context.add(file, line, "units", problem)
                units = None
        sd: float | None = None
        sd_ok = True
        sd_text = row.get("sd", "")
        if sd_text:
            sd = _number(sd_text)
            if sd is None or sd <= 0.0:
                context.add(
                    file,
                    line,
                    "sd",
                    "sd must be a finite positive standard deviation in the row's units when given; it weights the "
                    "observation in a fit.",
                )
                sd_ok = False
        replicates = _optional_positive_int(row, "replicates", file=file, line=line, context=context)
        source = _required_text(row, "source", file=file, line=line, context=context)
        method = _required_text(row, "method", file=file, line=line, context=context)
        if (
            strain_id is None
            or class_key is None
            or substrate_id is None
            or condition_id is None
            or observable is None
            or time is None
            or time_units is None
            or value is None
            or units is None
            or not sd_ok
            or replicates is False
            or source is None
            or method is None
        ):
            continue
        rows.append(
            _TimecourseRow(
                row=line,
                strain_id=strain_id,
                class_key=class_key,
                substrate_id=substrate_id,
                condition_id=condition_id,
                observable=observable,
                time=time,
                time_units=time_units,
                value=value,
                units=units,
                sd=sd,
                replicates=replicates if isinstance(replicates, int) and not isinstance(replicates, bool) else None,
                source=source,
                method=method,
            )
        )
    by_series: dict[tuple[str, str, str, str, str], list[_TimecourseRow]] = {}
    for item in rows:
        by_series.setdefault(item.series_key, []).append(item)
    for (strain_id, class_key, substrate_id, condition_id, observable), items in by_series.items():
        where = (
            f"{observable} of strain {strain_id!r}, class {class_key!r}, substrate {substrate_id!r}, "
            f"condition {condition_id!r}"
        )
        first = items[0]
        seen: dict[float, int] = {}
        for item in items:
            for column, value, expected in (
                ("time_units", item.time_units, first.time_units),
                ("units", item.units, first.units),
            ):
                if value != expected:
                    context.add(
                        file,
                        item.row,
                        column,
                        f"Row {item.row} gives {where} in {column} {value!r} while row {first.row} uses "
                        f"{expected!r}; one series uses one time unit and one value unit.",
                    )
            if item.time in seen:
                context.add(
                    file,
                    item.row,
                    "time",
                    f"Rows {seen[item.time]} and {item.row} both give {where} at time {_number_text(item.time)} "
                    f"{item.time_units}; give each time once per series (report replicates as their mean with sd "
                    "and replicates).",
                )
            else:
                seen[item.time] = item.row
    return rows


def _timecourse_units_problem(units: str, case_row: _Kinetics | None) -> str | None:
    """Refuse time-course units that are not an amount per volume, the kind of the case's states."""

    error = _unit_parse_error(units)
    if error is not None:
        return f"units {units!r} cannot be parsed: {error}"
    kind = _concentration_kind(units)
    case_text = (
        ""
        if case_row is None
        else f" (the case states {case_row.quantity} in {case_row.units!r}, kinetics.csv row {case_row.row})"
    )
    if kind is None:
        return (
            f"units {units!r} are not a concentration. A time course measures substrate remaining or product "
            f"formed as an amount per volume, the units of the case's states{case_text}, for example uM or mM."
        )
    if kind == "mass":
        return (
            f"units {units!r} are a mass concentration, but the case's states are amounts per volume{case_text} "
            f"and the product yield is {_YIELD_BASIS}; comparing a mass concentration would need a molar mass, "
            "which FungMod does not assume."
        )
    return None


def _timecourse_series(parsed: _Parsed, *, dataset_id: str) -> Mapping[str, tuple[UserTimecourse, ...]]:
    """Group time-course rows into series keyed by the generated case id, observables in a fixed order."""

    grouped: dict[tuple[str, str, str, str, str], list[_TimecourseRow]] = {}
    for item in parsed.timecourses:
        grouped.setdefault(item.series_key, []).append(item)
    by_case: dict[str, list[UserTimecourse]] = {}
    for key, items in grouped.items():
        strain_id, class_key, substrate_id, condition_id, observable = key
        substrate = parsed.substrates[substrate_id]
        ordered = sorted(items, key=lambda item: item.time)
        case_id = "__".join((dataset_id, strain_id, class_key, substrate_id, condition_id))
        by_case.setdefault(case_id, []).append(
            UserTimecourse(
                case_id=case_id,
                strain_id=strain_id,
                class_key=class_key,
                substrate_id=substrate_id,
                condition_id=condition_id,
                fungus_id="__".join((dataset_id, strain_id)),
                enzyme_class_id="__".join((dataset_id, class_key)),
                substrate_record_id=substrate.registry_id or "__".join((dataset_id, substrate_id)),
                environment_id="__".join((dataset_id, condition_id)),
                observable=observable,
                time_units=ordered[0].time_units,
                units=ordered[0].units,
                points=tuple(
                    TimecoursePoint(
                        row=item.row,
                        time=item.time,
                        value=item.value,
                        sd=item.sd,
                        replicates=item.replicates,
                        source=item.source,
                        method=item.method,
                    )
                    for item in ordered
                ),
            )
        )
    return MappingProxyType(
        {
            case_id: tuple(sorted(series, key=lambda item: TIMECOURSE_OBSERVABLES.index(item.observable)))
            for case_id, series in by_case.items()
        }
    )


def _validate_fit_block(
    parsed: _Parsed,
    manifest: Mapping[str, Any] | None,
    *,
    directory: Path,
    context: _Context,
) -> dict[str, bytes]:
    """Check the manifest's fit block against the ``fitted`` kinetics rows; return the fit report's bytes.

    A ``fitted`` row is accepted only when the manifest carries the block that
    ``fit_user_dataset`` writes (method, objective, error model, input dataset
    digest, data rows, bounds and identifiability per quantity) and the block
    lists that row's case, condition, quantity, value and units; every listed
    value must have its row. The fit report file named by the block must exist
    beside the manifest with the recorded SHA-256; its bytes enter the dataset
    digest.
    """

    fitted = [row for row in parsed.kinetics if row.evidence_type == FITTED_EVIDENCE_TYPE]
    block = None if manifest is None else manifest.get("fit")
    if not isinstance(block, Mapping):
        if manifest is not None:
            for row in fitted:
                context.add(
                    "kinetics.csv",
                    row.row,
                    "evidence_type",
                    f"evidence_type {FITTED_EVIDENCE_TYPE!r} is reserved for rows written by fit_user_dataset; the "
                    "manifest has no fit block describing the fit (method, objective, data rows, bounds and "
                    "identifiability), so the value cannot be traced to a fit.",
                )
        return {}
    file = USER_DATASET_MANIFEST
    count = len(context.issues)

    def add(column: str, message: str) -> None:
        context.add(file, None, f"fit.{column}" if column else "fit", message)

    keys = {str(key) for key in block}
    unknown = sorted(keys.difference(_FIT_BLOCK_FIELDS))
    if unknown:
        add("", f"Unsupported fit field(s): {', '.join(unknown)}.")
    missing = sorted(_FIT_BLOCK_FIELDS.difference(keys))
    if missing:
        add("", f"fit is missing {', '.join(missing)}; the block written by fit_user_dataset must stay complete.")
        return {}
    if block["kind"] != FIT_BLOCK_KIND:
        add("kind", f"kind must be {FIT_BLOCK_KIND!r}.")
    for key in ("method", "objective", "input_dataset_id", "claim_boundary"):
        if not _is_text(block[key]):
            add(key, f"{key} must be nonblank text.")
    if block["error_model"] not in FIT_ERROR_MODELS:
        add("error_model", f"error_model must be one of {', '.join(FIT_ERROR_MODELS)}.")
    if not _is_sha256(block["input_dataset_digest"]):
        add("input_dataset_digest", "input_dataset_digest must be the SHA-256 digest of the fitted input dataset.")
    allow_unidentified = block["allow_unidentified"]
    if not isinstance(allow_unidentified, bool):
        add("allow_unidentified", "allow_unidentified must be true or false.")
    case = block["case"]
    case_key: tuple[str, str, str] | None = None
    if (
        not isinstance(case, Mapping)
        or set(map(str, case)) != {"strain_id", "enzyme_class", "substrate_id"}
        or not all(_is_text(case[key]) for key in ("strain_id", "enzyme_class", "substrate_id"))
    ):
        add("case", "case must name strain_id, enzyme_class and substrate_id.")
    else:
        case_key = (str(case["strain_id"]), str(case["enzyme_class"]), str(case["substrate_id"]))
    conditions = block["conditions"]
    if (
        not isinstance(conditions, list)
        or not conditions
        or not all(isinstance(item, str) and item in parsed.conditions for item in conditions)
    ):
        add("conditions", "conditions must list the condition_ids of conditions.csv the fit used.")
        conditions = []
    timecourse_rows = block["timecourse_rows"]
    known_rows = {item.row for item in parsed.timecourses}
    if (
        not isinstance(timecourse_rows, list)
        or not timecourse_rows
        or not all(isinstance(item, int) and not isinstance(item, bool) and item in known_rows for item in timecourse_rows)
    ):
        add("timecourse_rows", f"timecourse_rows must list the {TIMECOURSE_TABLE} rows the fit used.")
    entries: dict[str, Mapping[str, Any]] = {}
    quantities = block["quantities"]
    if not isinstance(quantities, list) or not quantities:
        add("quantities", "quantities must list each fitted quantity.")
        quantities = []
    for entry in quantities:
        problem = _fit_entry_problem(entry, allow_unidentified=allow_unidentified is True)
        if problem is not None:
            add("quantities", problem)
            continue
        assert isinstance(entry, Mapping)
        if entry["quantity"] in entries:
            add("quantities", f"quantity {entry['quantity']!r} is listed twice.")
            continue
        entries[str(entry["quantity"])] = entry
    report_bytes = _fit_report_bytes(block, directory=directory, add=add)
    if len(context.issues) > count or case_key is None:
        return {}
    expected = {(condition, quantity): entry for condition in conditions for quantity, entry in entries.items()}
    matched: set[tuple[str, str]] = set()
    for row in fitted:
        key = (row.condition_id, row.quantity)
        entry = expected.get(key)
        if (row.strain_id, row.class_key, row.substrate_id) != case_key or entry is None:
            context.add(
                "kinetics.csv",
                row.row,
                "evidence_type",
                f"This {FITTED_EVIDENCE_TYPE!r} row ({row.quantity} at condition {row.condition_id!r}) is not "
                "described by the manifest's fit block.",
            )
            continue
        if row.value != float(entry["value"]) or row.units != entry["units"]:
            context.add(
                "kinetics.csv",
                row.row,
                "value",
                f"This {FITTED_EVIDENCE_TYPE!r} row gives {row.quantity} = {row.value!r} {row.units} but the fit "
                f"block records {entry['value']!r} {entry['units']}; a fitted value is not edited by hand.",
            )
        matched.add(key)
    for condition, quantity in sorted(set(expected).difference(matched)):
        add(
            "quantities",
            f"The fit block lists {quantity} at condition {condition!r} but kinetics.csv has no "
            f"{FITTED_EVIDENCE_TYPE!r} row for it.",
        )
    return report_bytes


def _fit_entry_problem(entry: Any, *, allow_unidentified: bool) -> str | None:
    if not isinstance(entry, Mapping) or {str(key) for key in entry} != _FIT_QUANTITY_FIELDS:
        return f"each quantities entry must give exactly {', '.join(sorted(_FIT_QUANTITY_FIELDS))}."
    if entry["quantity"] not in FITTABLE_QUANTITIES:
        return f"quantity must be one of {', '.join(FITTABLE_QUANTITIES)}."
    for key in ("value", "initial"):
        value = entry[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0.0:
            return f"{entry['quantity']}: {key} must be a finite positive number."
    if not _is_text(entry["units"]) or _quantity_units_error(str(entry["quantity"]), str(entry["units"])) is not None:
        return f"{entry['quantity']}: units must be valid units for the quantity."
    if not _is_number_pair(entry["bounds"], positive=True):
        return f"{entry['quantity']}: bounds must be [lower, upper] with 0 < lower < upper."
    if entry["interval"] is not None and not _is_number_pair(entry["interval"], positive=True):
        return f"{entry['quantity']}: interval must be [lower, upper] or null."
    if entry["identifiability"] not in FIT_IDENTIFIABILITY_CLASSES:
        return f"{entry['quantity']}: identifiability must be one of {', '.join(FIT_IDENTIFIABILITY_CLASSES)}."
    if not _is_text(entry["identifiability_method"]):
        return f"{entry['quantity']}: identifiability_method must be nonblank text."
    if entry["identifiability"] != FIT_IDENTIFIED and not allow_unidentified:
        return (
            f"{entry['quantity']} is {entry['identifiability']}, but allow_unidentified is false; fit_user_dataset "
            "writes an unidentified value only when allow_unidentified is true."
        )
    return None


def _fit_report_bytes(block: Mapping[str, Any], *, directory: Path, add: Any) -> dict[str, bytes]:
    name = block["report_file"]
    if (
        not isinstance(name, str)
        or not name
        or "/" in name
        or "\\" in name
        or name in {USER_DATASET_MANIFEST, *_TABLE_COLUMNS}
        or name.lower().endswith(".csv")
    ):
        add("report_file", "report_file must name the fit report file beside the manifest, such as fit_report.json.")
        return {}
    path = directory / name
    if not path.is_file():
        add("report_file", f"The fit report {name!r} named by the fit block is missing from the dataset directory.")
        return {}
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != block["report_sha256"]:
        add(
            "report_sha256",
            f"The fit report {name!r} does not match report_sha256; the report and the fitted rows must stay as "
            "fit_user_dataset wrote them.",
        )
        return {}
    return {name: data}


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _is_number_pair(value: Any, *, positive: bool) -> bool:
    if not isinstance(value, list) or len(value) != 2:
        return False
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) for item in value):
        return False
    lower, upper = float(value[0]), float(value[1])
    return lower < upper and (lower > 0.0 or not positive)


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
        if quantity in _POSITIVE_QUANTITIES and parsed["value"] <= 0.0:
            context.add(file, line, "value", f"{quantity} must be positive.")
            return None
        if quantity in _PH_RANGE_QUANTITIES and parsed["value"] > _PH_SCALE[1]:
            context.add(file, line, "value", f"{quantity} {raw['value']} is outside pH 0 to 14.")
            return None
        return parsed["value"], None, None
    if quantity in _PH_RANGE_QUANTITIES:
        context.add(
            file,
            line,
            "lower",
            f"{quantity} bounds the pH range over which the pH-ionization law was fitted; give it as an exact value, "
            "not a range.",
        )
        return None
    lower, upper = parsed["lower"], parsed["upper"]
    if not lower < upper:
        context.add(file, line, "upper", "lower must be smaller than upper.")
        return None
    if quantity in _POSITIVE_QUANTITIES and lower <= 0.0:
        context.add(file, line, "lower", f"{quantity} must be positive.")
        return None
    return None, lower, upper


def _unsupported_quantity_text(quantity: str) -> str:
    """Why a kinetics.csv quantity is refused: a retired name, an input of an unbound law, or unknown."""

    if quantity in _RETIRED_QUANTITY_HINTS:
        return _RETIRED_QUANTITY_HINTS[quantity]
    if quantity in _SURFACE_LAW_QUANTITIES:
        return f"quantity {quantity!r} ({_SURFACE_LAW_QUANTITIES[quantity]}) is refused: {_SURFACE_LAW_LIMIT}"
    return f"quantity {quantity!r} is not one of {', '.join(KINETIC_QUANTITIES)}."


def _quantity_units_error(quantity: str, units: str, *, solid: bool = False) -> str | None:
    """Check the dimension of a kinetics.csv value; ``solid`` selects the dry-mass rules of a solid substrate."""

    error = _unit_parse_error(units)
    if error is not None:
        return f"units {units!r} cannot be parsed: {error}"
    if quantity == "reactivity_exponent":
        if _unit_dimension_error(units, _DIMENSIONLESS_REFERENCE_UNITS) is not None:
            return (
                f"reactivity_exponent units {units!r} must be dimensionless (write dimensionless): it is the exponent "
                "n of the factor (S / S0)^n."
            )
        return None
    if quantity == "enzyme_dose":
        if _is_enzyme_amount_per(units, "gram"):
            return None
        return (
            f"enzyme_dose units {units!r} must be an enzyme amount per dry substrate mass: a protein mass per "
            "substrate mass (for example mg/g) or an assay activity per substrate mass (for example FPU/g)."
        )
    if quantity == INACTIVATION_RATE_QUANTITY:
        # The same rule on a dissolved and a solid substrate: a first-order constant of the enzyme state.
        if _unit_dimension_error(units, _RATE_CONSTANT_REFERENCE_UNITS) is not None:
            return (
                f"inactivation_rate units {units!r} must have the dimension 1/time (for example 1/h or 1/min): it is "
                "the first-order constant k_d of dE/dt = -k_d E. A half-life is not a rate constant; FungMod does not "
                "convert one (k_d = ln 2 / t_half is yours to state)."
            )
        return None
    if solid:
        return _solid_quantity_units_error(quantity, units)
    if quantity == INHIBITION_CONSTANT_QUANTITY:
        kind = _concentration_kind(units)
        if kind == "molar":
            return None
        if kind == "mass":
            return (
                f"ki units {units!r} are a mass concentration; the pools of a dissolved network are amounts per "
                f"volume with {_YIELD_BASIS} yields, so Ki must be an amount of the inhibiting product per volume "
                "(for example mM or uM). FungMod does not convert between molar and mass concentrations."
            )
        return (
            f"ki units {units!r} must be an amount of the inhibiting product per volume (for example mM or uM), "
            "the unit basis of the product pool."
        )
    if quantity in _RATE_CONSTANT_QUANTITIES:
        if _unit_dimension_error(units, _RATE_CONSTANT_REFERENCE_UNITS) is not None:
            return f"{quantity} units {units!r} must have the dimension 1/time (for example 1/s or 1/min)."
        return None
    if quantity in _DIMENSIONLESS_QUANTITIES:
        if _unit_dimension_error(units, _DIMENSIONLESS_REFERENCE_UNITS) is not None:
            return f"{quantity} units {units!r} must be dimensionless (write dimensionless); a pK or pH has no unit."
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


def _is_enzyme_amount_per(units: str, denominator: str) -> bool:
    """Whether ``units`` are a protein mass or an assay activity per ``denominator`` (never a molar amount)."""

    return units_are_compatible(units, f"gram / {denominator}") or any(
        units_are_compatible(units, f"{assay} / {denominator}") for assay in _ENZYME_ASSAY_UNITS
    )


def _solid_quantity_units_error(quantity: str, units: str) -> str | None:
    """The dimension rules of a case on a solid substrate stated on a dry-mass basis.

    Substrate-side amounts (``km``, ``substrate_initial_concentration``) are dry
    mass per volume and ``vmax`` a dry mass per volume per time; a molar amount
    of a solid polymer would need the molar mass of a repeat unit, which FungMod
    does not assume. The enzyme is a protein mass or an assay activity per
    volume. ``kcat`` is a substrate mass per time per enzyme amount: with a
    protein-mass enzyme that is 1/time (gram per gram per time), with an assay
    activity a mass per time per assay unit. Whether ``kcat`` fits the case's
    own enzyme and substrate units is checked per case.
    """

    if quantity in {"km", "substrate_initial_concentration"}:
        kind = _concentration_kind(units)
        if kind == "mass":
            return None
        if kind == "molar":
            return (
                f"{quantity} units {units!r} are a molar concentration, but the substrate is a solid polymer stated "
                "on a dry-mass basis: give a dry mass per volume (for example g/L). A molar amount of a polymer would "
                "need the molar mass of a repeat unit, which FungMod does not assume."
            )
        return f"{quantity} units {units!r} must be a dry mass of the solid substrate per volume (for example g/L)."
    if quantity == "enzyme_concentration":
        if _is_enzyme_amount_per(units, "liter"):
            return None
        if _concentration_kind(units) == "molar":
            return (
                f"enzyme_concentration units {units!r} are a molar concentration; on a solid substrate the enzyme "
                "is a protein mass per volume (for example mg/L) or an assay activity per volume (for example FPU/L), "
                "and kcat carries the conversion to substrate mass."
            )
        return (
            f"enzyme_concentration units {units!r} must be a protein mass per volume (for example mg/L) or an assay "
            f"activity per volume in one of the registry's assay units ({', '.join(_ENZYME_ASSAY_UNITS)}, for "
            "example FPU/L)."
        )
    if quantity == "kcat":
        if units_are_compatible(units, _RATE_CONSTANT_REFERENCE_UNITS) or any(
            units_are_compatible(units, f"gram / second / {assay}") for assay in _ENZYME_ASSAY_UNITS
        ):
            return None
        return (
            f"kcat units {units!r} must be a substrate mass per time per enzyme amount on a solid substrate: per "
            "protein mass (for example g/(mg h), which is 1/time) or per assay unit (for example g/(FPU h)), so that "
            "kcat x E is a dry mass per volume per time."
        )
    if quantity == "vmax":
        if units_are_compatible(units, _MASS_RATE_REFERENCE_UNITS):
            return None
        if units_are_compatible(units, _MOLAR_RATE_REFERENCE_UNITS):
            return (
                f"vmax units {units!r} are an amount per volume per time, but the substrate is a solid polymer "
                "stated on a dry-mass basis: give a dry mass per volume per time (for example g/L/h)."
            )
        return (
            f"vmax units {units!r} must be a dry mass of the solid substrate per volume per time (for example g/L/h)."
        )
    # Every other quantity is refused on a solid substrate before its units are read.
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
        if parsed.substrates[case_key[2]].is_solid:
            # A solid case states dry masses; its units were checked per row and are checked per case below.
            continue
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
    _validate_cultures(parsed, context)
    _validate_rate_forms(parsed, context)
    _validate_solid_cases(parsed, context)
    _validate_ph_ionization(parsed, context)
    _validate_responses(parsed, context)
    _validate_inactivation(parsed, context)
    _validate_networks(parsed, context)
    _validate_pairs(parsed, context)


def _validate_cultures(parsed: _Parsed, context: _Context) -> None:
    """Find each culture's consuming pools, build the culture models and refuse what they cannot run.

    A culture is the culture.csv rows of one strain on one substrate. Its
    enzyme pools are the classes its rows name; every one whose class acts on
    the substrate (at least one) consumes it, in parallel with the others
    (CULTURE-002: their rates add, and every consumed gram feeds growth through
    the one yield). Cultures of one substrate whose consuming pools overlap are
    one culture model (``parsed.culture_pairs``, keyed by its first consuming
    class) with the pools every such culture names, and every strain that
    declares one of its consuming classes runs it on that substrate, so such a
    strain must declare every pool and no other class that acts on the
    substrate (FungMod builds one model per strain, substrate and condition and
    does not choose between a culture and an enzyme assay). A culture class runs
    the culture form on every substrate it acts on (a class runs one process
    law), so kinetics.csv rows of a culture class are refused, and so is a
    dissolved substrate it acts on; another solid it acts on becomes a culture
    of gaps with the consuming classes of its model that act there.
    kinetics.csv rows of a strain and substrate with a culture, and
    responses.csv rows of a culture, are refused and left out of the later
    checks. The units of each case are checked together with pint.
    """

    if not parsed.culture_rows:
        return
    file = CULTURE_TABLE
    grouped: dict[tuple[str, str, str, str, str], list[_CultureRow]] = {}
    for row in parsed.culture_rows:
        grouped.setdefault((row.strain_id, row.substrate_id, row.condition_id, row.quantity, row.class_key), []).append(
            row
        )
    for key, rows in grouped.items():
        if len(rows) < 2:
            continue
        pool = f" of enzyme pool {key[4]!r}" if key[4] else ""
        for row in rows[1:]:
            context.add(
                file,
                row.row,
                "quantity",
                f"Rows {', '.join(str(item.row) for item in rows)} give {key[3]}{pool} for strain {key[0]!r}, "
                f"substrate {key[1]!r}, condition {key[2]!r}: duplicate or conflicting rows for one role.",
            )
    by_culture: dict[tuple[str, str], list[_CultureRow]] = {}
    for row in parsed.culture_rows:
        by_culture.setdefault(row.culture_key, []).append(row)
    # The valid cultures in culture.csv order: (strain, substrate), the consuming pools, every pool named.
    cultures: list[tuple[tuple[str, str], list[str], dict[str, int]]] = []
    for (strain_id, substrate_id), rows in by_culture.items():
        substrate = parsed.substrates[substrate_id]
        named: dict[str, int] = {}
        for row in rows:
            if row.class_key:
                named.setdefault(row.class_key, row.row)
        acting = [class_key for class_key in named if _shared_bonds(parsed.classes[class_key], substrate) is not None]
        where = f"strain {strain_id!r} on substrate {substrate_id!r}"
        if not acting:
            context.add(
                file,
                rows[0].row,
                "enzyme_class",
                f"The culture of {where} ({_rows_text(rows)}) names no enzyme pool whose class acts on the substrate "
                f"(pools named: {', '.join(repr(item) for item in named) or 'none'}). A culture consumes its "
                "substrate through at least one enzyme pool: give that pool's rows (for example its "
                f"initial_enzyme_concentration) with a class that acts on {substrate_id!r} (substrate class "
                f"{substrate.substrate_class!r}, bond classes {list(substrate.bond_classes)}).",
            )
            continue
        consumers_text = (
            f"the pool that consumes the substrate, {acting[0]!r} in the culture of {where};"
            if len(acting) == 1
            else f"a pool that consumes the substrate ({', '.join(repr(item) for item in acting)} in the culture of "
            f"{where});"
        )
        for row in rows:
            if row.quantity in CULTURE_CONSUMPTION_QUANTITIES and row.class_key not in acting:
                context.add(
                    file,
                    row.row,
                    "enzyme_class",
                    f"{row.quantity} belongs to {consumers_text} pool {row.class_key!r} does not act on "
                    f"{substrate_id!r} and is produced and lost only.",
                )
        cultures.append(((strain_id, substrate_id), acting, named))
    # Several pools acting on the substrate consume it in parallel (CULTURE-002): their rates add, and every consumed
    # gram feeds growth through the culture's one yield. Cultures of one substrate whose consuming pools overlap are
    # one culture model, because every strain that declares a consuming class runs that class's model.
    parent: dict[tuple[str, str], tuple[str, str]] = {}

    def root(node: tuple[str, str]) -> tuple[str, str]:
        while parent[node] != node:
            node = parent[node]
        return node

    for (_strain_id, substrate_id), acting, _named in cultures:
        nodes = [(substrate_id, class_key) for class_key in acting]
        for node in nodes:
            parent.setdefault(node, node)
        for node in nodes[1:]:
            first, other = root(nodes[0]), root(node)
            if first != other:
                parent[other] = first
    models: dict[tuple[str, str], tuple[list[str], dict[str, int | None]]] = {}
    model_of: dict[tuple[str, str], tuple[str, str]] = {}
    for key, acting, named in cultures:
        model_key = root((key[1], acting[0]))
        consumers, pools = models.setdefault(model_key, ([], {}))
        for class_key in acting:
            if class_key not in consumers:
                consumers.append(class_key)
            pools.setdefault(class_key, named[class_key])
        for class_key, line in named.items():
            pools.setdefault(class_key, line)
        model_of[key] = model_key
    pair_pools: dict[tuple[str, str], dict[str, int | None]] = {}
    pair_consumers: dict[tuple[str, str], list[str]] = {}
    for (substrate_id, _class_key), (consumers, pools) in models.items():
        pair_pools[(consumers[0], substrate_id)] = pools
        pair_consumers[(consumers[0], substrate_id)] = consumers
    for key, model_key in model_of.items():
        parsed.cultured[key] = models[model_key][0][0]
    consumer_pairs = {(class_key, pair[1]) for pair, consumers in pair_consumers.items() for class_key in consumers}
    culture_classes = {class_key for consumers in pair_consumers.values() for class_key in consumers}
    culture_rows_text = {
        class_key: _rows_text(
            [
                row
                for row in parsed.culture_rows
                if row.culture_key in model_of and class_key in models[model_of[row.culture_key]][0]
            ]
        )
        for class_key in culture_classes
    }
    kept: list[_Kinetics] = []
    for row in parsed.kinetics:
        consuming = parsed.cultured.get((row.strain_id, row.substrate_id))
        if row.quantity == INACTIVATION_RATE_QUANTITY and (
            consuming is not None
            or (row.class_key, row.substrate_id) in consumer_pairs
            or row.class_key in culture_classes
        ):
            if consuming is not None:
                what = (
                    f"strain {row.strain_id!r} has a culture on substrate {row.substrate_id!r} ({file} "
                    f"{_rows_text(by_culture[(row.strain_id, row.substrate_id)])})"
                )
            else:
                what = f"enzyme class {row.class_key!r} runs the culture form ({file} {culture_rows_text[row.class_key]})"
            context.add("kinetics.csv", row.row, "quantity", _culture_inactivation_refusal(what))
        elif consuming is not None:
            culture = by_culture[(row.strain_id, row.substrate_id)]
            context.add(
                "kinetics.csv",
                row.row,
                "substrate_id",
                f"Strain {row.strain_id!r} has a culture on substrate {row.substrate_id!r} ({file} "
                f"{_rows_text(culture)}), and this row gives {row.quantity} of an enzyme-assay case of the same strain "
                "and substrate. The culture form models the strain growing on the substrate and secreting its enzyme "
                "pools; the enzyme-assay forms model an enzyme at a stated concentration. FungMod builds one model per "
                "strain, substrate and condition and does not choose between them, so one dataset uses one of them "
                "for a strain and substrate: keep the assay kinetics in a separate dataset.",
            )
        elif (row.class_key, row.substrate_id) in consumer_pairs:
            context.add(
                "kinetics.csv",
                row.row,
                "enzyme_class",
                f"Enzyme class {row.class_key!r} on substrate {row.substrate_id!r} uses the culture form ({file} "
                f"{culture_rows_text[row.class_key]}), and this row gives {row.quantity} of an enzyme-assay form. All "
                "strains and conditions of one enzyme class and substrate share one generated process (FungMod selects "
                "a process by enzyme class and substrate class), so strain "
                f"{row.strain_id!r}'s cases on {row.substrate_id!r} are culture cases; give its culture in "
                f"{file}, or keep the assay kinetics in a separate dataset.",
            )
        elif row.class_key in culture_classes:
            context.add(
                "kinetics.csv",
                row.row,
                "enzyme_class",
                f"Enzyme class {row.class_key!r} consumes a substrate in a culture ({file} "
                f"{culture_rows_text[row.class_key]}) and this row gives {row.quantity} of an enzyme-assay form on "
                f"substrate {row.substrate_id!r}. The generated enzyme class lists the process law it runs, and "
                "preflight looks for a compatibility of that law on each substrate of the class, so a class runs the "
                "culture form on all of its substrates or on none; keep the assay kinetics in a separate dataset.",
            )
        else:
            kept.append(row)
    parsed.kinetics[:] = kept
    # Consuming classes of one started model stay together on another substrate they act on.
    linked = {class_key: tuple(consumers) for consumers in pair_consumers.values() for class_key in consumers}
    gap_models: dict[tuple[str, tuple[str, ...]], tuple[str, str]] = {}
    for class_key in sorted(culture_classes):
        info = parsed.classes[class_key]
        for substrate in parsed.substrates.values():
            pair = (class_key, substrate.substrate_id)
            if pair in consumer_pairs or _shared_bonds(info, substrate) is None:
                continue
            if not substrate.is_solid:
                context.add(
                    "substrates.csv",
                    substrate.row,
                    "physical_state",
                    f"Enzyme class {class_key!r} runs the culture form ({file} {culture_rows_text[class_key]}) and "
                    f"acts on the {substrate.physical_state} substrate {substrate.substrate_id!r}. A class runs one "
                    "process law on all of its substrates, and a culture needs a solid_polymer substrate on a dry-mass "
                    "basis; leave this substrate out of the dataset, or give the culture in a separate dataset.",
                )
                continue
            # A substrate the class acts on without culture rows takes the culture form with its consuming pools only
            # (the classes of the class's culture model that act on it); its roles are explicit gaps.
            group = (substrate.substrate_id, linked[class_key])
            lead = gap_models.get(group)
            if lead is None:
                gap_models[group] = pair
                pair_pools[pair] = {class_key: None}
                pair_consumers[pair] = [class_key]
            else:
                pair_pools[lead][class_key] = None
                pair_consumers[lead].append(class_key)
    for pair, pools in pair_pools.items():
        consumers = tuple(pair_consumers[pair])
        parsed.culture_pairs[pair] = _CulturePair(
            class_key=pair[0],
            substrate_id=pair[1],
            pools=tuple(pools),
            pool_rows=MappingProxyType(dict(pools)),
            consumers=consumers if len(consumers) > 1 else (),
        )
    parsed.culture_classes.update(culture_classes)
    declared_by_strain: dict[str, dict[str, _StrainClass]] = {}
    for item in parsed.strain_classes:
        declared_by_strain.setdefault(item.strain_id, {})[item.class_key] = item
    for pair, culture in parsed.culture_pairs.items():
        substrate = parsed.substrates[pair[1]]
        running: dict[str, _StrainClass] = {}
        for item in parsed.strain_classes:
            # Every strain that declares a consuming class runs the model, through the first one it declares.
            if item.class_key in culture.consuming_pools:
                running.setdefault(item.strain_id, item)
        for item in running.values():
            declared = declared_by_strain[item.strain_id]
            for pool, pool_row in culture.pool_rows.items():
                if pool not in declared:
                    context.add(
                        file,
                        pool_row,
                        "enzyme_class",
                        f"Enzyme pool {pool!r} is part of the culture model of class {item.class_key!r} on substrate "
                        f"{pair[1]!r}, which every strain that declares {item.class_key!r} runs on that substrate; "
                        f"strain {item.strain_id!r} declares {item.class_key!r} ({item.file} row {item.row}) but not "
                        f"{pool!r}. Declare {pool!r} for that strain (its rows then become explicit gaps until "
                        "measured), or give that strain's culture in a separate dataset.",
                    )
            for other_key, other in declared.items():
                if other_key in culture.consuming_pools or _shared_bonds(parsed.classes[other_key], substrate) is None:
                    continue
                context.add(
                    other.file,
                    other.row,
                    "enzyme_class",
                    f"Strain {item.strain_id!r} declares {other_key!r}, which acts on substrate {pair[1]!r}, and "
                    f"{item.class_key!r}, whose cases on that substrate run the culture model ({file}). FungMod builds "
                    "one model per strain, substrate and condition and does not choose between a culture and an "
                    "enzyme-assay case; in a culture the consuming pools are the strain's only classes acting on the "
                    f"substrate. To make {other_key!r} a consuming pool of the culture, give its rows in {file} (the "
                    "consuming pools act in parallel); otherwise leave the other class out of this dataset (a class "
                    "from a genome annotation: run the culture in a dataset without genomes.csv).",
                )
    kept_responses: list[_Response] = []
    for response in parsed.responses:
        pair = (response.class_key, response.substrate_id)
        if (
            pair in parsed.culture_pairs
            or response.class_key in culture_classes
            or (response.strain_id, response.substrate_id) in parsed.cultured
        ):
            context.add(
                "responses.csv",
                response.row,
                "law",
                f"Strain {response.strain_id!r}, class {response.class_key!r} and substrate {response.substrate_id!r} "
                "belong to a culture, and response laws are not bound to culture cases in this version: the culture "
                "model applies no temperature or pH law (the condition's temperature and pH are metadata), so a "
                "culture's constants hold at the condition of their rows only."
                + (
                    f" {INACTIVATION_LAW} scales the inactivation_rate of an enzyme-assay case; a culture pool is lost "
                    "at its own enzyme_loss_rate in culture.csv, which no temperature law rescales."
                    if response.law == INACTIVATION_LAW
                    else ""
                ),
            )
        else:
            kept_responses.append(response)
    parsed.responses[:] = kept_responses
    _validate_culture_case_units(parsed, context)
    for pair, culture in parsed.culture_pairs.items():
        substrate = parsed.substrates[pair[1]]
        names = list(_culture_state_names(culture, substrate).values())
        if len(set(names)) != len(names):
            context.add(
                "substrates.csv",
                substrate.row,
                "substrate_id",
                f"The culture model of class {pair[0]!r} on substrate {pair[1]!r} would give two of its states one "
                f"name ({', '.join(names)}); rename the substrate or the enzyme class.",
            )


def _culture_inactivation_refusal(what: str) -> str:
    """Why an inactivation_rate row is refused for a culture: its pools already have their own first-order loss."""

    return (
        f"inactivation_rate binds first-order inactivation to the enzyme state of an enzyme-assay case, but {what}. A "
        f"culture's enzyme pools are already lost at their own first-order rate, enzyme_loss_rate in {CULTURE_TABLE} "
        "(the existing first_order law), and FungMod adds no second loss law to a culture pool: two first-order losses "
        "of one pool are one constant stated twice, which no data could tell apart. State the loss of the pool as "
        f"enzyme_loss_rate in {CULTURE_TABLE}, or keep the enzyme-assay case in a separate dataset."
    )


def _validate_culture_case_units(parsed: _Parsed, context: _Context) -> None:
    """Check the units of each culture case taken together with pint.

    The substrate and the biomass share one unit (the closure ledger adds them
    with weight one). ``hydrolysis_capacity x E`` must be a substrate amount per
    volume per time with the case's consuming pool, and
    ``specific_production_rate x X`` an amount of the pool per volume per time,
    so that a pool in assay units is never paired with a rate per protein mass.
    """

    file = CULTURE_TABLE
    by_case: dict[tuple[str, str, str], dict[tuple[str, str], _CultureRow]] = {}
    for row in parsed.culture_rows:
        by_case.setdefault((row.strain_id, row.substrate_id, row.condition_id), {}).setdefault(row.role_key, row)
    for case_key, roles in by_case.items():
        if case_key[:2] not in parsed.cultured:
            continue
        where = f"strain {case_key[0]!r} on substrate {case_key[1]!r}, condition {case_key[2]!r}"
        initial = roles.get(("substrate_initial_concentration", ""))
        biomass = roles.get(("initial_biomass", ""))
        if initial is not None and biomass is not None and biomass.units != initial.units:
            context.add(
                file,
                biomass.row,
                "units",
                f"initial_biomass is in {biomass.units!r} and substrate_initial_concentration (row {initial.row}) in "
                f"{initial.units!r} for {where}: the culture closes one dry-mass balance over the substrate, the "
                "biomass and two closure ledgers, whose states share one unit. Write both in the same units; FungMod "
                "does not rescale one to the other.",
            )
        substrate_units = _MASS_REFERENCE_UNITS if initial is None else initial.units
        biomass_units = _MASS_REFERENCE_UNITS if biomass is None else biomass.units
        for (quantity, pool), enzyme in roles.items():
            if quantity != "initial_enzyme_concentration":
                continue
            capacity = roles.get(("hydrolysis_capacity", pool))
            if capacity is not None and not units_are_compatible(
                capacity.units, f"({substrate_units}) / second / ({enzyme.units})"
            ):
                context.add(
                    file,
                    capacity.row,
                    "units",
                    f"hydrolysis_capacity units {capacity.units!r} do not fit the consuming pool {pool!r} of {where} in "
                    f"{enzyme.units!r} (row {enzyme.row}): k_h x E x S / (K_h + S) must be a substrate dry mass per "
                    f"volume per time ({substrate_units} per time). Give k_h per unit of the pool, for example "
                    "g/(FPU h) with FPU/L or g/(mg h) with mg/L.",
                )
            production = roles.get(("specific_production_rate", pool))
            if production is not None and not units_are_compatible(
                production.units, f"({enzyme.units}) / ({biomass_units}) / second"
            ):
                context.add(
                    file,
                    production.row,
                    "units",
                    f"specific_production_rate units {production.units!r} do not fit pool {pool!r} of {where} in "
                    f"{enzyme.units!r} (row {enzyme.row}): q x X must be an amount of the pool per volume per time "
                    f"with X in {biomass_units}. Give q per biomass dry mass in the pool's own amount, for example "
                    "FPU/(g h) with FPU/L or mg/(g h) with mg/L.",
                )


def _rows_text(rows: Sequence[Any]) -> str:
    numbers = sorted({int(row.row) for row in rows})
    if len(numbers) == 1:
        return f"row {numbers[0]}"
    return f"rows {', '.join(str(number) for number in numbers)}"


def _case_form_rows(
    rows: Sequence[_Kinetics],
) -> tuple[list[_Kinetics], dict[str, list[_Kinetics]], list[_Kinetics]]:
    """Split a case's rows into kcat-form rows, Vmax-route rows (route name to rows) and pH-ionization rows.

    The enzyme concentration (and the enzyme dose of a solid case, which sets
    it) is listed with the kcat-form rows; the pH-ionization form uses the
    enzyme concentration too, which ``_validate_rate_forms`` takes into account.
    """

    kcat_rows = [row for row in rows if row.quantity in _KCAT_FORM_ROW_QUANTITIES]
    routes: dict[str, list[_Kinetics]] = {}
    for row in rows:
        route = _QUANTITY_VMAX_ROUTE.get(row.quantity)
        if route is not None:
            routes.setdefault(route, []).append(row)
    ionization_rows = [row for row in rows if row.quantity in PH_IONIZATION_QUANTITIES]
    return kcat_rows, routes, ionization_rows


def _form_rows(rows: Sequence[_Kinetics], form: str) -> list[_Kinetics]:
    """The rows of one case that set ``form``."""

    kcat_rows, routes, ionization_rows = _case_form_rows(rows)
    if form == RATE_FORM_KCAT:
        return kcat_rows
    if form == RATE_FORM_VMAX:
        return [row for route_rows in routes.values() for row in route_rows]
    return ionization_rows


def _pair_form(parsed: _Parsed, pair: tuple[str, str]) -> str:
    """The rate form of an enzyme class and substrate.

    A pair whose cases give rate rows has the form they started. A pair without
    rate rows takes the pH-ionization form when its enzyme class uses that form
    on its other substrates (a class runs one process law), otherwise the kcat
    form, whose gap requests name every form.
    """

    form = parsed.pair_forms.get(pair)
    if form is not None:
        return form
    return RATE_FORM_PH_IONIZATION if pair[0] in parsed.ionization_classes else RATE_FORM_KCAT


def _class_process_type(parsed: _Parsed, class_key: str) -> str:
    if parsed.network_dataset:
        # Every class of a network dataset runs in its networks only: no single-class compatibility is generated.
        return USER_DATASET_NETWORK_PROCESS_TYPE
    if class_key in parsed.culture_classes:
        return USER_DATASET_CULTURE_PROCESS_TYPE
    return _FORM_PROCESS_TYPE[RATE_FORM_PH_IONIZATION if class_key in parsed.ionization_classes else RATE_FORM_KCAT]


def _validate_rate_forms(parsed: _Parsed, context: _Context) -> None:
    """Check that each case, each enzyme class and substrate pair, and each enzyme class uses one rate form.

    A case is one strain, enzyme class, substrate and condition. It uses the
    kcat form (kcat and an enzyme concentration), the Vmax form, which takes
    exactly one route, or the pH-ionization form (limiting constants, four pK
    values and the fitted pH range, with an enzyme concentration). All cases of
    one enzyme class and substrate share one generated process, so they share
    one form. The form of a pair is stored in ``parsed.pair_forms``; a pair
    without any rate row has no entry. An enzyme class runs one process law on
    all of its substrates, so the pH-ionization form and the two homogeneous
    forms are not mixed across the substrates of one class; the classes that use
    the pH-ionization form are stored in ``parsed.ionization_classes``.
    """

    file = "kinetics.csv"
    by_case: dict[tuple[str, str, str, str], list[_Kinetics]] = {}
    for row in parsed.kinetics:
        by_case.setdefault(row.case_key, []).append(row)
    case_forms: dict[tuple[str, str, str, str], str] = {}
    for case_key, rows in by_case.items():
        kcat_rows, routes, ionization_rows = _case_form_rows(rows)
        if ionization_rows:
            others = [
                *(row for row in kcat_rows if row.quantity == "kcat"),
                *(row for route_rows in routes.values() for row in route_rows),
            ]
            for row in sorted(others, key=lambda item: item.row):
                context.add(
                    file,
                    row.row,
                    "quantity",
                    f"Row {row.row} gives {row.quantity} while {_rows_text(ionization_rows)} give the pH-ionization "
                    f"quantities ({', '.join(dict.fromkeys(item.quantity for item in ionization_rows))}) for the same "
                    "strain, class, substrate and condition: the pH-ionization form (kcat_limiting, km_limiting, four "
                    "pK values, ph_min and ph_max, with an enzyme concentration) is a rate form of its own, and one case "
                    "uses one form. Its limiting constants are not the kcat, Km or Vmax at any one pH, and FungMod "
                    "does not derive one form from another.",
                )
            if not others:
                case_forms[case_key] = RATE_FORM_PH_IONIZATION
            continue
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
        reference, *others = [form for form in _FORM_ORDER if form in forms]
        reference_rows = [row for case_key in forms[reference] for row in _form_rows(by_case[case_key], reference)]
        for form in others:
            for case_key in forms[form]:
                for row in _form_rows(by_case[case_key], form):
                    context.add(
                        file,
                        row.row,
                        "quantity",
                        f"Enzyme class {pair[0]!r} on substrate {pair[1]!r} uses the {_FORM_LABEL[reference]} form in "
                        f"{_rows_text(reference_rows)} and the {_FORM_LABEL[form]} form in row {row.row}. All strains "
                        "and conditions of one enzyme class and substrate share one generated process (FungMod "
                        "selects a process by enzyme class and substrate class), so they must use one rate form.",
                    )
    _validate_class_processes(parsed, context)


def _validate_class_processes(parsed: _Parsed, context: _Context) -> None:
    """Refuse an enzyme class that uses the pH-ionization form on some substrates and another form on others."""

    by_class: dict[str, dict[str, list[tuple[str, str]]]] = {}
    for pair, form in parsed.pair_forms.items():
        by_class.setdefault(pair[0], {}).setdefault(_FORM_PROCESS_TYPE[form], []).append(pair)
    for class_key, processes in by_class.items():
        ionization_pairs = processes.get(USER_DATASET_PH_IONIZATION_PROCESS_TYPE, [])
        if not ionization_pairs:
            continue
        if len(processes) == 1:
            parsed.ionization_classes.add(class_key)
            continue
        others = "; ".join(
            f"{pair[1]!r} ({_FORM_LABEL[parsed.pair_forms[pair]]} form)"
            for process_type, pairs in processes.items()
            if process_type != USER_DATASET_PH_IONIZATION_PROCESS_TYPE
            for pair in pairs
        )
        for pair in ionization_pairs:
            rows = [row for row in parsed.kinetics if row.pair_key == pair and row.quantity in PH_IONIZATION_QUANTITIES]
            context.add(
                "kinetics.csv",
                min(row.row for row in rows),
                "quantity",
                f"Enzyme class {class_key!r} uses the pH-ionization form on substrate {pair[1]!r} ({_rows_text(rows)}) "
                f"and another form on {others}. The generated enzyme class lists the process laws it runs, and "
                "preflight looks for a compatibility of every listed law on each substrate of the class, so in this "
                "version a class uses the pH-ionization form on all of its substrates or on none.",
            )


def _validate_solid_cases(parsed: _Parsed, context: _Context) -> None:
    """Check the enzyme route and the dimension of kcat in every case on a solid substrate.

    A solid case states its enzyme either as ``enzyme_concentration`` or as an
    ``enzyme_dose`` per substrate mass, never both; the dose is multiplied by
    the case's exact ``substrate_initial_concentration`` (a sampled initial
    substrate would be drawn independently of the enzyme derived from it). The
    units of ``kcat`` must make ``kcat x E`` a substrate concentration per time
    in the case's own units, which pint checks against the case's enzyme and
    substrate rows. A pair with a ``reactivity_exponent`` row binds the
    conversion-dependent reactivity factor and is stored in
    ``parsed.reactivity_pairs``. An enzyme class in the pH-ionization form
    cannot act on a solid substrate, because a class runs one process law on all
    of its substrates and that form is refused on solids.
    """

    file = "kinetics.csv"
    by_case: dict[tuple[str, str, str, str], dict[str, _Kinetics]] = {}
    for row in parsed.kinetics:
        if parsed.substrates[row.substrate_id].is_solid:
            by_case.setdefault(row.case_key, {}).setdefault(row.quantity, row)
            if row.quantity == "reactivity_exponent":
                parsed.reactivity_pairs.add(row.pair_key)
    for case_key, quantities in by_case.items():
        binding = _binding_text((case_key[0], case_key[1], case_key[2]))
        where = f"{binding}, condition {case_key[3]!r}"
        dose = quantities.get("enzyme_dose")
        explicit = quantities.get("enzyme_concentration")
        initial = quantities.get("substrate_initial_concentration")
        enzyme_units: str | None = None
        enzyme_text = ""
        if dose is not None and explicit is not None:
            context.add(
                file,
                dose.row,
                "quantity",
                f"Row {dose.row} gives enzyme_dose and row {explicit.row} gives enzyme_concentration for {where}: both "
                "set the enzyme concentration of the case. Give one; the dose route derives enzyme_concentration = "
                "enzyme_dose x substrate_initial_concentration.",
            )
        elif dose is not None and initial is not None and not initial.is_exact:
            context.add(
                file,
                dose.row,
                "quantity",
                f"Row {dose.row} gives enzyme_dose for {where}, but substrate_initial_concentration (row "
                f"{initial.row}) is a range. The derived enzyme concentration would be sampled independently of the "
                "initial substrate it is derived from, so the dose route needs an exact initial substrate "
                "concentration (the dose itself may be a range).",
            )
        elif explicit is not None:
            enzyme_units, enzyme_text = explicit.units, f"enzyme_concentration, row {explicit.row}"
        elif dose is not None and initial is not None:
            enzyme_units = _dose_product_units(dose, initial)[0]
            enzyme_text = f"enzyme_dose x substrate_initial_concentration, rows {dose.row} and {initial.row}"
        kcat = quantities.get("kcat")
        if kcat is None or enzyme_units is None:
            continue
        substrate_row = initial or quantities.get("km")
        substrate_units = _MASS_REFERENCE_UNITS if substrate_row is None else substrate_row.units
        expected = f"({substrate_units}) / second / ({enzyme_units})"
        if units_are_compatible(kcat.units, expected):
            continue
        product = (Q_(1.0, kcat.units) * Q_(1.0, enzyme_units)).to_reduced_units().units
        context.add(
            file,
            kcat.row,
            "units",
            f"kcat units {kcat.units!r} do not fit the enzyme concentration of {where} in {enzyme_units!r} "
            f"({enzyme_text}): kcat x E x S / (Km + S) must be a substrate concentration per time "
            f"({substrate_units} per time), but kcat x E has units {product}. Give kcat as substrate mass per time "
            "per unit of the case's enzyme, for example g/(FPU h) with FPU/L or g/(mg h) with mg/L.",
        )
    for class_key in sorted(parsed.ionization_classes):
        info = parsed.classes[class_key]
        for substrate in parsed.substrates.values():
            if substrate.is_solid and _shared_bonds(info, substrate) is not None:
                context.add(
                    "substrates.csv",
                    substrate.row,
                    "physical_state",
                    f"Enzyme class {class_key!r} uses the pH-ionization form in kinetics.csv and acts on the "
                    f"{substrate.physical_state} substrate {substrate.substrate_id!r}. A class runs one process law on "
                    "all of its substrates, and the pH-ionization form is refused on solid substrates; give that "
                    "class's kinetics in the kcat or Vmax form, or leave the solid substrate out of this dataset.",
                )


def _dose_product_units(dose: _Kinetics, initial: _Kinetics) -> tuple[str, float]:
    """Units and pint factor of enzyme_dose x substrate_initial_concentration (an enzyme amount per volume)."""

    product = Q_(1.0, dose.units) * Q_(1.0, initial.units)
    units = str(product.to_reduced_units().units)
    return units, float(product.to(units).magnitude)


def _validate_ph_ionization(parsed: _Parsed, context: _Context) -> None:
    """Check the pK ordering, the fitted pH range and the condition pH of every pH-ionization case.

    The diprotic law needs each lower pK below its upper pK; with ranges, the
    whole lower range must lie below the whole upper range, so that every
    sampled pair is ordered. ``ph_min`` must be below ``ph_max``. The law reads
    the condition pH, so the condition of every case with pH-ionization rows
    needs an exact pH inside the case's ``ph_min`` to ``ph_max``: FungMod does
    not extrapolate the law beyond the range it was fitted over.
    """

    file = "kinetics.csv"
    by_case: dict[tuple[str, str, str, str], list[_Kinetics]] = {}
    for row in parsed.kinetics:
        if parsed.pair_forms.get(row.pair_key) == RATE_FORM_PH_IONIZATION:
            by_case.setdefault(row.case_key, []).append(row)
    for case_key, rows in by_case.items():
        if not any(row.quantity in PH_IONIZATION_QUANTITIES for row in rows):
            continue
        quantities: dict[str, _Kinetics] = {}
        for row in rows:
            quantities.setdefault(row.quantity, row)
        binding = _binding_text((case_key[0], case_key[1], case_key[2]))
        for lower_name, upper_name, label in _PK_PAIRS:
            lower, upper = quantities.get(lower_name), quantities.get(upper_name)
            if lower is None or upper is None:
                continue
            lower_top = lower.value if lower.value is not None else lower.upper
            upper_bottom = upper.value if upper.value is not None else upper.lower
            assert lower_top is not None and upper_bottom is not None
            if lower_top < upper_bottom:
                continue
            ranged = "" if lower.is_exact and upper.is_exact else (
                " over the whole of both ranges, so that every sampled pair is ordered"
            )
            context.add(
                file,
                upper.row,
                "value",
                f"{lower_name} ({_kinetics_value_text(lower)}, row {lower.row}) must lie below {upper_name} "
                f"({_kinetics_value_text(upper)}, row {upper.row}) for {binding}: the diprotic law needs the lower "
                f"ionization of the {label} below the upper one{ranged}.",
            )
        ph_min, ph_max = quantities.get("ph_min"), quantities.get("ph_max")
        range_known = ph_min is not None and ph_max is not None
        if ph_min is not None and ph_max is not None:
            assert ph_min.value is not None and ph_max.value is not None
            if not ph_min.value < ph_max.value:
                context.add(
                    file,
                    ph_max.row,
                    "value",
                    f"ph_min ({_number_text(ph_min.value)}, row {ph_min.row}) must be smaller than ph_max "
                    f"({_number_text(ph_max.value)}, row {ph_max.row}) for {binding}.",
                )
                range_known = False
        condition = parsed.conditions[case_key[3]]
        if condition.ph is None:
            context.add(
                "conditions.csv",
                condition.row,
                "ph",
                f"Condition {condition.condition_id!r} has an unknown pH, but kinetics.csv {_rows_text(rows)} give the "
                f"pH-ionization form for {binding} there. The law reads the pH, so the condition needs one exact pH "
                "inside the case's ph_min to ph_max.",
            )
        elif range_known:
            assert ph_min is not None and ph_max is not None and ph_min.value is not None and ph_max.value is not None
            if not ph_min.value <= condition.ph <= ph_max.value:
                context.add(
                    "conditions.csv",
                    condition.row,
                    "ph",
                    f"Condition {condition.condition_id!r} has pH {condition.ph_text}, outside the pH range "
                    f"{_number_text(ph_min.value)} to {_number_text(ph_max.value)} (ph_min and ph_max, kinetics.csv rows "
                    f"{ph_min.row} and {ph_max.row}) over which the pH-ionization law of {binding} was fitted. FungMod "
                    "does not extrapolate the law beyond its fitted range; run the case at a pH inside it.",
                )


def _kinetics_value_text(row: _Kinetics) -> str:
    if row.value is not None:
        return _number_text(row.value)
    assert row.lower is not None and row.upper is not None
    return f"{_number_text(row.lower)} to {_number_text(row.upper)}"


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
    _refuse_laws_read_by_the_process(parsed, valid, context)
    for binding, laws in valid.items():
        by_condition: dict[str, list[str]] = {}
        for law_name in laws:
            if RESPONSE_LAWS[law_name].scales != LAW_SCALES_RATE:
                # The inactivation law scales the inactivation constant, not the rate: it composes with a rate law.
                continue
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


def _validate_inactivation(parsed: _Parsed, context: _Context) -> None:
    """Find the enzyme class and substrate pairs whose enzyme state is lost, and refuse a loss with no enzyme state.

    A pair binds enzyme inactivation when a case of it gives
    ``inactivation_rate`` or a strain binds the ``thermal_inactivation`` law of
    responses.csv to it. All strains and conditions of a pair share one
    generated process, so every case of the pair then runs the loss process
    (a case without the row gets an explicit gap, never a default value): the
    existing ``first_order`` law with the stated constant, or the existing
    ``thermal_inactivation`` law when a strain binds it. The Vmax form has no
    enzyme state, so both are refused there. Valid pairs are stored in
    ``parsed.inactivation_pairs``; culture rows were refused before.
    """

    rows: dict[tuple[str, str], list[_Kinetics]] = {}
    for row in parsed.kinetics:
        if row.quantity == INACTIVATION_RATE_QUANTITY:
            rows.setdefault(row.pair_key, []).append(row)
    law_rows: dict[tuple[str, str], list[_Response]] = {}
    for binding, laws in parsed.laws.items():
        if INACTIVATION_LAW in laws:
            law_rows.setdefault((binding[1], binding[2]), []).extend(laws[INACTIVATION_LAW].values())
    for pair in dict.fromkeys((*rows, *law_rows)):
        form = _pair_form(parsed, pair)
        if form in _ENZYME_FORMS:
            parsed.inactivation_pairs[pair] = INACTIVATION_LAW if pair in law_rows else _FIRST_ORDER_LOSS
            continue
        reason = (
            f"enzyme class {pair[0]!r} on substrate {pair[1]!r} uses the {_FORM_LABEL[form]} form, which has no enzyme "
            "state: Vmax is a rate of the simulated system, so there is no enzyme amount to lose. Give the case in the "
            "kcat form (kcat with an enzyme concentration) to simulate enzyme inactivation."
        )
        for row in rows.get(pair, []):
            context.add("kinetics.csv", row.row, "quantity", f"inactivation_rate binds first-order inactivation, but {reason}")
        if pair in law_rows:
            context.add(
                "responses.csv",
                min(row.row for row in law_rows[pair]),
                "law",
                f"{INACTIVATION_LAW} scales the first-order inactivation constant of an enzyme state, but {reason}",
            )


def _refuse_laws_read_by_the_process(
    parsed: _Parsed,
    valid: dict[tuple[str, str, str], dict[str, dict[str, _Response]]],
    context: _Context,
) -> None:
    """Refuse a response law on a condition the pair's own process law already reads.

    The pH-ionization law makes the rate depend on pH through its pK values; a
    pH response law on the same pair would apply the pH effect a second time.
    Refused laws are removed from ``valid``.
    """

    for binding, laws in valid.items():
        process_type = _FORM_PROCESS_TYPE[_pair_form(parsed, (binding[1], binding[2]))]
        read = PROCESS_ENVIRONMENT_CONDITIONS.get(process_type, ())
        for law_name in [name for name in laws if RESPONSE_LAWS[name].condition in read]:
            law = RESPONSE_LAWS[law_name]
            context.add(
                "responses.csv",
                min(row.row for row in laws[law_name].values()),
                "law",
                f"{law_name} binds a {law.condition} response to {_binding_text(binding)}, whose kinetics use the "
                f"{_FORM_LABEL[RATE_FORM_PH_IONIZATION]} form: that process law already makes the rate depend on "
                f"{law.condition} through its pK values, so {law_name} would count the {law.condition} effect twice. "
                f"Remove the {law_name} rows, or give this pair's kinetics in the kcat or Vmax form.",
            )
            del laws[law_name]


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
    user's declaration that the values are reference values. In an enzyme
    network a process's ``ki`` is checked with its other constants. The
    inactivation law scales the ``inactivation_rate`` only, so that is the
    constant it checks.
    """

    reference = chosen[law.reference_parameter]
    inactivation = law.scales == LAW_SCALES_INACTIVATION
    rows_by_condition: dict[str, list[_Kinetics]] = {}
    for row in parsed.kinetics:
        if (row.strain_id, row.class_key, row.substrate_id) == binding and row.quantity in _law_reference_quantities(law):
            rows_by_condition.setdefault(row.condition_id, []).append(row)
    for condition_id in sorted(rows_by_condition):
        condition = parsed.conditions[condition_id]
        rows = rows_by_condition[condition_id]
        current = condition.temperature_kelvin if law.reads == "temperature" else condition.ph
        if current is None:
            scaled = (
                f"the inactivation_rate there for {_binding_text(binding)}, which {law.law} scales with the {law.reads}"
                if inactivation
                else f"kinetic constants there for {_binding_text(binding)}, whose rate {law.law} scales with the "
                f"{law.reads}"
            )
            context.add(
                "responses.csv",
                reference.row,
                "value",
                f"Condition {condition_id!r} has an unknown {law.reads}, but kinetics.csv {_rows_text(rows)} give "
                f"{scaled}. State the {law.reads} in conditions.csv.",
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
        if inactivation:
            context.add(
                "responses.csv",
                reference.row,
                "value",
                f"The inactivation_rate of {_binding_text(binding)} at condition {condition_id!r} "
                f"({_condition_text(condition)}; kinetics.csv {_rows_text(rows)}) is not at the reference temperature "
                f"of {law.law}, {law.reference_parameter} {_number_text(reference.value)} {reference.units} (differs by "
                f"{_number_text(difference)} {reference.units}; {tolerance_text}). The law rescales the inactivation "
                f"constant from its reference value ({law.formula}), so the inactivation_rate must be stated at the "
                "reference temperature. State it there, give a reference_tolerance on this row that covers the "
                "difference, or set kinetics_at_reference to yes if the value is already the reference value.",
            )
            continue
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


def _check_thermal_inactivation(values: Mapping[str, Any]) -> None:
    arrhenius_inactivation_rate_constant(
        reference_rate_constant=Q_(1.0, _RATE_CONSTANT_REFERENCE_UNITS),
        inactivation_energy=values["activation_energy"],
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
    INACTIVATION_LAW: _check_thermal_inactivation,
}


def _law_reference_quantities(law: ResponseLaw) -> frozenset[str]:
    """The kinetics.csv quantities a law rescales, which must be stated at its reference condition."""

    if law.scales == LAW_SCALES_INACTIVATION:
        return frozenset({INACTIVATION_RATE_QUANTITY})
    return _LAW_REFERENCE_QUANTITIES


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
            if _consumes_in_culture(parsed, class_key, substrate.substrate_id) or parsed.network_dataset:
                # A culture model's state names are checked in _validate_cultures, a network's in _validate_networks.
                continue
            states = _state_names(class_key, substrate, form=_pair_form(parsed, (class_key, substrate.substrate_id)))
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
            _enzyme_class_mapping(
                parsed.classes[class_key], namespace, process_type=_class_process_type(parsed, class_key)
            ),
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
                culture_substrates=tuple(
                    pair[1] for pair in parsed.culture_pairs if any(item.class_key == pair[0] for item in declared)
                ),
                network_entries=tuple(
                    entry for entry, network in parsed.networks.items() if strain.strain_id in network.strains
                ),
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
    constant_conditions: dict[tuple[str, str, str], set[str]] = {}
    for row in parsed.kinetics:
        rows_by_case.setdefault(row.case_key, {})[row.quantity] = row
        if row.quantity in _KINETIC_CONSTANT_QUANTITIES:
            constant_conditions.setdefault((row.strain_id, row.class_key, row.substrate_id), set()).add(row.condition_id)
    # Culture models are generated by _generate_culture_records and enzyme networks by _generate_network_records
    # below; a network dataset has no single-class pairs.
    pairs: list[tuple[str, _Substrate]] = [
        (class_key, substrate)
        for class_key in used_classes
        for substrate in parsed.substrates.values()
        if _shared_bonds(parsed.classes[class_key], substrate) is not None
        and not _consumes_in_culture(parsed, class_key, substrate.substrate_id)
        and not parsed.network_dataset
    ]
    for class_key, substrate in pairs:
        pair = (class_key, substrate.substrate_id)
        started = pair in parsed.pair_forms
        form = _pair_form(parsed, pair)
        process_type = _FORM_PROCESS_TYPE[form]
        laws = _pair_laws(parsed, pair)
        rate_laws = tuple(law for law in laws if law.scales == LAW_SCALES_RATE)
        # A pair with a reactivity_exponent row binds the reactivity factor; its other cases get gaps for it.
        reactive = pair in parsed.reactivity_pairs
        # Likewise a pair whose enzyme state is lost (an inactivation_rate row or the inactivation law).
        inactivation = parsed.inactivation_pairs.get(pair, "")
        role_quantities = (
            *_FORM_QUANTITIES[form],
            *(("reactivity_exponent",) if reactive else ()),
            *((INACTIVATION_RATE_QUANTITY,) if inactivation else ()),
        )
        info = parsed.classes[class_key]
        pair_records: list[ParameterRecord] = []
        for item in parsed.strain_classes:
            if item.class_key != class_key:
                continue
            strain = parsed.strains[item.strain_id]
            strain_laws = parsed.laws.get((strain.strain_id, class_key, substrate.substrate_id), {})
            measured = constant_conditions.get((strain.strain_id, class_key, substrate.substrate_id), set())
            for condition in parsed.conditions.values():
                case_rows = rows_by_case.get((strain.strain_id, class_key, substrate.substrate_id, condition.condition_id), {})
                elsewhere = (
                    ()
                    if condition.condition_id in measured
                    else tuple(other for other in parsed.conditions.values() if other.condition_id in measured)
                )
                case = _CaseContext(
                    strain=strain,
                    info=info,
                    substrate=substrate,
                    condition=condition,
                    namespace=namespace,
                    case_rows=case_rows,
                    form_started=started,
                    laws=tuple(name for name in strain_laws if RESPONSE_LAWS[name].scales == LAW_SCALES_RATE),
                    form=form,
                    genome=item.genome if item.genome_only else None,
                    measured_elsewhere=elsewhere,
                    inactivation=inactivation,
                )
                for quantity in role_quantities:
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
                            reference_conditions=_reference_conditions(parsed, response.binding_key, law),
                            process_type=process_type,
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
                            process_type=process_type,
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
            _template_mapping(
                info,
                substrate,
                namespace,
                scientific=scientific,
                form=form,
                laws=rate_laws,
                reactivity=reactive,
                inactivation=inactivation,
                inactivation_stated=bool(parsed.inactivation_pairs),
            ),
            origin=("substrates.csv", substrate.row, "substrate_id"),
        )
        _emit(
            generated,
            context,
            "process_compatibility",
            _compatibility_mapping(
                info, substrate, namespace, form=form, laws=laws, reactivity=reactive, inactivation=inactivation
            ),
            origin=("substrates.csv", substrate.row, "substrate_id"),
        )
    _generate_culture_records(parsed, context, generated, namespace)
    _generate_network_records(parsed, context, generated, namespace)
    return generated


def _consumes_in_culture(parsed: _Parsed, class_key: str, substrate_id: str) -> bool:
    """Whether the class consumes the substrate in a culture model (as its first or another consuming pool)."""

    return any(
        pair[1] == substrate_id and class_key in culture.consuming_pools for pair, culture in parsed.culture_pairs.items()
    )


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
    form: str
    # Set when the class of this strain comes from its genome annotation alone.
    genome: _ClassEvidence | None = None
    # Other conditions at which this strain, class and substrate have kinetic constants, when this case has none.
    measured_elsewhere: tuple[_Condition, ...] = ()
    # The name of the pool that competitively inhibits this process in an enzyme network (its ki gap names it).
    inhibitor_name: str = ""
    # The process law through which the case's enzyme state is lost ("first_order", "thermal_inactivation" or blank).
    inactivation: str = ""

    @property
    def process_type(self) -> str:
        return _FORM_PROCESS_TYPE[self.form]


def _pair_laws(parsed: _Parsed, pair: tuple[str, str]) -> tuple[ResponseLaw, ...]:
    """Laws bound by any strain to one enzyme class and substrate, in ``RESPONSE_LAWS`` order."""

    used = {
        law_name
        for binding, laws in parsed.laws.items()
        if (binding[1], binding[2]) == pair
        for law_name in laws
    }
    return tuple(law for name, law in RESPONSE_LAWS.items() if name in used)


def _reference_conditions(parsed: _Parsed, binding: tuple[str, str, str], law: ResponseLaw) -> list[str]:
    """Conditions at which the binding has the constants the law scales, all checked against the law's reference."""

    quantities = _law_reference_quantities(law)
    return sorted(
        {
            row.condition_id
            for row in parsed.kinetics
            if (row.strain_id, row.class_key, row.substrate_id) == binding and row.quantity in quantities
        }
    )


def _role_mapping(quantity: str, case: _CaseContext) -> tuple[dict[str, Any], tuple[str, int | None, str | None]]:
    """Return the parameter or gap mapping of one role quantity of a case, with its origin."""

    if quantity == "vmax":
        return _vmax_mapping(case)
    row = case.case_rows.get(quantity)
    if row is not None:
        return _parameter_mapping(row, case=case), ("kinetics.csv", row.row, "quantity")
    if quantity == "enzyme_concentration":
        dose, initial = case.case_rows.get("enzyme_dose"), case.case_rows.get("substrate_initial_concentration")
        if dose is not None and initial is not None:
            return _derived_enzyme_mapping(dose, initial, case=case), ("kinetics.csv", dose.row, "quantity")
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


def _enzyme_class_mapping(info: _EnzymeClassInfo, namespace: _Namespace, *, process_type: str) -> dict[str, Any]:
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
            f"from the user's enzymes.csv. Restricted to {_PROCESS_LABEL[process_type]} kinetics."
        )
    else:
        provenance = {
            "source": info.source,
            "confidence_level": "user_supplied",
            USER_DATASET_PROVENANCE_KEY: namespace.provenance("enzyme_classes.csv", info.row),
        }
        notes = (
            f"User-defined enzyme class {info.key} from dataset {namespace.dataset_id}; "
            f"restricted to {_PROCESS_LABEL[process_type]} kinetics."
        )
    mapping: dict[str, Any] = {
        "record_id": namespace.id(info.key),
        "name": f"{info.name} ({namespace.dataset_id} user dataset)",
        "maturity": USER_DATASET_RECORD_MATURITY,
        "provenance": provenance,
        "notes": notes,
        "target_bond_classes": list(info.target_bond_classes),
        "compatible_substrate_classes": list(info.compatible_substrate_classes),
        "compatible_processes": [process_type],
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
    culture_substrates: Sequence[str] = (),
    network_entries: Sequence[str] = (),
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
    if culture_substrates:
        mapping["notes"] = (
            f"User-supplied strain {strain.strain_id} from dataset {namespace.dataset_id}. Its enzyme classes "
            f"{class_sources}. Its cases on {', '.join(culture_substrates)} are culture cases: the strain grows on "
            f"the substrate and secretes its enzyme pools following the culture_physiology model of {CULTURE_TABLE}; "
            "no other growth, secretion or uptake model is implied."
        )
    if network_entries:
        mapping["notes"] = (
            f"User-supplied strain {strain.strain_id} from dataset {namespace.dataset_id}. Its enzyme classes "
            f"{class_sources}. Its cases on {', '.join(network_entries)} are enzyme networks: every declared class "
            "that acts on a pool of the network runs its own Michaelis-Menten process, and the processes act together "
            "only through their shared pools; no growth, secretion or uptake model is implied."
        )
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
    if substrate.is_solid:
        notes = (
            f"User-defined {substrate.physical_state} substrate {substrate.substrate_id} from dataset "
            f"{namespace.dataset_id}; amounts are dry mass per volume (amount_basis {substrate.amount_basis}) and the "
            f"product yield is {substrate.yield_basis}. No surface area, crystallinity or particle size is recorded."
        )
    else:
        notes = f"User-defined dissolved substrate {substrate.substrate_id} from dataset {namespace.dataset_id}."
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
        "physical_state": substrate.physical_state,
        "bond_classes": list(substrate.bond_classes),
        "products": [substrate.product],
        "properties": {},
        "notes": notes,
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
    reactivity: bool = False,
    inactivation: str = "",
) -> dict[str, Any]:
    shared = _shared_bonds(info, substrate) or ()
    process_type = _FORM_PROCESS_TYPE[form]
    roles = (
        *_FORM_ROLES[form],
        *((REACTIVITY_EXPONENT_ROLE,) if reactivity else ()),
        *((INACTIVATION_RATE_QUANTITY,) if inactivation else ()),
    )
    symbols = {
        role: _parameter_symbol(namespace, _ROLE_QUANTITY[role], info.key, substrate.substrate_id) for role in roles
    }
    for law in laws:
        for parameter in law.parameters:
            # Law parameters never share a role with a form role: a law on a condition the
            # form's process law reads (a pH law on a pH-ionization pair) is refused at load,
            # and the inactivation law's roles carry the law's name.
            role = _single_law_role(law, parameter)
            assert role not in symbols, role
            symbols[role] = _law_symbol(namespace, law, parameter, info.key, substrate.substrate_id)
    return {
        "record_id": namespace.id(info.key, substrate.substrate_id, _PROCESS_ID_SUFFIX[process_type]),
        "name": f"{info.name} on {substrate.name} {_PROCESS_LABEL[process_type]} ({namespace.dataset_id})",
        "maturity": USER_DATASET_RECORD_MATURITY,
        "provenance": {
            "source": namespace.source,
            "confidence_level": "user_supplied",
            USER_DATASET_PROVENANCE_KEY: namespace.provenance("substrates.csv", substrate.row),
        },
        "enzyme_class": namespace.id(info.key),
        "substrate_class": substrate.substrate_class,
        "required_bond_classes": list(shared),
        "process_type": process_type,
        "required_parameters": list(symbols.values()),
        "parameter_roles": dict(symbols),
        "product_map_required": True,
        "case_template_id": _template_id(namespace, info, substrate, form=form),
        "notes": (
            f"{_PROCESS_SENTENCE_LABEL[process_type]} compatibility generated from user dataset "
            f"{namespace.dataset_id}; the enzyme class and substrate share the listed bond classes."
            + (
                f" The law runs as an apparent bulk law on the {substrate.physical_state} substrate (dry-mass basis)."
                if substrate.is_solid
                else ""
            )
        ),
    }


def _single_law_role(law: ResponseLaw, parameter: ResponseLawParameter) -> str:
    """The template role of a law parameter of a single-class case.

    A rate law's parameter keeps its own name (one law per condition, so the
    names never collide); the inactivation law's carry the law's name, since
    an Arrhenius rate law on the same pair has parameters of the same names.
    """

    return parameter.name if law.scales == LAW_SCALES_RATE else f"{law.law}__{parameter.name}"


def _template_id(namespace: _Namespace, info: _EnzymeClassInfo, substrate: _Substrate, *, form: str) -> str:
    suffix = _PROCESS_ID_SUFFIX[_FORM_PROCESS_TYPE[form]]
    return namespace.id(info.key, substrate.substrate_id, f"{suffix}_template")


def _template_mapping(
    info: _EnzymeClassInfo,
    substrate: _Substrate,
    namespace: _Namespace,
    *,
    scientific: bool,
    form: str,
    laws: Sequence[ResponseLaw],
    reactivity: bool = False,
    inactivation: str = "",
    inactivation_stated: bool = False,
) -> dict[str, Any]:
    """The case template of one enzyme class and substrate.

    ``laws`` are the rate laws (process modifiers). ``inactivation`` names the
    loss law of the enzyme state (USERDATA-011), declared under
    ``enzyme_inactivation`` for the enzyme-kinetics assembler. When the dataset
    states inactivation for some pair (``inactivation_stated``), a pair with an
    enzyme state but no inactivation says that its activity is assumed
    constant; a dataset without inactivation keeps every earlier text.
    """

    template_id = _template_id(namespace, info, substrate, form=form)
    process_type = _FORM_PROCESS_TYPE[form]
    process_label = _PROCESS_LABEL[process_type]
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
    if form in _ENZYME_FORMS:
        initial_state_mapping["enzyme"] = {
            "parameter_role": "enzyme_initial_concentration",
            "units_from_role": "enzyme_initial_concentration",
        }
    observable_roles = [*states, "degradation_rate", "product_release_rate"]
    process_state_metadata: dict[str, Any] = {
        "config_name": f"User dataset {namespace.dataset_id}: {info.name} on {substrate.name} {process_label}",
        "config_mode": mode,
        "config_maturity": mode,
        "process_id": namespace.id(info.key, substrate.substrate_id, _PROCESS_ID_SUFFIX[process_type]),
        "parameter_set_id": namespace.id(info.key, substrate.substrate_id, "parameters"),
        "product_map_name": f"{substrate.name} to {substrate.product} product map ({namespace.dataset_id})",
        "public_path": True,
    }
    modifiers: list[dict[str, Any]] = []
    if reactivity:
        # (S / S0)^n: the reference S0 is the case's own initial-substrate record, never a separate constant.
        modifiers.append(
            {
                "type": SUBSTRATE_REACTIVITY_MODIFIER_TYPE,
                "substrate_state_role": "substrate",
                "reference_concentration_role": "substrate_initial_concentration",
                "exponent_role": REACTIVITY_EXPONENT_ROLE,
            }
        )
    modifiers.extend(
        {"type": law.law, **{f"{parameter.name}_role": parameter.name for parameter in law.parameters}} for law in laws
    )
    if modifiers:
        process_state_metadata["process_modifiers"] = modifiers
    if inactivation:
        process_state_metadata[ENZYME_INACTIVATION_TEMPLATE_KEY] = _inactivation_template(
            info.name,
            law=inactivation,
            process_id=namespace.id(info.key, substrate.substrate_id, "enzyme_inactivation"),
            rate_role=INACTIVATION_RATE_QUANTITY,
            law_roles={
                parameter.name: _single_law_role(RESPONSE_LAWS[INACTIVATION_LAW], parameter)
                for parameter in RESPONSE_LAWS[INACTIVATION_LAW].parameters
            },
        )
    rate_limitation = _RATE_FORM_LIMITATION.get(form)
    if form == RATE_FORM_PH_IONIZATION and not laws and inactivation == INACTIVATION_LAW:
        law_limitation = (
            "No temperature response law scales the catalytic rate; its constants apply at the temperature of their "
            "condition only."
        )
    elif not laws and inactivation == INACTIVATION_LAW:
        law_limitation = (
            "No temperature or pH response law scales the catalytic rate; its constants apply at their stated "
            "condition only."
        )
    elif form == RATE_FORM_PH_IONIZATION:
        law_limitation = (
            "No temperature response law is bound; the constants apply at the temperature of their condition only."
            if not laws
            else "Response laws from responses.csv scale the rate: "
            + "; ".join(f"{law.law} ({law.formula})" for law in laws)
            + ". Kinetic constants are reference values at each law's reference condition; the pK values, the "
            "fitted pH range and the concentrations are not rescaled."
        )
    else:
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
        "name": f"{info.name} on {substrate.name} {process_label} template ({namespace.dataset_id})",
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
        "process_type": process_type,
        "state_roles": dict(states),
        "initial_state_mapping": initial_state_mapping,
        "product_map": {
            "id": namespace.id(info.key, substrate.substrate_id, "product_map"),
            "product_map_type": "stoichiometric",
            "substrate_state_role": "substrate",
            "product_state_role": "product",
            "stoichiometric_yield": yield_value,
            "notes": (
                f"User-stated yield {_number_text(yield_value)} g {substrate.product} per g dry "
                f"{substrate.substrate_id} (substrates.csv row {substrate.row})."
                if substrate.is_solid
                else f"User-stated yield {_number_text(yield_value)} mol {substrate.product} per mol "
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
            (
                f"Apparent {process_label} kinetics on a suspended {substrate.physical_state} substrate (dry-mass "
                f"basis) from user dataset {namespace.dataset_id}."
                if substrate.is_solid
                else f"Dissolved {process_label} kinetics from user dataset {namespace.dataset_id}."
            ),
            "This is an enzyme-kinetics case, not a whole-fungus growth, secretion or uptake model.",
            law_limitation,
            *([rate_limitation] if rate_limitation is not None else []),
            *(_solid_limitations(reactivity) if substrate.is_solid else []),
            *(
                [_inactivation_limitation(info.name, law=inactivation, where=substrate.name)]
                if inactivation_stated and form in _ENZYME_FORMS
                else []
            ),
        ],
        "validity_notes": [
            f"Values come from user dataset {namespace.dataset_id} (sha256 {namespace.digest}); "
            "FungMod did not check them against an external source.",
            f"Product formation uses the user-stated yield of {_number_text(yield_value)} {substrate.yield_basis}.",
            *([_PH_IONIZATION_VALIDITY_NOTE] if form == RATE_FORM_PH_IONIZATION else []),
            *([_SOLID_VALIDITY_NOTE] if substrate.is_solid else []),
        ],
        "notes": (
            f"Assembly template generated from user dataset {namespace.dataset_id} for enzyme class "
            f"{info.key} on substrate {substrate.substrate_id}."
        ),
    }


_RATE_FORM_LIMITATION = {
    RATE_FORM_VMAX: (
        "Homogeneous Michaelis-Menten in the Vmax form: Vmax is a rate for the simulated system and no enzyme "
        "state is represented, so enzyme loss or dilution cannot be simulated."
    ),
    RATE_FORM_PH_IONIZATION: (
        "Michaelis-Menten with the diprotic pH-ionization law: kcat(pH) = kcat_limiting / f_es(pH) and "
        "Km(pH) = km_limiting x f_e(pH) / f_es(pH), with f(pH) = (10^(pK_lower - pH) + 1)(10^(pH - pK_upper) + 1) "
        "for the free enzyme (f_e) and the enzyme-substrate complex (f_es). The limiting constants are plateau "
        "values of the fit, not the kcat or Km at any one pH. The pH is read once from the environment; no pH "
        "dynamics, buffer identity, ionic strength or pH-dependent enzyme stability is represented."
    ),
}
# Limitations every case on a solid substrate carries: what the apparent law stands for and what it leaves out.
_SOLID_APPARENT_LAW_LIMITATION = (
    "Apparent bulk saturation law on a suspended solid polymer: the dry mass per volume stands in for the "
    "accessible substrate, Km is an apparent half-saturation constant and not a binding constant, and kcat or Vmax "
    "and Km are specific to the substrate preparation and to the enzyme and solids loadings at which they were "
    "measured. No enzyme adsorption or partitioning between free and bound enzyme, accessible surface area, "
    "crystallinity, synergy between enzyme classes, product inhibition, or oxidative (LPMO) action is represented."
)
_SOLID_NO_REACTIVITY_LIMITATION = (
    "No conversion-dependent slowdown is represented: without a reactivity_exponent the rate depends on the "
    "remaining substrate only through the saturation term."
)
_SOLID_REACTIVITY_LIMITATION = (
    "Conversion-dependent reactivity: the rate is multiplied by (S / S0)^n, with S0 the case's own initial "
    "substrate concentration and n the reactivity_exponent from kinetics.csv (the existing substrate_reactivity "
    "modifier; n = 1 is the linear substrate reactivity factor of Kadam et al. 2004, n = 0 removes it). The factor is "
    f"phenomenological and resolves no surface or structure. Source of the factor: {KADAM_2004_SOURCE}."
)
_SOLID_VALIDITY_NOTE = (
    "The substrate is a solid polymer on a dry-mass basis: every substrate-side amount is a dry mass per volume, in "
    "the kcat form kcat was checked with pint to make kcat x E a dry mass per volume per time, and no molar mass, "
    "hydration factor or conversion between assay units and protein mass was applied."
)


def _inactivation_parameter_roles(law: str, *, rate_role: str, law_roles: Mapping[str, str]) -> dict[str, str]:
    """The parameter fields of the loss law of an enzyme state, bound to the template's roles."""

    if law == INACTIVATION_LAW:
        return {
            "reference_rate_constant": rate_role,
            "inactivation_energy": law_roles["activation_energy"],
            "reference_temperature": law_roles["reference_temperature"],
        }
    return {"rate_constant": rate_role}


def _inactivation_assumptions(name: str, *, law: str) -> list[str]:
    if law == INACTIVATION_LAW:
        return [
            f"{name} loses activity irreversibly at a first-order rate whose constant follows the Arrhenius reference "
            "form, k_d(T) = k_d(T_ref) exp(-E_d / R (1/T - 1/T_ref)), with k_d(T_ref) the inactivation_rate of "
            "kinetics.csv and E_d and T_ref from responses.csv; the temperature is read once from the environment, "
            "and no inactive enzyme pool is represented."
        ]
    return [
        f"{name} loses activity irreversibly at a constant first-order rate, dE/dt = -k_d E, with k_d the "
        "inactivation_rate of kinetics.csv at the case's condition; no inactive enzyme pool is represented."
    ]


def _inactivation_template(
    name: str,
    *,
    law: str,
    process_id: str,
    rate_role: str,
    law_roles: Mapping[str, str],
) -> dict[str, Any]:
    """The ``enzyme_inactivation`` declaration of a single-class template: the loss law of its enzyme state."""

    return {
        "process_id": process_id,
        "process_type": law,
        "parameter_roles": _inactivation_parameter_roles(law, rate_role=rate_role, law_roles=law_roles),
        "assumptions": _inactivation_assumptions(name, law=law),
    }


_INACTIVATION_SCOPE = (
    "Irreversible single-exponential loss only: no reversible unfolding, proteolysis, aggregation, substrate or "
    "product protection, adsorption to a solid, or inactive enzyme pool is represented, and the constant is only as "
    "transferable as the preparation and medium it was measured in."
)


def _inactivation_limitation(name: str, *, law: str, where: str) -> str:
    """What the enzyme inactivation of one enzyme state is, or that the state is not lost (USERDATA-011)."""

    if not law:
        return (
            f"Enzyme activity assumed constant over the run for {name} on {where}: kinetics.csv gives no "
            "inactivation_rate for it, so its enzyme state has no inactivation term (FungMod applies no default "
            "constant)."
        )
    if law == INACTIVATION_LAW:
        return (
            f"Enzyme inactivation of {name} on {where}: the existing thermal_inactivation process law, "
            "dE/dt = -k_d(T) E with k_d(T) = k_d(T_ref) exp(-E_d / R (1/T - 1/T_ref)), k_d(T_ref) the inactivation_rate "
            "of kinetics.csv stated at the reference temperature, and E_d and T_ref from responses.csv; it rescales "
            "the inactivation constant only, never the catalytic constants, and reads the temperature once from the "
            f"environment. {_INACTIVATION_SCOPE}"
        )
    return (
        f"Enzyme inactivation of {name} on {where}: the existing first_order process law, dE/dt = -k_d E with k_d the "
        "inactivation_rate of kinetics.csv at the case's condition, so E(t) = E0 exp(-k_d t); no temperature law "
        "rescales k_d, so at any other temperature (an EnvironmentGrid condition) it keeps its stated value. "
        f"{_INACTIVATION_SCOPE}"
    )


def _solid_limitations(reactivity: bool) -> list[str]:
    return [
        _SOLID_APPARENT_LAW_LIMITATION,
        _SOLID_REACTIVITY_LIMITATION if reactivity else _SOLID_NO_REACTIVITY_LIMITATION,
    ]


_PH_IONIZATION_VALIDITY_NOTE = (
    "The pH of every condition with pH-ionization values lies within that case's ph_min to ph_max (checked when "
    "the dataset is loaded); an EnvironmentGrid pH outside the fitted range runs with an environmental validity "
    "warning from the law."
)


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
    fit = _fit_provenance(namespace.manifest.get("fit"), row) if row.evidence_type == FITTED_EVIDENCE_TYPE else None
    if fit is not None:
        extra["fit"] = fit
    provenance: dict[str, Any] = {
        "source": row.source,
        "confidence_level": confidence,
        "measurement_method": row.method or "user estimate without a stated method",
        "validity_range": (
            _inactivation_validity_range(condition, law=case.inactivation)
            if quantity == INACTIVATION_RATE_QUANTITY
            else _validity_range(condition, case.laws, form=case.form)
        ),
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
    if fit is not None:
        verdict = fit.get("identifiability")
        name = (
            f"Fitted {_QUANTITY_LABEL[quantity]} for {info.name} from {strain.name} on {substrate.name} at "
            f"{condition.condition_id} ({namespace.dataset_id})"
        )
        notes = (
            f"{row.quantity} fitted by fit_user_dataset to the time courses of dataset {fit.get('input_dataset_id')} "
            f"(kinetics.csv row {row.row}); evidence type {row.evidence_type}; identifiability {verdict}"
            f" ({fit.get('identifiability_method')}). {_FITTED_SCIENTIFIC_BOUNDARY}"
        )
        if verdict != FIT_IDENTIFIED:
            notes = (
                f"NOT IDENTIFIED by the time courses ({verdict}); written only because the fit ran with "
                f"allow_unidentified=True. {notes}"
            )
    elif route is None:
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
        **_selectors(namespace, strain, info, substrate, condition, quantity, process_type=case.process_type),
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
    if evidence_type == FITTED_EVIDENCE_TYPE:
        # In-sample fits are not independent evidence; there is no relabelling route to scientific use.
        return PARAMETER_ALLOWED_USE_EXPLORATORY_SCREENING
    if exact:
        return PARAMETER_ALLOWED_USE_SCIENTIFIC
    return PARAMETER_ALLOWED_USE_EXPLORATORY_SCREENING


def _fit_provenance(block: Any, row: _Kinetics) -> dict[str, Any]:
    """The fit description a fitted record carries: method, objective, data rows, bounds and identifiability."""

    if not isinstance(block, Mapping):
        return {}
    entry = next(
        (
            item
            for item in block.get("quantities", [])
            if isinstance(item, Mapping) and item.get("quantity") == row.quantity
        ),
        {},
    )
    return {
        "method": block.get("method"),
        "objective": block.get("objective"),
        "error_model": block.get("error_model"),
        "input_dataset_id": block.get("input_dataset_id"),
        "input_dataset_digest": block.get("input_dataset_digest"),
        "report_file": block.get("report_file"),
        "report_sha256": block.get("report_sha256"),
        "conditions": _plain(block.get("conditions", [])),
        "timecourse_file": TIMECOURSE_TABLE,
        "timecourse_rows": _plain(block.get("timecourse_rows", [])),
        "units": entry.get("units"),
        "bounds": _plain(entry.get("bounds")),
        "initial": entry.get("initial"),
        "identifiability": entry.get("identifiability"),
        "identifiability_method": entry.get("identifiability_method"),
        "interval": _plain(entry.get("interval")),
        "allow_unidentified": block.get("allow_unidentified"),
        "claim_boundary": block.get("claim_boundary"),
        "scientific_mode": _FITTED_SCIENTIFIC_BOUNDARY,
    }


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
        "validity_range": _validity_range(condition, case.laws, form=case.form),
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
        **_selectors(namespace, strain, info, substrate, condition, "vmax", process_type=case.process_type),
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


def _derived_enzyme_mapping(dose: _Kinetics, initial: _Kinetics, *, case: _CaseContext) -> dict[str, Any]:
    """Enzyme concentration = enzyme dose x initial substrate concentration, converted with pint.

    One derived parameter record for the enzyme-concentration role of a solid
    case: the dose row produces no record of its own, the initial-substrate row
    keeps its own record for the initial-substrate role. The maturity is the
    weaker input's; a dose range scaled by the exact initial substrate is again
    a uniform range, and a range of the initial substrate is refused during
    validation.
    """

    strain, info, substrate, condition, namespace = (
        case.strain,
        case.info,
        case.substrate,
        case.condition,
        case.namespace,
    )
    units, factor = _dose_product_units(dose, initial)
    evidence_type = _weakest_evidence((dose.evidence_type, initial.evidence_type))
    maturity = _EVIDENCE_MATURITY[evidence_type]
    confidence = _confidence(evidence_type)
    exact = dose.is_exact and initial.is_exact
    source = dose.source if dose.source == initial.source else f"{dose.source}; {initial.source}"
    value: dict[str, Any] = {
        "kind": "exact" if exact else "range",
        "units": units,
        "source": source,
        "confidence_level": confidence,
        "notes": (
            f"Derived in user dataset {namespace.dataset_id} as enzyme_dose (kinetics.csv row {dose.row}) x "
            f"substrate_initial_concentration (row {initial.row}); ({dose.units}) x ({initial.units}) converted to "
            f"{units} with factor {_number_text(factor)}."
        ),
    }
    assert initial.value is not None
    if dose.value is not None:
        value["value"] = dose.value * initial.value * factor
    else:
        assert dose.lower is not None and dose.upper is not None
        value["lower"] = dose.lower * initial.value * factor
        value["upper"] = dose.upper * initial.value * factor
    derivation = {
        "route": "enzyme_dose",
        "formula": "enzyme_concentration = enzyme_dose x substrate_initial_concentration",
        "units_conversion": f"({dose.units}) x ({initial.units}) -> {units}, factor {_number_text(factor)} (pint)",
        "maturity_rule": f"weakest input in the order {_MATURITY_ORDER_TEXT}",
        "inputs": [_input_summary(dose), _input_summary(initial)],
    }
    method = (
        f"Derived: enzyme_concentration = enzyme_dose x substrate_initial_concentration from kinetics.csv rows "
        f"{dose.row} and {initial.row} (pint unit conversion)"
    )
    provenance: dict[str, Any] = {
        "source": source,
        "confidence_level": confidence,
        "measurement_method": method,
        "validity_range": _validity_range(condition, case.laws, form=case.form),
        USER_DATASET_PROVENANCE_KEY: namespace.provenance(
            "kinetics.csv",
            None,
            rows=[dose.row, initial.row],
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
        "record_id": namespace.id(
            strain.strain_id, info.key, substrate.substrate_id, condition.condition_id, "enzyme_concentration"
        ),
        "name": (
            f"Enzyme concentration from enzyme dose and initial substrate for {info.name} from {strain.name} on "
            f"{substrate.name} at {condition.condition_id} ({namespace.dataset_id})"
        ),
        "maturity": maturity,
        "provenance": provenance,
        "notes": (
            f"Derived enzyme concentration in dataset {namespace.dataset_id}: enzyme_dose (kinetics.csv row "
            f"{dose.row}) x substrate_initial_concentration (row {initial.row}); maturity {maturity} is the weaker "
            "input's."
        ),
        **_selectors(
            namespace, strain, info, substrate, condition, "enzyme_concentration", process_type=case.process_type
        ),
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
    if case.substrate.is_solid:
        units = _solid_gap_units(quantity, case.case_rows)
        dimension = _SOLID_GAP_DIMENSION[quantity]
        units_text = units if units is not None else _SOLID_GAP_UNITS_TEXT[quantity]
    else:
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
        **_selectors(namespace, strain, info, substrate, condition, quantity, process_type=case.process_type),
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
    "ki": "concentration of the inhibiting product (amount per volume)",
    "kcat": "1/time",
    INACTIVATION_RATE_QUANTITY: "1/time",
    "vmax": "concentration per time (amount per volume per time)",
    "kcat_limiting": "1/time",
    **{quantity: "dimensionless" for quantity in sorted(_DIMENSIONLESS_QUANTITIES)},
}
_GAP_UNITS_TEXT = {
    "ki": "amount of the inhibiting product per volume, for example mM",
    "kcat": "units of 1/time",
    INACTIVATION_RATE_QUANTITY: "units of 1/time, for example 1/h",
    "vmax": "concentration per time",
    "kcat_limiting": "units of 1/time",
    **{quantity: "dimensionless" for quantity in sorted(_DIMENSIONLESS_QUANTITIES)},
}


# The dimension and the units wording of each gap of a case on a solid substrate (dry-mass basis).
_SOLID_GAP_DIMENSION = MappingProxyType(
    {
        "km": "dry mass of the solid substrate per volume",
        "substrate_initial_concentration": "dry mass of the solid substrate per volume",
        "kcat": "substrate mass per time per enzyme amount (per protein mass, which is 1/time, or per assay unit)",
        "enzyme_concentration": "enzyme protein mass per volume or an assay activity per volume",
        "vmax": "dry mass of the solid substrate per volume per time",
        "reactivity_exponent": "dimensionless",
        INACTIVATION_RATE_QUANTITY: "1/time",
    }
)
_SOLID_GAP_UNITS_TEXT = MappingProxyType(
    {
        "km": "dry mass per volume, for example g/L",
        "substrate_initial_concentration": "dry mass per volume, for example g/L",
        "kcat": "substrate mass per time per enzyme amount, for example g/(FPU h) or g/(mg h)",
        "enzyme_concentration": "protein mass or assay activity per volume, for example mg/L or FPU/L",
        "vmax": "dry mass per volume per time, for example g/L/h",
        "reactivity_exponent": "dimensionless",
        INACTIVATION_RATE_QUANTITY: "units of 1/time, for example 1/h",
    }
)


def _solid_gap_units(quantity: str, case_rows: Mapping[str, _Kinetics]) -> str | None:
    """Units of a solid case's gap: a substrate amount takes the case's own dry-mass units, nothing else is guessed."""

    if quantity not in {"km", "substrate_initial_concentration"}:
        return None
    for other in ("substrate_initial_concentration", "km"):
        row = case_rows.get(other)
        if row is not None:
            return row.units
    return None


_QUANTITY_LABEL = {
    "km": "km",
    "kcat": "kcat",
    "substrate_initial_concentration": "initial substrate concentration",
    "enzyme_concentration": "enzyme concentration",
    "vmax": "Vmax",
    "kcat_limiting": "limiting turnover kcat_limiting",
    "km_limiting": "limiting Michaelis constant km_limiting",
    "pk_free_lower": "lower free-enzyme pK pk_free_lower",
    "pk_free_upper": "upper free-enzyme pK pk_free_upper",
    "pk_complex_lower": "lower enzyme-substrate complex pK pk_complex_lower",
    "pk_complex_upper": "upper enzyme-substrate complex pK pk_complex_upper",
    "ph_min": "lowest fitted pH ph_min",
    "ph_max": "highest fitted pH ph_max",
    "reactivity_exponent": "substrate reactivity exponent",
    "ki": "competitive inhibition constant Ki",
    INACTIVATION_RATE_QUANTITY: "first-order inactivation rate constant",
}
# What a measurement request asks for, per pH-ionization quantity.
_PH_IONIZATION_REQUEST = {
    "kcat_limiting": "the limiting turnover (kcat_limiting, the plateau kcat)",
    "km_limiting": "the limiting Michaelis constant (km_limiting)",
    "pk_free_lower": "the lower pK of the free enzyme (pk_free_lower)",
    "pk_free_upper": "the upper pK of the free enzyme (pk_free_upper)",
    "pk_complex_lower": "the lower pK of the enzyme-substrate complex (pk_complex_lower)",
    "pk_complex_upper": "the upper pK of the enzyme-substrate complex (pk_complex_upper)",
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
    request = _with_measured_condition_note(
        _measurement_request_text(quantity, case=case, units_text=units_text), case.measured_elsewhere
    )
    return _with_genome_note(request, case.genome)


def _with_measured_condition_note(request: str, measured: Sequence[_Condition]) -> str:
    """Name the conditions at which the case's kinetic constants were stated instead of this one."""

    if not measured:
        return request
    where = " and ".join(f"{condition.condition_id} ({_condition_text(condition)})" for condition in measured)
    return (
        f"{request.rstrip('.')}; kinetics.csv states kinetic constants of this strain, enzyme class and substrate "
        f"only at {where}, and FungMod does not reuse kinetics measured at another condition."
    )


def _measurement_request_text(quantity: str, *, case: _CaseContext, units_text: str) -> str:
    strain, info, substrate, condition = case.strain, case.info, case.substrate, case.condition
    where = _condition_text(condition)
    if quantity in _PH_IONIZATION_REQUEST:
        return (
            f"Measure {_PH_IONIZATION_REQUEST[quantity]} of {info.name} from {strain.name} on {substrate.name} "
            f"({units_text}) by fitting the diprotic pH-ionization law to initial rates over a pH series at the "
            f"temperature of condition {condition.condition_id} ({_temperature_text(condition)})."
        )
    if quantity in _PH_RANGE_QUANTITIES:
        bound = "lowest" if quantity == "ph_min" else "highest"
        return (
            f"State the {bound} pH of the pH series the pH-ionization law of {info.name} from {strain.name} on "
            f"{substrate.name} was fitted over ({quantity}, {units_text}); the pH of condition "
            f"{condition.condition_id} must lie inside the fitted range."
        )
    if quantity == INACTIVATION_RATE_QUANTITY:
        reference = (
            f"; the {INACTIVATION_LAW} law of responses.csv rescales it from the reference temperature, so state it "
            "there"
            if case.inactivation == INACTIVATION_LAW
            else ""
        )
        return (
            f"Measure the first-order inactivation rate constant k_d of {info.name} from {strain.name} in the "
            f"{substrate.name} system at {where} ({units_text}), for example from the decay of its activity over time "
            f"at that condition{reference}. Enzyme inactivation is bound to {info.name} on {substrate.name} (by an "
            f"inactivation_rate row or the {INACTIVATION_LAW} law), and every case of one enzyme class and substrate "
            "runs it."
        )
    if substrate.is_solid:
        solid_request = _solid_measurement_request_text(quantity, case=case, units_text=units_text)
        if solid_request is not None:
            return solid_request
    if quantity in _KCAT_FORM_QUANTITIES and not case.form_started and case.form != RATE_FORM_PH_IONIZATION:
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
    if quantity == INHIBITION_CONSTANT_QUANTITY:
        return (
            f"Measure the competitive inhibition constant Ki of {info.name} from {strain.name} on {substrate.name} by "
            f"{case.inhibitor_name} at {where} ({units_text}), for example from initial rates at several "
            f"{substrate.name} and {case.inhibitor_name} concentrations."
        )
    if quantity == "substrate_initial_concentration":
        return (
            f"Specify the initial {substrate.name} concentration for {info.name} from {strain.name} "
            f"at {where} ({units_text})."
        )
    return (
        f"Measure or specify the {info.name} concentration from {strain.name} in the {substrate.name} assay "
        f"at {where} ({units_text})."
    )


def _solid_measurement_request_text(quantity: str, *, case: _CaseContext, units_text: str) -> str | None:
    """The requests that differ on a solid substrate; ``None`` keeps the common wording.

    A solid case has no activity route to Vmax, may state its enzyme as a dose
    per substrate mass, and may bind the reactivity exponent.
    """

    strain, info, substrate, condition = case.strain, case.info, case.substrate, case.condition
    where = _condition_text(condition)
    if quantity == "reactivity_exponent":
        return (
            f"Measure or state the substrate reactivity exponent (reactivity_exponent, {units_text}) of {info.name} "
            f"from {strain.name} on {substrate.name} at {where}: the exponent n of the factor (S / S0)^n by which the "
            "rate slows with conversion, for example from rates of fresh enzyme on partially converted substrate."
        )
    if quantity in _KCAT_FORM_QUANTITIES and not case.form_started:
        return (
            f"Measure kcat and the enzyme concentration of {info.name} from {strain.name} on {substrate.name} at "
            f"{where} (kcat as substrate mass per time per enzyme amount; the enzyme as a protein mass or assay "
            "activity per volume, or as an enzyme_dose per substrate mass), or Vmax (dry mass per volume per time)."
        )
    if quantity == "vmax":
        return f"Measure Vmax of {info.name} from {strain.name} on {substrate.name} at {where} ({units_text})."
    if quantity == "enzyme_concentration":
        dose = case.case_rows.get("enzyme_dose")
        if dose is not None:
            return (
                f"Specify the initial {substrate.name} concentration (dry mass per volume) for {info.name} from "
                f"{strain.name} at {where} to derive the enzyme concentration from the enzyme_dose in kinetics.csv "
                f"row {dose.row}."
            )
        return (
            f"Measure or specify the {info.name} concentration from {strain.name} in the {substrate.name} assay at "
            f"{where} ({units_text}), or the enzyme_dose per substrate mass."
        )
    return None


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
    process_type: str,
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
    inactivation = law.scales == LAW_SCALES_INACTIVATION
    if response.parameter == law.reference_parameter:
        extra["reference_condition"] = {
            "rule": (
                "the inactivation_rate of this strain, enzyme class and substrate must be stated at this reference "
                "temperature, exactly or within the row's reference_tolerance, or be declared the reference value"
                if inactivation
                else "kinetic constants of this strain, enzyme class and substrate must be stated at this reference "
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
            + (
                "every condition of the case and rescales the reference inactivation constant, not the catalytic "
                "constants."
                if inactivation
                else "every condition of the case and rescales the reference kinetic constants."
            )
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
        **_law_selectors(namespace, law, spec, strain, info, substrate, process_type=process_type),
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
    process_type: str,
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
        **_law_selectors(namespace, law, parameter, strain, info, substrate, process_type=process_type),
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
    *,
    process_type: str,
) -> dict[str, Any]:
    """Selectors of a law parameter: like kinetics, but valid at every environment of the case."""

    return {
        "parameter_symbol": _law_symbol(namespace, law, parameter, info.key, substrate.substrate_id),
        "process_type": process_type,
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
    *,
    process_type: str,
) -> dict[str, Any]:
    return {
        "parameter_symbol": _parameter_symbol(namespace, quantity, info.key, substrate.substrate_id),
        "process_type": process_type,
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


def _validity_range(condition: _Condition, laws: Sequence[str] = (), *, form: str = RATE_FORM_KCAT) -> str:
    if form == RATE_FORM_PH_IONIZATION:
        text = (
            f"Condition {condition.condition_id}: {_condition_text(condition)}; the diprotic pH-ionization law reads "
            "the environment pH and holds within the case's ph_min to ph_max"
        )
        if not laws:
            return f"{text}; no temperature response law is attached."
        return (
            f"{text}; the response law(s) {', '.join(laws)} from responses.csv rescale the rate away from their "
            "reference condition."
        )
    if not laws:
        return (
            f"Condition {condition.condition_id}: {_condition_text(condition)}; "
            "no temperature or pH response law is attached."
        )
    return (
        f"Condition {condition.condition_id}: {_condition_text(condition)}; the response law(s) "
        f"{', '.join(laws)} from responses.csv rescale the rate away from their reference condition."
    )


def _inactivation_validity_range(condition: _Condition, *, law: str) -> str:
    if law == INACTIVATION_LAW:
        return (
            f"Condition {condition.condition_id}: {_condition_text(condition)}; the reference value of the "
            f"{INACTIVATION_LAW} law from responses.csv, which rescales it away from the reference temperature; the "
            "catalytic constants are not rescaled by it."
        )
    return (
        f"Condition {condition.condition_id}: {_condition_text(condition)}; the first-order inactivation constant at "
        "this condition, which no temperature law rescales."
    )


def _condition_text(condition: _Condition) -> str:
    ph = "unknown pH" if condition.ph is None else f"pH {condition.ph_text}"
    return f"{_temperature_text(condition)}, {ph}"


def _temperature_text(condition: _Condition) -> str:
    if condition.temperature_kelvin is None:
        return "unknown temperature"
    return f"{condition.temperature_text} {condition.temperature_units}"


def _state_names(class_key: str, substrate: _Substrate, *, form: str) -> dict[str, str]:
    substrate_key = substrate.registry_id or substrate.substrate_id
    names = {
        "substrate": f"{substrate_key}_concentration",
        "product": f"{substrate.product}_concentration",
    }
    if form in _ENZYME_FORMS:
        names["enzyme"] = f"{class_key}_concentration"
    return names


def enzyme_class_acts_on(
    *,
    target_bond_classes: Sequence[str],
    compatible_substrate_classes: Sequence[str],
    substrate_class: str,
    bond_classes: Sequence[str],
) -> tuple[str, ...]:
    """Return the bond classes through which an enzyme class acts on a substrate, sorted; empty when it does not.

    This is the categorical compatibility rule of the registry and of user
    datasets: the substrate class must be one of the enzyme class's compatible
    substrate classes, and the substrate must carry a bond class the enzyme
    class targets.
    """

    if substrate_class not in compatible_substrate_classes:
        return ()
    return tuple(sorted(set(bond_classes).intersection(target_bond_classes)))


def _shared_bonds(info: _EnzymeClassInfo, substrate: _Substrate) -> tuple[str, ...] | None:
    shared = enzyme_class_acts_on(
        target_bond_classes=info.target_bond_classes,
        compatible_substrate_classes=info.compatible_substrate_classes,
        substrate_class=substrate.substrate_class,
        bond_classes=substrate.bond_classes,
    )
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


# ---------------------------------------------------------------------------
# Culture records


@dataclass(frozen=True)
class _CultureCase:
    """One strain on one culture substrate at one condition during record generation."""

    strain: _Strain
    culture: _CulturePair
    info: _EnzymeClassInfo
    substrate: _Substrate
    condition: _Condition
    namespace: _Namespace
    # The culture.csv rows of this case by (quantity, pool class); the class is blank for a culture-level quantity.
    rows: Mapping[tuple[str, str], _CultureRow]
    pool_names: Mapping[str, str]
    # Genome or proteome evidence of each pool class this strain declares from genomes.csv alone.
    genomes: Mapping[str, _ClassEvidence]
    # Other conditions at which this culture has culture.csv rows, when this case has none.
    measured_elsewhere: tuple[_Condition, ...] = ()


def _generate_culture_records(
    parsed: _Parsed,
    context: _Context,
    generated: _Generated,
    namespace: _Namespace,
) -> None:
    """Emit the parameter records, case template and compatibility of every culture model.

    Every strain that declares a culture's consuming class gets one record per
    role and condition: the culture.csv row's value, or an explicit gap with a
    measurement request. The template is scientific only when every record
    bound to it is exact and scientific-eligible.
    """

    rows_by_case: dict[tuple[str, str, str], dict[tuple[str, str], _CultureRow]] = {}
    for row in parsed.culture_rows:
        rows_by_case.setdefault((row.strain_id, row.substrate_id, row.condition_id), {})[row.role_key] = row
    pool_names = {class_key: info.name for class_key, info in parsed.classes.items()}
    for pair, culture in parsed.culture_pairs.items():
        info = parsed.classes[pair[0]]
        substrate = parsed.substrates[pair[1]]
        pair_records: list[ParameterRecord] = []
        for item in parsed.strain_classes:
            if item.class_key != pair[0]:
                continue
            strain = parsed.strains[item.strain_id]
            genomes = {
                other.class_key: other.genome
                for other in parsed.strain_classes
                if other.strain_id == strain.strain_id and other.genome_only and other.genome is not None
            }
            measured = {
                row.condition_id
                for row in parsed.culture_rows
                if row.culture_key == (strain.strain_id, substrate.substrate_id)
            }
            for condition in parsed.conditions.values():
                case = _CultureCase(
                    strain=strain,
                    culture=culture,
                    info=info,
                    substrate=substrate,
                    condition=condition,
                    namespace=namespace,
                    rows=rows_by_case.get((strain.strain_id, substrate.substrate_id, condition.condition_id), {}),
                    pool_names=pool_names,
                    genomes=genomes,
                    measured_elsewhere=(
                        ()
                        if condition.condition_id in measured
                        else tuple(other for other in parsed.conditions.values() if other.condition_id in measured)
                    ),
                )
                for quantity, pool in _culture_role_keys(culture):
                    row = case.rows.get((quantity, pool if quantity not in CULTURE_LEVEL_QUANTITIES else ""))
                    if row is not None:
                        mapping = _culture_parameter_mapping(row, quantity=quantity, pool=pool, case=case)
                        origin: tuple[str, int | None, str | None] = (CULTURE_TABLE, row.row, "quantity")
                    else:
                        mapping = _culture_gap_mapping(quantity, pool, case=case)
                        origin = (CULTURE_TABLE, None, "quantity")
                    record = _emit(generated, context, "parameter_records", mapping, origin=origin)
                    if isinstance(record, ParameterRecord):
                        pair_records.append(record)
        scientific = bool(pair_records) and all(
            record.value.is_exact and parameter_record_is_mode_eligible(record, mode="scientific")
            for record in pair_records
        )
        origin = (CULTURE_TABLE, culture.pool_rows.get(culture.class_key), "enzyme_class")
        _emit(
            generated,
            context,
            "case_templates",
            _culture_template_mapping(culture, parsed=parsed, namespace=namespace, scientific=scientific),
            origin=origin,
        )
        # One compatibility per consuming class, all pointing to the one template: the preflight looks for a
        # compatibility of every class of the strain that acts on the substrate.
        for consumer in culture.consuming_pools:
            _emit(
                generated,
                context,
                "process_compatibility",
                _culture_compatibility_mapping(culture, parsed=parsed, namespace=namespace, consumer=consumer),
                origin=origin,
            )


def _culture_report(parsed: _Parsed, *, dataset_id: str) -> tuple[Mapping[str, Any], ...]:
    """One entry per strain and culture substrate: what the culture model of that case is built from."""

    namespace = _Namespace(dataset_id=dataset_id, digest="", manifest={})
    entries: list[Mapping[str, Any]] = []
    for pair, culture in parsed.culture_pairs.items():
        substrate = parsed.substrates[pair[1]]
        for item in parsed.strain_classes:
            if item.class_key != pair[0]:
                continue
            rows = [row.row for row in parsed.culture_rows if row.culture_key == (item.strain_id, pair[1])]
            entries.append(
                MappingProxyType(
                    {
                        "strain_id": item.strain_id,
                        "substrate_id": pair[1],
                        "enzyme_class": pair[0],
                        # Every pool that consumes the substrate, in parallel; enzyme_class is the first of them.
                        "consuming_pools": list(culture.consuming_pools),
                        "enzyme_pools": list(culture.pools),
                        "fungus_id": namespace.id(item.strain_id),
                        "substrate_record_id": substrate.registry_id or namespace.id(pair[1]),
                        "case_template_id": _culture_template_id(namespace, culture),
                        "process_compatibility_id": namespace.id(pair[0], pair[1], USER_DATASET_CULTURE_PROCESS_TYPE),
                        "process_compatibility_ids": [
                            namespace.id(consumer, pair[1], USER_DATASET_CULTURE_PROCESS_TYPE)
                            for consumer in culture.consuming_pools
                        ],
                        "file": CULTURE_TABLE,
                        "rows": rows,
                    }
                )
            )
    return tuple(entries)


def _culture_role_keys(culture: _CulturePair) -> tuple[tuple[str, str], ...]:
    """(quantity, pool class) of every role of a culture model in record order; culture-level roles name the
    first consuming class, and the consumption roles each consuming pool."""

    keys = [(quantity, culture.class_key) for quantity in CULTURE_LEVEL_QUANTITIES]
    keys.extend((quantity, pool) for pool in culture.consuming_pools for quantity in CULTURE_CONSUMPTION_QUANTITIES)
    for pool in culture.pools:
        keys.extend((quantity, pool) for quantity in CULTURE_POOL_QUANTITIES)
    return tuple(keys)


def _culture_role(quantity: str, pool: str, *, several: bool = False) -> str:
    """The template role of a culture quantity: a fixed role, or ``<quantity>__<pool class>`` for a pool quantity.

    With several consuming pools (``several``) each consumption quantity is also per pool; one consuming pool keeps
    the fixed USERDATA-009 roles ``hydrolysis_capacity`` and ``hydrolysis_half_saturation``.
    """

    if several and quantity in CULTURE_CONSUMPTION_QUANTITIES:
        return f"{quantity}__{pool}"
    return _CULTURE_ROLE[quantity] if quantity in _CULTURE_ROLE else f"{quantity}__{pool}"


def _culture_pool_part(culture: _CulturePair, quantity: str, pool: str) -> tuple[str, ...]:
    """The pool in a symbol or record id: for a pool quantity, and for a consumption quantity of several consumers."""

    per_pool = quantity in CULTURE_POOL_QUANTITIES or (culture.several and quantity in CULTURE_CONSUMPTION_QUANTITIES)
    return (pool,) if per_pool else ()


def _culture_symbol(namespace: _Namespace, culture: _CulturePair, quantity: str, pool: str) -> str:
    pool_part = _culture_pool_part(culture, quantity, pool)
    return namespace.id("culture", quantity, *pool_part, culture.class_key, culture.substrate_id)


def _culture_record_id(case: _CultureCase, quantity: str, pool: str) -> str:
    pool_part = _culture_pool_part(case.culture, quantity, pool)
    return case.namespace.id(
        case.strain.strain_id, case.substrate.substrate_id, case.condition.condition_id, "culture", quantity, *pool_part
    )


def _culture_selectors(case: _CultureCase, quantity: str, pool: str) -> dict[str, Any]:
    namespace, substrate = case.namespace, case.substrate
    return {
        "parameter_symbol": _culture_symbol(namespace, case.culture, quantity, pool),
        "process_type": USER_DATASET_CULTURE_PROCESS_TYPE,
        # With several consuming pools the selector is empty: the compatibility of each consuming class selects the
        # one model's records (as for an enzyme network).
        "enzyme_class": None if case.culture.several else namespace.id(case.culture.class_key),
        "substrate_class": substrate.substrate_class,
        "fungus_id": namespace.id(case.strain.strain_id),
        "substrate_id": substrate.registry_id or namespace.id(substrate.substrate_id),
        "environment_id": namespace.id(case.condition.condition_id),
    }


def _culture_label(quantity: str, pool: str, case: _CultureCase) -> str:
    pool_name = case.pool_names[pool]
    labels = {
        "substrate_initial_concentration": "Initial substrate concentration",
        "initial_biomass": "Initial biomass dry mass concentration",
        "biomass_yield": "Biomass yield on consumed substrate",
        "biomass_loss_rate": "Biomass loss rate",
        "induction_half_saturation": "Half-saturation constant of the induction of enzyme production",
        "hydrolysis_capacity": f"Substrate consumption capacity of {pool_name}",
        "hydrolysis_half_saturation": f"Half-saturation constant of substrate consumption by {pool_name}",
        "initial_enzyme_concentration": f"Initial {pool_name} level",
        "specific_production_rate": f"Specific production rate of {pool_name}",
        "enzyme_loss_rate": f"Loss rate of {pool_name}",
    }
    return labels[quantity]


def _culture_parameter_mapping(row: _CultureRow, *, quantity: str, pool: str, case: _CultureCase) -> dict[str, Any]:
    """Map one culture.csv row to the parameter record of its role, at the maturity of its evidence type."""

    strain, substrate, condition, namespace = case.strain, case.substrate, case.condition, case.namespace
    exact = row.value is not None
    confidence = _confidence(row.evidence_type)
    notes = [f"User dataset {namespace.dataset_id}, {CULTURE_TABLE} row {row.row}; evidence type {row.evidence_type}."]
    if row.sd is not None:
        notes.append(f"Reported standard deviation {_number_text(row.sd)} {row.units} (kept as provenance, not sampled).")
    if row.replicates is not None:
        notes.append(f"Replicates: {row.replicates}.")
    value: dict[str, Any] = {
        "kind": "exact" if exact else "range",
        "units": row.units,
        "source": row.source,
        "confidence_level": confidence,
        "notes": " ".join(notes),
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
        "validity_range": _culture_validity_range(case),
        USER_DATASET_PROVENANCE_KEY: namespace.provenance(
            CULTURE_TABLE,
            row.row,
            source=row.source,
            method=row.method or None,
            evidence_type=row.evidence_type,
            sd=row.sd,
            replicates=row.replicates,
            condition_id=condition.condition_id,
            quantity=quantity,
            enzyme_pool=namespace.id(pool) if quantity not in CULTURE_LEVEL_QUANTITIES else None,
        ),
    }
    if row.evidence_type == "estimate":
        provenance["exploratory_prior"] = True
    mapping: dict[str, Any] = {
        "record_id": _culture_record_id(case, quantity, pool),
        "name": (
            f"{_culture_label(quantity, pool, case)} of {strain.name} on {substrate.name} at "
            f"{condition.condition_id} ({namespace.dataset_id})"
        ),
        "maturity": _EVIDENCE_MATURITY[row.evidence_type],
        "provenance": provenance,
        "notes": (
            f"User-supplied {quantity} of the culture model from dataset {namespace.dataset_id} ({CULTURE_TABLE} row "
            f"{row.row}); evidence type {row.evidence_type}."
        ),
        **_culture_selectors(case, quantity, pool),
        "value": value,
        "allowed_use": _allowed_use(row.evidence_type, exact=exact),
    }
    if not exact:
        mapping["range_scope"] = "user_supplied_range"
        mapping["range_interpretation"] = (
            "user_supplied_exploratory_prior_not_literature_curated"
            if row.evidence_type == "estimate"
            else "user_stated_bounds_not_calibrated_uncertainty"
        )
    return mapping


# The dimension and the units wording of each culture gap.
_CULTURE_GAP_DIMENSION = MappingProxyType(
    {
        "substrate_initial_concentration": "dry mass of the solid substrate per volume",
        "initial_biomass": "biomass dry mass per volume, in the units of the initial substrate concentration",
        "biomass_yield": "dimensionless (g biomass dry mass per g dry substrate consumed, between 0 and 1)",
        "biomass_loss_rate": "1/time",
        "induction_half_saturation": "dry mass of the solid substrate per volume",
        "hydrolysis_capacity": "substrate dry mass per time per amount of the consuming enzyme pool",
        "hydrolysis_half_saturation": "dry mass of the solid substrate per volume",
        "initial_enzyme_concentration": "enzyme protein mass per volume or an assay activity per volume",
        "specific_production_rate": "enzyme amount (protein mass or assay activity) per biomass dry mass per time",
        "enzyme_loss_rate": "1/time",
    }
)
_CULTURE_GAP_UNITS_TEXT = MappingProxyType(
    {
        "substrate_initial_concentration": "dry mass per volume, for example g/L",
        "initial_biomass": "biomass dry mass per volume in the units of the initial substrate, for example g/L",
        "biomass_yield": "g/g, dimensionless",
        "biomass_loss_rate": "1/time, for example 1/h",
        "induction_half_saturation": "dry mass per volume, for example g/L",
        "hydrolysis_capacity": "substrate mass per time per enzyme amount, for example g/(FPU h) or g/(mg h)",
        "hydrolysis_half_saturation": "dry mass per volume, for example g/L",
        "initial_enzyme_concentration": "protein mass or assay activity per volume, for example mg/L or FPU/L",
        "specific_production_rate": "enzyme amount per biomass dry mass per time, for example FPU/(g h) or mg/(g h)",
        "enzyme_loss_rate": "1/time, for example 1/h",
    }
)


def _culture_gap_units(quantity: str, rows: Mapping[tuple[str, str], _CultureRow]) -> str | None:
    """Units of a culture gap: the substrate and the biomass share the units the other one states; nothing else is
    guessed."""

    partner = {"initial_biomass": "substrate_initial_concentration", "substrate_initial_concentration": "initial_biomass"}
    other = partner.get(quantity)
    row = None if other is None else rows.get((other, ""))
    return None if row is None else row.units


def _culture_gap_mapping(quantity: str, pool: str, *, case: _CultureCase) -> dict[str, Any]:
    strain, substrate, condition, namespace = case.strain, case.substrate, case.condition, case.namespace
    units = _culture_gap_units(quantity, case.rows)
    dimension = _CULTURE_GAP_DIMENSION[quantity]
    units_text = units if units is not None else _CULTURE_GAP_UNITS_TEXT[quantity]
    pool_row = case.rows.get(("initial_enzyme_concentration", pool))
    if units is None and pool_row is not None and quantity in {"hydrolysis_capacity", "specific_production_rate"}:
        # Name the pool's own amount, so that a rate is not requested per another pool's unit.
        per = (
            "substrate dry mass per time per unit of the pool"
            if quantity == "hydrolysis_capacity"
            else "amount of the pool per biomass dry mass per time"
        )
        units_text = f"{per}; the pool is stated in {pool_row.units}, {CULTURE_TABLE} row {pool_row.row}"

    request = _culture_measurement_request(quantity, pool, case=case, units_text=units_text)
    level = quantity in CULTURE_LEVEL_QUANTITIES
    notes = (
        f"No {CULTURE_TABLE} row gives {quantity}{'' if level else f' of enzyme pool {pool}'} for this culture in "
        f"dataset {namespace.dataset_id}."
    )
    if units is None:
        notes = f"{notes} The value requires the dimension {dimension}."
    genome = case.genomes.get(case.culture.class_key if level else pool)
    return {
        "record_id": f"{_culture_record_id(case, quantity, pool)}__gap",
        "name": (
            f"Missing {_culture_label(quantity, pool, case).lower()} of {strain.name} on {substrate.name} at "
            f"{condition.condition_id} ({namespace.dataset_id})"
        ),
        "maturity": USER_DATASET_MATURITY_GAP,
        "provenance": {
            "source": f"User dataset {namespace.dataset_id} gap analysis",
            "confidence_level": "missing_from_user_dataset",
            "measurement_request": request,
            USER_DATASET_PROVENANCE_KEY: namespace.provenance(
                CULTURE_TABLE,
                None,
                evidence_type="gap",
                quantity=quantity,
                enzyme_pool=None if level else namespace.id(pool),
                condition_id=condition.condition_id,
                required_dimension=dimension,
                **_genome_gap_provenance(genome),
            ),
        },
        "notes": notes,
        **_culture_selectors(case, quantity, pool),
        "value": {
            "kind": "unknown",
            "units": units,
            "source": f"User dataset {namespace.dataset_id} gap analysis",
            "confidence_level": "missing_from_user_dataset",
            "notes": notes,
        },
        "allowed_use": PARAMETER_ALLOWED_USE_GAP_ANALYSIS_ONLY,
    }


def _culture_measurement_request(quantity: str, pool: str, *, case: _CultureCase, units_text: str) -> str:
    """Name the missing role of a culture in plain words: what to measure, of which strain, on what, where."""

    strain, substrate = case.strain.name, case.substrate.name
    where = f"condition {case.condition.condition_id} ({_condition_text(case.condition)})"
    pool_name = case.pool_names[pool]
    requests = {
        "substrate_initial_concentration": (
            f"Specify the initial {substrate} loading of the {strain} culture at {where} ({units_text})."
        ),
        "initial_biomass": (
            f"Measure or specify the initial biomass dry mass concentration (the inoculum) of {strain} on {substrate} "
            f"at {where} ({units_text})."
        ),
        "biomass_yield": (
            f"Measure the biomass yield of {strain} on {substrate} at {where}: grams of biomass dry mass formed per "
            f"gram of dry {substrate} consumed ({units_text})."
        ),
        "biomass_loss_rate": (
            f"Measure the first-order biomass loss rate of {strain} on {substrate} at {where} ({units_text}), for "
            "example from the decline of biomass dry mass once the substrate is exhausted."
        ),
        "induction_half_saturation": (
            f"Measure the {substrate} concentration that half-saturates the induction of enzyme production by "
            f"{strain} at {where} ({units_text}), for example from production rates at low substrate loadings."
        ),
        "hydrolysis_capacity": (
            f"Measure the {substrate} consumption capacity of {pool_name} from {strain} at {where}: the substrate dry "
            f"mass consumed per time per unit of enzyme at saturating substrate ({units_text})."
        ),
        "hydrolysis_half_saturation": (
            f"Measure the {substrate} concentration at which consumption by {pool_name} from {strain} runs at half "
            f"its maximum, at {where} ({units_text})."
        ),
        "initial_enzyme_concentration": (
            f"Measure or specify the initial {pool_name} level of the {strain} culture on {substrate} at {where} "
            f"({units_text})."
        ),
        "specific_production_rate": (
            f"Measure the specific production rate of {pool_name} by {strain} growing on {substrate} at {where}: "
            f"enzyme produced per biomass dry mass per time at inducing substrate levels ({units_text})."
        ),
        "enzyme_loss_rate": (
            f"Measure the first-order loss rate of {pool_name} in the {strain} culture on {substrate} at {where} "
            f"({units_text}), for example from the decay of activity in cell-free broth."
        ),
    }
    request = requests[quantity]
    if case.measured_elsewhere:
        stated = " and ".join(
            f"{condition.condition_id} ({_condition_text(condition)})" for condition in case.measured_elsewhere
        )
        request = (
            f"{request.rstrip('.')}; {CULTURE_TABLE} states values of this culture only at {stated}, and FungMod does "
            "not reuse values stated at another condition."
        )
    level = quantity in CULTURE_LEVEL_QUANTITIES
    return _with_genome_note(request, case.genomes.get(case.culture.class_key if level else pool))


def _culture_validity_range(case: _CultureCase) -> str:
    return (
        f"Condition {case.condition.condition_id}: {_condition_text(case.condition)}; culture of "
        f"{case.strain.strain_id} on {case.substrate.substrate_id} only; no temperature or pH response law is attached."
    )


def _template_text(text: str) -> str:
    """User text inside a template config name, which the assembler formats with ``{fungus_id}``."""

    return text.replace("{", "{{").replace("}", "}}")


def _culture_template_id(namespace: _Namespace, culture: _CulturePair) -> str:
    return namespace.id(culture.class_key, culture.substrate_id, "culture_template")


def _culture_pool_role(culture: _CulturePair, pool: str) -> str:
    """The template state role of an enzyme pool: ``enzyme`` for the consuming pool, ``enzyme_<class>`` otherwise."""

    return "enzyme" if pool == culture.class_key else f"enzyme_{pool}"


def _culture_state_names(culture: _CulturePair, substrate: _Substrate) -> dict[str, str]:
    substrate_key = substrate.registry_id or substrate.substrate_id
    names = {
        "substrate": f"{substrate_key}_concentration",
        "biomass": "biomass_dry_mass_concentration",
        **{_culture_pool_role(culture, pool): f"{pool}_concentration" for pool in culture.pools},
        "ledger_unassimilated_substrate": f"consumed_{substrate_key}_not_retained_as_biomass",
        "ledger_biomass_loss": "biomass_dry_mass_lost",
    }
    return names


_CULTURE_LIMITATIONS = (
    "Nutrient, oxygen, maintenance, pH and morphology dynamics are not represented, and there is no spatial "
    "mycelium; the temperature and pH of the condition are metadata and no environment response law is applied, so "
    "the constants hold at the condition of their rows only.",
    "Enzyme pools keep the units of their culture.csv rows (a protein mass or an assay activity per volume); FungMod "
    "converts no pool between protein mass, assay units and molarity.",
    "Consumed substrate not retained as biomass is an explicit closure ledger, not a measured product; soluble "
    "sugars, respired carbon and secreted protein are not resolved, and the product named in substrates.csv is not "
    "released by the culture.",
    "Only the consuming pool acts on the substrate; every other pool is produced and lost only and has no feedback on "
    "consumption. All pools share one induction half-saturation constant.",
    "The constants are apparent and specific to the strain, the substrate preparation and the culture conditions at "
    "which they were obtained; nothing extrapolates them to another loading, condition or strain.",
)


def _culture_template_mapping(
    culture: _CulturePair,
    *,
    parsed: _Parsed,
    namespace: _Namespace,
    scientific: bool,
) -> dict[str, Any]:
    """The culture_physiology template of one culture model, composed from the registry's generic process laws."""

    info = parsed.classes[culture.class_key]
    substrate = parsed.substrates[culture.substrate_id]
    template_id = _culture_template_id(namespace, culture)
    states = _culture_state_names(culture, substrate)
    simulation = namespace.manifest["simulation"]
    mode = "scientific" if scientific else "exploratory"
    substrate_record_id = substrate.registry_id or namespace.id(substrate.substrate_id)
    initial_state_mapping: dict[str, Any] = {
        "substrate": {"parameter_role": "initial_substrate", "units_from_role": "initial_substrate"},
        "biomass": {"parameter_role": "initial_biomass", "units_from_role": "initial_biomass"},
    }
    for pool in culture.pools:
        role = _culture_role("initial_enzyme_concentration", pool)
        initial_state_mapping[_culture_pool_role(culture, pool)] = {"parameter_role": role, "units_from_role": role}
    for ledger in ("ledger_unassimilated_substrate", "ledger_biomass_loss"):
        initial_state_mapping[ledger] = {"value": 0.0, "units_from_role": "initial_substrate"}
    product_map_id = namespace.id(culture.class_key, culture.substrate_id, "biomass_yield_map")
    if culture.several:
        # One consumption process per consuming pool (CULTURE-002), sharing the biomass-yield product map.
        consumption_templates = [
            _culture_consumption_template(culture, pool, parsed=parsed, namespace=namespace, product_map_id=product_map_id)
            for pool in culture.consuming_pools
        ]
    else:
        consumption_templates = [
            {
                "id": "substrate_consumption",
                "process_type": USER_DATASET_PROCESS_TYPE,
                "state_roles": {"substrate": "substrate", "enzyme": "enzyme", "product": "biomass"},
                "parameter_roles": {"kcat": "hydrolysis_capacity", "km": "hydrolysis_half_saturation"},
                "rate_units_from_state_role": "substrate",
                "product_map": product_map_id,
                "assumptions": [
                    f"Bulk {substrate.name} consumption is proportional to the consuming enzyme pool ({info.name}) "
                    "and saturates in the substrate (consumption = k_h E S / (K_h + S)); the substrate is a suspended "
                    "solid on a dry-mass basis and the law is an apparent bulk law.",
                    "Consumed substrate is converted to biomass dry mass with a constant explicit yield Y; the "
                    "remaining (1 - Y) is booked to an explicit closure ledger, and soluble intermediates are not "
                    "resolved.",
                ],
            }
        ]
    process_templates: list[dict[str, Any]] = [
        *consumption_templates,
        {
            "id": "biomass_loss",
            "process_type": "first_order",
            "state_roles": {"source": "biomass", "product": "ledger_biomass_loss"},
            "parameter_roles": {"rate_constant": "biomass_loss_rate"},
            "assumptions": [
                "Biomass dry mass is lost at a constant first-order rate into an explicit ledger pool; no viability, "
                "lysis or death mechanism is claimed."
            ],
        },
    ]
    for pool in culture.pools:
        role = _culture_pool_role(culture, pool)
        name = parsed.classes[pool].name
        process_templates.append(
            {
                "id": f"enzyme_synthesis__{pool}",
                "process_type": "proportional_synthesis",
                "state_roles": {"producer": "biomass", "inducer": "substrate", "product": role},
                "parameter_roles": {
                    "specific_rate": _culture_role("specific_production_rate", pool),
                    "induction_half_saturation": "induction_half_saturation",
                },
                "rate_units_from_state_role": role,
                "assumptions": [
                    f"{name} is produced in proportion to biomass and saturably induced by the substrate (production "
                    "= q X S / (K_ind + S)) with the culture's one induction constant; the material cost of "
                    "production is not represented."
                ],
            }
        )
        process_templates.append(
            {
                "id": f"enzyme_loss__{pool}",
                "process_type": "first_order",
                "state_roles": {"source": role},
                "parameter_roles": {"rate_constant": _culture_role("enzyme_loss_rate", pool)},
                "assumptions": [
                    f"{name} is lost at a constant first-order rate; no inactive protein pool is represented."
                ],
            }
        )
    enzymes = [
        {
            "id": namespace.id(pool),
            "data": {
                "kind": "enzyme",
                "name": parsed.classes[pool].name,
                "enzyme_class": namespace.id(pool),
                "target_bond_types": list(parsed.classes[pool].target_bond_classes),
                "target_substrate_classes": list(parsed.classes[pool].compatible_substrate_classes),
                "target_substrate_names": [substrate.name] if pool in culture.consuming_pools else [],
                "validity_labels": [USER_DATASET_RECORD_MATURITY, "culture_enzyme_pool"],
                "provenance": {
                    "source": parsed.classes[pool].source,
                    "measurement_method": f"enzyme pool of a user culture ({CULTURE_TABLE})",
                    "confidence_level": "user_supplied",
                    "notes": (
                        "Consumes the substrate."
                        if pool in culture.consuming_pools
                        else "Acts on no modelled state in this culture; it is produced and lost only."
                    )
                    + " The pool keeps the units of its culture.csv rows and is not converted.",
                    "validity_range": f"Culture cases of user dataset {namespace.dataset_id} only",
                    "units": "not_applicable",
                },
                "catalytic_parameters": [],
                "adsorption_parameters": [],
                "parameters": [],
            },
        }
        for pool in culture.pools
    ]
    rows = sorted(
        row.row for row in parsed.culture_rows if parsed.cultured.get(row.culture_key) == culture.class_key
        and row.substrate_id == culture.substrate_id
    )
    through = " and ".join(parsed.classes[pool].name for pool in culture.consuming_pools)
    return {
        "record_id": template_id,
        "case_template_id": template_id,
        "name": f"Culture on {substrate.name} consumed through {through} template ({namespace.dataset_id})",
        "maturity": USER_DATASET_RECORD_MATURITY,
        "provenance": {
            "source": namespace.source,
            "confidence_level": "user_supplied",
            USER_DATASET_PROVENANCE_KEY: namespace.provenance(
                USER_DATASET_MANIFEST,
                None,
                substrate_row=substrate.row,
                culture_rows=rows,
                config_mode_rule=(
                    "scientific only when every parameter record bound to this template is exact and "
                    "scientific-eligible; otherwise exploratory"
                ),
            ),
        },
        "schema_version": CASE_TEMPLATE_SCHEMA_VERSION,
        "process_type": USER_DATASET_CULTURE_PROCESS_TYPE,
        "state_roles": dict(states),
        "initial_state_mapping": initial_state_mapping,
        "product_map": {},
        "stoichiometric_yields": {},
        "time_grid": {
            "start": 0.0,
            "stop": float(simulation["duration"]),
            "points": int(simulation["points"]),
            "units": str(simulation["units"]),
            "notes": f"From the simulation block of user dataset {namespace.dataset_id}.",
        },
        "observable_roles": [*states, "degradation_rate"],
        "output_state_roles": dict(states),
        "process_state_metadata": {
            "config_name": (
                f"User dataset {namespace.dataset_id}: culture of {{fungus_id}} on {_template_text(substrate.name)}, "
                f"consumed through {_template_text(through)}"
            ),
            "config_mode": mode,
            "config_maturity": mode,
            "parameter_set_id": namespace.id(culture.class_key, culture.substrate_id, "culture_parameters"),
            "public_path": True,
            # Concentration-only: the culture model reads no vessel volume, so none is claimed.
            "geometry": None,
            "entities": {
                "substrates": [
                    {
                        "id": substrate_record_id,
                        "loader": "generic_solid",
                        "data": {
                            "kind": "substrate",
                            "name": substrate.name,
                            "substrate_type": "generic_solid",
                            "chemical_class": substrate.substrate_class,
                            "physical_state": substrate.physical_state,
                            "bond_types": list(substrate.bond_classes),
                            "accessible_bonds": list(substrate.bond_classes),
                            "required_enzyme_classes": [namespace.id(pool) for pool in culture.consuming_pools],
                            "degradation_products": [],
                            "completeness": "partial",
                            "default_degradation_model": "unknown",
                            "water_activity_dependence": "unknown",
                            "provenance": {
                                "source": substrate.source,
                                "confidence_level": "user_supplied",
                                "notes": (
                                    f"Suspended {substrate.physical_state} substrate represented as a bulk dry mass "
                                    "per volume; surface area, crystallinity and particle size are not modelled."
                                ),
                            },
                            "parameters": [],
                        },
                    }
                ],
                "enzymes": enzymes,
            },
            "state_species": {
                "substrate": {"entity_type": "substrate", "species": substrate_record_id},
                "biomass": {"entity_type": "organism", "species": namespace.id("culture_strain")},
                **{
                    _culture_pool_role(culture, pool): {"entity_type": "enzyme", "species": namespace.id(pool)}
                    for pool in culture.pools
                },
                "ledger_unassimilated_substrate": {
                    "entity_type": "ledger",
                    "species": states["ledger_unassimilated_substrate"],
                },
                "ledger_biomass_loss": {"entity_type": "ledger", "species": states["ledger_biomass_loss"]},
            },
            "product_maps": [
                {
                    "id": product_map_id,
                    "name": (
                        f"{substrate.name} consumption to biomass with an explicit yield and a closure ledger "
                        f"({namespace.dataset_id})"
                    ),
                    "product_map_type": "stoichiometric",
                    "reactants": {"substrate": 1.0},
                    "products": {
                        "biomass": {"parameter_role": "biomass_yield"},
                        "ledger_unassimilated_substrate": {"complement_of_parameter_role": "biomass_yield"},
                    },
                    "notes": (
                        f"One gram of consumed dry {substrate.name} forms Y gram of biomass dry mass; the remaining "
                        "(1 - Y) gram is booked to an explicit ledger of consumed substrate not retained as biomass, "
                        "which closes the dry-mass balance."
                    ),
                }
            ],
            "process_templates": process_templates,
            "conservation": {
                "id": "dry_mass_closure_ledger",
                "closed_system": True,
                "state_weights": {
                    "substrate": 1.0,
                    "biomass": 1.0,
                    "ledger_unassimilated_substrate": 1.0,
                    "ledger_biomass_loss": 1.0,
                },
            },
        },
        "limitations": (
            [
                (
                    f"Well-mixed batch culture of one strain on the suspended {substrate.physical_state} substrate "
                    f"{substrate.substrate_id} (dry-mass basis) from user dataset {namespace.dataset_id}, composed "
                    "from the registry's culture_physiology process laws: substrate consumption by one enzyme pool "
                    "with an explicit biomass yield, first-order biomass loss, biomass-proportional substrate-induced "
                    "synthesis and first-order loss of each enzyme pool."
                ),
                *_CULTURE_LIMITATIONS,
            ]
            if not culture.several
            else _several_consumer_limitations(culture, parsed=parsed, namespace=namespace)
        ),
        "validity_notes": [
            f"Values come from user dataset {namespace.dataset_id} (sha256 {namespace.digest}); FungMod did not "
            "check them against an external source.",
            "Every substrate-side amount and the biomass are dry masses per volume in one unit, hydrolysis_capacity "
            "and specific_production_rate were checked with pint against the case's own pool and biomass units, and "
            "no molar mass, hydration factor or conversion between assay units and protein mass was applied.",
        ],
        "notes": (
            f"Culture-physiology template generated from user dataset {namespace.dataset_id} for enzyme class "
            f"{culture.class_key} consuming substrate {culture.substrate_id}; enzyme pools "
            f"{', '.join(culture.pools)}."
            if not culture.several
            else f"Culture-physiology template generated from user dataset {namespace.dataset_id} for the enzyme "
            f"classes {', '.join(culture.consuming_pools)} consuming substrate {culture.substrate_id} in parallel; "
            f"enzyme pools {', '.join(culture.pools)}."
        ),
    }


def _culture_consumption_template(
    culture: _CulturePair,
    pool: str,
    *,
    parsed: _Parsed,
    namespace: _Namespace,
    product_map_id: str,
) -> dict[str, Any]:
    """The consumption process of one of several consuming pools: the same law and product map as one pool's."""

    substrate = parsed.substrates[culture.substrate_id]
    name = parsed.classes[pool].name
    return {
        "id": f"substrate_consumption__{pool}",
        "enzyme_class": namespace.id(pool),
        "process_type": USER_DATASET_PROCESS_TYPE,
        "state_roles": {"substrate": "substrate", "enzyme": _culture_pool_role(culture, pool), "product": "biomass"},
        "parameter_roles": {
            "kcat": _culture_role("hydrolysis_capacity", pool, several=True),
            "km": _culture_role("hydrolysis_half_saturation", pool, several=True),
        },
        "rate_units_from_state_role": "substrate",
        "product_map": product_map_id,
        "assumptions": [
            f"Bulk {substrate.name} consumption by {name} is proportional to that pool and saturates in the substrate "
            "(its own k_h E S / (K_h + S)); the substrate is a suspended solid on a dry-mass basis and the law is an "
            "apparent bulk law.",
            f"{name} acts independently of the other consuming pools of the culture: their consumption rates add, "
            "with no competition for substrate or adsorption sites and no synergy.",
            "Consumed substrate is converted to biomass dry mass with the culture's one explicit yield Y, whichever "
            "pool consumed it; the remaining (1 - Y) is booked to an explicit closure ledger, and soluble "
            "intermediates are not resolved.",
        ],
    }


def _several_consumer_limitations(culture: _CulturePair, *, parsed: _Parsed, namespace: _Namespace) -> list[str]:
    """The limitations of a culture whose substrate is consumed by several pools in parallel (CULTURE-002)."""

    substrate = parsed.substrates[culture.substrate_id]
    consumers = ", ".join(parsed.classes[pool].name for pool in culture.consuming_pools)
    others = [parsed.classes[pool].name for pool in culture.pools if pool not in culture.consuming_pools]
    return [
        (
            f"Well-mixed batch culture of one strain on the suspended {substrate.physical_state} substrate "
            f"{substrate.substrate_id} (dry-mass basis) from user dataset {namespace.dataset_id}, composed from the "
            "registry's culture_physiology process laws: substrate consumption by several enzyme pools in parallel "
            f"({consumers}), each by its own saturation law, with one explicit biomass yield, first-order biomass "
            "loss, biomass-proportional substrate-induced synthesis and first-order loss of each enzyme pool."
        ),
        _CULTURE_LIMITATIONS[0],
        _CULTURE_LIMITATIONS[1],
        _CULTURE_LIMITATIONS[2],
        (
            "The consuming pools act on the substrate additively and independently: their consumption rates add, "
            "with no competition for substrate or adsorption sites, no synergy (for example endo- and exo-acting "
            "cooperation) and no product inhibition; every consumed gram feeds growth through the one yield, "
            "whichever pool consumed it. "
            + (
                f"The other pools ({', '.join(others)}) are produced and lost only and have no feedback on "
                "consumption. "
                if others
                else ""
            )
            + "All pools share one induction half-saturation constant."
        ),
        (
            "Released soluble products are not resolved and do not feed growth: FungMod has no uptake law for a "
            "soluble pool with an explicit yield that culture.csv binds, so a culture is not combined with an "
            "enzyme network and no pool acts on a product of another."
        ),
        _CULTURE_LIMITATIONS[4],
    ]


def _culture_compatibility_mapping(
    culture: _CulturePair,
    *,
    parsed: _Parsed,
    namespace: _Namespace,
    consumer: str,
) -> dict[str, Any]:
    """The compatibility of one consuming class of a culture model; every one points to the model's template."""

    info = parsed.classes[consumer]
    substrate = parsed.substrates[culture.substrate_id]
    symbols = {
        _culture_role(quantity, pool, several=culture.several): _culture_symbol(namespace, culture, quantity, pool)
        for quantity, pool in _culture_role_keys(culture)
    }
    notes = (
        f"Culture-physiology compatibility generated from user dataset {namespace.dataset_id}: every strain that "
        f"declares {culture.class_key} grows on {substrate.substrate_id} and secretes the enzyme pools "
        f"{', '.join(culture.pools)}; the class consumes the substrate through the bond classes listed."
        if not culture.several
        else f"Culture-physiology compatibility generated from user dataset {namespace.dataset_id}: every strain that "
        f"declares {consumer} grows on {substrate.substrate_id} and secretes the enzyme pools "
        f"{', '.join(culture.pools)}, of which {', '.join(culture.consuming_pools)} consume the substrate in "
        f"parallel; {consumer} acts on it through the bond classes listed. Every consuming class has such a record, "
        "all pointing to the one culture template."
    )
    return {
        "record_id": namespace.id(consumer, culture.substrate_id, USER_DATASET_CULTURE_PROCESS_TYPE),
        "name": f"{info.name} on {substrate.name} culture physiology ({namespace.dataset_id})",
        "maturity": USER_DATASET_RECORD_MATURITY,
        "provenance": {
            "source": namespace.source,
            "confidence_level": "user_supplied",
            USER_DATASET_PROVENANCE_KEY: namespace.provenance("substrates.csv", substrate.row),
        },
        "enzyme_class": namespace.id(consumer),
        "substrate_class": substrate.substrate_class,
        "required_bond_classes": list(_shared_bonds(info, substrate) or ()),
        "process_type": USER_DATASET_CULTURE_PROCESS_TYPE,
        "required_parameters": list(symbols.values()),
        "parameter_roles": dict(symbols),
        "product_map_required": True,
        "case_template_id": _culture_template_id(namespace, culture),
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# Enzyme networks: several enzyme classes acting together on a chain of pools


_NETWORK_ENTRY_COLUMN = f"{NETWORK_MANIFEST_FIELD}.{NETWORK_ENTRY_FIELD}"
_NETWORK_INITIAL_ROLE = "substrate_initial_concentration"
_NETWORK_TABLE_REFUSALS = (
    (
        CULTURE_TABLE,
        "culture_rows",
        "culture.csv is not combined with enzyme_network in this version. The secreted pools of a culture act "
        "together in culture.csv itself: every pool whose class acts on the culture substrate consumes it, in "
        "parallel, and the consumed substrate feeds growth through the culture's one yield. A network's released "
        "pools cannot be part of a growing culture: FungMod has no uptake law for a released soluble pool with an "
        "explicit yield, so the substrate a pool releases would either be counted twice (as biomass and as the "
        "released pool) or feed nothing, and splitting it between them is a partition no table states. Keep "
        "cultures in a dataset without enzyme_network.",
    ),
    (
        TIMECOURSE_TABLE,
        "timecourses",
        "timecourse.csv is not combined with enzyme_network in this version: the comparison and the fit read the "
        "substrate and product of a single-class case, and the intermediate pools of a network are not observables "
        "of either yet.",
    ),
)


def _validate_networks(parsed: _Parsed, context: _Context) -> None:
    """Build the enzyme network of every entry substrate and refuse what a network cannot run.

    Links between pools come only from explicit data: a substrate's
    substrates.csv product that equals another substrate_id. The members of a
    network are the dataset's declared classes that act on one of its pools by
    the categorical rule; each runs one Michaelis-Menten process on its pool in
    its pair's rate form. A link from a solid pool to a dissolved pool (or a
    molar final product) needs the solid's unit-bearing yield. Refused: tables
    not combined with networks yet, unknown entries, cycles, ambiguous products,
    links across amount bases without a unit-bearing yield (and from a
    dissolved pool to a solid one), a unit-bearing yield on a same-basis link or
    outside a network, a class on two pools of one network, strains with
    different member classes, the
    pH-ionization form, initial amounts, doses and reactivity exponents on
    intermediate pools, disagreeing initial concentrations of an entry, unused
    substrates, colliding state names, and ki rows that name no downstream pool,
    several inhibitors of one process or no network at all.
    """

    if parsed.network_entries is None:
        return
    if not parsed.network_entries:
        for substrate in parsed.substrates.values():
            if substrate.yield_units:
                context.add(
                    "substrates.csv",
                    substrate.row,
                    "yield_basis",
                    f"yield_basis {substrate.yield_units!r} is a unit-bearing yield (an amount of product per dry mass), "
                    "which links a solid pool to a dissolved pool of an enzyme network; this version supports it in "
                    f"network datasets only (declare {NETWORK_MANIFEST_FIELD} with {NETWORK_ENTRY_FIELD} in "
                    f"user_dataset.yml). A single-class case on a solid states its product in g/g.",
                )
        for row in parsed.kinetics:
            if row.quantity == INHIBITION_CONSTANT_QUANTITY:
                context.add(
                    "kinetics.csv",
                    row.row,
                    "quantity",
                    "ki binds competitive product inhibition to a process of an enzyme network, which this version "
                    f"supports in network datasets only: declare {NETWORK_MANIFEST_FIELD} with {NETWORK_ENTRY_FIELD} "
                    "in user_dataset.yml (a network of one enzyme class is the single-class case with inhibition).",
                )
        return
    for file, attribute, message in _NETWORK_TABLE_REFUSALS:
        if getattr(parsed, attribute):
            context.add(file, None, None, message)
    entries = [entry for entry in parsed.network_entries if entry in parsed.substrates]
    for entry in parsed.network_entries:
        if entry not in parsed.substrates:
            context.add(
                USER_DATASET_MANIFEST,
                None,
                _NETWORK_ENTRY_COLUMN,
                f"Entry substrate {entry!r} is not a substrate_id of substrates.csv.",
            )
    # Each substrate's link, decided once: (accepted, the pool its product releases or None for a final product).
    links: dict[str, tuple[bool, str | None]] = {}
    chains: dict[str, tuple[tuple[str, ...], str]] = {}
    reported_cycles: set[frozenset[str]] = set()
    for entry in entries:
        chain = _follow_network_links(parsed, entry, links, reported_cycles, context)
        if chain is not None:
            chains[entry] = chain
    class_order = list(dict.fromkeys(item.class_key for item in parsed.strain_classes))
    intermediates = {pool for pools, _product in chains.values() for pool in pools[1:]}
    in_networks = {pool for pools, _product in chains.values() for pool in pools}
    for substrate in parsed.substrates.values():
        if len(chains) == len(entries) and substrate.substrate_id not in in_networks:
            context.add(
                "substrates.csv",
                substrate.row,
                "substrate_id",
                f"Substrate {substrate.substrate_id!r} is part of no enzyme network: it is no entry substrate and no "
                f"entry's chain of products reaches it. List it in {NETWORK_ENTRY_FIELD} or remove it; a network "
                "dataset simulates networks only.",
            )
    _refuse_intermediate_rows(parsed, context, entries=set(entries), intermediates=intermediates)
    reported_classes: set[tuple[str, tuple[str, ...]]] = set()
    reported_strains: set[tuple[str, tuple[str, ...]]] = set()
    for entry, (pools, product) in chains.items():
        network = _network_members(
            parsed,
            context,
            entry=entry,
            pools=pools,
            product=product,
            class_order=class_order,
            intermediates=intermediates,
            reported_classes=reported_classes,
            reported_strains=reported_strains,
        )
        if network is not None:
            parsed.networks[entry] = network
    _validate_network_inhibitors(parsed, context)
    _bind_network_laws(parsed)


def _follow_network_links(
    parsed: _Parsed,
    entry: str,
    links: dict[str, tuple[bool, str | None]],
    reported_cycles: set[frozenset[str]],
    context: _Context,
) -> tuple[tuple[str, ...], str] | None:
    """Follow substrates.csv products from ``entry``: (pools, final product), or None after a refusal."""

    pools = [entry]
    while True:
        substrate = parsed.substrates[pools[-1]]
        if substrate.substrate_id not in links:
            links[substrate.substrate_id] = _network_link(parsed, substrate, context)
        accepted, target = links[substrate.substrate_id]
        if not accepted:
            return None
        if target is None:
            return tuple(pools), substrate.product
        if target in pools:
            cycle = frozenset(pools[pools.index(target) :])
            if cycle not in reported_cycles:
                reported_cycles.add(cycle)
                context.add(
                    "substrates.csv",
                    substrate.row,
                    "product",
                    f"Substrate {substrate.substrate_id!r} releases {target!r}, which is already a pool of the "
                    f"enzyme network that starts from {entry!r} ({' -> '.join((*pools, target))}): the links form a "
                    "cycle. A network's pools are released one into the next and FungMod does not break a cycle; "
                    "change the product of one of these substrates.",
                )
            return None
        pools.append(target)


def _network_link(parsed: _Parsed, substrate: _Substrate, context: _Context) -> tuple[bool, str | None]:
    """Whether a substrate's product is accepted, and the pool it releases (None: the network's final product)."""

    product = substrate.product
    for other in parsed.substrates.values():
        if other.registry_id == product and other.substrate_id != product:
            context.add(
                "substrates.csv",
                substrate.row,
                "product",
                f"The product {product!r} of substrate {substrate.substrate_id!r} is the registry substrate of "
                f"substrates.csv row {other.row} (substrate_id {other.substrate_id!r}) but not a substrate_id. An "
                "enzyme network links a product to a pool only when it equals a substrate_id, and FungMod does not "
                f"guess which was meant: write the product as {other.substrate_id!r} to release that pool, or give "
                "the product another name to keep it the network's final product.",
            )
            return False, None
    if product not in parsed.substrates:
        # The final product: a unit-bearing yield releases it as an amount per volume, a g/g yield as a dry mass.
        return True, None
    target = parsed.substrates[product]
    if not substrate.is_solid and target.is_solid:
        context.add(
            "substrates.csv",
            substrate.row,
            "product",
            f"Substrate {substrate.substrate_id!r} ({_basis_text(substrate)}) releases {product!r}, a "
            f"{_basis_text(target)} substrate. An enzyme network links a dissolved pool only to dissolved pools: "
            "forming a solid from a dissolved pool is not supported in this version. Give the product another name "
            "so that it stays the network's final product.",
        )
        return False, None
    if substrate.is_solid and not target.is_solid and not substrate.yield_units:
        context.add(
            "substrates.csv",
            substrate.row,
            "yield_basis",
            f"Substrate {substrate.substrate_id!r} ({_basis_text(substrate)}) releases {product!r}, a "
            f"{_basis_text(target)} substrate, with a {substrate.yield_basis} yield. Linking a dry-mass pool to an "
            "amount-per-volume pool needs a unit-bearing yield that converts the dry mass consumed into the amount "
            "released: state it in yield_basis as an amount of product per dry mass (for example mmol/g, which you "
            f"may compute from molar masses and say so) with {YIELD_EVIDENCE_COLUMN} and, for a measured or "
            f"literature value, {YIELD_METHOD_COLUMN}. FungMod never derives it from a molar mass.",
        )
        return False, None
    if substrate.yield_units and target.is_solid:
        context.add(
            "substrates.csv",
            substrate.row,
            "yield_basis",
            f"Substrate {substrate.substrate_id!r} releases {product!r}, another solid pool on a dry-mass basis, but "
            f"states a unit-bearing yield ({substrate.yield_units}). A link between pools on one basis takes the "
            f"pure-number yield of that basis ({_SOLID_YIELD_BASIS}); a unit-bearing yield converts a dry mass into "
            "the amount of a dissolved pool only.",
        )
        return False, None
    return True, product


def _basis_text(substrate: _Substrate) -> str:
    if substrate.is_solid:
        return f"{substrate.physical_state}, dry mass per volume, yield {substrate.yield_basis}"
    return f"{substrate.physical_state}, amount per volume, yield {_YIELD_BASIS}"


def _refuse_intermediate_rows(
    parsed: _Parsed,
    context: _Context,
    *,
    entries: set[str],
    intermediates: set[str],
) -> None:
    """Refuse kinetics.csv rows that would set an intermediate pool's own initial amount or reference."""

    for row in parsed.kinetics:
        if row.substrate_id not in intermediates:
            continue
        if row.quantity == "substrate_initial_concentration" and row.substrate_id not in entries:
            context.add(
                "kinetics.csv",
                row.row,
                "quantity",
                f"Substrate {row.substrate_id!r} is an intermediate pool of an enzyme network: it is released by the "
                "network and starts at zero, so it takes no initial concentration. List it in "
                f"{NETWORK_ENTRY_FIELD} to start a network of its own from this initial concentration.",
            )
        elif row.quantity in {"enzyme_dose", REACTIVITY_EXPONENT_ROLE}:
            what = (
                "an enzyme_dose multiplies the pool's own initial loading"
                if row.quantity == "enzyme_dose"
                else "a reactivity_exponent refers to the pool's own initial amount (S / S0)^n"
            )
            context.add(
                "kinetics.csv",
                row.row,
                "quantity",
                f"Substrate {row.substrate_id!r} is an intermediate pool of an enzyme network, which starts at zero; "
                f"{what}, which an intermediate does not have. Give the enzyme as enzyme_concentration, and leave "
                "the reactivity factor to entry pools.",
            )


def _network_members(
    parsed: _Parsed,
    context: _Context,
    *,
    entry: str,
    pools: tuple[str, ...],
    product: str,
    class_order: Sequence[str],
    intermediates: set[str],
    reported_classes: set[tuple[str, tuple[str, ...]]],
    reported_strains: set[tuple[str, tuple[str, ...]]],
) -> _Network | None:
    """The member classes, processes, strains and entry rows of one network, refusing what it cannot run."""

    count = len(context.issues)
    acting = {
        pool: [class_key for class_key in class_order if _shared_bonds(parsed.classes[class_key], parsed.substrates[pool])]
        for pool in pools
    }
    for class_key in class_order:
        on = tuple(pool for pool in pools if class_key in acting[pool])
        if len(on) > 1 and (class_key, on) not in reported_classes:
            reported_classes.add((class_key, on))
            file, row = _first_class_row(parsed, class_key)
            context.add(
                file,
                row,
                "enzyme_class",
                f"Enzyme class {class_key!r} acts on {len(on)} pools of the enzyme network that starts from "
                f"{entry!r} ({', '.join(on)}). One enzyme acting on two substrates of one system competes for its "
                "active site, which independent Michaelis-Menten processes do not represent, and FungMod binds no "
                "competing-substrate law yet. Narrow the class's compatible substrate classes, or run the pools in "
                "separate datasets.",
            )
    if not acting[entry]:
        context.add(
            USER_DATASET_MANIFEST,
            None,
            _NETWORK_ENTRY_COLUMN,
            f"No declared enzyme class acts on entry substrate {entry!r}, so the network that starts from it has no "
            "process; declare a class that acts on it, or remove the entry.",
        )
    members = tuple(class_key for class_key in class_order if any(class_key in acting[pool] for pool in pools))
    declared: dict[str, set[str]] = {}
    for item in parsed.strain_classes:
        declared.setdefault(item.strain_id, set()).add(item.class_key)
    strains: list[str] = []
    for strain in parsed.strains.values():
        have = declared.get(strain.strain_id, set()).intersection(members)
        if not have:
            continue
        strains.append(strain.strain_id)
        missing = tuple(class_key for class_key in members if class_key not in have)
        if missing and (strain.strain_id, missing) not in reported_strains:
            reported_strains.add((strain.strain_id, missing))
            context.add(
                "strains.csv",
                strain.row,
                "strain_id",
                f"Strain {strain.strain_id!r} declares {', '.join(sorted(have))} of the enzyme network that starts "
                f"from {entry!r} but not {', '.join(missing)}. One network serves every strain of a dataset (FungMod "
                "selects a process by enzyme class and substrate class), so its strains must declare the same "
                "classes; put strains with other enzyme sets in separate datasets.",
            )
    processes: list[_NetworkProcess] = []
    for pool in pools:
        for class_key in acting[pool]:
            pair = (class_key, pool)
            form = _pair_form(parsed, pair)
            if form == RATE_FORM_PH_IONIZATION:
                rows = [row for row in parsed.kinetics if row.pair_key == pair and row.quantity in PH_IONIZATION_QUANTITIES]
                file, line = ("kinetics.csv", min(row.row for row in rows)) if rows else _first_class_row(parsed, class_key)
                context.add(
                    file,
                    line,
                    "quantity" if rows else "enzyme_class",
                    f"Enzyme class {class_key!r} runs the pH-ionization form on {pool!r}, which an enzyme network does "
                    "not bind in this version (its processes are homogeneous Michaelis-Menten laws in the kcat or "
                    "Vmax form). Run pH-ionization cases in a dataset without enzyme_network.",
                )
                continue
            reactive = pair in parsed.reactivity_pairs and pool == entry and pool not in intermediates
            processes.append(_NetworkProcess(class_key=class_key, pool=pool, form=form, reactive=reactive))
    entry_rows = _network_entry_rows(parsed, context, entry=entry, classes=acting[entry], strains=strains)
    names: dict[str, str] = {}
    for role, state in _network_state_names(parsed, pools, product, processes).items():
        if state in names:
            context.add(
                USER_DATASET_MANIFEST,
                None,
                _NETWORK_ENTRY_COLUMN,
                f"The enzyme network that starts from {entry!r} would give the state {state!r} to both {names[state]} "
                f"and {role}; rename a substrate, product or enzyme class.",
            )
        names[state] = role
    if len(context.issues) > count:
        return None
    return _Network(
        entry=entry,
        pools=pools,
        product=product,
        processes=tuple(processes),
        classes=members,
        strains=tuple(strains),
        entry_rows=MappingProxyType(entry_rows),
        unit_bearing_yield_pools=tuple(pool for pool in pools if parsed.substrates[pool].yield_units),
    )


def _network_entry_rows(
    parsed: _Parsed,
    context: _Context,
    *,
    entry: str,
    classes: Sequence[str],
    strains: Sequence[str],
) -> dict[tuple[str, str], _Kinetics]:
    """The entry's initial-concentration row per (strain, condition); the rows of its classes must agree."""

    by_case: dict[tuple[str, str], list[_Kinetics]] = {}
    for row in parsed.kinetics:
        if (
            row.quantity == "substrate_initial_concentration"
            and row.substrate_id == entry
            and row.class_key in classes
            and row.strain_id in strains
        ):
            by_case.setdefault((row.strain_id, row.condition_id), []).append(row)
    chosen: dict[tuple[str, str], _Kinetics] = {}
    for key, rows in by_case.items():
        ordered = sorted(rows, key=lambda item: (list(classes).index(item.class_key), item.row))
        first = ordered[0]
        for other in ordered[1:]:
            if (other.value, other.lower, other.upper, other.units) != (first.value, first.lower, first.upper, first.units):
                context.add(
                    "kinetics.csv",
                    other.row,
                    "value",
                    f"Rows {first.row} and {other.row} give different initial concentrations of {entry!r} for strain "
                    f"{key[0]!r} at condition {key[1]!r} ({_kinetics_value_text(first)} and "
                    f"{_kinetics_value_text(other)}). The classes of an enzyme network act on one pool, whose initial "
                    "concentration is one value; state it identically (value or range and units) on every class's row.",
                )
        chosen[key] = first
    return chosen


def _validate_network_inhibitors(parsed: _Parsed, context: _Context) -> None:
    """A ki row names a pool released downstream of its own pool; one inhibitor per process."""

    processes = {
        (process.class_key, process.pool): network
        for network in parsed.networks.values()
        for process in network.processes
    }
    inhibitors: dict[tuple[str, str], tuple[str, int]] = {}
    for row in parsed.kinetics:
        if row.quantity != INHIBITION_CONSTANT_QUANTITY:
            continue
        network = processes.get(row.pair_key)
        if network is None:
            # The pair belongs to a network refused above, or to none; the refusal names the reason.
            continue
        downstream = network.downstream(row.substrate_id)
        if row.inhibitor not in downstream:
            context.add(
                "kinetics.csv",
                row.row,
                INHIBITOR_COLUMN,
                f"inhibitor {row.inhibitor!r} is not a pool the enzyme network releases downstream of "
                f"{row.substrate_id!r} (released after it: {', '.join(downstream)}). ki binds competitive inhibition "
                "of a process by a product of the network; inhibition by the substrate itself or by an upstream pool "
                "is another law, which FungMod does not bind.",
            )
            continue
        bound = inhibitors.setdefault(row.pair_key, (row.inhibitor, row.row))
        if bound[0] != row.inhibitor:
            context.add(
                "kinetics.csv",
                row.row,
                INHIBITOR_COLUMN,
                f"Row {bound[1]} names {bound[0]!r} as the inhibitor of {row.class_key!r} on {row.substrate_id!r} and "
                f"row {row.row} names {row.inhibitor!r}. One process takes one competitive inhibitor: the core binds "
                "at most one competitive-inhibition law to a process and composes no two of them, and every strain "
                "and condition of a process shares one template.",
            )
    for network in list(parsed.networks.values()):
        network_processes = tuple(
            replace(process, inhibitor=inhibitors.get((process.class_key, process.pool), ("", 0))[0])
            for process in network.processes
        )
        parsed.networks[network.entry] = replace(network, processes=network_processes)


def _bind_network_laws(parsed: _Parsed) -> None:
    """Bind each valid responses.csv law to the network process of its enzyme class and pool.

    ``parsed.laws`` holds the laws that passed the single-class rules (every
    parameter once, the law's own domain, one law per condition, the same law
    for a condition across the strains of a class and pool, kinetic constants
    and Ki at the reference condition). A responses.csv row names a strain, a
    class the strain declares and a substrate the class acts on, so in a network
    dataset it names the process of that class on that pool; the law then
    scales that process only, in every network that runs it (an intermediate
    that is also an entry runs it in both). Every strain of the network that
    binds no law another strain binds gets explicit gaps for the law's
    parameters when the records are generated. A binding whose process belongs
    to a refused network has no process here; the network's refusal names the
    reason. The enzyme inactivation of the class on its pool (USERDATA-011) is
    bound the same way: ``inactivation`` names the loss law of the process's
    enzyme state, and the thermal_inactivation law is not one of its rate laws.
    """

    for entry, network in list(parsed.networks.items()):
        processes = tuple(
            replace(
                process,
                laws=tuple(
                    law.law
                    for law in _pair_laws(parsed, (process.class_key, process.pool))
                    if law.scales == LAW_SCALES_RATE
                ),
                inactivation=parsed.inactivation_pairs.get((process.class_key, process.pool), ""),
            )
            for process in network.processes
        )
        parsed.networks[entry] = replace(network, processes=processes)


def _network_pool_role(network_pools: Sequence[str], pool: str) -> str:
    """The template state role of a pool: ``substrate`` for the entry, ``intermediate_<position>`` after it."""

    position = list(network_pools).index(pool)
    return "substrate" if position == 0 else f"intermediate_{position}"


def _network_enzyme_role(class_key: str) -> str:
    return f"enzyme_{class_key}"


def _network_next_role(network: _Network, pool: str) -> str:
    position = network.pools.index(pool)
    return "product" if position == len(network.pools) - 1 else _network_pool_role(network.pools, network.pools[position + 1])


def _network_inhibitor_role(network: _Network, inhibitor: str) -> str:
    return "product" if inhibitor == network.product else _network_pool_role(network.pools, inhibitor)


def _network_state_names(
    parsed: _Parsed,
    pools: Sequence[str],
    product: str,
    processes: Sequence[_NetworkProcess],
) -> dict[str, str]:
    names = {
        _network_pool_role(pools, pool): f"{parsed.substrates[pool].registry_id or pool}_concentration" for pool in pools
    }
    names["product"] = f"{product}_concentration"
    for process in processes:
        if process.form in _ENZYME_FORMS:
            names[_network_enzyme_role(process.class_key)] = f"{process.class_key}_concentration"
    return names


def _network_roles(network: _Network) -> tuple[tuple[str, str, str, str], ...]:
    """(template role, kinetics quantity, enzyme class, pool) of every parameter role of a network, in record order."""

    roles: list[tuple[str, str, str, str]] = [(_NETWORK_INITIAL_ROLE, "substrate_initial_concentration", "", network.entry)]
    roles.extend(
        (_network_yield_role(pool), NETWORK_YIELD_QUANTITY, "", pool) for pool in network.unit_bearing_yield_pools
    )
    for process in network.processes:
        key, pool = process.class_key, process.pool
        roles.append((f"km__{key}__{pool}", "km", key, pool))
        if process.form == RATE_FORM_KCAT:
            roles.append((f"kcat__{key}__{pool}", "kcat", key, pool))
            roles.append((f"enzyme_initial_concentration__{key}", "enzyme_concentration", key, pool))
        else:
            roles.append((f"vmax__{key}__{pool}", "vmax", key, pool))
        if process.reactive:
            roles.append((f"{REACTIVITY_EXPONENT_ROLE}__{key}__{pool}", REACTIVITY_EXPONENT_ROLE, key, pool))
        if process.inhibitor:
            roles.append((f"ki__{key}__{pool}", INHIBITION_CONSTANT_QUANTITY, key, pool))
        if process.inactivation:
            roles.append((_network_inactivation_role(process), INACTIVATION_RATE_QUANTITY, key, pool))
    return tuple(roles)


def _network_inactivation_role(process: _NetworkProcess) -> str:
    return f"{INACTIVATION_RATE_QUANTITY}__{process.class_key}__{process.pool}"


def _network_law_role(law_name: str, parameter: ResponseLawParameter, process: _NetworkProcess) -> str:
    return f"{law_name}__{parameter.name}__{process.class_key}__{process.pool}"


def _network_process_laws(process: _NetworkProcess) -> tuple[str, ...]:
    """Every responses.csv law of a network process: its rate laws, then the inactivation law of its enzyme state."""

    return (*process.laws, *((INACTIVATION_LAW,) if process.inactivation == INACTIVATION_LAW else ()))


def _network_law_roles(network: _Network) -> tuple[tuple[str, ResponseLaw, ResponseLawParameter, str, str], ...]:
    """(template role, law, law parameter, enzyme class, pool) of every response-law parameter of a network.

    A role is ``<law>__<parameter>__<class>__<pool>``: one law per condition and process, so a process's roles never
    collide, and they never share a name with a kinetics role (which starts with the kinetics quantity).
    """

    roles: list[tuple[str, ResponseLaw, ResponseLawParameter, str, str]] = []
    for process in network.processes:
        for law_name in _network_process_laws(process):
            law = RESPONSE_LAWS[law_name]
            roles.extend(
                (_network_law_role(law.law, parameter, process), law, parameter, process.class_key, process.pool)
                for parameter in law.parameters
            )
    return tuple(roles)


def _network_yield_role(pool: str) -> str:
    """The template role of the unit-bearing yield with which ``pool`` releases the next pool."""

    return f"{NETWORK_YIELD_QUANTITY}__{pool}"


def _network_symbol(namespace: _Namespace, network: _Network, role: str) -> str:
    return namespace.id("network", network.entry, role)


def _network_template_id(namespace: _Namespace, network: _Network) -> str:
    return namespace.id(network.entry, "enzyme_network_template")


def _network_process_id(namespace: _Namespace, process: _NetworkProcess) -> str:
    return namespace.id(process.class_key, process.pool, _PROCESS_ID_SUFFIX[USER_DATASET_PROCESS_TYPE])


def _network_pool_name(parsed: _Parsed, network: _Network, pool: str) -> str:
    return pool if pool == network.product else parsed.substrates[pool].name


def _generate_network_records(
    parsed: _Parsed,
    context: _Context,
    generated: _Generated,
    namespace: _Namespace,
) -> None:
    """Emit the parameter records, case template and compatibilities of every enzyme network.

    Every strain of a network gets one record per role and condition: the
    kinetics.csv row of its class and pool (or the derived record of a Vmax
    route or an enzyme dose), or an explicit gap with the measurement request of
    the single-class route. The records carry the network's own symbols and are
    selected per case (strain, entry substrate, condition); their provenance
    names the class and pool. One compatibility per class acting on the entry
    points to the one template, which is scientific only when every record bound
    to it is exact and scientific-eligible.
    """

    rows_by_case: dict[tuple[str, str, str, str], dict[str, _Kinetics]] = {}
    constant_conditions: dict[tuple[str, str, str], set[str]] = {}
    for row in parsed.kinetics:
        rows_by_case.setdefault(row.case_key, {})[row.quantity] = row
        if row.quantity in _KINETIC_CONSTANT_QUANTITIES:
            constant_conditions.setdefault((row.strain_id, row.class_key, row.substrate_id), set()).add(row.condition_id)
    for network in parsed.networks.values():
        entry = parsed.substrates[network.entry]
        processes = {(process.class_key, process.pool): process for process in network.processes}
        network_records: list[ParameterRecord] = []
        for strain_id in network.strains:
            strain = parsed.strains[strain_id]
            items = {item.class_key: item for item in parsed.strain_classes if item.strain_id == strain_id}
            for condition in parsed.conditions.values():
                entry_row = network.entry_rows.get((strain_id, condition.condition_id))
                for role, quantity, class_key, pool in _network_roles(network):
                    if quantity == NETWORK_YIELD_QUANTITY:
                        mapping = _network_yield_mapping(
                            parsed,
                            namespace=namespace,
                            network=network,
                            pool=pool,
                            role=role,
                            strain=strain,
                            condition=condition,
                        )
                        record = _emit(
                            generated,
                            context,
                            "parameter_records",
                            mapping,
                            origin=("substrates.csv", parsed.substrates[pool].row, "yield_basis"),
                        )
                        if isinstance(record, ParameterRecord):
                            network_records.append(record)
                        continue
                    if not class_key:
                        # The entry's initial concentration: one pool, stated on the rows of its classes.
                        class_key = entry_row.class_key if entry_row is not None else network.processes[0].class_key
                        pool = network.entry
                    process = processes[(class_key, pool)]
                    case_rows = dict(rows_by_case.get((strain_id, class_key, pool, condition.condition_id), {}))
                    if pool == network.entry and entry_row is not None:
                        case_rows.setdefault("substrate_initial_concentration", entry_row)
                    measured = constant_conditions.get((strain_id, class_key, pool), set())
                    item = items[class_key]
                    case = _CaseContext(
                        strain=strain,
                        info=parsed.classes[class_key],
                        substrate=parsed.substrates[pool],
                        condition=condition,
                        namespace=namespace,
                        case_rows=case_rows,
                        form_started=(class_key, pool) in parsed.pair_forms,
                        # The process's own rate laws for its constants; the entry's shared initial amount is no constant.
                        laws=(
                            ()
                            if role == _NETWORK_INITIAL_ROLE
                            else tuple(
                                name
                                for name in parsed.laws.get((strain_id, class_key, pool), {})
                                if RESPONSE_LAWS[name].scales == LAW_SCALES_RATE
                            )
                        ),
                        form=process.form,
                        genome=item.genome if item.genome_only else None,
                        measured_elsewhere=(
                            ()
                            if condition.condition_id in measured
                            else tuple(other for other in parsed.conditions.values() if other.condition_id in measured)
                        ),
                        inhibitor_name=(
                            _network_pool_name(parsed, network, process.inhibitor) if process.inhibitor else ""
                        ),
                        inactivation=process.inactivation,
                    )
                    mapping, origin = _role_mapping(quantity, case)
                    if role == _NETWORK_INITIAL_ROLE and entry_row is None:
                        mapping = _network_initial_gap(mapping, network=network, entry=entry, case=case)
                    mapping = _as_network_record(
                        mapping,
                        namespace=namespace,
                        network=network,
                        entry=entry,
                        role=role,
                        strain=strain,
                        condition=condition,
                        class_key="" if role == _NETWORK_INITIAL_ROLE else class_key,
                        pool=pool,
                    )
                    record = _emit(generated, context, "parameter_records", mapping, origin=origin)
                    if isinstance(record, ParameterRecord):
                        network_records.append(record)
            for role, law, parameter, class_key, pool in _network_law_roles(network):
                law_mapping, law_origin = _network_law_mapping(
                    parsed,
                    namespace=namespace,
                    network=network,
                    role=role,
                    law=law,
                    parameter=parameter,
                    strain=strain,
                    class_key=class_key,
                    pool=pool,
                    genome=items[class_key].genome if items[class_key].genome_only else None,
                )
                record = _emit(generated, context, "parameter_records", law_mapping, origin=law_origin)
                if isinstance(record, ParameterRecord):
                    network_records.append(record)
        scientific = bool(network_records) and all(
            record.value.is_exact and parameter_record_is_mode_eligible(record, mode="scientific")
            for record in network_records
        )
        origin = ("substrates.csv", entry.row, "substrate_id")
        _emit(
            generated,
            context,
            "case_templates",
            _network_template_mapping(network, parsed=parsed, namespace=namespace, scientific=scientific),
            origin=origin,
        )
        for class_key in network.classes:
            if (class_key, network.entry) in processes:
                _emit(
                    generated,
                    context,
                    "process_compatibility",
                    _network_compatibility_mapping(network, class_key, parsed=parsed, namespace=namespace),
                    origin=origin,
                )


def _network_yield_mapping(
    parsed: _Parsed,
    *,
    namespace: _Namespace,
    network: _Network,
    pool: str,
    role: str,
    strain: _Strain,
    condition: _Condition,
) -> dict[str, Any]:
    """The parameter record of a unit-bearing yield: the substrates.csv value, units, evidence, method and source.

    The record binds the release coefficient of the pool, so its evidence type
    sets the template's mode like any other input (an estimate keeps it
    exploratory). It is one stated value: FungMod neither derived it from a
    molar mass or a registry product map nor checks it against one. One record
    per strain and condition, selected per case like every network record.
    """

    substrate = parsed.substrates[pool]
    entry = parsed.substrates[network.entry]
    released = _network_pool_name(parsed, network, network.downstream(pool)[0])
    evidence = substrate.yield_evidence_type
    confidence = _confidence(evidence)
    statement = (
        f"{_number_text(float(substrate.product_yield))} {substrate.yield_units} of {released} released per dry mass "
        f"of {substrate.name} consumed"
    )
    provenance: dict[str, Any] = {
        "source": substrate.source,
        "confidence_level": confidence,
        "measurement_method": substrate.yield_method or "user estimate without a stated method",
        "validity_range": (
            f"The conversion stated in substrates.csv row {substrate.row} of user dataset {namespace.dataset_id} "
            f"({statement}); FungMod did not derive it from a molar mass or a registry product map."
        ),
        USER_DATASET_PROVENANCE_KEY: namespace.provenance(
            "substrates.csv",
            substrate.row,
            source=substrate.source,
            method=substrate.yield_method or None,
            evidence_type=evidence,
            condition_id=condition.condition_id,
            enzyme_network={"entry_substrate": network.entry, "role": role, "enzyme_class": None, "pool": pool},
        ),
    }
    if evidence == "estimate":
        provenance["exploratory_prior"] = True
    record_id = namespace.id("network", network.entry, strain.strain_id, condition.condition_id, role)
    return {
        "record_id": record_id,
        "name": (
            f"Yield of {released} from {substrate.name} in the enzyme network from {entry.name} for {strain.name} at "
            f"{condition.condition_id} ({namespace.dataset_id})"
        ),
        "maturity": _EVIDENCE_MATURITY[evidence],
        "provenance": provenance,
        "notes": (
            f"User-stated unit-bearing yield from dataset {namespace.dataset_id} (substrates.csv row {substrate.row}, "
            f"yield_basis {substrate.yield_units}): {statement}; evidence type {evidence}. It converts the dry mass "
            "consumed into the amount released and is never derived by FungMod."
        ),
        "parameter_symbol": _network_symbol(namespace, network, role),
        "process_type": USER_DATASET_NETWORK_PROCESS_TYPE,
        "enzyme_class": None,
        "substrate_class": entry.substrate_class,
        "fungus_id": namespace.id(strain.strain_id),
        "substrate_id": entry.registry_id or namespace.id(entry.substrate_id),
        "environment_id": namespace.id(condition.condition_id),
        "value": {
            "kind": "exact",
            "units": substrate.yield_units,
            "source": substrate.source,
            "confidence_level": confidence,
            "notes": f"substrates.csv row {substrate.row} of user dataset {namespace.dataset_id}: {statement}.",
            "value": float(substrate.product_yield),
        },
        "allowed_use": _allowed_use(evidence, exact=True),
    }


def _network_law_mapping(
    parsed: _Parsed,
    *,
    namespace: _Namespace,
    network: _Network,
    role: str,
    law: ResponseLaw,
    parameter: ResponseLawParameter,
    strain: _Strain,
    class_key: str,
    pool: str,
    genome: _ClassEvidence | None,
) -> tuple[dict[str, Any], tuple[str, int | None, str | None]]:
    """One response-law parameter of one network process for one strain: the single-class record, re-keyed.

    The value, units (temperatures in kelvin), maturity (the weakest row of the
    law), reference-condition provenance and allowed use are exactly those of
    the single-class route (``_response_mapping``), or its gap with the
    measurement request when another strain binds the law and this one does
    not. Like every law parameter the record applies at every environment of
    the case (no environment selector), so a law reaches EnvironmentGrid
    conditions; it carries the network's symbol and names the class and pool.
    """

    info = parsed.classes[class_key]
    substrate = parsed.substrates[pool]
    law_rows = parsed.laws.get((strain.strain_id, class_key, pool), {}).get(law.law, {})
    response = law_rows.get(parameter.name)
    if response is not None:
        mapping = _response_mapping(
            response,
            law=law,
            law_rows=law_rows,
            strain=strain,
            info=info,
            substrate=substrate,
            namespace=namespace,
            reference_conditions=_reference_conditions(parsed, response.binding_key, law),
            process_type=USER_DATASET_NETWORK_PROCESS_TYPE,
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
            genome=genome,
            process_type=USER_DATASET_NETWORK_PROCESS_TYPE,
        )
        origin = ("responses.csv", None, "parameter")
    entry = parsed.substrates[network.entry]
    gap = mapping["maturity"] == USER_DATASET_MATURITY_GAP
    provenance = dict(mapping["provenance"])
    dataset = dict(provenance[USER_DATASET_PROVENANCE_KEY])
    dataset["enzyme_network"] = {
        "entry_substrate": network.entry,
        "role": role,
        "enzyme_class": namespace.id(class_key),
        "pool": pool,
    }
    provenance[USER_DATASET_PROVENANCE_KEY] = dataset
    record_id = namespace.id("network", network.entry, strain.strain_id, role)
    return (
        {
            **mapping,
            "record_id": f"{record_id}__gap" if gap else record_id,
            "name": f"{mapping['name']} in the enzyme network from {entry.name}",
            "provenance": provenance,
            "parameter_symbol": _network_symbol(namespace, network, role),
            "process_type": USER_DATASET_NETWORK_PROCESS_TYPE,
            "enzyme_class": None,
            "substrate_class": entry.substrate_class,
            "substrate_id": entry.registry_id or namespace.id(entry.substrate_id),
            "environment_id": None,
        },
        origin,
    )


def _network_initial_gap(
    mapping: Mapping[str, Any],
    *,
    network: _Network,
    entry: _Substrate,
    case: _CaseContext,
) -> dict[str, Any]:
    """Word the entry's missing initial concentration as the network's, not as one class's."""

    units = mapping["value"].get("units")
    units_text = units if units else _GAP_UNITS_TEXT.get("substrate_initial_concentration", "concentration units")
    request = (
        f"Specify the initial {entry.name} concentration of the enzyme network of {case.strain.name} at "
        f"{_condition_text(case.condition)} ({units_text}); every class of the network that acts on {entry.name} "
        "acts on this one pool."
    )
    provenance = dict(mapping["provenance"])
    provenance["measurement_request"] = request
    return {
        **mapping,
        "name": (
            f"Missing initial {entry.name} concentration of the enzyme network of {case.strain.name} at "
            f"{case.condition.condition_id} ({case.namespace.dataset_id})"
        ),
        "provenance": provenance,
    }


def _as_network_record(
    mapping: Mapping[str, Any],
    *,
    namespace: _Namespace,
    network: _Network,
    entry: _Substrate,
    role: str,
    strain: _Strain,
    condition: _Condition,
    class_key: str,
    pool: str,
) -> dict[str, Any]:
    """Re-key a single-class record as one role of a network: its symbol, selectors and identifier.

    The value, maturity, allowed use and provenance stay those of the row (or
    derivation, or gap); the provenance adds the network, the role, the class
    and the pool. The enzyme class selector is left empty, because one network
    serves the compatibility of every class acting on its entry substrate.
    """

    gap = mapping["maturity"] == USER_DATASET_MATURITY_GAP
    provenance = dict(mapping["provenance"])
    dataset = dict(provenance[USER_DATASET_PROVENANCE_KEY])
    dataset["enzyme_network"] = {
        "entry_substrate": network.entry,
        "role": role,
        "enzyme_class": namespace.id(class_key) if class_key else None,
        "pool": pool,
    }
    provenance[USER_DATASET_PROVENANCE_KEY] = dataset
    record_id = namespace.id("network", network.entry, strain.strain_id, condition.condition_id, role)
    return {
        **mapping,
        "record_id": f"{record_id}__gap" if gap else record_id,
        "name": f"{mapping['name']} in the enzyme network from {entry.name}",
        "provenance": provenance,
        "parameter_symbol": _network_symbol(namespace, network, role),
        "process_type": USER_DATASET_NETWORK_PROCESS_TYPE,
        "enzyme_class": None,
        "substrate_class": entry.substrate_class,
        "substrate_id": entry.registry_id or namespace.id(entry.substrate_id),
        "environment_id": namespace.id(condition.condition_id),
    }


_NETWORK_LIMITATIONS = (
    "Parallel enzyme classes on one pool act additively and independently: each runs its own Michaelis-Menten law "
    "on the shared pool and their rates add. No competition between classes for substrate binding or adsorption "
    "sites, no synergy (for example endo- and exo-acting cooperation), and no interaction between the enzymes is "
    "represented.",
    "Pools are linked only where a substrate's substrates.csv product is another substrate_id of the dataset, with "
    "the user-stated yield; intermediate pools and the final product start at zero, and every pool is reported in "
    "the units of the entry's initial concentration.",
    "Non-competitive, uncompetitive and mixed inhibition, inhibition of one process by several products, substrate "
    "inhibition, competing substrates of one enzyme and transglycosylation are not represented.",
    "This is an enzyme-kinetics case, not a whole-fungus growth, secretion or uptake model; no temperature or pH "
    "response law is bound, so the values apply at the condition of their rows only.",
)


_NETWORK_NOT_A_CULTURE = "This is an enzyme-kinetics case, not a whole-fungus growth, secretion or uptake model."


def _network_law_limitation(parsed: _Parsed, process: _NetworkProcess) -> str:
    """What the response laws of one process do, or that the process has none and keeps its rows' condition."""

    info = parsed.classes[process.class_key]
    pool = parsed.substrates[process.pool].name
    if not process.laws and process.inactivation == INACTIVATION_LAW:
        return (
            f"No temperature or pH response law scales the rate of {info.name} on {pool}: its catalytic constants "
            "apply at the condition of their rows only, and at any other temperature or pH (an EnvironmentGrid "
            f"condition) only its inactivation constant changes, through the {INACTIVATION_LAW} law."
        )
    if not process.laws:
        return (
            f"No temperature or pH response law is bound to {info.name} on {pool}: its constants apply at the condition "
            "of their rows only, and at any other temperature or pH (an EnvironmentGrid condition) its rate is "
            "unchanged, so the network responds to that condition only through the other processes' laws."
        )
    laws = "; ".join(f"{law_name} ({RESPONSE_LAWS[law_name].formula})" for law_name in process.laws)
    read = sorted({RESPONSE_LAWS[law_name].condition for law_name in process.laws})
    read_text = " and ".join("pH" if condition == "ph" else condition for condition in read)
    return (
        f"Response laws from responses.csv scale the rate of {info.name} on {pool}: {laws}. Its kinetic constants "
        "(Km, kcat or Vmax, and Ki when bound) are reference values at each law's reference condition; only this "
        f"process's rate is rescaled (Km, Ki, the concentrations and the yields are not), and no condition other than "
        f"{read_text} acts on it."
    )


_NETWORK_CONVERSION_VALIDITY_NOTE = (
    "Upstream of the unit-bearing yield the closure weights carry its units, so the conservation check sums every "
    "pool in the final product's units through the stated yield (a dry mass per volume times an amount per dry mass "
    "is an amount per volume); pint checked that the yield converts the solid's units into the released pool's."
)


def _network_conversion_limitation(parsed: _Parsed, network: _Network, pool: str) -> str:
    substrate = parsed.substrates[pool]
    released = _network_pool_name(parsed, network, network.downstream(pool)[0])
    return (
        f"Basis change from {substrate.name} (dry mass per volume) to {released} (amount per volume) through the "
        f"user-stated yield of {_number_text(float(substrate.product_yield))} {substrate.yield_units} (substrates.csv row "
        f"{substrate.row}, evidence type {substrate.yield_evidence_type}, a parameter record of this template). FungMod "
        "did not derive it from a molar mass, a degree of polymerisation or a registry product map and does not check "
        f"it against one; {released} and every pool after it are reported in the entry's initial-concentration units "
        "times the yield's units, simplified by pint."
    )


def _network_inhibition_limitation(parsed: _Parsed, network: _Network, process: _NetworkProcess) -> str:
    info = parsed.classes[process.class_key]
    pool = parsed.substrates[process.pool].name
    if not process.inhibitor:
        return (
            f"No product inhibition is represented for {info.name} on {pool}: kinetics.csv gives no ki for this "
            "process, and FungMod assumes none."
        )
    inhibitor = _network_pool_name(parsed, network, process.inhibitor)
    return (
        f"Competitive product inhibition of {info.name} on {pool} by {inhibitor}: {COMPETITIVE_INHIBITION_EQUATION}, "
        f"the existing competitive_inhibition modifier with this process's own Km and the Ki of kinetics.csv (law "
        f"provenance {COMPETITIVE_INHIBITION_LAW_SOURCE}, maturity {COMPETITIVE_INHIBITION_LAW_MATURITY}; the source "
        "supports the equation, not the Ki value)."
    )


def _network_weights(parsed: _Parsed, network: _Network) -> dict[str, Any]:
    """Closure weights from the yields: the final product weighs 1, each pool its yield times the next pool's.

    Upstream of a unit-bearing yield a weight carries that yield's units
    (``{value, units}``): the weighted dry mass of a solid pool is then an
    amount per volume, so the ledger is summed in the final product's units
    through the stated yield. Without one every weight is a pure number, as
    before.
    """

    weights: dict[str, Any] = {"product": 1.0}
    weight = 1.0
    units = ""
    for pool in reversed(network.pools):
        substrate = parsed.substrates[pool]
        weight = float(substrate.product_yield) * weight
        units = substrate.yield_units or units
        weights[_network_pool_role(network.pools, pool)] = {"value": weight, "units": units} if units else weight
    return weights


def _network_units_mapping(network: _Network, pool: str) -> dict[str, Any]:
    """Where a pool's (or the final product's) units come from: the entry's, times the yield's after a basis change."""

    if network.converted(pool):
        return {"units_from_roles": [_NETWORK_INITIAL_ROLE, _network_yield_role(network.unit_bearing_yield_pools[0])]}
    return {"units_from_role": _NETWORK_INITIAL_ROLE}


def _network_template_mapping(
    network: _Network,
    *,
    parsed: _Parsed,
    namespace: _Namespace,
    scientific: bool,
) -> dict[str, Any]:
    """The enzyme_network template of one network: one homogeneous Michaelis-Menten process per class and pool."""

    entry = parsed.substrates[network.entry]
    last = parsed.substrates[network.pools[-1]]
    template_id = _network_template_id(namespace, network)
    states = _network_state_names(parsed, network.pools, network.product, network.processes)
    simulation = namespace.manifest["simulation"]
    mode = "scientific" if scientific else "exploratory"
    initial_state_mapping: dict[str, Any] = {
        "substrate": {"parameter_role": _NETWORK_INITIAL_ROLE, "units_from_role": _NETWORK_INITIAL_ROLE},
    }
    for pool in network.pools[1:]:
        initial_state_mapping[_network_pool_role(network.pools, pool)] = {
            "value": 0.0,
            **_network_units_mapping(network, pool),
        }
    initial_state_mapping["product"] = {"value": 0.0, **_network_units_mapping(network, network.product)}
    for process in network.processes:
        if process.form in _ENZYME_FORMS:
            role = f"enzyme_initial_concentration__{process.class_key}"
            initial_state_mapping[_network_enzyme_role(process.class_key)] = {"parameter_role": role, "units_from_role": role}
    product_maps = []
    for pool in network.pools:
        substrate = parsed.substrates[pool]
        next_role = _network_next_role(network, pool)
        released = _network_pool_name(parsed, network, network.downstream(pool)[0])
        unit = "g" if substrate.is_solid else "mol"
        if substrate.yield_units:
            # The coefficient is the yield's parameter record, with its units: it converts the dry mass consumed.
            coefficient: Any = {"parameter_role": _network_yield_role(pool)}
            notes = (
                f"User-stated unit-bearing yield {_number_text(float(substrate.product_yield))} {substrate.yield_units} "
                f"({substrate.product} per dry mass of {substrate.substrate_id} consumed; substrates.csv row "
                f"{substrate.row}, evidence type {substrate.yield_evidence_type}), bound as parameter role "
                f"{_network_yield_role(pool)}; FungMod derived it from no molar mass."
            )
        else:
            coefficient = float(substrate.product_yield)
            notes = (
                f"User-stated yield {_number_text(float(substrate.product_yield))} {unit} {substrate.product} per "
                f"{unit} {substrate.substrate_id} consumed (substrates.csv row {substrate.row})."
            )
        product_maps.append(
            {
                "id": namespace.id("network", network.entry, pool, "release_map"),
                "name": f"{substrate.name} to {released} in the enzyme network from {entry.name} ({namespace.dataset_id})",
                "product_map_type": "stoichiometric",
                "reactants": {_network_pool_role(network.pools, pool): 1.0},
                "products": {next_role: coefficient},
                "notes": notes,
            }
        )
    process_templates = []
    for process in network.processes:
        info = parsed.classes[process.class_key]
        pool = parsed.substrates[process.pool]
        pool_role = _network_pool_role(network.pools, process.pool)
        released = _network_pool_name(parsed, network, network.downstream(process.pool)[0])
        state_roles: dict[str, str] = {"substrate": pool_role, "product": _network_next_role(network, process.pool)}
        parameter_roles = {"km": f"km__{process.class_key}__{process.pool}"}
        if process.form == RATE_FORM_KCAT:
            state_roles["enzyme"] = _network_enzyme_role(process.class_key)
            parameter_roles["kcat"] = f"kcat__{process.class_key}__{process.pool}"
        else:
            parameter_roles["vmax"] = f"vmax__{process.class_key}__{process.pool}"
        modifiers: list[dict[str, Any]] = []
        if process.reactive:
            modifiers.append(
                {
                    "type": SUBSTRATE_REACTIVITY_MODIFIER_TYPE,
                    "substrate_state_role": pool_role,
                    "reference_concentration_role": _NETWORK_INITIAL_ROLE,
                    "exponent_role": f"{REACTIVITY_EXPONENT_ROLE}__{process.class_key}__{process.pool}",
                }
            )
        if process.inhibitor:
            modifiers.append(
                {
                    "type": COMPETITIVE_INHIBITION_MODIFIER_TYPE,
                    "substrate_state_role": pool_role,
                    "inhibitor_state_role": _network_inhibitor_role(network, process.inhibitor),
                    "michaelis_constant_role": parameter_roles["km"],
                    "inhibition_constant_role": f"ki__{process.class_key}__{process.pool}",
                    "primary_source": COMPETITIVE_INHIBITION_LAW_SOURCE,
                    "maturity": COMPETITIVE_INHIBITION_LAW_MATURITY,
                }
            )
        # A responses.csv law of this class on this pool: the existing environment modifier, as in single-class
        # templates, with the network's per-process roles; it multiplies this process's rate only.
        modifiers.extend(
            {
                "type": law_name,
                **{
                    f"{parameter.name}_role": f"{law_name}__{parameter.name}__{process.class_key}__{process.pool}"
                    for parameter in RESPONSE_LAWS[law_name].parameters
                },
            }
            for law_name in process.laws
        )
        spec: dict[str, Any] = {
            "id": _network_process_id(namespace, process),
            "enzyme_class": namespace.id(process.class_key),
            "process_type": USER_DATASET_PROCESS_TYPE,
            "state_roles": state_roles,
            "parameter_roles": parameter_roles,
            "rate_units_from_state_role": pool_role,
            "product_map": namespace.id("network", network.entry, process.pool, "release_map"),
            "assumptions": [
                f"{info.name} consumes {pool.name} by its own homogeneous Michaelis-Menten law ({_FORM_LABEL[process.form]}"
                " form), independently of every other class of the network; processes on one pool add their rates.",
                f"Consumed {pool.name} is released as {released} with the user-stated yield of substrates.csv"
                + (
                    f" ({_number_text(float(pool.product_yield))} {pool.yield_units}, which converts the dry mass consumed "
                    "into the amount released)."
                    if pool.yield_units
                    else "."
                ),
            ],
        }
        if modifiers:
            spec["modifiers"] = modifiers
        process_templates.append(spec)
    # The loss of each enzyme state that kinetics.csv or responses.csv binds (USERDATA-011), after the
    # Michaelis-Menten processes: one existing first_order or thermal_inactivation process per class.
    for process in network.processes:
        if not process.inactivation:
            continue
        process_templates.append(
            {
                "id": namespace.id(process.class_key, process.pool, "enzyme_inactivation"),
                "enzyme_class": namespace.id(process.class_key),
                "process_type": process.inactivation,
                "state_roles": {
                    ENZYME_INACTIVATION_PROCESS_LAWS[process.inactivation][0]: _network_enzyme_role(process.class_key)
                },
                "parameter_roles": _inactivation_parameter_roles(
                    process.inactivation,
                    rate_role=_network_inactivation_role(process),
                    law_roles={
                        parameter.name: _network_law_role(INACTIVATION_LAW, parameter, process)
                        for parameter in RESPONSE_LAWS[INACTIVATION_LAW].parameters
                    },
                ),
                "assumptions": _inactivation_assumptions(parsed.classes[process.class_key].name, law=process.inactivation),
            }
        )
    substrate_entities = []
    for pool in network.pools:
        substrate = parsed.substrates[pool]
        record_id = substrate.registry_id or namespace.id(pool)
        # Each pool is loaded on its own basis (the entry's, unless a unit-bearing yield changed it).
        loader = "generic_solid" if substrate.is_solid else "generic_dissolved"
        substrate_entities.append(
            {
                "id": record_id,
                "loader": loader,
                "data": {
                    "kind": "substrate",
                    "name": substrate.name,
                    "substrate_type": loader,
                    "chemical_class": substrate.substrate_class,
                    "physical_state": substrate.physical_state,
                    "bond_types": list(substrate.bond_classes),
                    "accessible_bonds": list(substrate.bond_classes),
                    "required_enzyme_classes": [
                        namespace.id(process.class_key) for process in network.processes if process.pool == pool
                    ],
                    "degradation_products": [
                        {
                            "name": substrate.product,
                            "source": substrate.source,
                            "notes": f"Product stated in substrates.csv row {substrate.row} of user dataset "
                            f"{namespace.dataset_id}.",
                        }
                    ],
                    "completeness": "partial",
                    "default_degradation_model": "unknown" if substrate.is_solid else "homogeneous_dissolved",
                    "water_activity_dependence": "unknown",
                    "provenance": {
                        "source": substrate.source,
                        "confidence_level": "user_supplied",
                        "notes": (
                            f"Pool of the enzyme network from {entry.name}"
                            + (
                                "; a suspended solid represented as a bulk dry mass per volume, without surface area, "
                                "crystallinity or particle size."
                                if substrate.is_solid
                                else "; dissolved and well mixed."
                            )
                        ),
                    },
                    "parameters": [],
                },
            }
        )
    enzymes = [
        {
            "id": namespace.id(class_key),
            "data": {
                "kind": "enzyme",
                "name": parsed.classes[class_key].name,
                "enzyme_class": namespace.id(class_key),
                "target_bond_types": list(parsed.classes[class_key].target_bond_classes),
                "target_substrate_classes": list(parsed.classes[class_key].compatible_substrate_classes),
                "target_substrate_names": [
                    parsed.substrates[process.pool].name for process in network.processes if process.class_key == class_key
                ],
                "validity_labels": [USER_DATASET_RECORD_MATURITY, "enzyme_network_member"],
                "provenance": {
                    "source": parsed.classes[class_key].source,
                    "measurement_method": f"enzyme class of a user enzyme network ({NETWORK_MANIFEST_FIELD})",
                    "confidence_level": "user_supplied",
                    "notes": "Acts on its pool through its own Michaelis-Menten process.",
                    "validity_range": f"Enzyme-network cases of user dataset {namespace.dataset_id} only",
                    "units": "not_applicable",
                },
                "catalytic_parameters": [],
                "adsorption_parameters": [],
                "parameters": [],
            },
        }
        for class_key in network.classes
    ]
    state_species: dict[str, dict[str, str]] = {
        _network_pool_role(network.pools, pool): {
            "entity_type": "substrate",
            "species": parsed.substrates[pool].registry_id or namespace.id(pool),
        }
        for pool in network.pools
    }
    state_species["product"] = {"entity_type": "product", "species": network.product}
    for process in network.processes:
        if process.form in _ENZYME_FORMS:
            state_species[_network_enzyme_role(process.class_key)] = {
                "entity_type": "enzyme",
                "species": namespace.id(process.class_key),
            }
    chain = " -> ".join((*network.pools, network.product))
    basis = "dry mass per volume (yields g/g)" if entry.is_solid else f"amount per volume (yields {_YIELD_BASIS})"
    if network.unit_bearing_yield_pools:
        converting = parsed.substrates[network.unit_bearing_yield_pools[0]]
        basis = (
            f"dry mass per volume up to {converting.substrate_id}, then amount per volume through its stated yield of "
            f"{_number_text(float(converting.product_yield))} {converting.yield_units}"
        )
    vmax_processes = [process for process in network.processes if process.form == RATE_FORM_VMAX]
    # A temperature law on an inactivation constant is a law of the network too: the last generic sentence ("no
    # temperature or pH response law is bound") would no longer hold.
    with_laws = any(process.laws or process.inactivation == INACTIVATION_LAW for process in network.processes)
    limitations = [
        (
            f"Enzyme network of user dataset {namespace.dataset_id} from {entry.substrate_id}: the pools {chain} "
            f"({basis}), with {len(network.processes)} homogeneous Michaelis-Menten process(es) of the classes "
            f"{', '.join(network.classes)}."
        ),
        # Without a response law the network's last limitation says that none is bound, as before.
        *(_NETWORK_LIMITATIONS if not with_laws else (*_NETWORK_LIMITATIONS[:-1], _NETWORK_NOT_A_CULTURE)),
        *(_network_inhibition_limitation(parsed, network, process) for process in network.processes),
        *(_network_law_limitation(parsed, process) for process in network.processes if with_laws),
    ]
    if vmax_processes:
        limitations.append(
            "Processes in the Vmax form ("
            + ", ".join(f"{process.class_key} on {process.pool}" for process in vmax_processes)
            + f"): {_RATE_FORM_LIMITATION[RATE_FORM_VMAX]}"
        )
    if entry.is_solid:
        limitations.extend(_solid_limitations(any(process.reactive for process in network.processes)))
    limitations.extend(_network_conversion_limitation(parsed, network, pool) for pool in network.unit_bearing_yield_pools)
    if parsed.inactivation_pairs:
        # A dataset that states inactivation says, for every enzyme state of the network, whether and how it is lost.
        limitations.extend(
            _inactivation_limitation(
                parsed.classes[process.class_key].name,
                law=process.inactivation,
                where=parsed.substrates[process.pool].name,
            )
            for process in network.processes
            if process.form in _ENZYME_FORMS
        )
    rows = sorted(
        {
            row.row
            for row in parsed.kinetics
            if (row.class_key, row.substrate_id) in {(process.class_key, process.pool) for process in network.processes}
        }
    )
    return {
        "record_id": template_id,
        "case_template_id": template_id,
        "name": f"Enzyme network from {entry.name} template ({namespace.dataset_id})",
        "maturity": USER_DATASET_RECORD_MATURITY,
        "provenance": {
            "source": namespace.source,
            "confidence_level": "user_supplied",
            USER_DATASET_PROVENANCE_KEY: namespace.provenance(
                USER_DATASET_MANIFEST,
                None,
                substrate_row=entry.row,
                kinetics_rows=rows,
                network_field=NETWORK_MANIFEST_FIELD,
                config_mode_rule=(
                    "scientific only when every parameter record bound to this template is exact and "
                    "scientific-eligible; otherwise exploratory"
                ),
            ),
        },
        "schema_version": CASE_TEMPLATE_SCHEMA_VERSION,
        "process_type": USER_DATASET_NETWORK_PROCESS_TYPE,
        "state_roles": dict(states),
        "initial_state_mapping": initial_state_mapping,
        # The release of the final product, as the single-step templates state it; every step's map is in
        # process_state_metadata.product_maps, and each released role's yield from its precursor is listed below.
        "product_map": {
            "id": namespace.id("network", network.entry, last.substrate_id, "release_map"),
            "product_map_type": "stoichiometric",
            "substrate_state_role": _network_pool_role(network.pools, last.substrate_id),
            "product_state_role": "product",
            "stoichiometric_yield": float(last.product_yield),
            "notes": "The last release step of the network; the yield of every step is in stoichiometric_yields."
            + (
                " A unit-bearing yield ("
                + ", ".join(
                    f"{pool}: {parsed.substrates[pool].yield_units}" for pool in network.unit_bearing_yield_pools
                )
                + ") appears there as its number; its units and record are in process_state_metadata.product_maps."
                if network.unit_bearing_yield_pools
                else ""
            ),
        },
        "stoichiometric_yields": {
            _network_next_role(network, pool): float(parsed.substrates[pool].product_yield) for pool in network.pools
        },
        "time_grid": {
            "start": 0.0,
            "stop": float(simulation["duration"]),
            "points": int(simulation["points"]),
            "units": str(simulation["units"]),
            "notes": f"From the simulation block of user dataset {namespace.dataset_id}.",
        },
        "observable_roles": [*states, "degradation_rate", "product_release_rate"],
        "output_state_roles": dict(states),
        "process_state_metadata": {
            "config_name": (
                f"User dataset {namespace.dataset_id}: enzyme network of {{fungus_id}} from {_template_text(entry.name)}"
            ),
            "config_mode": mode,
            "config_maturity": mode,
            "parameter_set_id": namespace.id(network.entry, "network_parameters"),
            "public_path": True,
            # Concentration-only: the network reads no vessel volume, so none is claimed.
            "geometry": None,
            "entities": {"substrates": substrate_entities, "enzymes": enzymes},
            "state_species": state_species,
            "product_maps": product_maps,
            "process_templates": process_templates,
            "conservation": {
                "id": "network_pool_balance",
                "closed_system": True,
                "state_weights": _network_weights(parsed, network),
            },
        },
        "limitations": limitations,
        "validity_notes": [
            f"Values come from user dataset {namespace.dataset_id} (sha256 {namespace.digest}); FungMod did not "
            "check them against an external source.",
            "The closure weights are the user-stated yields multiplied along the chain (the final product weighs 1), "
            "so the conservation check tests the integration, not the yields.",
            *([_SOLID_VALIDITY_NOTE] if entry.is_solid else []),
            *([_NETWORK_CONVERSION_VALIDITY_NOTE] if network.unit_bearing_yield_pools else []),
        ],
        "notes": (
            f"Enzyme-network template generated from user dataset {namespace.dataset_id} for the network that starts "
            f"from {network.entry}: pools {chain}; processes "
            + ", ".join(f"{process.class_key} on {process.pool}" for process in network.processes)
            + "."
        ),
    }


def _network_compatibility_mapping(
    network: _Network,
    class_key: str,
    *,
    parsed: _Parsed,
    namespace: _Namespace,
) -> dict[str, Any]:
    info = parsed.classes[class_key]
    entry = parsed.substrates[network.entry]
    symbols = {role: _network_symbol(namespace, network, role) for role, *_rest in _network_roles(network)}
    symbols.update((role, _network_symbol(namespace, network, role)) for role, *_rest in _network_law_roles(network))
    return {
        "record_id": namespace.id(class_key, network.entry, USER_DATASET_NETWORK_PROCESS_TYPE),
        "name": f"{info.name} on {entry.name} enzyme network ({namespace.dataset_id})",
        "maturity": USER_DATASET_RECORD_MATURITY,
        "provenance": {
            "source": namespace.source,
            "confidence_level": "user_supplied",
            USER_DATASET_PROVENANCE_KEY: namespace.provenance("substrates.csv", entry.row),
        },
        "enzyme_class": namespace.id(class_key),
        "substrate_class": entry.substrate_class,
        "required_bond_classes": list(_shared_bonds(info, entry) or ()),
        "process_type": USER_DATASET_NETWORK_PROCESS_TYPE,
        "required_parameters": list(symbols.values()),
        "parameter_roles": dict(symbols),
        "product_map_required": True,
        "case_template_id": _network_template_id(namespace, network),
        "notes": (
            f"Enzyme-network compatibility generated from user dataset {namespace.dataset_id}: {class_key} acts on "
            f"the entry substrate {network.entry} through the bond classes listed, and the case runs the whole network "
            f"of classes {', '.join(network.classes)}. Every class acting on the entry has such a record, all pointing "
            "to the one network template."
        ),
    }


def _network_report(parsed: _Parsed, *, dataset_id: str) -> tuple[Mapping[str, Any], ...]:
    """One entry per enzyme network: its pools, links, processes, strains and generated ids."""

    namespace = _Namespace(dataset_id=dataset_id, digest="", manifest={})
    entries: list[Mapping[str, Any]] = []
    for network in parsed.networks.values():
        entries.append(
            MappingProxyType(
                {
                    "entry_substrate": network.entry,
                    "pools": list(network.pools),
                    "product": network.product,
                    "links": [
                        {
                            "substrate_id": pool,
                            "releases": network.downstream(pool)[0],
                            "yield": float(parsed.substrates[pool].product_yield),
                            "yield_basis": parsed.substrates[pool].yield_basis,
                            "substrates_row": parsed.substrates[pool].row,
                            # The evidence type of a unit-bearing yield (a parameter record); None for g/g and mol/mol.
                            "yield_evidence_type": parsed.substrates[pool].yield_evidence_type or None,
                        }
                        for pool in network.pools
                    ],
                    "processes": [
                        {
                            "enzyme_class": process.class_key,
                            "pool": process.pool,
                            "rate_form": _FORM_LABEL[process.form],
                            "process_id": _network_process_id(namespace, process),
                            "inhibitor": process.inhibitor or None,
                            "reactivity_factor": process.reactive,
                            "response_laws": list(process.laws),
                            # The loss law of the class's enzyme state (USERDATA-011), or None: not lost.
                            "enzyme_inactivation": process.inactivation or None,
                        }
                        for process in network.processes
                    ],
                    "enzyme_classes": list(network.classes),
                    "strains": list(network.strains),
                    "substrate_record_id": parsed.substrates[network.entry].registry_id
                    or namespace.id(network.entry),
                    "case_template_id": _network_template_id(namespace, network),
                    "process_compatibility_ids": [
                        namespace.id(process.class_key, network.entry, USER_DATASET_NETWORK_PROCESS_TYPE)
                        for process in network.processes
                        if process.pool == network.entry
                    ],
                }
            )
        )
    return tuple(entries)


def _inactivation_report(parsed: _Parsed, *, dataset_id: str) -> tuple[Mapping[str, Any], ...]:
    """One entry per enzyme class and substrate whose enzyme state is lost: its law, ids and rows (USERDATA-011)."""

    namespace = _Namespace(dataset_id=dataset_id, digest="", manifest={})
    entries: list[Mapping[str, Any]] = []
    for (class_key, substrate_id), law in parsed.inactivation_pairs.items():
        if parsed.network_dataset:
            template_ids = [
                _network_template_id(namespace, network)
                for network in parsed.networks.values()
                if any((process.class_key, process.pool) == (class_key, substrate_id) for process in network.processes)
            ]
        else:
            template_ids = [
                _template_id(
                    namespace,
                    parsed.classes[class_key],
                    parsed.substrates[substrate_id],
                    form=_pair_form(parsed, (class_key, substrate_id)),
                )
            ]
        entries.append(
            MappingProxyType(
                {
                    "enzyme_class": class_key,
                    "substrate_id": substrate_id,
                    "law": law,
                    "process_id": namespace.id(class_key, substrate_id, "enzyme_inactivation"),
                    "case_template_ids": template_ids,
                    "kinetics_rows": sorted(
                        row.row
                        for row in parsed.kinetics
                        if row.pair_key == (class_key, substrate_id) and row.quantity == INACTIVATION_RATE_QUANTITY
                    ),
                    "responses_rows": sorted(
                        response.row
                        for binding, laws in parsed.laws.items()
                        if (binding[1], binding[2]) == (class_key, substrate_id)
                        for response in laws.get(INACTIVATION_LAW, {}).values()
                    ),
                }
            )
        )
    return tuple(entries)


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
# Dataset copies


def _dataset_files_with_kinetics(
    dataset: UserDataset,
    *,
    drop_rows: Sequence[int],
    new_rows: Sequence[Mapping[str, str]],
    manifest: Mapping[str, Any],
    extra_files: Mapping[str, bytes] | None = None,
) -> dict[str, bytes]:
    """Return a copy of a dataset's input files with kinetics rows replaced and a new manifest.

    ``drop_rows`` are kinetics.csv spreadsheet lines left out; ``new_rows`` are
    appended (missing cells are blank, and their columns are added to the
    header when the input lacks them). Every other file, annotation files
    included, is copied byte for byte.
    """

    files = dict(dataset._raw_files)
    text = files["kinetics.csv"].decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text, newline=""))
    header = [cell.strip() for cell in next(reader)]
    columns = [*header, *(column for row in new_rows for column in row if column not in header)]
    columns = list(dict.fromkeys(columns))
    dropped = set(drop_rows)
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(columns)
    for cells in reader:
        line = reader.line_num
        if not any(cell.strip() for cell in cells) or line in dropped:
            continue
        values = {column: (cells[index].strip() if index < len(cells) else "") for index, column in enumerate(header)}
        writer.writerow([values.get(column, "") for column in columns])
    for row in new_rows:
        writer.writerow([row.get(column, "") for column in columns])
    files["kinetics.csv"] = output.getvalue().encode("utf-8")
    files[USER_DATASET_MANIFEST] = yaml.safe_dump(_plain(manifest), sort_keys=False, allow_unicode=True).encode("utf-8")
    files.update(extra_files or {})
    return files


def _write_dataset_files(files: Mapping[str, bytes], directory: Path) -> None:
    """Write dataset files (relative paths, ``/``-separated) into ``directory``, which must be new or empty."""

    if directory.exists() and (not directory.is_dir() or any(directory.iterdir())):
        raise UserDataError(
            f"Refusing to write a user dataset into {str(directory)!r}: the path exists and is not an empty directory.",
            issues=[_issue(str(directory), None, None, "Choose a new or empty directory; nothing is overwritten.")],
        )
    directory.mkdir(parents=True, exist_ok=True)
    for name, data in sorted(files.items()):
        path = directory / PurePosixPath(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


# ---------------------------------------------------------------------------
# Cell helpers


def _issue(file: str, row: int | None, column: str | None, message: str) -> dict[str, Any]:
    return {"file": file, "row": row, "column": column, "message": message}


def _review_issue(file: str, row: int | None, column: str, text: str) -> dict[str, Any]:
    return _issue(
        file,
        row,
        column,
        f"{_REVIEW_ISSUE_PREFIX} {column}: {text!r}. Replace it with a reviewed value before loading.",
    )


def _review_marker_paths(value: Any, prefix: str = "") -> dict[str, str]:
    """Dotted paths of every manifest string that still begins with the review marker."""

    found: dict[str, str] = {}
    if isinstance(value, Mapping):
        for key, item in value.items():
            found.update(_review_marker_paths(item, f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.update(_review_marker_paths(item, f"{prefix}[{index}]"))
    elif isinstance(value, str) and value.strip().startswith(REVIEW_MARKER):
        found[prefix] = value.strip()
    return found


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
    "CULTURE_CONSUMPTION_QUANTITIES",
    "CULTURE_EVIDENCE_TYPES",
    "CULTURE_LEVEL_QUANTITIES",
    "CULTURE_POOL_QUANTITIES",
    "CULTURE_QUANTITIES",
    "CULTURE_TABLE",
    "EVIDENCE_TYPES",
    "FITTABLE_QUANTITIES",
    "FITTED_EVIDENCE_TYPE",
    "FIT_BLOCK_KIND",
    "FIT_ERROR_MODELS",
    "FIT_IDENTIFIABILITY_CLASSES",
    "FIT_IDENTIFIED",
    "FIT_NOT_IDENTIFIED",
    "GENOME_ANNOTATION_TOOLS",
    "UNIPROT_SOURCE_TYPE",
    "GENOME_TABLE",
    "KINETIC_QUANTITIES",
    "PH_IONIZATION_QUANTITIES",
    "RATE_FORM_KCAT",
    "RATE_FORM_PH_IONIZATION",
    "RATE_FORM_VMAX",
    "RESPONSE_EVIDENCE_TYPES",
    "RESPONSE_LAWS",
    "REVIEW_MARKER",
    "ResponseLaw",
    "ResponseLawParameter",
    "TIMECOURSE_OBSERVABLES",
    "TIMECOURSE_TABLE",
    "TimecoursePoint",
    "USER_DATASET_CULTURE_PROCESS_TYPE",
    "USER_DATASET_MANIFEST",
    "USER_DATASET_MATURITY_DESIGN",
    "USER_DATASET_MATURITY_ESTIMATE",
    "USER_DATASET_MATURITY_FITTED",
    "USER_DATASET_MATURITY_GAP",
    "USER_DATASET_MATURITY_LITERATURE",
    "USER_DATASET_MATURITY_MEASURED",
    "USER_DATASET_MATURITY_ORDER",
    "USER_DATASET_PARAMETER_MATURITIES",
    "USER_DATASET_PH_IONIZATION_PROCESS_TYPE",
    "USER_DATASET_RECORD_MATURITY",
    "USER_DATASET_SCHEMA_VERSION",
    "UserDataError",
    "UserDataset",
    "UserTimecourse",
    "VMAX_ROUTES",
    "enzyme_class_acts_on",
    "load_user_dataset",
]
