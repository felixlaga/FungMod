# Jørgensen 2009 extracellular protein production

Jørgensen TR, Goosen T, van den Hondel CAMJJ, Ram AFJ, Iversen JJL (2009).
*Transcriptomic comparison of Aspergillus niger growing on two different sugars
reveals coordinated regulation of the secretory pathway*. BMC Genomics 10:44.
DOI: [10.1186/1471-2164-10-44](https://doi.org/10.1186/1471-2164-10-44).

The preserved primary article XML was retrieved from
[Europe PMC](https://www.ebi.ac.uk/europepmc/webservices/rest/PMC2639373/fullTextXML)
on 2026-10-03. The article is licensed under
[CC BY 2.0](https://creativecommons.org/licenses/by/2.0/).
`manifest.json` binds the primary source and deterministic extract by byte count
and SHA-256. No data values have been corrected or digitized from figures.

`observations.json` contains all four Table 1 rows, original text, units, means,
SDs, significance markers, footnotes and assay metadata. The four group means
describe three steady states per strain/carbon combination. There were six
culture runs, each switched from xylose to maltose; these are not twelve
independent culture runs. Nominal growth/dilution rate is 0.16/h, 30°C, pH 3.
Maltose residuals are glucose equivalents, retained in the reported basis.

This supports a bounded, retrospective test of total extracellular protein
output conditioned on supplied growth rate and carbon-source identity. It does
not establish the dynamic regulatory mechanism, active enzyme concentration,
protein composition, catalytic activity, synthesis yield, retention/loss, or
full fungal degradation. Raw replicates and cross-condition covariances were
not published in this table. SDs are not confidence intervals. Transcriptomic
measurements are not converted to enzyme concentration.

Re-extract offline with `python scripts/prepare_secretion_data.py`; verify
without writing with `python scripts/prepare_secretion_data.py --check`.
