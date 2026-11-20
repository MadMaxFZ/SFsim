# model/spacecraft.py
"""Spacecraft: translational state, propulsion, and rigid-body attitude."""

import logging
from dataclasses import dataclass

import numpy as np

from model.constants import G0
from model.rotations import q_to_matrix, q_integrate


@dataclass
class ShipConfig:
    dry_mass: float = 8000.0         # kg
    propellant: float = 22000.0      # kg
    thrust: float = 120e3            # N, main engine (body +X)
    isp: float = 3500.0              # s  (high-performance nuclear-thermal class)
    rcs_torque: float = 4000.0       # N*m per axis
    size: tuple = (12.0, 4.0, 4.0)   # m, box used for the inertia tensor


class Spacecraft:
    def __init__(self, name: str, r: np.ndarray, v: np.ndarray, config: ShipConfig = None):
        self.name = name
        self.cfg = config or ShipConfig()
        self.r = np.asarray(r, float)        # km, heliocentric ecliptic
        self.v = np.asarray(v, float)        # km/s
        self.propellant = self.cfg.propellant
        self.throttle = 0.0                  # 0..1
        self.q = np.array([1.0, 0.0, 0.0, 0.0])   # body -> inertial
        self.omega = np.zeros(3)             # rad/s, body frame
        self.torque_cmd = np.zeros(3)        # N*m, body frame (from RCS)
        self.dv_expended = 0.0               # km/s
        self.status = 'FLIGHT'               # FLIGHT | CRASHED
        logging.info(f"Spacecraft {name}: wet {self.mass:.0f} kg, dV {self.delta_v_remaining * 1000:.0f} m/s")

    # ------------------------------------------------------------- properties
    @property
    def mass(self) -> float:
        return self.cfg.dry_mass + self.propellant

    @property
    def inertia(self) -> np.ndarray:
        lx, ly, lz = self.cfg.size
        m = self.mass
        return np.diag([m * (ly ** 2 + lz ** 2), m * (lx ** 2 + lz ** 2), m * (lx ** 2 + ly ** 2)]) / 12.0

    @property
    def forward(self) -> np.ndarray:
        return q_to_matrix(self.q)[:, 0]

    @property
    def mass_flow(self) -> float:
        return self.cfg.thrust / (self.cfg.isp * G0 * 1000.0)    # kg/s at full throttle

    @property
    def delta_v_remaining(self) -> float:
        return self.cfg.isp * G0 * np.log(self.mass / self.cfg.dry_mass)   # km/s

    @property
    def max_accel(self) -> float:
        return self.cfg.thrust / self.mass / 1000.0             # km/s^2

    def thrust_accel(self, dt: float = 0.0) -> np.ndarray:
        """Inertial thrust acceleration (km/s^2), averaged over dt if given."""
        if self.throttle <= 0 or self.propellant <= 0 or self.status != 'FLIGHT':
            return np.zeros(3)
        if dt > 0:
            used = min(self.propellant, self.mass_flow * self.throttle * dt)
            return self.forward * (-self.cfg.isp * G0 * np.log1p(-used / self.mass) / dt)
        return self.forward * self.max_accel * self.throttle

    # ---------------------------------------------------------------- updates
    def burn_propellant(self, dt: float) -> float:
        """Consume propellant for dt seconds; returns dv delivered (km/s)."""
        if self.throttle <= 0 or self.propellant <= 0:
            return 0.0
        used = min(self.propellant, self.mass_flow * self.throttle * dt)
        dv = -self.cfg.isp * G0 * np.log1p(-used / self.mass)
        self.propellant -= used
        self.dv_expended += dv
        if self.propellant <= 0:
            self.throttle = 0.0
        return dv

    def step_attitude(self, dt: float) -> None:
        """Euler's equations with RCS torque; exact quaternion step for the mean rate."""
        I = self.inertia
        tau = np.clip(self.torque_cmd, -self.cfg.rcs_torque, self.cfg.rcs_torque)
        w_dot = np.linalg.solve(I, tau - np.cross(self.omega, I @ self.omega))
        w_new = self.omega + w_dot * dt
        self.q = q_integrate(self.q, 0.5 * (self.omega + w_new), dt)
        self.omega = w_new
