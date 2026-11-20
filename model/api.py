# model/api.py
"""
SpaceflightSimAPI: the single entry point the UI and ShipOS use to drive the model.

Responsibilities
  * simulation clock and time warp (requested vs. achieved)
  * sub-stepped integration of every spacecraft (translation + attitude)
  * SOI hand-over and impact detection
  * calling per-ship controllers (ShipAI) through a small duck-typed protocol:

        controller.max_step(ship, ctx)                -> float | None
        controller.pre_step(ship, ctx)                -> None   (throttle / programs)
        controller.attitude(ship, ctx, dt, physical)  -> None   (torque or snap)
        controller.on_event(ship, kind, text, t)      -> None

Performance notes
  The ship is stepped in its dominant body's frame. Perturbing-body positions
  are cached and refreshed every PERTURBER_REFRESH_S of sim time (or every
  step when steps are longer than that), and the per-frame work is bounded by
  CPU time rather than step count, so very high warps simply run as fast as
  the machine allows and report the achieved warp.
"""

import logging
import math
import time as _time
from typing import Dict

import numpy as np
from astropy.time import Time

from model.constants import gm, radius, children
from model.dynamics import rk4_step, rk4_step_tv, perturbers
from model.ephemeris import SolarSystem
from model.rotations import q_integrate, q_from_forward
from model.spacecraft import Spacecraft, ShipConfig

PHYSICAL_ATTITUDE_MAX_WARP = 10     # above this, attitude is held ideally (snap)
ATTITUDE_DT = 0.02                  # s, attitude integration step
STEP_FRACTION = 0.004               # sub-step as a fraction of local orbital period
PERTURBER_REFRESH_S = 300.0         # s of sim time between perturber refreshes
LONG_STEP_S = 120.0                 # steps longer than this re-evaluate perturbers per RK4 stage
FRAME_CPU_BUDGET_S = 0.025          # physics CPU time allowed per frame
MAX_FRAME_DT = 0.1                  # s of real time per frame (avoid hitches)


class StepContext(dict):
    """Per-step context for controllers. 'states' (full ephemeris) is computed lazily;
    'solar' gives access to the SolarSystem for look-ahead queries."""

    def __init__(self, solar, **kw):
        super().__init__(solar=solar, **kw)
        self._solar = solar

    def __missing__(self, key):
        if key == 'states':
            v = self._solar.states(self['t'])
            self['states'] = v
            return v
        raise KeyError(key)


class _ShipIntegrator:
    """Ship state held relative to its dominant body, plus cached perturbers."""

    def __init__(self, solar, sc, t):
        self.solar = solar
        self.dom = solar.dominant_body(sc.r, t)
        st = solar.states(t)
        self.r = sc.r - st[self.dom][0]
        self.v = sc.v - st[self.dom][1]
        self.t_pert = None
        self.s = self.mu_k = self.names = None
        self.child_idx = []

    def refresh(self, t):
        st = self.solar.states(t)
        self.s, self.mu_k, self.names = perturbers(st, self.dom)
        self.child_idx = [(k, n) for k, n in enumerate(self.names) if n in children(self.dom)]
        self.t_pert = t

    def to_helio(self, t):
        rd, vd = self.solar.states(t)[self.dom]
        return self.r + rd, self.v + vd

    def rebase(self, new_dom, t):
        rh, vh = self.to_helio(t)
        st = self.solar.states(t)
        self.dom = new_dom
        self.r, self.v = rh - st[new_dom][0], vh - st[new_dom][1]
        self.refresh(t)


class SpaceflightSimAPI:
    def __init__(self, epoch: Time):
        self.solar_system = SolarSystem(epoch)
        self.t = 0.0                                   # s since epoch (TDB)
        self.time_warp = 1.0                           # requested
        self.warp_achieved = 1.0
        self.spacecraft: Dict[str, Spacecraft] = {}
        self.controllers: Dict[str, object] = {}
        self._integ: Dict[str, _ShipIntegrator] = {}
        self._crash_rel: Dict[str, np.ndarray] = {}
        self.last_frame_cpu = 0.0

    # ------------------------------------------------------------- setup
    def add_spacecraft(self, name: str, r, v, config: ShipConfig = None) -> Spacecraft:
        if name in self.spacecraft:
            raise ValueError(f"Spacecraft {name} already exists")
        sc = Spacecraft(name, r, v, config)
        self.spacecraft[name] = sc
        self._integ[name] = _ShipIntegrator(self.solar_system, sc, self.t)
        return sc

    def add_spacecraft_in_orbit(self, name: str, body: str, altitude_km: float,
                                inclination_deg: float = 0.0, phase_deg: float = 0.0,
                                config: ShipConfig = None) -> Spacecraft:
        """Circular orbit about `body`, inclination measured from the ecliptic."""
        rb, vb = self.solar_system.states(self.t)[body]
        rr = radius(body) + altitude_km
        vc = math.sqrt(gm(body) / rr)
        ph, inc = math.radians(phase_deg), math.radians(inclination_deg)
        r_loc = rr * np.array([math.cos(ph), math.sin(ph) * math.cos(inc), math.sin(ph) * math.sin(inc)])
        v_loc = vc * np.array([-math.sin(ph), math.cos(ph) * math.cos(inc), math.cos(ph) * math.sin(inc)])
        sc = self.add_spacecraft(name, rb + r_loc, vb + v_loc, config)
        sc.q = q_from_forward(v_loc)
        return sc

    def register_controller(self, name: str, controller) -> None:
        self.controllers[name] = controller

    # ------------------------------------------------------------- queries
    @property
    def epoch(self) -> Time:
        return self.solar_system.time_at(self.t)

    def dominant(self, name: str) -> str:
        return self._integ[name].dom

    def context(self, name: str, t: float = None) -> StepContext:
        t = self.t if t is None else t
        ig = self._integ[name]
        return StepContext(self.solar_system, t=t, dominant=ig.dom, r_rel=ig.r.copy(),
                           v_rel=ig.v.copy(), warp=self.warp_achieved)

    # ------------------------------------------------------------- stepping
    def advance(self, real_dt: float) -> None:
        cpu0 = _time.perf_counter()
        real_dt = min(real_dt, MAX_FRAME_DT)
        target = self.time_warp * real_dt
        physical = self.time_warp <= PHYSICAL_ATTITUDE_MAX_WARP
        deadline = cpu0 + FRAME_CPU_BUDGET_S
        reached = target
        for name in self.spacecraft:
            reached = min(reached, self._advance_ship(name, self.t, self.t + target,
                                                      physical, deadline))
        self.t += reached
        for name in self.spacecraft:                   # sync heliocentric state for UI
            sc = self.spacecraft[name]
            if sc.status != 'CRASHED':
                sc.r, sc.v = self._integ[name].to_helio(self.t)
            else:
                ig = self._integ[name]
                rd, vd = self.solar_system.states(self.t)[ig.dom]
                sc.r, sc.v = rd + self._crash_rel[name], vd.copy()
        self.warp_achieved = reached / real_dt if real_dt > 0 else self.time_warp
        self.last_frame_cpu = _time.perf_counter() - cpu0

    def _advance_ship(self, name, t0, t_end, physical, deadline) -> float:
        sc = self.spacecraft[name]
        ig = self._integ[name]
        ctrl = self.controllers.get(name)
        if sc.status == 'CRASHED':
            return t_end - t0
        t = t0
        perf = _time.perf_counter
        while t < t_end - 1e-9:
            if perf() > deadline:
                break
            mu_d = gm(ig.dom)
            r2 = ig.r @ ig.r
            h = min(STEP_FRACTION * 2 * math.pi * math.sqrt(r2 * math.sqrt(r2) / mu_d), t_end - t)
            ctx = None
            if ctrl is not None:
                ctx = StepContext(self.solar_system, t=t, dominant=ig.dom, r_rel=ig.r, v_rel=ig.v,
                                  warp=self.time_warp)
                lim = ctrl.max_step(sc, ctx)
                if lim:
                    h = min(h, max(lim, 1e-3))
                ctrl.pre_step(sc, ctx)

            # ---- attitude
            if physical:
                n = max(1, math.ceil(h / ATTITUDE_DT))
                dta = h / n
                for _ in range(n):
                    if ctrl is not None:
                        ctrl.attitude(sc, ctx, dta, True)
                    sc.step_attitude(dta)
            elif ctrl is not None:
                ctrl.attitude(sc, ctx, h, False)
            else:
                sc.q = q_integrate(sc.q, sc.omega, h)

            # ---- translation
            if h <= LONG_STEP_S:
                # short steps: perturbers barely move, use the cached set
                if ig.t_pert is None or abs(t + 0.5 * h - ig.t_pert) > PERTURBER_REFRESH_S:
                    ig.refresh(t + 0.5 * h)
                ig.r, ig.v = rk4_step(ig.r, ig.v, h, mu_d, ig.s, ig.mu_k, sc.thrust_accel(h))
            else:
                dom = ig.dom
                ig.r, ig.v = rk4_step_tv(ig.r, ig.v, t, h, mu_d,
                                         lambda tt: perturbers(self.solar_system.states(tt), dom)[:2],
                                         sc.thrust_accel(h))
                ig.refresh(t + h)
            sc.burn_propellant(h)
            t += h

            # ---- impact
            rn = math.sqrt(ig.r @ ig.r)
            if rn < radius(ig.dom):
                sc.status = 'CRASHED'
                sc.throttle = 0.0
                self._crash_rel[name] = ig.r / rn * radius(ig.dom)
                self._event(name, 'CRASH', f"Impact on {ig.dom}", t)
                return t_end - t0

            # ---- SOI hand-over (leave current SOI, or enter a child's)
            new_dom = None
            if rn > self.solar_system.soi[ig.dom]:
                new_dom = self.solar_system.dominant_body(ig.to_helio(t)[0], t)
            else:
                for k, child in ig.child_idx:
                    d = ig.r - ig.s[k]
                    if d @ d < self.solar_system.soi[child] ** 2:
                        ig.refresh(t)                      # confirm with fresh positions
                        new_dom = self.solar_system.dominant_body(ig.to_helio(t)[0], t)
                        break
            if new_dom and new_dom != ig.dom:
                old = ig.dom
                ig.rebase(new_dom, t)
                self._event(name, 'SOI', f"SOI change: {old} -> {new_dom}", t)
        if t_end - t <= 1e-9:          # absorb round-off so the clock never stalls
            t = t_end
        return t - t0

    def _event(self, name, kind, text, t):
        logging.info(f"[{name}] {text}")
        ctrl = self.controllers.get(name)
        if ctrl is not None and hasattr(ctrl, 'on_event'):
            ctrl.on_event(self.spacecraft[name], kind, text, t)
