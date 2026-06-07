# VALIDATION-001: Deep Repository Review and Scientific/Architectural Audit

## Purpose

This file defines a validation-only milestone for FungMod.

The task is not to implement features.

The task is not to refactor code.

The task is not to fetch new data.

The task is not to add new biology.

The task is to perform a deep, professional, adversarial review of the entire repository and produce written validation artifacts that evaluate whether FungMod is moving toward its central goal:

```text
FungMod exists to let researchers run mechanistic virtual experiments of fungi or enzyme systems degrading substrates across environments, producing clean time-series and summary tables of substrate loss, product release, degradation rates, threshold times, uncertainty, provenance, and limitations.
```

Modelability is only a preflight guardrail.

The main product is degradation dynamics over time.

This validation pass must be severe. Assume hidden shortcuts may exist. Assume tests passing is not enough. Assume recent Codex changes may have introduced architecture debt.

---

## 1. Strict non-editing rule

This is a review-only pass.

Allowed actions:

```text
read files
run tests
inspect generated outputs
inspect notebooks
write validation reports
write proposed changes
write risk register
```

Forbidden actions:

```text
edit source code
edit registry records
edit data records
edit notebooks, except validation notes if explicitly placed under validation folder
fetch new data
add biology
refactor code
change APIs
change parameter values
change output formats
fix issues during the review
```

Only create or update files under:

```text
foundation_progress/validation/
```

Required artifacts:

```text
foundation_progress/validation/VALIDATION_001_DEEP_REPO_REVIEW.md
foundation_progress/validation/VALIDATION_001_PROPOSED_CHANGES.md
foundation_progress/validation/VALIDATION_001_TEST_RESULTS.md
foundation_progress/validation/VALIDATION_001_RISK_REGISTER.md
```

---

## 2. Files and areas to inspect

Review the whole repository.

At minimum inspect:

```text
README.md
pyproject.toml
src/fungal_model/
src/fungal_model/api/
src/fungal_model/screening/
src/fungal_model/data/
src/fungal_model/registry/
src/fungal_model/processes/
src/fungal_model/workflows/
src/fungal_model/calibration/
data_registry/
data/
notebooks/
tests/
foundation_progress/
scripts/
```

If folders do not exist, record this.

Do not assume missing folders are acceptable.

---

## 3. Required review artifact: deep repo review

Create:

```text
foundation_progress/validation/VALIDATION_001_DEEP_REPO_REVIEW.md
```

It must include:

```text
Executive summary
Current maturity rating
Central-goal alignment
Architecture assessment
Public API assessment
Researcher workflow assessment
Scientific-model assessment
Data/provenance assessment
Output-table assessment
Notebook assessment
Test-suite assessment
Documentation/progress-file assessment
Hidden-risk assessment
Critical blockers
High-priority improvements
Medium-priority improvements
Low-priority improvements
What must not be built next
What should be built next
```

This should be a professional technical review, not a short checklist.

---

## 4. Required review artifact: proposed changes

Create:

```text
foundation_progress/validation/VALIDATION_001_PROPOSED_CHANGES.md
```

List every change Codex recommends, but do not apply any changes.

Each proposed change must include:

```text
ID
Title
Priority: critical/high/medium/low
Category: architecture/API/science/data/tests/docs/notebooks/outputs
Reason
Evidence from repo
Files likely affected
Expected benefit
Risks
Acceptance criteria
Should this be done before new data ingestion? yes/no
Should this be done before new biology? yes/no
```

Bad proposed change:

```text
Improve API.
```

Good proposed change:

```text
Add DegradationResult.write_tables() that writes time_series_long.csv, final_metrics.csv, threshold_times.csv, sampled_parameters.csv, provenance_table.csv, and limitations_table.csv from RegistryScreenResult.
```

---

## 5. Required review artifact: test results

Create:

```text
foundation_progress/validation/VALIDATION_001_TEST_RESULTS.md
```

Record every command run.

At minimum attempt:

```bash
pytest tests/test_sabiork_reaction_618_registry_case.py
pytest tests/test_registry_ensemble_homogeneous_mm.py
pytest tests/test_registry_ensemble_simulation.py
pytest tests/test_environment_grid.py
pytest tests/test_virtual_experiment_environment_grid.py
pytest tests/test_sabiork_reaction_618_parameter_ranges.py
pytest tests/test_bio001_surface_cellulose_virtual_experiment.py
pytest
```

If a test file does not exist, record:

```text
not present
```

If tests fail, record the exact failure summaries.

Do not report success unless the tests were actually run.

---

## 6. Required review artifact: risk register

Create:

```text
foundation_progress/validation/VALIDATION_001_RISK_REGISTER.md
```

Each risk must include:

```text
Risk ID
Risk title
Severity
Likelihood
Evidence
Why it matters scientifically
Why it matters architecturally
Mitigation
Suggested next milestone
```

Include scientific risks, architecture risks, API risks, data risks, and testing risks.

---

## 7. Maturity scoring

Score the project from 0 to 10 in the following dimensions.

Provide a numeric score and explanation for each.

```text
Central-goal alignment
Architecture foundation
Public researcher API
Low-level developer API
Registry/data model
Scientific honesty
Biological realism
Output-table quality
Notebook usability
Testing depth
Data provenance
Extensibility
Atmodeller-like usability
Overall maturity
```

Use strict scoring.

Do not inflate scores.

If uncertain, say uncertain and explain what would need to be inspected.

---

## 8. Central-goal alignment audit

Answer these questions explicitly:

1. Does the current codebase primarily help simulate degradation dynamics over time?
2. Or is it drifting into modelability-only checks, registry decoration, or data dumping?
3. Does the public API hide internal complexity from researchers?
4. Can a researcher define a virtual experiment and receive degradation outputs?
5. Are output tables centered on substrate loss, product release, rates, threshold times, uncertainty, provenance, and limitations?
6. Are modelability checks correctly treated as preflight guardrails?
7. Are notebooks demonstrating the actual degradation process, or mostly internal infrastructure?
8. Are plots optional and derived from tables?
9. Are tables publication-friendly?
10. Are limitations explicit enough to prevent overclaiming?

---

## 9. Public API audit

Inspect at minimum:

```text
src/fungal_model/__init__.py
src/fungal_model/api/
src/fungal_model/screening/__init__.py
src/fungal_model/data/__init__.py
src/fungal_model/calibration/__init__.py
```

Evaluate:

```text
Is there a stable researcher-facing VirtualExperiment API?
Can a user define fungi, substrates, and environments easily?
Does the API expose degradation outputs, not internal implementation objects?
Does the API support environment grids?
Does the API support writing standard output tables?
Does the API support quick-look plots without making plots primary?
Does the API still require too many internal registry IDs?
Are internal classes leaking into public usage?
Are APIs versioned or stable enough?
```

Report whether the current API can support conceptual usage such as:

```python
study = FungMod.virtual_experiment(...)
result = study.simulate(...)
result.write_tables(...)
```

If not, explain exactly what is missing.

---

## 10. Output-table audit

Inspect generated output code and tests.

Validate whether FungMod can write or intends to write:

```text
modelability_preflight.csv
case_summary.csv
time_series_long.csv
final_states.csv
final_metrics.csv
threshold_times.csv
sampled_parameters.csv
sampled_parameter_summary.csv
summary_metrics.csv
trajectory_quantiles.csv
provenance_table.csv
limitations_table.csv
environment_summary.csv
screen_summary.json
```

For each table, record:

```text
exists / missing / partially exists
file or function responsible
test coverage
scientific meaning
problems
```

Check especially:

```text
final states are scalar values, not trajectory lists
time series are long-format or otherwise easy to analyze
threshold times are computed correctly
not_reached cases are represented honestly
units are included
environment columns are included where relevant
sampled parameter provenance is preserved
```

---

## 11. Scientific honesty audit

Look for overclaims.

Check whether code, notebooks, docs, progress files, or filenames imply:

```text
enzyme-only case = whole fungus eating substrate
exploratory prior = literature value
literature range = calibrated uncertainty
broad cross-organism range = condition-specific response curve
modelable = validated
simulation = experimentally proven
pH/temperature grid = pH/temperature response law
cellulose surface pilot = whole-fungus cellulose degradation
```

If any of these appear, record them as critical scientific risks.

---

## 12. Data and provenance audit

Inspect:

```text
data/
data_registry/
scripts/
src/fungal_model/data/
foundation_progress/
```

Check:

```text
Are raw snapshots preserved?
Are curated records separated from raw data?
Are selected entries documented?
Are excluded entries documented?
Are parameter ranges scoped correctly?
Are original units preserved?
Are converted units documented?
Are source EntryIDs/PubMed IDs retained?
Are user-supplied exploratory priors clearly marked?
Are synthetic/test values clearly marked?
Are unknown values preserved as unknown rather than patched?
Are broad literature ranges used only where appropriate?
```

Special focus:

```text
SABIO-RK Reaction 618
EntryID 35622
Km/kcat exact values
enzyme_concentration_beta_glucosidase unknown
exploratory enzyme concentration prior
multi-entry literature ranges
parameter_range_summary.json
```

---

## 13. ENV-001 audit

If ENV-001 exists, inspect it deeply.

Check whether environment grids are implemented as virtual experiment case expansion, not fake response models.

Check:

```text
EnvironmentGrid creates correct combinations
environment IDs are stable
output tables include environment metadata
environment_effect_status is present
pH/temperature do not silently affect kinetics without response laws
limitations explain whether environment is metadata-only or active
environment_summary.csv exists
```

Critical risk:

```text
The code must not imply pH/temperature response if no modifier or condition-specific parameters exist.
```

---

## 14. DATA-002 audit

If DATA-002 exists, inspect it deeply.

Check:

```text
local SABIO-RK snapshot is used
live API is not required for tests
eligible entries table exists
excluded entries table exists
every exclusion has a reason
ranges are scoped by organism/pH/temperature where possible
groups with low n are marked insufficient_n
broad ranges are not treated as selected-entry uncertainty
```

Critical risk:

```text
Do not let DATA-002 ranges become fake environmental response curves.
```

---

## 15. BIO-001 audit

If BIO-001 exists, inspect it deeply.

Check whether it truly added:

```text
solid/insoluble cellulose-like substrate degradation
surface-accessible substrate process
soluble product release
biologically meaningful output states
threshold times
limitations
tests
notebook
```

Check whether it improperly added:

```text
whole-fungus claims
secretion without parameters
uptake without parameters
growth without process law
fake cellulose degradation constants
hardcoded toy values without exploratory labels
```

BIO-001 should be a controlled step from soluble enzyme kinetics toward solid substrate degradation.

It must not pretend to be a full fungus-on-cellulose model.

---

## 16. Architecture audit

Inspect for structural problems:

```text
large god modules
duplicated process-specific code
private helper imports across modules
hardcoded Reaction 618 assumptions in generic code
hardcoded cellobiose/cellulose/PET assumptions
notebook-only core logic
test-only logic leaking into production
registry mutation at runtime without explicit overlay design
poor separation between raw data, curated records, registry records, and outputs
unclear process/plugin interface
unclear result-table generation layer
```

For every issue, record:

```text
evidence
risk
proposed fix
priority
```

---

## 17. Testing audit

Evaluate whether tests cover:

```text
unit tests
registry loading
modelability
case building
ensemble simulation
homogeneous Michaelis-Menten
surface catalysis
environment grids
virtual experiment API
output tables
threshold metrics
data provenance
scientific/exploratory separation
failure modes
notebook smoke tests
```

Identify missing tests.

Pay special attention to tests that only check file existence but not scientific contents.

---

## 18. Notebook audit

Inspect notebooks.

Check:

```text
Do notebooks use public APIs rather than internal functions?
Do notebooks avoid defining core model logic?
Do notebooks clearly distinguish scientific vs exploratory mode?
Do notebooks show degradation dynamics, not only modelability?
Do notebooks display output tables?
Do notebooks save reproducible outputs?
Do notebooks state limitations?
Do notebooks avoid whole-fungus claims for enzyme-only examples?
```

---

## 19. Documentation/progress audit

Inspect:

```text
foundation_progress/
README.md
docs/, if present
notebook markdown cells
```

Check:

```text
Is the central goal present?
Are milestones tracked?
Are completed/incomplete tasks clear?
Are architecture debt and data debt recorded?
Are next steps concrete?
Are limitations honest?
```

If progress files are missing, mark as high priority.

---

## 20. Hidden-flaw search

Actively search for hidden flaws.

Examples:

```text
TODO
FIXME
hack
placeholder
toy
hardcoded
fake
mock
broad except blocks
silent exception handling
default values that become physical constants
random seeds not preserved
units ignored
parameter values without provenance
tests that rely on live API
notebooks that mutate registry files
output files that overwrite each other
misleading function names
```

Create a section listing all suspicious findings.

---

## 21. Final recommendation

The review must end with:

```text
Recommended next milestone
Do / do not proceed to new data ingestion
Do / do not proceed to new biology
Do / do not proceed to public API polishing
Top 5 blockers
Top 5 safe next tasks
```

Be explicit.

If the repo is not ready for new data, say so.

If the repo is not ready for new biology, say so.

If the repo should consolidate API/output layers first, say so.

---

## 22. Final response format

After completing this validation pass, respond with:

```text
1. Files reviewed
2. Commands/tests run
3. Files created
4. Executive summary
5. Maturity scores
6. Critical blockers
7. Highest-risk hidden flaws
8. Whether API-001/ENV-001/DATA-002/BIO-001 are correctly implemented
9. Whether the repo is aligned with the central goal
10. Whether new data ingestion should continue
11. Whether new biology should continue
12. Next recommended milestone
```

Do not say the repo is good because tests pass.

Do not say a milestone is complete unless its scientific meaning and output behavior are correct.
