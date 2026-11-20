# shipos/telemetry.py
"""
Telemetry: one snapshot per frame for every instrument, so panels never
query the model directly (and never recompute the same thing twice).
The trajectory predictor runs at a lower rate because it is expensive.
"""

import time as _time

import numpy as np

from model.constants import gm, radius, parent, BODIES
from model.dynamics import propagate_free
from model.kepler import rv_to_elements
from model.rotations import q_to_matrix
from shipos.guidance import orbit_summary, plan_transfer, reference_direction, unit

PREDICT_PERIOD_S = 1.0       # real seconds between trajectory predictions


class Telemetry:
    def __init__(self, api, ship_name: str, ai):
        self.api = api
        self.name = ship_name
        self.ai = ai
        self.snapshot = {}
        self._pred = {'path': [], 'impact': False, 'closest': None, 'encounter': None}
        self._last_pred = -1e9

    def update(self) -> dict:
        api, ai = self.api, self.ai
        sc = api.spacecraft[self.name]
        ctx = api.context(self.name)
        st, dom = ctx['states'], ctx['dominant']
        r_rel, v_rel = ctx['r_rel'], ctx['v_rel']
        orb = orbit_summary(dom, r_rel, v_rel)

        now = _time.perf_counter()
        if now - self._last_pred > PREDICT_PERIOD_S:
            self._predict(sc, ctx, orb)
            self._last_pred = now

        target = None
        if ai.target and ai.target in st and ai.target != dom:
            rt, vt = st[ai.target][0] - sc.r, st[ai.target][1] - sc.v
            d = np.linalg.norm(rt)
            target = {
                'name': ai.target,
                'distance_km': d,
                'rel_speed_kms': float(np.linalg.norm(vt)),
                'closing_kms': float(-np.dot(rt, vt) / d),
                'plan': plan_transfer(st, dom, r_rel, v_rel, ai.target, api.solar_system, api.t),
                'closest': self._pred['closest'],
                'encounter': self._pred['encounter'],
            }

        # attitude relative to the prograde reference: pitch/yaw offsets of the nose
        R = q_to_matrix(sc.q)
        fwd = R[:, 0]
        pro = unit(v_rel)
        nrm = unit(np.cross(r_rel, v_rel))
        rad = np.cross(nrm, pro)
        att_pitch = np.degrees(np.arcsin(np.clip(np.dot(fwd, rad), -1, 1)))
        att_yaw = np.degrees(np.arctan2(np.dot(fwd, nrm), np.dot(fwd, pro)))
        bank = np.degrees(np.arctan2(np.dot(R[:, 1], rad), np.dot(R[:, 2], rad)))

        snap = {
            'epoch': api.epoch.iso[:19],
            't': api.t,
            'warp_req': api.time_warp,
            'warp': api.warp_achieved,
            'warp_limited': api.warp_achieved < 0.95 * api.time_warp,
            'frame_cpu_ms': api.last_frame_cpu * 1000,
            'bodies': {n: st[n][0] for n in st},
            'soi': api.solar_system.soi,
            'ship': {
                'name': sc.name,
                'r': sc.r.copy(), 'v': sc.v.copy(),
                'dominant': dom,
                'status': sc.status,
                'mass_kg': sc.mass,
                'propellant_kg': sc.propellant,
                'propellant_frac': sc.propellant / sc.cfg.propellant,
                'dv_remaining_ms': sc.delta_v_remaining * 1000,
                'dv_expended_ms': sc.dv_expended * 1000,
                'throttle': sc.throttle,
                'accel_ms2': sc.max_accel * 1000 * sc.throttle,
                'twr_max_ms2': sc.max_accel * 1000,
                'omega': sc.omega.copy(),
                'forward': fwd,
                'att_pitch_deg': att_pitch,
                'att_yaw_deg': att_yaw,
                'att_bank_deg': bank,
                'orbit': orb,
            },
            'ai': {
                'mode': ai.attitude_mode,
                'program': None if not ai.program else
                f"{ai.program['label']} [{ai.program['state']}]",
                'target': ai.target,
                'log': list(ai.log),
            },
            'target': target,
            'prediction': self._pred['path'],
            'impact_predicted': self._pred['impact'],
        }
        ai.update_alarms(sc, snap)
        snap['alarms'] = sorted(ai.alarms)
        self.snapshot = snap
        return snap

    def _predict(self, sc, ctx, orb):
        """Coast prediction. Orbits closed inside the SOI are drawn analytically by
        the map (path left empty); the numeric predictor still runs over one
        period when a target is selected, to find encounters / closest approach."""
        dom = ctx['dominant']
        soi = self.api.solar_system.soi[dom]
        tgt = self.ai.target if self.ai.target != dom else None
        closed = orb['bound'] and (orb['ap_alt_km'] + radius(dom) < soi)
        if closed and tgt is None:
            self._pred = {'path': [], 'impact': orb['pe_alt_km'] < 0,
                          'closest': None, 'encounter': None}
            return
        horizon = min(1.05 * orb['period_s'], 500 * 86400.0) if closed else 500 * 86400.0
        samples = propagate_free(self.api.solar_system, sc.r, sc.v, self.api.t, horizon,
                                 fraction=0.004, max_steps=1500, target=tgt)
        path = [(t, r, d) for t, r, v, d in samples]
        impact = False
        if samples:
            t_last, r_last, _, d_last = samples[-1]
            st = self.api.solar_system.states(t_last)
            impact = np.linalg.norm(r_last - st[d_last][0]) < radius(d_last) * 1.01
        impact = impact or (closed and orb['pe_alt_km'] < 0)
        closest = None
        encounter = None
        if tgt:
            best = None
            for t, r, v, d in samples:
                rt = self.api.solar_system.states(t)[tgt][0]
                dist = np.linalg.norm(r - rt)
                if best is None or dist < best[1]:
                    best = (t, dist)
                if d == tgt and encounter is None:
                    rr = r - rt
                    vv = v - self.api.solar_system.states(t)[tgt][1]
                    el = rv_to_elements(rr, vv, gm(tgt))
                    encounter = {'t': t, 'pe_alt_km': el.periapsis - radius(tgt), 'e': el.e}
            if best:
                closest = {'t': best[0], 'dist_km': best[1]}
        if closed and dom != 'Sun':
            path = []                                  # map draws the exact conic
        self._pred = {'path': path, 'impact': impact, 'closest': closest, 'encounter': encounter}
