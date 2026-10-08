from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import fungal_model
import fungal_model.workflows as workflows
from fungal_model import (
    AssembledTablesDraft,
    DegradationScreenResult,
    EnvironmentCase,
    EnvironmentGrid,
    Parameter,
    ParameterSet,
    SourceProviderError,
    UserDataError,
    UserDataset,
    UserTablesAssemblyError,
    UserTablesDraft,
    UserTablesSourceError,
    VirtualExperiment,
    VirtualExperimentError,
    assemble_user_tables,
    environment_grid,
    load_geometry,
    load_model_config,
    load_parameter_set,
    load_product_map,
    load_substrate,
    load_user_dataset,
    run_configured_model,
    source_proposal,
    user_tables_from_sabiork,
    virtual_experiment,
)
from fungal_model.plugins import pet as pet_plugin
from fungal_model.processes import (
    AssembledModel,
    ModelBuilder,
    ProcessLibrary,
    ProcessRegistry,
)
from fungal_model.results import SimulationResult
from fungal_model.solvers import ProcessODESolver, RunRequest
from fungal_model.workflows import ConfiguredModelExecutionError


ROOT = Path(__file__).resolve().parents[1]

FOUNDATION_PUBLIC_API = {
    "run_configured_model": run_configured_model,
    "load_model_config": load_model_config,
    "load_substrate": load_substrate,
    "load_geometry": load_geometry,
    "load_product_map": load_product_map,
    "load_parameter_set": load_parameter_set,
    "ModelBuilder": ModelBuilder,
    "AssembledModel": AssembledModel,
    "ProcessLibrary": ProcessLibrary,
    "ProcessRegistry": ProcessRegistry,
    "ProcessODESolver": ProcessODESolver,
    "RunRequest": RunRequest,
    "SimulationResult": SimulationResult,
    "Parameter": Parameter,
    "ParameterSet": ParameterSet,
}

RESEARCHER_PUBLIC_API = {
    "VirtualExperiment": VirtualExperiment,
    "virtual_experiment": virtual_experiment,
    "EnvironmentGrid": EnvironmentGrid,
    "environment_grid": environment_grid,
    "EnvironmentCase": EnvironmentCase,
    "DegradationScreenResult": DegradationScreenResult,
    "VirtualExperimentError": VirtualExperimentError,
    "source_proposal": source_proposal,
    "SourceProviderError": SourceProviderError,
    "load_user_dataset": load_user_dataset,
    "UserDataset": UserDataset,
    "UserDataError": UserDataError,
    "user_tables_from_sabiork": user_tables_from_sabiork,
    "UserTablesDraft": UserTablesDraft,
    "UserTablesSourceError": UserTablesSourceError,
    "assemble_user_tables": assemble_user_tables,
    "AssembledTablesDraft": AssembledTablesDraft,
    "UserTablesAssemblyError": UserTablesAssemblyError,
}

PET_PLUGIN_ONLY_NAMES = (
    "PETSurfaceWorkflowConfig",
    "pet_substrate_loader_registry",
    "register_pet_substrate_loader",
    "run_pet_surface_integration",
)


def test_current_foundation_public_api_is_exported() -> None:
    class_names = {
        "ModelBuilder",
        "AssembledModel",
        "ProcessLibrary",
        "ProcessRegistry",
        "ProcessODESolver",
        "RunRequest",
        "SimulationResult",
        "Parameter",
        "ParameterSet",
    }
    for name, expected in FOUNDATION_PUBLIC_API.items():
        assert name in fungal_model.__all__
        assert getattr(fungal_model, name) is expected
        if name in class_names:
            assert inspect.isclass(expected)
        else:
            assert callable(expected)


def test_current_researcher_public_api_is_exported() -> None:
    class_names = {
        "VirtualExperiment",
        "EnvironmentGrid",
        "EnvironmentCase",
        "DegradationScreenResult",
        "VirtualExperimentError",
        "SourceProviderError",
        "UserDataset",
        "UserDataError",
        "UserTablesDraft",
        "UserTablesSourceError",
        "AssembledTablesDraft",
        "UserTablesAssemblyError",
    }
    for name, expected in RESEARCHER_PUBLIC_API.items():
        assert name in fungal_model.__all__
        assert getattr(fungal_model, name) is expected
        if name in class_names:
            assert inspect.isclass(expected)
        else:
            assert callable(expected)


def test_top_level_api_is_generic_first() -> None:
    for name in PET_PLUGIN_ONLY_NAMES:
        assert not hasattr(fungal_model, name)
        assert not hasattr(workflows, name)


def test_pet_plugin_helpers_are_available_only_from_pet_plugin() -> None:
    for name in PET_PLUGIN_ONLY_NAMES:
        assert hasattr(pet_plugin, name)
        assert name in pet_plugin.__all__


def test_uniprot_route_api_is_exported_and_not_a_placeholder() -> None:
    """USERDATA-007: the UniProt parser and resolver from ``fungal_model.capability``, the fetch client from
    ``fungal_model.sources.uniprot``; complete functions, not top-level names."""

    import fungal_model.capability as capability
    import fungal_model.sources.uniprot as uniprot_source

    for module, names in (
        (capability, ("decode_uniprot_tsv", "parse_uniprot_tsv", "resolve_uniprot_proteome")),
        (
            uniprot_source,
            (
                "build_stream_url",
                "fetch_proteome_snapshot",
                "load_proteome_snapshot",
                "organism_query",
                "proteome_query",
                "write_snapshot_to_user_dataset",
                # FETCH-001: from an organism name to a reference proteome, through its candidates.
                "build_proteome_search_url",
                "choose_proteome",
                "fetch_proteome_by_name",
                "load_proteome_search_snapshot",
                "normalize_organism_name",
                "parse_proteome_search_tsv",
                "proteome_name_query",
                "resolve_proteome_name",
                "search_key",
                "search_proteomes_by_name",
            ),
        ),
    ):
        for name in names:
            assert name in module.__all__, name
            assert not hasattr(fungal_model, name), name
            source = inspect.getsource(getattr(module, name)).lower()
            assert "notimplementederror" not in source, name
            assert "placeholder" not in source, name
            assert "todo" not in source, name


def test_kinetics_lookup_api_is_exported_and_not_a_placeholder() -> None:
    """FETCH-002: the SABIO-RK query snapshots of the kinetics lookup; complete functions, not top-level names."""

    import fungal_model.api.user_data_assembly as assembly
    import fungal_model.sources.sabiork.query_snapshots as query_snapshots

    for module, names in (
        (
            query_snapshots,
            (
                "complete_ec_number",
                "ec_number_query",
                "fetch_kinlaw_query_snapshot",
                "fetch_kinlaw_query_snapshots",
                "kinlaw_query_directory",
                "kinlaw_query_snapshot_exists",
                "load_kinlaw_query_snapshot",
            ),
        ),
        (assembly, ("assemble_user_tables",)),
    ):
        for name in names:
            assert name in module.__all__, name
            source = inspect.getsource(getattr(module, name)).lower()
            assert "notimplementederror" not in source, name
            assert "placeholder" not in source, name
            assert "todo" not in source, name
    for name in ("fetch_kinlaw_query_snapshot", "ec_number_query", "load_kinlaw_query_snapshot"):
        assert not hasattr(fungal_model, name), name
    for name in ("KineticsLookupError", "MissingKineticsSnapshotError", "KineticsSnapshotConflictError"):
        assert name in assembly.__all__, name
        assert issubclass(getattr(assembly, name), assembly.UserTablesAssemblyError), name


def test_culture_route_names_are_exported_and_not_placeholders() -> None:
    """USERDATA-009: culture.csv is read by load_user_dataset; its vocabulary is exported from the user-data module."""

    import fungal_model.api.user_data as user_data

    for name in (
        "CULTURE_TABLE",
        "CULTURE_QUANTITIES",
        "CULTURE_LEVEL_QUANTITIES",
        "CULTURE_CONSUMPTION_QUANTITIES",
        "CULTURE_POOL_QUANTITIES",
        "CULTURE_EVIDENCE_TYPES",
        "USER_DATASET_CULTURE_PROCESS_TYPE",
    ):
        assert name in user_data.__all__, name
    assert user_data.CULTURE_TABLE == "culture.csv"
    assert set(user_data.CULTURE_QUANTITIES) == {
        *user_data.CULTURE_LEVEL_QUANTITIES,
        *user_data.CULTURE_CONSUMPTION_QUANTITIES,
        *user_data.CULTURE_POOL_QUANTITIES,
    }
    for function in (
        user_data.load_user_dataset,
        user_data._parse_culture,
        user_data._validate_cultures,
        user_data._generate_culture_records,
    ):
        source = inspect.getsource(function).lower()
        assert "notimplementederror" not in source
        assert "placeholder" not in source
        assert "todo" not in source


def test_command_line_entry_point_is_complete_and_uses_the_public_api() -> None:
    import fungal_model.__main__ as module_entry
    import fungal_model.cli as cli

    assert callable(cli.main)
    for source in (inspect.getsource(cli), inspect.getsource(module_entry)):
        lowered = source.lower()
        assert "notimplementederror" not in lowered
        assert "placeholder" not in lowered
        assert "todo" not in lowered
    source = inspect.getsource(cli)
    assert "virtual_experiment(" in source
    assert ".simulate(" in source
    assert ".preflight(" in source
    for low_level in ("simulate_screen", "assess_modelability", "run_configured_model", "ProcessODESolver"):
        assert low_level not in source


def test_public_api_names_are_not_unfinished_placeholders() -> None:
    candidates = (
        *FOUNDATION_PUBLIC_API.values(),
        fungal_model.AssembledModel.run,
    )
    for candidate in candidates:
        source = inspect.getsource(candidate).lower()
        assert "notimplementederror" not in source
        assert "placeholder" not in source
        assert "todo" not in source


def test_public_api_is_documented_in_readme() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "## Public API" in readme
    for name in RESEARCHER_PUBLIC_API:
        assert f"`{name}`" in readme
    for name in FOUNDATION_PUBLIC_API:
        assert f"`{name}`" in readme
    assert "`run_pet_surface_integration`" in readme
    assert "fungal_model.plugins.pet" in readme


def test_load_model_config_validates_generic_top_level_contract(tmp_path) -> None:
    config_path = tmp_path / "toy_model.yml"
    config_path.write_text(
        """
kind: model_config
name: toy generic shell
mode: toy
maturity: framework_benchmark
entities: {}
parameters: []
processes: []
initial_state: {}
time:
  start:
    value: 0.0
    units: second
  stop:
    value: 1.0
    units: second
  points: 2
validators: []
outputs: {}
""".lstrip(),
        encoding="utf-8",
    )

    config = fungal_model.load_model_config(config_path)

    assert config.kind == "model_config"
    assert config.name == "toy generic shell"
    assert config.validate().passed
    assert config.to_dict()["maturity"] == "framework_benchmark"


def test_run_configured_model_fails_with_structured_report(tmp_path) -> None:
    config_path = tmp_path / "toy_model.yml"
    config_path.write_text(
        """
kind: model_config
name: toy generic shell
mode: toy
maturity: framework_benchmark
entities: {}
parameters: []
processes: []
initial_state: {}
time:
  start:
    value: 0.0
    units: second
  stop:
    value: 1.0
    units: second
  points: 2
validators: []
outputs: {}
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfiguredModelExecutionError) as exc_info:
        fungal_model.run_configured_model(config_path)

    report = exc_info.value.report
    assert report.config_name == "toy generic shell"
    assert report.stage == "configured_model_execution"
    assert "configured_processes" in report.missing_capabilities
    assert "configured_initial_state" in report.missing_capabilities
    assert report.to_dict()["config_path"] == str(config_path)
