# API reference

## Virtual experiments

::: fungal_model.api.virtual_experiment
    options:
      members:
        - VirtualExperiment
        - DegradationScreenResult
        - VirtualExperimentError
        - virtual_experiment

## Command line

The `fungmod` console script (also `python -m fungal_model`); see
[command line](cli.md) for the subcommands and exit codes.

::: fungal_model.cli
    options:
      members:
        - main
        - build_parser

## User-supplied data

::: fungal_model.api.user_data
    options:
      members:
        - load_user_dataset
        - UserDataset
        - UserTimecourse
        - TimecoursePoint
        - UserDataError

::: fungal_model.api.user_data_fit
    options:
      members:
        - compare_with_timecourses
        - TimecourseComparison
        - fit_user_dataset
        - UserDatasetFit
        - FittedQuantity
        - UserDataFitError
::: fungal_model.api.user_data_sources
    options:
      members:
        - user_tables_from_sabiork
        - UserTablesDraft
        - UserTablesSourceError
        - SABIORK_UNIT_SPELLINGS

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

## Uncertainty and sensitivity

::: fungal_model.uncertainty
    options:
      members:
        - ParameterUncertaintySpec
        - run_monte_carlo
        - LocalSensitivitySpec
        - local_sensitivity
        - GlobalSensitivityResult
        - global_sensitivity

## Calibration and evidence auditing

::: fungal_model.calibration
    options:
      members:
        - FittableParameter
        - LeastSquaresCalibrationResult
        - fit_least_squares
        - CalibrationEvidenceContext
        - CalibrationAuditCriteria
        - CalibrationEvidenceAudit
        - audit_calibration_evidence

## Bayesian calibration and identifiability

::: fungal_model.calibration.bayesian
    options:
      members:
        - PriorSpecification
        - NoiseScalePrior
        - ObservedCondition
        - SamplerSettings
        - IdentifiabilityCriteria
        - BayesianProblem
        - BayesianCalibrationResult
        - build_bayesian_problem
        - run_ensemble_sampler
        - analyze_run
        - sample_posterior
        - classify_identifiability
        - local_information_analysis
        - posterior_predictive
        - pooled_replicate_standard_deviation

::: fungal_model.calibration.compiled_predictor
    options:
      members:
        - ObservableMapping
        - ConfiguredCondition
        - ConfiguredConditionPredictor
        - inline_parameter_config_factory

::: fungal_model.screening.case_builder
    options:
      members:
        - ResolvedRegistryCase
        - resolve_registry_case
        - build_resolved_case_config
        - registry_case_config_factory

## Spatial reaction diffusion

::: fungal_model.transport
    options:
      members:
        - ReactionDiffusionEngine1D
        - UniformCartesianGrid
        - BoundaryConditionsND
        - ReactionDiffusionEngineND

## Spatial mycelium

::: fungal_model.mycelium
    options:
      members:
        - SpatialGrid
        - FieldSpec
        - FieldProcess
        - MyceliumModel
        - CompiledMyceliumModel
        - MyceliumResult
        - TipExtension
        - TipMotion
        - LateralBranching
        - DichotomousBranching
        - Anastomosis
        - FirstOrderLoss
        - LocalUptake
        - Translocation
        - LocalSecretion
        - FieldDiffusion

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
