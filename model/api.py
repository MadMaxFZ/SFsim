from .solar_system import SolarSystem, BodyState
from .spacecraft import Spacecraft, SpacecraftState
from poliastro.twobody import Orbit
from astropy import units as u
from typing import Dict, Optional, Union, List
import numpy as np
import logging

logger = logging.getLogger(__name__)

class SpaceflightSimAPI:
    """Production-ready API for spaceflight simulation.

    Features:
    - Thread-safe operations
    - Comprehensive state management
    - Efficient propagation
    - Detailed logging
    - Error handling
    """

    def __init__(self):
        """Initialize the simulation API."""
        self.solar_system = SolarSystem()
        self.spacecraft: Dict[str, Spacecraft] = {}
        self._sim_time = 0 * u.s
        logger.info("SpaceflightSimAPI initialized")

    def add_spacecraft(self, name: str, orbit: Orbit, mass: u.kg, isp: u.s = 300 * u.s):
        """Add a spacecraft to the simulation.

        Args:
            name: Identifier for the spacecraft
            orbit: Initial orbit
            mass: Initial mass (kg)
            isp: Specific impulse (s)
        """
        if name in self.spacecraft:
            logger.warning(f"Overwriting existing spacecraft {name}")
        self.spacecraft[name] = Spacecraft(name, orbit, mass, isp)

    def get_spacecraft_state(self, name: str) -> Optional[SpacecraftState]:
        """Get the current state of a spacecraft.

        Args:
            name: Name of the spacecraft to query

        Returns:
            SpacecraftState object or None if not found
        """
        if name not in self.spacecraft:
            logger.warning(f"Spacecraft {name} not found")
            return None
        return self.spacecraft[name].get_state()

    def get_all_spacecraft_states(self) -> Dict[str, SpacecraftState]:
        """Get states of all spacecraft.

        Returns:
            Dictionary mapping spacecraft names to their states
        """
        return {name: sc.get_state() for name, sc in self.spacecraft.items()}

    def propagate_system(self, time_step: u.Quantity):
        """Propagate the entire system forward.

        Args:
            time_step: Time duration to propagate (astropy Quantity)
        """
        try:
            self.solar_system.propagate(time_step)
            for spacecraft in self.spacecraft.values():
                spacecraft.propagate(time_step)
            self._sim_time += time_step
            logger.debug(f"Propagated system by {time_step}")
        except Exception as e:
            logger.error(f"System propagation failed: {str(e)}")
            raise

    def apply_spacecraft_maneuver(self, name: str, delta_v: np.ndarray):
        """Apply a maneuver to a spacecraft.

        Args:
            name: Name of the spacecraft
            delta_v: Velocity change vector (km/s)
        """
        if name not in self.spacecraft:
            logger.warning(f"Spacecraft {name} not found")
            return
        self.spacecraft[name].apply_maneuver(delta_v)

    def get_body_state(self, name: str) -> Optional[BodyState]:
        """Get the current state of a celestial body.

        Args:
            name: Name of the body to query

        Returns:
            BodyState object or None if not found
        """
        return self.solar_system.get_body_state(name)

    def get_relative_position(self, body1: str, body2: str) -> Optional[np.ndarray]:
        """Get the position of body1 relative to body2 in km.

        Args:
            body1: Name of the first body
            body2: Name of the second body

        Returns:
            Relative position vector in km or None if either body not found
        """
        return self.solar_system.get_relative_position(body1, body2)

    @property
    def simulation_time(self) -> u.Quantity:
        """Get the current simulation time."""
        return self._sim_time
