# Calibration Data

This folder contains synthetic calibration fixtures. The configured calibration
API also accepts provenance-complete `literature_raw` and `literature_processed`
datasets from `data/experiments/literature/`.

The supported calibration path is:

- load a configured FungMod model;
- load an explicitly labelled synthetic or literature `ExperimentDataset`;
- map dataset measurements to model observables explicitly;
- fit requested configured parameters;
- write a separate calibration output bundle.

Calibration must not mutate source model configs in place. Fitted parameter
sets, residuals, optimizer metadata, assumptions, warnings, and figures are
written to output bundles under the caller-selected output directory.

Literature fitting is parameter estimation for the recorded preparation and assay,
not independent validation. Source measurements remain unchanged. The stage-2
Alvarez-Gonzalez runner fits one series and predicts other conditions from the
same publication; those results are not independent experimental replication.

Training reduced chi-square uses the explicit fitted-parameter count. Held-out
metrics use zero parameters fitted to those observations. Pointwise uncertainty
is preserved; partial, nonpositive, or nonfinite uncertainty fails explicitly.
Entirely unknown uncertainty stays unknown, with an unweighted-fit warning.
Digitization resolution does not become experimental uncertainty after fitting.
