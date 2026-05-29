# Data Directory

This directory is reserved for curated parameters, references, and experiment
metadata. Do not add unsourced numerical data. Every scientific value should
be traceable through `Parameter` objects or documented source files.

The `fungal_model.data` package currently exposes experiment dataset loading
and explicit model-dataset comparison primitives. Use
`load_experiment_dataset`, `ObservableMapping`, and
`evaluate_model_against_dataset` for synthetic infrastructure comparisons.
Use `GaussianNoise` and `generate_synthetic_dataset_from_result` to generate
reloadable synthetic datasets from existing `SimulationResult` objects.
Do not add real literature observations until the literature extraction schema
exists and is tested.
