# A worked example on stored literature data

The [walkthrough](walkthrough.md) follows the route from a fungus name to a
simulation on synthetic test fixtures. This page runs the two registry cases
whose numbers come from published sources, from the stored records alone and
with no network access:

1. **[*Trichoderma harzianum* P49P11 on cellulose](#case-1-t-harzianum-p49p11-on-cellulose)**:
   the fungus growing on Celufloc 200 cellulose at 10, 20 and 30 g/L
   ([Gelain et al. 2020](https://doi.org/10.1016/j.cesx.2020.100085)). This
   whole-culture case runs in scientific mode.
2. **[BGL1A of *Phanerochaete chrysosporium* on cellobiose](#case-2-p-chrysosporium-bgl1a-on-cellobiose-ph-4-to-8)**:
   the fungus's beta-glucosidase BGL1A on cellobiose at pH 4 to 8 (Tsukada et
   al. 2008, deposited in SABIO-RK as entry 38522). This enzyme case has a pH
   law and runs in exploratory mode only.

For each case the page gives the command and its output, explains how to read
the output, and lists where every number comes from, the maturity labels and
limitations, and the measurements that would improve the case.

!!! warning "Stored literature data, not validated predictions"

    Every input below is a registry record with provenance. It is one of
    three kinds:

    - a value copied from a deposited workbook or a SABIO-RK export (both are
      archived in the repository with their SHA-256);
    - a constant that FungMod fitted to the same published culture data;
    - an assumption, labelled as one.

    Neither case is validated against independent data. The culture
    constants are a retrospective fit to the very measurements this page
    compares them with. The enzyme case integrates initial-rate constants over
    time, at assay loadings that FungMod assumed. Every printed output on this
    page is real output of the commands shown, run offline from the root of a
    repository checkout. `tests/test_real_example_doc.py` reruns the commands
    and checks every line shown (`...` marks omitted text).

## The stored cases

`fungmod list` names what the registry holds:

<!-- real-example-command: list -->
```bash
fungmod list
```

<!-- real-example-output: list -->
```text
Registry: .../data_registry/registry_index.yml (registry toy_registry, version 0.1.0, maturity development)

Fungi and enzyme sources (--fungus): 5
  id                               name                                                   maturity
  toy_fungus_alpha                 Toy fungus alpha                                       toy_development
  generic_cellulase_source         Generic cellulase enzyme source                        exploratory_metadata
  sabiork_beta_glucosidase_source  SABIO-RK Reaction 618 beta-glucosidase source          literature_processed
  trichoderma_harzianum_p49p11     Trichoderma harzianum P49P11                           literature_metadata
  phanerochaete_chrysosporium_k3   Phanerochaete chrysosporium K-3 (BGL1A enzyme source)  literature_metadata
...
Environments (--environment): 11
...
  gelain_2020_cellulose_batch_10gl            Gelain 2020 T. harzianum batch culture on 10 g/L cellulose (29 C, pH 5)     literature_processed
  gelain_2020_cellulose_batch_20gl            Gelain 2020 T. harzianum batch culture on 20 g/L cellulose (29 C, pH 5)     literature_processed
  gelain_2020_cellulose_batch_30gl            Gelain 2020 T. harzianum batch culture on 30 g/L cellulose (29 C, pH 5)     literature_processed
  tsukada_2008_bgl1a_assay_30c_ph4            Tsukada 2008 BGL1A cellobiose assay at 30 C, pH 4.0 (50 mM sodium acetate)  literature_processed
  tsukada_2008_bgl1a_assay_30c_ph5            Tsukada 2008 BGL1A cellobiose assay at 30 C, pH 5.0 (50 mM sodium acetate)  literature_processed
  tsukada_2008_bgl1a_assay_30c_ph6            Tsukada 2008 BGL1A cellobiose assay at 30 C, pH 6.0 (50 mM MES)             literature_processed
  tsukada_2008_bgl1a_assay_30c_ph7            Tsukada 2008 BGL1A cellobiose assay at 30 C, pH 7.0 (50 mM HEPES)           literature_processed
  tsukada_2008_bgl1a_assay_30c_ph8            Tsukada 2008 BGL1A cellobiose assay at 30 C, pH 8.0 (50 mM EPPS)            literature_processed
```

The registry as a whole is labelled `toy_registry`, maturity `development`,
because it holds toy fixtures next to the curated records. Each record
carries its own maturity, and the preflight judges every case by the records
it uses. The table below lists every fungus record and says which ones this
page runs:

<!-- real-example-table: survey -->
| Registry fungus | Substrate and conditions | Source | What the source measured or states | Runs in | On this page |
| --- | --- | --- | --- | --- | --- |
| `trichoderma_harzianum_p49p11` | Celufloc 200 cellulose at 10, 20 and 30 g/L; 29 °C, pH 5 | Gelain et al. 2020 and its deposited workbooks ([doi:10.17632/shd3wcczsr.2](https://doi.org/10.17632/shd3wcczsr.2), CC BY 4.0) | Duplicate means of biomass, residual cellulose, filter-paper activity and beta-glucosidase activity from 0 to 96 h in stirred batch cultures | scientific mode: every input is exact | Case 1 |
| `phanerochaete_chrysosporium_k3` | Cellobiose at 30 °C, pH 4 to 8 | SABIO-RK Reaction 618 entry 38522, reporting Tsukada et al. 2008 (PMID 18023045) | The constants and standard deviations of a pH-dependent Michaelis-Menten law for recombinant BGL1A, fitted over pH 4 to 8 at 30 °C; no substrate or enzyme concentration and no time course | exploratory mode only: the assay loadings are assumptions | Case 2 |
| `sabiork_beta_glucosidase_source` | Cellobiose at 30 °C, pH 5 | SABIO-RK Reaction 618 entry 35622 | Km, kcat and the initial cellobiose concentration of a recombinant rice (*Oryza sativa*) beta-glucosidase; no enzyme concentration | exploratory mode only: the enzyme concentration is sampled from a stated prior | No: a plant enzyme, not a fungus (it is the [registry-environment example](cli.md#registry-environments) of the command line) |
| `toy_fungus_alpha` | Toy substrate and environment | FungMod test fixture | Nothing | neither mode: its toy case has a missing value | No: a toy record |
| `generic_cellulase_source` | Generic cellulose film | FungMod's controlled virtual-experiment scaffold (BIO-001) | Nothing; its values are exploratory assumptions | exploratory mode only | No: not literature data |

The repository holds other published data as well, such as the
beta-glucosidase time courses of the [calibration evidence](calibration-evidence.md)
and the literature [configured models](configured-models.md). These run from
configuration files rather than from a fungus name, so this page does not
cover them. For a fungus that has no stored case, follow the
[walkthrough](walkthrough.md): there, kinetics of another organism's enzyme
are estimates and missing kinetics are gaps.

## Case 1: *T. harzianum* P49P11 on cellulose

**What the stored records hold.** Gelain et al. grew *T. harzianum* P49P11 in
stirred batch reactors on Celufloc 200 cellulose: 10, 20 and 30 g/L in
Mandels medium with 1 g/L peptone, at 29 °C, pH 5.0 and dissolved oxygen
above 30 %. They deposited workbooks with the duplicate means of four
measurements at 0, 8, 12, 24, 32, 48, 54, 72 and 96 h:

- biomass, measured as total dry mass minus the acid-treated residue;
- residual cellulose;
- filter-paper activity (FPU/L);
- beta-glucosidase activity (pNPG units per litre).

The deposit has no individual replicates and no standard deviations.

The registry takes the initial values from the workbooks. It also holds nine
constants that FungMod fitted to all 96 non-initial observations of the three
cultures: the "hydrolysis candidate" of the
[joint comparison](gelain-joint-benchmark.md). That model has the following
parts:

- filter-paper activity drives cellulose consumption, `k_h F S / (K_h + S)`;
- a fraction `Y` of the consumed cellulose becomes biomass;
- biomass is lost at a first-order rate;
- cellulose induces the production of both activities, and both are lost at
  a first-order rate.

These are not the published Gelain equations, which are bespoke and
rank-deficient ([organism physiology](organism-physiology.md)). Nothing in
this case comes from another organism.

### Run it

<!-- real-example-command: th-run -->
```bash
fungmod run --fungus "T. harzianum P49P11" --substrate "Celufloc 200" \
  --environment gelain_2020_cellulose_batch_10gl \
  --environment gelain_2020_cellulose_batch_20gl \
  --environment gelain_2020_cellulose_batch_30gl \
  --mode scientific --output outputs/t_harzianum
```

<!-- real-example-output: th-run -->
```text
Registry: .../data_registry/registry_index.yml (registry toy_registry, version 0.1.0, maturity development)
  fungus 'T. harzianum P49P11' -> trichoderma_harzianum_p49p11 (Trichoderma harzianum P49P11)
  substrate 'Celufloc 200' -> cellulose_celufloc_200 (Cellulose (Celufloc 200))
  environment 'gelain_2020_cellulose_batch_10gl' -> gelain_2020_cellulose_batch_10gl (Gelain 2020 T. harzianum batch culture on 10 g/L cellulose (29 C, pH 5))
  environment 'gelain_2020_cellulose_batch_20gl' -> gelain_2020_cellulose_batch_20gl (Gelain 2020 T. harzianum batch culture on 20 g/L cellulose (29 C, pH 5))
  environment 'gelain_2020_cellulose_batch_30gl' -> gelain_2020_cellulose_batch_30gl (Gelain 2020 T. harzianum batch culture on 30 g/L cellulose (29 C, pH 5))
Cases: 1 fungus x 1 substrate x 3 environment = 3

Preflight in scientific mode:
  #  fungus                        substrate               environment                       status     runnable
  1  trichoderma_harzianum_p49p11  cellulose_celufloc_200  gelain_2020_cellulose_batch_10gl  modelable  yes
  2  trichoderma_harzianum_p49p11  cellulose_celufloc_200  gelain_2020_cellulose_batch_20gl  modelable  yes
  3  trichoderma_harzianum_p49p11  cellulose_celufloc_200  gelain_2020_cellulose_batch_30gl  modelable  yes

Simulated 3 case(s) in scientific mode: one exact run per case.
Run label: scientific_exact_unvalidated
Scientific mode uses exact non-exploratory registry values and implemented process laws. It is not a claim of experimental validation.

Case case_0000: trichoderma_harzianum_p49p11 + cellulose_celufloc_200 + gelain_2020_cellulose_batch_10gl
  samples: 1 simulated, 0 failed
  environment effect: metadata_only
  environment guardrail: Metadata-only environment cases cannot be ranked or plotted as environmental response models.
  Final metrics (one run):
    final_substrate_remaining          ... gram / liter
    final_substrate_degraded_fraction  1 dimensionless
    final_product_concentration        not_applicable (No product state mapping was available.)
    final_product_formed               not_applicable (No product state mapping was available.)
    maximum_product_release_rate       not_applicable (No product state mapping was available.)
    maximum_substrate_depletion_rate   0.5056 gram / hour / liter
  Threshold times (one run):
    time_to_10_percent_substrate_degradation  10.89 hour
    time_to_50_percent_substrate_degradation  22.28 hour
    time_to_90_percent_substrate_degradation  31.44 hour

Case case_0001: trichoderma_harzianum_p49p11 + cellulose_celufloc_200 + gelain_2020_cellulose_batch_20gl
...
    maximum_substrate_depletion_rate   1.288 gram / hour / liter
  Threshold times (one run):
    time_to_10_percent_substrate_degradation  12.02 hour
    time_to_50_percent_substrate_degradation  22.24 hour
    time_to_90_percent_substrate_degradation  29.16 hour

Case case_0002: trichoderma_harzianum_p49p11 + cellulose_celufloc_200 + gelain_2020_cellulose_batch_30gl
...
    maximum_substrate_depletion_rate   2.226 gram / hour / liter
  Threshold times (one run):
    time_to_10_percent_substrate_degradation  12.92 hour
    time_to_50_percent_substrate_degradation  22.57 hour
    time_to_90_percent_substrate_degradation  28.52 hour

Output directory: outputs/t_harzianum
Manifest: outputs/t_harzianum/output_manifest.json
Report: outputs/t_harzianum/report/virtual_experiment_report.md
Limitations: 39 (9 important, 30 info) in outputs/t_harzianum/limitations_table.csv
Provenance: 54 row(s) in outputs/t_harzianum/provenance_table.csv
Suggested experiments: 6 in outputs/t_harzianum/suggested_experiments.csv
```

### Read it

- **From the name to the stored case.** "T. harzianum P49P11" resolves to the
  registry fungus. Its record lists two enzyme classes: total cellulase,
  measured as filter-paper activity, and beta-glucosidase. The culture
  template binds them to 13 parameter records per culture (tables below;
  only the cellulose loading differs between the cultures). The preflight
  finds every record exact, non-exploratory and provenance-backed, so the
  cases are `modelable` in scientific mode. The run label says what that
  means: exact inputs and implemented process laws, not experimental
  validation.
- **Substrate loss.** All three cultures consume their cellulose within the
  96 simulated hours (`final_substrate_degraded_fraction` 1). The remaining
  cellulose, shown as `...` above, is of order 1e-12 g/L: solver noise
  around zero whose sign means nothing
  ([negative solver iterates](organism-physiology.md#depletion-and-negative-solver-iterates)).
  Half of the cellulose is gone after 22.2 to 22.6 h at every loading. The
  maximum depletion rate grows with the loading, from 0.51 to 1.29 to
  2.23 g/L/h.
- **Product release.** There is no product. Gelain et al. measured no soluble
  sugars, so the template maps no product state, and the product metrics are
  `not_applicable` with the reason. The consumed cellulose that is not kept
  as biomass (a fraction `1 - Y`) goes to an explicit closure ledger,
  `consumed_cellulose_not_retained_as_biomass` in `time_series_long.csv`.
  The ledger is not a measured product.
- **The time courses.** `time_series_long.csv` holds every state at the
  template's 97 hourly points from 0 to 96 h: cellulose, biomass,
  filter-paper activity, beta-glucosidase activity and the two ledgers.
  The activities stay in assay units and are never converted into enzyme
  amounts. The quick-look figures in `figures/` plot the cellulose
  remaining, the degradation fraction and the degradation rate against
  time.
- **Uncertainty.** Each case has one exact run and no band. The deposit has
  no replicate standard deviations, so there is no measured uncertainty to
  propagate. The parameter records carry 95 % credible intervals from the
  recorded [posterior study](bayesian-calibration.md) (table below). The
  run does not sample them, and they rest on an assumed error model.
- **Environment.** The environment effect is `metadata_only`: temperature and
  pH are the cultures' controlled set points and act on no rate. The three
  cases differ only in their stored initial cellulose loading. Read them as
  three loadings, not as an environmental response; the guardrail forbids the
  latter.

### Against the measurements it was fitted to

The run's time courses can be set beside the deposited means. The snippet
below reads `outputs/t_harzianum/time_series_long.csv` and the extracted
workbook values in `data/benchmarks/gelain_2020_v2/observations.json`. Each
value in that file carries its workbook, sheet and cell.

<!-- real-example-code: th-compare -->
```python
import csv
import json

with open("data/benchmarks/gelain_2020_v2/observations.json", encoding="utf-8") as handle:
    measured = {entry["condition_id"]: entry for entry in json.load(handle)}
with open("outputs/t_harzianum/time_series_long.csv", encoding="utf-8", newline="") as handle:
    simulated = {
        (row["environment_id"], row["state"], float(row["time"])): float(row["value"])
        for row in csv.DictReader(handle)
        if row["source"] == "simulation_state"
    }
print("loading  time  cellulose (g/L)     biomass (g/L)       filter paper (FPU/L)")
print("          (h)  simulated measured  simulated measured  simulated measured")
for loading in ("10gl", "20gl", "30gl"):
    observed = measured[f"gelain_2020_cellulose_{loading}"]
    for index, time in enumerate(observed["times_h"]):
        cells = []
        for state, observable, digits in (
            ("cellulose_concentration", "substrate", 2),
            ("biomass_dry_mass_concentration", "biomass", 2),
            ("cellulase_activity", "cellulase_activity", 0),
        ):
            value = simulated[(f"gelain_2020_cellulose_batch_{loading}", state, float(time))]
            reported = observed["observations"][observable]["values"][index]
            # "z" prints a value that rounds to zero as 0.00, whatever its sign
            cells.append(f"{value:>z9.{digits}f} {reported:>8.{digits}f}")
        print(f"{loading:>7} {time:>5}  " + "  ".join(cells))
```

<!-- real-example-output: th-compare -->
```text
loading  time  cellulose (g/L)     biomass (g/L)       filter paper (FPU/L)
          (h)  simulated measured  simulated measured  simulated measured
   10gl     8       9.48     9.88       0.55     2.86         20        0
   10gl    12       8.77     9.22       0.79     3.67         36       21
   10gl    24       4.14     2.74       2.36     5.91        139      422
   10gl    32       0.85     1.26       3.26     4.74        273      767
   10gl    48       0.00     0.53       2.64     4.24        470      819
   10gl    54       0.00     0.27       2.35     3.57        472      846
   10gl    72       0.00     0.20       1.64     2.63        472      888
   10gl    96       0.00     0.27       1.02     2.12        472      791
   20gl     8      19.21    19.97       0.65     4.00         22        0
   20gl    12      18.01    18.95       1.08     4.81         42        0
   20gl    24       7.79     8.02       4.71     8.22        221      234
   20gl    32       0.54     4.42       6.75     7.95        502      430
   20gl    48       0.00     1.44       5.08     4.13        726      790
   20gl    54       0.00     0.91       4.51     3.90        726      843
   20gl    72       0.00     0.46       3.15     3.02        726      814
   20gl    96       0.00     0.23       1.96     2.27        726      770
   30gl     8      29.04    31.19       0.72     3.39         23        0
   30gl    12      27.51    28.99       1.28     4.57         45        0
   30gl    24      11.99    15.73       6.90     9.41        286      153
   30gl    32       0.33     7.87      10.26     9.36        715      343
   30gl    48       0.00     2.67       7.57     5.49        939      665
   30gl    54       0.00     1.65       6.72     4.39        939      745
   30gl    72       0.00     0.81       4.70     3.69        939      796
   30gl    96       0.00     0.41       2.91     3.08        939      755
```

This is in-sample agreement. The nine constants were fitted to exactly
these observations, and to the beta-glucosidase activities not printed here,
so the match is not evidence of predictive accuracy. Even in-sample, the
model departs from the data in three visible ways:

- The simulated cellulose is used up by 48 h at every loading. The measured
  cellulose stays between 0.20 and 2.67 g/L from 48 to 96 h. The model has no
  term for a residue that resists hydrolysis or for an assay floor.
- The simulated biomass at 8 h is a fraction of the measured biomass (0.55
  against 2.86 g/L at 10 g/L).
- The simulated filter-paper activity levels off higher at higher loadings
  (472, 726 and 939 FPU/L). The measured activity at 96 h is between 755 and
  791 FPU/L at all three loadings.

The out-of-sample test that exists is recorded in the
[joint comparison](gelain-joint-benchmark.md#recorded-result-2026-09-28). In
its whole-condition holdouts, this hydrolysis candidate had pooled
root-mean-square errors of 2.493 g/L (biomass), 2.465 g/L (cellulose),
346.9 FPU/L and 726.7 pNPG U/L, and it failed the comparison's
observable-worsening screen. The published Gelain equations did better there.
The registry carries this candidate rather than the published equations,
which fit better but are bespoke and rank-deficient
([organism physiology](organism-physiology.md#what-this-case-does-not-claim)).
The candidate composes generic process laws, and its fit has full practical
rank.

### Provenance

`provenance_table.csv` lists, per case, the source, maturity and allowed use
of every record. The nine fitted constants all have the maturity
`calibrated`, the confidence level `calibrated_retrospective_unvalidated` and
the same source: FungMod's retrospective all-condition fit of the hydrolysis
candidate (`gelain_2020_joint_culture_v2`, scenario `primary`) to the Gelain
2020 data. Each record names the fit artifact
`data/benchmarks/gelain_2020_v2/results/full_fits/cellulose_hydrolysis_primary.json`
with its SHA-256, the three training conditions, the practical rank (9 of 9)
and the three constants that sit at a fitting bound (`K_ind`, `kF`, `kB`).
The class and the 95 % credible interval come from the recorded posterior
study
(`data/benchmarks/gelain_2020_bayesian/results/bayesian_calibration.json`).
That study is conditional on a log-uniform prior box and an assumed error
model. "Inside" says whether the exact value the run uses lies in that
interval.

<!-- real-example-table: th-constants -->
| Role | Record | Value | Units | Posterior class | 95 % credible interval | Inside |
| --- | --- | --- | --- | --- | --- | --- |
| `hydrolysis_capacity` | `gelain_hydrolysis_k_h_calibrated` | 0.01838 | gram / filter_paper_unit / hour | `identified` | 0.00714 to 0.0639 | yes |
| `hydrolysis_half_saturation` | `gelain_hydrolysis_Kh_calibrated` | 16.73 | gram / liter | `bounded_below_only` | 4.26 to 81.9 | yes |
| `biomass_yield` | `gelain_hydrolysis_Y_calibrated` | 0.4148 | dimensionless | `identified` | 0.328 to 0.648 | yes |
| `biomass_loss_rate` | `gelain_hydrolysis_kd_calibrated` | 0.01987 | 1 / hour | `identified` | 0.0114 to 0.0392 | yes |
| `induction_half_saturation` | `gelain_hydrolysis_K_ind_calibrated` | 0.01 | gram / liter | `bounded_above_only` | 0.0103 to 0.12 | no |
| `cellulase_specific_production_rate` | `gelain_hydrolysis_qF_calibrated` | 5.823 | filter_paper_unit / gram / hour | `identified` | 4.2 to 7.94 | yes |
| `cellulase_loss_rate` | `gelain_hydrolysis_kF_calibrated` | 1e-06 | 1 / hour | `bounded_above_only` | 1.21e-06 to 0.004 | no |
| `beta_glucosidase_specific_production_rate` | `gelain_hydrolysis_qB_calibrated` | 13.94 | beta_glucosidase_assay_unit / gram / hour | `identified` | 9.9 to 18.7 | yes |
| `beta_glucosidase_loss_rate` | `gelain_hydrolysis_kB_calibrated` | 1e-06 | 1 / hour | `bounded_above_only` | 1.21e-06 to 0.0028 | no |

The data identify five constants. The other four are a lower limit
(`Kh`: saturation above the measured loadings cannot be told apart from
first-order kinetics) and three upper limits (`K_ind`, `kF`, `kB`: induction
is effectively saturated and the activity losses are effectively zero over
96 h). The exact values of `K_ind`, `kF` and `kB` sit on the lower edge of
the fit's bounds, just below their intervals. Read those four constants as
the ranges, not as exact values.

The initial state is copied from the t = 0 row of the deposited workbooks
(maturity `literature_processed`, confidence level `literature_curated`):

<!-- real-example-table: th-initial -->
| Role | Record | Value | Units | Workbook cell |
| --- | --- | --- | --- | --- |
| `initial_biomass` | `gelain_2020_cellulose_initial_biomass` | 0.3991 | gram / liter | E2 |
| `initial_substrate` | `gelain_2020_cellulose_initial_loading_10gl` | 10 | gram / liter | F2 |
| `initial_substrate` | `gelain_2020_cellulose_initial_loading_20gl` | 20 | gram / liter | F2 |
| `initial_substrate` | `gelain_2020_cellulose_initial_loading_30gl` | 30 | gram / liter | F2 |
| `initial_cellulase_activity` | `gelain_2020_cellulose_initial_cellulase_activity` | 0 | filter_paper_unit / liter | B2 |
| `initial_beta_glucosidase_activity` | `gelain_2020_cellulose_initial_beta_glucosidase_activity` | 0 | beta_glucosidase_assay_unit / liter | C2 |

The provenance table also carries the source of every other record. The
organism and substrate records cite Gelain 2020. Each
culture-condition record names its workbook and that workbook's SHA-256. The
compatibility and template records cite the fit they bind.

### Maturity and limitations

<!-- real-example-table: th-maturity -->
| Label | Records |
| --- | --- |
| `calibrated` | The nine fitted constants, the process compatibility and the case template |
| `literature_processed` | The six workbook values and the three culture conditions |
| `literature_metadata` | The organism and the substrate |
| `scientific_exact_unvalidated` | The run: exact inputs and implemented laws, not validated |

`limitations_table.csv` has 13 rows per case: 3 important and 10 for
information. The important ones, for the 10 g/L case:

<!-- real-example-table: th-limits -->
| Category | Limitation |
| --- | --- |
| `environment_effect` | Environment is metadata/context only. The simulation used the same kinetic parameter values across environments; no temperature or pH response law was applied. Do not rank or plot these cases as environmental response models. |
| `not_modelled` | This is a well-mixed culture physiology case composed from template-declared process laws; nutrient limitation, oxygen transfer, maintenance, morphology, pH dynamics, and soluble intermediates are not represented unless the template declares them. |
| `retrospective_calibration` | Calibrated parameter records are retrospective fits to published duplicate means without measured uncertainty; the trajectories are not validated predictions and must not be cited as independent evidence. |

The rows for information state the scope: *T. harzianum* P49P11 on
Celufloc 200 at 10 to 30 g/L, 29 °C, pH 5.0, dissolved oxygen above 30 %,
0 to 96 h. They also say that activities are assay units, that the closure
ledger is not a measured product, and that soluble sugars and respired carbon
were not measured.

### Follow-up measurements

`suggested_experiments.csv` holds the same two requests for each of the three
cases:

<!-- real-example-table: th-suggestions -->
| Suggestion | Priority | Experiment | Why |
| --- | --- | --- | --- |
| `gelain_replicate_level_time_courses` | high | Obtain individual replicate time courses (not duplicate means) of biomass, cellulose, filter-paper and beta-glucosidase activity for at least one held-out cellulose loading. | Replicate-level data with a measured error model are required before any calibrated constant can be promoted beyond a retrospective fit. |
| `induction_and_activity_loss_identifiability` | high | Measure activity production at cellulose concentrations below 1 g/L and activity decay in cell-free broth. | The induction constant and both activity-loss constants sit at their fitting bounds; the published means do not identify them. |

The page adds four suggestions of its own:

- **Freeze a prediction before measuring.** Before a new culture with
  replicates is run, at a loading or condition outside the fit, freeze the
  prediction with the
  [independent-validation workflow](independent-validation.md). That is the
  first test this case could pass or fail.
- **Measure what consumed cellulose becomes.** Soluble sugars and CO2 would
  turn the closure ledger into measured products.
- **Measure the residue.** Residual cellulose after 48 h would show whether a
  fraction resists hydrolysis or whether the assay has a floor.
- **Measure a temperature or pH series.** The registry holds no cardinal
  temperatures or pH values for this strain, so no response law can be bound
  yet ([environment response](environment-response.md#what-is-implemented-but-not-yet-bound-to-an-organism)).

## Case 2: *P. chrysosporium* BGL1A on cellobiose, pH 4 to 8

**What the stored records hold.** SABIO-RK Reaction 618 is
cellobiose + H2O = 2 beta-D-glucose. Its entry 38522 concerns the GH1
beta-glucosidase BGL1A of *P. chrysosporium* K-3: wild type, recombinant,
UniProt Q25BW5, expressed in *E. coli* Rosetta DE3. For that enzyme the entry
deposits the six constants, with their standard deviations, of the
pH-dependent Michaelis-Menten law that Tsukada et al. (2008) fitted over
pH 4 to 8 at 30 °C:

```text
v = E kcat(pH) S / (Km(pH) + S),   kcat(pH) = k0 / f_es(pH),   Km(pH) = Km0 f_e(pH) / f_es(pH)
f(pH) = (10^(pK_low - pH) + 1) (10^(pH - pK_high) + 1)
```

The assays used four buffers: sodium acetate (pH 4.0 to 5.5), MES (6.0 to
6.5), HEPES (7.0 to 7.5) and EPPS (8.0). SABIO-RK notes that the temperature
is "given in PMID:16896601", another publication. The entry records no
substrate or enzyme concentration and no time course. The raw export is
archived as
`data/kinetic_records/sabiork/case_001_reaction_618_beta_glucosidase/raw/kinlaw_entries_reaction_618.json`,
and every record copied from it carries the export's SHA-256. The registry
copies the constants verbatim.

Three things are assumed rather than sourced:

- the initial cellobiose concentration (5 mM);
- the enzyme concentration (1 µM, written 0.001 mM);
- the template's time grid: 4 hours, 145 points.

The 2:1 glucose yield is the reaction's stoichiometry, not a measured time
course.

The enzyme is the fungus's gene product made in a bacterium. This is an
enzyme case: no fungus grows or secretes anything in it.

### Run it

<!-- real-example-command: bgl-run -->
```bash
fungmod run --fungus "P. chrysosporium" --substrate cellobiose \
  --environment tsukada_2008_bgl1a_assay_30c_ph4 \
  --environment tsukada_2008_bgl1a_assay_30c_ph5 \
  --environment tsukada_2008_bgl1a_assay_30c_ph6 \
  --environment tsukada_2008_bgl1a_assay_30c_ph7 \
  --environment tsukada_2008_bgl1a_assay_30c_ph8 \
  --mode exploratory --samples 4 --seed 1 --output outputs/bgl1a
```

<!-- real-example-output: bgl-run -->
```text
Registry: .../data_registry/registry_index.yml (registry toy_registry, version 0.1.0, maturity development)
  fungus 'P. chrysosporium' -> phanerochaete_chrysosporium_k3 (Phanerochaete chrysosporium K-3 (BGL1A enzyme source))
  substrate 'cellobiose' -> cellobiose (Cellobiose)
  environment 'tsukada_2008_bgl1a_assay_30c_ph4' -> tsukada_2008_bgl1a_assay_30c_ph4 (Tsukada 2008 BGL1A cellobiose assay at 30 C, pH 4.0 (50 mM sodium acetate))
...
Cases: 1 fungus x 1 substrate x 5 environment = 5

Preflight in exploratory mode:
  #  fungus                          substrate   environment                       status     runnable
  1  phanerochaete_chrysosporium_k3  cellobiose  tsukada_2008_bgl1a_assay_30c_ph4  modelable  yes
  2  phanerochaete_chrysosporium_k3  cellobiose  tsukada_2008_bgl1a_assay_30c_ph5  modelable  yes
  3  phanerochaete_chrysosporium_k3  cellobiose  tsukada_2008_bgl1a_assay_30c_ph6  modelable  yes
  4  phanerochaete_chrysosporium_k3  cellobiose  tsukada_2008_bgl1a_assay_30c_ph7  modelable  yes
  5  phanerochaete_chrysosporium_k3  cellobiose  tsukada_2008_bgl1a_assay_30c_ph8  modelable  yes

Simulated 5 case(s) in exploratory mode: 4 sample(s) per case, seed 1.
Run label: exploratory_uncertainty_screen

Case case_0000: phanerochaete_chrysosporium_k3 + cellobiose + tsukada_2008_bgl1a_assay_30c_ph4
  samples: 4 simulated, 0 failed
  environment effect: active_response_model (ph:ph_ionization_michaelis_menten)
  environment guardrail: Environment comparisons are allowed: explicit response laws act on ph; every other environment condition is metadata and the laws carry the documented limitations.
  Final metrics (median [5th, 95th percentile] over samples):
    final_substrate_remaining          2.19 [2.19, 2.19] millimolar (n=4)
    final_substrate_degraded_fraction  0.5619 [0.5619, 0.5619] dimensionless (n=4)
    final_product_concentration        5.619 [5.619, 5.619] millimolar (n=4)
    final_product_formed               5.619 [5.619, 5.619] millimolar (n=4)
    final_product_yield                1.124 [1.124, 1.124] dimensionless (n=4)
    maximum_product_release_rate       0.0005145 [0.0005145, 0.0005145] millimolar / second (n=4)
    maximum_substrate_depletion_rate   0.0002572 [0.0002572, 0.0002572] millimolar / second (n=4)
  Threshold times (median [5th, 95th percentile] over samples):
    time_to_10_percent_substrate_degradation  2015 [2015, 2015] second (n=4)
    time_to_50_percent_substrate_degradation  1.227e+04 [1.227e+04, 1.227e+04] second (n=4)
    time_to_90_percent_substrate_degradation  not_reached in 4 of 4 samples (Threshold was not reached within the simulated time span.)

Case case_0001: phanerochaete_chrysosporium_k3 + cellobiose + tsukada_2008_bgl1a_assay_30c_ph5
  samples: 4 simulated, 0 failed
  environment effect: active_response_model (ph:ph_ionization_michaelis_menten)
...
  Final metrics (median [5th, 95th percentile] over samples):
    final_substrate_remaining          0.4305 [0.4305, 0.4305] millimolar (n=4)
    final_substrate_degraded_fraction  0.9139 [0.9139, 0.9139] dimensionless (n=4)
    final_product_concentration        9.139 [9.139, 9.139] millimolar (n=4)
    final_product_formed               9.139 [9.139, 9.139] millimolar (n=4)
    final_product_yield                1.828 [1.828, 1.828] dimensionless (n=4)
    maximum_product_release_rate       0.001277 [0.001277, 0.001277] millimolar / second (n=4)
    maximum_substrate_depletion_rate   0.0006387 [0.0006387, 0.0006387] millimolar / second (n=4)
  Threshold times (median [5th, 95th percentile] over samples):
    time_to_10_percent_substrate_degradation  808.1 [808.1, 808.1] second (n=4)
    time_to_50_percent_substrate_degradation  4824 [4824, 4824] second (n=4)
    time_to_90_percent_substrate_degradation  1.365e+04 [1.365e+04, 1.365e+04] second (n=4)
...
Output directory: outputs/bgl1a
Manifest: outputs/bgl1a/output_manifest.json
Report: outputs/bgl1a/report/virtual_experiment_report.md
Limitations: 70 (25 important, 45 info) in outputs/bgl1a/limitations_table.csv
Provenance: 75 row(s) in outputs/bgl1a/provenance_table.csv
Suggested experiments: 0 in outputs/bgl1a/suggested_experiments.csv
```

### Read it

The five cases side by side, from `summary_metrics.csv` and
`threshold_times.csv` (medians; all samples agree):

<!-- real-example-table: bgl-ph -->
| pH (buffer) | Cellobiose degraded after 4 h | Glucose formed (mM) | Maximum depletion rate (mM/s) | 10 % degraded (s) | 50 % degraded (s) | 90 % degraded (s) |
| --- | --- | --- | --- | --- | --- | --- |
| 4 (sodium acetate) | 0.5619 | 5.619 | 0.0002572 | 2015 | 1.227e+04 | not reached |
| 5 (sodium acetate) | 0.9139 | 9.139 | 0.0006387 | 808.1 | 4824 | 1.365e+04 |
| 6 (MES) | 0.9489 | 9.489 | 0.0007358 | 700.6 | 4157 | 1.163e+04 |
| 7 (HEPES) | 0.9167 | 9.167 | 0.0006267 | 822.1 | 4862 | 1.352e+04 |
| 8 (EPPS) | 0.5522 | 5.522 | 0.0002386 | 2156 | 1.265e+04 | not reached |

- **Substrate loss and product release.** Each cellobiose releases two
  glucose, so the glucose formed is twice the cellobiose degraded.
  `final_product_yield` (1.828 at pH 5) is the glucose formed per initial
  cellobiose.
- **Rates.** The enzyme concentration is constant and the law has no
  inhibition, so the rate falls as cellobiose is used up. The maximum
  depletion rate is therefore the rate at time zero, at 5 mM cellobiose and
  1 µM enzyme. It and the maximum product release rate (twice it) are the
  only outputs of the same kind as the source's initial rates, and they hold
  at loadings the source did not state.
- **pH.** The environment effect is
  `active_response_model (ph:ph_ionization_michaelis_menten)`: pH changes
  kcat and Km through the law, and the guardrail allows comparing and
  ranking the cases across pH. Conversion is fastest at pH 6 and slowest at
  pH 8. At pH 4 and 8 the 90 % threshold is not reached within the 4
  simulated hours. Temperature is the 30 °C set point and stays metadata.
- **Uncertainty.** Every input is exact, so the four samples agree and the
  5th to 95th percentile band has zero width. The deposited standard
  deviations (table below) are kept in the records' notes and are not
  propagated. The assumed loadings are single values, not ranges. A band would
  need stated ranges, for example in a [user dataset](user-data.md) of your
  own.

### Provenance

The constants come from entry 38522 and the assay loadings are assumptions
(raw export SHA-256
`a5e7ae132382e3afadcb08f1a37204fc7325fef7d02a7c455d54d7c1811ce904`):

<!-- real-example-table: bgl-records -->
| Role | Record | SABIO-RK parameter | Value | Units | Deposited SD | Maturity |
| --- | --- | --- | --- | --- | --- | --- |
| `turnover` | `tsukada_2008_bgl1a_k0_cellobiose` | `k0` | 1.81 | 1 / second | 0.05 | `literature_processed` |
| `michaelis_constant` | `tsukada_2008_bgl1a_Km0_cellobiose` | `Km0` | 6.8 | millimolar | 0.29 | `literature_processed` |
| `free_enzyme_lower_pk` | `tsukada_2008_bgl1a_pKe1` | `pKe1` | 4.4 | dimensionless | 0.2 | `literature_processed` |
| `free_enzyme_upper_pk` | `tsukada_2008_bgl1a_pKe2` | `pKe2` | 7.7 | dimensionless | 0.2 | `literature_processed` |
| `complex_lower_pk` | `tsukada_2008_bgl1a_pKes1` | `pKes1` | 4.1 | dimensionless | 0.1 | `literature_processed` |
| `complex_upper_pk` | `tsukada_2008_bgl1a_pKes2` | `pKes2` | 7.6 | dimensionless | 0.1 | `literature_processed` |
| `minimum_ph` | `tsukada_2008_bgl1a_ph_series_minimum` | `pH` (start) | 4 | dimensionless | none | `literature_processed` |
| `maximum_ph` | `tsukada_2008_bgl1a_ph_series_maximum` | `pH` (end) | 8 | dimensionless | none | `literature_processed` |
| `substrate_initial_concentration` | `bgl1a_assay_initial_cellobiose_concentration_exploratory` | none | 5 | millimolar | none | `exploratory_prior` |
| `enzyme_initial_concentration` | `bgl1a_assay_enzyme_concentration_exploratory` | none | 0.001 | millimolar | none | `exploratory_prior` |

`k0` and `Km0` are the plateau constants of the fit, not the kcat and Km at
any one pH. The last two rows are "user-supplied exploratory assumption"
records: the run's `provenance_table.csv` gives them the allowed use
`exploratory_simulation_only_not_literature_curated`. They are why the case
runs in exploratory mode only. The organism, the five pH environments, the
compatibility and the template each cite entry 38522 as well. These
`literature_metadata` and `literature_processed` records carry no kinetic
evidence of their own.

### Maturity and limitations

`limitations_table.csv` has 14 rows per pH: 5 important and 9 for
information. The important ones, for pH 5:

<!-- real-example-table: bgl-limits -->
| Category | Limitation |
| --- | --- |
| `environment_effect` | Environment response is active for ph: rates change with these conditions only through the explicit configured laws, each read once from the static environment. Every other environment condition is metadata, and the laws inherit the measured range and preparation of their source. |
| `exploratory_prior` | Exploratory priors are simulation assumptions and must not be cited as literature-curated values. |
| `ph_response` | pH changes the kinetics only through the diprotic ionization factors fitted by the source over its measured pH range; buffer identity, ionic strength, pH-dependent stability, and temperature remain outside the law. |
| `not_modelled` | This is an enzyme-source homogeneous kinetics simulation, not a whole-fungus growth, secretion, uptake, biomass, or respiration model. |
| `not_modelled` | The process is well-mixed and does not represent spatial gradients, solid-substrate accessibility, adsorption, or surface morphology. |

The rows for information add more. The loadings are assumptions because the
entry records none. Outside pH 4 to 8 the law warns rather than fails. The
source reports initial rates, not product time courses.

### Follow-up measurements

In exploratory mode the assumptions are accepted, so `suggested_experiments.csv`
is empty. Scientific mode names what is missing:

<!-- real-example-command: bgl-preflight -->
```bash
fungmod preflight --fungus "P. chrysosporium" --substrate cellobiose \
  --environment tsukada_2008_bgl1a_assay_30c_ph5 --mode scientific
```

<!-- real-example-output: bgl-preflight -->
```text
...
Preflight in scientific mode:
  #  fungus                          substrate   environment                       status              runnable
  1  phanerochaete_chrysosporium_k3  cellobiose  tsukada_2008_bgl1a_assay_30c_ph5  underparameterized  no
  case 1:
    missing parameter bgl1a_assay_initial_cellobiose_concentration; suggested experiment: Measure or curate bgl1a_assay_initial_cellobiose_concentration for the selected registry case.
    missing parameter bgl1a_assay_enzyme_concentration; suggested experiment: Measure or curate bgl1a_assay_enzyme_concentration for the selected registry case.
    blocked: missing_inputs; next action: measure_or_curate_missing_inputs

Not runnable: 1 of 1 case(s) cannot be simulated in scientific mode.
...
```

The exit code is 3. The page adds four suggestions of its own:

- **State the loadings of a real assay.** With the six constants in the
  [pH-ionization rate form](user-data.md#three-rate-forms) of a user dataset,
  and your cellobiose and enzyme concentrations as `design` values, the
  simulation describes your assay rather than an assumed one.
- **Measure time courses.** Cellobiose or glucose at known loadings at pH 4
  to 8 would test whether the initial-rate law holds over a whole
  conversion. Glucose inhibition and enzyme stability are not in the law.
  Compare such data with a run through
  [time courses](user-data.md#time-courses-comparison-and-fitting).
- **Measure a temperature series.** It would let a temperature law be bound;
  until then the case holds at 30 °C only.
- **Measure the fungus itself.** Nothing here says how much BGL1A
  *P. chrysosporium* makes, where, or under which conditions. Measurements in
  the fungus's own cultures would.

## What this page does not show

- **No validation against independent data.** Case 1's constants were fitted
  to every non-initial observation compared above. The only out-of-sample
  test is the [joint comparison](gelain-joint-benchmark.md)'s whole-condition
  holdouts quoted above, whose development screen the candidate failed. No
  independent replicate dataset is bundled
  ([independent validation](independent-validation.md)). Case 2's source
  reports initial-rate constants and no time course.
  `tests/test_bgl1a_ph_response_case.py` checks the pH 5 trajectory against
  an independent integration of the deposited formula. That tests the
  software, not the biology.
- **No prediction outside the stored scope.** Case 1 covers *T. harzianum*
  P49P11 on Celufloc 200 at 10 to 30 g/L, 29 °C, pH 5 and 0 to 96 h. Case 2
  covers BGL1A at 30 °C over pH 4 to 8.
- **Not the published Gelain model.** Case 1 runs FungMod's hydrolysis
  candidate, which describes the measurements less well than the published
  equations do.
- **Not a fungus degrading anything in case 2.** Case 2 is a recombinant
  enzyme on dissolved cellobiose. It has no growth, secretion, wood or
  insoluble cellulose.
- **No uncertainty bands.** Both cases are exact. The deposited deviations
  and the posterior intervals are recorded but not sampled.
- **Not your fungus.** The stored real cases cover two organisms. For any
  other fungus, follow the [walkthrough](walkthrough.md) route.
