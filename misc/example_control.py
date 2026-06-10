# example_control.py

import logging
import numpy as np
from astropy import units as u
from astropy.time import Time

from model.api import SpaceflightSimAPI
from model.spacecraft import Spacecraft
from poliastro.bodies import Earth
from poliastro.twobody import Orbit

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(message)s')


def attitude_control_hook(time_step: u.Quantity, spacecraft: Spacecraft) -> None:
    """
    Attitude control hook implementing damping with torque clamping.

    Reads the spacecraft's actual inertia tensor to ensure the clamp
    calculation matches the dynamics model exactly, guaranteeing monotonic
    convergence to zero angular velocity with no overshoot.
    """
    kd = 50.0  # N*m / (rad/s) damping gain — only affects pre-clamp magnitude

    dt = time_step.to(u.s).value

    # Read inertia diagonal from the spacecraft's actual inertia tensor
    inertia = np.diag(spacecraft.inertia_tensor)  # kg*m², shape (3,)

    current_omega = spacecraft.rotation.angular_velocity  # plain numpy array, rad/s

    # Unclamped damping torque
    damping_torque = -kd * current_omega  # N*m

    # Clamp: each axis torque cannot produce delta_omega larger than |omega| on that axis
    # max_torque_i = I_i * |omega_i| / dt  →  delta_omega_i = max_torque_i * dt / I_i = |omega_i|
    max_torque = inertia * np.abs(current_omega) / dt
    clamped_torque = np.sign(damping_torque) * np.minimum(np.abs(damping_torque), max_torque)

    torque = clamped_torque * (u.N * u.m)

    logging.info(
        f"Attitude control: omega={np.array2string(current_omega, precision=4)} rad/s | "
        f"torque={np.array2string(clamped_torque, precision=3)} N*m | "
        f"inertia_diag={np.array2string(inertia, precision=1)} kg*m²"
    )
    spacecraft.apply_torque(torque)


def main():
    epoch = Time.now().tdb
    api = SpaceflightSimAPI(epoch=epoch)

    initial_orbit = Orbit.circular(Earth, alt=400 * u.km)
    api.add_spacecraft(
        name="Explorer",
        orbit=initial_orbit,
        mass=1000.0 * u.kg
    )

    api.spacecraft["Explorer"].rotation.angular_velocity = np.array([0.1, 0.05, -0.02])

    api.register_spacecraft_hook(
        spacecraft_name="Explorer",
        callback=attitude_control_hook,
        hook_type="pre_attitude_control"
    )

    sim_duration = 10 * u.minute
    time_step = 1 * u.minute

    current_time = 0.0 * u.s
    while current_time < sim_duration:
        api.propagate_system(time_step)
        current_time = current_time + time_step

        spacecraft = api.spacecraft["Explorer"]
        omega = spacecraft.rotation.angular_velocity
        speed = np.linalg.norm(omega)
        logging.info(
            f"t={current_time.to(u.s).value:.0f}s | "
            f"omega={np.array2string(omega, precision=6, suppress_small=True)} rad/s | "
            f"|omega|={speed:.6f} rad/s"
        )


if __name__ == "__main__":
    main()
