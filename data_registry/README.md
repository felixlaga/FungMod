# FungMod Toy Registry

This registry is not a biological database. The current records are
toy/development fixtures used to test registry loading, exact values, ranges,
distributions, unknowns, and categorical compatibility records.

The registry layer is intended to support future modelability assessment and
plug-and-play screening. It separates categorical facts, such as enzyme class
and substrate class compatibility, from numeric value specifications.

Value specifications may be:

- `exact`: a single unit-bearing value;
- `range`: lower and upper bounds for exploratory sampling;
- `distribution`: a named distribution such as `uniform` or `loguniform`;
- `unknown`: expected units may be known, but the value is not;
- `not_applicable`: explicitly irrelevant, with notes explaining why.

Real registry records will require provenance, literature metadata schema
validation where paper-derived evidence is used, and review before they are
added. Do not treat the toy records in this folder as empirical fungal,
substrate, enzyme, or environmental data.
