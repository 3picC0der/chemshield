"""Stealth attack: commands that pass every rule check, so only the AI Dose Guard can stop them.

    ../chemshield/.venv/bin/python -m hmi.stealth_attack --station http://10.42.0.1:8000

The attacker here has stolen the operator's signing key (an insider, or a compromised laptop).
Every command is therefore correctly signed, fresh, never replayed, on an approved bottle and
under the 20 mL cap, and sent only when the 15 s mixing wait is over. The gateway's rule checks
(signature, replay, stale, dose cap, mixing wait) all pass. What gives the attack away is the
chemistry: each dose would push a tank that is in the normal band far out of it. Only the AI
Dose Guard (Model A) judges that, and it must block every one (MODEL_A_BLOCK, 0 reach a pump).

Safety: before sending each command, this script asks the same AI Dose Guard model on this
laptop, with the tank's live pH history from the station. If the local check would NOT call the
dose harmful, the command is not sent. So the script can never put a real dose in the tank.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

from hmi.common import gateway_config, load_secret, new_dose_command, next_sequence

# (name, channel, mL, what an operator would notice)
SCENARIOS = [
    ("base overdose", "BASE_BULK", 12.0, "12 mL of 0.5 M NaOH into a neutral tank: pH would shoot above 10"),
    ("acid overdose", "ACID_BULK", 12.0, "12 mL of 0.5 M HCl into a neutral tank: pH would crash below 4"),
    ("quiet base push", "BASE_BULK", 6.0, "6 mL of 0.5 M NaOH, small enough to look routine: still leaves the band"),
]
TAG = "attack script (stealth: stolen operator key)"


def post(url: str, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}")


def get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=8) as r:
        return json.loads(r.read())


def local_verdict(model, state: dict, channel: str, ml: float) -> tuple[str, float, float | None]:
    """The AI Dose Guard's verdict on this laptop, from the station's last 30 s of pH."""
    from model_a.features import build_features
    trend = state["ph"]["trend"][-30:]
    samples = [(float(t), float(ph)) for t, ph in trend]
    feats, problems = build_features(samples, 0.0, channel, ml, [], 0.0, chem=model.chem)
    d = model.decide(feats, problems)
    return d["label"], float(d["score"]), feats.get("predicted_post_ph")


def wait_ready(base: str, timeout: float = 90.0) -> dict:
    """NORMAL, nothing pending and the mixing wait over, like a careful attacker would wait."""
    t0 = time.time()
    while True:
        s = get(base + "/api/state")
        if s["mode"] == "NORMAL" and not s.get("pending") and not s.get("mixing_s"):
            return s
        if time.time() - t0 > timeout:
            raise SystemExit(f"station not ready ({s['mode']}, mixing {s.get('mixing_s')}); try again later")
        time.sleep(1.0)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m hmi.stealth_attack", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--station", default="http://10.42.0.1:8000")
    ap.add_argument("--rounds", type=int, default=1, help="times to run the 3 scenarios (default 1)")
    a = ap.parse_args(argv)
    base = a.station.rstrip("/")

    from model_a.inference import DEFAULT_ARTIFACT, ModelA
    model = ModelA(DEFAULT_ARTIFACT)
    cfg = gateway_config(load_secret()[0])

    print("\nSTEALTH ATTACK: signed with the stolen operator key, fresh, under 20 mL, after the mixing wait.")
    print("Every rule check passes. Only the AI Dose Guard can tell these doses are dangerous.\n")
    sent = blocked = reached = skipped = 0
    for r in range(a.rounds):
        for name, ch, ml, words in SCENARIOS:
            s = wait_ready(base)
            ph = s["ph"]["mean3"]
            label, score, post_ph = local_verdict(model, s, ch, ml)
            if label != "HARMFUL_CONTEXT":
                skipped += 1
                print(f"  {name:16s} SKIPPED: at pH {ph} the guard would not block it, so it is not sent")
                continue
            seq = next_sequence(int(s["gateway"]["last_sequence_number"]))
            cmd = new_dose_command(cfg, channel_id=ch, volume_ml=ml, event_id=f"OPS-STEALTH{seq % 100000}",
                                   sequence_number=seq, source="HMI")
            out = post(base + "/api/dose", dict(cmd, _sender=TAG))
            sent += 1
            fwd = bool(out.get("forwarded_to_actuator"))
            reached += fwd
            code = out.get("reason_code", "?")
            ok = code.startswith("MODEL_A") and not fwd
            blocked += ok
            lab = (out.get("model_a_label") or label).replace("_CONTEXT", "")
            print(f"  {name:16s} {ml:4.1f} mL {ch:9s} at pH {ph:.2f}  (would go to pH {post_ph:.1f})")
            print(f"  {'':16s} {words}")
            print(f"  {'':16s} signature OK, fresh, under cap, after mixing wait -> "
                  f"{'BLOCKED by AI Dose Guard' if ok else code} ({lab}, risk {out.get('model_a_score', score):.2f})"
                  f"{'  !! REACHED THE PUMP' if fwd else ''}\n")
            time.sleep(1.0)
    print(f"Summary: {sent} stealth commands sent, {blocked} blocked by the AI Dose Guard, "
          f"{reached} reached a pump" + (f", {skipped} not sent (guard would not block)" if skipped else ""))
    return 0 if sent and blocked == sent and reached == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
