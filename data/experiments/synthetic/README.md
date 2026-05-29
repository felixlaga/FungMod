# Synthetic Experiment Datasets

Synthetic datasets are infrastructure fixtures generated from known benchmark
models, equations, or saved model outputs. They are useful for loader,
comparison, and future calibration tests because the intended signal is known.

Synthetic datasets are not literature data and must not be described as
empirical evidence. They may use toy model configs as generation inputs, but
the dataset must still record its source, generation record, units,
preprocessing steps, and uncertainty policy.

Each synthetic dataset folder should contain:

- an `experiment_dataset` YAML file;
- one or more observation CSV files;
- a `generation_record.json` file describing the synthetic signal and any
  assigned noise or uncertainty.

CSV files must include the columns declared in the YAML validation section.
Uncertainty columns must either be present with explicit units or be
intentionally allowed missing by the dataset validation metadata.

Synthetic datasets can be compared against model outputs with
`ObservableMapping` and `evaluate_model_against_dataset`. A low residual on a
synthetic fixture only proves that the data plumbing and configured benchmark
agree; it is not an empirical validation claim.
