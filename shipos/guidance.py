# shipos/guidance.py
"""
Navigation mathematics: reference directions, orbit description, and
transfer planning (Hohmann within a system, or patched-conic ejection
to another planet).
"""

from dataclasses import dataclass
from typing import Optional

import numpy as np

from model.constants import gm, parent, radius
from model.kepler import rv_to_elements


def unit(v):
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def wrap_pi(a):
    return (a + np.pi) % (2 * np.pi) - np.pi


def ecliptic_angle(v):
    return np.arctan2(v[1], v[0])


def reference_direction(mode: str, r_rel, v_rel, r_target_rel=None, v_target_rel=None):
    """Inertial unit vector for an autopilot attitude mode."""
    h = np.cross(r_rel, v_rel)
    table = {
        'PROGRADE':   unit(v_rel),
        'RETROGRADE': -unit(v_rel),
        'NORMAL':     unit(h),
        'ANTINORMAL': -unit(h),
        'RADIAL_OUT': unit(r_rel),
        'RADIAL_IN':  -unit(r_rel),
    }
    if r_target_rel is not None:
        table['TARGET'] = unit(r_target_rel - r_rel)
        table['ANTITARGET'] = -table['TARGET']
        rel_v = v_rel - v_target_rel
        table['TGT_RETRO'] = -unit(rel_v)        # kill velocity relative to target
    return table.get(mode)


@dataclass
class TransferPlan:
    kind: str                   # 'LOCAL' (target orbits our primary) | 'INTERPLANETARY'
    dv_depart: float            # km/s, burn from the ship's current orbit
    dv_arrive: float            # km/s, v-inf (interplanetary) or circularisation dv (local)
    tof: float                  # s
    phase_req: float            # rad, target lead angle needed at departure
    phase_now: float            # rad
    wait: float                 # s until the next window (approx.)
    eject_req: Optional[float] = None   # rad, burn point angle from primary's velocity (interplanetary)
    eject_now: Optional[float] = None
    v_inf: Optional[float] = None       # km/s, required hyperbolic excess speed (interplanetary)


def hohmann(mu, r1, r2):
    at = 0.5 * (r1 + r2)
    dv1 = np.sqrt(mu / r1) * (np.sqrt(2 * r2 / (r1 + r2)) - 1)
    dv2 = np.sqrt(mu / r2) * (1 - np.sqrt(2 * r1 / (r1 + r2)))
    tof = np.pi * np.sqrt(at ** 3 / mu)
    return dv1, dv2, tof


def plan_transfer(states, dominant: str, r_rel, v_rel, target: str,
                  solar=None, t: float = None) -> Optional[TransferPlan]:
    """Hohmann-based plan. If `solar` and `t` are given, the target's distance
    at arrival (t + tof) is used instead of its current distance."""
    if target == dominant or target is None:
        return None
    t_par = parent(target)
    rs = np.linalg.norm(r_rel)

    if t_par == dominant:                                   # e.g. Earth orbit -> Moon
        mu = gm(dominant)
        rt_vec = states[target][0] - states[dominant][0]
        rt = np.linalg.norm(rt_vec)
        dv1, dv2, tof = hohmann(mu, rs, rt)
        n_t = np.sqrt(mu / rt ** 3)
        n_s = np.sqrt(mu / rs ** 3)
        phase_req = wrap_pi(np.pi - n_t * tof)
        phase_now = wrap_pi(ecliptic_angle(rt_vec) - ecliptic_angle(r_rel))
        wait = (wrap_pi(phase_now - phase_req) % (2 * np.pi)) / abs(n_s - n_t)
        return TransferPlan('LOCAL', abs(dv1), abs(dv2), tof, phase_req, phase_now, wait)

    if dominant != 'Sun' and t_par == parent(dominant):     # e.g. Earth orbit -> Mars
        mu_s = gm(t_par)
        rd_vec = states[dominant][0] - states[t_par][0]
        vd_vec = states[dominant][1] - states[t_par][1]
        rt_vec = states[target][0] - states[t_par][0]
        r1, r2 = np.linalg.norm(rd_vec), np.linalg.norm(rt_vec)
        dv1, dv2, tof = hohmann(mu_s, r1, r2)
        if solar is not None and t is not None:
            for _ in range(3):                         # target distance at arrival
                sa = solar.states(t + tof)
                r2 = np.linalg.norm(sa[target][0] - sa[t_par][0])
                dv1, dv2, tof = hohmann(mu_s, r1, r2)
        # required heliocentric speed on the transfer ellipse, versus the primary's
        # *actual* speed (planet orbits are not circular)
        a_t = 0.5 * (r1 + r2)
        v_dep = np.sqrt(mu_s * (2 / r1 - 1 / a_t))
        v_inf = abs(v_dep - np.linalg.norm(vd_vec))
        mu = gm(dominant)
        dv_eject = np.sqrt(v_inf ** 2 + 2 * mu / rs) - np.sqrt(mu / rs)
        n_t = np.sqrt(mu_s / r2 ** 3)
        n_d = np.sqrt(mu_s / r1 ** 3)
        phase_now = wrap_pi(ecliptic_angle(rt_vec) - ecliptic_angle(rd_vec))
        if solar is not None and t is not None:
            # exact: the target must be 180 deg from our departure longitude at arrival
            sa = solar.states(t + tof)
            lam_arr = ecliptic_angle(sa[target][0] - sa[t_par][0])
            err = wrap_pi(lam_arr - ecliptic_angle(rd_vec) - np.pi)
            phase_req = wrap_pi(phase_now - err)
        else:
            phase_req = wrap_pi(np.pi - n_t * tof)
        wait = (wrap_pi(phase_now - phase_req) % (2 * np.pi)) / abs(n_d - n_t)
        # burn-point geometry for the escape hyperbola
        e_h = 1 + rs * v_inf ** 2 / mu
        nu_inf = np.arccos(-1 / e_h)
        asym = ecliptic_angle(vd_vec) if r2 > r1 else ecliptic_angle(-vd_vec)
        eject_req = wrap_pi(asym - nu_inf - ecliptic_angle(vd_vec))
        eject_now = wrap_pi(ecliptic_angle(r_rel) - ecliptic_angle(vd_vec))
        return TransferPlan('INTERPLANETARY', dv_eject, abs(dv2), tof,
                            phase_req, phase_now, wait, eject_req, eject_now, v_inf)
    return None


def orbit_summary(dominant: str, r_rel, v_rel) -> dict:
    mu = gm(dominant)
    el = rv_to_elements(r_rel, v_rel, mu)
    rn = np.linalg.norm(r_rel)
    return {
        'body': dominant,
        'a_km': el.a,
        'e': el.e,
        'i_deg': np.degrees(el.i),
        'raan_deg': np.degrees(el.raan),
        'argp_deg': np.degrees(el.argp),
        'nu_deg': np.degrees(el.nu),
        'pe_alt_km': el.periapsis - radius(dominant),
        'ap_alt_km': (el.apoapsis - radius(dominant)) if el.bound else np.inf,
        'period_s': el.period,
        'alt_km': rn - radius(dominant),
        'speed_kms': float(np.linalg.norm(v_rel)),
        'v_circ_kms': float(np.sqrt(mu / rn)),
        'v_esc_kms': float(np.sqrt(2 * mu / rn)),
        'radial_kms': float(np.dot(r_rel, v_rel) / rn),
        'bound': el.bound,
    }


# --------------------------------------------------------------------------
# Trajectory correction manoeuvre (heliocentric cruise)
# --------------------------------------------------------------------------
def _coast_helio(solar, r, v, t0, t1, exclude, steps=600):
    """Sun-centred RK4 coast from t0 to t1, perturbed by every planet except
    `exclude` (the target is treated as massless so the aim point is linear)."""
    from model.dynamics import rk4_step_tv, perturbers

    def pert(tt):
        s, mu_k, names = perturbers(solar.states(tt), 'Sun')
        keep = [k for k, n in enumerate(names) if n != exclude]
        return s[keep], mu_k[keep]

    # geometric step growth: fine near departure (Earth still close), coarse later
    span = t1 - t0
    w = np.geomspace(1.0, 20.0, steps)
    hs = span * w / w.sum()
    t = t0
    for h in hs:
        r, v = rk4_step_tv(r, v, t, h, gm('Sun'), pert, np.zeros(3))
        t += h
    return r, v


def solve_tcm(solar, r, v, t, target, t_arrive, pe_alt_km=300.0, iters=8,
              accel_kms2=None):
    """
    B-plane targeting. Seeds a delta-v vector (km/s, heliocentric)
    that places the ship's miss vector, perpendicular to the approach velocity,
    at the impact parameter giving a periapsis altitude of `pe_alt_km`.
    Arrival timing is left free. The target is treated as massless during the
    seed solve. Refine against the incoming periapsis predicted with target
    gravity, approximating a finite burn by an impulse at its midpoint.
    Returns None if a candidate cannot be verified. Requires solar cruise.
    """
    if not np.isfinite(t_arrive) or t_arrive <= t or not np.isfinite(pe_alt_km) or pe_alt_km < 0:
        return None
    mu_t = gm(target)
    rp = radius(target) + pe_alt_km

    def miss(dv):
        rr, vv = _coast_helio(solar, r, v + dv, t, t_arrive, target, steps=600)
        st = solar.states(t_arrive)[target]
        return rr - st[0], vv - st[1]

    dv = np.zeros(3)
    for _ in range(iters):
        m, vrel = miss(dv)
        vinf = np.linalg.norm(vrel)
        if not np.isfinite(vinf) or vinf < 1e-9:
            return None
        u_v = vrel / vinf
        # B-plane basis
        axis = np.eye(3)[np.argmin(np.abs(u_v))]
        e1 = unit(np.cross(u_v, axis))
        e2 = np.cross(u_v, e1)
        B = np.array([m @ e1, m @ e2])
        b = rp * np.sqrt(1 + 2 * mu_t / (rp * vinf ** 2))
        aim = B / np.linalg.norm(B) * b if np.linalg.norm(B) > 1.0 else np.array([b, 0.0])
        f = B - aim
        if np.linalg.norm(f) < 50.0:
            break
        J = np.zeros((2, 3))
        eps = 1e-4
        for k in range(3):
            d = np.zeros(3)
            d[k] = eps
            mk, _ = miss(dv + d)
            J[:, k] = (np.array([mk @ e1, mk @ e2]) - B) / eps
        step = -np.linalg.pinv(J) @ f                 # minimum-norm correction
        n = np.linalg.norm(step)
        if n > 0.5:
            step *= 0.5 / n
        dv = dv + step
    return _refine_tcm(solar, r, v, t, target, t_arrive, pe_alt_km, dv, accel_kms2)


def _refine_tcm(solar, r, v, t, target, t_arrive, pe_alt_km, seed, accel_kms2):
    """Differentially correct incoming osculating periapsis at SOI entry."""
    from model.dynamics import propagate_free, perturbers, rk4_step_tv

    mu_t = gm(target)
    lead = t_arrive - t
    duration = lead + 60 * 86400.0
    # Finite-difference impulse sized to move the arrival by roughly 10 km.
    eps = float(np.clip(10.0 / lead, 5e-7, 1e-4))

    def periapsis(dv):
        half = 0.5 * np.linalg.norm(dv) / accel_kms2 if accel_kms2 else 0.0
        if half >= lead:
            return None
        if half:
            rr, vv = rk4_step_tv(
                r, v, t, half, gm('Sun'),
                lambda tt: perturbers(solar.states(tt), 'Sun')[:2], np.zeros(3))
        else:
            rr, vv = r, v
        tt, rr, vv, dom = propagate_free(
            solar, rr, vv + dv, t + half, duration - half, fraction=0.001,
            max_steps=4000, sample_every=4001, target=target, stop_at_target=True)[-1]
        if dom != target:
            return None
        rt, vt = solar.states(tt)[target]
        rr, vv = rr - rt, vv - vt
        if rr @ vv >= 0:
            return None
        # p/(1+e) is well conditioned even for nearly parabolic encounters.
        h = np.cross(rr, vv)
        e = np.linalg.norm(np.cross(vv, h) / mu_t - unit(rr))
        return (h @ h) / (mu_t * (1.0 + e)) - radius(target)

    coast_alt = periapsis(np.zeros(3))
    if coast_alt is not None and abs(coast_alt - pe_alt_km) <= 5.0:
        return np.zeros(3)
    dv = seed
    alt = periapsis(dv)
    if alt is None:
        return None
    for _ in range(8):
        err = alt - pe_alt_km
        if abs(err) <= 5.0:
            return dv
        nearby = [periapsis(dv + eps * axis) for axis in np.eye(3)]
        if any(a is None for a in nearby):
            return None
        gradient = (np.array(nearby) - alt) / eps
        norm2 = gradient @ gradient
        if not np.isfinite(norm2) or norm2 == 0:
            return None
        step = -err * gradient / norm2
        for scale in (1.0, 0.5, 0.25, 0.125):
            trial = dv + scale * step
            trial_alt = periapsis(trial)
            if trial_alt is not None and abs(trial_alt - pe_alt_km) < abs(err):
                dv, alt = trial, trial_alt
                break
        else:
            return None
    return dv if abs(alt - pe_alt_km) <= 5.0 else None
