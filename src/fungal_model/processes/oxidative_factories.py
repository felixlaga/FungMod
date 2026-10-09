"""Configured construction for finite-chain scission and peroxide kinetics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fungal_model.core.units import Q_
from fungal_model.processes.base import Process
from fungal_model.processes.chain_scission import ChainScissionProcess
from fungal_model.processes.factories import BuildDecision, ProcessBuildContext, _apply_rate_modifiers
from fungal_model.processes.peroxide import PeroxideInactivationProcess, PeroxideOxidativeCleavageProcess


def _options(config: Any, key: str) -> dict[str, Any]:
    raw = dict(config.raw or {})
    # ProcessConfig.to_dict retains original extension fields in raw.
    return dict(raw.get(key, dict(raw.get("raw") or {}).get(key, {})) or {})


@dataclass(frozen=True)
class OxidativeMechanismFactory:
    process_type: str

    def can_build(self, context: ProcessBuildContext, process_config: Any) -> BuildDecision:
        states, parameters = process_config.states, process_config.parameters
        if self.process_type.startswith("chain_"):
            fields = ("enzyme", "chains")
            required = ("kcat", "km", "accessible_fraction")
            options, needed = (
                _options(process_config, "chain_structure"),
                ("parent_length", "fragment_length", "solid_min_length", "source"),
            )
        else:
            fields = (
                ("substrate", "peroxide", "enzyme", "product", "cuts")
                if self.process_type == "peroxide_oxidative_cleavage"
                else ("substrate", "peroxide", "enzyme", "inactive")
            )
            required = (
                ("kcat", "peroxide_km", "substrate_km", "substrate_binding")
                if self.process_type == "peroxide_oxidative_cleavage"
                else ("inactivation_constant", "substrate_km")
            )
            options, needed = (
                _options(process_config, "oxidative_yield"),
                (("value", "units", "source") if self.process_type == "peroxide_oxidative_cleavage" else ()),
            )
        missing = [f"states.{k}" for k in fields if k not in states]
        missing += [f"parameters.{k}" for k in required if not parameters.get(k)]
        missing += [f"options.{k}" for k in needed if k not in options]
        for key in fields:
            value = states.get(key)
            names = value.values() if key == "chains" and isinstance(value, dict) else (value,)
            missing += [f"state_units.{name}" for name in names if name is not None and name not in context.state_units]
        return BuildDecision(
            not missing,
            self.process_type,
            type(self).__name__,
            reasons=("missing_fields",) if missing else (),
            missing_fields=tuple(missing),
        )

    def build(self, context: ProcessBuildContext, process_config: Any) -> Process:
        decision = self.can_build(context, process_config)
        if not decision.can_build:
            raise ValueError(f"Process factory cannot build config: {decision.to_dict()}")
        states, params = process_config.states, process_config.parameters
        if self.process_type.startswith("chain_"):
            structure = _options(process_config, "chain_structure")
            raw_chains = states["chains"]
            if any(type(i) is not int and not (isinstance(i, str) and i.isdecimal()) for i in raw_chains):
                raise ValueError("Chain-length keys must be integers or integer strings.")
            chains = {int(i): str(n) for i, n in raw_chains.items()}
            if len(chains) != len(raw_chains):
                raise ValueError("Chain-length keys must be unique after parsing.")
            process = ChainScissionProcess(
                name=process_config.id,
                chain_states=chains,
                parent_length=structure["parent_length"],
                fragment_length=structure["fragment_length"],
                solid_min_length=structure["solid_min_length"],
                mode="endo" if self.process_type == "chain_endo_scission" else "exo",
                enzyme_state=states["enzyme"],
                state_units=context.state_units[chains[1]],
                enzyme_units=context.state_units[states["enzyme"]],
                kcat_symbol=params["kcat"],
                km_symbol=params["km"],
                accessible_fraction_symbol=params["accessible_fraction"],
                source=structure["source"],
            )
        else:
            common = dict(
                name=process_config.id,
                substrate_state=states["substrate"],
                peroxide_state=states["peroxide"],
                enzyme_state=states["enzyme"],
                state_units=context.state_units[states["substrate"]],
                peroxide_units=context.state_units[states["peroxide"]],
                enzyme_units=context.state_units[states["enzyme"]],
                substrate_km_symbol=params["substrate_km"],
                source=context.source,
            )
            if self.process_type == "peroxide_oxidative_cleavage":
                yield_data = _options(process_config, "oxidative_yield")
                process = PeroxideOxidativeCleavageProcess(
                    **common,
                    product_state=states["product"],
                    cuts_state=states["cuts"],
                    kcat_symbol=params["kcat"],
                    peroxide_km_symbol=params["peroxide_km"],
                    substrate_binding_symbol=params["substrate_binding"],
                    product_yield=Q_(yield_data["value"], yield_data["units"]),
                    yield_source=yield_data["source"],
                )
            else:
                process = PeroxideInactivationProcess(
                    **common,
                    inactive_state=states["inactive"],
                    inactivation_constant_symbol=params["inactivation_constant"],
                )
        return _apply_rate_modifiers(context, process_config, process)


def oxidative_mechanism_factories() -> tuple[OxidativeMechanismFactory, ...]:
    return tuple(
        OxidativeMechanismFactory(kind)
        for kind in (
            "chain_endo_scission",
            "chain_exo_scission",
            "peroxide_oxidative_cleavage",
            "peroxide_inactivation",
        )
    )
