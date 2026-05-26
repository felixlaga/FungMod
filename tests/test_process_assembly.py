from __future__ import annotations

from pathlib import Path

import pytest

from fungal_model.core.assumptions import Assumption
from fungal_model.core.errors import (
    IncompatibleUnitsError,
    MissingParameterError,
    MissingProcessError,
)
from fungal_model.core.parameters import Parameter, ParameterSet
from fungal_model.processes import (
    ModelBuilder,
    ParameterRequirement,
    Process,
    ProcessRegistry,
    StateVariableSpec,
)


def assembly_assumption() -> Assumption:
    return Assumption(
        name="toy assembly process",
        description="A deliberately small process used to test model assembly.",
        justification="Milestone 1 requires a process registry without hard-coded substrate logic.",
        known_limitations="This process declares requirements only and has no solver implementation.",
        source="FungMod assembly test fixture.",
    )


def toy_process() -> Process:
    return Process(
        name="toy first-order loss",
        process_type="first_order_decay",
        required_state_variables=(
            StateVariableSpec(
                name="substrate",
                units="mole / liter",
                description="Dissolved toy substrate.",
            ),
        ),
        changed_state_variables=(
            StateVariableSpec(
                name="product",
                units="mole / liter",
                description="Dissolved toy product.",
            ),
        ),
        required_parameters=(
            ParameterRequirement(
                symbol="k_decay",
                units="1 / second",
                name="toy first-order decay constant",
            ),
        ),
        assumptions=(assembly_assumption(),),
        failure_modes=("missing k_decay blocks assembly",),
        source="FungMod assembly test fixture.",
    )


def sourced_decay_parameter(*, source: str | None = "FungMod assembly test fixture.") -> Parameter:
    return Parameter(
        name="toy first-order decay constant",
        symbol="k_decay",
        value=0.1,
        units="1 / second",
        uncertainty=0.0,
        source=source,
        confidence_level="testing",
        notes="Used only to verify process assembly parameter checks.",
        measurement_method="defined test value",
    )


def test_missing_process_fails_with_structured_report() -> None:
    builder = ModelBuilder(
        process_library=ProcessRegistry.default(),
        requested_processes=("surface_hydrolysis",),
    )

    with pytest.raises(MissingProcessError) as exc_info:
        builder.assemble()

    report = exc_info.value.report
    assert report is not None
    assert not report.success
    assert report.missing_processes[0].process_type == "surface_hydrolysis"
    assert "surface_hydrolysis" in report.human_readable()
    assert report.to_dict()["missing_processes"][0]["process_type"] == "surface_hydrolysis"


def test_missing_parameter_fails_after_process_match() -> None:
    builder = ModelBuilder(
        process_library=ProcessRegistry([toy_process()]),
        requested_processes=("first_order_decay",),
        parameters=ParameterSet(),
    )

    with pytest.raises(MissingParameterError) as exc_info:
        builder.assemble()

    report = exc_info.value.report
    assert report.matched_processes[0].name == "toy first-order loss"
    assert report.missing_parameters[0].symbol == "k_decay"
    assert report.missing_parameters[0].reason == "absent"
    assert "k_decay" in report.human_readable()


def test_unknown_parameter_value_blocks_scientific_assembly() -> None:
    unknown = Parameter(
        name="toy first-order decay constant",
        symbol="k_decay",
        value=None,
        units="1 / second",
        uncertainty=None,
        source="Known missing value for assembly test.",
        confidence_level="unknown",
        notes="Explicitly unknown to verify no fallback constants are inserted.",
        measurement_method=None,
    )
    builder = ModelBuilder(
        process_library=ProcessRegistry([toy_process()]),
        requested_processes=("first_order_decay",),
        parameters=ParameterSet([unknown]),
    )

    with pytest.raises(MissingParameterError) as exc_info:
        builder.assemble()

    assert exc_info.value.report.missing_parameters[0].reason == "unknown_value"


def test_missing_parameter_provenance_blocks_scientific_assembly() -> None:
    builder = ModelBuilder(
        process_library=ProcessRegistry([toy_process()]),
        requested_processes=("first_order_decay",),
        parameters=ParameterSet([sourced_decay_parameter(source=None)]),
    )

    with pytest.raises(MissingParameterError) as exc_info:
        builder.assemble()

    assert exc_info.value.report.missing_parameters[0].reason == "missing_source"


def test_testing_escape_hatch_allows_unsourced_parameter_only_when_explicit() -> None:
    builder = ModelBuilder(
        process_library=ProcessRegistry([toy_process()]),
        requested_processes=("first_order_decay",),
        parameters=ParameterSet([sourced_decay_parameter(source=None)]),
        allow_unsourced_for_testing=True,
    )

    assembled = builder.assemble()

    assert assembled.assembly_report.success
    assert assembled.processes[0].name == "toy first-order loss"


def test_incompatible_parameter_units_fail_separately() -> None:
    incompatible = Parameter(
        name="toy first-order decay constant",
        symbol="k_decay",
        value=0.1,
        units="meter",
        uncertainty=None,
        source="FungMod assembly test fixture.",
        confidence_level="testing",
        notes="Wrong units by design.",
        measurement_method="defined test value",
    )
    builder = ModelBuilder(
        process_library=ProcessRegistry([toy_process()]),
        requested_processes=("first_order_decay",),
        parameters=ParameterSet([incompatible]),
    )

    with pytest.raises(IncompatibleUnitsError) as exc_info:
        builder.assemble()

    report = exc_info.value.report
    assert report.incompatible_units[0].symbol == "k_decay"
    assert report.incompatible_units[0].supplied_units == "meter"
    assert not report.missing_parameters


def test_successful_assembly_exports_state_assumptions_and_report() -> None:
    builder = ModelBuilder(
        process_library=ProcessRegistry([toy_process()]),
        requested_processes=("first_order_decay",),
        parameters=ParameterSet([sourced_decay_parameter()]),
    )

    assembled = builder.assemble()
    data = assembled.to_dict()

    assert assembled.assembly_report.success
    assert [process.name for process in assembled.processes] == ["toy first-order loss"]
    assert {variable.name for variable in assembled.state_variables} == {"substrate", "product"}
    assert assembled.assumptions[0].name == "toy assembly process"
    assert data["assembly_report"]["success"] is True
    assert data["solver_settings"]["method"] == "LSODA"


def test_process_modules_do_not_import_pet_specific_modules() -> None:
    process_dir = Path(__file__).resolve().parents[1] / "src" / "fungal_model" / "processes"
    source_text = "\n".join(path.read_text(encoding="utf-8") for path in process_dir.glob("*.py"))

    assert "substrates.pet" not in source_text
    assert "PETSubstrate" not in source_text
