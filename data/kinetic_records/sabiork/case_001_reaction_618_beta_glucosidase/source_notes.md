# Source Notes

Source database: SABIO-RK.

Export endpoint:

```text
https://sabio.h-its.org/export-api/sabio/kinlaw-entry/json
```

REAL-001A fetch command:

```bash
python scripts/fetch_sabiork_kinlaw_entries.py \
  --query "SabioReactionID:618" \
  --output-dir data/kinetic_records/sabiork/case_001_reaction_618_beta_glucosidase/raw
```

The fetch script stores the raw export response and a `fetch_metadata.json`
file. It does not normalize SABIO-RK entries, choose a kinetic law, convert
units, or create FungMod registry records.

REAL-002A local range curation command:

```bash
python scripts/curate_sabiork_reaction_618_parameter_ranges.py \
  --input data/kinetic_records/sabiork/case_001_reaction_618_beta_glucosidase/raw/kinlaw_entries_reaction_618.json \
  --output-dir data/kinetic_records/sabiork/case_001_reaction_618_beta_glucosidase/curated
```

This curation command reads the saved raw export only. It writes
`curated/parameter_range_summary.json` with included and excluded EntryIDs,
`Km_cellobiose` bounds, and `kcat_cellobiose` bounds. It does not fetch live
SABIO-RK data, infer missing values, or convert units.
