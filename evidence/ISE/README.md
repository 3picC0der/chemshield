# ISE evidence

Regenerate everything here with one command from the repo root:

    python -m redosing.run_all

| Folder | Test | Files |
|---|---|---|
| `ISE-AT-01/` | C3, reagent ≤50 mmol per event | batch CSV + traces, histogram, filled sheet |
| `ISE-AT-02/` | S6, ≥95% of recoveries within 300 s | batch CSV + traces, I-MR chart, filled sheet |
| `ISE-AT-03/` | S5, mean SUS ≥80 | study kit, scoring script (no data until Thu 1 Oct) |
| `ISE_evidence_summary.json` | every number on the sheets, in one file | |

`chem_source` in every CSV and in every figure footer says whether the chemistry came
from Aspen or from the placeholder. It reads PLACEHOLDER until CHE delivers
`sim/aspen_tables/`.
