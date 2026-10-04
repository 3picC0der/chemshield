# Khalid FDR Evidence Report

**Student:** Khalid Alenazi  
**Area:** ICS / Gateway / HMI / Cybersecurity evidence  
**Repository:** `khledb/chemshield`  
**Evidence date:** 29 September 2026  

This report summarizes the evidence collected from Khalid's ChemShield gateway and HMI work. The full formatted Word evidence report was generated as `Khalid_FDR_Evidence_Report.docx` for submission. This Markdown file records the same requirement mapping and screenshot labels inside the repository evidence folder.

## Overall result

The evidence is valid and logically consistent. The local project run showed:

- C2 gateway-only path: **PASS**
- Security test: **PASS**
- Replay/stale rejection: **100.0%** with target **>= 99%**
- Valid command acceptance: **100.0%**
- Malicious commands reaching actuator: **0**
- Audit hash chain valid: **True**
- Fail-safe tests: **PASS**
- INT-S1 timing support: **PASS**

## Requirement coverage

| Requirement / task | What must be shown | Evidence collected |
|---|---|---|
| C2 gateway-only actuator path | Every actuator command must pass through the gateway. | Main runner PASS summary, network/trust-boundary diagram, HMI accepted valid command with `Forwarded=true`, HMI rejected unsafe command with `Forwarded=false`. |
| S3 replay/stale rejection | Replayed/stale commands must be rejected at least 99% of the time. | Main runner shows replay/stale rejection `100.0%`; security plot shows attack categories rejected. |
| Secure command validation | Validate schema/session/HMAC/timestamp/nonce/sequence/role/state/dose limits. | Runner output, audit log, generated CSVs, and HMI `DOSE_LIMIT` rejection. |
| Fail-safe behavior | Faults must block new dosing and reach SAFE_HOLD within 2 seconds. | SAFE_HOLD timing plot and fail-safe PASS result. |
| Evidence package | Provide code, CSVs, plots, reports, network diagram, and HMI proof. | Project structure screenshot, generated CSV list, generated PNG list, plots, HMI screenshots. |

## Commands used

```powershell
python -m pip install -r requirements.txt
python gateway\run_all.py
Get-ChildItem -Recurse -Filter *.csv | Select-Object FullName
Get-ChildItem -Recurse -Filter *.png | Select-Object FullName
explorer .\evidence\generated\plots
python -m uvicorn hmi.app:app --reload
```

HMI URL:

```text
http://127.0.0.1:8000
```

## Screenshot list included in the Word report

1. Project Code Structure in VS Code  
2. Requirements Installed Successfully  
3. Requirements Installation Completed  
4. Main Runner PASS/FAIL Summary  
5. Generated CSV Evidence Files  
6. Generated Plot and Diagram Files  
7. Security Test Summary Plot  
8. SAFE_HOLD Timing Plot  
9. Network and Trust Boundary Diagram  
10. HMI Server Running  
11. HMI Page Running in Browser  
12. HMI Accepted Valid Dose Command  
13. HMI Rejected Unsafe Dose Command  

## Submission notes

- The generated CSV files and PNG plots should remain under `evidence/generated` because they support the screenshots in the Word evidence report.
- The HMI ACCEPT screenshot proves that a valid command is forwarded only after gateway validation.
- The HMI REJECT screenshot proves that an unsafe command is blocked and not forwarded to the actuator.
- The security plot and PASS summary support S3 by showing replay/stale and other attack categories rejected.
- The network/trust-boundary diagram supports C2 by showing the gateway as the only permitted actuator path.
- The SAFE_HOLD timing plot supports fail-safe behavior by showing timing below the 2-second target.
