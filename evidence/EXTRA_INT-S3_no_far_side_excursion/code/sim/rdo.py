"""RDO - Recovery Dosing Optimiser (runtime decision model, replaces the dose rule).

Robust MILP re-solved after every averaged pH reading. It plans a short block of up to H doses
that can be released back-to-back (mixing hold between doses, no re-read), subject to worst-case
no-overshoot under measurement, pump and fill-volume uncertainty, and to every operating limit.

Standard form:   min c'x   s.t.  A x <= b,   lb <= x <= ub,   y_hp in {0,1}
x = [ v_hp (H*4, mL) | y_hp (H*4) | z (umol) | w (umol) ]"""
import time, numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from .model import P, PUMPS, C, G, M, n_of

NP = 4


def idx_v(h, p): return h * NP + p
def idx_y(h, p, H): return H * NP + h * NP + p


def interval(pH_m, V_hat, par=P, T=25.0):
    """[nL, nU] (umol): the true excess given the reading +- delta and the fill-volume error.
    n(pH) is strictly decreasing, so the pH interval maps exactly onto a mole interval."""
    d, eV = par["delta"], par["eps_V"]
    hi = n_of(pH_m - d, V_hat, T) * 1e6; lo = n_of(pH_m + d, V_hat, T) * 1e6
    nU = hi * (1 + eV) if hi > 0 else hi * (1 - eV)
    nL = lo * (1 - eV) if lo > 0 else lo * (1 + eV)
    return nL, nU


def build(pH_m, V_hat, ctx, par=P, T=25.0, H=None):
    H = H or par.get("H", 4)
    NX = 2 * H * NP + 2; IZ, IW = NX - 2, NX - 1
    nL, nU = interval(pH_m, V_hat, par, T)
    nhat = n_of(pH_m, V_hat, T) * 1e6
    Nhi = n_of(par["stop"][0], V_hat, T) * 1e6          # pH 6.3 edge
    Nlo = n_of(par["stop"][1], V_hat, T) * 1e6          # pH 8.2 edge
    nc = 0.5 * (Nhi + Nlo)
    Lb, Ub = min(nL, Nlo), max(nU, Nhi)
    eps, e = par["eps_p"], par["e_abs"]
    avail = np.asarray(ctx.get("avail", [1] * 4), float)
    inv = np.asarray(ctx.get("inventory", [1e9] * 4), float)
    res = np.asarray(ctx.get("reserve", [0.0] * 4), float)
    usable = np.maximum(inv - res, 0.0)
    ucap = np.minimum(par["v_max"], par["G_v"])
    avail = np.where(usable < par["v_min"], 0.0, avail)
    tq = 60.0 / par["dose_speed_ml_per_min"]; tm = par["t_mix"]; tr = par["t_hold"] - par["t_mix"]

    rows, rhs, names = [], [], []
    def add(r, b, nm): rows.append(r); rhs.append(b); names.append(nm)
    def cum(h, coef_v, coef_y):
        r = np.zeros(NX)
        for j in range(h + 1):
            for p in range(NP):
                r[idx_v(j, p)] = coef_v[p]; r[idx_y(j, p, H)] = coef_y[p]
        return r
    kL, kU, kY = M * (G + eps), M * (-G + eps), M * e
    for h in range(H):                                   # (1)(2) robust far-side safety after each dose
        add(cum(h, kL, kY), nL - Lb, f"safety-low h={h+1}")
        add(cum(h, kU, kY), Ub - nU, f"safety-high h={h+1}")
    r = cum(H - 1, kU, kY); r[IZ] = -1; add(r, Nhi - nU, "residual z (acid side)")      # (3)
    r = cum(H - 1, kL, kY); r[IZ] = -1; add(r, nL - Nlo, "residual z (base side)")      # (4)
    r = cum(H - 1, -G * M, np.zeros(NP)); r[IW] = -1; add(r, nc - nhat, "centring w (+)")  # (5)
    r = cum(H - 1, G * M, np.zeros(NP)); r[IW] = -1; add(r, nhat - nc, "centring w (-)")   # (6)
    for h in range(H):
        for p in range(NP):                              # (7)(8) semi-continuous dose
            r = np.zeros(NX); r[idx_v(h, p)] = 1; r[idx_y(h, p, H)] = -ucap
            add(r, 0.0, f"cap h={h+1} P{p+1}")
            r = np.zeros(NX); r[idx_v(h, p)] = -1; r[idx_y(h, p, H)] = par["v_min"]
            add(r, 0.0, f"floor h={h+1} P{p+1}")
    for h in range(H):                                   # (9) one pump per dose slot
        r = np.zeros(NX); r[[idx_y(h, p, H) for p in range(NP)]] = 1
        add(r, 1.0, f"one pump h={h+1}")
    for h in range(H - 1):                               # (10) slots filled in order
        r = np.zeros(NX)
        r[[idx_y(h + 1, p, H) for p in range(NP)]] = 1; r[[idx_y(h, p, H) for p in range(NP)]] = -1
        add(r, 0.0, f"order h={h+1}")
    for p in range(NP):                                  # (11) reservoir inventory
        r = np.zeros(NX); r[[idx_v(h, p) for h in range(H)]] = 1
        add(r, usable[p], f"inventory P{p+1}")
    pos = lambda q: max(0.0, q)                          # an exhausted budget means "no more", not "infeasible"
    add(cum(H - 1, C, np.zeros(NP)), pos(par["R_max"] - ctx.get("R_used", 0.0)), "reagent C3")    # (12)
    add(cum(H - 1, np.full(NP, 1 + eps), np.full(NP, par["e_abs"])),
        pos(1000 * (par["V_hi"] - V_hat * (1 + par["V_3s"]))), "tank level")                                # (13)
    r = cum(H - 1, np.full(NP, tq), np.full(NP, tm))
    r[[idx_y(0, p, H) for p in range(NP)]] += tr          # settle + 3 reads once, after the block
    add(r, pos(par["T_abort"] - ctx.get("t_el", 0.0)), "abort time")                              # (14)
    add(cum(H - 1, np.ones(NP), np.zeros(NP)), pos(par["G_cum"] - ctx.get("V_used", 0.0)), "gateway")  # (15)

    A = np.array(rows); b = np.array(rhs)
    S = max(abs(nU), abs(nL), Nhi - Nlo)                 # scale: worst-case remaining excess
    c = np.zeros(NX); c[IZ] = 1.0 / S; c[IW] = par["lam_c"] / S
    for h in range(H):
        for p in range(NP):
            c[idx_v(h, p)] = par["lam_T"] * tq + par["lam_R"] * C[p]
            c[idx_y(h, p, H)] = par["lam_T"] * tm
    lb = np.zeros(NX)
    ub = np.r_[np.full(H * NP, ucap), np.tile(avail, H), np.inf, np.inf]
    integ = np.r_[np.zeros(H * NP), np.ones(H * NP), 0, 0]
    meta = dict(S=S, nL=nL, nU=nU, nhat=nhat, Nhi=Nhi, Nlo=Nlo, nc=nc, L=Lb, U=Ub, H=H,
                ucap=ucap, avail=avail, usable=usable, names=names)
    return c, A, b, lb, ub, integ, meta


def solve(pH_m, V_hat, ctx=None, par=P, T=25.0, H=None):
    """Returns dict(doses=[(pump, mL), ...], z, status, ms, ...).
    x = 0 is always feasible, so the solve never fails; a zero-dose optimum with z > 0 is the
    formal ESCALATE signal (no safe progress is possible under the active constraints)."""
    ctx = ctx or {}
    c, A, b, lb, ub, integ, meta = build(pH_m, V_hat, ctx, par, T, H)
    H = meta["H"]
    t0 = time.perf_counter()
    r = milp(c=c, constraints=LinearConstraint(A, -np.inf, b), integrality=integ,
             bounds=Bounds(lb, ub), options=dict(mip_rel_gap=1e-9))
    ms = (time.perf_counter() - t0) * 1000
    base = dict(A=A, b=b, c=c, meta=meta, ms=ms)
    if not r.success:
        return dict(base, doses=[], z=np.nan, status="SOLVER_FAIL", x=None)
    x = r.x; doses = []
    for h in range(H):
        for p in range(NP):
            if x[idx_y(h, p, H)] > 0.5 and x[idx_v(h, p)] > 1e-9:
                doses.append((p, float(x[idx_v(h, p)])))
    z = float(x[-2])
    # no dose chosen: either the residual is not worth one dose cycle (re-read), or a constraint blocks
    # every worthwhile dose (escalate). The threshold is the objective's own price of one dose cycle.
    worth = par["lam_T"] * par["t_hold"]
    status = "DOSE" if doses else ("ESCALATE" if z / meta["S"] > worth else ("RE-READ" if z > 1e-9 else "HOLD"))
    forecast = None
    if doses:                                            # can the recovery still finish in time?
        mt = meta; tq = 60.0 / par["dose_speed_ml_per_min"]
        prog = sum(M[p] * (v * (1 - par["eps_p"]) - par["e_abs"]) for p, v in doses)
        remain = max(mt["nU"] - mt["Nhi"], mt["Nlo"] - mt["nL"])
        blk = sum(tq * v + par["t_mix"] for p, v in doses) + (par["t_hold"] - par["t_mix"])
        if remain > prog > 0:
            forecast = ctx.get("t_el", 0.0) + remain / prog * blk
            if forecast > par["T_abort"]: status = "DOSE+ESCALATE"
            elif forecast > par["T_spec"]: status = "DOSE+S6_AT_RISK"
    return dict(base, doses=doses, z=z, w=float(x[-1]), obj=float(r.fun), status=status, x=x,
                forecast=forecast)


def closed_form(pH_m, V_hat, par=P, T=25.0):
    """Handover rule P4/P5 (adaptive, measurement error only). Used to verify the MILP.
    Pure-water rule: it takes the dose direction from the sign of n, which is only right
    when n = 0 sits inside the stop band, so use it with use_analytic_chemistry()."""
    nhat = n_of(pH_m, V_hat, T)
    beta = 10 ** par["delta"]
    edge = n_of(par["stop"][1] if nhat > 0 else par["stop"][0], V_hat, T)
    d = abs(nhat) / beta + abs(edge)
    for i in ([0, 1] if nhat > 0 else [2, 3]):
        v = d / C[i] * 1000
        if v >= par["v_min"]:
            return i, min(v, par["v_max"])
    return None, 0.0
