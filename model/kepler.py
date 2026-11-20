# model/kepler.py
"""
Two-body utilities: state vectors <-> classical elements, and fast
vectorised elliptic propagation used for planetary ephemerides.
"""

from dataclasses import dataclass

import numpy as np


@dataclass
class Elements:
    a: float        # semi-major axis, km (negative for hyperbolic)
    e: float        # eccentricity
    i: float        # inclination, rad
    raan: float     # longitude of ascending node, rad
    argp: float     # argument of periapsis, rad
    nu: float       # true anomaly, rad
    mu: float       # gravitational parameter, km^3/s^2

    @property
    def periapsis(self) -> float:
        return self.a * (1.0 - self.e)

    @property
    def apoapsis(self) -> float:
        return self.a * (1.0 + self.e) if self.e < 1.0 else np.inf

    @property
    def period(self) -> float:
        return 2 * np.pi * np.sqrt(self.a ** 3 / self.mu) if 0 <= self.e < 1.0 else np.inf

    @property
    def bound(self) -> bool:
        return self.e < 1.0


def rv_to_elements(r: np.ndarray, v: np.ndarray, mu: float) -> Elements:
    r = np.asarray(r, float)
    v = np.asarray(v, float)
    rn, vn = np.linalg.norm(r), np.linalg.norm(v)
    h = np.cross(r, v)
    hn = np.linalg.norm(h)
    n = np.cross([0.0, 0.0, 1.0], h)
    nn = np.linalg.norm(n)
    e_vec = ((vn ** 2 - mu / rn) * r - np.dot(r, v) * v) / mu
    e = np.linalg.norm(e_vec)
    energy = vn ** 2 / 2 - mu / rn
    a = -mu / (2 * energy) if abs(energy) > 1e-12 else np.inf
    i = np.arccos(np.clip(h[2] / hn, -1, 1)) if hn > 0 else 0.0

    if nn > 1e-10:
        raan = np.arctan2(n[1], n[0]) % (2 * np.pi)
    else:
        raan = 0.0
        n = np.array([1.0, 0.0, 0.0])
        nn = 1.0

    if e > 1e-9:
        argp = np.arccos(np.clip(np.dot(n, e_vec) / (nn * e), -1, 1))
        if e_vec[2] < 0:
            argp = 2 * np.pi - argp
        if i < 1e-10 or i > np.pi - 1e-10:      # equatorial: measure from x-axis
            argp = np.arctan2(e_vec[1], e_vec[0]) % (2 * np.pi)
            if i > np.pi / 2:
                argp = (2 * np.pi - argp) % (2 * np.pi)
        nu = np.arccos(np.clip(np.dot(e_vec, r) / (e * rn), -1, 1))
        if np.dot(r, v) < 0:
            nu = 2 * np.pi - nu
    else:                                        # circular: angle from node line
        argp = 0.0
        nu = np.arccos(np.clip(np.dot(n, r) / (nn * rn), -1, 1))
        if r[2] < 0 or (i < 1e-10 and r[1] < 0):
            nu = 2 * np.pi - nu
    return Elements(a, e, i, raan, argp, nu, mu)


def perifocal_basis(i, raan, argp):
    """Return unit vectors P (to periapsis) and Q (90 deg ahead) in the inertial frame."""
    cO, sO = np.cos(raan), np.sin(raan)
    cw, sw = np.cos(argp), np.sin(argp)
    ci, si = np.cos(i), np.sin(i)
    P = np.array([cO * cw - sO * sw * ci, sO * cw + cO * sw * ci, sw * si])
    Q = np.array([-cO * sw - sO * cw * ci, -sO * sw + cO * cw * ci, cw * si])
    return P, Q


def conic_points(el: Elements, n: int = 180, max_r: float = None) -> np.ndarray:
    """Sample the conic described by `el` (positions relative to the focus)."""
    P, Q = perifocal_basis(el.i, el.raan, el.argp)
    p = el.a * (1 - el.e ** 2)
    if el.e < 1:
        nus = np.linspace(0, 2 * np.pi, n)
    else:
        lim = np.arccos(-1 / el.e) * 0.98
        nus = np.linspace(-lim, lim, n)
    rs = p / (1 + el.e * np.cos(nus))
    if max_r is not None:
        rs = np.where(rs > max_r, np.nan, rs)
    return (rs * np.cos(nus))[:, None] * P + (rs * np.sin(nus))[:, None] * Q


class EllipticOrbitSet:
    """
    Vectorised Keplerian propagation of many elliptic orbits from a common epoch.
    Used for the planets/moons so that a whole ephemeris costs one numpy call.
    """

    def __init__(self, r0: np.ndarray, v0: np.ndarray, mu: np.ndarray):
        n = len(mu)
        self.mu = np.asarray(mu, float)
        self.a = np.zeros(n)
        self.e = np.zeros(n)
        self.M0 = np.zeros(n)
        self.nmot = np.zeros(n)
        self.P = np.zeros((n, 3))
        self.Q = np.zeros((n, 3))
        for k in range(n):
            el = rv_to_elements(r0[k], v0[k], self.mu[k])
            if not el.bound:
                raise ValueError("EllipticOrbitSet only supports bound orbits")
            self.a[k], self.e[k] = el.a, el.e
            self.P[k], self.Q[k] = perifocal_basis(el.i, el.raan, el.argp)
            E = 2 * np.arctan(np.sqrt((1 - el.e) / (1 + el.e)) * np.tan(el.nu / 2))
            self.M0[k] = E - el.e * np.sin(E)
            self.nmot[k] = np.sqrt(self.mu[k] / el.a ** 3)
        self.b_fac = np.sqrt(1 - self.e ** 2)

    def state(self, t: float):
        """Positions and velocities (relative to each orbit's focus) at t seconds past epoch."""
        M = self.M0 + self.nmot * t
        E = M.copy()
        for _ in range(8):  # Newton iterations; e < 0.25 for all catalogue bodies
            E -= (E - self.e * np.sin(E) - M) / (1 - self.e * np.cos(E))
        cE, sE = np.cos(E), np.sin(E)
        x = self.a * (cE - self.e)
        y = self.a * self.b_fac * sE
        fac = self.nmot * self.a / (1 - self.e * cE)
        vx = -fac * sE
        vy = fac * self.b_fac * cE
        r = x[:, None] * self.P + y[:, None] * self.Q
        v = vx[:, None] * self.P + vy[:, None] * self.Q
        return r, v


def time_to_periapsis(r: np.ndarray, v: np.ndarray, mu: float) -> float:
    """Time (s) until the next periapsis passage; negative if outbound on a hyperbola
    (periapsis already passed)."""
    el = rv_to_elements(r, v, mu)
    e, nu = el.e, el.nu
    if e < 1.0:
        E = 2 * np.arctan(np.sqrt((1 - e) / (1 + e)) * np.tan(nu / 2))
        M = (E - e * np.sin(E)) % (2 * np.pi)
        n = np.sqrt(mu / el.a ** 3)
        return (2 * np.pi - M) / n if M > 1e-12 else 0.0
    nu = (nu + np.pi) % (2 * np.pi) - np.pi
    F = 2 * np.arctanh(np.sqrt((e - 1) / (e + 1)) * np.tan(nu / 2))
    M = e * np.sinh(F) - F
    n = np.sqrt(mu / (-el.a) ** 3)
    return -M / n
