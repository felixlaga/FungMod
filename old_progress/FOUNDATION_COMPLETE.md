# Foundation Complete Gate

Status: complete

Date: 2026-05-28

This gate certifies the FungMod software foundation only. It does not approve
real fungal biology, PETase mechanisms, literature parameters, fungal
metabolism, growth physiology, or substrate-specific scientific mechanisms.

## Completion Criteria

- [x] all guardrail tests pass;
- [x] all configured workflow tests pass;
- [x] all failure-path tests pass;
- [x] all maturity-mode tests pass;
- [x] all output reproducibility tests pass;
- [x] CI passes;
- [x] coverage gate passes;
- [x] no active foundation-blocking architecture debt remains;
- [x] PET is plugin-only;
- [x] notebooks use public APIs only;
- [x] README honestly states limitations;
- [x] `run_configured_model` runs homogeneous, dummy non-PET, and PET-plugin foundation configs.

## Active Non-Blocking Architecture Debt

- `FD-005`: Pyright optional-member-access remains disabled. This is a
  package-quality ratchet, not a foundation-blocking architecture debt and not
  permission to add biology.
- `FD-006`: Process-to-Reaction compatibility adapters remain for the P1.4
  retirement/containment decision. This is adapter-transition tracking, not a
  foundation-blocking architecture debt and not permission to route configured
  public workflows through the legacy reaction engine.

## Required Evidence

- `tests/test_guardrails_no_hardcoding.py`
- `tests/test_guardrails_no_shortcuts.py`
- `tests/test_guardrails_public_api.py`
- `tests/test_guardrails_config_generality.py`
- `tests/test_guardrails_native_execution.py`
- `tests/test_configured_model_workflow.py`
- `tests/test_configured_workflow_components.py`
- `tests/test_configured_workflow_failures.py`
- `tests/test_maturity_policy.py`
- `tests/test_configured_output_bundle_reproducibility.py`
- `tests/test_notebooks.py`
- `tests/test_quality_config.py`
- `tests/test_foundation_complete_gate.py`

## Required Commands

```bash
python -m ruff check src tests
python -m pyright --pythonpath "$(python -c 'import sys; print(sys.executable)')"
python -m pytest --cov=fungal_model --cov-report=term-missing --cov-report=xml
```
