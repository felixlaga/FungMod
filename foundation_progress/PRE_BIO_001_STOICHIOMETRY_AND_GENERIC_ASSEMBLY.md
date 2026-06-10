# PRE-BIO-001: Stoichiometry and Generic Assembly Hardening

## Goal

Fix the remaining blockers before adding new biology.

## Required

```text
1. Make stoichiometric product-map yields affect product dynamics.
2. Add a Reaction 618 test:
   beta-D-glucose formed ≈ 2 × cellobiose consumed.
3. Remove or reduce BIO-001-specific branching.
4. Move case-specific metadata into templates/registry records.
5. Add a test proving a new surface-catalysis template can assemble without a record-ID-specific Python branch.
6. Isolate toy/test templates from public researcher-facing paths.
```

## Do not

```text
- add new biology;
- fetch new data;
- implement CURATION-001;
- add whole-fungus growth;
- add PET/lignin/full lignocellulose.
```

## Acceptance

BIO-002 is allowed only when product stoichiometry and generic assembly are safe.
