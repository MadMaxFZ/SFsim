from poliastro.twobody import Orbit
from poliastro.maneuver import Maneuver
from astropy import units as u
import numpy as np
from typing import Dict, Optional
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SpacecraftState:
    """Container for spacecraft state information."""
    position: np.ndarray  # km
    velocity: np.ndarray  # km/s
    mass: float  # kg


class Spacecraft:
    """Advanced spacecraft model with maneuvering and fuel consumption.

    Features:
    - Impulsive maneuvers
    - Fuel consumption calculation
    - State caching
    - Performance optimization
    """

    def __init__(self, name: str, orbit: Orbit, mass: u.kg, isp: u.s = 300 * u.s):
        """Initialize a new spacecraft.

        Args:
            name: Identifier for the spacecraft
            orbit: Initial orbit
            mass: Initial mass (kg)
            isp: Specific impulse (s)
        """
        self.name = name
        self.orbit = orbit
        self.mass = mass
        self.isp = isp
        self._state_cache = SpacecraftState(
                position=self.orbit.r.to(u.km).value,
                velocity=self.orbit.v.to(u.km / u.s).value,
                mass=self.mass.value,
                )
        logger.info(f"Initialized spacecraft {name} with mass {mass}")

    def propagate(self, time_step: u.Quantity):
        """Propagate the spacecraft's orbit forward.

        Args:
            time_step: Time duration to propagate (astropy Quantity)
        """
        try:
            self.orbit = self.orbit.propagate(time_step)
            # Update cache
            self._state_cache = SpacecraftState(
                    position=self.orbit.r.to(u.km).value,
                    velocity=self.orbit.v.to(u.km / u.s).value,
                    mass=self.mass.value,
                    )
        except Exception as e:
            logger.error(f"Propagation failed for {self.name}: {str(e)}")
            raise

    def apply_maneuver(self, delta_v: np.ndarray):
        """Apply an impulsive maneuver to the spacecraft.

        Args:
            delta_v: Velocity change vector (km/s)
        """
        try:
            # Calculate fuel consumption
            delta_v_mag = np.linalg.norm(delta_v) * u.km / u.s
            if delta_v_mag.value > 0:
                g0 = 9.80665 * u.m / u.s ** 2  # Standard gravity
                fuel_mass = self.mass * (1 - np.exp(-delta_v_mag / (self.isp * g0)))
                self.mass -= fuel_mass

            # Apply maneuver
            maneuver = Maneuver.impulse(delta_v * u.km / u.s)
            self.orbit = self.orbit.apply_maneuver(maneuver)

            # Update cache
            self._state_cache = SpacecraftState(
                    position=self.orbit.r.to(u.km).value,
                    velocity=self.orbit.v.to(u.km / u.s).value,
                    mass=self.mass.value,
                    )
            logger.info(f"Applied Δv={delta_v} km/s to {self.name}, fuel used: {fuel_mass:.2f}")
        except Exception as e:
            logger.error(f"Maneuver failed for {self.name}: {str(e)}")
            raise

    def get_state(self) -> SpacecraftState:
        """Get the current state of the spacecraft.

        Returns:
            SpacecraftState object containing position, velocity, and mass
        """
        return self._state_cache
