# model/api.py

import logging
from typing import Callable, Dict, Optional
import numpy as np
from astropy import units as u
from astropy.time import Time
from poliastro.constants import J2000_TDB
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

    def __init__(self, epoch: Time = J2000_TDB):
        self.spacecraft: Dict[str, Spacecraft] = {}
        self.hooks: Dict[str, Dict[str, ControlHook]] = {}
        self.simulation_time = epoch
        self.time_warp = 1
        self.solar_system = SolarSystem(epoch=epoch)
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
        if spacecraft_name not in self.spacecraft.keys():
            raise ValueError(f"Spacecraft {spacecraft_name} not found")
        self.hooks[spacecraft_name][hook_type] = ControlHook(callback, hook_type)
        logging.info(f"Registered spacecraft control hook: {hook_type}")

    def propagate_system(self, time_step: u.Quantity) -> None:
        """Propagate the entire system forward in time."""
        self.solar_system.propagate(time_step * self.time_warp)

        for name, sc in self.spacecraft.items():
            if "pre_attitude_control" in self.hooks[name]:
                self.hooks[name]["pre_attitude_control"](time_step * self.time_warp,
                                                         self.get_spacecraft_state(name))

            sc.propagate_attitude(time_step * self.time_warp)

            if "post_attitude_control" in self.hooks[name]:
                self.hooks[name]["post_attitude_control"](time_step * self.time_warp,
                                                          self.get_spacecraft_state(name))

            sc.propagate_orbit(time_step * self.time_warp)

        self.simulation_time = self.simulation_time + time_step * self.time_warp

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
                        'position_km': [x, y, z],
                        'velocity_kms': [vx, vy, vz],
                    }, ...
                },
                'spacecraft': {
                    name: {
                        'position_km': [x, y, z],
                        'velocity_kms': [vx, vy, vz],
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
                r_km = body_state.orbit.r.to(u.km)    #.value.tolist()
                v_kms = body_state.orbit.v.to(u.km / u.s) #.value.tolist()
                bodies[name] = {
                        'position_km' : r_km,
                        'velocity_kms': v_kms,
                        }
            except Exception as e:
                logging.warning(f"Could not get state for body {name}: {e}")

        spacecraft = {}
        for name, sc in self.spacecraft.items():
            try:
                r_m = sc.orbit.r.to(u.km)    #.value.tolist()
                v_ms = sc.orbit.v.to(u.km / u.s) #.value.tolist()
                spacecraft[name] = sc.state

            except Exception as e:
                logging.warning(f"Could not get state for spacecraft {name}: {e}")

        res = {
                'epoch'            : str(self.solar_system.epoch.iso),
                'simulation_time_s': str(self.simulation_time),
                'time_warp'        : self.time_warp,
                'bodies'           : bodies,
                'spacecraft'       : spacecraft,
                }
        pass
        return res

    def get_spacecraft_state(self, name: str):
        """Get the current state of a spacecraft."""
        if name not in self.spacecraft.keys():
            raise ValueError(f"Spacecraft {name} not found")
        sc = self.spacecraft[name]
        return sc.state

    def apply_spacecraft_maneuver(self, name: str,
                                   delta_v: np.ndarray) -> None:
        """
        Apply an impulsive maneuver to a spacecraft.

        Args:
            name: Spacecraft name
            delta_v: Delta-v vector in km/s (plain numpy array, shape (3,))
        """
        if name not in self.spacecraft.keys():
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
