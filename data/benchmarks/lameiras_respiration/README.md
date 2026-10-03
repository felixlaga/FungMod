# Lameiras respiration source intake

CC-BY-4.0 primary articles and deterministic numeric table extracts. Attribution:
Francisca Lameiras, Joseph J. Heijnen and Walter M. van Gulik (2015),
doi:10.1007/s11306-015-0781-z; Francisca Lameiras, Cor Ras, Angela ten Pierick,
Joseph J. Heijnen and Walter M. van Gulik (2017), doi:10.1007/s00449-017-1854-3.
License: https://creativecommons.org/licenses/by/4.0/.

`manifest.json` pins downloaded primary XML and the extract. Reproduce with
`python scripts/prepare_respiration_data.py --check`. Changes from the sources:
XML table extraction, standardized field names, mmol/mCmol-to-mol/Cmol conversion,
role annotations and explicit quality flags. No published numbers are corrected.

Primary fitting/scoring uses only 2015 unreconciled glucose/oxygen/CO2 rates.
Reconciled rates are separately marked; conservation imposed during their
construction cannot be independently validated against them. A 2017 CO2/TOC
pair at dilution 0.16/h is quarantined pending source verification. Reported
errors are not assumed to be independent standard deviations. Same laboratory,
same strain, different pH/regime; sequential mixed-substrate conditions share a
culture. Full scientific scope and reproduction are in
`docs/respiration-benchmark.md` at the repository root.

This intake does not promote parameters into the registry, authorize biological
predictions, resolve unidentified secreted organic carbon, or supply fungal
formation energies or kinetic resource-limitation parameters.
