# Inhibition laws and modifier gradients

A rate modifier multiplies the rate of the process it is attached to by one
dimensionless factor. This page lists the inhibition factors that exist, the
mechanism each one names, the analytic gradient each one offers to the
compiled Jacobian, and the guard that refuses two environment laws for one
condition. Nothing here ships a parameter value: every constant is a declared
`Parameter` with its own source.

## The condition every modifier declares

Every modifier declares a `condition`, one of `temperature`, `ph`, `oxygen`,
`water_activity` or `state`, and a `read_states` list of `(state, units)`
pairs. Environment-only laws read no state, so their gradient with respect to
the state vector is identically zero. State laws (inhibition, conversion
dependence) read solver states; every state they read is declared on the
wrapped process with role `modifier_input`, so assembly reports a missing state
by name instead of failing late with a `KeyError` in the compiler.

## Laws

| Law (`type`) | Base | Mechanism | Factor `a` | Constants | Law source |
| --- | --- | --- | --- | --- | --- |
| `product_inhibition` | any | noncompetitive (`K_ic = K_iu = K_i`) | `1 / (1 + P / K_i)` | `K_i` | Cornish-Bowden 2012 |
| `competitive_inhibition` | Michaelis-Menten | competitive | `(K_m + S) / (K_m (1 + I / K_i) + S)` | `K_m`, `K_i` | Cornish-Bowden 2012 |
| `substrate_inhibition` | Michaelis-Menten | Haldane | `(K_m + S) / (K_m + S + S^2 / K_i)` | `K_m`, `K_i` | Andrews 1968 Biotechnol. Bioeng. 10:707 |
| `coupled_substrate_product_inhibition` | Michaelis-Menten | squared product term plus optional Haldane | `(K_m + S) / (K_m (1 + P / K_p)^2 + S (1 + S / K_i))` | `K_m`, `K_p`, optional `K_i` | Cornish-Bowden 2012 frame; preparation-specific empirical form |
| `mixed_inhibition` | Michaelis-Menten | per inhibitor: competitive, uncompetitive, noncompetitive or mixed | `(K_m + S) / (K_m alpha + S beta)` with `alpha = 1 + sum_i I_i / K_ic,i`, `beta = 1 + sum_i I_i / K_iu,i` | `K_m`; per inhibitor `K_ic` and/or `K_iu` | Cornish-Bowden 2012; Kari et al. 2020 Biochem. J. 477:1971 |
| `substrate_reactivity` | any | empirical conversion dependence | `(S / S_ref)^n` | `S_ref`, `n` | Kadam et al. 2004 (n = 1); Yang et al. 2006, Levine et al. 2010 for the attribution caveat |

The generic product factor `1 / (1 + P / K_i)` applied to a whole rate is the
noncompetitive special case of the reversible-inhibition taxonomy. Its
`to_dict()` now says `mechanism: noncompetitive` and its assumption is named
"noncompetitive product inhibition". Competitive, uncompetitive and mixed
product inhibition change the substrate dependence and need
`mixed_inhibition` on a Michaelis-Menten base.

Every inhibition `to_dict()` emits `law_source` (the paper or textbook that
defines the algebra, fixed in code) beside `primary_source` (the study the
user names for the constants). The maturity label is declared by the user and
must be `literature_backed_software_tested` or `framework_benchmark`; a toy
or artificial benchmark must say `framework_benchmark`.

## Mixed inhibition

`mixed_inhibition` takes a list of inhibitors. Each entry names its `state`,
its `mechanism`, and only the constants that mechanism uses:

| `mechanism` | Required symbols | Effect |
| --- | --- | --- |
| `competitive` | `competitive_constant` (K_ic) | raises apparent K_m |
| `uncompetitive` | `uncompetitive_constant` (K_iu) | lowers apparent V_max and K_m together |
| `noncompetitive` | `inhibition_constant` (one symbol for both) | lowers apparent V_max |
| `mixed` | `competitive_constant` and `uncompetitive_constant` | both |

A missing constant is refused. A constant the mechanism does not use is
refused. Two mechanisms that collapse into one (mixed with `K_ic = K_iu`) are
refused with a message pointing to the noncompetitive label. Limits:
`I = 0` gives `a = 1`; competitive inhibition vanishes as `S -> inf`;
uncompetitive inhibition vanishes as `S -> 0`.

Config example (symbols only, values come from the parameter records):

```yaml
modifiers:
  - type: mixed_inhibition
    substrate_state: cellobiose
    michaelis_constant: K_m_cellobiose
    inhibitors:
      - state: glucose
        mechanism: mixed
        competitive_constant: K_ic_glucose
        uncompetitive_constant: K_iu_glucose
      - state: gluconolactone
        mechanism: noncompetitive
        inhibition_constant: K_i_gluconolactone
    primary_source: "<study that reports the constants>"
    maturity: literature_backed_software_tested
```

## Gradients and the compiled Jacobian

Every state law offers `compile_activity_gradient(context)`, the gradient of
its factor with respect to the numeric state vector:

| Law | Gradient |
| --- | --- |
| product | `da/dP = -(1 / K_i) / (1 + P / K_i)^2` |
| competitive, `D = K_m (1 + I / K_i) + S` | `da/dS = K_m (I / K_i) / D^2`; `da/dI = -(K_m + S) K_m / (K_i D^2)` |
| Haldane, `D = K_m + S + S^2 / K_i` | `da/dS = [D - (K_m + S)(1 + 2 S / K_i)] / D^2` |
| coupled, `D = K_m (1 + P / K_p)^2 + S (1 + S / K_i)` | `da/dS` as Haldane with this `D`; `da/dP = -(K_m + S) 2 K_m (1 + P / K_p) / (K_p D^2)` |
| mixed, `D = K_m alpha + S beta` | `da/dS = [D - (K_m + S) beta] / D^2`; `da/dI_i = -(K_m + S)(K_m / K_ic,i + S / K_iu,i) / D^2` |
| reactivity | `da/dS = n (S / S_ref)^(n - 1) / S_ref` for `S > 0`; at `S = 0` the right-derivative `1 / S_ref` for `n = 1` and `0` for `n > 1`; no analytic gradient for `0 <= n < 1` |

The wrapped process combines them by the product rule,
`d(v prod_k a_k)/dy = (dv/dy) prod_k a_k + v sum_k (da_k/dy) prod_{j != k} a_j`.
The result is an `analytic` Jacobian kernel whenever the base process and
every state modifier offer one. If any part offers none (a reactivity exponent
below one, or a base law without a gradient), the wrapper returns `None` and
the compiled core records a `finite_difference` kernel for that process. The
`jacobian_kernels` summary names the kind per process.

Tests check every gradient against a Richardson extrapolation of central
differences of the compiled right-hand side (one-sided at the non-negative
boundary), at interior and zero states, across state units, and for a
modifier that reads a state another process owns.

## One environment law per condition

The multiplicative composition of modifiers is the gamma concept (Zwietering
et al. 1992; Rosso et al. 1995 Appl. Environ. Microbiol. 61:610): factors for
different conditions are treated as independent and multiplied. Two laws for
one condition (an Arrhenius and a cardinal temperature law on one process)
double-count that condition. `RateModifierProcess` refuses that unless
`allow_stacked_condition_laws=True` is set explicitly; the opt-in is recorded
in `to_dict()` and as a validity limitation. In a model config the opt-in is
the process-level key `allow_stacked_condition_laws: true`; it must be a YAML
boolean, and a quoted string is refused. The process carries the
gamma-concept assumption, including its known limitation: no interaction term
between conditions, so combined stresses near growth boundaries deviate from
the product (Akkermans et al. 2017 Int. J. Food Microbiol. 240:85).

## Input checks

Every inhibition and reactivity law refuses negative, NaN and infinite states
and non-positive or non-finite constants, in the unit-aware `activity` path
and in the compiled kernel. Nothing is clipped to zero.

## Not covered

Surface (adsorption-site) inhibition on the Langmuir `surface_catalysis`
process is not represented by any of these factors. Cooperative, allosteric,
irreversible and time-dependent inhibition are absent. The `substrate_reactivity`
factor is empirical: the restart literature attributes the decline with
conversion to accessibility, hydrolysable fraction, enzyme clogging and
surface heterogeneity rather than a reactivity change of the remaining
material, and this law does not decide between those mechanisms.
