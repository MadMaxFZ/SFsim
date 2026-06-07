"""Rotation and attitude dynamics module for spacecraft simulation."""

import numpy as np
from dataclasses import dataclass
from typing import Tuple
import astropy.units as u
from numpy.linalg import inv

@dataclass
class Quaternion:
    """Unit quaternion for 3D rotations."""
    w: float  # Scalar component
    x: float  # Vector components
    y: float
    z: float

    def __post_init__(self):
        """Normalize the quaternion to ensure it's a unit quaternion."""
        norm = np.sqrt(self.w**2 + self.x**2 + self.y**2 + self.z**2)
        self.w /= norm
        self.x /= norm
        self.y /= norm
        self.z /= norm

    def conjugate(self) -> 'Quaternion':
        """Return the conjugate of this quaternion."""
        return Quaternion(self.w, -self.x, -self.y, -self.z)

def multiply_quaternions(q1: Quaternion, q2: Quaternion) -> Quaternion:
    """Multiply two quaternions."""
    w = q1.w * q2.w - q1.x * q2.x - q1.y * q2.y - q1.z * q2.z
    x = q1.w * q2.x + q1.x * q2.w + q1.y * q2.z - q1.z * q2.y
    y = q1.w * q2.y - q1.x * q2.z + q1.y * q2.w + q1.z * q2.x
    z = q1.w * q2.z + q1.x * q2.y - q1.y * q2.x + q1.z * q2.w
    return Quaternion(w, x, y, z)

class RotationState:
    """Represents the rotational state of a rigid body."""

    def __init__(self, orientation: Quaternion, angular_velocity: u.Quantity,
                 inertia_tensor: np.ndarray):
        """
        Initialize rotation state.

        Args:
            orientation: Initial orientation as quaternion
            angular_velocity: Initial angular velocity (rad/s)
            inertia_tensor: 3x3 inertia tensor (kg·m²)
        """
        self.orientation = orientation
        self.angular_velocity = angular_velocity.to(u.rad / u.s)
        self.inertia_tensor = inertia_tensor

    def propagate(self, time_step: u.s, torque: np.ndarray) -> None:
        """
        Propagate attitude dynamics forward in time with applied torque.

        Args:
            time_step: Time step for propagation (seconds)
            torque: Applied torque in N·m (3-element array)
        """
        dt = time_step.to(u.s).value

        # Convert angular velocity to rad/s for calculations
        omega = self.angular_velocity.to(u.rad / u.s).value

        # Euler's rotation equation: I*ω̇ + ω×(I*ω) = τ
        omega_dot = np.dot(np.linalg.inv(self.inertia_tensor),
                          torque - np.cross(omega, np.dot(self.inertia_tensor, omega)))

        # Update angular velocity (first-order integration)
        new_omega = omega + omega_dot * dt

        # Update orientation using quaternion kinematics
        omega_norm = np.linalg.norm(new_omega)
        if omega_norm > 1e-10:  # Avoid division by zero
            axis = new_omega / omega_norm
            angle = omega_norm * dt
            q_delta = Quaternion(
                np.cos(angle/2),
                axis[0] * np.sin(angle/2),
                axis[1] * np.sin(angle/2),
                axis[2] * np.sin(angle/2)
            )
            self.orientation = multiply_quaternions(q_delta, self.orientation)

        # Update angular velocity (with units)
        self.angular_velocity = new_omega * u.rad / u.s

        # Renormalize quaternion to prevent drift
        norm = np.sqrt(self.orientation.w**2 + self.orientation.x**2 +
                      self.orientation.y**2 + self.orientation.z**2)
        self.orientation = Quaternion(
            self.orientation.w / norm,
            self.orientation.x / norm,
            self.orientation.y / norm,
            self.orientation.z / norm
        )



def quaternion_to_euler(q: Quaternion) -> Tuple[float, float, float]:
    """Convert quaternion to Euler angles (roll, pitch, yaw) in radians."""
    # Roll (x-axis rotation)
    sinr_cosp = 2 * (q.w * q.x + q.y * q.z)
    cosr_cosp = 1 - 2 * (q.x * q.x + q.y * q.y)
    roll = np.arctan2(sinr_cosp, cosr_cosp)

    # Pitch (y-axis rotation)
    sinp = 2 * (q.w * q.y - q.z * q.x)
    if abs(sinp) >= 1:
        pitch = np.copysign(np.pi / 2, sinp)  # Use 90 degrees if out of range
    else:
        pitch = np.arcsin(sinp)

    # Yaw (z-axis rotation)
    siny_cosp = 2 * (q.w * q.z + q.x * q.y)
    cosy_cosp = 1 - 2 * (q.y * q.y + q.z * q.z)
    yaw = np.arctan2(siny_cosp, cosy_cosp)

    return roll, pitch, yaw