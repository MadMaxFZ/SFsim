# model/constants.py
"""
Physical constants and the body catalogue.

Internal unit convention for the whole model:  km, s, kg.
All vectors are expressed in the heliocentric J2000 ECLIPTIC frame.
"""

import numpy as np

G0 = 9.80665e-3          # standard gravity, km/s^2
AU_KM = 1.495978707e8    # km per astronomical unit
DAY_S = 86400.0
OBLIQUITY_J2000 = np.radians(23.4392911)

# name: (GM km^3/s^2, mean radius km, parent)
BODIES = {
    'Sun':     (1.32712440018e11, 695700.0, None),
    'Mercury': (2.2032e4,           2439.7, 'Sun'),
    'Venus':   (3.24859e5,          6051.8, 'Sun'),
    'Earth':   (3.986004418e5,      6371.0, 'Sun'),
    'Moon':    (4.9048695e3,        1737.4, 'Earth'),
    'Mars':    (4.282837e4,         3389.5, 'Sun'),
    'Jupiter': (1.26686534e8,      69911.0, 'Sun'),
    'Saturn':  (3.7931187e7,       58232.0, 'Sun'),
    'Uranus':  (5.793939e6,        25362.0, 'Sun'),
    'Neptune': (6.836529e6,        24622.0, 'Sun'),
}


def gm(name: str) -> float:
    return BODIES[name][0]


def radius(name: str) -> float:
    return BODIES[name][1]


def parent(name: str):
    return BODIES[name][2]


def children(name: str):
    return [n for n, (_, _, p) in BODIES.items() if p == name]


def equatorial_to_ecliptic(vec: np.ndarray) -> np.ndarray:
    """Rotate ICRS/equatorial vector(s) into the J2000 ecliptic frame."""
    c, s = np.cos(OBLIQUITY_J2000), np.sin(OBLIQUITY_J2000)
    rot = np.array([[1.0, 0.0, 0.0],
                    [0.0,   c,   s],
                    [0.0,  -s,   c]])
    return vec @ rot.T
