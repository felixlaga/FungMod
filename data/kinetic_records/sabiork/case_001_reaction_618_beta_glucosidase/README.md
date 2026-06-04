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
