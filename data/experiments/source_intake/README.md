# Public experimental source intake

Fetched and reviewed on 2026-09-28. `manifest.json` records original file URLs,
licenses, sizes, and SHA-256 digests. Source licenses remain applicable; the
repository's MIT software license does not replace them. No downloaded code or
spreadsheet formula was executed. The full Gelain archive includes simulations
and code and must never be bulk-imported as experimental observations.

## Gelain 2020: a first whole-culture benchmark candidate

Lucas Gelain, *Mathematical modelling for the optimization of cellulase
production*, Mendeley Data V2,
[10.17632/shd3wcczsr.2](https://data.mendeley.com/datasets/shd3wcczsr/2), CC BY 4.0.
Related article by Gelain, van der Wielen, van Gulik, Pradella and da Costa:
[10.1016/j.cesx.2020.100085](https://doi.org/10.1016/j.cesx.2020.100085).

`gelain_2020/supplementary_material.rar` preserves the exact download.
`originals/` preserves the six experimental workbooks and two Information
documents. Those documents explicitly distinguish concentration-specific
experimental workbooks from simulated `data.xlsx` trajectories.

`simulation_reference/{glycerol,cellulose}.xlsx` now preserves those two
deposited simulation workbooks as a separate role in the source manifest.
They produce `data/benchmarks/gelain_2020/source_simulations.csv` and the full
precision source parameter records. They are used only to test software parity;
they never become experimental observations or independent validation.

`recorded_values.csv` contains **162 source entries**: 144 published mean values
and 18 initial-condition entries, spanning six conditions at nine times.
It retains each source file, sheet and cell, and the source's numeric precision.
The record grain is one observable at one time under one culture condition.
These are not 162 independent experimental replicates.

- Glycerol: nominal 5, 10 and 20 g/L, biomass and substrate.
- Cellulose: nominal 10, 20 and 30 g/L, biomass, substrate, filter-paper activity
  (FPU/L), and beta-glucosidase activity (U/L).
- Strain: *Trichoderma harzianum* P49P11; 29 °C, controlled pH 5.0 ± 0.5,
  1.9 L working volume; dissolved oxygen kept above 30% (article Methods 2.2).
- Individual duplicate runs and their SD arrays are absent. Empty uncertainty
  and replicate fields mean **unknown**, not zero or one replicate.
- The article describes averages of duplicate cultures with different inocula.
  Initial biomass values are source averages/initializations, not extra samples.
- The workbooks include 54 h, omitted from the Methods sampling list. It is
  preserved and flagged. Early substrate increases and later non-monotonicity
  are preserved. Reported zeros have unknown detection/censoring limits.
- Original-paper validation conditions (15 g/L glycerol, 5/40 g/L cellulose,
  repeated batch) were not found as experimental workbooks. Simulink validation
  files are models, not replacement observations.

The six datasets under `../literature/gelain_2020_t_harzianum/` expose only
biomass and substrate, excluding t=0: **96 observations in twelve series**.
Activity data remain here until an explicit assay-to-model observation operator
is implemented. FPU/L and U/L must not be converted into enzyme mass or molarity
without a justified, preparation-specific calibration. These datasets support
exploratory comparison and a new bounded benchmark, not the existing frozen
prediction evaluator's raw-replicate validation requirements.

## Novy 2021: secretome composition evidence

Vera Novy, Fredrik Nielsen, Daniel Cullen, Grzegorz Sabat, Carl J. Houtman and
Christopher G. Hunt, additional file 2,
[10.6084/m9.figshare.14490032.v1](https://doi.org/10.6084/m9.figshare.14490032.v1).
Article: [10.1186/s13068-021-01955-5](https://doi.org/10.1186/s13068-021-01955-5).
The repository labels the license `CC BY + CC0`; its exact metadata is preserved.

`novy_2021/secretome.xlsx` is the original four-sheet workbook.
`proteins_all.csv` extracts the 232 populated protein rows of `Proteins_All`
without changing the source's condition labels or values. The header says
`Identified Proteins (234/242)` although this sheet has 232 populated data rows;
the source discrepancy is retained, not filled with invented records.

These are endpoint **normalized total spectra**, under three substrate
conditions for *T. reesei* QM6a. They are processed abundance measurements, not
absolute concentrations, secretion rates, kinetic constants, or degradation
time courses. No biological replicate columns appear in this sheet. They can
help select enzyme classes for a later strain-specific module; they cannot be
pooled with the different *T. harzianum* preparation as matched validation.

## De Ligne 2019: colony growth under a temperature-humidity grid

De Ligne L, Vidal-Diez de Ulzurrun G, Baetens JM, Van den Bulcke J, Van Acker J,
De Baets B (2019). Analysis of spatio-temporal fungal growth dynamics under
different environmental conditions. IMA Fungus 10:7,
[10.1186/s43008-019-0009-3](https://doi.org/10.1186/s43008-019-0009-3), CC BY 4.0.

`de_ligne_2019/article.pdf` and `de_ligne_2019/additional_file_{1..5}.pdf` are
the owner's downloads from the article page (the development container cannot
reach the publisher), preserved verbatim with their SHA-256 digests. Additional
file 1 documents the image-analysis workflow; files 2 to 5 are one-page PDFs
carrying the growth curves as embedded raster panels: mycelial area (files 2
and 3) and number of tips (files 4 and 5) for *Coniophora puteana* and
*Rhizoctonia solani*, hourly to 62 h, as the mean of four replicates with
standard-deviation bars, for the sixteen combinations of four temperatures and
four relative humidities. No table or machine-readable series is published and
individual replicates are available from the authors on request only.

`de_ligne_2019/digitized_panels.csv` is the per-panel extraction table written
by `scripts/digitize_de_ligne_2019_figures.py`: one row per figure, panel,
series and hour with the marker pixel position, its visible fraction, the
error-bar extents and which caps were visible, the converted value and the
reading flags. The merged datasets under
`../literature/de_ligne_2019_colony_growth/` are built from it. Regenerate
with the script; verify with `--check`.

## Reproduction and access results

Run `python scripts/prepare_public_experimental_data.py --check` from the repo
root. It verifies all original hashes and reproduces all CSV/YAML extracts
offline. Omit `--check` to regenerate the reviewed outputs. Formula cells and
changed source headers fail rather than silently becoming measurements.

The Mendeley HTTP client/API returned 403; the site's normal browser download
succeeded. The article PDF came from TU Delft and the secretome workbook from
Figshare. A further candidate, PeerJ 8792 supplemental raw pNPG activity data,
was located but **not fetched**: direct requests returned 403, the PMC page
displayed a challenge, and the Europe PMC supplementary endpoint returned 502.
It is also a different substrate/preparation from current cellobiose curves.
No communication was sent to authors and no inaccessible values were inferred.
