# API reference

## Virtual experiments

::: fungal_model.api.virtual_experiment
    options:
      members:
        - VirtualExperiment
        - DegradationScreenResult
        - VirtualExperimentError
        - virtual_experiment

## Environment grids

::: fungal_model.api.environment_grid
    options:
      members:
        - EnvironmentCase
        - EnvironmentGrid
        - environment_grid

## Packaged assets

::: fungal_model.resources
    options:
      members:
        - default_registry_path
        - example_data_path
        - package_data_path

## Configured models

::: fungal_model.workflows.configured_model
    options:
      members:
        - ConfiguredModelRunner
        - run_configured_model

## Source proposals

::: fungal_model.api.source_provider
    options:
      members:
        - source_proposal
        - SourceProviderError

## Curation

::: fungal_model.api.curation
    options:
      members:
        - CurationDecision
        - CurationResult
        - review_source_proposal
        - load_curation_bundle

## Registry promotion

::: fungal_model.api.registry_promotion
    options:
      members:
        - plan_registry_promotion
        - apply_registry_promotion
