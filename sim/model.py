"""ChemShield - process model, equipment parameters and truth model (design phase).
Units: volume mL (doses) / L (tank), moles in umol inside the optimiser, mmol for reagent totals.
Four reservoirs: 0.5 M and 0.005 M, HCl and NaOH (Final BOM item 2, pumps item 8)."""
import numpy as np
from scipy.optimize import brentq

# ------------------------------------------------------------------ parameters
# How fast a dose goes into the tank, mL/min. 300 is the operating rate of the old
# KPHM400 peristaltic pump (~400 mL/min max). The team doses by hand syringe now:
# replace this with the measured hand-syringe speed. It sets how long every dose takes
# in the batch, the live tank and the optimiser's time budget. S6 depends on it (on the
# pure-water table: 87.5 % at 65 mL/min, 96 % at 80, 99.7 % at 100, 100 % at 120+).
DOSE_SPEED_ML_PER_MIN = 300.0

P = dict(
    V0=5.0,            # L   working fill in the 10 L vessel (BOM item 1)
    V_hi=5.5,          # L   high-level interlock setpoint used as a tank constraint
    v_min=0.5,         # mL  metering floor per dose (to be confirmed by test T2)
    v_max=20.0,        # mL  dose cap (S2)
    dose_speed_ml_per_min=DOSE_SPEED_ML_PER_MIN,   # see above; override per run with make_par()
    t_mix=15.0, t_settle=5.0, t_read=2.0, n_read=3, t_detect=2.0,
    sd_mix=1.2, sd_settle=1.5, p_reread=0.12,
    t_hold=26.0,       # s   nominal hold + settle + 3 reads, used inside the optimiser
    sigma_pH=0.0333,   # pH  per reading (+-0.1 pH treated as 3 sigma, S8) - to be measured in T1
    stop=(6.3, 8.2),   # internal stop band
    band=(6.0, 8.5),   # INT-S2 / C3 recovery band
    ovs=(5.5, 9.5),    # INT-S3 far-side limits
    R_max=50.0,        # mmol per recovery event (C3)
    T_spec=300.0,      # s  S6 upper limit (95 % of recoveries)
    T_abort=600.0,     # s  hard abort / escalation limit used inside the optimiser
    G_v=20.0,          # mL gateway per-command cap (ICS) - placeholder = S2 cap
    G_cum=200.0,       # mL gateway per-event cumulative cap (ICS) - placeholder
    pump_3s=0.05,      # 3-sigma relative pump delivery error (to be measured in T2)
    e_abs=0.015,       # mL 3-sigma absolute pump error (to be measured in T2)
    V_3s=0.015,        # 3-sigma relative error of the fill volume (fill by mass)
    T_C=25.0,
    bias_cal=0.03,     # pH  calibration-bias allowance = acceptance tolerance of the daily 2-point buffer check
    H=4,               # max doses released per reading (dose block)
    lam_c=0.05, lam_T=0.005, lam_R=0.0,   # objective weights: per unit of scaled residual / per second
)

def robust_params(par):
    """Statistical tolerancing (RSS) of the three multiplicative error sources.
    Worst-case stacking adds the 3-sigma log-errors; RSS adds them in quadrature, which is
    the joint 3-sigma level for independent errors. k = RSS / linear sum scales each term."""
    d3 = 3 * par["sigma_pH"] / np.sqrt(par["n_read"])          # pH, 3 sigma of the mean
    terms = np.array([np.log(10) * d3, np.log1p(par["pump_3s"]), np.log1p(par["V_3s"])])
    k = np.sqrt((terms ** 2).sum()) / terms.sum() if par.get("rss", True) else 1.0
    # calibration bias is systematic, so it is added linearly on top of the random part
    par.update(delta=d3 * k + par.get("bias_cal", 0.0), eps_p=par["pump_3s"] * k, eps_V=par["V_3s"] * k,
               delta_3s=d3, k_rss=k, gamma_ws=float(np.exp(terms.sum())),
               gamma_rss=float(np.exp(np.sqrt((terms ** 2).sum()))))
    return par

def make_par(**kw):
    par = dict(P); par.update(kw); return robust_params(par)

robust_params(P)

PUMPS = [  # g = +1 removes excess acid (base reagent), -1 adds acid
    dict(id="P1", name="NaOH 0.5 M bulk",   c=0.5,   g=+1),
    dict(id="P2", name="NaOH 0.005 M fine", c=0.005, g=+1),
    dict(id="P3", name="HCl 0.5 M bulk",    c=0.5,   g=-1),
    dict(id="P4", name="HCl 0.005 M fine",  c=0.005, g=-1),
]
C = np.array([p["c"] for p in PUMPS])          # mol/L  == mmol/mL
G = np.array([p["g"] for p in PUMPS], float)
M = 1000.0 * C                                 # umol per mL

# ------------------------------------------------------------------ chemistry
def Kw(T=25.0):
    """pKw(T) quadratic through 0, 25, 50 C (14.94, 14.00, 13.26)."""
    return 10.0 ** -(14.94 - 0.0416 * T + 0.00016 * T * T)

def ph(n, V, T=25.0, CT=0.0, pKa=6.35):
    """pH of the tank. n = net excess strong acid (mol), V in L.
    CT > 0 adds a weak-acid buffer (used only for fault injection, assumption B1)."""
    kw = Kw(T); Cn = n / V
    if CT <= 0:
        if Cn > 0: h = 0.5 * (Cn + np.sqrt(Cn * Cn + 4 * kw))
        else:      h = kw / (0.5 * (-Cn + np.sqrt(Cn * Cn + 4 * kw)))
        return -np.log10(h)
    Ka = 10 ** -pKa; h7 = 1e-7
    B0 = CT * Ka / (Ka + h7) + kw / h7 - h7        # buffer salt cation: pH 7 at n = 0
    f = lambda x: 10**-x + B0 - kw * 10**x - CT * Ka / (Ka + 10**-x) - Cn
    return brentq(f, 0.0, 14.5)

def n_of(pH, V, T=25.0):
    """Inverse of ph() for the unbuffered model: net excess strong acid (mol)."""
    h = 10.0 ** (-pH); return (h - Kw(T) / h) * V

def hold(rng, par=None):
    par = par or P
    t = max(par["t_mix"], rng.normal(par["t_mix"] + 0.8, par["sd_mix"]))
    t += max(4.0, rng.normal(par["t_settle"], par["sd_settle"]))
    if rng.random() < par["p_reread"]:
        t += max(4.0, rng.normal(par["t_settle"], par["sd_settle"]))
    return t

# ------------------------------------------------------------------ truth model
class Truth:
    """Everything the controller does NOT know. Defaults = in-control process."""
    def __init__(self, rng, pump_bias_sd=0.01, pump_rand_sd=0.012, pump_abs_sd=0.005,
                 V_sd=0.005, probe_offset=0.0, conc_factor=None, bias_override=None,
                 CT=0.0, mix_incomplete=False):
        self.bias = rng.normal(0, pump_bias_sd, 4)
        if bias_override is not None:
            for k, b in bias_override.items(): self.bias[k] = b
        self.rand_sd, self.abs_sd = pump_rand_sd, pump_abs_sd
        self.V_err = rng.normal(0, V_sd)
        self.offset = probe_offset
        self.cf = np.ones(4) if conc_factor is None else np.asarray(conc_factor, float)
        self.CT = CT; self.mix_incomplete = mix_incomplete

    def deliver(self, p, v, rng):
        vt = max(0.0, v * (1 + self.bias[p] + rng.normal(0, self.rand_sd))
                 + rng.normal(0, self.abs_sd))
        return vt, vt / 1000 * C[p] * self.cf[p]          # mL, mol
