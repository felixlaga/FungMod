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

## Researcher-facing example coverage

The scoped reversible-product-inhibition target now has a researcher-facing
example notebook:

```text
notebooks/examples/12_reversible_product_inhibition_example.ipynb
```

The notebook uses public virtual-experiment APIs, compares inhibited and
uninhibited exploratory runs, and inspects `mechanism_summary.csv`,
configured metadata, limitations, and final degradation/product metrics. Its
example registry uses an explicit provenance-labelled exploratory `K_i`
fixture and does not supply validation data.

The configured-model workflow also includes a non-PET genericity benchmark:

```text
data/model_configs/toy_surface_dummy_non_pet_product_inhibition.yml
```

That fixture is `mode: toy` and `maturity: framework_benchmark`. It uses an
explicit artificial product-state `K_i` parameter only to verify that
`product_inhibition` runs through the generic configured path outside the
researcher-facing BIO-002 public example. It is not biological inhibition
evidence, validation data, calibration, toxicity, uptake, secretion, biomass,
physiology, or multi-product inhibition support.

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
- configured workflow tests include a non-PET toy surface benchmark that emits
  configured product-inhibition metadata and assumption records.
- registry-backed case-assembly tests show explicit template modifier records
  flow into configured outputs and `mechanism_summary.csv` without fallback
  inhibition constants.
- notebook/example tests show the researcher-facing virtual-experiment example
  executes through public APIs and exposes the active modifier in standard
  output tables.
