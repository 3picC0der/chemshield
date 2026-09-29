# Integrated evidence (ISE-owned rows)

Regenerate everything here with one command from the repo root:

    python -m redosing.run_all

| Folder | Test | Files |
|---|---|---|
| `INT-AT-02/` | INT-S2, pH restored to 6.0-8.5 within 5 min | batch CSV + traces, all-traces plot, filled sheet |
| `INT-AT-03/` | INT-S3, no far-side excursion past 5.5/9.5 | batch CSV + traces, far-side CSV, worst-case plot, filled sheet |

INT-AT-01 and INT-AT-04 are Belal's and are not in this folder.

`chem_source` in every CSV and in every figure footer says whether the chemistry came
from Aspen or from the placeholder. It reads PLACEHOLDER until CHE delivers
`sim/aspen_tables/`.
