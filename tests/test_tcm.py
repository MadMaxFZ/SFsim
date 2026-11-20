import numpy as np
import pytest
from astropy.time import Time

from model.api import SpaceflightSimAPI
from model.constants import gm, radius
from model.dynamics import propagate_free
from model.kepler import rv_to_elements
from model.spacecraft import Spacecraft
from shipos import ShipAI
from shipos.guidance import solve_tcm


def test_tcm_targets_mars_periapsis_with_gravity():
    api = SpaceflightSimAPI(Time('2027-08-01', scale='tdb'))
    solar = api.solar_system
    rm, vm = solar.states(0.0)['Mars']
    offset = 1.6 * solar.soi['Mars']
    r = rm + np.array([offset, 20000.0, 10000.0])
    v = vm + np.array([-4.0, 0.0, 0.0])
    assert solar.dominant_body(r, 0.0) == 'Sun'
    lead = offset / 4.0
    dv = solve_tcm(solar, r, v, 0.0, 'Mars', lead, 300.0)
    assert dv is not None
    assert 0 < np.linalg.norm(dv) < 1.0
    t, re, ve, dom = propagate_free(
        solar, r, v + dv, 0.0, 2 * lead, fraction=0.0005,
        sample_every=10000, target='Mars', stop_at_target=True)[-1]
    assert dom == 'Mars'
    rm, vm = solar.states(t)['Mars']
    assert (re - rm) @ (ve - vm) < 0
    alt = rv_to_elements(re - rm, ve - vm, gm('Mars')).periapsis - radius('Mars')
    assert alt == pytest.approx(300.0, abs=15.0)


def test_tcm_does_not_arm_at_invalid_arrival():
    api = SpaceflightSimAPI(Time('2027-08-01', scale='tdb'))
    api.add_spacecraft_in_orbit('T', 'Sun', 149_000_000.0)
    ai = ShipAI('T')
    ai.set_target('Mars')
    assert ai.command_tcm(api, t_arrive=api.t) is None
    assert ai.program is None


def test_timestep_thrust_matches_booked_delta_v_at_fuel_exhaustion():
    sc = Spacecraft('T', np.zeros(3), np.zeros(3))
    sc.propellant = 0.1
    sc.throttle = 1.0
    dt = 10.0
    applied = sc.thrust_accel(dt) * dt
    booked = sc.burn_propellant(dt)
    assert applied == pytest.approx(sc.forward * booked)
    assert booked > 0.0
    assert sc.propellant == 0.0
    assert sc.throttle == 0.0
