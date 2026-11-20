# shipos/autopilot.py
"""
Attitude control laws. Produces RCS torque commands (physical mode) or, under
high time warp, an ideal attitude snap (Orbiter-style "attitude held").
"""

import numpy as np

from model.rotations import q_to_matrix, q_from_forward

MAX_RATE = 0.15          # rad/s slew-rate limit
TAU = 0.5                # s, rate-loop time constant


def attitude_error(q, desired):
    """Body-frame rotation vector taking body +X onto `desired`, and its angle."""
    R = q_to_matrix(q)
    f = R[:, 0]
    axis = np.cross(f, desired)
    s, c = np.linalg.norm(axis), float(np.dot(f, desired))
    angle = np.arctan2(s, c)
    if s < 1e-9:
        if c > 0:
            return np.zeros(3), 0.0
        axis_b = np.array([0.0, 0.0, 1.0])               # 180 deg: yaw around
        return axis_b * angle, angle
    return R.T @ (axis / s) * angle, angle


def rate_command(ship, desired):
    """Desired body rates to slew onto `desired` without overshoot."""
    if desired is None:                                  # KILLROT
        return np.zeros(3)
    err, angle = attitude_error(ship.q, desired)
    if angle < 1e-6:
        return np.zeros(3)
    alpha = ship.cfg.rcs_torque / np.max(np.diag(ship.inertia))
    rate = min(MAX_RATE, 0.8 * np.sqrt(2 * alpha * angle), 1.0 * angle)
    return err / angle * rate


def torque_command(ship, omega_des):
    I = ship.inertia
    tau = I @ (omega_des - ship.omega) / TAU
    lim = ship.cfg.rcs_torque
    return np.clip(tau, -lim, lim)


def snap(ship, desired):
    """Ideal attitude hold used when attitude dynamics are not resolved (high warp)."""
    if desired is not None:
        ship.q = q_from_forward(desired)
    ship.omega = np.zeros(3)
