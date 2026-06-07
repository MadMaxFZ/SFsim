# model/api.py

import logging
from typing import Callable, Dict, Optional
import numpy as np
from astropy import units as u
from astropy.time import Time
from poliastro.twobody import Orbit

from model.spacecraft import Spacecraft
from model.solar_system import SolarSystem


class ControlHook:
    """Wrapper for spacecraft control hooks."""

    def __init__(self, callback: Callable, hook_type: str):
        self.callback = callback
        self.hook_type = hook_type

    def __call__(self, time_step: u.Quantity, spacecraft: Spacecraft):
        return self.callback(time_step, spacecraft)


class SpaceflightSimAPI:
    """API for interacting with the spaceflight simulation model."""

    def __init__(self, epoch: Time = None):
        self.solar_system = SolarSystem(epoch=epoch)
        self.spacecraft: Dict[str, Spacecraft] = {}
        self.hooks: Dict[str, Dict[str, ControlHook]] = {}
        self.simulation_time = 0.0 * u.s
        self.time_warp = 1
        logging.info("SpaceflightSimAPI initialized with control hook system")

    def add_spacecraft(self, name: str, orbit: Orbit,
                       mass: u.Quantity = 1000 * u.kg) -> None:
        """Add a spacecraft to the simulation."""
        if name in self.spacecraft:
            raise ValueError(f"Spacecraft {name} already exists")
        self.spacecraft[name] = Spacecraft(name, orbit, mass)
        self.hooks[name] = {}
        logging.info(f"Added spacecraft {name} with mass {mass.to(u.kg).value} kg")

    def register_spacecraft_hook(
        self,
        spacecraft_name: str,
        callback: Callable,
        hook_type: str
    ) -> None:
        """
        Register a control hook for a spacecraft.

        Args:
            spacecraft_name: Name of the spacecraft
            callback: Function with signature func(time_step, spacecraft)
            hook_type: One of 'pre_attitude_control', 'post_attitude_control'
        """
        if spacecraft_name not in self.spacecraft:
            raise ValueError(f"Spacecraft {spacecraft_name} not found")
        self.hooks[spacecraft_name][hook_type] = ControlHook(callback, hook_type)
        logging.info(f"Registered spacecraft control hook: {hook_type}")

    def propagate_system(self, time_step: u.Quantity) -> None:
        """Propagate the entire system forward in time."""
        self.solar_system.propagate(time_step)

        for name, spacecraft in self.spacecraft.items():
            if "pre_attitude_control" in self.hooks[name]:
                self.hooks[name]["pre_attitude_control"](time_step, spacecraft)

            spacecraft.propagate_attitude(time_step)

            if "post_attitude_control" in self.hooks[name]:
                self.hooks[name]["post_attitude_control"](time_step, spacecraft)

            spacecraft.propagate_orbit(time_step)

        self.simulation_time = self.simulation_time + time_step

    # model/api.py
    # Only the get_system_state() method needs updating — full method shown:

    def get_system_state(self) -> dict:
        """
        Return a snapshot of the full simulation state suitable for UI consumption.

        Returns:
            {
                'epoch': str,
                'simulation_time_s': float,
                'time_warp': int,
                'bodies': {
                    name: {
                        'position_m': [x, y, z],
                        'velocity_ms': [vx, vy, vz],
                    }, ...
                },
                'spacecraft': {
                    name: {
                        'position_m': [x, y, z],
                        'velocity_ms': [vx, vy, vz],
                        'mass_kg': float,
                        'angular_velocity_rads': [wx, wy, wz],
                        'quaternion': [q0, q1, q2, q3],
                    }, ...
                }
            }
        """
        bodies = {}
        for name, body_state in self.solar_system.body_states.items():
            try:
                r_m = body_state.orbit.r.to(u.m).value.tolist()
                v_ms = body_state.orbit.v.to(u.m / u.s).value.tolist()
                bodies[name] = {
                        'position_m' : r_m,
                        'velocity_ms': v_ms,
                        }
            except Exception as e:
                logging.warning(f"Could not get state for body {name}: {e}")

        spacecraft = {}
        for name, sc in self.spacecraft.items():
            try:
                r_m = sc.orbit.r.to(u.m).value.tolist()
                v_ms = sc.orbit.v.to(u.m / u.s).value.tolist()
                spacecraft[name] = {
                        'position_m'           : r_m,
                        'velocity_ms'          : v_ms,
                        'mass_kg'              : sc.mass.to(u.kg).value,
                        'angular_velocity_rads': sc.rotation.angular_velocity.tolist(),
                        'quaternion'           : sc.rotation.quaternion.tolist(),
                        }
            except Exception as e:
                logging.warning(f"Could not get state for spacecraft {name}: {e}")

        return {
                'epoch'            : str(self.solar_system.epoch.iso),
                'simulation_time_s': self.simulation_time.to(u.s).value,
                'time_warp'        : self.time_warp,
                'bodies'           : bodies,
                'spacecraft'       : spacecraft,
                }

    def get_spacecraft_state(self, name: str):
        """Get the current state of a spacecraft."""
        if name not in self.spacecraft:
            raise ValueError(f"Spacecraft {name} not found")
        sc = self.spacecraft[name]
        return sc.orbit.state

    def apply_spacecraft_maneuver(self, name: str,
                                   delta_v: np.ndarray) -> None:
        """
        Apply an impulsive maneuver to a spacecraft.

        Args:
            name: Spacecraft name
            delta_v: Delta-v vector in km/s (plain numpy array, shape (3,))
        """
        if name not in self.spacecraft:
            raise ValueError(f"Spacecraft {name} not found")
        sc = self.spacecraft[name]
        dv = delta_v * u.km / u.s
        from poliastro.maneuver import Maneuver
        maneuver = Maneuver.impulse(dv)
        sc.orbit = sc.orbit.apply_maneuver(maneuver)

    def get_body_state(self, name: str):
        """Get the current state of a solar system body."""
        return self.solar_system.get_body_state(name)

    def get_relative_position(self, body1: str, body2: str) -> np.ndarray:
        """
        Get position of body2 relative to body1 in km.

        Args:
            body1: Reference body name
            body2: Target body name

        Returns:
            Relative position vector in km as plain numpy array
        """
        state1 = self.solar_system.get_body_state(body1)
        state2 = self.solar_system.get_body_state(body2)
        if state1 is None or state2 is None:
            raise ValueError(
                f"Could not find states for {body1} and/or {body2}"
            )
        r1 = state1.orbit.r.to(u.km).value
        r2 = state2.orbit.r.to(u.km).value
        return r2 - r1
