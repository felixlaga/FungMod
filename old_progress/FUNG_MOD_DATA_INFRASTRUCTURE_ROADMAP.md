# FungMod Scientific Data Infrastructure Roadmap

## Purpose

The software foundation is now good enough to stop focusing on architecture-only work and start building the **data infrastructure layer**.

This does **not** mean real fungal biology should be implemented yet.

The next objective is:

> Build a rigorous data, provenance, dataset, residual, and calibration infrastructure so that later biological mechanisms and literature parameters can enter FungMod without becoming unsourced, unverifiable, or fake-scientific.

FungMod already has a `data/` folder with subfolders for model configs, substrates, enzymes, geometries, environments, parameters, product maps, and examples. That is a good start. But for scientific modelling it is still too basic unless it can represent raw experimental datasets, processed datasets, literature extraction metadata, measured quantities with units, uncertainty, censoring, experimental conditions, exact mappings between model states and measured observables, synthetic datasets for tests, calibration reports, validation splits, and data maturity rules.

This roadmap defines how to build that layer without implementing real biology yet.

## Non-goals

Do **not** implement real PETase kinetic mechanisms, real cellulose/lignin/chitin/starch degradation models, real fungal growth physiology, intracellular metabolism, new biological ODE systems, real literature parameter extraction, paper-by-paper data curation, JAX, Bayesian calibration, global sensitivity analysis, or 2D/3D spatial biology.

This stage is only about data infrastructure, synthetic calibration, provenance enforcement, and model-data comparison plumbing.

## High-level target

After this stage, FungMod should support this workflow:

```python
from fungal_model import run_configured_model
from fungal_model.data import load_experiment_dataset
from fungal_model.data.comparison import evaluate_model_against_dataset, ObservableMapping

result = run_configured_model("data/model_configs/toy_homogeneous_ab.yml")

dataset = load_experiment_dataset(
    "data/experiments/synthetic/first_order_ab/synthetic_first_order_ab.yml"
)

comparison = evaluate_model_against_dataset(
    result=result,
    dataset=dataset,
    observable_mapping=[
        ObservableMapping(
            dataset_measurement_id="product_mass",
            model_observable="released_product_amount",
            observable_type="state",
        )
    ],
)

comparison.save("outputs/synthetic_first_order_comparison")
```

And later:

```python
calibration = calibrate_configured_model(
    model_config="data/model_configs/synthetic_first_order_calibration.yml",
    dataset="data/experiments/synthetic/first_order_ab/synthetic_first_order_ab.yml",
    parameter_symbols=["k_ab"],
    observable_mapping=[...],
)

calibration.save("outputs/synthetic_first_order_calibration")
```

No literature biology is required yet. Synthetic datasets are enough to prove the infrastructure.

---

# Part 1: Data folder structure

## Required final structure

Refactor or extend the existing `data/` folder toward:

```text
data/
    README.md

    model_configs/
        toy_homogeneous_ab.yml
        toy_surface_dummy_non_pet.yml
        toy_surface_pet_plugin.yml
        synthetic_first_order_calibration.yml

    fungi/
        toy/
        literature/
        calibrated/
        validated/

    enzymes/
        toy/
        literature/
        calibrated/
        validated/

    substrates/
        toy/
        literature/
        calibrated/
        validated/

    environments/
        toy/
        literature/
        calibrated/
        validated/

    geometries/
        toy/
        literature/
        calibrated/
        validated/

    product_maps/
        toy/
        literature/

    parameters/
        toy/
        literature/
        calibrated/

    experiments/
        README.md
        synthetic/
            first_order_ab/
                synthetic_first_order_ab.yml
                synthetic_first_order_ab_observations.csv
                generation_record.json
            surface_catalysis/
                synthetic_surface_catalysis.yml
                synthetic_surface_catalysis_observations.csv
                generation_record.json
        literature/
            README.md
        validation/
            README.md

    calibration/
        README.md
        synthetic/
            first_order_ab/
                calibration_config.yml
```

## Rules

1. `toy/` means artificial benchmark data for software tests.
2. `synthetic/` means generated from a known model with known parameters.
3. `literature/` means extracted from papers, but no files should be added there until the literature extraction schema is implemented and tested.
4. `calibrated/` means produced by fitting.
5. `validated/` means checked against independent validation data.

Do not mix these categories casually.

---

# Part 2: Dataset maturity system

## Required maturity labels

Every dataset must have:

```yaml
maturity: toy | synthetic | literature_raw | literature_processed | calibrated | validated
```

Definitions:

- `toy`: artificial demo values, not generated from a documented simulation.
- `synthetic`: generated from a known FungMod model/config with known parameters.
- `literature_raw`: manually digitized or transcribed values from a source, minimally processed.
- `literature_processed`: cleaned/converted/normalized literature data with processing notes.
- `calibrated`: model outputs or parameter sets fit to a dataset.
- `validated`: model outputs checked against independent data not used for fitting.

## Scientific use rules

Scientific mode may eventually allow `literature_raw`, `literature_processed`, `calibrated`, and `validated`.

Scientific mode must reject `toy`, synthetic datasets presented as empirical evidence, datasets without source/provenance, datasets without units, datasets with unknown measured quantity definitions, and datasets with untracked preprocessing.

Synthetic datasets are allowed for infrastructure tests, calibration tests, and examples, but not as biological evidence.

---

# Part 3: ExperimentDataset object

## Required class

Create:

```text
src/fungal_model/data/datasets.py
```

or equivalent.

Define:

```python
@dataclass(frozen=True)
class ExperimentDataset:
    name: str
    dataset_id: str
    maturity: str
    source: DataSource
    system: ExperimentalSystem
    conditions: ExperimentalConditions
    measurements: tuple[MeasurementSeries, ...]
    preprocessing: PreprocessingRecord
    notes: str
    path: Path | None = None

    def validate(self) -> ValidationResult: ...
    def to_dict(self) -> dict[str, Any]: ...
```

Supporting objects:

```python
DataSource
ExperimentalSystem
ExperimentalConditions
MeasurementSeries
MeasurementPoint
PreprocessingRecord
```

Keep this minimal but explicit. Do not overbuild.

## Required dataset fields

A dataset YAML must contain:

```yaml
kind: experiment_dataset
dataset_id: synthetic_first_order_ab_v1
name: Synthetic first-order A to B benchmark
maturity: synthetic

source:
  type: generated
  citation: null
  doi: null
  url: null
  generated_by: FungMod synthetic dataset generator
  generation_config: data/model_configs/toy_homogeneous_ab.yml
  generation_commit: null
  notes: Synthetic dataset for infrastructure tests only.

system:
  organism: null
  enzyme: null
  substrate: generic dissolved substrate
  product: released product
  environment: toy well-mixed environment
  geometry: well_mixed

conditions:
  temperature:
    value: 298.15
    units: kelvin
  ph:
    value: 7.0
    units: dimensionless
  volume:
    value: 1.0
    units: liter
  notes: Controlled synthetic conditions.

measurements:
  - id: product_mass
    measured_quantity: released_product_amount
    observable_type: state
    data_file: synthetic_first_order_ab_observations.csv
    time_column: time_s
    value_column: product_mass_kg
    uncertainty_column: product_mass_sigma_kg
    units:
      time: second
      value: kilogram
      uncertainty: kilogram
    uncertainty_type: standard_deviation
    censoring: none
    replicate_id_column: null
    notes: Synthetic product mass generated from known first-order model.

preprocessing:
  status: generated
  raw_data_available: true
  steps:
    - generated from known model parameters
    - optional Gaussian noise added with fixed seed
  excluded_points: []
  notes: No literature preprocessing.

validation:
  expected_columns:
    - time_s
    - product_mass_kg
    - product_mass_sigma_kg
  allow_missing_uncertainty: false
```

## CSV format

Example:

```csv
time_s,product_mass_kg,product_mass_sigma_kg
0.0,0.0,0.001
1.0,0.095,0.001
2.0,0.181,0.001
```

## Tests

Add tests that load a valid synthetic dataset; reject missing `kind`; reject invalid `maturity`; reject missing source; reject missing units; reject missing CSV file; reject missing CSV columns; preserve uncertainty; preserve preprocessing notes; and ensure `to_dict()` is JSON-safe.

---

# Part 4: Dataset loader

## Required module

Create:

```text
src/fungal_model/data/loaders.py
```

API:

```python
def load_experiment_dataset(path: str | Path) -> ExperimentDataset:
    ...
```

Expose from:

```python
fungal_model.data
```

and eventually top-level `fungal_model` if stable.

## Loader requirements

The loader must:

1. read YAML;
2. validate `kind == experiment_dataset`;
3. resolve relative CSV paths relative to YAML path;
4. load measurement CSVs;
5. attach units;
6. preserve uncertainty;
7. reject missing required columns;
8. return `ExperimentDataset`.

Do not silently fill missing uncertainty unless `allow_missing_uncertainty: true`.

Do not silently infer units from column names unless units are explicit in YAML.

## Tests

Test relative path resolution, wrong CSV column failure, missing uncertainty failure by default, missing uncertainty allowed only when configured, and numeric arrays retaining units or unit metadata.

---

# Part 5: Observable mapping layer

## Reason

Model state names and experimental measurement names will differ.

Example:

```text
model state: released_product_amount
dataset measurement: product_mass
```

The comparison system must explicitly map them.

## Required object

Create:

```python
@dataclass(frozen=True)
class ObservableMapping:
    dataset_measurement_id: str
    model_observable: str
    observable_type: Literal["state", "process_rate", "derived"]
    transform: Literal["identity", "unit_conversion", "fractional_conversion"] = "identity"
    model_units: str | None = None
```

## Required behavior

`evaluate_model_against_dataset(...)` must require an explicit mapping. No automatic fuzzy matching.

Allowed transforms initially:

- `identity`;
- `unit_conversion`;
- `fractional_conversion`.

Do not add biological transforms yet.

## Tests

Test identity mapping, unit conversion, missing model observable failure, missing dataset measurement failure, incompatible unit failure, and fractional conversion requiring an initial value.

---

# Part 6: Model-data comparison object

## Required module

Create:

```text
src/fungal_model/data/comparison.py
```

or:

```text
src/fungal_model/calibration/comparison.py
```

Define:

```python
@dataclass(frozen=True)
class ModelDatasetComparison:
    dataset_id: str
    model_name: str
    mappings: tuple[ObservableMapping, ...]
    residuals: tuple[ResidualSeries, ...]
    metrics: dict[str, float]
    validation_results: tuple[ValidationResult, ...]

    def to_dict(self) -> dict[str, Any]: ...
    def save(self, output_dir: str | Path) -> None: ...
    def plot_observed_vs_predicted(...) -> Path: ...
    def plot_residuals(...) -> Path: ...
```

## Required function

```python
def evaluate_model_against_dataset(
    *,
    result: SimulationResult,
    dataset: ExperimentDataset,
    observable_mapping: Sequence[ObservableMapping] | Mapping[str, str],
) -> ModelDatasetComparison:
    ...
```

## Residual definition

For each data point:

```text
residual = model_prediction - observed_value
standardized_residual = residual / uncertainty
```

If uncertainty is unavailable and allowed, compute raw residuals but not standardized residuals, and issue a validation warning.

## Interpolation

Model output times and dataset times may differ.

Initial policy:

- interpolate model states linearly to dataset times;
- reject extrapolation beyond model time range unless explicitly allowed.

## Tests

Test exact-time comparison, interpolation, extrapolation failure, standardized residuals, missing uncertainty handling, and metrics including RMSE and chi-square when uncertainty exists.

---

# Part 7: Synthetic dataset generation

## Reason

Before using literature data, test the entire data/calibration pipeline on synthetic data where the true answer is known.

## Required module

Create:

```text
src/fungal_model/data/synthetic.py
```

Initial generator:

```python
generate_synthetic_dataset_from_result(
    result: SimulationResult,
    observable_mapping: Mapping[str, str],
    output_dir: str | Path,
    noise_model: NoiseModel,
    seed: int,
) -> ExperimentDataset
```

Simpler first version is acceptable:

```python
generate_first_order_ab_synthetic_dataset(...)
```

but generic is better if practical.

## Noise model

Initial:

```python
@dataclass(frozen=True)
class GaussianNoise:
    sigma: Quantity
    seed: int
```

Requirements:

- fixed seed for reproducibility;
- noise metadata saved;
- true values optionally saved in generation record;
- generated dataset marked `maturity: synthetic`.

## Output

Synthetic generation should write:

```text
synthetic_first_order_ab.yml
synthetic_first_order_ab_observations.csv
generation_record.json
```

## Tests

Test reproducibility with same seed, changed observations with different seed, reloadability, comparison against original model result, and generation record metadata.

---

# Part 8: Calibration infrastructure on synthetic data

## Reason

Do not calibrate real biology yet. First prove the calibration machinery can recover a known parameter from synthetic data.

## Required module

Create or extend:

```text
src/fungal_model/calibration/
```

Potential files:

```text
calibration/config.py
calibration/residuals.py
calibration/least_squares.py
calibration/report.py
```

## Required function

```python
calibrate_configured_model(
    *,
    model_config: str | Path,
    dataset: ExperimentDataset | str | Path,
    parameter_symbols: Sequence[str],
    observable_mapping: Sequence[ObservableMapping],
    initial_guess: Mapping[str, float],
    bounds: Mapping[str, tuple[float, float]] | None = None,
    output_dir: str | Path | None = None,
) -> CalibrationResult:
    ...
```

## Required object

```python
@dataclass(frozen=True)
class CalibrationResult:
    dataset_id: str
    model_config: str
    parameter_symbols: tuple[str, ...]
    fitted_parameters: ParameterSet
    initial_guess: dict[str, float]
    bounds: dict[str, tuple[float, float]]
    metrics: dict[str, float]
    residuals: tuple[ResidualSeries, ...]
    success: bool
    optimizer_metadata: dict[str, Any]
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]: ...
    def save(self, output_dir: str | Path) -> None: ...
```

## First calibration target

Synthetic first-order model:

```text
A -> B
rate constant k_ab
```

Generate synthetic data with known `k_true`.

Fit `k_ab`.

Test that recovered parameter is within tolerance:

```python
assert fitted_k == pytest.approx(k_true, rel=0.05)
```

The exact tolerance depends on noise.

## Rules

- calibration must not mutate source config in place;
- calibration must write a calibrated parameter set separately;
- calibration result must record initial guess, bounds, optimizer status;
- calibration must not claim validation;
- calibration must be synthetic-only at first.

---

# Part 9: Train/validation split infrastructure

## Reason

Later, real scientific claims require calibration and independent validation.

Build the split machinery now using synthetic data.

## Required feature

In dataset YAML or calibration config:

```yaml
split:
  method: by_time
  train_fraction: 0.7
  validation_fraction: 0.3
```

or:

```yaml
split:
  train_ids: [...]
  validation_ids: [...]
```

Calibration uses train points only.

Report metrics separately:

```text
train_rmse
validation_rmse
train_chi_square
validation_chi_square
```

Tests must verify no overlap and no validation claim if no validation split exists.

---

# Part 10: Literature extraction schema, but no real extraction yet

## Reason

Before reading papers, define how paper-derived data must be recorded.

Create:

```text
data/experiments/literature/README.md
```

Every literature dataset must record citation, DOI/URL, authors, year, figure/table, extraction method/tool, extracted_by, extraction_date, raw units, notes, digitization metadata if applicable, table metadata if applicable, unit-conversion notes, excluded points, and preprocessing steps.

No real paper data should be added until this contract exists and has schema tests.

---

# Part 11: Data validation rules

Implement validators for required metadata, valid maturity, known units, CSV columns, finite numeric values, nonnegative time, monotonic time per series, nonnegative uncertainty, uncertainty presence unless explicitly allowed missing, no duplicate measurement IDs, source/provenance, and preprocessing notes.

Each validator must have at least one passing and one failing test.

---

# Part 12: Public API

Once stable, expose:

```python
from fungal_model.data import (
    ExperimentDataset,
    MeasurementSeries,
    ObservableMapping,
    load_experiment_dataset,
    evaluate_model_against_dataset,
)
```

Maybe expose top-level later. Do not expose unstable calibration APIs top-level until tested.

---

# Part 13: Output structure

Comparison output:

```text
outputs/comparisons/<name>/
    comparison_record.json
    dataset_snapshot.json
    observable_mapping.json
    residuals.csv
    metrics.json
    validation_report.json
    figures/
        observed_vs_predicted.png
        residuals.png
```

Calibration output:

```text
outputs/calibration/<name>/
    calibration_record.json
    source_model_config.json
    dataset_snapshot.json
    fitted_parameters.yml
    fitted_parameters.json
    optimizer_metadata.json
    train_residuals.csv
    validation_residuals.csv
    metrics.json
    assumptions.json
    warnings.json
    figures/
        observed_vs_predicted_train.png
        observed_vs_predicted_validation.png
        residuals_train.png
        residuals_validation.png
```

---

# Part 14: Milestone sequence

## D1: Dataset schema and loader

Deliver:

- `ExperimentDataset`;
- YAML loader;
- CSV measurement loader;
- validation;
- synthetic dataset YAML + CSV fixture.

Done when valid synthetic dataset loads and bad datasets fail structurally.

## D2: Observable mapping and comparison

Deliver:

- `ObservableMapping`;
- `evaluate_model_against_dataset`;
- residual computation;
- interpolation;
- comparison output bundle.

Done when a model result can be compared to a synthetic dataset.

## D3: Synthetic dataset generation

Deliver:

- generator from existing `SimulationResult`;
- Gaussian noise option;
- generation record;
- reproducibility tests.

Done when generated dataset reloads and compares correctly.

## D4: Synthetic calibration

Deliver:

- `calibrate_configured_model`;
- fit first-order `k_ab`;
- save calibration output;
- recover known parameter.

Done when synthetic calibration recovers known parameter within tolerance.

## D5: Train/validation split

Deliver:

- split representation;
- train/validation residuals;
- separate metrics;
- no validation claim without validation data.

Done when synthetic train/validation split works.

## D6: Literature schema only

Deliver:

- `data/experiments/literature/README.md`;
- fake-schema tests;
- no real paper data.

Done when the literature metadata contract exists before literature extraction begins.

---

# Definition of done for the data infrastructure layer

The data infrastructure layer is ready when:

1. synthetic datasets can be loaded and validated;
2. model outputs can be compared to datasets through explicit observable mappings;
3. residuals and metrics are unit-aware;
4. synthetic datasets can be generated reproducibly;
5. simple synthetic calibration recovers a known parameter;
6. calibration outputs are reproducible and inspectable;
7. train/validation split machinery exists;
8. literature data rules exist but no real paper data are added without the schema;
9. toy/synthetic/literature/calibrated/validated maturity labels are enforced;
10. all of this is tested in CI.

Only then should the project begin real literature extraction and real biology.

---

# First Codex task

Start with D1 only.

Task:

```text
Implement ExperimentDataset schema, YAML/CSV loader, validation, and one synthetic first-order dataset fixture.
```

Do not implement calibration yet.

Do not add real literature data.

Do not add biology.
