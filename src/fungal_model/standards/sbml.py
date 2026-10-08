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
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fungal_model.core.units import ASSAY_BASE_UNITS, Q_, Quantity
from fungal_model.processes.homogeneous import (
    FirstOrderDecayProcess,
    HomogeneousMichaelisMentenProcess,
    MassActionProcess,
)
from fungal_model.processes.physiology import ProportionalSynthesisProcess

if TYPE_CHECKING:
    from fungal_model.processes.assembly import AssembledModel

SBML_EXPORTABLE_PROCESS_TYPES: tuple[str, ...] = (
    "first_order_decay",
    "mass_action",
    "homogeneous_michaelis_menten",
    "proportional_synthesis",
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
        self.non_si_base_units: list[str] = []

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
                if kind_name is None and name in ASSAY_BASE_UNITS:
                    # SBML has no extensible unit system. An assay-activity base
                    # unit is written as a dimensionless factor whose unit
                    # definition keeps the FungMod unit string as its name; the
                    # kinetic laws carry every numeric conversion explicitly, so
                    # no SI equivalent is implied. The model notes list them.
                    if name not in self.non_si_base_units:
                        self.non_si_base_units.append(name)
                    self._add_unit(definition, libsbml.UNIT_KIND_DIMENSIONLESS, exponent, 1.0)
                    continue
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
        for species, order in (*process.reactants.items(), *process.catalysts.items()):
            species_id = sid.of(species)
            if float(order) == 1.0:
                factors.append(species_id)
            else:
                factors.append(f"pow({species_id}, {float(order):g})")
        return reactants, products, tuple(process.catalysts), " * ".join(factors)

    if isinstance(process, HomogeneousMichaelisMentenProcess):
        if process.product_coefficient_units:
            # SBML stoichiometries are pure numbers; a unit-bearing coefficient would be frozen as one.
            raise SbmlExportError(
                f"Process {process.name!r} forms {', '.join(sorted(process.product_coefficient_units))} with a "
                "unit-bearing product coefficient (an amount of product per amount of substrate on another basis), "
                "which an SBML stoichiometry cannot carry; the exporter does not write it as a pure number."
            )
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

    if isinstance(process, ProportionalSynthesisProcess):
        products = {process.product_state: 1.0}
        law_species: list[str] = [process.producer_state]
        formula = f"{sid.of(process.specific_rate_symbol)} * {sid.of(process.producer_state)}"
        if process.induced:
            assert process.inducer_state is not None
            assert process.induction_half_saturation_symbol is not None
            inducer_id = sid.of(process.inducer_state)
            half_id = sid.of(process.induction_half_saturation_symbol)
            formula = f"{formula} * {inducer_id} / ({half_id} + {inducer_id})"
            if process.inducer_state != process.producer_state:
                law_species.append(process.inducer_state)
        return {}, products, tuple(law_species), formula

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


def _scaled_expression(expression: str, source_units: str, target_units: str) -> str:
    """Encode conversions in the math; SBML unit annotations never rescale values."""

    factor = _to_float(Q_(1.0, source_units).to(target_units).magnitude)
    if not math.isfinite(factor) or factor <= 0:
        raise SbmlExportError("Unit conversion must have a finite positive scale.")
    return expression if factor == 1.0 else f"({factor:.17g} * ({expression}))"


@dataclass(frozen=True)
class _ReactionSpec:
    """One SBML reaction derived from a FungMod process."""

    reactants: dict[str, float]
    products: dict[str, float]
    modifiers: tuple[str, ...]
    formula: str
    suffix: str = ""
    kinetic_law_sbo: bool = True


def _bound_coefficient_specs(process: Any, sid: _SIds, model: "AssembledModel") -> list[_ReactionSpec]:
    """Split parameter-bound product coefficients into reactions of their own.

    A product coefficient bound to a parameter ``Y`` (or ``1 - Y``) is written
    as a separate reaction whose kinetic law is ``Y * rate`` (or
    ``(1 - Y) * rate``), so the exported model keeps the dependence on ``Y``
    instead of freezing the numeric coefficient into the stoichiometry. The
    numeric coefficient must agree with the parameter's current value; the
    export is refused otherwise.
    """

    reactants, products, modifiers, formula = _reaction_spec(process, sid)
    bindings = dict(getattr(process, "product_coefficient_bindings", {}) or {})
    main = _ReactionSpec(
        dict(reactants),
        {state: coefficient for state, coefficient in products.items() if state not in bindings},
        tuple(modifiers),
        formula,
    )
    if not bindings:
        return [main]
    law_species = tuple(dict.fromkeys((*reactants, *modifiers)))
    specs = [main]
    for state, binding in bindings.items():
        try:
            parameter = model.parameters.get(binding.parameter_symbol)
        except KeyError as exc:
            raise SbmlExportError(
                f"Process {process.name!r} binds the coefficient of {state!r} to parameter "
                f"{binding.parameter_symbol!r}, which the model does not carry."
            ) from exc
        if parameter.quantity is None:
            raise SbmlExportError(
                f"Bound coefficient parameter {binding.parameter_symbol!r} is unknown; a value is required."
            )
        if parameter.quantity.dimensionality != Q_(1.0, "dimensionless").dimensionality:
            raise SbmlExportError(
                f"Bound coefficient parameter {binding.parameter_symbol!r} must be dimensionless; "
                f"got units {parameter.units!r}."
            )
        expected = binding.value(_to_float(parameter.quantity.to("dimensionless").magnitude))
        actual = float(products[state])
        if not math.isclose(expected, actual, rel_tol=1e-9, abs_tol=1e-12):
            raise SbmlExportError(
                f"Process {process.name!r} coefficient of {state!r} is {actual!r} but its binding "
                f"{binding.describe()} evaluates to {expected!r}; refusing to export an inconsistent model."
            )
        symbol_id = sid.of(binding.parameter_symbol)
        factor = f"(1 - {symbol_id})" if binding.complement else symbol_id
        specs.append(
            _ReactionSpec({}, {state: 1.0}, law_species, f"{factor} * ({formula})", suffix=f"__{state}", kinetic_law_sbo=False)
        )
    return specs


def _converted_reaction_specs(process: Any, sid: _SIds, model: "AssembledModel") -> list[_ReactionSpec]:
    return [_converted_reaction_spec(process, sid, model, spec) for spec in _bound_coefficient_specs(process, sid, model)]


def _converted_reaction_spec(process: Any, sid: _SIds, model: "AssembledModel", spec: _ReactionSpec) -> _ReactionSpec:
    reactants, products, modifiers, formula = spec.reactants, spec.products, spec.modifiers, spec.formula
    state_units = {spec.name: spec.units for spec in model.state_variables}
    expressions = {
        sid.of(spec.name): _scaled_expression(sid.of(spec.name), state_units[spec.name], spec.units)
        for spec in process.state_variables
    }
    for requirement in process.required_parameters:
        parameter = model.parameters.get(requirement.symbol)
        if parameter.quantity is None:
            raise SbmlExportError(f"Required parameter {requirement.symbol!r} is unknown.")
        expressions[sid.of(requirement.symbol)] = _scaled_expression(
            sid.of(requirement.symbol), parameter.units, requirement.units,
        )
    formula = re.sub(r"\b[A-Za-z_][A-Za-z0-9_]*\b", lambda match: expressions.get(match[0], match[0]), formula)
    if isinstance(process, FirstOrderDecayProcess):
        expression_units = Q_(1, process.state_units).units / Q_(1, "second").units
    elif isinstance(process, MassActionProcess):
        expression_units = Q_(1, process.rate_constant_units).units
        for name, order in (*process.reactants.items(), *process.catalysts.items()):
            expression_units *= Q_(1, process.state_units[name]).units ** order
    else:
        expression_units = Q_(1, process.rate_units).units
    # One reaction flux drives all participants. Convert its contribution for
    # each state, including states stored in different compatible unit scales.
    reference = next(iter(reactants or products))
    flux_units = f"({state_units[reference]}) / second"
    formula = _scaled_expression(formula, str(expression_units), flux_units)

    def converted(coefficients):
        return {
            name: coefficient * _to_float(Q_(1, flux_units).to(f"({state_units[name]}) / second").magnitude)
            for name, coefficient in coefficients.items()
        }

    return _ReactionSpec(
        converted(reactants), converted(products), modifiers, formula, suffix=spec.suffix, kinetic_law_sbo=spec.kinetic_law_sbo
    )


def to_sbml(
    model: "AssembledModel",
    *,
    initial_state: Mapping[str, Quantity],
    model_id: str = "fungmod_model",
    model_name: str | None = None,
    annotations: Mapping[str, Sequence[MiriamAnnotation]] | None = None,
    names_as_ids: bool = False,
) -> str:
    """Export an assembled FungMod model to an SBML Level 3 Version 2 string.

    Args:
        model: An assembled well-mixed model whose processes are all in
            :data:`SBML_EXPORTABLE_PROCESS_TYPES`.
        initial_state: Initial value (a pint quantity) for every state variable.
        model_id: SBML model identifier.
        model_name: Human-readable model name (defaults to ``model_id``).
        annotations: MIRIAM annotations keyed by ``"model"``, state name or
            process name.
        names_as_ids: Write each parameter's SBML ``name`` as its identifier
            (the FungMod symbol) instead of its descriptive name, for tools
            that address model entities by name.

    Product coefficients bound to a parameter (``ProductReleaseMap``
    ``coefficient_bindings``) are written as separate reactions whose kinetic
    law multiplies the process rate by the parameter, so the dependence stays
    live in the exported model. Assay-activity base units, which SBML cannot
    express, are written as named dimensionless unit definitions and listed in
    the model notes.

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
        sbml_parameter.setName(sid.of(parameter.symbol) if names_as_ids else (parameter.name or parameter.symbol))
        sbml_parameter.setValue(_to_float(quantity.magnitude))
        sbml_parameter.setUnits(units.id_for(parameter.units))
        sbml_parameter.setConstant(True)
        if parameter.symbol in parameter_sbo:
            sbml_parameter.setSBOTerm(parameter_sbo[parameter.symbol])

    for index, process in enumerate(model.processes):
        for spec in _converted_reaction_specs(process, sid, model):
            reaction_id = sid.of(f"{process.name}{spec.suffix}__reaction_{index}")
            reaction = sbml_model.createReaction()
            reaction.setId(reaction_id)
            reaction.setMetaId(f"meta_{reaction_id}")
            reaction.setName(process.name + spec.suffix.replace("__", " -> ", 1))
            reaction.setReversible(False)
            reaction.setSBOTerm(_SBO_BIOCHEMICAL_REACTION)
            for species_name, coefficient in spec.reactants.items():
                reference = reaction.createReactant()
                reference.setSpecies(sid.of(species_name))
                reference.setStoichiometry(float(coefficient))
                reference.setConstant(True)
            for species_name, coefficient in spec.products.items():
                reference = reaction.createProduct()
                reference.setSpecies(sid.of(species_name))
                reference.setStoichiometry(float(coefficient))
                reference.setConstant(True)
            for species_name in spec.modifiers:
                reference = reaction.createModifier()
                reference.setSpecies(sid.of(species_name))
                reference.setSBOTerm(_SBO_ENZYMATIC_CATALYST)
            if process.name in annotations and not spec.suffix:
                _apply_miriam(libsbml, reaction, annotations[process.name])
            kinetic_law = reaction.createKineticLaw()
            law_sbo = _KINETIC_LAW_SBO.get(process.process_type) if spec.kinetic_law_sbo else None
            if law_sbo is not None:
                kinetic_law.setSBOTerm(law_sbo)
            math_ast = libsbml.parseL3Formula(spec.formula)
            if math_ast is None:
                raise SbmlExportError(
                    f"Failed to parse kinetic law for {process.name!r}: "
                    f"{libsbml.getLastParseL3Error()} (formula: {spec.formula})"
                )
            kinetic_law.setMath(math_ast)

    notes = (
        "<body xmlns='http://www.w3.org/1999/xhtml'><p>Exported from FungMod. "
        "Well-mixed model; species are represented as SBML amounts in a unit "
        "(size 1) compartment so the kinetic law reproduces FungMod's rate law "
        "exactly.</p>"
    )
    if units.non_si_base_units:
        notes += (
            "<p>Assay-activity base units without an SI representation are written as "
            "named dimensionless unit definitions; the kinetic laws carry every numeric "
            "conversion explicitly and no SI equivalent is implied: "
            + ", ".join(units.non_si_base_units)
            + ".</p>"
        )
    sbml_model.setNotes(notes + "</body>")

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
