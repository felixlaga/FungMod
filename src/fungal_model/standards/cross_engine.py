"""Cross-engine trajectory checks for FungMod SBML exports.

FungMod integrates its models with :class:`~fungal_model.solvers.process_ode.ProcessODESolver`.
An SBML export is only trustworthy if a *different* engine, reading only the
exported SBML, reproduces the same trajectory. This module provides:

- :func:`simulate_reference_sbml` — a small, independent ODE integrator that
  consumes an SBML document produced by :mod:`fungal_model.standards.sbml` and
  integrates ``d(amount)/dt = sum(stoichiometry * kinetic_law)`` with SciPy.
- :func:`cross_engine_trajectory_check` — runs FungMod's own engine and the
  reference SBML engine on the same model and time grid and reports the
  per-species maximum absolute difference.

The reference simulator is deliberately restricted to the subset of SBML that
FungMod emits: constant parameters, species as amounts in a unit compartment,
irreversible reactions, and kinetic laws built from ``+ - * /`` and ``pow``.
It raises :class:`~fungal_model.standards.sbml.SbmlExportError` on any construct
outside that subset rather than returning a silently wrong result. It is a
verification aid, not a general-purpose SBML simulator.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from fungal_model.core.units import Q_, Quantity
from fungal_model.standards.sbml import SbmlExportError, to_sbml

if TYPE_CHECKING:
    from fungal_model.processes.assembly import AssembledModel


KineticFormula = Callable[[Mapping[str, float]], float]
"""A compiled kinetic law: maps a symbol environment to a rate."""

_NUMBER = re.compile(r"(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_OPERATORS = frozenset("+-*/^(),")


def _unsupported(formula: str, detail: str) -> SbmlExportError:
    return SbmlExportError(
        "Kinetic law contains an unsupported operation for the reference simulator: "
        f"{formula} ({detail})"
    )


def _tokenize(formula: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    position = 0
    while position < len(formula):
        character = formula[position]
        if character.isspace():
            position += 1
            continue
        if character in _OPERATORS:
            tokens.append(("operator", character))
            position += 1
            continue
        for kind, pattern in (("number", _NUMBER), ("name", _NAME)):
            match = pattern.match(formula, position)
            if match is not None:
                tokens.append((kind, match.group(0)))
                position = match.end()
                break
        else:
            raise _unsupported(formula, f"unrecognised text {formula[position:position + 12]!r}")
    return tokens


def _binary(operator: str, left: KineticFormula, right: KineticFormula) -> KineticFormula:
    if operator == "+":
        return lambda environment: left(environment) + right(environment)
    if operator == "-":
        return lambda environment: left(environment) - right(environment)
    if operator == "*":
        return lambda environment: left(environment) * right(environment)
    if operator == "/":
        return lambda environment: left(environment) / right(environment)
    return lambda environment: left(environment) ** right(environment)


class _FormulaParser:
    """Recursive-descent parser for the L3 infix subset FungMod emits.

    Grammar (``^`` binds tighter than unary minus and is right-associative,
    matching libSBML's L3 infix rules)::

        expression := term (("+" | "-") term)*
        term       := unary (("*" | "/") unary)*
        unary      := ("+" | "-") unary | power
        power      := atom ("^" unary)?
        atom       := NUMBER | NAME | "pow" "(" expression "," expression ")"
                    | "(" expression ")"
    """

    def __init__(self, formula: str, symbols: Collection[str]) -> None:
        self.formula = formula
        self.symbols = frozenset(symbols)
        self.tokens = _tokenize(formula)
        self.position = 0

    def parse(self) -> KineticFormula:
        if not self.tokens:
            raise _unsupported(self.formula, "empty formula")
        result = self._expression()
        if self.position != len(self.tokens):
            raise _unsupported(self.formula, f"unexpected {self.tokens[self.position][1]!r}")
        return result

    def _peek(self, *operators: str) -> str | None:
        if self.position < len(self.tokens):
            kind, value = self.tokens[self.position]
            if kind == "operator" and value in operators:
                return value
        return None

    def _expect(self, operator: str) -> None:
        if self._peek(operator) is None:
            raise _unsupported(self.formula, f"expected {operator!r}")
        self.position += 1

    def _expression(self) -> KineticFormula:
        result = self._term()
        while (operator := self._peek("+", "-")) is not None:
            self.position += 1
            result = _binary(operator, result, self._term())
        return result

    def _term(self) -> KineticFormula:
        result = self._unary()
        while (operator := self._peek("*", "/")) is not None:
            self.position += 1
            result = _binary(operator, result, self._unary())
        return result

    def _unary(self) -> KineticFormula:
        operator = self._peek("+", "-")
        if operator is None:
            return self._power()
        self.position += 1
        operand = self._unary()
        if operator == "+":
            return operand
        return lambda environment: -operand(environment)

    def _power(self) -> KineticFormula:
        base = self._atom()
        if self._peek("^") is None:
            return base
        self.position += 1
        return _binary("^", base, self._unary())

    def _atom(self) -> KineticFormula:
        if self.position >= len(self.tokens):
            raise _unsupported(self.formula, "incomplete expression")
        kind, value = self.tokens[self.position]
        self.position += 1
        if kind == "number":
            constant = float(value)
            return lambda _environment: constant
        if kind == "name":
            if self._peek("(") is not None:
                if value != "pow":
                    raise _unsupported(self.formula, f"function {value!r}")
                self.position += 1
                base = self._expression()
                self._expect(",")
                exponent = self._expression()
                self._expect(")")
                return _binary("^", base, exponent)
            if value not in self.symbols:
                raise SbmlExportError(f"Unknown symbol {value!r} in kinetic law.")
            name = value
            return lambda environment: float(environment[name])
        if kind == "operator" and value == "(":
            inner = self._expression()
            self._expect(")")
            return inner
        raise _unsupported(self.formula, f"unexpected {value!r}")


def compile_kinetic_formula(formula: str, symbols: Collection[str]) -> KineticFormula:
    """Compile an L3 infix kinetic law into a callable over a symbol environment.

    Only the subset FungMod emits is accepted: numbers, the given ``symbols``,
    ``+ - * /``, ``^`` and ``pow(base, exponent)``. Anything else raises
    :class:`~fungal_model.standards.sbml.SbmlExportError` at compile time, so a
    wrong rate can never be integrated silently.

    The reference simulator works from the formula *text* rather than from
    libSBML ``ASTNode`` objects on purpose. SWIG keeps one proxy registry per
    process, so once ``libsedml`` has been imported (for example by a SED-ML
    export in the same session), kinetic-law nodes come back wrapped by its
    classes and libSBML's ``AST_*`` type constants no longer match them.
    """

    return _FormulaParser(formula, symbols).parse()


def simulate_reference_sbml(
    sbml: str | Path,
    *,
    times: np.ndarray,
    rtol: float = 1e-9,
    atol: float = 1e-12,
) -> dict[str, np.ndarray]:
    """Integrate an exported SBML document with an independent SciPy engine.

    Args:
        sbml: SBML XML text, or a path to an ``.xml`` file.
        times: Monotonic time points (in seconds) at which to report species.
        rtol: SciPy ``solve_ivp`` relative tolerance.
        atol: SciPy ``solve_ivp`` absolute tolerance.

    Returns:
        A mapping from species *name* (the original FungMod name) to its
        trajectory array aligned to ``times``.

    Raises:
        SbmlExportError: If the document uses SBML constructs outside the subset
            FungMod emits (rules, events, function definitions, non-constant
            parameters, or an unsupported kinetic-law operation).
    """

    try:
        import libsbml
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised via error path
        raise SbmlExportError(
            "Cross-engine checks require the optional 'standards' dependency. "
            "Install it with: pip install fungmod[standards]"
        ) from exc
    from scipy.integrate import solve_ivp

    text = Path(sbml).read_text(encoding="utf-8") if _looks_like_path(sbml) else str(sbml)
    document = libsbml.readSBMLFromString(text)
    model = document.getModel()
    if model is None:
        raise SbmlExportError("Could not parse the SBML document.")

    for unsupported, count in (
        ("rules", model.getNumRules()),
        ("events", model.getNumEvents()),
        ("function definitions", model.getNumFunctionDefinitions()),
        ("initial assignments", model.getNumInitialAssignments()),
    ):
        if count:
            raise SbmlExportError(f"Reference simulator does not support SBML {unsupported}.")

    species_ids = [model.getSpecies(i).getId() for i in range(model.getNumSpecies())]
    species_names = {
        model.getSpecies(i).getId(): (model.getSpecies(i).getName() or model.getSpecies(i).getId())
        for i in range(model.getNumSpecies())
    }
    index = {species_id: position for position, species_id in enumerate(species_ids)}
    y0 = np.array([model.getSpecies(i).getInitialAmount() for i in range(model.getNumSpecies())], dtype=float)

    parameters: dict[str, float] = {}
    for i in range(model.getNumParameters()):
        parameter = model.getParameter(i)
        if not parameter.getConstant():
            raise SbmlExportError(f"Reference simulator requires constant parameters; {parameter.getId()!r} is not.")
        parameters[parameter.getId()] = parameter.getValue()

    symbols = set(parameters) | set(species_ids)
    reactions: list[tuple[KineticFormula, dict[str, float]]] = []
    for i in range(model.getNumReactions()):
        reaction = model.getReaction(i)
        kinetic_law = reaction.getKineticLaw()
        if kinetic_law is None or kinetic_law.getMath() is None:
            raise SbmlExportError(f"Reaction {reaction.getId()!r} has no kinetic law.")
        stoichiometry: dict[str, float] = {}
        for j in range(reaction.getNumReactants()):
            reference = reaction.getReactant(j)
            stoichiometry[reference.getSpecies()] = (
                stoichiometry.get(reference.getSpecies(), 0.0) - reference.getStoichiometry()
            )
        for j in range(reaction.getNumProducts()):
            reference = reaction.getProduct(j)
            stoichiometry[reference.getSpecies()] = (
                stoichiometry.get(reference.getSpecies(), 0.0) + reference.getStoichiometry()
            )
        formula = libsbml.formulaToL3String(kinetic_law.getMath())
        if not formula:
            raise SbmlExportError(f"Reaction {reaction.getId()!r} has an unreadable kinetic law.")
        reactions.append((compile_kinetic_formula(formula, symbols), stoichiometry))

    def rhs(_t: float, y: np.ndarray) -> np.ndarray:
        environment: dict[str, float] = dict(parameters)
        for species_id in species_ids:
            environment[species_id] = y[index[species_id]]
        derivatives = np.zeros_like(y)
        for rate_of, stoichiometry in reactions:
            rate = rate_of(environment)
            for species_id, coefficient in stoichiometry.items():
                derivatives[index[species_id]] += coefficient * rate
        return derivatives

    grid = np.asarray(times, dtype=float)
    solution = solve_ivp(
        rhs, (float(grid[0]), float(grid[-1])), y0, t_eval=grid, rtol=rtol, atol=atol, method="LSODA"
    )
    if not solution.success:  # pragma: no cover - defensive
        raise SbmlExportError(f"Reference SBML integration failed: {solution.message}")
    return {species_names[species_id]: solution.y[index[species_id]] for species_id in species_ids}


@dataclass(frozen=True)
class CrossEngineComparison:
    """Result of comparing FungMod's engine with the reference SBML engine."""

    times: np.ndarray
    fungmod: dict[str, np.ndarray]
    sbml: dict[str, np.ndarray]
    max_absolute_difference: dict[str, float]

    @property
    def worst_absolute_difference(self) -> float:
        return max(self.max_absolute_difference.values(), default=0.0)

    def agrees(self, *, atol: float = 1e-6) -> bool:
        """Return whether every species agrees within ``atol``."""

        return self.worst_absolute_difference <= atol


def cross_engine_trajectory_check(
    model: "AssembledModel",
    *,
    initial_state: Mapping[str, Quantity],
    times: Quantity,
    rtol: float = 1e-9,
    atol: float = 1e-12,
) -> CrossEngineComparison:
    """Run FungMod and the reference SBML engine and compare their trajectories.

    Args:
        model: An SBML-exportable assembled model.
        initial_state: Initial value for each state variable.
        times: Time points (a pint quantity) shared by both engines.
        rtol: Relative tolerance for the reference SBML integration.
        atol: Absolute tolerance for the reference SBML integration.

    Returns:
        A :class:`CrossEngineComparison` with per-species maximum absolute
        differences.
    """

    seconds = np.asarray(Q_(times).to("second").magnitude, dtype=float)
    t_span = (Q_(seconds[0], "second"), Q_(seconds[-1], "second"))

    result = model.run(
        initial_state=initial_state,
        t_span=t_span,
        t_eval=Q_(seconds, "second"),
        label="cross_engine_check",
    )

    sbml_text = to_sbml(model, initial_state=initial_state)
    sbml_trajectories = simulate_reference_sbml(sbml_text, times=seconds, rtol=rtol, atol=atol)

    fungmod_trajectories: dict[str, np.ndarray] = {}
    differences: dict[str, float] = {}
    for spec in model.state_variables:
        name = spec.name
        fungmod_values = np.asarray(result.state(name).to(spec.units).magnitude, dtype=float)
        sbml_values = np.asarray(sbml_trajectories[name], dtype=float)
        fungmod_trajectories[name] = fungmod_values
        differences[name] = float(np.max(np.abs(fungmod_values - sbml_values)))

    return CrossEngineComparison(
        times=seconds,
        fungmod=fungmod_trajectories,
        sbml=sbml_trajectories,
        max_absolute_difference=differences,
    )


def _looks_like_path(value: str | Path) -> bool:
    if isinstance(value, Path):
        return True
    text = str(value)
    return "<" not in text and text.strip().endswith(".xml")


__all__ = [
    "CrossEngineComparison",
    "cross_engine_trajectory_check",
    "simulate_reference_sbml",
]
