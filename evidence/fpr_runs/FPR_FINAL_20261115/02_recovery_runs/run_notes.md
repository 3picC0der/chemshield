# FPR evidence record, 15 Nov 2026 (session 20261115-210905-uno), operator notes

| Run | Spill | Notes |
|---|---|---|
| E-0001 | 6 mL 0.5 M HCl (3 mmol) | by the impeller, probe far side |
| E-0002 | 6 mL 0.5 M HCl (3 mmol) | same |
| E-0003 | 12 mL 0.5 M HCl (6 mmol), in two pours | first 6 mL only reached pH 6.16 (above the 6.0 trigger), second 6 mL took it to 3.7. Buffer nearly used up; correction peaked at 9.48 (< 9.5) |

Between E-0002 and E-0003: manual 0.2 mL NaOH 0.5 M accepted; 2.0 mL NaOH 0.5 M request blocked by the AI Dose Guard (HARMFUL) at 18:50 UTC.
After E-0003: tank re-buffered with 10 mL NaHCO3 stock (0.5 M) and trimmed back to ~7 with 0.5 M HCl.
| E-0004 | unknown (acid ran out) | one probe reading of 2.25 (acid stream hit the probe), tank itself only ~5.9; recovered in 2 s with 2.54 mL base, ended at 7.5. Recommended "leave out". HALT 19:20:25 / RESUME 19:20:31 by operator. |

19:14:32 UTC: 25 mL NaOH 0.005 M request rejected, DOSE_LIMIT (S2).
| E-0005 | none (not a spill) | pH rose 7.5 → 8.4 around 19:22 after a manual top-up, crept to 8.51 and triggered a base event. HMI showed RECOVERY 10.2 s late (tab in background), INT-S1 FAIL for this event. Left out by Claude at Belal's request context ("Not a spill"). |
| (new session) E-0001 = counted run 4 | 6 mL 0.5 M HCl from the panel | station restarted after the Uno panel was used to dispense acid. pH 4.45 low, 0.34 s, in band 31 s, 4.89 mmol, peak 7.33 |
| (session 230411) E-0001 = counted run 5 | 8 mL 0.5 M HCl | probe low 5.84, INT-S1 6.8 ms, in band 7 s, closed 34 s, 3.86 mmol |

Scorecard after 5 counted runs (20:09 UTC): INT-S1 5/5 worst 496 ms; INT-S2 5/5 worst 42 s; INT-S3 5/5 peak 9.49; S6 5/5 worst 141 s; C3 max 10.08 mmol; S2 PASS (3 over-20 mL rejects, 1 lockout hold); S4 32 doses slowest 2.3 ms.

S1 hold attempt 1 (20:16-20:26 UTC): FAIL on one reading of 6.11 at 42.5 s (bumped probe), 599/600 in band. CSV in ../20261115_s1_hold_attempt1.
S1 hold attempt 2 (20:37:59-20:47:59 UTC): PASS, 599 readings 6.85-7.14, 0 outside, 0 doses. CSV in ../20261115_s1_hold.
S3: 1,000 stale (age 5 s) -> 1,000 STALE; 1,000 replay-now -> 1,000 REUSED_NONCE; fpr.sh attack 150/150 blocked (forged, unsigned, tampered, stale, replay). Outputs in ../20261115_s3_attacks. The replay-now originals are real 1 mL BASE_FINE doses; 6 were accepted, the rest were held by the 15 s mixing wait (that is why S2 shows ~954 lockout holds).
S4: 1,000 requests on the Pi, max 1.61 ms, mean 0.88 ms. Outputs in ../20261115_s4_latency_1000.
Final HMI scorecard (20:50 UTC): every HMI item PASS. See scorecard_2050utc.txt and spec_scorecard.csv.
