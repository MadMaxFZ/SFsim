# sim_app.py

import logging
import pygame
from astropy.time import Time
from model.api import SpaceflightSimAPI
from ui.display_manager import DisplayManager

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')


def main():
    api = SpaceflightSimAPI(epoch=Time("2026-01-01", scale='tdb'))
    display = DisplayManager(api)
    display.initialize()
    display.run()


if __name__ == "__main__":
    main()
