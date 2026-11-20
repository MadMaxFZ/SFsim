# model/dynamics.py
"""
Translational dynamics.

The ship is integrated relative to its *dominant body* D (the body whose sphere
of influence it is in). In that frame the acceleration is

    a = -mu_D r/|r|^3 + sum_k mu_k [ (s_k - r)/|s_k - r|^3 - s_k/|s_k|^3 ] + a_thrust

where s_k are the other bodies' positions relative to D. The perturbing bodies
move slowly compared with the ship's motion about D, so their positions are
frozen at the sub-step midpoint. This keeps LEO accurate while still feeling
the Sun, the Moon and the planets, and SOI transitions happen naturally.
"""

import numpy as np

from model.constants import BODIES, gm

_NAMES = list(BODIES)
_MU = np.array([gm(n) for n in _NAMES])


def accel(r_rel: np.ndarray, mu_d: float, s: np.ndarray, mu_k: np.ndarray, a_extra: np.ndarray):
    rn2 = r_rel @ r_rel
    a = (-mu_d / (rn2 * np.sqrt(rn2))) * r_rel + a_extra
    if len(mu_k):
        d = s - r_rel
        dn2 = np.einsum('ij,ij->i', d, d)
        sn2 = np.einsum('ij,ij->i', s, s)
        a = a + (mu_k / (dn2 * np.sqrt(dn2))) @ d - (mu_k / (sn2 * np.sqrt(sn2))) @ s
    return a


def rk4_step(r, v, h, mu_d, s, mu_k, a_extra):
    k1v = accel(r, mu_d, s, mu_k, a_extra)
    k1r = v
    k2v = accel(r + 0.5 * h * k1r, mu_d, s, mu_k, a_extra)
    k2r = v + 0.5 * h * k1v
    k3v = accel(r + 0.5 * h * k2r, mu_d, s, mu_k, a_extra)
    k3r = v + 0.5 * h * k2v
    k4v = accel(r + h * k3r, mu_d, s, mu_k, a_extra)
    k4r = v + h * k3v
    return (r + h / 6 * (k1r + 2 * k2r + 2 * k3r + k4r),
            v + h / 6 * (k1v + 2 * k2v + 2 * k3v + k4v))


def rk4_step_tv(r, v, t, h, mu_d, pert, a_extra):
    """RK4 with time-varying perturbers: pert(t) -> (s, mu_k) is evaluated at the
    start, midpoint and end of the step. Needed for long (heliocentric) steps,
    where planets move a large distance during one step."""
    s0, m0 = pert(t)
    s1, m1 = pert(t + 0.5 * h)
    s2, m2 = pert(t + h)
    k1v = accel(r, mu_d, s0, m0, a_extra)
    k1r = v
    k2v = accel(r + 0.5 * h * k1r, mu_d, s1, m1, a_extra)
    k2r = v + 0.5 * h * k1v
    k3v = accel(r + 0.5 * h * k2r, mu_d, s1, m1, a_extra)
    k3r = v + 0.5 * h * k2v
    k4v = accel(r + h * k3r, mu_d, s2, m2, a_extra)
    k4r = v + h * k3v
    return (r + h / 6 * (k1r + 2 * k2r + 2 * k3r + k4r),
            v + h / 6 * (k1v + 2 * k2v + 2 * k3v + k4v))


def perturbers(states: dict, dominant: str):
    """Positions of all non-dominant bodies relative to the dominant one.
    Returns (s, mu_k, names)."""
    rd = states[dominant][0]
    names = [n for n in _NAMES if n != dominant]
    s = np.array([states[n][0] - rd for n in names])
    mu_k = np.array([gm(n) for n in names])
    return s, mu_k, names


def max_step(r_rel: np.ndarray, mu_d: float, fraction: float) -> float:
    """Step limit as a fraction of the local circular period about D."""
    rn = np.linalg.norm(r_rel)
    return fraction * 2 * np.pi * np.sqrt(rn ** 3 / mu_d)


def propagate_free(solar, r, v, t, duration, fraction=0.01, max_steps=4000, sample_every=1, target=None):
    """
    Coast prediction (no thrust). Returns list of (t, r_helio, v_helio, dominant).
    If `target` is given, steps are shortened while approaching its SOI so
    encounters are not stepped over.
    Used by the trajectory predictor and navigation instruments.
    """
    out = [(t, r.copy(), v.copy(), solar.dominant_body(r, t))]
    t_end = t + duration
    steps = 0
    while t < t_end and steps < max_steps:
        dom = solar.dominant_body(r, t)
        st0 = solar.states(t)
        r_rel, v_rel = r - st0[dom][0], v - st0[dom][1]
        if np.linalg.norm(r_rel) < BODIES[dom][1]:
            break                                     # impact predicted
        h = min(max_step(r_rel, gm(dom), fraction), t_end - t)
        if target is not None and target != dom:      # refine steps near an encounter
            d = r - st0[target][0]
            dv = np.linalg.norm(v - st0[target][1]) + 1e-9
            h = min(h, max(60.0, 0.25 * (np.linalg.norm(d) - 0.5 * solar.soi.get(target, 0)) / dv))
        r_rel, v_rel = rk4_step_tv(r_rel, v_rel, t, h, gm(dom),
                                   lambda tt: perturbers(solar.states(tt), dom)[:2], np.zeros(3))
        t += h
        st1 = solar.states(t)
        r, v = r_rel + st1[dom][0], v_rel + st1[dom][1]
        steps += 1
        if steps % sample_every == 0:
            out.append((t, r.copy(), v.copy(), dom))
    return out
