# Independent validation from frozen predictions

For model-specific claims, the new [scoped validation contract](gelain-joint-benchmark.md#validation-tied-to-a-model-and-operating-scope)
also freezes exact parameters, observation mappings, acceptance thresholds and
operating/time scope. Its evaluator composes the raw-replicate workflow below.

The workflow separates prediction from evaluation. It does **not** establish
biological independence, validate an arbitrary fungus, or authorize publication.
No preparation-matched independent raw replicate dataset is bundled yet.

## Before seeing validation responses

1. Archive a prospective analysis plan identifying the training experiment,
   validation experiment, preparation, assay conditions, observables, noise
   model, and an acceptance threshold for each observable. Establish sample
   independence and preparation identity with external evidence.
2. Fit on the training experiment only. Prepare a model config for the validation
   conditions using the frozen fitted parameters and the same justified mechanism.
3. Simulate the declared validation conditions and freeze the resulting trajectory:

```python
from fungal_model import run_configured_model
from fungal_model.calibration import freeze_prediction
from fungal_model.data.loaders import load_experiment_dataset

prediction = run_configured_model("validation_conditions_with_frozen_parameters.yml")
training = load_experiment_dataset("training_dataset.yml")
prediction_sha256 = freeze_prediction(
    result=prediction,
    training_dataset=training,
    model_source="Immutable model commit or archived release identifier",
    path="validation/prediction.json",
)
```

The prediction file includes parameter values, trajectories, solver information,
and a fingerprint of the training observations. It cannot be overwritten by this
API. Archive its returned checksum with the analysis plan before evaluation.
A local checksum detects changes; it cannot prove when an experiment or plan
was performed. Do not tune parameters or acceptance thresholds after inspection.

## Required independent data

Provide a provenance-complete `ExperimentDataset` of observed replicate means
and a separate raw replicate CSV with these columns:

| Column | Meaning |
| --- | --- |
| `measurement_id` | The measurement identifier in the dataset |
| `time`, `time_units` | Observation time and explicit units |
| `value`, `units` | Individual replicate value and explicit units |
| `replicate_id` | Nonblank identifier, unique within each observation group |
| `experiment_id` | The plan's independent validation experiment identifier |
| `preparation_id` | The plan's preparation identifier |

Every dataset point needs at least two distinct raw replicates. Their mean must
match the dataset value after unit conversion. More complex preprocessing needs
a separately reviewed extension; it is not silently inferred. Supply positive
experimental standard deviations or standard errors and a source explaining
which uncertainty is appropriate. Digitization resolution is not accepted as
experimental uncertainty. Raw replicate means are verified, but the scientific
justification of the supplied uncertainty still requires external review.

## Score without refitting

Construct `IndependentValidationPlan` with the archived plan source, prediction
and raw-file SHA-256 digests, distinct experiment IDs, preparation ID, preparation
match evidence, independence evidence, uncertainty source, and raw-data source.
Pass this plan, the raw CSV, observable mappings, and one provenance-bearing,
unit-compatible `Parameter` threshold per measurement to
`evaluate_frozen_prediction(...)`:

```python
from fungal_model.calibration import evaluate_frozen_prediction

report = evaluate_frozen_prediction(
    prediction_path="validation/prediction.json",
    dataset=validation_dataset,
    plan=plan,
    raw_replicates_path="validation/raw_replicates.csv",
    observable_mapping=mappings,
    maximum_rmse=thresholds_from_archived_plan,
    output_dir="validation/report",
)
```

The scorer never invokes an optimizer or changes parameters. It refuses changed
artifacts, reused training observations, incomplete mappings/criteria, missing
replicates, preparation mismatches, and missing experimental uncertainty. It
records per-observable RMSE and threshold results, the complete frozen prediction,
dataset snapshot, and evidence declarations. `publication_claim_authorized` is
always false. A criteria pass is conditional on the externally declared evidence.

Synthetic fixtures require `allow_synthetic_for_testing=True`, are labelled
`synthetic_software_test`, and always have `empirical_criteria_met=False`.
They verify the workflow, not biology.

## API

::: fungal_model.calibration.independent
    options:
      members:
        - freeze_prediction
        - IndependentValidationPlan
        - evaluate_frozen_prediction
