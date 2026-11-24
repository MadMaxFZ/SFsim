#!/usr/bin/env python3
# tools/headless_mission.py
"""
Headless end-to-end mission check (no display needed):

  1. Start in a 400 km circular orbit about Earth (ecliptic plane).
  2. Warp to the Mars departure window (phase angle), then arm EJECT.
  3. ShipAI waits for the ejection angle, burns prograde (closed-loop on C3),
     the ship leaves Earth's SOI and coasts on a heliocentric transfer.
  4. Two trajectory-correction manoeuvres target a 300 km Mars periapsis
     (one early in cruise, one ~30 days out).
  5. Cruise to Mars' SOI and circularise at periapsis (capture).

Run from the repository root:  python tools/headless_mission.py [start-epoch]
"""

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from astropy.time import Time

from model.api import SpaceflightSimAPI
from model.constants import gm, radius
from model.kepler import rv_to_elements
from shipos import ShipAI, Telemetry
from shipos.guidance import plan_transfer

logging.basicConfig(level=logging.WARNING, format='%(levelname)s:%(message)s')

DAY = 86400.0


def run(api, seconds, warp, dt=1 / 60):
    api.time_warp = warp
    t_end = api.t + seconds
    while t_end - api.t > 1e-7:
        api.advance(min(dt, (t_end - api.t) / warp))


def main():
    epoch = sys.argv[1] if len(sys.argv) > 1 else "2026-10-25"
    api = SpaceflightSimAPI(Time(epoch, scale='tdb'))
    api.add_spacecraft_in_orbit("Explorer", "Earth", 400.0)
    ai = ShipAI("Explorer")
    api.register_controller("Explorer", ai)
    tel = Telemetry(api, "Explorer", ai)
    ai.set_target("Mars")

    ctx = api.context("Explorer")
    plan = plan_transfer(ctx['states'], ctx['dominant'], ctx['r_rel'], ctx['v_rel'], 'Mars',
                         api.solar_system, api.t)
    print(f"Mars window in {plan.wait / DAY:.1f} d, ejection dv {plan.dv_depart * 1000:.0f} m/s, "
          f"TOF {plan.tof / DAY:.0f} d")

    # coast to the window at high warp (budget-limited automatically)
    run(api, plan.wait, 1e5, dt=0.1)
    ctx = api.context("Explorer")
    plan = plan_transfer(ctx['states'], ctx['dominant'], ctx['r_rel'], ctx['v_rel'], 'Mars',
                         api.solar_system, api.t)
    print(f"At window: phase now {np.degrees(plan.phase_now):.1f} deg, "
          f"required {np.degrees(plan.phase_req):.1f} deg, epoch {api.epoch.iso[:10]}")

    ai.command_eject()
    for _ in range(300):                      # wait for burn point + burn (warp 100)
        run(api, 60, 100, dt=1 / 60)
        if ai.program is None:
            break
    sc = api.spacecraft["Explorer"]
    print(f"Burn done: dv expended {sc.dv_expended * 1000:.0f} m/s, log: {[m for _, m in ai.log][:3]}")

    run(api, 5 * DAY, 1e4, dt=0.1)
    print(f"After 5 d: dominant body {api.dominant('Explorer')}")

    tel._last_pred = -1e9
    clo = tel.update()['target']['closest']
    print(f"Uncorrected: closest approach {clo['dist_km']:.3e} km in {(clo['t'] - api.t) / DAY:.0f} d")

    # trajectory correction toward a 300 km Mars periapsis
    dv = ai.command_tcm(api, pe_alt_km=300.0)
    if dv is None:
        raise SystemExit("First TCM could not be verified")
    print(f"TCM solved: {np.linalg.norm(dv) * 1000:.1f} m/s")
    for _ in range(200):
        run(api, 60, 100, dt=1 / 60)
        if ai.program is None:
            break
    tel._last_pred = -1e9
    tgt = tel.update()['target']
    if tgt['encounter']:
        e = tgt['encounter']
        print(f"Predicted Mars SOI encounter in {(e['t'] - api.t) / DAY:.0f} d, "
              f"periapsis alt {e['pe_alt_km']:.0f} km")
    else:
        c = tgt['closest']
        raise SystemExit(f"No SOI encounter after TCM; closest {c['dist_km']:.3e} km")

    # cruise to ~30 days before the encounter, then a second, finer TCM
    run(api, (e['t'] - api.t) - 30 * DAY, 1e5, dt=0.1)
    dv = ai.command_tcm(api, pe_alt_km=300.0)
    if dv is None:
        raise SystemExit("Second TCM could not be verified")
    print(f"TCM-2 solved: {np.linalg.norm(dv) * 1000:.1f} m/s")
    for _ in range(200):
        run(api, 60, 100, dt=1 / 60)
        if ai.program is None:
            break
    tel._last_pred = -1e9
    e = tel.update()['target']['encounter']
    if e is None:
        raise SystemExit("No SOI encounter after second TCM")
    print(f"After TCM-2: predicted periapsis alt {e['pe_alt_km']:.0f} km")

    # cruise to Mars SOI, then capture into a low circular orbit
    while api.dominant("Explorer") != 'Mars':
        run(api, min(DAY, max(DAY / 24, e['t'] - api.t - DAY)), 1e5, dt=0.1)
        if api.t > e['t'] + 5 * DAY:
            raise SystemExit("Missed Mars SOI")
    c = api.context("Explorer")
    incoming = rv_to_elements(c['r_rel'], c['v_rel'], gm('Mars')).periapsis - radius('Mars')
    print(f"Entered Mars SOI at {api.epoch.iso[:16]}, incoming periapsis {incoming:.1f} km")
    ai.command_circularize('PE')
    deadline = api.t + 3 * DAY
    while ai.program is not None and sc.status == 'FLIGHT' and api.t < deadline:
        run(api, 600, 100, dt=1 / 60)
    if ai.program is not None or sc.status != 'FLIGHT':
        raise SystemExit("Mars capture burn did not complete")
    run(api, 3600, 10)
    orb = tel.update()['ship']['orbit']
    if not (orb['body'] == 'Mars' and orb['bound'] and orb['pe_alt_km'] > 0):
        raise SystemExit("Did not achieve a non-impacting Mars orbit")
    print(f"Final: {orb['body']} orbit Pe {orb['pe_alt_km']:.0f} km / Ap {orb['ap_alt_km']:.0f} km, "
          f"e {orb['e']:.4f}, status {sc.status}, dV used {sc.dv_expended * 1000:.0f} m/s, "
          f"remaining {sc.delta_v_remaining * 1000:.0f} m/s")
    print("ShipAI log:", [m for _, m in ai.log][:5])


if __name__ == "__main__":
    main()
