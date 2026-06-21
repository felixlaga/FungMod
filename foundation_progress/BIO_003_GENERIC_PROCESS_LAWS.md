# BIO-003: Generic Mechanism Expansion Through Process Laws

Status: `partial/software-tested` for the first BIO-003 mechanism-family
target.

BIO-003 should expand biology through reusable process laws and modifiers, not
case-specific fungus, substrate, enzyme, or experiment branches.

## Selected first target

The first selected BIO-003 target is:

```text
reversible_product_inhibition
```

The machine-checkable proposal is:

```text
foundation_progress/proposals/BIO_003_REVERSIBLE_PRODUCT_INHIBITION.yml
```

This target was selected because the repository already contains a generic
`ProductInhibitionModifier` with unit/provenance-aware behavior. It is now
available to configured process assembly as an explicit generic rate modifier,
and registry-backed case templates can expose it when explicit product-state
and `K_i` parameter records exist.

## Required next implementation scope

The next implementation PR after this registry-backed assembly slice should:

- add researcher-facing virtual-experiment examples or notebooks that use only
  public APIs;
- keep missing or unknown `K_i` explicit rather than guessing a fallback;
- preserve output visibility for active modifier assumptions, parameters,
  provenance, and limitations.

## What this does not permit

This selected target does not permit:

- organism-specific product inhibition branches;
- substrate-specific shortcuts;
- whole-fungus toxicity, uptake, secretion, biomass, or physiology claims;
- competitive, mixed, uncompetitive, or multi-product inhibition claims;
- validation or calibration claims without real observations;
- silent fallback inhibition constants.

## Completion signal for this scoped BIO-003 slice

This scoped slice can be marked complete only when:

- the proposal passes BIO readiness validation;
- active roadmap/status docs identify reversible product inhibition as the next
  target;
- tests ensure the selected mechanism remains generic and explicitly scoped;
- configured workflow tests show the mechanism scales rates only when explicit
  product-state and `K_i` inputs are provided.
- registry-backed case-assembly tests show explicit template modifier records
  flow into configured outputs and `mechanism_summary.csv` without fallback
  inhibition constants.
