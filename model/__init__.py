"""
Spaceflight Simulation Core Model

This package provides the foundational components for a spaceflight simulator:
- Solar system modeling with major celestial bodies
- Spacecraft dynamics with maneuvering capabilities
- Simulation control API
"""

from .solar_system import SolarSystem
from .spacecraft import Spacecraft
from .api import SpaceflightSimAPI

__all__ = ['SolarSystem', 'Spacecraft', 'SpaceflightSimAPI']
__version__ = '1.0.0'
