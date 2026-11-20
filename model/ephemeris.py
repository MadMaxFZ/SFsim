# model/ephemeris.py
"""
Solar-system environment.

Initial states come from astropy's built-in ephemeris (no download needed) at
the simulation epoch. After that each body follows a Keplerian orbit about its
parent, evaluated in closed form, so positions at any sim time cost one
vectorised call and are smooth for the integrator.
"""

import logging
from typing import Dict, List

import numpy as np
from astropy import units as u
from astropy.coordinates import get_body_barycentric_posvel, solar_system_ephemeris
from astropy.time import Time

from model.constants import BODIES, gm, radius, parent, children, equatorial_to_ecliptic
from model.kepler import EllipticOrbitSet, rv_to_elements


class SolarSystem:
    def __init__(self, epoch: Time):
        self.epoch = Time(epoch, scale='tdb')
        self.names: List[str] = [n for n in BODIES if n != 'Sun']
        self.index: Dict[str, int] = {n: k for k, n in enumerate(self.names)}
        self.soi: Dict[str, float] = {'Sun': np.inf}
        self._orbits = self._initialise()
        # cache the last evaluation (dynamics asks for the same t many times)
        self._cache_t = None
        self._cache = None
        logging.info(f"SolarSystem initialised at {self.epoch.iso} with {len(self.names)} bodies")

    def _initialise(self) -> EllipticOrbitSet:
        bary = {}
        with solar_system_ephemeris.set('builtin'):
            for name in BODIES:
                p, v = get_body_barycentric_posvel(name.lower(), self.epoch)
                bary[name] = (equatorial_to_ecliptic(p.xyz.to(u.km).value),
                              equatorial_to_ecliptic(v.xyz.to(u.km / u.s).value))
        r0, v0, mu = [], [], []
        for name in self.names:
            par = parent(name)
            r0.append(bary[name][0] - bary[par][0])
            v0.append(bary[name][1] - bary[par][1])
            mu.append(gm(par) + gm(name))
            a = rv_to_elements(r0[-1], v0[-1], mu[-1]).a
            self.soi[name] = a * (gm(name) / gm(par)) ** 0.4    # Laplace sphere of influence
        return EllipticOrbitSet(np.array(r0), np.array(v0), np.array(mu))

    # ------------------------------------------------------------------ queries
    def states(self, t: float):
        """Heliocentric (Sun-centred) positions/velocities of all bodies at t s past epoch.
        Returns dict name -> (r, v); the Sun is at the origin."""
        if t == self._cache_t:
            return self._cache
        r_rel, v_rel = self._orbits.state(t)
        out = {'Sun': (np.zeros(3), np.zeros(3))}
        for name in self.names:            # BODIES is ordered parents-first
            k = self.index[name]
            pr, pv = out[parent(name)]
            out[name] = (pr + r_rel[k], pv + v_rel[k])
        self._cache_t, self._cache = t, out
        return out

    def position(self, name: str, t: float) -> np.ndarray:
        return self.states(t)[name][0]

    def time_at(self, t: float) -> Time:
        return self.epoch + t * u.s

    def dominant_body(self, r_helio: np.ndarray, t: float) -> str:
        """Walk the SOI hierarchy (Sun -> planet -> moon) to find the body whose
        sphere of influence contains the point."""
        st = self.states(t)
        current = 'Sun'
        while True:
            for child in children(current):
                if np.linalg.norm(r_helio - st[child][0]) < self.soi[child]:
                    current = child
                    break
            else:
                return current

    def orbit_elements(self, name: str, t: float):
        st = self.states(t)
        par = parent(name)
        return rv_to_elements(st[name][0] - st[par][0], st[name][1] - st[par][1],
                              gm(par) + gm(name))

    @staticmethod
    def radius(name: str) -> float:
        return radius(name)
