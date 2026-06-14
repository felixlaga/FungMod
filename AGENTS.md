# FungMod Agent Instructions

## Current Goal

FungMod is a registry-backed, uncertainty-aware, mechanistic virtual-experiment
engine for fungal and enzyme-mediated substrate degradation. Work should move
toward honest simulations of degradation dynamics over time: substrate loss,
product release, degradation rates, threshold times, uncertainty, provenance,
limitations, and suggested follow-up experiments.

## Active Source Of Truth

Use these sources in order:

1. `AGENTS.md` for binding Codex and contributor instructions.
2. `README.md` for the current user-facing capability summary and quality gates.
3. `foundation_progress/FUNGMOD_CENTRAL_GOAL_VIRTUAL_EXPERIMENTS.md` for the central product goal.
4. `foundation_progress/FUNGMOD_NEXT_PHASES_ROADMAP.md` for active roadmap intent, after checking status against code, tests, and `progress.md`.
5. `progress.md` for the implementation ledger.
6. `ARCHITECTURE_DEBT.md` for active architecture-debt containment.
7. Executable code and tests for actual behavior.

If roadmap text, progress notes, and executable behavior disagree, verify the
behavior from code and tests before acting. Do not assume roadmap phase gates or
audit text are current merely because they are written down.

## Archive Rule

`old_progress/` is historical and non-binding. It may contain completed gates,
obsolete restrictions, and foundation-first plans that no longer describe the
active project state. Historical documents must not override `AGENTS.md`, active
README guidance, the central-goal document, the active roadmap, `progress.md`,
`ARCHITECTURE_DEBT.md`, or executable code/tests.

## Biology Rule

Biology may be added only when the mechanism is explicitly implemented,
provenance-backed, maturity-labelled, covered by tests, and honest about
assumptions and limitations. Unsupported, invented, silently guessed, or falsely
validated biology is forbidden.

This is not permission for unrestricted biology expansion. It is the current
replacement for older blanket foundation-era bans.

## No-Shortcut Rules

- No PET-, cellulose-, enzyme-, fungus-, or mechanism-specific branches in generic/core modules.
- No silent fallback constants.
- No toy or synthetic data presented as scientific.
- No feature may be called generic without a materially different non-specific test case.
- No scientific logic hidden inside notebooks.
- No public API placeholders that appear complete.
- No unsupported biological state or output may be emitted.
- Unknown values must remain explicit or require an explicit exploratory opt-in.
- No scientific or numerical behavior should change in documentation-only guardrail tasks.

## Tests And Reporting

Add or update tests whenever a guardrail, behavior, public API, output schema, or
documented contract changes. Run the repository quality gates relevant to the
task, and report any command that could not run with the exact reason.

Every task report should state what changed, what did not change, tests added or
modified, commands run, command results, scientific behavior impact,
backward-compatibility impact, remaining ambiguities, risk level, and the
recommended next task.
