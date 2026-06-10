import logging
from dataclasses import dataclass, field

import numpy as np
from astropy import units as u
from poliastro.twobody import Orbit


@dataclass
class SpacecraftRotation:
    """Spacecraft rotational state."""
    quaternion: np.ndarray = field(default_factory=lambda: np.array([1.0, 0.0, 0.0, 0.0]))
    angular_velocity: np.ndarray = field(default_factory=lambda: np.zeros(3))  # rad/s, plain array
    inertia_tensor: np.ndarray = np.eye(3)

    def propagate(self, time_step: u.s, torque: u.Quantity, inertia_tensor: np.ndarray) -> None:
        """
        Propagate rotational state forward in time.

        Args:
            time_step: Time step for propagation
            torque: Applied torque in N·m (astropy Quantity, shape (3,))
            inertia_tensor: Moment of inertia tensor in kg·m² (plain numpy array, shape (3,3))
        """
        dt = float(time_step.to(u.s).value)

        # torque values in N·m
        tau = torque.to(u.N * u.m).value  # shape (3,), plain float array

        # Angular acceleration: alpha = I^-1 * tau  (rad/s²)
        I_inv = np.linalg.inv(inertia_tensor)
        alpha = I_inv @ tau  # rad/s²

        # Update angular velocity (plain float array, rad/s)
        self.angular_velocity = self.angular_velocity + alpha * dt

        # Update quaternion using first-order integration
        omega = self.angular_velocity  # rad/s
        omega_norm = float(np.linalg.norm(omega))

        if omega_norm > 1e-10:
            # Quaternion derivative: dq/dt =0 0.5 * Omega(omega) * q
            wx, wy, wz = omega
            omega_matrix = 0.5 * np.array([
                [0,  -wx, -wy, -wz],
                [wx,   0,  wz, -wy],
                [wy, -wz,   0,  wx],
                [wz,  wy, -wx,   0]
            ])
            self.quaternion = self.quaternion + omega_matrix @ self.quaternion * dt
            # Normalize quaternion
            q_norm = np.linalg.norm(self.quaternion)
            if q_norm > 1e-10:
                self.quaternion = self.quaternion / q_norm


class Spacecraft:
    """Spacecraft model with orbital and rotational state."""

    def __init__(self, name: str, orbit: Orbit, mass: u.Quantity):
        self.name = name
        self.orbit = orbit
        self.mass = mass.to(u.kg)
        self.rotation = SpacecraftRotation()

        # Default inertia tensor: solid sphere approximation (kg·m²), plain numpy array
        m = float(self.mass.value)
        r = 2.0  # assumed radius in meters
        I = (2.0 / 5.0) * m * r ** 2
        self.rotation.inertia_tensor = np.eye(3) * I

        # Current torque: astropy Quantity
        self._current_torque = np.zeros(3) * u.N * u.m

        logging.info(f"Initialized spacecraft {self.name} with mass {self.mass}")

    def apply_torque(self, torque: u.Quantity) -> None:
        """Apply torque to the spacecraft."""
        if not torque.unit.is_equivalent(u.N * u.m):
            raise ValueError(f"Torque must have units equivalent to N·m, got {torque.unit}")
        if torque.shape != (3,):
            raise ValueError(f"Torque must be a 3-element vector, got shape {torque.shape}")
        self._current_torque = torque.to(u.N * u.m)

    def propagate_orbit(self, time_step: u.s) -> None:
        """Propagate orbital state forward in time."""
        self.orbit = self.orbit.propagate(time_step)

    def propagate_attitude(self, time_step: u.s) -> None:
        """Propagate attitude state forward in time."""
        self.rotation.propagate(time_step, self._current_torque, self.inertia_tensor)

    def get_angular_velocity_str(self) -> str:
        """Return angular velocity as a formatted string."""
        return np.array2string(self.rotation.angular_velocity, precision=6, suppress_small=True)

    @property
    def inertia_tensor(self):
        return self.rotation.inertia_tensor

    @property
    def state(self):
        return {        'name'                 : self.name,
                        'position_m'           : self.orbit.r,
                        'velocity_ms'          : self.orbit.v,
                        'mass_kg'              : self.mass.to(u.kg).value,
                        'angular_velocity_rads': self.rotation.angular_velocity,
                        'quaternion'           : self.rotation.quaternion,
                        'inertia_tensor'       : self.rotation.inertia_tensor,
                        'orbit'                : self.orbit
                        }
