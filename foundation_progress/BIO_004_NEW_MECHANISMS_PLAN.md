# BIO-004: Plan For Six New Mechanisms

Status update (2026-10-09): all six mechanisms now have explicit implementations,
checked law-form records, synthetic software tests and input routes. Proposals are
`software_tested`, not calibrated or empirically validated. The implementation
and its supported scope are documented in [the mechanism guide](../docs/bio004-mechanisms.md).
This plan was originally written against `main` at 4d08938; the stage descriptions
below retain the design intent, while code, tests and the implementation guide
record the delivered scope. M5 uses a sourced finite-chain population law instead
of inventing the proposed aggregate end-exhaustion term. M6 uses the complete
sourced ternary law and refuses unsourced oxidative fragment allocation.

The six mechanisms are the ones FungMod's documentation lists as absent:

| ID | Mechanism | Lifts today's refusal |
| --- | --- | --- |
| M1 | Enzyme adsorption onto solids, with a binding capacity and depletion of free enzyme | `binding_capacity`, `adsorption_constant` and related quantities in user data |
| M2 | Release of soluble sugar from a solid and its uptake by a growing culture | "no uptake law for a released soluble pool" |
| M3 | Dissolved-oxygen balance: transfer from the gas phase and consumption by the culture | "no oxygen dynamics"; `oxygen_monod` refused in user data |
| M4 | pH dynamics: a proton balance through a buffer capacity | "no pH dynamics or buffering" |
| M5 | Synergy between endo- and exo-acting cellulases through the substrate's structure | "no synergy" |
| M6 | H2O2-driven oxidative cleavage by lytic polysaccharide monooxygenases (LPMOs) | "AA9 maps to an LPMO class without a record" |

The owner's request was LPMOs, synergy, adsorption from user data, sugar
uptake, and pH or oxygen dynamics. pH and oxygen are planned separately (M3,
M4) because they share infrastructure but not mechanisms.

Proposals, one per mechanism, all `validation_status: software_tested`:

| Mechanism | Proposal |
| --- | --- |
| M1 | `proposals/BIO_004_ADSORBED_ENZYME_HYDROLYSIS.yml` |
| M2 | `proposals/BIO_004_SOLUBLE_SUBSTRATE_UPTAKE.yml` |
| M3 | `proposals/BIO_004_DISSOLVED_OXYGEN_BALANCE.yml` |
| M4 | `proposals/BIO_004_PROTON_BALANCE_PH.yml` |
| M5 | `proposals/BIO_004_CHAIN_END_SYNERGY.yml` |
| M6 | `proposals/BIO_004_PEROXIDE_DRIVEN_OXIDATIVE_CLEAVAGE.yml` |

Each proposal also lists its candidate sources with a verification status.

## 1. The rule this plan follows

`AGENTS.md` allows biology only when the mechanism is explicitly implemented,
provenance-backed, maturity-labelled, tested and honest about its limits.
For each mechanism that means:

1. **The law's form comes from a source, not from us.**
   - A source supports a law form: a paper that states and fits the equation,
     or a textbook that derives it.
   - The plan names candidate sources below.
   - Before any code is written, the chosen source is taken in under the
     sourcing gate (section 3). The equations are copied with page and
     equation numbers, and the extraction is frozen.
2. **A law form is not a parameter value.** A paper that supports
   Michaelis-Menten kinetics in H2O2 for one enzyme on one substrate supports
   the form, not FungMod using its constants for another enzyme. Constants
   enter only as records with their own evidence type (`measured`,
   `literature`, `design`, `estimate`, `fitted`). An `estimate` keeps a case
   exploratory, as today.
3. **No tuning factors.**
   - A "synergy factor", an "LPMO boost" or an "efficiency" multiplier that
     no source defines is forbidden.
   - Synergy must emerge from the mechanism (M5), never be imposed.
4. **Every new law reduces to the existing one in its limit.** This is
   pinned by tests, for example:
   - adsorption far from saturation with a large capacity gives the current
     apparent law;
   - an infinite buffer capacity gives today's static pH;
   - oxygen held at saturation gives today's oxygen-free closure.
5. **Existing datasets and drafts stay byte-identical.** Every earlier user
   dataset, registry case and draft keeps its records, configs and outputs.
   The pinned digests already in the test suite extend to each new step.
6. **Materially different test cases.** Each law is tested on two unrelated
   synthetic systems, labelled as synthetic, before any real data. One
   example is cellulose and chitin for M6, mirroring the published LPMO
   kinetics on chitin.
7. **Maturity ladder per proposal.**
   - `proposed` (now);
   - `source_supported`: the law-form sources are taken in;
   - `software_tested`: the law is implemented, tested and documented;
   - `calibrated`: constants fitted to a deposited dataset under a frozen
     plan;
   - `validated`: a held-out prediction made under a frozen plan.
   This plan aims at `software_tested` for all six. It names the datasets
   that could carry each one further.

## 2. Where FungMod stands (verified against the code)

| Area | Exists | Missing |
| --- | --- | --- |
| Adsorption | Equilibrium Langmuir coverage, `kinetics/langmuir.py`. Surface law `r = k_s·θ·A`, `processes/surface.py` (`SurfaceCatalysisProcess`, no analytic Jacobian). Template-driven surface assembler (SURFACE-001, `screening/case_builder.py`). | Binding capacity Γmax; a bound-enzyme state; depletion of free enzyme by binding; competition for sites; sourced adsorption records (the registry holds only exploratory priors). The user-data route refuses every adsorption quantity (`api/user_data.py`, `_SURFACE_LAW_QUANTITIES`, `_SURFACE_LAW_SUBSTRATE_COLUMNS`). |
| Sugar uptake | Generic Pirt/Monod closure (`resource_limited_growth`, `resource_limited_maintenance`, `costed_secretion`, `dilution_exchange`, `gas_transfer` in `processes/culture.py`, all with analytic Jacobians). Opt-in classes `ResourceLimitedCulture` and `DegradingCulture`; the latter already has a soluble pool taken up through the Pirt capacity. Research-only model `M2_soluble_product_pool` (`research/gelain_criticism.py`). | Any registry template or user-data route that binds the closure. The `culture_physiology` composer cannot pass `stoichiometry`: it is not in `_PROCESS_TEMPLATE_FIELDS`. A culture template with a released pool. Catabolite repression (none anywhere). |
| Oxygen | `oxygen_monod` modifier (reads the static environment). `gas_transfer` process `k_La·(c_sat − c)`. Oxidant state in the closure. `OxygenDemand` stoichiometry helper. | A dissolved-oxygen state reachable from templates or user data; oxygen solubility (c_sat is caller-supplied); an oxygen yield and maintenance demand bound from records. `EnvironmentGrid` oxygen is a label only. |
| pH | Gaussian and cardinal pH modifiers and the pH-ionization law, all read once from the static environment and folded into constants. Elemental and charge conservation in `chemistry/macrochemistry.py`. | A proton balance, buffer capacity or speciation; any modifier that reads pH from a state; signed balance states (the compiled core evaluates rates at max(state, 0), `solvers/compiled.py`). |
| Synergy | Independent processes whose rates add on shared pools (`screening/enzyme_network.py`). Competitive product inhibition through a `ki` row, so relief of cellobiose inhibition by beta-glucosidase is already representable. | Any substrate-structure state (chain ends, attack sites); an endoglucanase class (GH5/12/45 map to `cellulase_generic`); a multi-reactant law in the chain assembler. "No synergy" is stated in about twenty places. |
| LPMO | The CAZy map sends AA9 to `lytic_polysaccharide_monooxygenase` (`data_registry/cazyme_families/cazyme_family_map.yml`). | The enzyme-class record, so AA9 lands in "classes without a model". AA10, AA11 and AA13–AA16 are unmapped. No H2O2, reductant or oxygen co-substrate. No oxidative bond or product class. No law, compatibility record or parameter. |

Tests that currently assert absence, and must be updated deliberately as each
mechanism lands:
- `tests/test_registry_polysaccharide_classes.py`
- `tests/test_user_data_solid_substrates.py`
- `tests/test_capability_resolution.py`
- `tests/test_fetch_by_name.py`
- `tests/test_user_data_v2.py` (the `oxygen_monod` refusal)

The same holds for the docs sentences listed in section 12.

## 3. The sourcing gate (step S0 of every mechanism)

No mechanism code is written before its S0 is complete.

**S0.1 Choose the law-form source.**
- Pick one primary source per law from the candidates in sections 5–10.
- The source must state the equation, ideally fitted to data. A review alone
  is not enough; it may support the choice between forms.

**S0.2 Take it in** as a mechanism-source record (foundation F1):
- citation and DOI, both resolved, with the date checked;
- licence;
- what the source supports: the law form, constants for its own system, or
  data;
- the equations copied verbatim with equation and page numbers;
- the study system: enzyme family, substrate, conditions;
- the stated assumptions and validity range;
- any table or figure to digitise, with the SHA-256 of the file used.

**S0.3 Record what the source does not support.** This is the proposal's
`not_in_scope` and `limitations`, and it carries into the template
limitations a user sees.

**S0.4 Promote the proposal** from `proposed` to `source_supported`, in its
own small PR. The PR changes only the proposal, the intake record and the
ledger.

Sources whose bibliographic details were checked on 2026-10-09 are marked
"checked" in section 14. Sources cited from memory are marked "re-check".
Those that could not be confirmed are marked "unverified" and may not be
used until confirmed.

## 4. Shared foundations

These are software changes with no biology of their own. Each is one PR with
tests.

### F1 Mechanism-source records

- `data/mechanism_sources/<source_id>/source.yml` plus any extracted tables,
  with a loader and schema (`fungal_model.provenance`) mirroring the
  data-intake manifest:
  - URL, DOI, licence, retrieval date, SHA-256 of any downloaded file;
  - `supports: [law_form | constants | data]`;
  - `equations`, `assumptions`, `validity`.
- A proposal at `source_supported` or above must reference at least one
  record whose `supports` includes `law_form`. A test enforces this.

### F2 Environment read from a state

- **Why:** pH (M4) and oxygen (M3) must be able to drive the existing laws
  (cardinal pH, Gaussian pH, pH ionization, `oxygen_monod`) from a state
  instead of the static environment.
- **Pattern to reuse:** `ProductInhibitionModifier.compile_activity` already
  reads a state slot (`modifiers/product_inhibition.py`).
- **Design:**
  - Each environment-reading modifier gets an optional `state_source` (the
    state ID that carries the value).
  - Without it, behaviour is unchanged: the constant is folded once,
    byte-identical.
  - With it, the activity kernel reads the state and gains an analytic
    derivative column.
- **Not affected:** temperature stays static. No temperature dynamics are
  planned.
- **Tests:**
  - With `state_source` held at the static value, results equal the
    static-environment run to 1e-12.
  - The Jacobian column matches centred differences.

### F3 Signed and bounded balance states

- **Why:** the compiled core projects negative states to zero before
  evaluating a kernel. A proton-excess state can be legitimately negative,
  and pH is bounded.
- **Design:** add a declared `domain` per state (`non_negative`, the default,
  or `signed`). Only `signed` states skip the projection.
- **Tests:** existing models are bitwise unchanged; a signed state integrates
  through zero.

### F4 Closure stoichiometry through the composer

- Add `stoichiometry` and `extent_state` to `_PROCESS_TEMPLATE_FIELDS` in
  `screening/culture_physiology.py`.
- Build the stoichiometry from records: a yield record becomes a
  coefficient, exactly as NETWORK-002's unit-bearing yield does.
- The closure processes (`resource_limited_growth` and friends) become
  bindable from templates.
- Test: a template-bound closure reproduces `ResourceLimitedCulture` on its
  example to 1e-10.

### F5 New state roles and conservation checks

- **New roles in `registry/records.py`:**
  - `bound_enzyme`
  - `chain_end`
  - `dissolved_oxygen`
  - `peroxide`
  - `proton_excess` or `ph`
  - `soluble_product`
- **Result tables and the closure ledger:**
  - total enzyme = free + bound, for M1 and M6;
  - an oxygen ledger: transferred minus consumed, for M3;
  - a proton ledger: added minus produced, for M4.
- Each ledger is a pinned conservation check like today's closure checks.

### F6 Leave-one-out counterfactual runs (for M5)

- A generic option on a network run re-simulates the case once with each
  member class removed.
- It reports the degree of synergy: product formed by the full mixture
  divided by the sum formed by each member alone. The definition is to be
  confirmed against Kostylev & Wilson 2012 at S0.
- This is software, not biology. Today it reports synergy only from what the
  network already represents: product links and relief of product
  inhibition. That is honest and useful before M5 exists.

## 5. M1 — Enzyme adsorption onto solids

**Goal.** A laboratory states, for its own enzyme on its own solid:
- the binding capacity Γmax (enzyme mass per substrate mass);
- the association constant K, or the dissociation constant Kd;
- a rate constant for bound enzyme.

FungMod then partitions the enzyme into free and bound fractions as the solid
is consumed, so that rates follow the bound enzyme and saturate at high
loading.

**Mechanism (candidate form, to be confirmed at S0).** Quasi-steady Langmuir
partition with depletion of free enzyme, and a hydrolysis rate proportional to
bound enzyme:

```text
E_b = Γmax · S · K · E_f / (1 + K · E_f)        (Langmuir, per mass of solid)
E_T = E_f + E_b                                 (enzyme conservation)
→ E_f from the positive root of the quadratic
  K·E_f² + (1 + K·Γmax·S − K·E_T)·E_f − E_T = 0
r = k_b · E_b · (S/S0)^n                         (optional existing reactivity term)
```

- A dynamic form, `dE_b/dt = k_on·E_f·(Γmax·S − E_b) − k_off·E_b`, is a later
  step (M1b). It is needed only when adsorption is not fast compared with
  hydrolysis.
- One candidate source reports adsorption reaching half its maximum within 3
  minutes and completing in 60–90 minutes. If S0 confirms this, it supports
  the quasi-steady form for runs of hours.

**States and parameters**

| Symbol | Meaning | Units | Supplied by |
| --- | --- | --- | --- |
| S | solid substrate | g/L dry mass | existing `substrates.csv` |
| E_T | total enzyme | mg/L protein, µmol/L or assay units/L | existing enzyme rows |
| E_b | bound enzyme (output; a state in M1b) | as E_T | computed |
| Γmax | binding capacity | enzyme per g solid | new `binding_capacity` row |
| K or Kd | association or dissociation constant | 1/(enzyme concentration) or enzyme concentration | new row; exactly one of the two |
| k_b | rate constant per bound enzyme | g solid per (enzyme amount · time) | new `bound_rate_constant` row |

**Sources** (section 14):
- *Law form:*
  - Kadam et al. 2004: Langmuir adsorption inside a saccharification model.
    The form is already cited in the JOSS paper.
  - Medve et al. 1998: adsorption isotherms and time scale on
    microcrystalline cellulose; a linear relation between sugar production
    and adsorbed exo-cellulase.
- *Review for the choice of form:* Bansal et al. 2009 (unverified, confirm
  first).
- *Constants:* user data only. Records keep their evidence type.

**Design decisions**

1. **A new process type, `adsorbed_enzyme_hydrolysis`.** It does not change
   `surface_catalysis`. The existing surface law uses accessible area A and
   coverage θ, with no capacity. Its cases and drafts stay byte-identical.
2. **The quadratic is solved in closed form inside the kernel.** The analytic
   Jacobian comes by implicit differentiation, so there is no inner
   iteration.
3. **Accessible surface area and crystallinity stay refused.** M1 has no law
   that reads them, so FungMod still does not store a value that no law uses.

**Implementation steps (PRs)**

1. **M1.1** Kinetics function and process (`compile_rate`,
   `compile_jacobian`); factory; toy config
   `data/model_configs/toy_adsorbed_enzyme_hydrolysis.yml`.
   - Update the factory-set and compiled-kernel guardrail tests.
   - Add mechanism-summary rows in `api/result_tables.py` and
     `workflows/configured_outputs.py`.
   - SBML: export it, or refuse it explicitly.
2. **M1.2** Registry template family and parameter roles; the compatibility
   record; the F5 ledger (free + bound).
3. **M1.3** User data:
   - Lift the refusal of `binding_capacity`, `adsorption_constant` and
     `adsorption_dissociation_constant` for solid substrates only.
   - Add `bound_rate_constant`, with pint unit checks per case.
   - Add a `check-data` table, a `run` output column for bound enzyme, and
     docs with real output.
   - Keep the refusal of area, crystallinity and particle size, with the
     message updated to name M1.
4. **M1.4 (optional)** Dynamic adsorption (M1b) with `k_on` and `k_off`
   records.

**Tests**
- **Exact quadratic:** E_f + E_b = E_T at every output time (rtol 1e-12), for
  dissolved enzyme in molar, mass and assay units.
- **Limits:**
  - K·E_f ≪ 1 with a large Γmax gives `r = k_b·Γmax·K·S·E_T`, matching the
    current apparent first-order behaviour.
  - Saturation gives `r → k_b·Γmax·S`, independent of E_T.
- **Jacobian:** against centred differences.
- **Two materially different synthetic cases:** a polysaccharide film with a
  low capacity, and a chitin-like solid with a high capacity.
- **Fail-closed:**
  - K and Kd both given, or neither;
  - Γmax without a mass basis;
  - a dissolved substrate;
  - area or crystallinity columns still refused.
- **Byte identity:** every earlier fixture, registry case and draft.

**Done means `software_tested`.** To go further, use adsorption isotherms
digitised from a source such as Medve et al. 1998, through the existing
digitiser and source intake, under a frozen plan.

**Risks**
- Lignin binding, i.e. a second, non-productive site class, is common in real
  lignocellulose. It is out of scope until sourced; the limitation must say
  so.
- Enzyme units: Γmax in mg/g and E_T in assay units/L cannot be combined
  without a stated conversion. Refuse rather than convert.

## 6. M2 — Soluble sugar released and taken up by a culture

**Goal.** A culture where the solid is hydrolysed into a soluble sugar pool,
the fungus takes up that sugar and grows on it, and a maintenance demand is
paid.

Unlike today's culture template, consumed substrate goes to the sugar pool,
not straight into biomass. The sugar becomes an output that can be compared
with measured reducing sugar or glucose.

**Mechanism (textbook forms, confirm at S0)**

```text
hydrolysis:   P → y_GP · G                        (existing consumption laws; y_GP stated, never derived from molar mass)
uptake:       q_G = q_max · G/(K_G + G)            (Monod 1949)
growth:       dX/dt = Y · max(q_G − m, 0) · X      (Pirt 1965 maintenance)
maintenance:  min(q_G, m) · X  → respired-carbon ledger
sugar:        dG/dt = y_GP · r_h − q_G · X
```

This is the existing `ResourceLimitedCulture` closure:

```text
capacity = q·S/(K_S+S)·O/(K_O+O)
growth   = Y·max(capacity − m, 0)·N/(K_N+N)
```

It is bound through F4. Nitrogen and oxygen become optional. When they are
absent, the factor is 1 and a stated limitation says nitrogen and oxygen are
not limiting. M3 adds oxygen later.

**Catabolite repression (M2b) is gated, not planned for implementation.**
- Ilmén et al. 1997 support the phenomenon qualitatively: no cellulase
  expression on glucose, and derepression after glucose is exhausted.
- They give no rate law. No quantitative repression law with fitted
  constants has been confirmed yet.
- Velkovska et al. 1997 is a candidate but unverified.
- M2b starts only after S0 finds a source that states and fits a repression
  term on induced synthesis. Until then the template says plainly that
  induction is not repressed by sugar.

**States and parameters**

| Symbol | Meaning | Units | Supplied by |
| --- | --- | --- | --- |
| G | soluble sugar pool | g/L or mmol/L | new state |
| y_GP | sugar released per solid consumed | g/g or mmol/g (stated; pint-checked) | `substrates.csv` product yield, as in NETWORK-002 |
| q_max | maximum specific uptake | sugar per (g biomass · h) | new `culture.csv` row |
| K_G | uptake half-saturation | as G | new row |
| Y | biomass yield on sugar | g biomass per sugar | existing culture yield, now on sugar |
| m | maintenance demand | sugar per (g biomass · h) | new row (may be 0 if stated) |

**Sources**
- *Law form:* Monod 1949; Pirt 1965.
- *Structure:* FungMod's own `DegradingCulture` (opt-in, tested) and the
  research model `M2_soluble_product_pool`.
- *Honest reading of M2_soluble_product_pool:* it passed the R1 holdout screen
  but its constants were not identified (`docs/gelain-model-criticism.md`).
  It is a structural precedent, not evidence for the constants.
- *Repression (M2b only):* Ilmén et al. 1997 (phenomenon); a quantitative
  source still to be found.

**Implementation steps**
1. **M2.1** F4, then a closure variant with optional nutrient and oxidant
   states. Absent pools enter as factor 1 with a stated assumption. Add
   analytic Jacobians.
2. **M2.2** A culture template family with a released pool:
   - hydrolysis by every consuming pool → sugar;
   - uptake, growth and maintenance by the closure;
   - induced synthesis and loss unchanged;
   - a closure ledger spanning the dry-mass and sugar bases through y_GP.
3. **M2.3** User data:
   - `culture.csv` gains `uptake_capacity`, `uptake_half_saturation` and
     `maintenance_demand`, and `substrates.csv` the product yield.
   - Lift the CULTURE-002 refusal of released pools.
   - Allow a culture in an enzyme network when the released pools are taken
     up. Today this is refused because the substrate would be counted twice.
   - Add `run` outputs for the sugar pool and the respired-carbon ledger, and
     compare and fit on sugar time courses.
4. **M2.4 (gated)** Catabolite repression, after S0.

**Tests**
- **Conservation at every output time** (rtol 1e-9):
  `S + G/y_GP + (X − X0)/(Y·y_GP) + ledger = S0 + G0/y_GP`, generalised to
  several pools.
- **Limits:**
  - With K_G → 0 and q_max large, uptake is immediate, which reproduces
    today's one-step culture (Y applied to consumed solid) to a stated
    tolerance.
  - m = 0 removes maintenance exactly.
- **Two different cultures:** a cellulose-like solid with an
  assay-unit enzyme, and a starch-like solid with a protein-mass enzyme.
- **Fail-closed:**
  - an uptake row without a stated product yield;
  - a yield without evidence;
  - repression rows before M2b.
- **Byte identity** of earlier cultures, including the shipped culture case.

**Done means `software_tested`.** To go further, use culture data with
soluble-sugar time courses. The transfer survey
(`foundation_progress/TRANSFER_DATASET_SURVEY_2026-10-05.md`) is the
starting point.

**Risks**
- Several sugars (glucose, cellobiose, xylose) with preferential uptake need
  a multi-substrate law. That is out of scope until sourced; one pooled
  sugar comes first, stated as such.

## 7. M3 — Dissolved-oxygen balance

Implementation note: the current proposal and `docs/bio004-uptake-oxygen.md`
supersede the candidate notation below. Maintenance is already a sugar/time
flux, so its oxygen coefficient is oxygen per sugar amount (no second biomass
or time multiplier). Saturation is explicitly supplied; no solubility formula
is inferred. The original candidate equations below are historical design
notes, not executable specifications.

**Goal.** Dissolved oxygen as a state that falls when the culture respires
and is resupplied through gas transfer. Growth slows when oxygen limits it.
Any rate law with an oxygen response can read the state through F2.

**Mechanism (confirm at S0)**

```text
dO/dt = kLa · (O* − O) − (growth extent · ν_O,growth + maintenance extent · ν_O,maint) · X
growth limited by O/(K_O + O)                      (already in the closure)
O* = c_sat(T, salinity, pressure)                  (solubility function, or a stated value)
```

The two terms are existing processes: `gas_transfer` and the closure's
oxidant column. The oxygen stoichiometries ν_O come from records (the oxygen
demand per unit extent), never from a hidden constant.

**Parameters**
- `kla` (1/h), measured.
- `oxygen_saturation` (mmol/L), stated or computed from temperature by the
  Benson & Krause 1984 freshwater equation. That equation is valid at 0–40 °C
  and the validity range is enforced.
- `oxygen_yield` and `oxygen_maintenance` (mmol O2 per g biomass, and per
  g·h).
- `oxygen_half_saturation`.
- Initial dissolved oxygen.

**Sources**
- *Law form:* Garcia-Ochoa & Gomez 2009 (transfer rate `kLa(C* − C)` against
  uptake rate); Pirt 1965 for maintenance.
- *Solubility:* Benson & Krause 1984.
- *kLa:* only a stated measurement. Correlations for kLa (for example van't
  Riet 1979, re-check) are not planned. They would be exploratory estimates
  at best, and only after S0.

**Implementation steps**
1. **M3.1** F2 for `oxygen_monod`, so it reads the dissolved-oxygen state.
   Add the solubility function with its validity range and tests against the
   source's tabulated values, which are taken in at S0.
2. **M3.2** Culture template with oxygen: the closure's oxidant becomes the
   dissolved-oxygen state, plus a `gas_transfer` process. Add the F5 oxygen
   ledger.
3. **M3.3** User data:
   - an `aeration.csv` table: kLa, saturation or temperature-derived
     saturation, initial dissolved oxygen, each with evidence;
   - oxygen stoichiometry rows in `culture.csv`;
   - lift the `oxygen_monod` refusal where a dissolved-oxygen state exists.
   - `EnvironmentGrid` oxygen stays a label for cases without the state; the
     docs say so.

**Tests**
- **Steady states:**
  - with no culture, O → O* exponentially at rate kLa, analytically;
  - with constant uptake, O_ss = O* − OUR/kLa.
- **Limits:** kLa → ∞ reproduces the oxygen-unlimited closure.
- **Ledger:** transferred = consumed + accumulated.
- **Solubility:** against the source's tabulated values.
- **Two cultures:** one oxygen-limited, one not.
- **Fail-closed:**
  - a temperature outside the solubility range;
  - kLa without units of 1/time;
  - an oxygen modifier without a state or a static value.

**Done means `software_tested`.** To go further, use any deposited culture
with dissolved-oxygen traces. The registry's culture case records oxygen as
`unknown`, so new data are needed.

## 8. M4 — pH dynamics

**Goal.** pH as a state that moves as the culture produces or consumes
protons, damped by the medium's buffer capacity. pH-dependent laws read it
through F2. Optionally, a pH-stat mode holds pH and reports the titrant
consumed, which is a measurable output.

**Mechanism (confirm at S0)**

```text
d(pH)/dt = −(1/β(pH)) · Σ_j ν_H,j · r_j             (buffer value β = dB/dpH, Van Slyke 1922)
β(pH) = 2.303 · ( [H+] + Kw/[H+] + Σ_i C_i · Ka_i · [H+] / (Ka_i + [H+])² )   (declared buffers i)
pH-stat:  pH constant; titrant rate = Σ_j ν_H,j · r_j  (reported, signed)
```

- ν_H,j is the protons released per unit extent of process j. It is a
  stated record per process: for example, protons per gram of biomass when
  ammonium is the nitrogen source.
- The repository does not infer ν_H from a nitrogen source, because no
  nitrogen uptake law exists in user data. The record says how it was
  measured: titrant consumption, or a stated stoichiometry with its source.

**Parameters**
- Buffers: species, total concentration and pKa, with temperature stated.
  The pKa is not corrected for temperature in this plan.
- ν_H per process.
- Initial pH.
- Optional pH-stat set point and titrant identity.

**Sources**
- *Law form:* Van Slyke 1922 (buffer value).
- *Coupling of proton release with ammonium uptake:* a 1984 study in
  *Microbiology* on a citric-acid-producing fungus, as a candidate (details
  unverified; confirm at S0). It supports the coupling qualitatively, not a
  value for any other organism.
- Constants come from user records.

**Design decisions**
1. **Buffer-capacity ODE (chosen) versus full charge-balance speciation
   (rejected for now).** Full speciation is a differential-algebraic system
   with ionic strength and activity coefficients. FungMod's
   `nonideal_thermodynamics` holds only constant activity coefficients, and
   the docs say state-dependent electrolyte models are unsupported. The
   buffer-capacity form is exact for declared weak-acid buffers in dilute
   solution, and its limitation says so.
2. **The state is pH itself**, bounded by the F3 domain at 0–14, rather than
   a signed proton excess. If S0 prefers proton excess, F3 supports that
   too.
3. **pH-stat is an option on the same balance**, not a separate law.

**Implementation steps**
1. **M4.1** F3 (signed and bounded states); F2 for the pH modifiers and the
   pH-ionization law (`state_source`).
2. **M4.2** The proton-balance process and the β(pH) function, with an
   analytic Jacobian; toy config; F5 proton ledger.
3. **M4.3** Templates and user data:
   - a `medium.csv` table (buffers, initial pH, pH-stat set point);
   - ν_H rows per process;
   - pH as an output curve;
   - titrant consumption as an output in pH-stat mode.
   - `conditions.csv` pH remains the static value for cases without the
     state.

**Tests**
- **Limits:**
  - β → ∞ (large buffer) leaves pH constant to 1e-12;
  - zero proton production keeps pH constant;
  - a single buffer matches the analytic titration curve of a weak acid.
- **pH-stat:** titrant equals the integrated proton production.
- **Coupling:** a pH-ionization enzyme slows as pH leaves its optimum, and
  the rate at each time equals the law evaluated at the state's pH.
- **Two systems:** an acidifying culture, and an alkalising process with a
  different buffer.
- **Fail-closed:**
  - pH leaving the domain of a pH law;
  - a buffer without pKa;
  - ν_H without evidence;
  - a pH law driven by both a static value and a state.

**Done means `software_tested`.** To go further, use cultures with pH traces
or titrant logs. The registry culture was pH-controlled with NH4OH and
H2SO4; if titrant data were deposited, pH-stat mode is the matching model.

## 9. M5 — Synergy between cellulases through the substrate's structure

**Goal.** An endo-acting enzyme and an exo-acting enzyme together degrade a
solid faster than the sum of each alone. This must come from a mechanism the
sources describe, with a degree of synergy reported as an output (F6).

**What the sources say, and why this is the hardest mechanism.**
- Jalak et al. 2012 report two synergy mechanisms acting in parallel:
  - the conventional one, where endo-cutting creates new chain ends for
    exo-acting enzymes, matters mainly at high enzyme-to-substrate ratios;
  - the other, where endo-acting enzymes prevent exo-acting enzymes from
    stalling, operates generally.
- A chain-end-only model would therefore represent one of the two, and its
  limitation must say which.
- Levine et al. 2010 give a mechanistic model with explicit surface and
  chain-structure states. Zhang & Lynd 2004 review aggregated chain-end
  frameworks.

**Candidate forms, to be chosen at S0, not designed here.**
- **(a) Aggregated chain-end model.**
  - A state N (accessible chain ends per volume).
  - The endo enzyme creates ends: `dN/dt = ν_ends · r_endo`.
  - The exo enzyme's rate follows N: `r_exo = k · E_exo · N/(K_N + N)`.
  - Chain ends are consumed as chains are exhausted, by a rule the source
    must state.
- **(b) Stalling model.**
  - Bound exo enzyme exists as active and stalled pools.
  - The endo enzyme releases stalled enzyme at a rate proportional to its
    own activity, following the source's equations.
- **(c) An explicit chain-length distribution,** as in Levine 2010. This is
  the most faithful and the most expensive: many states and many constants.

**Recommendation: (a) first, then (b) as a second law in the same family,**
each with its own source. (c) only if a dataset justifies it. S0 must extract
the exact equations of the chosen source. In particular, the rule for chain
ends consumed per exo-cleavage and the ends created per endo-cut must come
from the source, not from us.

**Already possible, documented as part of M5:**
- Beta-glucosidase relieving product inhibition of the cellobiose-producing
  step works today, through a network plus a competitive `ki`.
- F6 will report its degree of synergy. This is synergy through the soluble
  pool, not the solid's structure, and the docs must keep the two apart.

**States and parameters** (form (a); the final list follows the source)
- N, chain ends (mol/L).
- ν_ends: ends per endo-cut.
- k_exo and K_N for exo action on ends.
- The endo enzyme's own constants.
- With M1, rates use bound enzyme.

**Implementation steps**
1. **M5.0** F6 (degree of synergy), useful immediately.
2. **M5.1** An `endoglucanase` enzyme-class record, with GH5/12/45 mapped to
   it in the CAZy map.
   - Keep `cellulase_generic` for pooled activity.
   - Update the tests that assert GH5 → `cellulase_generic`.
3. **M5.2** Form (a): kinetics, process, factory, the F5 `chain_end` role, a
   template family with endo and exo members, user-data rows for ν_ends,
   k_exo and K_N, and an initial chain-end content measured or stated.
4. **M5.3** Form (b), after its own S0.

**Tests**
- **Emergence:** with both enzymes, the degree of synergy is above 1. It
  tends to 1 when chain ends are not limiting (large initial N). It is
  exactly 1 when the endo enzyme is absent or ν_ends = 0.
- **Exo alone** with fixed N reduces to Michaelis-Menten in N.
- **Mass balance:** solid lost equals soluble product in substrate
  equivalents.
- **Two systems:** cellulose-like and xylan-like, labelled synthetic.
- **Fail-closed:**
  - an exo member without a chain-end state;
  - ν_ends without a source;
  - a synergy multiplier anywhere (a guardrail test greps for
    "synergy_factor").

**Done means `software_tested`** for form (a). To go further, use time
courses of exo-acting enzyme with and without endo-acting enzyme on the same
substrate, of the kind reported by Jalak et al. 2012 or Medve et al. 1998,
digitised under a frozen plan.

## 10. M6 — LPMOs: H2O2-driven oxidative cleavage

**Goal.** An LPMO cleaves a polysaccharide solid oxidatively, using H2O2 as
co-substrate.
- **Supply:** H2O2 is fed or present at a stated level.
- **Inactivation:** the enzyme is inactivated by H2O2 when not productively
  engaged.
- **Synergy:** oxidative cuts can feed M5's chain ends, so LPMO boosts
  hydrolase action through the mechanism, not a multiplier.

**Mechanism (candidate, confirm at S0)**

```text
r_ox  = kcat · E_L,eng · H/(K_mH + H)                 (Michaelis-Menten in H2O2; LPMO engaged on substrate)
dH/dt = F_H − r_ox − k_dH · H                         (feed; 1 H2O2 per oxidative cut; stated non-productive decay)
dE_L/dt = −k_in · E_L,free · H                        (second-order inactivation by H2O2)
products: oxidized oligosaccharides (C1 or C4), with a stated yield; optional ν_ends · r_ox into N (M5)
```

- E_L,eng: either bound LPMO from M1, or, without M1, the stated assumption
  that the LPMO is saturated with substrate. This is an explicit choice
  shown in the limitations.
- Reductant: the enzyme is assumed already primed. Bissaro et al. 2017
  report that the reductant is consumed in priming rather than
  stoichiometrically when H2O2 is supplied. In situ H2O2 generation from
  reductant and O2 is out of scope (M6b) until sourced. It would couple to
  M3.

**Parameters**
- kcat (1/s);
- K_mH (µM);
- k_in (1/(µM·s));
- feed F_H (µM/h) or an initial H;
- k_dH (1/h);
- product yield and oxidation type;
- LPMO concentration.

**Sources**
- *H2O2 as co-substrate, the law form and inactivation:*
  - Bissaro et al. 2017;
  - Kuusk et al. 2018: Michaelis-Menten in H2O2, kcat and kcat/Km for chitin
    oxidation, and a second-order inactivation constant about three orders of
    magnitude below catalysis;
  - Kont et al. 2020: kcat/Km(H2O2) of 10^5–10^6 /M/s for cellulose-active
    LPMOs of several families.
- *Effect of a controlled H2O2 feed on saccharification with a hydrolase
  cocktail:* Müller et al. 2018 (feeds of about 90–600 µM/h); a candidate
  calibration dataset.
- *Enzyme family and existence:*
  - Vaaje-Kolstad et al. 2010 (oxidative boosting);
  - Quinlan et al. 2011 (cellulose-active copper enzyme);
  - Levasseur et al. 2013 (CAZy auxiliary-activity classes).
- These support the form for the studied enzymes and substrates. Constants
  for another LPMO are user records.

**Registry and resolution changes**
- An enzyme-class record `lytic_polysaccharide_monooxygenase`:
  - an oxidative process compatibility;
  - EC numbers for the C1- and C4-oxidising cellulose LPMOs, chitin LPMO and
    starch LPMO, confirmed at S0. The candidates are 1.14.99.54, 1.14.99.56,
    1.14.99.53 and 1.14.99.55.
  - This moves AA9 from "classes without a model" to modellable, and changes
    the tests listed in section 2.
- CAZy map: AA10, AA11 and AA13–AA16, each mapped only where S0 confirms the
  family's substrate class.
- **Bond class and products.** Do not invent a new bond class. Oxidative
  cleavage acts on the existing beta-1,4 glycosidic bond, and the
  compatibility record states the oxidative process. Oxidised products are a
  new soluble product class, or a stated yield into the existing soluble
  pools, marked oxidised.

**Implementation steps**
1. **M6.1** Kinetics, process, factory and toy config (H2O2 state, feed,
   decay, inactivation); the F5 `peroxide` role; ledgers for H2O2 and
   enzyme.
2. **M6.2** Registry: class record, compatibility, template family,
   CAZy-map entries, and updates to the tests that assert LPMO is absent.
3. **M6.3** User data:
   - `kinetics.csv` quantities for kcat, K_mH and k_in on an LPMO class;
   - an H2O2 feed in a new `feeds.csv`;
   - a product yield;
   - network membership, so LPMO and hydrolases act together.
   - With M5, oxidative cuts feed chain ends.
   - `assemble --fetch-kinetics` would already query SABIO-RK by the
     confirmed EC numbers.
4. **M6.4 (gated)** In situ H2O2 from reductant and O2, coupled to M3, after
   its own S0.

**Tests**
- **H2O2 dependence:**
  - linear in H at H ≪ K_mH, saturating above;
  - zero H gives zero rate, with no hidden O2 route.
- **Stoichiometry and inactivation:**
  - one H2O2 per cut (ledger);
  - the total turnover before inactivation matches the analytic expression
    for constant H.
- **Two systems:** chitin-like and cellulose-like solids.
- **With M5:** LPMO plus exo enzyme degrades more than the sum, through
  chain ends only, and the degree of synergy is reported.
- **Fail-closed:**
  - an LPMO class without an H2O2 state or feed;
  - kcat given without K_mH;
  - a feed without units of concentration per time.

**Done means `software_tested`.** To go further, use H2O2-fed saccharification
time courses such as Müller et al. 2018, or chitin oxidation kinetics such as
Kuusk et al. 2018, digitised under a frozen plan.

## 11. Order, dependencies and size

```text
F1 ─┬─ every S0
F5 ─┼─ M1 adsorption ───────────────┬─ M5 synergy ── M6 LPMO
F4 ─┼─ M2 sugar uptake ── M3 oxygen ┤                │
F2 ─┤                   └─ M4 pH ───┘                └─ (M6b in situ H2O2 needs M3)
F3 ─┘
F6 ── M5.0 degree of synergy (independent, can go first)
```

| Step | Depends on | PRs (estimate) | Why at this point |
| --- | --- | --- | --- |
| F1 mechanism-source records | – | 1 | Gate for everything |
| F6 degree of synergy | – | 1 | Software only, useful at once |
| M1 adsorption | F1, F5 | 3 (+1 dynamic) | Most existing code; lifts a user-data refusal |
| F4 + M2 sugar uptake | F1, F5 | 4 (+1 gated repression) | Closure exists; lifts the CULTURE-002 refusal |
| F2 + M3 oxygen | M2 | 3 | Reuses the closure's oxidant and `gas_transfer` |
| F3 + M4 pH | F2 | 3 | New balance; the riskiest numerics |
| M5 synergy | M1 (recommended), F5 | 3 (+1 second form) | Needs a sourced structural state |
| M6 LPMO | M1, M5 (for synergy), F5 | 3 (+1 gated in situ H2O2) | Most new biology; benefits from all of the above |

That is about 24–28 PRs including the six S0 promotions. Each PR follows the
repository's usual definition of done:
- tests and docs with real output;
- CHANGELOG and `progress.md` entries;
- byte-identity pins for earlier behaviour;
- the guardrail suites (factory set, compiled kernels, hard-coding tokens,
  SBML refusal).

Steps that touch `api/user_data.py` should not run in parallel with each
other. The file is shared and conflicts there cost a CI cycle.

## 12. Documentation that changes as each mechanism lands

These sentences state the absence today. Each must change in the PR that
lifts it, and not before:

- **`docs/capabilities.md`:**
  - the user-data row (adsorption, synergy, LPMO, released pools, oxygen and
    pH);
  - the culture row ("nutrient, oxygen and maintenance physiology are
    absent");
  - the surface-law row ("not reachable from user data");
  - the LPMO and endoglucanase notes.
- **`docs/organism-physiology.md`:** no oxygen, maintenance or soluble
  intermediate; closure processes not bound by any template.
- **`docs/user-data.md`:**
  - the LPMO and endoglucanase notes;
  - the refusals of adsorption and surface inputs;
  - the limits of the solid route;
  - no released pools and no uptake;
  - no oxygen or pH dynamics;
  - no endo/exo synergy.
- **`docs/environment-response.md`:** "an environment is a static entity",
  which becomes "static unless a state drives it" after F2.
- **`docs/compiled-core.md`:** the shipped process count and the list of
  types with an analytic Jacobian.
- **The JOSS paper's design section,** for M1, M2 and M6 at least.

## 13. Out of scope, and decisions for the owner

**Out of scope until a separate source and proposal exist:**
- non-productive lignin binding;
- multi-sugar uptake with preference;
- nitrogen uptake;
- temperature dynamics;
- full electrolyte speciation;
- in situ H2O2 from reductants;
- LPMO activity on hemicellulose or starch beyond the family mapping;
- morphology and spatial coupling to the mycelium core.

**Decisions for the owner before work starts:**
1. **Order.** The proposed order is adsorption, uptake, oxygen, pH, synergy,
   LPMO. If LPMOs matter most scientifically, M6 can start right after M1,
   with M5's chain-end coupling added later.
2. **Who confirms each S0 source:** the owner, or an agent with the
   extraction reviewed by the owner. The plan assumes the owner signs off
   each S0 PR.
3. **Whether calibration targets** (section "Done means") are wanted now. Each
   needs a deposited dataset and a frozen study plan, as for the existing
   culture studies.

## 14. Sources

Status: **checked** means the title, journal, volume, pages and DOI were
confirmed by search on 2026-10-09. **Re-check** means cited from knowledge and
not yet confirmed. **Unverified** means it could not be confirmed and is not
to be used until it is.

| Key | Reference | Supports | Status |
| --- | --- | --- | --- |
| kadam2004 | Kadam, Rydholm & McMillan (2004). Development and validation of a kinetic model for enzymatic saccharification of lignocellulosic biomass. *Biotechnol. Prog.* 20(3):698–705. doi:10.1021/bp034316x | M1 law form (Langmuir partition in saccharification) | checked (in `paper/joss/paper.bib`) |
| medve1998 | Medve, Karlsson, Lee & Tjerneld (1998). Hydrolysis of microcrystalline cellulose by cellobiohydrolase I and endoglucanase II from *Trichoderma reesei*: adsorption, sugar production pattern, and synergism of the enzymes. *Biotechnol. Bioeng.* 59(5):621–634. doi:10.1002/(SICI)1097-0290(19980905)59:5<621::AID-BIT13>3.0.CO;2-C | M1 time scale and isotherms; M5 data | checked |
| bansal2009 | Bansal et al. (2009). Modeling cellulase kinetics on lignocellulosic substrates. *Biotechnol. Adv.* | M1/M5 choice of form (review) | unverified |
| monod1949 | Monod (1949). The growth of bacterial cultures. *Annu. Rev. Microbiol.* 3:371–394. doi:10.1146/annurev.mi.03.100149.002103 | M2 uptake law | re-check |
| pirt1965 | Pirt (1965). The maintenance energy of bacteria in growing cultures. *Proc. R. Soc. Lond. B* 163:224–231. doi:10.1098/rspb.1965.0069 | M2, M3 maintenance | re-check |
| ilmen1997 | Ilmén, Saloheimo, Onnela & Penttilä (1997). Regulation of cellulase gene expression in the filamentous fungus *Trichoderma reesei*. *Appl. Environ. Microbiol.* 63(4):1298–1306 | M2b phenomenon only (no rate law) | checked |
| velkovska1997 | Velkovska, Marten & Ollis (1997). Kinetic model for batch cellulase production. *J. Biotechnol.* | M2b candidate repression term | unverified |
| garciaochoa2009 | Garcia-Ochoa & Gomez (2009). Bioreactor scale-up and oxygen transfer rate in microbial processes: an overview. *Biotechnol. Adv.* 27(2):153–176. doi:10.1016/j.biotechadv.2008.10.006 | M3 law form | checked |
| benson1984 | Benson & Krause (1984). The concentration and isotopic fractionation of oxygen dissolved in freshwater and seawater in equilibrium with the atmosphere. *Limnol. Oceanogr.* 29(3):620–632. doi:10.4319/lo.1984.29.3.0620 | M3 solubility function (0–40 °C) | checked |
| vanslyke1922 | Van Slyke (1922). On the measurement of buffer values and on the relationship of buffer value to the dissociation constant of the buffer and the concentration and reaction of the buffer solution. *J. Biol. Chem.* 52:525–570. doi:10.1016/S0021-9258(18)85845-8 | M4 buffer value | checked |
| ammonium1984 | A 1984 study in *Microbiology* 130(4), doi:10.1099/00221287-130-4-1007, reporting coupling of proton excretion with ammonium uptake in a citric-acid-producing fungus | M4 coupling (qualitative) | unverified (title and authors) |
| jalak2012 | Jalak, Kurašin, Teugjas & Väljamäe (2012). Endo-exo synergism in cellulose hydrolysis revisited. *J. Biol. Chem.* 287(34):28802–28815. doi:10.1074/jbc.M112.381624 | M5 mechanisms and data | checked |
| levine2010 | Levine, Fox, Blanch & Clark (2010). A mechanistic model of the enzymatic hydrolysis of cellulose. *Biotechnol. Bioeng.* 107(1):37–51. doi:10.1002/bit.22789 | M5 form (c), structure | checked |
| zhang2004 | Zhang & Lynd (2004). Toward an aggregated understanding of enzymatic hydrolysis of cellulose: noncomplexed cellulase systems. *Biotechnol. Bioeng.* 88(7):797–824. doi:10.1002/bit.20282 | M5 form (a) framework (review) | re-check |
| kostylev2012 | Kostylev & Wilson (2012). Synergistic interactions in cellulose hydrolysis. *Biofuels* 3(1):61–70 | F6 degree-of-synergy definition | checked (bibliographic only; the definition must be confirmed) |
| vaajekolstad2010 | Vaaje-Kolstad et al. (2010). An oxidative enzyme boosting the enzymatic conversion of recalcitrant polysaccharides. *Science* 330:219–222. doi:10.1126/science.1192231 | M6 existence and boosting | re-check |
| quinlan2011 | Quinlan et al. (2011). Insights into the oxidative degradation of cellulose by a copper metalloenzyme that exploits biomass components. *PNAS* 108:15079–15084. doi:10.1073/pnas.1105776108 | M6 cellulose-active family | re-check |
| levasseur2013 | Levasseur, Drula, Lombard, Coutinho & Henrissat (2013). Expansion of the enzymatic repertoire of the CAZy database to integrate auxiliary redox enzymes. *Biotechnol. Biofuels* 6:41. doi:10.1186/1754-6834-6-41 | M6 CAZy AA classes | re-check |
| bissaro2017 | Bissaro et al. (2017). Oxidative cleavage of polysaccharides by monocopper enzymes depends on H2O2. *Nat. Chem. Biol.* 13(10):1123–1128. doi:10.1038/nchembio.2470 | M6 co-substrate, priming | checked |
| kuusk2018 | Kuusk et al. (2018). Kinetics of H2O2-driven degradation of chitin by a bacterial lytic polysaccharide monooxygenase. *J. Biol. Chem.* 293(2):523–531. doi:10.1074/jbc.M117.817593 | M6 law form, inactivation | checked |
| kont2020 | Kont, Bissaro, Eijsink & Väljamäe (2020). Kinetic insights into the peroxygenase activity of cellulose-active lytic polysaccharide monooxygenases (LPMOs). *Nat. Commun.* 11:5786. doi:10.1038/s41467-020-19561-8 | M6 law form across families | checked |
| muller2018 | Müller, Chylenski, Bissaro, Eijsink & Horn (2018). The impact of hydrogen peroxide supply on LPMO activity and overall saccharification efficiency of a commercial cellulase cocktail. *Biotechnol. Biofuels* 11:209. doi:10.1186/s13068-018-1199-4 | M6 feed process; candidate data | checked |
