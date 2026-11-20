# shipos/ship_ai.py
"""
ShipAI: the ship's operating system.

  * attitude modes (KILLROT, PROGRADE, ... TARGET) -> autopilot
  * programs (sequenced, safety-gated actions):
        BURN  dv along a reference direction (or a fixed inertial VECTOR)
        EJECT patched-conic departure burn toward the current target
        TCM   trajectory correction: solve and fly the burn that sets up a
              target periapsis altitude (heliocentric cruise only)
        CIRC  circularise at the next periapsis ('PE') or apoapsis ('AP');
              the burn is centred on the apsis and cut off closed-loop
  * pilot inputs and pilot override (any manual input cancels the program)
  * alarms and an event log

It implements the controller protocol expected by model.api.SpaceflightSimAPI.
"""

from collections import deque
from typing import Optional

import numpy as np

from model.constants import parent
from shipos import autopilot
from shipos.guidance import reference_direction, plan_transfer, wrap_pi, unit

ATTITUDE_MODES = ['OFF', 'KILLROT', 'PROGRADE', 'RETROGRADE', 'NORMAL', 'ANTINORMAL',
                  'RADIAL_OUT', 'RADIAL_IN', 'TARGET', 'ANTITARGET', 'TGT_RETRO', 'VECTOR']
ALIGN_TOL = np.radians(1.0)
BURN_CUTOFF = 1e-4            # km/s (0.1 m/s)


class ShipAI:
    def __init__(self, name: str):
        self.name = name
        self.attitude_mode = 'KILLROT'
        self.target: Optional[str] = 'Moon'
        self.program: Optional[dict] = None
        self.pilot_torque = np.zeros(3)       # -1..1 per body axis (roll, pitch, yaw)
        self.pilot_throttle = 0.0
        self.log = deque(maxlen=8)
        self.vector = None                    # inertial unit vector for VECTOR mode
        self.alarms = set()
        self._t = 0.0

    # ---------------------------------------------------------------- pilot
    def say(self, text):
        self.log.appendleft((self._t, text))

    def set_attitude_mode(self, mode: str):
        if mode not in ATTITUDE_MODES:
            raise ValueError(mode)
        if self.program and mode != self.program.get('mode'):
            self.abort("pilot attitude change")
        self.attitude_mode = mode
        self.say(f"AP {mode}")

    def set_throttle(self, value: float):
        if self.program and self.program.get('state') == 'BURN':
            self.abort("pilot throttle override")
        self.pilot_throttle = float(np.clip(value, 0.0, 1.0))

    def set_pilot_torque(self, axes):
        axes = np.asarray(axes, float)
        if np.any(axes != 0) and self.attitude_mode != 'OFF':
            if self.program:
                self.abort("pilot RCS input")
            self.attitude_mode = 'OFF'
            self.say("AP OFF (manual RCS)")
        self.pilot_torque = axes

    def set_target(self, name: Optional[str]):
        self.target = name
        self.say(f"Target {name}")

    # -------------------------------------------------------------- programs
    def command_burn(self, dv_kms: float, mode: str = 'PROGRADE', label='BURN', c3=None):
        """Burn `dv_kms` along `mode`. If `c3` (km^2/s^2) is given the cutoff is
        closed-loop on orbital energy about the primary instead (used for ejection),
        which absorbs finite-burn and steering losses."""
        self.program = {'kind': 'BURN', 'label': label, 'mode': mode, 'dv': float(dv_kms),
                        'state': 'ALIGN', 'start_dv': None, 'c3': c3}
        self.attitude_mode = mode
        self.say(f"{label}: {dv_kms * 1000:.1f} m/s {mode}")

    def command_eject(self):
        self.program = {'kind': 'EJECT', 'label': 'EJECT', 'mode': 'PROGRADE',
                        'state': 'WAIT', 'prev_err': None}
        self.attitude_mode = 'PROGRADE'
        self.say(f"EJECT armed for {self.target}")

    def command_circularize(self, apsis: str = 'PE'):
        self.program = {'kind': 'CIRC', 'label': f'CIRC@{apsis}', 'apsis': apsis,
                        'mode': 'RETROGRADE' if apsis == 'PE' else 'PROGRADE',
                        'state': 'WAIT', 'prev_vr': None}
        self.attitude_mode = self.program['mode']
        self.say(f"CIRC armed at next {apsis}")

    def command_tcm(self, api, pe_alt_km: float = 300.0, t_arrive: float = None):
        """Solve a trajectory-correction burn toward the current target and queue it.
        `t_arrive` defaults to the predicted closest-approach time."""
        from shipos.guidance import solve_tcm
        from model.dynamics import propagate_free
        name = self.name
        if api.dominant(name) != 'Sun' or not self.target:
            self.say("TCM: only available in heliocentric cruise with a target")
            return None
        sc = api.spacecraft[name]
        solar = api.solar_system
        if t_arrive is None:
            samples = propagate_free(solar, sc.r, sc.v, api.t, 500 * 86400.0, fraction=0.004,
                                     max_steps=1500, target=self.target)
            t_arrive = min(samples, key=lambda s: np.linalg.norm(
                s[1] - solar.states(s[0])[self.target][0]))[0]
        dv = solve_tcm(solar, sc.r, sc.v, api.t, self.target, t_arrive, pe_alt_km)
        mag = float(np.linalg.norm(dv))
        self.vector = dv / mag
        self.command_burn(mag, 'VECTOR', label='TCM')
        return dv

    def abort(self, why="pilot"):
        if self.program:
            self.say(f"{self.program['label']} aborted: {why}")
        self.program = None
        self.pilot_throttle = 0.0

    # ----------------------------------------------------- controller protocol
    def max_step(self, ship, ctx):
        p = self.program
        if not p:
            return None
        if p['state'] == 'BURN' and p['kind'] == 'BURN' and p['start_dv'] is not None:
            remaining = self._remaining(ship, ctx, p)
            return max(0.02, 0.5 * remaining / max(ship.max_accel, 1e-12))
        if p['kind'] == 'EJECT' and p['state'] == 'WAIT':
            plan = self._plan(ship, ctx)
            if plan and plan.eject_req is not None:
                n = np.linalg.norm(np.cross(ctx['r_rel'], ctx['v_rel'])) / np.dot(ctx['r_rel'], ctx['r_rel'])
                dist = (-wrap_pi(plan.eject_now - self._eject_lead(ship, ctx, plan))) % (2 * np.pi)
                return max(0.5, 0.3 * dist / n)
        if p['kind'] == 'CIRC' and p['state'] == 'WAIT' and p['apsis'] == 'PE':
            from model.constants import gm
            from model.kepler import time_to_periapsis
            mu = gm(ctx['dominant'])
            r, v = ctx['r_rel'], ctx['v_rel']
            ttp = time_to_periapsis(r, v, mu)
            t_half = 0.5 * self._circ_dv_estimate(r, v, mu) / max(ship.max_accel, 1e-12)
            if ttp > t_half:
                return max(0.5, 0.3 * (ttp - t_half))
        if p['kind'] == 'CIRC' and p['state'] == 'WAIT':
            r, v = ctx['r_rel'], ctx['v_rel']
            vr = np.dot(r, v) / np.linalg.norm(r)
            n = np.linalg.norm(np.cross(r, v)) / np.dot(r, r)
            # step so the apsis is not overshot by more than ~0.5 deg of anomaly
            return max(0.5, np.radians(0.5) / n) if abs(vr) < 0.05 * np.linalg.norm(v) else None
        return None

    def pre_step(self, ship, ctx):
        self._t = ctx['t']
        p = self.program
        if ship.status != 'FLIGHT':
            ship.throttle = 0.0
            return
        if not p:
            ship.throttle = self.pilot_throttle
            return
        self.attitude_mode = p['mode']
        desired = self._desired(ctx)
        if p['kind'] == 'EJECT' and p['state'] == 'WAIT':
            ship.throttle = 0.0
            plan = self._plan(ship, ctx)
            if plan is None or plan.kind != 'INTERPLANETARY':
                self.abort("target must orbit the same star as the current primary")
                return
            err = wrap_pi(plan.eject_now - self._eject_lead(ship, ctx, plan))
            if p['prev_err'] is not None and p['prev_err'] < 0 <= err and abs(err) < 0.2:
                self.command_burn(plan.dv_depart, 'PROGRADE', label='EJECT BURN', c3=plan.v_inf ** 2)
            else:
                p['prev_err'] = err
            return
        if p['kind'] == 'CIRC' and p['state'] == 'WAIT':
            ship.throttle = 0.0
            r, v = ctx['r_rel'], ctx['v_rel']
            vr = float(np.dot(r, v))
            crossed = (p['prev_vr'] is not None and
                       ((p['apsis'] == 'PE' and p['prev_vr'] < 0 <= vr) or
                        (p['apsis'] == 'AP' and p['prev_vr'] > 0 >= vr)))
            p['prev_vr'] = vr
            if p['apsis'] == 'PE':
                # start early by half the burn so it is centred on periapsis
                from model.constants import gm
                from model.kepler import time_to_periapsis
                mu = gm(ctx['dominant'])
                ttp = time_to_periapsis(r, v, mu)
                dv_est = self._circ_dv_estimate(r, v, mu)
                t_half = 0.5 * dv_est / max(ship.max_accel, 1e-12)
                if 0 < ttp <= t_half or crossed:
                    p.update({'kind': 'BURN', 'state': 'ALIGN', 'start_dv': None, 'c3': None,
                              'dv': dv_est, 'circ': 'PE', 'label': 'CIRC BURN'})
                    self.say(f"CIRC BURN ~{dv_est * 1000:.0f} m/s, centred on Pe")
            elif crossed:
                from model.constants import gm
                mu = gm(ctx['dominant'])
                p.update({'kind': 'BURN', 'state': 'ALIGN', 'start_dv': None, 'c3': None,
                          'dv': self._circ_dv_estimate(r, v, mu, 'AP'), 'circ': 'AP', 'label': 'CIRC BURN'})
                self.say("CIRC BURN at Ap")
            return
        if p['kind'] == 'BURN':
            if p['state'] == 'ALIGN':
                ship.throttle = 0.0
                _, ang = autopilot.attitude_error(ship.q, desired)
                if ang < ALIGN_TOL and np.linalg.norm(ship.omega) < 0.01:
                    p['state'] = 'BURN'
                    p['start_dv'] = ship.dv_expended
                    self.say(f"{p['label']} ignition")
            if p['state'] == 'BURN':
                remaining = self._remaining(ship, ctx, p)
                if remaining <= BURN_CUTOFF or ship.propellant <= 0:
                    ship.throttle = 0.0
                    self.say(f"{p['label']} complete, residual {remaining * 1000:+.1f} m/s")
                    self.program = None
                    self.attitude_mode = 'KILLROT'
                    self.pilot_throttle = 0.0
                    return
                # ramp down over the last ~2 s of the burn
                ship.throttle = float(np.clip(remaining / (2.0 * ship.max_accel), 0.02, 1.0))

    def attitude(self, ship, ctx, dt, physical):
        if ship.status != 'FLIGHT':
            ship.torque_cmd = np.zeros(3)
            ship.omega = np.zeros(3)
            return
        mode = self.attitude_mode
        if mode == 'OFF':
            ship.torque_cmd = self.pilot_torque * ship.cfg.rcs_torque
            if not physical:
                from model.rotations import q_integrate
                ship.q = q_integrate(ship.q, ship.omega, dt)
            return
        desired = self._desired(ctx)
        if not physical:
            ship.torque_cmd = np.zeros(3)
            if mode == 'KILLROT':
                ship.omega = np.zeros(3)
            else:
                autopilot.snap(ship, desired)
            return
        omega_des = autopilot.rate_command(ship, None if mode == 'KILLROT' else desired)
        ship.torque_cmd = autopilot.torque_command(ship, omega_des)

    def on_event(self, ship, kind, text, t):
        self._t = t
        self.say(text)
        if kind == 'CRASH':
            self.program = None

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _circ_dv_estimate(r, v, mu, apsis='PE'):
        """|v - v_circ| evaluated at the coming apsis (from angular momentum)."""
        from model.kepler import rv_to_elements
        el = rv_to_elements(r, v, mu)
        ra = el.periapsis if apsis == 'PE' or not el.bound else el.apoapsis
        h = np.linalg.norm(np.cross(r, v))
        return abs(h / ra - np.sqrt(mu / ra))

    @staticmethod
    def _remaining(ship, ctx, p):
        """Remaining delta-v of the active burn (km/s)."""
        if p.get('circ'):
            # closed loop: drive the orbit toward circular. Remaining = speed change
            # needed to make the current speed the local circular speed, capped by
            # the eccentricity actually left.
            from model.constants import gm
            from model.kepler import rv_to_elements
            r, v = ctx['r_rel'], ctx['v_rel']
            mu = gm(ctx['dominant'])
            el = rv_to_elements(r, v, mu)
            if el.e < 0.005:
                return 0.0
            vc = np.sqrt(mu / np.linalg.norm(r))
            sp = np.linalg.norm(v)
            return (sp - vc) if p['circ'] == 'PE' else (vc - sp)
        if p.get('c3') is not None:
            from model.constants import gm
            r, v = ctx['r_rel'], ctx['v_rel']
            energy = 0.5 * (v @ v) - gm(ctx['dominant']) / np.linalg.norm(r)
            return (0.5 * p['c3'] - energy) / np.linalg.norm(v)
        return p['dv'] - (ship.dv_expended - p['start_dv'])

    def _plan(self, ship, ctx):
        solar = ctx.get('solar')
        return plan_transfer(ctx['states'], ctx['dominant'], ctx['r_rel'], ctx['v_rel'], self.target,
                             solar=solar, t=ctx['t'])

    @staticmethod
    def _eject_lead(ship, ctx, plan):
        """Required burn-start angle: centre the finite burn on the ideal impulse point
        by starting half the burn's swept orbital arc early."""
        from model.constants import G0
        ve = ship.cfg.isp * G0
        m1 = ship.mass * np.exp(-plan.dv_depart / ve)
        t_burn = (ship.mass - m1) / ship.mass_flow
        n = np.linalg.norm(np.cross(ctx['r_rel'], ctx['v_rel'])) / np.dot(ctx['r_rel'], ctx['r_rel'])
        return wrap_pi(plan.eject_req - 0.5 * n * t_burn)

    def _desired(self, ctx):
        mode = self.attitude_mode
        if mode in ('OFF', 'KILLROT'):
            return None
        if mode == 'VECTOR':
            return self.vector
        dom = ctx['dominant']
        rt = vt = None
        if mode in ('TARGET', 'ANTITARGET', 'TGT_RETRO') and self.target:
            st = ctx['states']
            rt = st[self.target][0] - st[dom][0]
            vt = st[self.target][1] - st[dom][1]
        d = reference_direction(mode, ctx['r_rel'], ctx['v_rel'], rt, vt)
        return unit(d) if d is not None else None

    def update_alarms(self, ship, telemetry: dict):
        a = set()
        if ship.status == 'CRASHED':
            a.add('CRASHED')
        if ship.propellant <= 0:
            a.add('NO FUEL')
        elif ship.propellant < 0.1 * ship.cfg.propellant:
            a.add('LOW FUEL')
        if telemetry.get('impact_predicted'):
            a.add('IMPACT PREDICTED')
        if telemetry.get('warp_limited'):
            a.add('WARP LIMITED')
        new = a - self.alarms
        for al in sorted(new):
            self.say(f"ALARM: {al}")
        self.alarms = a
