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
