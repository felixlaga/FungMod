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

The enzyme class `cellobiohydrolase` (EC 3.2.1.91, with the reducing-end EC
3.2.1.176 as an alias; CAZy GH6 and GH7) is categorical metadata only: it
lists the insoluble cellulose substrate classes and the homogeneous
Michaelis-Menten law that user data runs as an apparent law on a solid
substrate, and no parameter record or compatibility record carries kinetics
for it. Classes resolved to it from a genome or proteome become explicit gaps
on a solid cellulose substrate of a user dataset.

The enzyme classes `endo_xylanase` (EC 3.2.1.8; CAZy GH10 and GH11),
`glucoamylase` (EC 3.2.1.3; GH15) and `chitinase` (EC 3.2.1.14; GH18) are
categorical metadata of the same kind (IUBMB ExplorEnz entries and CAZy family
descriptions, Drula et al. 2022; `literature_metadata`; no kinetics). Each acts
on one generic solid polymer: `xylan` (bond class `beta_1_4_xylosidic`),
`starch` (`alpha_1_4_glycosidic` and `alpha_1_6_glycosidic`, listed
categorically; no branch-point model) and `chitin`
(`beta_1_4_n_acetylglucosaminidic`). These substrate records are generic
polysaccharide definitions (`exploratory_metadata`): composition varies by
source (xylan side chains, the amylose/amylopectin ratio of starch, the
acetylation of chitin) and none of it is recorded. Endo-xylanases and
chitinases release oligosaccharides, so xylan and chitin declare monomer
equivalents (`D_xylose_equivalent`, `N_acetyl_D_glucosamine_equivalent`, the
mass on complete hydrolysis); glucoamylase releases `beta_D_glucose` itself.
The three product maps in `product_maps/product_maps.yml` record the
complete-hydrolysis mass yields of the idealized homopolymers, computed from
conventional atomic weights with the formula in their provenance (1.136358,
1.111107 and 1.088659 g/g). They are reference stoichiometry: a user dataset
states its own yield, and no route fills or checks it from these maps. No
compatibility record, case template or parameter record exists for these
classes. The family map's other classes (LPMO, cellobiose dehydrogenase,
acetyl xylan esterase, laccase, class II peroxidase, alpha-amylase and pectate
lyase) and endoglucanase have no record.

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
