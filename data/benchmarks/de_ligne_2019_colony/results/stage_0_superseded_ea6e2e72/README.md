# Superseded stage 0 record (plan digest ea6e2e72...)

The first recorded stage 0 of COLONY-001, run on 2026-10-06 under the plan as
amended once (digest `ea6e2e7270b809fee092655f7e6882cf266e16d86d955c276ba5e2edc5ad959e`),
at the declared resolution (283 radial cells, 80 x 80 cartesian cells, hours
1 to 62) and the module's artificial check values.

| Check | Tip count | Mycelial area | Threshold | Verdict |
| --- | --- | --- | --- | --- |
| Grid (283 against 566 radial cells) | 0.574 | 0.102 | 0.02 | failed |
| Solver (LSODA against BDF) | 3.6e-6 | 0 | 0.005 | passed |
| Symmetry (radial against 80 x 80 cartesian) | 0.760 | 0.192 | 0.03 | failed |

The values are the largest relative differences over the output times. The
failure is the model's, not the solver's: the active translocation term
carried internal reserve up the tip-density gradient while branching made
tips where the reserve was, and the tips aggregated into a spike whose height
grew without bound as the cell shrank. Plan amendment 2 removed the active
term and added a fit-time grid-convergence guard before any fit; the current
`../stage_0/` record is the re-run under the amended plan. This record is
kept unchanged as the evidence for the amendment.
