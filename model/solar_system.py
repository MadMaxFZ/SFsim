from poliastro.bodies import (
    Body, Sun,
    Mercury, Venus, Earth, Moon,
    Mars, Jupiter, Saturn,
    Uranus, Neptune
)
from poliastro.twobody import Orbit
from astropy.time import Time
from astropy import units as u
from typing import Dict, Optional, Tuple
import numpy as np
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class BodyState:
    """Container for celestial body state information."""
    position: np.ndarray  # km
    velocity: np.ndarray  # km/s

class SolarSystem:
    """High-performance solar system simulator with major celestial bodies.

    Features:
    - J2000 epoch initialization
    - Circular orbit approximations
    - Efficient propagation
    - State caching for performance
    """

    # Orbital parameters (semi-major axis in AU)
    PLANETARY_DISTANCES = {
        "Mercury": 0.387098,
        "Venus": 0.723332,
        "Earth": 1.000000,
        "Mars": 1.523679,
        "Jupiter": 5.202603,
        "Saturn": 9.554909,
        "Uranus": 19.218446,
        "Neptune": 30.110387
    }

    # Average Moon distance from Earth in km
    MOON_DISTANCE = 384_400

    def __init__(self):
        """Initialize the solar system with all major bodies."""
        self.bodies: Dict[str, Body] = {
            "Sun": Sun,
            "Mercury": Mercury,
            "Venus": Venus,
            "Earth": Earth,
            "Moon": Moon,
            "Mars": Mars,
            "Jupiter": Jupiter,
            "Saturn": Saturn,
            "Uranus": Uranus,
            "Neptune": Neptune,
        }
        self.orbits: Dict[str, Orbit] = {}
        self._state_cache: Dict[str, BodyState] = {}
        self._initialize_orbits()

    def _initialize_orbits(self):
        """Initialize all celestial body orbits at J2000 epoch."""
        j2000 = Time("J2000", scale="tdb")

        for name, body in self.bodies.items():
            if name == "Sun":
                continue

            try:
                if name == "Moon":
                    self.orbits[name] = Orbit.circular(
                        attractor=Earth,
                        alt=self.MOON_DISTANCE * u.km,
                        epoch=j2000
                    )
                else:
                    self.orbits[name] = Orbit.circular(
                        attractor=Sun,
                        alt=self.PLANETARY_DISTANCES[name] * u.au,
                        epoch=j2000
                    )
                # Cache initial state
                self._state_cache[name] = BodyState(
                    position=self.orbits[name].r.to(u.km).value,
                    velocity=self.orbits[name].v.to(u.km/u.s).value
                )
            except Exception as e:
                logger.error(f"Failed to initialize orbit for {name}: {str(e)}")
                raise

    def propagate(self, time_step: u.Quantity):
        """Propagate all orbits forward by the given time step.

        Args:
            time_step: Time duration to propagate (astropy Quantity)
        """
        for name, orbit in self.orbits.items():
            try:
                self.orbits[name] = orbit.propagate(time_step)
                # Update cache
                self._state_cache[name] = BodyState(
                    position=self.orbits[name].r.to(u.km).value,
                    velocity=self.orbits[name].v.to(u.km/u.s).value
                )
            except Exception as e:
                logger.error(f"Propagation failed for {name}: {str(e)}")
                raise

    def get_body_state(self, name: str) -> Optional[BodyState]:
        """Get the current state of a celestial body.

        Args:
            name: Name of the body to query

        Returns:
            BodyState object containing position and velocity or None if not found
        """
        if name not in self._state_cache:
            logger.warning(f"Body {name} not found in cache")
            return None
        return self._state_cache[name]

    def get_body_position(self, name: str) -> Optional[np.ndarray]:
        """Get the current position of a body in km.

        Args:
            name: Name of the body to query

        Returns:
            Position vector in km or None if body not found
        """
        state = self.get_body_state(name)
        return state.position if state else None

    def get_body_velocity(self, name: str) -> Optional[np.ndarray]:
        """Get the current velocity of a body in km/s.

        Args:
            name: Name of the body to query

        Returns:
            Velocity vector in km/s or None if body not found
        """
        state = self.get_body_state(name)
        return state.velocity if state else None

    def get_relative_position(self, body1: str, body2: str) -> Optional[np.ndarray]:
        """Get the position of body1 relative to body2 in km.

        Args:
            body1: Name of the first body
            body2: Name of the second body

        Returns:
            Relative position vector in km or None if either body not found
        """
        pos1 = self.get_body_position(body1)
        pos2 = self.get_body_position(body2)
        if pos1 is None or pos2 is None:
            return None
        return pos1 - pos2
