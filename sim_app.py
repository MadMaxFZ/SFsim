#!/usr/bin/python
# sim_app.py
"""
Top-level entry point. Builds the model API, then hands it to the
DisplayManager, which wires ShipAI and Telemetry to the instruments.

    python sim_app.py [--epoch 2026-11-01] [--body Earth] [--alt 400]
"""

import argparse
import logging

from astropy.time import Time

from model.api import SpaceflightSimAPI
from ui.display_manager import DisplayManager

logging.basicConfig(level=logging.INFO, format='%(levelname)s:%(message)s')


def main():
    ap = argparse.ArgumentParser(description="SFsim spaceflight simulator")
    ap.add_argument('--epoch', default='2026-01-01', help='start epoch (TDB, ISO date)')
    ap.add_argument('--body', default='Earth', help='body to start in orbit around')
    ap.add_argument('--alt', type=float, default=400.0, help='initial circular altitude, km')
    ap.add_argument('--inc', type=float, default=0.0, help='inclination to the ecliptic, deg')
    args = ap.parse_args()

    api = SpaceflightSimAPI(Time(args.epoch, scale='tdb'))
    api.add_spacecraft_in_orbit("Explorer", args.body, args.alt, args.inc)

    display = DisplayManager(api, "Explorer")
    display.initialize()
    display.run()


if __name__ == "__main__":
    main()
