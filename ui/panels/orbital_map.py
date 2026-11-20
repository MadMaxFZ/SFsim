#!/usr/bin/python
# ui/panels/orbital_map.py

import math

import numpy as np
import pygame

from model.constants import AU_KM, BODIES, gm, parent, radius
from model.kepler import rv_to_elements, conic_points
from ui.colors import Colors
from ui.panel_base import PanelBase, fmt_dist


class OrbitalMap(PanelBase):
    """
    Top-down ecliptic map centred on a focus body (F cycles focus, C centres
    on the ship's primary). Mouse wheel / PgUp / PgDn zoom over ~10 decades.

    Draws: planetary orbits, bodies (true radius or minimum dot), SOI circles,
    the ship's osculating conic (bound) or predicted coast trajectory
    (escape / interplanetary), the ship marker with nose and velocity vectors,
    and the selected target.
    """

    FOCUS_ORDER = ['Sun'] + [n for n in BODIES if n != 'Sun']

    def __init__(self, screen, rect, app):
        super().__init__(screen, rect, app)
        self.focus = 'Earth'
        self.view_km = 60000.0           # width of the map in km
        self.follow_ship = True
        self._orbit_cache = {}
        self._orbit_cache_t = -1e18

    @property
    def scale(self) -> float:
        return self.rect.width / self.view_km      # px per km

    def to_screen(self, rel_km):
        return (int(self.rect.width / 2 + rel_km[0] * self.scale),
                int(self.rect.height / 2 - rel_km[1] * self.scale))

    def _visible(self, p, margin=50):
        return -margin <= p[0] < self.rect.width + margin and -margin <= p[1] < self.rect.height + margin

    # ------------------------------------------------------------ rendering
    def render(self) -> None:
        snap = self.snap
        self.clear()
        bodies = snap['bodies']
        ship = snap['ship']
        if self.follow_ship:
            self.focus = ship['dominant']
        c = bodies[self.focus]
        self._draw_orbits(c)
        self._draw_bodies(c)
        self._draw_ship_path(c)
        self._draw_ship(c)
        self.draw_border()
        self._draw_overlay()

    def _planet_orbits(self):
        t = self.snap['t']
        if abs(t - self._orbit_cache_t) > 86400 * 2:   # orbits change slowly
            self._orbit_cache = {}
            api = self.app.api
            for name in BODIES:
                if name == 'Sun':
                    continue
                el = api.solar_system.orbit_elements(name, t)
                self._orbit_cache[name] = (parent(name), conic_points(el, 240))
            self._orbit_cache_t = t
        return self._orbit_cache

    def _polyline(self, pts_rel, color, width=1):
        pts = [self.to_screen(p) for p in pts_rel if np.all(np.isfinite(p))]
        pts = [p for p in pts if abs(p[0]) < 20000 and abs(p[1]) < 20000]
        if len(pts) > 1:
            pygame.draw.lines(self.surface, color, False, pts, width)

    def _draw_orbits(self, c):
        bodies = self.snap['bodies']
        for name, (par, pts) in self._planet_orbits().items():
            # skip orbits much smaller than a pixel or far larger than the view
            a = np.max(np.linalg.norm(pts, axis=1))
            if a * self.scale < 3:
                continue
            self._polyline(pts + bodies[par] - c, Colors.ORBIT_LINE)

    def _draw_bodies(self, c):
        snap = self.snap
        tgt = snap['ai']['target']
        for name, pos in snap['bodies'].items():
            p = self.to_screen(pos - c)
            if not self._visible(p, 200):
                continue
            r_px = max(2 if name != 'Sun' else 5, int(radius(name) * self.scale))
            color = Colors.SUN_COLOR if name == 'Sun' else Colors.BODY_COLORS.get(name, (200, 200, 200))
            if r_px > 4000:
                continue
            pygame.draw.circle(self.surface, color, p, r_px)
            soi = snap['soi'].get(name, math.inf)
            if math.isfinite(soi):
                s_px = int(soi * self.scale)
                if 6 < s_px < 4000:
                    pygame.draw.circle(self.surface, Colors.GRID_LINE, p, s_px, 1)
            label_color = Colors.AMBER if name == tgt else self.COLOR_TEXT_DIM
            self.draw_label(name, p[0] + r_px + 3, p[1] - 6, font=self.FONT_MONO_SM, color=label_color)
            if name == tgt:
                pygame.draw.circle(self.surface, Colors.AMBER, p, r_px + 5, 1)

    def _draw_ship_path(self, c):
        snap = self.snap
        ship = snap['ship']
        dom = ship['dominant']
        bodies = snap['bodies']
        pred = snap['prediction']
        if pred:
            # predicted coast: draw relative to the focus body *at each future time*
            api = self.app.api
            pts = []
            for t, r, d in pred:
                pts.append(r - api.solar_system.states(t)[self.focus][0])
            self._polyline(pts, Colors.ORBIT_ACTIVE, 1)
        else:
            orb_rel = ship['r'] - bodies[dom], ship['v'] - (self.app.api.solar_system.states(snap['t'])[dom][1])
            el = rv_to_elements(orb_rel[0], orb_rel[1], gm(dom))
            pts = conic_points(el, 240, max_r=snap['soi'][dom])
            self._polyline(pts + bodies[dom] - c, Colors.ORBIT_ACTIVE, 1)
            # apsis markers
            if el.bound and el.e > 1e-3:
                from model.kepler import perifocal_basis
                P, _ = perifocal_basis(el.i, el.raan, el.argp)
                for rr, tag in ((el.periapsis, 'Pe'), (-el.apoapsis, 'Ap')):
                    p = self.to_screen(P * rr + bodies[dom] - c)
                    pygame.draw.circle(self.surface, Colors.CYAN, p, 3, 1)
                    self.draw_label(tag, p[0] + 4, p[1] + 2, font=self.FONT_MONO_SM, color=Colors.CYAN)

    def _draw_ship(self, c):
        ship = self.snap['ship']
        p = self.to_screen(ship['r'] - c)
        if not self._visible(p):
            return
        s = 6
        color = Colors.RED if ship['status'] == 'CRASHED' else Colors.SPACECRAFT_COLOR
        pygame.draw.polygon(self.surface, color, [(p[0], p[1] - s), (p[0] + s, p[1]),
                                                  (p[0], p[1] + s), (p[0] - s, p[1])], 1)
        f = ship['forward']
        pygame.draw.line(self.surface, Colors.AMBER, p, (p[0] + int(f[0] * 22), p[1] - int(f[1] * 22)), 1)
        self.draw_label(ship['name'], p[0] + s + 3, p[1] - 6, font=self.FONT_MONO_SM, color=color)

    def _draw_overlay(self):
        # scale bar: largest 1-2-5 step below 1/4 of the width
        target_km = self.view_km / 4
        mag = 10 ** math.floor(math.log10(target_km))
        step = max(m * mag for m in (1, 2, 5) if m * mag <= target_km)
        bar_px = int(step * self.scale)
        x0, y0 = 20, self.rect.height - 20
        pygame.draw.line(self.surface, self.COLOR_TEXT_DIM, (x0, y0), (x0 + bar_px, y0), 1)
        for x in (x0, x0 + bar_px):
            pygame.draw.line(self.surface, self.COLOR_TEXT_DIM, (x, y0 - 4), (x, y0 + 4), 1)
        self.draw_label(fmt_dist(step).strip(), x0, y0 - 18, font=self.FONT_MONO_SM, color=self.COLOR_TEXT_DIM)
        mode = "FOLLOW" if self.follow_ship else "FIXED"
        self.draw_label(f"MAP  focus {self.focus} [{mode}]  width {fmt_dist(self.view_km).strip()}",
                        x0, y0 - 36, font=self.FONT_MONO_SM,
                        color=self.COLOR_TEXT_DIM)

    # --------------------------------------------------------------- input
    def zoom(self, factor):
        self.view_km = float(np.clip(self.view_km * factor, 2000.0, 200 * AU_KM))

    def cycle_focus(self):
        self.follow_ship = False
        i = self.FOCUS_ORDER.index(self.focus)
        self.focus = self.FOCUS_ORDER[(i + 1) % len(self.FOCUS_ORDER)]
        self.view_km = max(self.view_km, 20 * radius(self.focus))

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEWHEEL and self.contains(pygame.mouse.get_pos()):
            self.zoom(0.85 if event.y > 0 else 1 / 0.85)
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_PAGEUP:
                self.zoom(0.5)
            elif event.key == pygame.K_PAGEDOWN:
                self.zoom(2.0)
            elif event.key == pygame.K_f:
                self.cycle_focus()
            elif event.key == pygame.K_c:
                self.follow_ship = True
