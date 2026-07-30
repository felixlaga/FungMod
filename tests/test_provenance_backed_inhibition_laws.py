from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from fungal_model import load_model_config, run_configured_model
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.core.units import Q_
from fungal_model.entities import Environment
from fungal_model.io import ProcessConfig
from fungal_model.modifiers import (
    CompetitiveInhibitionModifier,
    SubstrateInhibitionModifier,
)
from fungal_model.processes import (
    ProcessBuildContext,
    ProcessLibrary,
)


ROOT = Path(__file__).resolve().parents[1]
MODEL_CONFIGS = ROOT / "data" / "model_configs"
COMPETITIVE_CONFIG = MODEL_CONFIGS / "toy_homogeneous_competitive_inhibition.yml"
SUBSTRATE_CONFIG = MODEL_CONFIGS / "toy_homogeneous_substrate_inhibition.yml"
COMPETITIVE_SOURCE = "https://pubmed.ncbi.nlm.nih.gov/7985803/"
SUBSTRATE_SOURCE = "https://doi.org/10.1016/j.biortech.2010.01.084"
MATURITY = "literature_backed_software_tested"


def test_competitive_inhibition_matches_selected_rate_equation() -> None:
    modifier = CompetitiveInhibitionModifier(
        substrate_state="S",
        inhibitor_state="I",
        michaelis_constant_symbol="K_m",
        inhibition_constant_symbol="K_i",
        substrate_units="mole / liter",
        inhibitor_units="mole / liter",
        primary_source=COMPETITIVE_SOURCE,
        maturity=MATURITY,
    )
    parameters = _parameters(
        K_m=(0.5, "mole / liter"),
        K_i=(0.25, "mole / liter"),
    )
    environment = Environment(name="artificial benchmark")

    no_inhibitor = modifier.activity(
        parameters=parameters,
        environment=environment,
        state={"S": Q_(1.0, "mole / liter"), "I": Q_(0.0, "mole / liter")},
    )
    inhibited = modifier.activity(
        parameters=parameters,
        environment=environment,
        state={"S": Q_(1.0, "mole / liter"), "I": Q_(0.5, "mole / liter")},
    )

    assert no_inhibitor.magnitude == pytest.approx(1.0)
    assert inhibited.magnitude == pytest.approx((0.5 + 1.0) / (0.5 * 3.0 + 1.0))
    assert inhibited.magnitude < no_inhibitor.magnitude
    assert modifier.assumptions[0].source == COMPETITIVE_SOURCE


def test_haldane_substrate_inhibition_matches_selected_rate_equation() -> None:
    modifier = SubstrateInhibitionModifier(
        substrate_state="S",
        michaelis_constant_symbol="K_m",
        inhibition_constant_symbol="K_i",
        substrate_units="mole / liter",
        primary_source=SUBSTRATE_SOURCE,
        maturity=MATURITY,
    )
    parameters = _parameters(
        K_m=(0.4, "mole / liter"),
        K_i=(0.3, "mole / liter"),
    )
    environment = Environment(name="artificial benchmark")

    activity = modifier.activity(
        parameters=parameters,
        environment=environment,
        state={"S": Q_(2.0, "mole / liter")},
    )

    assert activity.magnitude == pytest.approx(
        (0.4 + 2.0) / (0.4 + 2.0 + 2.0**2 / 0.3)
    )
    assert 0.0 < activity.magnitude < 1.0
    assert modifier.assumptions[0].source == SUBSTRATE_SOURCE


@pytest.mark.parametrize(
    ("config_path", "process_id", "assumption_name", "primary_source"),
    (
        (
            COMPETITIVE_CONFIG,
            "generic_competitive_conversion",
            "single-inhibitor competitive Michaelis-Menten inhibition",
            COMPETITIVE_SOURCE,
        ),
        (
            SUBSTRATE_CONFIG,
            "generic_substrate_inhibited_conversion",
            "single-substrate Haldane inhibition",
            SUBSTRATE_SOURCE,
        ),
    ),
)
def test_configured_literature_laws_execute_and_emit_provenance(
    tmp_path: Path,
    config_path: Path,
    process_id: str,
    assumption_name: str,
    primary_source: str,
) -> None:
    output_dir = tmp_path / config_path.stem

    result = run_configured_model(config_path, output_dir=output_dir)

    metadata = json.loads(
        (output_dir / "configured_metadata.json").read_text(encoding="utf-8")
    )
    assumptions = json.loads(
        (output_dir / "assumptions.json").read_text(encoding="utf-8")
    )
    modifier = metadata["configured_process_modifiers"][0]
    assert result.solver_metadata["success"] is True
    assert process_id in result.process_rates
    assert np.all(np.asarray(result.process_rates[process_id].magnitude) >= 0.0)
    assert modifier["primary_source"] == primary_source
    assert modifier["maturity"] == MATURITY
    assert modifier["equation"].startswith("rate = Vmax*S")
    assert any(
        row["name"] == assumption_name and row["source"] == primary_source
        for row in assumptions
    )


def test_configured_competitive_inhibition_uses_expected_initial_rate(
    tmp_path: Path,
) -> None:
    result = run_configured_model(
        COMPETITIVE_CONFIG,
        output_dir=tmp_path / "competitive",
    )

    initial_rate = result.process_rates["generic_competitive_conversion"].magnitude[0]

    assert initial_rate == pytest.approx(0.2 * 1.0 / (0.5 * (1.0 + 0.5 / 0.25) + 1.0))


def test_configured_substrate_inhibition_uses_expected_initial_rate(
    tmp_path: Path,
) -> None:
    result = run_configured_model(
        SUBSTRATE_CONFIG,
        output_dir=tmp_path / "substrate",
    )

    initial_rate = result.process_rates[
        "generic_substrate_inhibited_conversion"
    ].magnitude[0]

    assert initial_rate == pytest.approx(0.15 * 2.0 / (0.4 + 2.0 + 2.0**2 / 0.3))


@pytest.mark.parametrize(
    "modifier",
    (
        {
            "type": "competitive_inhibition",
            "substrate_state": "S",
            "inhibitor_state": "I",
            "michaelis_constant": "K_m",
            "inhibition_constant": "K_i",
            "maturity": MATURITY,
        },
        {
            "type": "substrate_inhibition",
            "substrate_state": "S",
            "michaelis_constant": "K_m",
            "inhibition_constant": "K_i",
            "maturity": MATURITY,
        },
    ),
)
def test_new_biological_laws_require_explicit_primary_source(
    modifier: dict[str, str],
) -> None:
    process_config = _mm_process_config(modifier)

    with pytest.raises(ValueError, match="requires primary_source"):
        ProcessLibrary.default_foundation().build_processes(
            ProcessBuildContext(
                state_units={
                    "S": "mole / liter",
                    "P": "mole / liter",
                    "I": "mole / liter",
                }
            ),
            (process_config,),
        )


def test_new_biological_laws_reject_non_michaelis_menten_process() -> None:
    process_config = ProcessConfig.from_mapping(
        {
            "id": "unsupported_first_order_inhibition",
            "process_type": "first_order",
            "states": {"source": "S", "product": "P"},
            "parameters": {"rate_constant": "k"},
            "modifiers": [
                {
                    "type": "substrate_inhibition",
                    "substrate_state": "S",
                    "michaelis_constant": "K_m",
                    "inhibition_constant": "K_i",
                    "primary_source": SUBSTRATE_SOURCE,
                    "maturity": MATURITY,
                }
            ],
        }
    )

    with pytest.raises(ValueError, match="homogeneous_michaelis_menten"):
        ProcessLibrary.default_foundation().build_processes(
            ProcessBuildContext(
                state_units={"S": "mole / liter", "P": "mole / liter"}
            ),
            (process_config,),
        )


def test_new_biological_law_must_match_base_substrate_and_km() -> None:
    modifier = {
        "type": "competitive_inhibition",
        "substrate_state": "other_S",
        "inhibitor_state": "I",
        "michaelis_constant": "other_K_m",
        "inhibition_constant": "K_i",
        "primary_source": COMPETITIVE_SOURCE,
        "maturity": MATURITY,
    }

    with pytest.raises(ValueError, match="substrate_state must exactly match"):
        ProcessLibrary.default_foundation().build_processes(
            ProcessBuildContext(
                state_units={
                    "S": "mole / liter",
                    "other_S": "mole / liter",
                    "P": "mole / liter",
                    "I": "mole / liter",
                }
            ),
            (_mm_process_config(modifier),),
        )


def test_new_biological_laws_reject_nonpositive_parameters() -> None:
    modifier = SubstrateInhibitionModifier(
        substrate_state="S",
        michaelis_constant_symbol="K_m",
        inhibition_constant_symbol="K_i",
        substrate_units="mole / liter",
        primary_source=SUBSTRATE_SOURCE,
        maturity=MATURITY,
    )

    with pytest.raises(ValueError, match="K_i must be finite and positive"):
        modifier.activity(
            parameters=_parameters(
                K_m=(0.4, "mole / liter"),
                K_i=(0.0, "mole / liter"),
            ),
            environment=Environment(name="artificial benchmark"),
            state={"S": Q_(1.0, "mole / liter")},
        )


def test_new_biological_law_configs_remain_explicit_toy_benchmarks() -> None:
    for path in (COMPETITIVE_CONFIG, SUBSTRATE_CONFIG):
        config = load_model_config(path)
        assert config.mode == "toy"
        assert config.maturity == "framework_benchmark"
        assert "not a scientific case" in str(config.raw["provenance"]["source"])
        assert "not biological evidence" in str(
            config.raw["parameters"][0]["parameters"][2]["notes"]
        )


def _mm_process_config(modifier: dict[str, str]) -> ProcessConfig:
    return ProcessConfig.from_mapping(
        {
            "id": "generic_mm_inhibition",
            "process_type": "homogeneous_michaelis_menten",
            "states": {"substrate": "S", "product": "P"},
            "parameters": {
                "km": "K_m",
                "vmax": "V_max",
                "rate_units": "mole / liter / second",
            },
            "modifiers": [modifier],
        }
    )


def _parameters(**values: tuple[float, str]) -> ParameterSet:
    return ParameterSet(
        Parameter(
            name=symbol,
            symbol=symbol,
            value=value,
            units=units,
            uncertainty=0.0,
            source="FungMod artificial inhibition-law test.",
            confidence_level="testing",
            notes="Artificial value for software verification only.",
            measurement_method="defined benchmark value",
        )
        for symbol, (value, units) in values.items()
    )
