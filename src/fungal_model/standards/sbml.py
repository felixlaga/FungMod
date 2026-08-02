"""SBML Level 3 export for FungMod's supported well-mixed kinetic models.

FungMod assembles well-mixed models from :class:`~fungal_model.processes.base.Process`
objects. The three processes with closed-form, standard kinetic laws are
exportable to SBML:

- :class:`~fungal_model.processes.homogeneous.FirstOrderDecayProcess` — ``k * S``
- :class:`~fungal_model.processes.homogeneous.MassActionProcess` — ``k * prod(S_i^order_i)``
- :class:`~fungal_model.processes.homogeneous.HomogeneousMichaelisMentenProcess`
  — ``Vmax * S / (Km + S)`` or ``kcat * E * S / (Km + S)``

Any other process (surface catalysis, transglycosylation, rate-modifier
wrappers such as inhibition laws) and any model carrying dynamic thermodynamic
constraints is **rejected** with :class:`SbmlExportError` rather than exported
inexactly — the exported SBML must reproduce the FungMod rate law exactly.

Species are written as SBML amounts in a unit ("size 1") compartment. FungMod's
well-mixed state values are concentrations; representing them as amounts in a
unit compartment makes the exported kinetic law numerically identical to
FungMod's own right-hand side, which is what cross-engine trajectory checks
require. This convention is recorded in the model notes.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fungal_model.core.units import Q_, Quantity
from fungal_model.processes.homogeneous import (
    FirstOrderDecayProcess,
    HomogeneousMichaelisMentenProcess,
    MassActionProcess,
)

if TYPE_CHECKING:
    from fungal_model.processes.assembly import AssembledModel

SBML_EXPORTABLE_PROCESS_TYPES: tuple[str, ...] = (
    "first_order_decay",
    "mass_action",
    "homogeneous_michaelis_menten",
)

# pint base-unit name -> SBML UnitKind name. Populated lazily from libsbml so the
# module imports without the optional dependency installed.
_PINT_BASE_TO_SBML_KIND = {
    "mole": "UNIT_KIND_MOLE",
    "meter": "UNIT_KIND_METRE",
    "metre": "UNIT_KIND_METRE",
    "second": "UNIT_KIND_SECOND",
    "kilogram": "UNIT_KIND_KILOGRAM",
    "ampere": "UNIT_KIND_AMPERE",
    "kelvin": "UNIT_KIND_KELVIN",
    "candela": "UNIT_KIND_CANDELA",
    "radian": "UNIT_KIND_DIMENSIONLESS",
}


class SbmlExportError(RuntimeError):
    """Raised when a FungMod model cannot be exported to SBML."""


def _to_float(value: Any) -> float:
    """Coerce a (possibly numpy/pint) real scalar to a Python float."""

    return float(value)


@dataclass(frozen=True)
class MiriamAnnotation:
    """A MIRIAM annotation: a biology/model qualifier and identifier resources.

    ``qualifier`` is a CURIE such as ``"bqbiol:is"``, ``"bqbiol:isVersionOf"``,
    ``"bqbiol:hasTaxon"``, or ``"bqmodel:isDescribedBy"``. ``resources`` are
    identifier URIs (typically ``https://identifiers.org/...``).
    """

    qualifier: str
    resources: tuple[str, ...]


# SBO terms for the kinetic laws FungMod exports (by process_type).
_KINETIC_LAW_SBO = {
    "homogeneous_michaelis_menten": 29,  # Henri-Michaelis-Menten rate law
    "mass_action": 41,  # mass action rate law
    "first_order_decay": 49,  # first-order irreversible mass action kinetics
}
_SBO_SIMPLE_CHEMICAL = 247
_SBO_MACROMOLECULE = 252  # polypeptide chain (enzyme)
_SBO_BIOCHEMICAL_REACTION = 176
_SBO_ENZYMATIC_CATALYST = 460  # modifier role
# SBO terms for kinetic parameters (by role).
_SBO_KM = 27
_SBO_VMAX = 186
_SBO_KCAT = 25
_SBO_KINETIC_CONSTANT = 9


def _qualifier_terms(libsbml: Any, qualifier: str) -> tuple[int, int]:
    """Map a qualifier CURIE to (qualifier-type, specific-qualifier) libsbml enums."""

    biological = {
        "bqbiol:is": libsbml.BQB_IS,
        "bqbiol:isVersionOf": libsbml.BQB_IS_VERSION_OF,
        "bqbiol:hasVersion": libsbml.BQB_HAS_VERSION,
        "bqbiol:hasPart": libsbml.BQB_HAS_PART,
        "bqbiol:isPartOf": libsbml.BQB_IS_PART_OF,
        "bqbiol:hasTaxon": libsbml.BQB_HAS_TAXON,
        "bqbiol:encodes": libsbml.BQB_ENCODES,
        "bqbiol:occursIn": libsbml.BQB_OCCURS_IN,
    }
    model_level = {
        "bqmodel:is": libsbml.BQM_IS,
        "bqmodel:isDescribedBy": libsbml.BQM_IS_DESCRIBED_BY,
        "bqmodel:isDerivedFrom": libsbml.BQM_IS_DERIVED_FROM,
    }
    if qualifier in biological:
        return libsbml.BIOLOGICAL_QUALIFIER, biological[qualifier]
    if qualifier in model_level:
        return libsbml.MODEL_QUALIFIER, model_level[qualifier]
    raise SbmlExportError(f"Unsupported MIRIAM qualifier {qualifier!r}.")


def _apply_miriam(libsbml: Any, element: Any, annotations: Sequence[MiriamAnnotation]) -> None:
    """Attach MIRIAM CVTerms to an SBML element (which must already have a metaid)."""

    for annotation in annotations:
        term = libsbml.CVTerm()
        qualifier_type, specific = _qualifier_terms(libsbml, annotation.qualifier)
        term.setQualifierType(qualifier_type)
        if qualifier_type == libsbml.BIOLOGICAL_QUALIFIER:
            term.setBiologicalQualifierType(specific)
        else:
            term.setModelQualifierType(specific)
        for resource in annotation.resources:
            term.addResource(resource)
        element.addCVTerm(term)


def _require_libsbml() -> Any:
    try:
        import libsbml
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised via error path
        raise SbmlExportError(
            "SBML export requires the optional 'standards' dependency. "
            "Install it with: pip install fungmod[standards]"
        ) from exc
    return libsbml


class _SIds:
    """Assigns unique, valid SBML SIds and preserves the original names.

    Species, parameters, reactions, compartments, and unit definitions share a
    single SId namespace in SBML, so uniqueness is enforced globally.
    """

    def __init__(self) -> None:
        self._by_original: dict[str, str] = {}
        self._used: set[str] = set()

    def reserve(self, sid: str) -> str:
        if sid in self._used:
            raise SbmlExportError(f"Duplicate SBML identifier: {sid!r}")
        self._used.add(sid)
        return sid

    def of(self, original: str) -> str:
        if original in self._by_original:
            return self._by_original[original]
        candidate = re.sub(r"[^0-9A-Za-z_]", "_", original)
        if not candidate or not (candidate[0].isalpha() or candidate[0] == "_"):
            candidate = f"_{candidate}"
        unique = candidate
        suffix = 1
        while unique in self._used:
            unique = f"{candidate}_{suffix}"
            suffix += 1
        self._used.add(unique)
        self._by_original[original] = unique
        return unique


class _UnitDefinitions:
    """Builds and caches SBML UnitDefinitions from pint unit strings."""

    def __init__(self, libsbml: Any, model: Any, sids: _SIds) -> None:
        self._libsbml = libsbml
        self._model = model
        self._sids = sids
        self._by_unit: dict[str, str] = {}
        self._counter = 0

    def id_for(self, unit_str: str) -> str:
        key = str(unit_str)
        if key in self._by_unit:
            return self._by_unit[key]
        libsbml = self._libsbml
        base = Q_(1.0, key).to_base_units()
        multiplier = _to_float(base.magnitude)
        exponents = {str(name): float(exp) for name, exp in dict(base.units._units).items()}

        unit_id = self._sids.reserve(f"unit_{self._counter}")
        self._counter += 1
        definition = self._model.createUnitDefinition()
        definition.setId(unit_id)
        definition.setName(key)

        if not exponents:
            self._add_unit(definition, libsbml.UNIT_KIND_DIMENSIONLESS, 1.0, multiplier)
        else:
            if abs(multiplier - 1.0) > 1e-12 * max(1.0, abs(multiplier)):
                self._add_unit(definition, libsbml.UNIT_KIND_DIMENSIONLESS, 1.0, multiplier)
            for name, exponent in exponents.items():
                kind_name = _PINT_BASE_TO_SBML_KIND.get(name)
                if kind_name is None:
                    raise SbmlExportError(
                        f"Cannot represent unit {key!r} in SBML: unsupported base unit {name!r}."
                    )
                self._add_unit(definition, getattr(libsbml, kind_name), exponent, 1.0)

        self._by_unit[key] = unit_id
        return unit_id

    def _add_unit(self, definition: Any, kind: Any, exponent: float, multiplier: float) -> None:
        unit = definition.createUnit()
        unit.setKind(kind)
        unit.setExponent(float(exponent))
        unit.setScale(0)
        unit.setMultiplier(float(multiplier))


def _reaction_spec(
    process: Any, sid: _SIds
) -> tuple[dict[str, float], dict[str, float], tuple[str, ...], str]:
    """Return (reactants, products, modifiers, kinetic-law formula) for a process.

    Species keys are original FungMod names; the formula uses sanitized SIds.
    """

    if isinstance(process, FirstOrderDecayProcess):
        reactants = {process.substrate_state: 1.0}
        products = {process.product_state: 1.0} if process.product_state is not None else {}
        formula = f"{sid.of(process.rate_constant_symbol)} * {sid.of(process.substrate_state)}"
        return reactants, products, (), formula

    if isinstance(process, MassActionProcess):
        reactants = {species: float(order) for species, order in process.reactants.items()}
        products = {species: float(coeff) for species, coeff in process.products.items()}
        factors = [sid.of(process.rate_constant_symbol)]
        for species, order in process.reactants.items():
            species_id = sid.of(species)
            if float(order) == 1.0:
                factors.append(species_id)
            else:
                factors.append(f"pow({species_id}, {float(order):g})")
        return reactants, products, (), " * ".join(factors)

    if isinstance(process, HomogeneousMichaelisMentenProcess):
        reactants = {process.substrate_state: 1.0}
        products = {species: float(coeff) for species, coeff in process.product_coefficients.items()}
        substrate_id = sid.of(process.substrate_state)
        km_id = sid.of(process.km_symbol)
        if process.vmax_symbol is not None:
            vmax_id = sid.of(process.vmax_symbol)
            formula = f"{vmax_id} * {substrate_id} / ({km_id} + {substrate_id})"
            return reactants, products, (), formula
        assert process.kcat_symbol is not None and process.enzyme_state is not None
        kcat_id = sid.of(process.kcat_symbol)
        enzyme_id = sid.of(process.enzyme_state)
        formula = f"{kcat_id} * {enzyme_id} * {substrate_id} / ({km_id} + {substrate_id})"
        return reactants, products, (process.enzyme_state,), formula

    if hasattr(process, "base_process"):
        modifiers = getattr(process, "rate_modifiers", ())
        names = ", ".join(type(modifier).__name__ for modifier in modifiers) or "unknown"
        raise SbmlExportError(
            f"Process {process.name!r} is wrapped by rate modifiers ({names}), which are "
            "not supported by the SBML exporter. Export the unmodified process instead."
        )

    raise SbmlExportError(
        f"Process {process.name!r} (type {process.process_type!r}) is not SBML-exportable. "
        f"Supported process types: {', '.join(SBML_EXPORTABLE_PROCESS_TYPES)}."
    )


def _parameter_sbo_terms(model: "AssembledModel") -> dict[str, int]:
    """Map parameter symbols to SBO terms by their kinetic role."""

    terms: dict[str, int] = {}
    for process in model.processes:
        if isinstance(process, HomogeneousMichaelisMentenProcess):
            terms[process.km_symbol] = _SBO_KM
            if process.vmax_symbol is not None:
                terms[process.vmax_symbol] = _SBO_VMAX
            if process.kcat_symbol is not None:
                terms[process.kcat_symbol] = _SBO_KCAT
        elif isinstance(process, (MassActionProcess, FirstOrderDecayProcess)):
            terms[process.rate_constant_symbol] = _SBO_KINETIC_CONSTANT
    return terms


def to_sbml(
    model: "AssembledModel",
    *,
    initial_state: Mapping[str, Quantity],
    model_id: str = "fungmod_model",
    model_name: str | None = None,
    annotations: Mapping[str, Sequence[MiriamAnnotation]] | None = None,
) -> str:
    """Export an assembled FungMod model to an SBML Level 3 Version 2 string.

    Args:
        model: An assembled well-mixed model whose processes are all in
            :data:`SBML_EXPORTABLE_PROCESS_TYPES`.
        initial_state: Initial value (a pint quantity) for every state variable.
        model_id: SBML model identifier.
        model_name: Human-readable model name (defaults to ``model_id``).

    Returns:
        The SBML document serialized as an XML string.

    Raises:
        SbmlExportError: If the model contains an unsupported process, a
            rate-modifier wrapper, a dynamic thermodynamic constraint, or an
            initial value is missing for a state variable.
    """

    libsbml = _require_libsbml()

    if getattr(model, "thermodynamic_constraints", ()):
        raise SbmlExportError(
            "Model carries dynamic thermodynamic constraints, which gate the rate law "
            "at solver time and are not standard SBML kinetics. Export is refused to "
            "avoid producing an SBML model that does not match FungMod's behaviour."
        )

    annotations = annotations or {}
    parameter_sbo = _parameter_sbo_terms(model)

    sid = _SIds()
    document = libsbml.SBMLDocument(3, 2)
    sbml_model = document.createModel()
    model_sid = sid.reserve(_sanitize_model_id(model_id))
    sbml_model.setId(model_sid)
    sbml_model.setMetaId(f"meta_{model_sid}")
    sbml_model.setName(model_name or model_id)
    if "model" in annotations:
        _apply_miriam(libsbml, sbml_model, annotations["model"])
    sbml_model.setNotes(
        "<body xmlns='http://www.w3.org/1999/xhtml'><p>Exported from FungMod. "
        "Well-mixed model; species are represented as SBML amounts in a unit "
        "(size 1) compartment so the kinetic law reproduces FungMod's rate law "
        "exactly.</p></body>"
    )

    units = _UnitDefinitions(libsbml, sbml_model, sid)
    sbml_model.setTimeUnits(units.id_for("second"))

    compartment_id = sid.reserve("compartment")
    compartment = sbml_model.createCompartment()
    compartment.setId(compartment_id)
    compartment.setConstant(True)
    compartment.setSize(1.0)
    compartment.setSpatialDimensions(3)

    # Guard against a species name colliding with a parameter symbol.
    species_names = {spec.name for spec in model.state_variables}
    for parameter in model.parameters:
        if parameter.symbol in species_names:
            raise SbmlExportError(
                f"Ambiguous identifier {parameter.symbol!r} is both a species and a parameter."
            )

    for spec in model.state_variables:
        if spec.name not in initial_state:
            raise SbmlExportError(f"Missing initial value for state variable {spec.name!r}.")
        value = initial_state[spec.name].to(spec.units)
        species_id = sid.of(spec.name)
        species = sbml_model.createSpecies()
        species.setId(species_id)
        species.setMetaId(f"meta_{species_id}")
        species.setName(spec.name)
        species.setCompartment(compartment_id)
        species.setInitialAmount(_to_float(value.magnitude))
        species.setSubstanceUnits(units.id_for(spec.units))
        species.setHasOnlySubstanceUnits(True)
        species.setBoundaryCondition(False)
        species.setConstant(False)
        species.setSBOTerm(_SBO_MACROMOLECULE if spec.role == "enzyme" else _SBO_SIMPLE_CHEMICAL)
        if spec.name in annotations:
            _apply_miriam(libsbml, species, annotations[spec.name])

    for parameter in model.parameters:
        quantity = parameter.quantity
        if quantity is None:
            continue
        sbml_parameter = sbml_model.createParameter()
        sbml_parameter.setId(sid.of(parameter.symbol))
        sbml_parameter.setName(parameter.name or parameter.symbol)
        sbml_parameter.setValue(_to_float(quantity.magnitude))
        sbml_parameter.setUnits(units.id_for(parameter.units))
        sbml_parameter.setConstant(True)
        if parameter.symbol in parameter_sbo:
            sbml_parameter.setSBOTerm(parameter_sbo[parameter.symbol])

    for index, process in enumerate(model.processes):
        reactants, products, modifiers, formula = _reaction_spec(process, sid)
        reaction_id = sid.of(f"{process.name}__reaction_{index}")
        reaction = sbml_model.createReaction()
        reaction.setId(reaction_id)
        reaction.setMetaId(f"meta_{reaction_id}")
        reaction.setName(process.name)
        reaction.setReversible(False)
        reaction.setSBOTerm(_SBO_BIOCHEMICAL_REACTION)
        for species_name, coefficient in reactants.items():
            reference = reaction.createReactant()
            reference.setSpecies(sid.of(species_name))
            reference.setStoichiometry(float(coefficient))
            reference.setConstant(True)
        for species_name, coefficient in products.items():
            reference = reaction.createProduct()
            reference.setSpecies(sid.of(species_name))
            reference.setStoichiometry(float(coefficient))
            reference.setConstant(True)
        for species_name in modifiers:
            reference = reaction.createModifier()
            reference.setSpecies(sid.of(species_name))
            reference.setSBOTerm(_SBO_ENZYMATIC_CATALYST)
        if process.name in annotations:
            _apply_miriam(libsbml, reaction, annotations[process.name])
        kinetic_law = reaction.createKineticLaw()
        law_sbo = _KINETIC_LAW_SBO.get(process.process_type)
        if law_sbo is not None:
            kinetic_law.setSBOTerm(law_sbo)
        math_ast = libsbml.parseL3Formula(formula)
        if math_ast is None:
            raise SbmlExportError(
                f"Failed to parse kinetic law for {process.name!r}: "
                f"{libsbml.getLastParseL3Error()} (formula: {formula})"
            )
        kinetic_law.setMath(math_ast)

    _raise_on_sbml_errors(libsbml, document)
    return libsbml.writeSBMLToString(document)


def write_sbml(
    model: "AssembledModel",
    path: str | Path,
    *,
    initial_state: Mapping[str, Quantity],
    model_id: str = "fungmod_model",
    model_name: str | None = None,
    annotations: Mapping[str, Sequence[MiriamAnnotation]] | None = None,
) -> Path:
    """Export an assembled model to SBML and write it to ``path``."""

    text = to_sbml(
        model, initial_state=initial_state, model_id=model_id, model_name=model_name, annotations=annotations
    )
    destination = Path(path)
    destination.write_text(text, encoding="utf-8", newline="")
    return destination


def model_config_to_sbml(config_path: str | Path) -> str:
    """Load a model config, assemble it, and export it to SBML.

    Uses the initial state declared in the config. The config must assemble to a
    model whose processes are all SBML-exportable (see
    :data:`SBML_EXPORTABLE_PROCESS_TYPES`).
    """

    from fungal_model.io.model_config import load_model_config
    from fungal_model.workflows.configured_inputs import ConfiguredInputLoader
    from fungal_model.workflows.configured_processes import ConfiguredProcessAssembler

    config = load_model_config(config_path)
    inputs = ConfiguredInputLoader().load(config)
    assembly = ConfiguredProcessAssembler().assemble(config, inputs)
    return to_sbml(
        assembly.model,
        initial_state=inputs.initial_state,
        model_id=config.name,
        model_name=config.name,
    )


def write_model_config_sbml(config_path: str | Path, path: str | Path) -> Path:
    """Load, assemble, and export a model config to an SBML file at ``path``."""

    text = model_config_to_sbml(config_path)
    destination = Path(path)
    destination.write_text(text, encoding="utf-8", newline="")
    return destination


def _sanitize_model_id(model_id: str) -> str:
    candidate = re.sub(r"[^0-9A-Za-z_]", "_", str(model_id))
    if not candidate or not (candidate[0].isalpha() or candidate[0] == "_"):
        candidate = f"_{candidate}"
    return candidate


def _raise_on_sbml_errors(libsbml: Any, document: Any) -> None:
    document.checkConsistency()
    problems = []
    for index in range(document.getNumErrors()):
        error = document.getError(index)
        if error.getSeverity() >= libsbml.LIBSBML_SEV_ERROR:
            problems.append(f"[{error.getErrorId()}] {error.getMessage().strip()}")
    if problems:
        raise SbmlExportError("SBML export produced an invalid document:\n" + "\n".join(problems))
