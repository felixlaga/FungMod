# BIO-003: Generic Mechanism Expansion Through Process Laws

Status: `partial/software-tested` for four bounded BIO-003 mechanism-family
targets.

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

## Additional provenance-backed targets

PR-58 adds two configured homogeneous enzyme-rate laws:

```text
competitive_inhibition
substrate_inhibition
```

Their machine-checkable proposals are:

```text
foundation_progress/proposals/BIO_003_COMPETITIVE_INHIBITION.yml
foundation_progress/proposals/BIO_003_SUBSTRATE_INHIBITION.yml
```

Both modifiers require an exact homogeneous Michaelis-Menten
(`homogeneous_michaelis_menten`) base process, an explicit substrate state and
`K_m` symbol that exactly match that base, a positive finite unit-compatible
`K_i`, a nonblank `primary_source`, and the explicit
`literature_backed_software_tested` maturity label.

Competitive inhibition uses
`v = Vmax*S / (Km*(1 + I/Ki) + S)` and additionally requires an explicit
nonnegative inhibitor state. Its primary law evidence is the experimental
kinetics study at `https://pubmed.ncbi.nlm.nih.gov/7985803/`.

Substrate inhibition uses the Haldane form
`v = Vmax*S / (Km + S + S^2/Ki)`. Its primary law evidence is the purified
beta-fructosidase study by Martel et al. (2010),
`https://doi.org/10.1016/j.biortech.2010.01.084`, which explicitly fits that
equation and reports substrate inhibition for two tested fructans.

These sources support the selected mathematical laws in their study systems.
They do not support the artificial benchmark parameters, establish
applicability to a production FungMod case, or constitute FungMod validation.
More than one mechanistic enzyme-inhibition modifier per process and
composition with the older generic product-inhibition factor fail closed
because no combined law has been implemented.

## Provenance-backed substrate transglycosylation

The fourth bounded target is:

```text
substrate_transglycosylation
```

Its machine-checkable proposal is:

```text
foundation_progress/proposals/BIO_003_SUBSTRATE_TRANSGLYCOSYLATION.yml
```

Two generic configured process branches share the retaining-glycosidase law:

```text
D   = Km_h + S + S^2/Km_t
r_h = E*kcat_h*S/D
r_t = E*kcat_t*(S^2/Km_t)/D
```

The hydrolysis branch must consume exactly one donor-substrate equivalent. The
substrate-transfer branch must consume exactly two because the second substrate
molecule is the acceptor. Explicit product maps own every product coefficient.
Missing provenance, a maturity other than
`literature_backed_software_tested`, invalid/nonfinite inputs, unsupported
modifier composition, and branch/map mismatch fail closed.

The selected law is supported by Kawai et al. (2004),
`https://doi.org/10.1016/j.carres.2004.09.019`, which identified a fungal
substrate-transglycosylation product and fitted the coupled kinetic scheme. The
installed example
`data/model_configs/phanerochaete_bgl1b_cellobiose_transglycosylation.yml`
uses the four reported recombinant BGL1B cellobiose estimates from Tsukada et
al. (2006), `https://doi.org/10.1007/s00253-006-0526-z`, including their
reported uncertainties.

The example's enzyme dose and time grid are exploratory scenario inputs. Its
three-glucose-unit transfer-product pool deliberately leaves linkage identity
unresolved and omits subsequent hydrolysis. It is purified recombinant-enzyme
kinetics, not whole-fungus growth, secretion, uptake, regulation, validation,
or a measured time course.

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
- competitive or substrate-inhibition claims outside their explicit PR-58
  configuration contracts;
- transfer to non-substrate acceptors, multiple product isomers, sequential
  transfer, or transfer-product re-hydrolysis;
- mixed, uncompetitive, irreversible, time-dependent, covalent, combined, or
  multi-product inhibition claims;
- validation or calibration claims without real observations;
- silent fallback inhibition constants.
- production applicability inferred from a law citation or artificial fixture.

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

The PR-58 competitive/substrate-inhibition slice is complete only when both new
proposals pass BIO readiness validation, both selected equations execute
through materially different artificial configured benchmarks, primary source
and maturity metadata are visible in outputs, and missing provenance,
nonpositive parameters, base-law mismatch, and unsupported composition fail
closed.

The substrate-transglycosylation slice is complete for its scoped software
contract when both branch equations and stoichiometric contributions are unit
tested, the proposal passes BIO readiness, the source-parameter example runs
from installed resources with conservation checks, and output metadata exposes
branch, equation, source, maturity, assumptions, and limitations. This does not
complete broad BIO-003 or establish empirical validation.
