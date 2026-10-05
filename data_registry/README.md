# FungMod Registry

This registry is not a biological database. It contains toy/development
fixtures used to test registry loading, the first curated external
enzyme-kinetics pilot for SABIO-RK Reaction 618, and the first whole-organism
case: *Trichoderma harzianum* P49P11 on Celufloc 200 cellulose (Gelain 2020),
whose `culture_physiology` template composes generic process laws and whose
nine kinetic constants are `calibrated` records from a recorded retrospective
fit (artifact path and SHA-256 in each record). Those constants authorize
`scientific` simulation because they are exact and provenance-backed; they are
not experimentally validated, and three of them sit at fitting bounds.

The registry also holds the first case with an active environment-response
law: *Phanerochaete chrysosporium* K-3 beta-glucosidase BGL1A on cellobiose,
whose `ph_ionization_michaelis_menten` compatibility binds the six constants
and the pH 4-8 range of SABIO-RK Reaction 618 entry 38522 (Tsukada et al.
2008, PMID 18023045; raw export SHA-256 in every record, with the raw
export checked out byte-exact through `.gitattributes`) to the generic
diprotic pH-dependent Michaelis-Menten law. Five environment records give the
30 C assay at pH 4 to 8. The entry records no substrate or enzyme
concentration, so the assay loadings are explicit `exploratory_prior`
assumptions and the case runs in exploratory mode only; it is an
enzyme-kinetics case, not a whole-fungus model, and temperature stays
metadata for it.

The registry layer is intended to support future modelability assessment and
plug-and-play screening. It separates categorical facts, such as enzyme class
and substrate class compatibility, from numeric value specifications.

Process compatibility records may include `parameter_roles` to map registry
parameter symbols into generic process-factory roles. For example, a
surface-catalysis compatibility can map exact registry symbols to
`surface_rate_constant`, `adsorption_constant`, and `accessible_surface_area`
without introducing a substrate-specific workflow.

Exploratory registry screens may sample `range` and `distribution` value specs.
Those values remain first-class and must not be deleted, but every parameter
record also carries or derives:

- `range_scope`;
- `range_interpretation`;
- `allowed_use`.

Use those fields to distinguish selected exact values, broad literature
spreads, user-supplied exploratory priors, and software-test fixtures. A
sampleable range is not automatically calibrated uncertainty, a literature
claim, or an environmental response law.

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
