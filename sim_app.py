#!/usr/bin/python
# sim_app.py
"""
Top-level entry point. Wires the Model API to the DisplayManager.
"""

import logging
import pygame
from astropy.time import Time
from model.solar_system import SolarSystem
from api import SpaceflightSimAPI
from ui.display_manager import DisplayManager

logging.basicConfig(level=logging.INFO,
                    format='%(levelname)s:%(message)s')


def main():
    epoch = Time("2026-01-01", scale='tdb')
    # solar_system = SolarSystem(epoch=epoch)
    api = SpaceflightSimAPI(epoch)

    display = DisplayManager(api)
    display.initialize()
    display.run()


if __name__ == "__main__":
    main()
