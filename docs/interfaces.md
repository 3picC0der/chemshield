# Interfaces (agree these at the first team meeting)

An interface is where one person's code hands data to another's. Fix the format once, then everyone builds against it. Replace the example values if the team agrees on something different.

## I1: Dose request (HMI or redosing → gateway). Owners: Khalid + Hattan
```json
{"schema_version": 1, "session_id": "operator-1", "command_id": "c-000123",
 "channel_id": "BASE_BULK", "dose_ml": 20.0, "issued_at": 1790000000.0,
 "sequence_number": 42, "nonce": "9f1c...", "authentication_tag": "<HMAC-SHA256>"}
```
Gateway reply: `{"command_id": "c-000123", "decision": "ACCEPT" | "REJECT", "reason": "REPLAY" | "STALE" | "LIMIT" | "LOCKOUT" | "MODEL_A_BLOCK" | ..., "latency_ms": 4.1}`

Channels: `ACID_BULK` (0.5 M HCl), `ACID_FINE` (0.005 M HCl), `BASE_BULK` (0.5 M NaOH), `BASE_FINE` (0.005 M NaOH).

## I2: Process state (simulator → everyone), once per second. Owners: Hattan + Abdulkarim
```json
{"t": 1790000000.0, "ph": 3.12, "temp_c": 25.0, "level_ok": true,
 "excess_mmol": -30.4, "state": "RECOVERY", "event_mmol_used": 20.0, "source": "SIM" | "PROBE"}
```

## I3: Model A call (gateway → Model A). Owners: Belal + Khalid
Input: the 16 features listed in report Section 1.3, as a dict with fixed names.
Output: `{"label": "ACCEPTABLE_CONTEXT" | "HARMFUL_CONTEXT" | "UNCERTAIN_CONTEXT", "score": 0.82, "model_version": "A-0.3", "latency_ms": 3.9}`
If there is no answer within 100 ms or anything is invalid, the result is `UNCERTAIN_CONTEXT`.

## I4: Redosing call (state → redosing). Owner: Hattan
Input: an I2 state message. Output: `{"action": "DOSE", "channel_id": "BASE_BULK", "dose_ml": 11.8}` or `{"action": "ESCALATE", "reason": "INFEASIBLE"}`. A DOSE output is sent to the gateway as a normal I1 request.

## I5: Pump command (gateway → Uno over USB serial, 115200 baud). Owners: Belal + Khalid
Pi → Uno: `HB` (heartbeat every 0.5 s), `DOSE,<seq>,<pump 1-4>,<run_ms>`, `STATUS`
Uno → Pi: `OK,<seq>`, `REJECT,<seq>,<reason>`, `DONE,<seq>,<ms_run>`, `STATUS,<estop 0/1>,<busy 0/1>`
`run_ms` = dose_ml ÷ calibrated mL per second. (If the pumps turn out to be steppers, this becomes a step count.)
The Uno rejects a command if the E-stop is pressed, a pump is already running, `run_ms` exceeds the 20 mL maximum, the last dose was under 15 s ago, or `seq` is not the previous one + 1. It stops everything if there is no heartbeat for 2 s.
