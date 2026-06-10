# model/solar_system.py

import logging
from typing import Dict, Optional
from dataclasses import dataclass

import numpy as np
from astropy import units as u
from astropy.time import Time
from poliastro.bodies import Sun, Mercury, Venus, Earth, Moon, Mars, Jupiter, Saturn, Uranus, Neptune, Body
from poliastro.ephem import Ephem
from poliastro.twobody import Orbit


@dataclass
class BodyState:
    """State of a solar system body."""
    name: str
    orbit: Optional[Orbit]
    body: Body


class SolarSystem:
    """Solar system model with planetary ephemerides."""

    BODIES = {
        'Mercury': Mercury,
        'Venus': Venus,
        'Earth': Earth,
        'Moon': Moon,
        'Mars': Mars,
        'Jupiter': Jupiter,
        'Saturn': Saturn,
        'Uranus': Uranus,
        'Neptune': Neptune,
    }

    def __init__(self, epoch: Time = None):
        self.epoch = epoch if epoch is not None else Time.now()
        self.body_states: Dict[str, BodyState] = {}
        self._initialize_orbits()
        logging.info(f"Initialized solar system with {len(self.body_states)} bodies")

    def _initialize_orbits(self) -> None:
        """
        Initialize orbits using body.parent to determine the central body.
        Uses tdb scale to suppress TimeScaleWarning.
        """
        if self.epoch.format == 'tdb':
            epoch_tdb = self.epoch
        else:
            epoch_tdb = Time(self.epoch, scale='tdb')

        offsets = np.linspace(-180, 180, 9) * u.day
        t_range = Time(
            [epoch_tdb + offset for offset in offsets],
            scale='tdb'
        )

        for name, body in self.BODIES.items():
            try:
                parent = body.parent
                ephem = Ephem.from_body(body, t_range)
                orbit = Orbit.from_ephem(parent, ephem, self.epoch)
                self.body_states[name] = BodyState(name=name, orbit=orbit, body=body)
            except Exception as e:
                logging.warning(f"Could not initialize orbit for {name}: {str(e)}")
        pass

    def get_body_state(self, name: str) -> Optional[BodyState]:
        return self.body_states.get(name)

    def get_body_orbit(self, name: str) -> Optional[Orbit]:
        state = self.body_states.get(name)
        return state.orbit if state else None

    def propagate(self, time_step: u.Quantity) -> None:
        """Propagate all orbits forward in time."""
        new_epoch = self.epoch + time_step
        for name, state in self.body_states.items():
            try:
                state.orbit = state.orbit.propagate(time_step)
            except Exception as e:
                logging.warning(f"Could not propagate orbit for {name}: {str(e)}")
        self.epoch += time_step
