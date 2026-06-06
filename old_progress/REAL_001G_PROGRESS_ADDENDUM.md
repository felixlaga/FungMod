# REAL-001G Progress Addendum

Add this section to:

```text
foundation_progress/REAL_001_SABIO_RK_PROGRESS.md
```

## REAL-001G: Native homogeneous Michaelis-Menten exploratory ensemble support

Status: superseded by `foundation_progress/REAL_001_SABIO_RK_PROGRESS.md`; REAL-001G is complete.

### Goal

Move the successful notebook workaround into the package so `simulate_screen(...)` supports:

```text
process_type: homogeneous_michaelis_menten
```

### Current known state

- SABIO-RK Reaction 618 EntryID 35622 is loaded.
- Scientific mode is underparameterized because `enzyme_concentration_beta_glucosidase` is unknown.
- Manual notebook workaround sampled enzyme concentration from a user-supplied loguniform range.
- Manual run succeeded for 32/32 samples.
- `simulate_screen(...)` currently fails because it supports only `surface_catalysis`.

### Completed work

- Native homogeneous Michaelis-Menten ensemble support was implemented in `simulate_screen(...)`.
- A clearly marked exploratory enzyme-concentration prior was added for Reaction 618.
- Scientific mode remains underparameterized when the SABIO-RK enzyme concentration is unknown.
- The Reaction 618 notebook now calls `simulate_screen(...)` directly.
- Tests cover exploratory run success, fixed-seed reproducibility, sampled-value bounds, scalar final-state outputs, and scientific strictness.

### Incomplete work

- None for REAL-001G.

### Architecture debt

- The manual notebook workaround has been removed.
- Homogeneous Michaelis-Menten ensemble dispatch has been implemented.
- Final-state CSV output now stores scalar final values.
- Remaining debt is tracked in `foundation_progress/REAL_001_SABIO_RK_PROGRESS.md`.

### Data debt

- `enzyme_concentration_beta_glucosidase` is not curated from SABIO-RK EntryID 35622.
- Any enzyme concentration range is user-supplied exploratory input, not literature data.
- No time-course validation dataset exists yet.

### Next recommended action

Follow the current next phase recorded in:

```text
foundation_progress/REAL_001_SABIO_RK_PROGRESS.md
```
