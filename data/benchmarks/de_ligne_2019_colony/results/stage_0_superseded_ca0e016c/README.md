# Superseded stage 0 record (plan digest ca0e016c...)

The second recorded stage 0 of COLONY-001, run on 2026-10-06 under plan
amendment 2 (digest `ca0e016cf22652c3d44bcfad49ac64f706eeea2f78a459470b11722c6f495103`),
at the declared resolution (283 radial cells to 28.3 mm, 80 x 80 cartesian
cells on the 40 mm window, hours 1 to 62) and the module's artificial check
values, with the active translocation term removed.

| Check | Tip count | Mycelial area | Threshold | Verdict |
| --- | --- | --- | --- | --- |
| Grid (283 against 566 radial cells) | 5.3e-5 | 0.0056 | 0.02 | passed |
| Solver (LSODA against BDF) | 1.1e-7 | 0 | 0.005 | passed |
| Symmetry (radial against 80 x 80 cartesian) | 0.382 | 0.059 | 0.03 | failed |

Without the active term the model is grid converged. The symmetry check
failed because the two domains differ once the colony reaches the window
edge: the cartesian reference was the 40 mm window with walls that reflect
tips back into it, and the radial domain ended at 28.3 mm with a wall of its
own; the two models agreed within 1 to 3 percent until about 12 h. Neither
wall is physical. Plan amendment 3 put the radial domain at the dish wall,
declared the window separately, and restricted the symmetry comparison to the
hours the colony is inside the window; `../stage_0/` is the re-run under the
amended plan. This record is kept unchanged as the evidence for the amendment.
