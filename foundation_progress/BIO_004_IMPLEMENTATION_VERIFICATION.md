# BIO-004 implementation verification

Date: 2026-10-09. Plan: PR #134, head `5ad535a65dd077c6221149ac8f41bb621dd527ea`.
Implementation was developed and verified in the attached
`bio004-six-mechanisms` worktree on branch `codex/bio004-six-mechanisms`.
The original `lit-correct` checkout and its separate ongoing work are excluded
from this change set. This report records local verification before publication;
remote delivery and CI status are reported separately in the task. Publishing
these commits does not release a package or publish a new scientific dataset.

The implementation is based on the merged planning PR at `a26ba3f`. Its tree is
identical to plan head `5ad535a`, so adopting that mainline parent introduces no
source changes relative to the tested implementation.

## What changed

All six explicit mechanism implementations, their law-form source records,
compiled rates and gradients, evidence-bearing input routes, numerical ledgers,
summary reductions, examples and scope documentation are implemented. The
[guide](../docs/bio004-mechanisms.md) identifies the exact supported scope.

Shared numerical changes support signed/bounded states and state-driven
environmental modifiers. Bounds are converted before merging; numerical
derivatives remain inside declared domains. Unsupported signed/bounded models
are refused by SBML export rather than silently losing their domain semantics.
Source readiness is enforced for both mapping and file API callers.

## What did not change

No experimental dataset, fitted constant, original checkout or default CAZy
mapping was modified. Seven historical user datasets retain their pinned
record hashes; older annotation/draft routes retain their output behavior.
Existing unbounded nonnegative-state arithmetic has exact compatibility tests.
Older models opt into none of the new mechanism behavior by default.

## Tests added or modified

New tests cover source records and promotion bypasses, adsorption on two solids
and three enzyme-unit bases, explicit sugar/oxygen closure, dynamic responses,
pH titration and signed pH-stat, finite-chain scission, peroxide cleavage and
inactivation, counterfactual denominators, input evidence/units/refusals,
threshold reductions, finite-run mechanism summaries, undefined fractions with
strict JSON/CSV serialization, legacy/null template metadata, signed states
crossing zero, mixed-unit bounds, bounded
numerical derivatives, public CSV/CLI paths and output artifact reuse.
Publication checks extend Git transport byte-preservation coverage to all three
new mechanism input/source directories, preventing line-ending conversion from
changing provenance hashes.
Existing contract checks were updated for new factory types, explicit-only
registry classes, new culture quantities, native state-modifier Jacobians and
new configured CLI commands. Historical digest expectations were not repinned.

Independent reviews found and corrected unit, domain, derivative, source-gate,
standalone-chain-state and export issues before the final full run.

## Commands and results

The interpreter is `/Users/felix/Documents/GitHub/FungMod/.venv/bin/python`.
Source checks use `PYTHONPATH=src:/tmp/fungmod-testdeps` in the isolated worktree.
Optional test dependencies were installed under `/tmp`, leaving the project
virtual environment unchanged. Ruff uses a writable `/tmp/fungmod-ruff` cache.

| Command/check | Result |
| --- | --- |
| `python -m ruff check src tests scripts/run_*.py` | Passed |
| `python -m pyright --pythonpath /Users/felix/Documents/GitHub/FungMod/.venv/bin/python` | 0 errors, 0 warnings |
| `python -m mkdocs build --strict` | Passed |
| `python -m build` | Wheel and source distribution built |
| `python -m twine check dist/*` | Both distributions passed |
| `git diff --check` | Passed; staged byte-preserved data checked separately |
| `python -m pytest -q tests/test_git_data_integrity.py` | Publication guardrail: 3 passed across all Git line-ending modes |
| Installed wheel replay from outside repository | Four configured mechanism examples and both explicit-table examples ran; all configured validators passed; all eight packaged law records validated; all six summary files passed strict JSON/schema checks |
| Full frozen-source pytest/coverage command | **3,438 passed, 1 failed, 1 warning** in 573.14 seconds; **88.44% coverage** (80% required). The sole failure is the pre-existing digitizer discrepancy documented below. |

Full command:

```bash
PYTHONPATH=src:/tmp/fungmod-testdeps MPLBACKEND=Agg \
  /Users/felix/Documents/GitHub/FungMod/.venv/bin/python -m pytest \
  -n 8 --dist loadfile --cov=fungal_model \
  --cov-report=term-missing --cov-report=xml
```

The full suite exits with status 1 because of that existing failure; it is not
reported as fully green. All implementation and compatibility regressions pass.
No requested quality command was unavailable. A source-hash-sensitive Gelain
benchmark test passed in isolation on both the implementation and pristine plan
HEAD; final verification runs with all source edits frozen. Existing multi-state
quicklook plots emit Matplotlib tight-layout warnings; this task does not claim
visual validation of those plots.

### Existing digitizer reproducibility discrepancy

`tests/test_de_ligne_2019_dataset.py::test_digitizer_reproduces_the_committed_files_from_the_preserved_pdfs`
also fails on a pristine archive of plan HEAD `5ad535a`. The extracted numeric
CSV values and panel table agree with the preserved files. A metadata-only
`panel_disagreement` flag lies on a floating-point boundary: the difference is
`0.05893909626719063`, the three-pixel threshold `0.0589390962671906`, an excess
of `2.78e-17`. This changes the C. puteana metadata and audit count. Initial
Pillow/pypdfium2 version mismatches disappeared after installing the recorded
12.3.0/5.14.0 versions under `/tmp`; the flag discrepancy remains. Frozen data,
expected flags and tolerances were not changed to mask it.

## Scientific behavior, compatibility and remaining ambiguity

Scientific behavior changes only with explicit new mechanisms or state metadata.
The implementations are software-tested with checked law forms; they are not
calibrated or empirically validated. M5 uses the sourced finite-chain population
law instead of inventing aggregate chain-end exhaustion. M6 uses the full sourced
ternary law; oxidative-to-chain fragment allocation remains unsupported without a
source. Pirt's capped maintenance closure is an explicit exploratory extension;
its original primary abstract, rather than inaccessible full text, was verified.
All constants and initial conditions remain user-supplied evidence.

One sugar pool, fixed-volume ideal buffering, explicit oxygen saturation and
externally supplied peroxide are bounded modeling choices. Dynamic adsorption,
repression, stalling, in situ peroxide generation, culture-parameter fitting and
unsourced oxidative chain allocation are outside the delivered scope. Thresholds
are supplied explicitly; none is inferred. The default annotation route does not
start predicting new enzyme mechanisms from family presence alone.

Risk is **medium** for new numerical/scientific behavior, contained by opt-in
inputs, explicit limitations and backward-compatibility checks. Next: resolve the
existing digitizer's metadata boundary independently, then freeze a licensed,
condition-matched calibration and independent holdout study before making
predictive-accuracy claims.
