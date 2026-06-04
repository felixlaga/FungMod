# FungMod Registry

This registry is not a biological database. It contains toy/development
fixtures used to test registry loading and the first curated external
enzyme-kinetics pilot for SABIO-RK Reaction 618.

The registry layer is intended to support future modelability assessment and
plug-and-play screening. It separates categorical facts, such as enzyme class
and substrate class compatibility, from numeric value specifications.

Process compatibility records may include `parameter_roles` to map registry
parameter symbols into generic process-factory roles. For example, a
surface-catalysis compatibility can map exact registry symbols to
`surface_rate_constant`, `adsorption_constant`, and `accessible_surface_area`
without introducing a substrate-specific workflow.

Exploratory registry screens may sample `range` and `distribution` value specs
to generate toy configured-model runs. These ensembles are uncertainty plumbing
tests only unless records explicitly carry curated scientific provenance.

Value specifications may be:

- `exact`: a single unit-bearing value;
- `range`: lower and upper bounds for exploratory sampling;
- `distribution`: a named distribution such as `uniform` or `loguniform`;
- `unknown`: expected units may be known, but the value is not;
- `not_applicable`: explicitly irrelevant, with notes explaining why.

Curated registry records require provenance, literature metadata schema
validation where paper-derived evidence is used, and review before they are
used as scientific evidence. The SABIO-RK Reaction 618 records are an
enzyme-only soluble kinetic pilot; they are not a whole-fungus degradation
model and do not imply secretion, uptake, biomass growth, oxygen limitation,
PET chemistry, or cellulose surface morphology. Do not treat the toy records
in this folder as empirical fungal, substrate, enzyme, or environmental data.

The Reaction 618 homogeneous Michaelis-Menten compatibility requires exact
Km, kcat, initial cellobiose concentration, and enzyme concentration records
for deterministic assembly. The selected local SABIO-RK entry provides exact
Km, kcat, and Cellobiose variable `S` start concentration, but the enzyme
variable `E` has no start value. FungMod therefore stores the enzyme
concentration as an explicit `unknown` `ValueSpec` and reports the default
case as underparameterized rather than inventing a value.
