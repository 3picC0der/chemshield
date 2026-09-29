"""Monte Carlo harness: identical scenarios, identical noise, every controller.
Four-reservoir configuration, pump delivery error and fill-volume error included in the truth."""
import numpy as np
from . import model as Mo
from . import rdo
from .model import robust_params as model_rp
from .model import P, C, G, ph, n_of, hold

def scenarios(n, seed=7, acid_frac=0.6, vol=(40, 80), V=(4.8, 5.2)):
    rng = np.random.default_rng(seed); out = []
    for i in range(n):
        Vt = rng.uniform(*V); acid = rng.random() < acid_frac; v = rng.uniform(*vol)
        out.append(dict(id=i + 1, V=Vt, vol=v, acid=acid, n0=v / 1000 * 0.5 * (1 if acid else -1)))
    return out

def stage_pick(d_mol, side, par):
    """strongest stage that can meter d (mol); side +1 = base pumps"""
    for i in ([0, 1] if side > 0 else [2, 3]):
        v = d_mol / C[i] * 1000
        if v >= par["v_min"]: return i, min(v, par["v_max"])
    return None, 0.0

def run_event(sc, kind, rng, truth=None, par=P, ctx0=None, keep=False, max_steps=40):
    """One recovery. kind in pi | rule | adaptive | rdo | rdo_ce.
    Returns summary + per-step log (for QC)."""
    tr = truth or Mo.Truth(rng)
    V = sc["V"]; n = sc["n0"]; CT = tr.CT
    V_hat = V * (1 - tr.V_err)                    # the controller's belief about the fill
    t = par["t_detect"]; R = 0.0; Vused = 0.0; pHs = [ph(n, V, CT=CT)]; steps = []
    ctx = dict(avail=[1, 1, 1, 1], inventory=[1000.0] * 4, reserve=[100.0] * 4)
    if ctx0: ctx.update(ctx0)
    inv = list(ctx["inventory"]); I = 0.0; status = "OK"; nread = 1 if kind == "pi" else par["n_read"]
    k = 0; alarm_t = None; Vmax = V; rereads = 0
    for k in range(1, max_steps + 1):
        # --- measurement: nread probe reads; incomplete mixing makes the reads drift
        true_ph = ph(n, V, CT=CT)
        if tr.mix_incomplete and steps:
            n_prev = steps[-1]["n_before"]; fr = [0.80, 0.88, 0.95]
            reads = [ph(n_prev + (n - n_prev) * f, V, CT=CT) + tr.offset + rng.normal(0, par["sigma_pH"]) for f in fr[:nread]]
        else:
            reads = [true_ph + tr.offset + rng.normal(0, par["sigma_pH"]) for _ in range(nread)]
        m = float(np.mean(reads)); rng_r = float(np.ptp(reads)) if nread > 1 else np.nan
        nhat = n_of(m, V_hat)
        if par["stop"][0] <= m <= par["stop"][1]:
            k -= 1; break
        # --- decision
        u_cmd = None
        if kind == "pi":
            e = 7.0 - m; I = float(np.clip(I + e, -6, 6))
            side = np.sign(e); ae = abs(e)
            p = (0 if side > 0 else 2) if ae > 2.5 else (1 if side > 0 else 3)
            v = float(np.clip(abs(1.5 * e + 0.25 * I), par["v_min"], par["v_max"]))
            if k > 12: status = "PI_ABORT"; k -= 1; break
        elif kind in ("rule", "adaptive"):
            side = np.sign(nhat)
            if kind == "rule": d = abs(nhat) * 0.90
            else:
                edge = n_of(par["stop"][1] if side > 0 else par["stop"][0], V_hat)
                d = abs(nhat) / 10 ** par["delta_3s"] + abs(edge)
            p, v = stage_pick(d, side, par)
            if p is None: status = "STALL"; k -= 1; break
            if not ctx["avail"][p]: status = "FAULTED_PUMP_COMMANDED"; k -= 1; break
            if v > par["G_v"] + 1e-9: status = "GATEWAY_REJECTED"; k -= 1; break
        else:
            pr = dict(par)
            if kind == "rdo_ce": pr.update(delta=0.0, eps_p=0.0, e_abs=0.0, eps_V=0.0)
            if kind == "rdo1": pr["H"] = 1
            if kind == "rdo_cal": pr.update(pump_3s=0.11); model_rp(pr)
            cx = dict(ctx, inventory=inv, R_used=R, t_el=t, V_used=Vused)
            s = rdo.solve(m, V_hat + Vused / 1000, cx, pr)
            if not s["doses"]:
                if s["status"] in ("RE-READ", "HOLD"):
                    rereads += 1; t += par["t_settle"] + par["n_read"] * par["t_read"]
                    if rereads >= 2: k -= 1; break
                    continue
                status = s["status"]; alarm_t = alarm_t if alarm_t is not None else t; k -= 1; break
            rereads = 0
            if "ESCALATE" in s["status"] and alarm_t is None: alarm_t = t; status = s["status"]
        plan = s["doses"] if kind.startswith("rdo") else [(p, v)]
        for j, (p, v) in enumerate(plan):
            last = j == len(plan) - 1
            # --- actuation (truth)
            vt, mol = tr.deliver(p, v, rng)
            trip = None
            if kind in ("rule", "adaptive", "pi"):          # the rule sees neither inventory nor level;
                res_p = ctx["reserve"][p]                   # the PLC float-switch interlocks do
                if inv[p] - vt < res_p:
                    vt = max(inv[p] - res_p, 0.0); mol = vt / 1000 * C[p] * tr.cf[p]; trip = "LOW_LEVEL_TRIP"
                if V + vt / 1000 > par["V_hi"]:
                    vt = max((par["V_hi"] - V) * 1000, 0.0); mol = vt / 1000 * C[p] * tr.cf[p]; trip = "HIGH_LEVEL_TRIP"
            n_before = n
            if kind in ('rule', 'adaptive', 'pi') and not ctx['avail'][p]: vt, mol = 0.0, 0.0
            n = n - G[p] * mol; V += vt / 1000; inv[p] -= vt; Vmax = max(Vmax, V)
            R += v * C[p]; Vused += v
            if last:
                h = hold(rng, par) + (nread * par["t_read"] if kind != "pi" else 0.0)
            else:
                h = max(par["t_mix"], rng.normal(par["t_mix"] + 0.8, par["sd_mix"]))
            t += v / par["Q"] * 60 + h
            pH_after = ph(n, V, CT=CT); pHs.append(pH_after)
            steps.append(dict(k=k, m=m, rng=rng_r, nhat=nhat, pump=p, v=v, u=v * C[p] * 1000,
                              n_before=n_before, pH_after=pH_after, t=t, chained=not last,
                              block=len(plan)))
            if trip: status = trip; break
        if status in ("LOW_LEVEL_TRIP", "HIGH_LEVEL_TRIP"): break
    end = ph(n, V, CT=CT)
    acid = sc["n0"] > 0
    seg = pHs[1:] if len(pHs) > 1 else pHs
    far_ok = (max(seg) <= par["ovs"][1]) if acid else (min(seg) >= par["ovs"][0])
    in_band = par["band"][0] <= end <= par["band"][1]
    out = dict(t=t, R=R, ph0=pHs[0], t0=par["t_detect"],
               doses=len(steps), reads=len(set(s["k"] for s in steps)), end=end, in_band=in_band, far_ok=far_ok,
               status=status, theo=abs(sc["n0"]) * 1000, steps=steps, alarm_t=alarm_t, Vmax=Vmax, inv_min=min(inv),
               nhat0=abs(n_of(steps[0]["m"], V_hat)) * 1000 if steps else np.nan)
    return out

def bench(kind, scs, seed=11, truth_kw=None, par=P, ctx0=None):
    rng = np.random.default_rng(seed); rows = []
    for sc in scs:
        tr = Mo.Truth(rng, **(truth_kw or {}))
        rows.append(run_event(sc, kind, rng, tr, par, ctx0))
    return rows

def summary(rows, par=P):
    T = np.array([r["t"] for r in rows]); R = np.array([r["R"] for r in rows])
    th = np.array([r["theo"] for r in rows])
    ok = np.array([r["far_ok"] for r in rows]); ib = np.array([r["in_band"] for r in rows])
    N = len(rows); p = ok.mean()
    return dict(N=N, succeed=ib.mean() * 100, mean_t=T.mean(), sd_t=T.std(ddof=1),
                p95=np.percentile(T, 95), max_t=T.max(), within=(T <= par["T_spec"]).mean() * 100,
                no_ovs=p * 100, lcb=(p - 1.645 * np.sqrt(max(p * (1 - p), 1e-12) / N)) * 100,
                R_mean=R.mean(), R_max=R.max(), R_theo=th.mean(),
                doses=np.mean([r["doses"] for r in rows]), reads=np.mean([r["reads"] for r in rows]),
                c3_ok=(R <= par["R_max"]).mean() * 100)
