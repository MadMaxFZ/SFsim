# tests/test_physics.py
"""Run from the repository root:  python -m pytest -q tests"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pytest
from astropy.time import Time

from model.api import SpaceflightSimAPI
from model.constants import gm, AU_KM
from model.kepler import rv_to_elements, perifocal_basis
from shipos import ShipAI
from shipos.autopilot import attitude_error

EPOCH = Time("2026-01-01", scale='tdb')


@pytest.fixture(scope='module')
def base_api():
    return SpaceflightSimAPI(EPOCH)


def make(alt=400.0, ai=True):
    api = SpaceflightSimAPI(EPOCH)
    api.add_spacecraft_in_orbit("T", "Earth", alt)
    a = None
    if ai:
        a = ShipAI("T")
        api.register_controller("T", a)
    return api, a


def run(api, seconds, warp, dt=1 / 60):
    api.time_warp = warp
    end = api.t + seconds
    while api.t < end - 1e-6:
        api.advance(min(dt, (end - api.t) / warp))


def test_kepler_roundtrip():
    mu = gm('Earth')
    r = np.array([7000.0, 1000.0, 500.0])
    v = np.array([-1.0, 7.2, 0.5])
    el = rv_to_elements(r, v, mu)
    P, Q = perifocal_basis(el.i, el.raan, el.argp)
    p = el.a * (1 - el.e ** 2)
    rr = p / (1 + el.e * np.cos(el.nu))
    r2 = rr * (np.cos(el.nu) * P + np.sin(el.nu) * Q)
    assert np.allclose(r, r2, rtol=1e-9)


def test_ephemeris_sane(base_api):
    st = base_api.solar_system.states(0.0)
    d_earth = np.linalg.norm(st['Earth'][0]) / AU_KM
    d_moon = np.linalg.norm(st['Moon'][0] - st['Earth'][0])
    assert 0.98 < d_earth < 1.02
    assert 356000 < d_moon < 407000
    assert abs(st['Earth'][0][2]) < 1e4          # ecliptic frame: Earth near z=0


def test_leo_stable_one_day():
    api, _ = make()
    run(api, 86400, 1e4, dt=0.1)
    c = api.context("T")
    el = rv_to_elements(c['r_rel'], c['v_rel'], gm('Earth'))
    assert abs(el.a - 6771.0) < 2.0
    assert el.e < 1e-3


def test_burn_executor_accuracy():
    api, ai = make()
    ai.command_burn(0.100, 'PROGRADE')
    run(api, 120, 1)
    assert ai.program is None
    sc = api.spacecraft["T"]
    assert abs(sc.dv_expended - 0.100) < 0.0005


def test_attitude_slew_retrograde():
    api, ai = make()
    ai.set_attitude_mode('RETROGRADE')
    run(api, 90, 1)
    c = api.context("T")
    v = c['v_rel'] / np.linalg.norm(c['v_rel'])
    _, ang = attitude_error(api.spacecraft["T"].q, -v)
    assert np.degrees(ang) < 1.0


def test_escape_changes_soi():
    api, ai = make()
    ai.command_burn(3.6, 'PROGRADE')
    run(api, 1200, 10)
    assert ai.program is None
    run(api, 5 * 86400, 1e4, dt=0.1)
    assert api.dominant("T") == 'Sun'


def test_impact_detected():
    api, ai = make(alt=200.0)
    ai.command_burn(0.3, 'RETROGRADE')
    run(api, 400, 10)
    run(api, 6000, 100)
    assert api.spacecraft["T"].status == 'CRASHED'
