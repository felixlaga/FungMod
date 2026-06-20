# BIO-003: Generic Mechanism Expansion Through Process Laws

Status: `selected/proposed` for the first BIO-003 mechanism-family target.

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
`ProductInhibitionModifier` with unit/provenance-aware behavior, but it is not
yet promoted into the configured or registry-backed virtual-experiment path as
a BIO-003 mechanism family.

## Required next implementation scope

The next implementation PR should:

- expose reversible product inhibition through configured model inputs or the
  registry-backed case assembly path;
- require an explicit product state and a positive, unit-compatible `K_i`;
- keep missing or unknown `K_i` explicit rather than guessing a fallback;
- write active modifier assumptions, parameters, provenance, and limitations
  into configured and/or virtual-experiment outputs;
- include at least two materially different non-specific tests, such as one
  homogeneous benchmark case and one chain/surface-compatible case.

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
- no scientific or numerical behavior changes are introduced by the selection
  PR itself.

