# SABIO-RK Reaction 618 Beta-Glucosidase Pilot

This directory stores the first local source snapshot for REAL-001. It is a
single SABIO-RK Reaction 618 kinetic-law export for:

```text
Cellobiose + H2O = 2 beta-D-Glucose
```

The files in `raw/` are source snapshots, not curated FungMod registry records.
They must not be treated as a whole-fungus degradation model, cellulose surface
model, secretion model, uptake model, or validated time-course dataset.

Phase REAL-001A only fetched and froze the raw export. Later phases selected
EntryID 35622, curated the first `kinetic_record.yml`, added registry records,
and implemented the homogeneous Michaelis-Menten pilot.

REAL-002A adds `curated/parameter_range_summary.json`, a local curation report
for literature-derived `Km_cellobiose` and `kcat_cellobiose` ranges. The report
uses only saved entries from `raw/kinlaw_entries_reaction_618.json`; it does not
call SABIO-RK. Eligible entries must be plain Michaelis-Menten, Reaction 618,
EC 3.2.1.21 beta-glucosidase, Cellobiose substrate, beta-D-Glucose/glucose
product, and must have explicit `Km` in `mM` plus explicit `kcat` in `s^(-1)`.
No unit conversion is applied.

ENV-003 (2026-10-05) consumes the pH-dependent entries differently from the
range curation: entry 38522 (Phanerochaete chrysosporium BGL1A wild type,
Michaelis-Menten (pH-dependent), kinetic-law type 24) is copied verbatim into
registry parameter records bound to the generic `ph_ionization_michaelis_menten`
process law, with the raw export's SHA-256 recorded on every record. The
entries stay excluded from `curated/parameter_range_summary.json`, which is a
plain Michaelis-Menten range report; nothing in `curated/` was regenerated.
Entry 38534 (BGL1B, `k0` "estimated from plot", no deviations) and the mutant
entries are not curated into the registry.
