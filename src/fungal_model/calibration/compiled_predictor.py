"""Compiled-core predictions of configured models for calibration.

A :class:`ConfiguredConditionPredictor` turns a candidate parameter set into
observable predictions for one experimental condition by rebuilding the
condition's model config through a caller-supplied factory, loading its
inputs, assembling the processes, compiling the model
(:mod:`fungal_model.solvers.compiled`) and integrating it at the requested
observation times. Rebuilding the config rather than patching a parameter set
keeps every derived quantity honest: a registry case whose product-map
coefficients are bound to a fitted parameter is rebuilt from its records, so
the fitted value reaches every place the public path puts it.

The predictor introduces no observation operator beyond a unit conversion
from a model state to the observable it is declared to measure.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from fungal_model.core.kernels import conversion_factor
from fungal_model.core.numerics import solve_checked
from fungal_model.core.parameters import ParameterSet
from fungal_model.core.provenance import has_text
from fungal_model.core.units import Q_, assert_compatible
from fungal_model.io.model_config import ModelConfig
from fungal_model.solvers.compiled import compile_assembled_model, resolve_state_units
from fungal_model.validation.maturity import enforce_run_maturity
from fungal_model.workflows.configured_inputs import ConfiguredInputLoader
from fungal_model.workflows.configured_processes import ConfiguredProcessAssembler

ConfigFactory = Callable[[Mapping[str, float]], ModelConfig]
"""Materialize a model config for candidate values (symbol -> value in that parameter's units)."""


@dataclass(frozen=True)
class ObservableMapping:
    """One observable measured as one model state, reported in ``units``."""

    observable: str
    state: str
    units: str

    def __post_init__(self) -> None:
        if not has_text(self.observable) or not has_text(self.state):
            raise ValueError("An observable mapping needs an observable name and a state name.")
        Q_(1.0, self.units)


@dataclass(frozen=True)
class ConfiguredCondition:
    """A configured model for one condition and the observables it predicts."""

    condition_id: str
    config_factory: ConfigFactory
    observables: tuple[ObservableMapping, ...]

    def __post_init__(self) -> None:
        if not has_text(self.condition_id):
            raise ValueError("A configured condition needs an identifier.")
        names = [mapping.observable for mapping in self.observables]
        if not names or len(set(names)) != len(names):
            raise ValueError(f"Condition {self.condition_id!r} needs unique observables.")

    @property
    def observable_names(self) -> tuple[str, ...]:
        return tuple(mapping.observable for mapping in self.observables)


class ConfiguredConditionPredictor:
    """``predict(parameters, condition_id, times)`` on the compiled core for configured conditions."""

    def __init__(
        self,
        conditions: Sequence[ConfiguredCondition],
        *,
        fitted_symbols: Sequence[str],
        enforce_maturity: bool = True,
        input_loader: ConfiguredInputLoader | None = None,
        process_assembler: ConfiguredProcessAssembler | None = None,
    ) -> None:
        ids = [condition.condition_id for condition in conditions]
        if not ids or len(set(ids)) != len(ids):
            raise ValueError("Conditions must be nonempty with unique identifiers.")
        symbols = tuple(fitted_symbols)
        if not symbols or len(set(symbols)) != len(symbols):
            raise ValueError("fitted_symbols must be nonempty and unique.")
        self._conditions = {condition.condition_id: condition for condition in conditions}
        self._fitted_symbols = symbols
        self._enforce_maturity = enforce_maturity
        self._loader = input_loader if input_loader is not None else ConfiguredInputLoader()
        self._assembler = process_assembler if process_assembler is not None else ConfiguredProcessAssembler()
        self._factor_cache: dict[tuple[str, str], float] = {}

    @property
    def condition_ids(self) -> tuple[str, ...]:
        return tuple(self._conditions)

    @property
    def fitted_symbols(self) -> tuple[str, ...]:
        return self._fitted_symbols

    def fitted_values(self, parameters: ParameterSet) -> dict[str, float]:
        """Candidate values of the fitted symbols in each parameter's own units."""

        values: dict[str, float] = {}
        for symbol in self._fitted_symbols:
            quantity = parameters.require_quantity(symbol)
            values[symbol] = float(np.asarray(quantity.magnitude, dtype=float))
        return values

    def __call__(self, parameters: ParameterSet, condition_id: str, times: np.ndarray) -> np.ndarray:
        return self.predict_values(self.fitted_values(parameters), condition_id, times)

    def predict_values(self, values: Mapping[str, float], condition_id: str, times: np.ndarray) -> np.ndarray:
        """Observable predictions (``len(times) x observables``) for explicit fitted values."""

        if condition_id not in self._conditions:
            raise KeyError(f"Unknown condition {condition_id!r}; known: {sorted(self._conditions)}.")
        condition = self._conditions[condition_id]
        requested = np.asarray(times, dtype=float)
        if requested.ndim != 1 or not requested.size or not np.all(np.isfinite(requested)):
            raise ValueError("times must be a nonempty finite one-dimensional array.")
        config = condition.config_factory(values)
        inputs = self._loader.load(config)
        if self._enforce_maturity:
            enforce_run_maturity(
                mode=config.mode,
                maturity=config.maturity,
                parameters=inputs.parameters,
                entities=inputs.maturity_entities(),
                product_maps=inputs.product_maps,
                process_configs=config.processes,
            )
        model = self._assembler.assemble(config, inputs).model
        state_units = resolve_state_units(model)
        names = tuple(state_units)
        time_units = str(inputs.t_span[1].units)
        start = float(inputs.t_span[0].to(time_units).magnitude)
        stop = float(inputs.t_span[1].to(time_units).magnitude)
        unique_times, inverse = np.unique(requested, return_inverse=True)
        if unique_times[0] < start or unique_times[-1] > stop:
            raise ValueError(
                f"{condition_id}: requested times [{unique_times[0]}, {unique_times[-1]}] {time_units} lie outside "
                f"the configured span [{start}, {stop}]."
            )
        initial = np.array(
            [float(assert_compatible(inputs.initial_state[name], units, name=name).magnitude) for name, units in state_units.items()],
            dtype=float,
        )
        compiled = compile_assembled_model(model, time_units=time_units)
        options = model.solver_settings.scipy_options(state_units, time_units)
        solution = solve_checked(compiled.rhs, (start, stop), initial, t_eval=unique_times, **options)
        trajectory = np.asarray(solution.y, dtype=float)
        output = np.empty((requested.size, len(condition.observables)), dtype=float)
        for column, mapping in enumerate(condition.observables):
            if mapping.state not in state_units:
                raise KeyError(f"{condition_id}: state {mapping.state!r} for observable {mapping.observable!r} is not in the model.")
            key = (state_units[mapping.state], mapping.units)
            factor = self._factor_cache.get(key)
            if factor is None:
                factor = conversion_factor(key[0], key[1], name=mapping.observable)
                self._factor_cache[key] = factor
            output[:, column] = trajectory[names.index(mapping.state), inverse] * factor
        return output

    def to_dict(self) -> dict[str, Any]:
        return {
            "fitted_symbols": list(self._fitted_symbols),
            "enforce_maturity": self._enforce_maturity,
            "conditions": {
                condition_id: {
                    "observables": [
                        {"observable": mapping.observable, "state": mapping.state, "units": mapping.units}
                        for mapping in condition.observables
                    ]
                }
                for condition_id, condition in self._conditions.items()
            },
            "integration": "compiled stoichiometric right-hand side on scipy.solve_ivp with the config's solver settings",
        }


def inline_parameter_config_factory(config: ModelConfig | Mapping[str, Any]) -> ConfigFactory:
    """A factory that substitutes candidate values into a config's inline parameter entries.

    Only symbols present as inline ``parameters[*].parameters[*]`` entries can be
    substituted; a candidate symbol absent from the config raises instead of
    being ignored. Outputs are disabled so predictions write nothing.
    """

    if isinstance(config, ModelConfig):
        raw: Mapping[str, Any] = config.raw
        path = config.path
    else:
        raw = config
        path = None
    base = _deep_copy(raw)
    inline_symbols = {
        str(entry.get("symbol"))
        for parameter_set in base.get("parameters", [])
        for entry in (parameter_set.get("parameters") or [])
    }

    def factory(values: Mapping[str, float]) -> ModelConfig:
        missing = sorted(set(values).difference(inline_symbols))
        if missing:
            raise KeyError(f"Candidate values name symbols absent from the config's inline parameters: {missing}.")
        data = _deep_copy(base)
        for parameter_set in data.get("parameters", []):
            for entry in parameter_set.get("parameters") or []:
                symbol = str(entry.get("symbol"))
                if symbol in values:
                    entry["value"] = float(values[symbol])
        outputs = dict(data.get("outputs", {}))
        outputs["directory"] = None
        outputs["save"] = []
        outputs["plots"] = []
        data["outputs"] = outputs
        return ModelConfig.from_mapping(data, path=path)

    return factory


def _deep_copy(data: Mapping[str, Any]) -> dict[str, Any]:
    import json

    return json.loads(json.dumps(data))


__all__ = [
    "ConfigFactory",
    "ConfiguredCondition",
    "ConfiguredConditionPredictor",
    "ObservableMapping",
    "inline_parameter_config_factory",
]
