# Calibration Data

Calibration records in this folder are configuration and provenance fixtures
for the data-infrastructure layer. They do not contain empirical biology.

The first supported calibration path is synthetic-only:

- load a configured FungMod model;
- load a synthetic `ExperimentDataset`;
- map dataset measurements to model observables explicitly;
- fit requested configured parameters;
- write a separate calibration output bundle.

Calibration must not mutate source model configs in place. Fitted parameter
sets, residuals, optimizer metadata, assumptions, warnings, and figures are
written to output bundles under the caller-selected output directory.

Real literature calibration is not allowed yet.
