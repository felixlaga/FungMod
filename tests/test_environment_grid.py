from __future__ import annotations

from fungal_model.api import EnvironmentGrid


def test_environment_grid_creates_cartesian_environment_cases() -> None:
    grid = EnvironmentGrid(
        temperature_C=[20, 25],
        ph=[5.0, 6.0],
        oxygen=["aerobic"],
    )

    cases = grid.environment_cases()

    assert len(cases) == 4
    assert [case.environment_id for case in cases] == [
        "temp_20C_ph_5p0_aerobic",
        "temp_20C_ph_6p0_aerobic",
        "temp_25C_ph_5p0_aerobic",
        "temp_25C_ph_6p0_aerobic",
    ]


def test_environment_grid_generated_ids_are_stable_and_safe() -> None:
    grid = EnvironmentGrid(
        temperature_C=[20, 20.5],
        ph=[4.5],
        oxygen=["aerobic culture"],
    )

    assert grid.registry_ids() == (
        "temp_20C_ph_4p5_aerobic_culture",
        "temp_20p5C_ph_4p5_aerobic_culture",
    )


def test_environment_grid_metadata_and_record_provenance_are_explicit() -> None:
    case = EnvironmentGrid(
        temperature_C=[30],
        ph=[5.0],
        oxygen=["aerobic"],
    ).environment_cases()[0]

    record = case.to_record()
    validation = record.validate()

    assert validation.passed
    assert case.temperature == 30.0
    assert case.temperature_units == "degree_Celsius"
    assert case.ph == 5.0
    assert case.oxygen == "aerobic"
    assert case.environment_source == "runtime_environment_grid"
    assert case.environment_effect_status == "metadata_only"
    assert record.provenance["runtime_environment_grid"] is True
    assert record.provenance["environment_effect_status"] == "metadata_only"
    assert record.conditions["temperature"].value == 30.0
    assert record.conditions["ph"].value == 5.0
    assert record.conditions["oxygen"].kind == "not_applicable"
