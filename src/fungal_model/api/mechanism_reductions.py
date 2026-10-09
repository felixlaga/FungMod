"""Finite-run reductions of explicitly bound adsorption, chain and peroxide pools.

These are reporting identities, not additional kinetic laws. Counterfactual
synergy cannot be inferred from one run; peroxide exchange ledgers are named
explicitly rather than guessed from arbitrary product species.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from fungal_model.core.units import Q_, Quantity, assert_compatible
from fungal_model.io.model_config import ModelConfig
from fungal_model.processes.chain_scission import chain_observables
from fungal_model.results import SimulationResult
from fungal_model.screening.synergy import degree_of_synergy


def trajectory_metrics(config: ModelConfig, result: SimulationResult) -> list[dict[str, Any]]:
    """Return the existing five-column metric schema, scoped to process/population.

    ``metric_definitions.peroxide_ledgers`` maps a peroxide state to ``feed``
    and ``decay`` state names. A missing entry is unknown; explicit null means
    no modeled contribution. Cumulative ledger changes use final minus initial.

    Optional ``metric_definitions.synergy_comparisons[chain_population_N]``
    supplies scalar, baseline-subtracted full and individual increments as
    value/units mappings, a source and ``matched_conditions: true``. Member
    doses and all other conditions must match. No asymptotic extrapolation is
    performed for turnover, activity or conversion.
    """
    metrics: list[dict[str, Any]] = []
    definitions = config.raw.get("metric_definitions", {})
    if not isinstance(definitions, Mapping):
        raise ValueError("metric_definitions must be a mapping.")
    time_count = len(np.asarray(result.time.magnitude))

    def series(quantity: Quantity, name: str) -> Quantity:
        values = np.asarray(quantity.magnitude, dtype=float)
        if values.ndim != 1 or not len(values) or len(values) != time_count or not np.isfinite(values).all():
            raise ValueError(f"Metric trajectory {name!r} must be finite and match the time grid.")
        return quantity

    def endpoint(quantity: Quantity, position: int) -> Quantity:
        return Q_(float(np.asarray(quantity.magnitude, dtype=float)[position]), quantity.units)

    def state(name: str) -> Quantity:
        if name not in result.states:
            raise ValueError(f"Metric state {name!r} was not simulated.")
        return series(result.states[name], name)

    def add(scope: str, name: str, quantity: Quantity | None, *, units: str = "dimensionless", notes: str = "") -> None:
        value: float | str = ""
        if quantity is not None:
            value = float(quantity.magnitude)
            units = str(quantity.units)
            if not np.isfinite(value):
                raise ValueError(f"Metric {scope}.{name} must be finite.")
        metrics.append(dict(metric_name=f"{scope}.{name}", value=value, units=units,
                            status="unknown" if quantity is None else "computed", notes=notes))

    chain_groups: dict[tuple[Any, ...], str] = {}
    for process in config.processes:
        if process.process_type == "adsorbed_enzyme_hydrolysis":
            prefix = process.id + "."
            total_enzyme = state(str(process.states["enzyme"]))
            for metric, position in (("initial_bound_fraction", 0), ("final_bound_fraction", -1)):
                key = prefix + "bound_fraction"
                if float(np.asarray(total_enzyme.magnitude, dtype=float)[position]) == 0:
                    add(process.id, metric, None, notes="Undefined: total enzyme is zero at this saved endpoint.")
                elif key not in result.derived_quantities:
                    add(process.id, metric, None, notes=f"No derived quantity {key!r} was written.")
                else:
                    fractions = result.derived_quantities[key].to("dimensionless")
                    values = np.asarray(fractions.magnitude, dtype=float)
                    defined = np.asarray(total_enzyme.magnitude) != 0
                    if (values.ndim != 1 or len(values) != time_count
                            or not np.isfinite(values[defined]).all()):
                        raise ValueError(f"Defined adsorption fraction {key!r} must be finite and match the time grid.")
                    add(process.id, metric, endpoint(fractions, position), notes="Quasi-steady partition at the saved endpoint.")
            key = prefix + "enzyme_conservation_residual"
            if key not in result.derived_quantities:
                add(process.id, "max_absolute_enzyme_conservation_residual", None,
                    units=str(state(str(process.states["enzyme"])).units), notes=f"No derived quantity {key!r} was written.")
            else:
                residual = series(result.derived_quantities[key], key)
                add(process.id, "max_absolute_enzyme_conservation_residual",
                    Q_(float(np.max(np.abs(residual.magnitude))), residual.units),
                    notes="Maximum absolute free+bound-total residual over all saved times; numerical conservation only.")

        elif process.process_type in {"chain_endo_scission", "chain_exo_scission"}:
            chains = {int(length): str(name) for length, name in process.states["chains"].items()}
            options = dict(process.raw or {})
            structure = options.get("chain_structure", dict(options.get("raw") or {}).get("chain_structure"))
            if not isinstance(structure, Mapping) or type(structure.get("solid_min_length")) is not int:
                raise ValueError("Chain metrics require the explicit integer solid_min_length.")
            threshold = structure["solid_min_length"]
            key = (tuple(sorted(chains.items())), threshold)
            if key in chain_groups:
                continue
            scope = f"chain_population_{len(chain_groups) + 1}"
            chain_groups[key] = scope
            observed = chain_observables({name: state(name) for name in chains.values()}, chains, solid_min_length=threshold)
            for name in ("chain_ends", "solid_equivalents", "soluble_equivalents", "material_equivalents"):
                add(scope, "final_" + name, endpoint(observed[name], -1),
                    notes="Final saved finite-chain population; chain ends mean one exo-eligible end per solid chain.")
            comparisons = definitions.get("synergy_comparisons", {})
            if not isinstance(comparisons, Mapping):
                raise ValueError("synergy_comparisons must be a mapping keyed by chain population scope.")
            comparison = comparisons.get(scope)
            if comparison is None:
                add(scope, "degree_of_synergy", None,
                    notes="A single run cannot determine synergy; matching full-mixture and singleton increments were not supplied.")
            else:
                if (not isinstance(comparison, Mapping) or comparison.get("matched_conditions") is not True
                        or not str(comparison.get("source", "")).strip()):
                    raise ValueError("A synergy comparison needs source and matched_conditions: true.")
                def increment(value: Any) -> Quantity:
                    if not isinstance(value, Mapping) or set(value) != {"value", "units"}:
                        raise ValueError("Synergy increments require scalar value and units.")
                    number = value["value"]
                    if isinstance(number, bool) or not isinstance(number, (int, float)):
                        raise ValueError("Synergy increments require scalar numeric values.")
                    return Q_(number, value["units"])
                singles = comparison.get("individual_increments")
                if not isinstance(singles, list):
                    raise ValueError("Synergy comparison requires individual_increments as a list of singleton increments.")
                compared = degree_of_synergy(full_increment=increment(comparison.get("full_increment")),
                    individual_increments=[increment(value) for value in singles])
                add(scope, "degree_of_synergy",
                    Q_(float(compared.degree_of_synergy), "dimensionless") if bool(compared.defined) else None,
                    notes=f"Full increment divided by summed singleton increments at matching member doses; source: {comparison['source']}. Zero denominator is undefined.")

        elif process.process_type == "peroxide_oxidative_cleavage":
            scope = process.id
            enzyme = state(str(process.states["enzyme"]))
            cuts = state(str(process.states["cuts"]))
            peroxide_name = str(process.states["peroxide"])
            peroxide = state(peroxide_name)
            product = state(str(process.states["product"]))
            cut_increment = (endpoint(cuts, -1) - endpoint(cuts, 0)).to(peroxide.units)
            initial_enzyme = endpoint(enzyme, 0)
            if float(initial_enzyme.magnitude) < 0 or float(cut_increment.magnitude) < 0:
                raise ValueError("Peroxide reporting needs nonnegative initial enzyme and cumulative cut increment.")
            has_enzyme = float(initial_enzyme.magnitude) > 0
            for name, value in (("final_oxidative_cuts", endpoint(cuts, -1)), ("final_oxidized_product", endpoint(product, -1)),
                                ("final_active_enzyme", endpoint(enzyme, -1)), ("final_peroxide", endpoint(peroxide, -1)),
                                ("productive_peroxide_consumed", cut_increment)):
                add(scope, name, value, notes="Saved endpoint or cumulative productive peroxide change over this finite run; no extrapolation.")
            add(scope, "finite_run_turnover", (cut_increment / initial_enzyme).to("dimensionless") if has_enzyme else None,
                notes="Productive cut increment / initial active enzyme with unit conversion; undefined for zero initial enzyme. This is not asymptotic turnover.")
            add(scope, "remaining_active_fraction", (endpoint(enzyme, -1) / initial_enzyme).to("dimensionless") if has_enzyme else None,
                notes="Final / initial active enzyme; undefined for zero initial active enzyme.")
            declared_ledgers = definitions.get("peroxide_ledgers", {})
            if not isinstance(declared_ledgers, Mapping):
                raise ValueError("peroxide_ledgers must be a mapping keyed by peroxide state.")
            bindings = declared_ledgers.get(peroxide_name, {})
            if not isinstance(bindings, Mapping):
                raise ValueError("Peroxide ledger bindings must map feed and decay to states or explicit null.")
            amounts: dict[str, Quantity | None] = {}
            for kind in ("feed", "decay"):
                if kind not in bindings:
                    amount, note = None, "Unknown: no explicit cumulative ledger binding or null boundary declaration was supplied."
                elif bindings[kind] is None:
                    amount, note = Q_(0., peroxide.units), "Explicit null declares no modeled contribution; this is a model boundary, not an inferred rate."
                elif isinstance(bindings[kind], str) and bindings[kind].strip():
                    ledger = assert_compatible(state(bindings[kind]), str(peroxide.units), name=f"peroxide {kind} ledger")
                    amount, note = endpoint(ledger, -1) - endpoint(ledger, 0), f"Final minus initial cumulative ledger {bindings[kind]!r}, converted to peroxide units."
                    if float(amount.magnitude) < 0:
                        raise ValueError(f"Peroxide {kind} cumulative ledger must not decrease.")
                else:
                    raise ValueError("Peroxide ledger binding must be a nonempty state name or explicit null.")
                amounts[kind] = amount
                add(scope, "peroxide_" + ("fed" if kind == "feed" else "decayed"), amount,
                    units=str(peroxide.units), notes=note)
            decay = amounts["decay"]
            add(scope, "total_modeled_peroxide_consumed", None if decay is None else cut_increment + decay,
                units=str(peroxide.units), notes="Productive cuts plus explicitly tracked nonproductive decay; no invented damage stoichiometry.")
    return metrics
