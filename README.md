# SFsim

Experimental spaceflight simulator: an instrumented ship that can navigate the
solar system, flown by a pilot together with a ShipAI (the ship's operating system).

## Run

```bash
pip install -r requirements.txt
python sim_app.py                       # 400 km orbit about Earth, epoch 2026-01-01
python sim_app.py --epoch 2026-11-20    # start near the 2026 Mars departure window
python tools/headless_mission.py        # scripted LEO -> Mars ejection, no display
python -m pytest -q tests               # physics / autopilot tests
```

## Layout

```text
sim_app.py              entry point (argparse: --epoch --body --alt --inc)
model/                  physics; knows nothing about UI or ShipAI
  constants.py          GM, radii, body hierarchy, ecliptic rotation (units: km, s, kg)
  kepler.py             rv <-> elements, conic sampling, vectorised elliptic propagation
  ephemeris.py          SolarSystem: astropy built-in ephemeris at epoch -> Kepler orbits;
                        SOI radii; dominant-body lookup
  dynamics.py           dominant-body-frame RK4 with third-body perturbations; coast predictor
  rotations.py          quaternion utilities (body -> inertial)
  spacecraft.py         Spacecraft + ShipConfig: propellant, thrust, Isp, RCS, inertia
  api.py                SpaceflightSimAPI: clock, warp, sub-stepping, SOI hand-over,
                        impact detection, controller protocol
shipos/                 ship operating system
  guidance.py           reference directions, orbit summary, Hohmann / ejection planning
  autopilot.py          attitude control laws (rate-limited slew, kill-rotation, snap)
  ship_ai.py            ShipAI: attitude modes, programs (BURN / EJECT / CIRC),
                        pilot override, alarms, event log
  telemetry.py          per-frame snapshot for all instruments + trajectory predictor
ui/                     pygame cockpit
  display_manager.py    window, main loop, keyboard mapping, wiring
  panel_base.py         panel base class + formatting helpers
  colors.py             palette
  panels/               orbital_map, mfd (ORB/NAV/SYS/ATT), hud, telemetry_panel, timeline_bar
tests/test_physics.py
tools/headless_mission.py
```

Data flow per frame: `keys -> ShipAI -> SpaceflightSimAPI.advance()` (ShipAI is
called inside every sub-step for throttle, programs and attitude) `-> Telemetry.update()
-> panels`. Panels read only the telemetry snapshot.

## Physics model

* Frame: heliocentric J2000 ecliptic. Bodies: Sun, 8 planets, Moon.
* Body states come from astropy's built-in ephemeris at the start epoch and are
  then propagated as Kepler orbits about their parents (cheap and smooth; drifts
  slowly over years versus a full ephemeris).
* The ship is integrated with RK4 relative to its dominant body (Laplace SOI),
  with every other body as a third-body perturbation, so lunar and solar effects
  and SOI transitions happen naturally. The sub-step is 0.4 % of the local orbital period.
* Finite burns with propellant consumption (Tsiolkovsky). Default ship: 30 t
  wet, 120 kN, Isp 3500 s, about 45 km/s total delta-v (edit `ShipConfig`).
* Attitude: rigid body with RCS torque at warp up to x10. Above x10 the autopilot
  holds attitude ideally (Orbiter style). Free rotation persists with AP off.
* Physics CPU time is capped per frame. At very high warp the HUD shows the warp
  actually achieved and raises a `WARP LIMITED` alarm.

## Controls

| Key | Action |
|---|---|
| 1..9, 0 | AP: KILLROT, PROGRADE, RETRO, NORMAL, ANTINORMAL, RADIAL+, RADIAL-, TARGET, TGT-RETRO, OFF |
| W/S, A/D, Q/E | manual pitch / yaw / roll (switches AP off) |
| Shift / Ctrl | throttle up / down; Z full, X cut |
| TAB | cycle target |
| , . | time warp down / up (or click the timeline buttons) |
| B | burn 10 m/s along current AP direction |
| J | EJECT: wait for the ejection angle, then burn to the target planet |
| P / O | circularise at next periapsis / apoapsis |
| T | TCM: solve and fly a trajectory correction for a 300 km periapsis at the target |
| K | abort program |
| F / C | map focus cycle / follow ship; PgUp/PgDn/wheel zoom |
| M / N | cycle left / right MFD page |

## Example: Earth -> Mars

1. Target Mars (TAB). Open the NAV page and warp until `WAIT` is near 0 (the phase angle matches the required angle).
2. Press `J`. ShipAI holds prograde, waits for `EJ` to reach `EJreq`, then executes the ejection burn.
3. After the SOI change to the Sun, NAV shows the predicted encounter or closest approach. Press `T`
   a few days out for a first correction, then again about 30 days before arrival to refine the
   periapsis (the headless mission reaches a ~550 x 640 km Mars orbit this way).
4. Inside Mars' SOI, press `P` to capture and circularise at periapsis.
