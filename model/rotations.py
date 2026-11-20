# model/rotations.py
"""Quaternion helpers. Quaternions are numpy arrays [w, x, y, z] mapping body -> inertial."""

import numpy as np


def q_normalize(q: np.ndarray) -> np.ndarray:
    return q / np.linalg.norm(q)


def q_multiply(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return np.array([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
                     w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
                     w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2])


def q_to_matrix(q: np.ndarray) -> np.ndarray:
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                     [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def q_from_axis_angle(axis: np.ndarray, angle: float) -> np.ndarray:
    n = np.linalg.norm(axis)
    if n < 1e-12:
        return np.array([1.0, 0.0, 0.0, 0.0])
    axis = axis / n
    return np.concatenate([[np.cos(angle / 2)], axis * np.sin(angle / 2)])


def q_integrate(q: np.ndarray, omega_body: np.ndarray, dt: float) -> np.ndarray:
    """Exact integration for constant body rate over dt."""
    wn = np.linalg.norm(omega_body)
    if wn < 1e-12:
        return q
    return q_normalize(q_multiply(q, q_from_axis_angle(omega_body, wn * dt)))


def q_from_forward(forward: np.ndarray, up_hint: np.ndarray = None) -> np.ndarray:
    """Quaternion whose body +X axis points along `forward` (body +Z kept near up_hint)."""
    f = forward / np.linalg.norm(forward)
    up = np.array([0.0, 0.0, 1.0]) if up_hint is None else up_hint
    if abs(np.dot(f, up / np.linalg.norm(up))) > 0.99:
        up = np.array([0.0, 1.0, 0.0])
    y = np.cross(up, f)
    y /= np.linalg.norm(y)
    z = np.cross(f, y)
    m = np.column_stack([f, y, z])
    return matrix_to_q(m)


def matrix_to_q(m: np.ndarray) -> np.ndarray:
    tr = np.trace(m)
    if tr > 0:
        s = 2 * np.sqrt(tr + 1)
        q = [0.25 * s, (m[2, 1] - m[1, 2]) / s, (m[0, 2] - m[2, 0]) / s, (m[1, 0] - m[0, 1]) / s]
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = 2 * np.sqrt(1 + m[0, 0] - m[1, 1] - m[2, 2])
        q = [(m[2, 1] - m[1, 2]) / s, 0.25 * s, (m[0, 1] + m[1, 0]) / s, (m[0, 2] + m[2, 0]) / s]
    elif m[1, 1] > m[2, 2]:
        s = 2 * np.sqrt(1 + m[1, 1] - m[0, 0] - m[2, 2])
        q = [(m[0, 2] - m[2, 0]) / s, (m[0, 1] + m[1, 0]) / s, 0.25 * s, (m[1, 2] + m[2, 1]) / s]
    else:
        s = 2 * np.sqrt(1 + m[2, 2] - m[0, 0] - m[1, 1])
        q = [(m[1, 0] - m[0, 1]) / s, (m[0, 2] + m[2, 0]) / s, (m[1, 2] + m[2, 1]) / s, 0.25 * s]
    return q_normalize(np.array(q))


def q_to_euler(q: np.ndarray):
    """Roll, pitch, yaw (rad) of the body frame relative to the inertial frame."""
    w, x, y, z = q
    roll = np.arctan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    pitch = np.arcsin(np.clip(2 * (w * y - z * x), -1, 1))
    yaw = np.arctan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return roll, pitch, yaw
