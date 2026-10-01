# Interfaces

An interface is where one person's code hands data to another's. These are the formats the
code uses as of 1 Oct (the PPR rig: hand dosing, real pH probe on the Uno). The laptop HMI
and the Pi station both import `hmi/common.py`, so the command format, the key and the
reason words can't drift between them. Change a format here and in the code together, and
tell the other owner.

## I1: Dose request (laptop HMI or the station's planner → gateway). Owners: Khalid + Hattan

The laptop builds and signs it (`hmi.common.new_dose_command`); the station checks it with
Khalid's `GatewayValidator`. Sent as JSON to `POST http://<pi-ip>:8000/api/dose`.

```json
{"schema_version": 1, "session_id": "S-261-KHALID-PPR", "command_id": "HMI-3f9c1a7b2e",
 "event_id": "OPS", "timestamp_utc": "2026-10-01T09:30:00.123Z", "nonce": "9f1c...",
 "sequence_number": 42, "user_role": "operator", "action": "DOSE",
 "channel_id": "BASE_FINE", "volume_ml": 10.0, "flow_ml_min": 120.0, "mixing_time_s": 15.0,
 "recovery_plan_hash": "manual", "client_cert_fingerprint": "CERT-KHALID-DEMO",
 "hmac_sha256": "<HMAC-SHA256 of the other fields, sorted-key JSON, operator key>"}
```

- `channel_id`: `ACID_BULK` (0.5 M HCl), `ACID_FINE` (0.005 M HCl), `BASE_BULK` (0.5 M NaOH),
  `BASE_FINE` (0.005 M NaOH). The gateway computes mmol itself as `volume_ml` × molarity.
- `timestamp_utc` is the sender's clock. The gateway rejects it if it is more than 2 s old or
  2 s in the future, so the laptop and Pi clocks must agree (`python -m hmi.clock_sync`).
- `event_id`: the station's current event (`E-...`) during a recovery, else `OPS`.
- `action`: `DOSE` from the operator, `RECOVERY_DOSE` from the planner.

**Reply** (HTTP 200, or 401 when unsigned or signed with the wrong key):
```json
{"command_id": "HMI-3f9c1a7b2e", "decision": "ACCEPT", "reason_code": "ACCEPTED",
 "reason_detail": "...", "latency_ms": 4.1, "channel_id": "BASE_FINE", "volume_ml": 10.0,
 "dose_mmol": 0.05, "event_mmol_total": 0.05, "model_a_label": "ACCEPTABLE_CONTEXT",
 "model_a_score": 0.02, "model_a_latency_ms": 1.8, "group": "ACCEPT",
 "words": "Accepted by the gateway", "mode": "NORMAL", "received_utc": "...", "decided_utc": "..."}
```

**Reason codes** (the full list with the operator's words is `REASONS` in `hmi/common.py`):

| Group (what the test sheets count) | Codes |
|---|---|
| Replayed | `REUSED_NONCE`, `DUPLICATE_COMMAND_ID`, `OLD_SEQUENCE` |
| Stale | `STALE_TIMESTAMP`, `FUTURE_TIMESTAMP` |
| Over limit | `DOSE_LIMIT` (over 20 mL), `EVENT_MMOL_LIMIT` (event past 50 mmol) |
| Mixing lockout | `MIXING_LOCKOUT` (under 15 s since the last accepted dose) |
| Model A block | `MODEL_A_BLOCK`, `MODEL_A_TIMEOUT` |
| Not authorised | `INVALID_HMAC`, `MISSING_SIGNATURE`, `BAD_CLIENT_CERT`, `UNAUTHORIZED_ROLE`, `INVALID_SESSION` |
| Malformed | `SCHEMA_MISSING_FIELD`, `SCHEMA_TYPE_ERROR`, `BAD_TIMESTAMP` |
| Wrong state | `SAFE_HOLD_ACTIVE` (halted), `HEARTBEAT_LOSS`, `DOSE_PENDING`, `EVENT_MISMATCH` |

## I2: Process state, once per second. Owners: Hattan + Abdulkarim

From the simulator (`sim/live.py`, and the station's `--ph-source sim`):
```json
{"t": 1790000000.0, "ph": 3.12, "temp_c": 25.0, "level_ok": true,
 "excess_mmol": -30.4, "state": "RECOVERY", "event_mmol_used": 20.0, "source": "SIM"}
```
On the rig the pH comes from the Uno's `PH,<pH>` lines (I5) instead, labelled `PROBE`. The
station publishes its full state, including the pH, mode, event, plan and Uno link, at
`GET /api/state`.

## I3: Model A call (gateway → Model A). Owners: Belal + Khalid

`ModelAClient.predict(command, state)` in `model_a/inference.py`. Input: the I1 command (it
needs `channel_id` and `volume_ml`) and the gateway's state; the 16 features come from the
command, the probe readings and the Pi's dose log (`model_a/README.md`).
Output:
```json
{"label": "ACCEPTABLE_CONTEXT" | "HARMFUL_CONTEXT" | "UNCERTAIN_CONTEXT", "score": 0.82,
 "model_version": "A-1.0-ppr", "latency_ms": 3.9, "reason": "MODEL_RISK", "threshold": 0.35}
```
Only `ACCEPTABLE_CONTEXT` lets a dose through. No answer within 100 ms, missing or stale
probe data, a missing model file or any error gives `UNCERTAIN_CONTEXT` (fail closed).

## I4: Redosing call (state → redosing). Owner: Hattan

`redosing.planner.plan_next_dose(state)`. Input: an I2 state message. Output:
`{"action": "DOSE", "channel_id": "BASE_BULK", "dose_ml": 11.8}` or
`{"action": "ESCALATE", "reason": "INFEASIBLE"}`. The station sends each DOSE to the gateway
as an I1 `RECOVERY_DOSE` (with `volume_ml`), and the operator adds it by hand.

## I5: Uno link (station ↔ Uno over USB serial, 115200 baud). Owners: Belal + Khalid

One line per message, ending in `\n`. The firmware is `firmware/uno/chemshield_uno/`;
`hmi/mock_uno.py` is a pretend Uno that speaks the same lines.

| Pi → Uno | Meaning | Uno answers |
|---|---|---|
| `HB` | heartbeat, every 0.5 s | nothing. After 2 s without one: light off, dose ended, `HB_LOST` |
| `DOSE,<seq>,<pump 1-4>,<run_ms>` | dose approved: light on for `run_ms` (pump 1 NaOH bulk, 2 NaOH fine, 3 HCl bulk, 4 HCl fine) | `OK,<seq>`, then `DONE,<seq>,<ms>`; or `REJECT,<seq>,<ESTOP\|HALTED\|NO_HB\|BUSY\|TOO_LONG\|BAD>` |
| `STOP` | the operator pressed DOSE ADDED or cancelled: light off | `OK,STOP` |
| `MODE,NORMAL` / `MODE,RECOVERY` / `MODE,HALT` | light off / slow blink / fast blink | `OK,MODE,<mode>` (the station times this for INT-S1) |
| `STATUS` | | `STATUS,<estop 0/1>,<busy 0/1>` |

| Uno → Pi, unasked | |
|---|---|
| `PH,<pH>` | once a second, the calibrated probe reading. Any line counts as "alive"; 2 s of silence = link lost, and the station halts |
| `STATUS,1,0` / `STATUS,0,0` | the E-stop was pressed (the station halts at once) / released |
| `READY,...`, `HB_LOST`, `WARN,...` | start-up, heartbeat lost, wiring warning: logged |

Calibration lines (`CAL,<buffer pH>`, `CAL,SHOW`, `CAL,CLEAR`, `V`) are used only with the
station stopped, through `firmware/uno/uno_tool.py`.

With hand dosing the Uno does not enforce the 20 mL cap, the 15 s wait or the 50 mmol limit:
the gateway on the Pi does, before a dose ever reaches the Uno. `run_ms` only sets how long
the light stays on (`--hand-speed`, mL/s, on the station).
