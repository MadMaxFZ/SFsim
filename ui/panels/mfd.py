#!/usr/bin/python
# ui/panels/mfd.py

import math
from enum import Enum, auto

import numpy as np
import pygame

from ui.colors import Colors
from ui.panel_base import PanelBase, fmt_dist, fmt_time, fmt_speed


class MFDMode(Enum):
    ORBIT = auto()
    NAV = auto()
    SYSTEMS = auto()
    ATTITUDE = auto()


class MFD(PanelBase):
    """
    Multi-Function Display. Click the buttons along the bottom edge (or press
    the panel's hot-key with Shift) to cycle pages.

      ORB  osculating elements about the current primary
      NAV  target data, transfer plan, predicted encounter
      SYS  mass, propellant, delta-v budget, engine state, alarms, ShipAI log
      ATT  attitude ball (nose vs. prograde frame), rates, autopilot mode
    """

    MODES = list(MFDMode)
    MODE_LABELS = {MFDMode.ORBIT: "ORB", MFDMode.NAV: "NAV",
                   MFDMode.SYSTEMS: "SYS", MFDMode.ATTITUDE: "ATT"}
    OSB_H = 26

    def __init__(self, screen, rect, app, label="MFD", mode=MFDMode.ORBIT):
        super().__init__(screen, rect, app)
        self.label = label
        self.mode = mode
        self._osb_rects = []

    def render(self) -> None:
        self.clear()
        self.draw_border()
        self.draw_label(f"{self.label} [{self.MODE_LABELS[self.mode]}]", 6, 4,
                        font=self.FONT_MONO_SM, color=self.COLOR_ACCENT)
        {MFDMode.ORBIT: self._orbit, MFDMode.NAV: self._nav,
         MFDMode.SYSTEMS: self._systems, MFDMode.ATTITUDE: self._attitude}[self.mode]()
        self._draw_osbs()

    def _draw_osbs(self) -> None:
        self._osb_rects.clear()
        n = len(self.MODES)
        w = (self.rect.width - 8) // n
        y = self.rect.height - self.OSB_H - 4
        for i, mode in enumerate(self.MODES):
            r = pygame.Rect(4 + i * w, y, w - 4, self.OSB_H)
            color = self.COLOR_ACCENT if mode == self.mode else self.COLOR_BORDER
            pygame.draw.rect(self.surface, color, r, 1)
            self.draw_label(self.MODE_LABELS[mode], r.x + r.w // 2 - 11, r.y + 6,
                            font=self.FONT_MONO_SM, color=color)
            self._osb_rects.append((r, mode))

    # ------------------------------------------------------------------ pages
    def _orbit(self):
        o = self.snap['ship']['orbit']
        y = 24
        y = self.draw_kv("REF", o['body'], y, color=self.COLOR_ACCENT)
        y = self.draw_kv("ALT", fmt_dist(o['alt_km']), y)
        y = self.draw_kv("SPD", fmt_speed(o['speed_kms']), y)
        y = self.draw_kv("VRAD", fmt_speed(o['radial_kms']), y)
        y = self.draw_kv("VCIRC", fmt_speed(o['v_circ_kms']), y, color=self.COLOR_TEXT_DIM)
        y = self.draw_kv("VESC", fmt_speed(o['v_esc_kms']), y, color=self.COLOR_TEXT_DIM)
        y += 6
        pe_col = self.COLOR_DANGER if o['pe_alt_km'] < 0 else None
        y = self.draw_kv("PeA", fmt_dist(o['pe_alt_km']), y, color=pe_col)
        y = self.draw_kv("ApA", fmt_dist(o['ap_alt_km']) if o['bound'] else "  ESCAPE", y,
                         color=None if o['bound'] else self.COLOR_WARNING)
        y = self.draw_kv("SMa", fmt_dist(o['a_km']), y)
        y = self.draw_kv("ECC", f"{o['e']:10.6f}", y)
        y = self.draw_kv("INC", f"{o['i_deg']:9.3f} deg", y)
        y = self.draw_kv("LAN", f"{o['raan_deg']:9.3f} deg", y)
        y = self.draw_kv("AgP", f"{o['argp_deg']:9.3f} deg", y)
        y = self.draw_kv("TrA", f"{o['nu_deg']:9.3f} deg", y)
        y = self.draw_kv("T", fmt_time(o['period_s']), y)
        soi = self.snap['soi'][o['body']]
        self.draw_kv("SOI", fmt_dist(soi) if math.isfinite(soi) else "   inf", y, color=self.COLOR_TEXT_DIM)

    def _nav(self):
        tgt = self.snap['target']
        y = 24
        name = self.snap['ai']['target'] or "---"
        y = self.draw_kv("TGT", name, y, color=Colors.AMBER)
        if not tgt:
            self.draw_label("TAB: cycle target", 6, y + 6, font=self.FONT_MONO_SM, color=self.COLOR_TEXT_DIM)
            return
        y = self.draw_kv("DST", fmt_dist(tgt['distance_km']), y)
        y = self.draw_kv("VREL", fmt_speed(tgt['rel_speed_kms']), y)
        y = self.draw_kv("CLOS", fmt_speed(tgt['closing_kms']), y)
        y += 6
        plan = tgt['plan']
        if plan:
            self.draw_label(f"HOHMANN ({plan.kind[:5]})", 6, y, font=self.FONT_MONO_SM, color=self.COLOR_ACCENT)
            y += 16
            y = self.draw_kv("DV1", fmt_speed(plan.dv_depart), y)
            y = self.draw_kv("DV2", fmt_speed(plan.dv_arrive), y)
            y = self.draw_kv("TOF", fmt_time(plan.tof), y)
            err = math.degrees((plan.phase_now - plan.phase_req + math.pi) % (2 * math.pi) - math.pi)
            y = self.draw_kv("PHA", f"{math.degrees(plan.phase_now):7.2f} deg", y)
            y = self.draw_kv("PHreq", f"{math.degrees(plan.phase_req):7.2f} deg", y)
            col = self.COLOR_ACCENT if abs(err) < 2 else None
            y = self.draw_kv("WAIT", fmt_time(plan.wait), y, color=col)
            if plan.eject_req is not None:
                y = self.draw_kv("EJ", f"{math.degrees(plan.eject_now):7.2f} deg", y)
                y = self.draw_kv("EJreq", f"{math.degrees(plan.eject_req):7.2f} deg", y)
        else:
            self.draw_label("no direct transfer from", 6, y, font=self.FONT_MONO_SM, color=self.COLOR_TEXT_DIM)
            y += 15
            self.draw_label("this primary", 6, y, font=self.FONT_MONO_SM, color=self.COLOR_TEXT_DIM)
            y += 15
        y += 6
        enc, clo = tgt['encounter'], tgt['closest']
        if enc:
            self.draw_label("ENCOUNTER", 6, y, font=self.FONT_MONO_SM, color=self.COLOR_ACCENT)
            y += 16
            y = self.draw_kv("IN", fmt_time(enc['t'] - self.snap['t']), y)
            y = self.draw_kv("PeA", fmt_dist(enc['pe_alt_km']), y,
                             color=self.COLOR_DANGER if enc['pe_alt_km'] < 0 else None)
        elif clo:
            self.draw_label("CLOSEST APPROACH", 6, y, font=self.FONT_MONO_SM, color=self.COLOR_TEXT_DIM)
            y += 16
            y = self.draw_kv("IN", fmt_time(clo['t'] - self.snap['t']), y)
            y = self.draw_kv("DST", fmt_dist(clo['dist_km']), y)

    def _systems(self):
        s = self.snap['ship']
        y = 24
        y = self.draw_kv("STAT", s['status'], y, color=self.COLOR_DANGER if s['status'] != 'FLIGHT' else None)
        y = self.draw_kv("MASS", f"{s['mass_kg']:9.0f} kg", y)
        y = self.draw_kv("PROP", f"{s['propellant_kg']:9.0f} kg", y)
        self._bar(y, s['propellant_frac'], Colors.AMBER if s['propellant_frac'] < 0.1 else self.COLOR_ACCENT)
        y += 12
        y = self.draw_kv("dVrem", f"{s['dv_remaining_ms']:9.0f} m/s", y)
        y = self.draw_kv("dVuse", f"{s['dv_expended_ms']:9.0f} m/s", y)
        y = self.draw_kv("THR", f"{s['throttle'] * 100:8.1f} %", y)
        self._bar(y, s['throttle'], Colors.BRIGHT_AMBER)
        y += 12
        y = self.draw_kv("ACC", f"{s['accel_ms2']:8.2f} m/s2", y)
        y = self.draw_kv("AMAX", f"{s['twr_max_ms2']:8.2f} m/s2", y, color=self.COLOR_TEXT_DIM)
        y += 6
        for al in self.snap['alarms']:
            self.draw_label(f"! {al}", 6, y, font=self.FONT_MONO_SM, color=self.COLOR_DANGER)
            y += 15
        y += 4
        self.draw_label("SHIP AI LOG", 6, y, font=self.FONT_MONO_SM, color=self.COLOR_TEXT_DIM)
        y += 15
        for _, text in self.snap['ai']['log'][:6]:
            self.draw_label(text[:30], 6, y, font=self.FONT_MONO_SM)
            y += 14

    def _bar(self, y, frac, color):
        w = self.rect.width - 70
        pygame.draw.rect(self.surface, self.COLOR_GRID, (58, y, w, 7), 1)
        pygame.draw.rect(self.surface, color, (58, y, int(w * max(0.0, min(1.0, frac))), 7))

    def _attitude(self):
        s = self.snap['ship']
        ai = self.snap['ai']
        y = 24
        y = self.draw_kv("AP", ai['mode'], y, color=self.COLOR_ACCENT)
        y = self.draw_kv("PROG", ai['program'] or "---", y, color=Colors.AMBER if ai['program'] else None)
        # attitude "ball": nose position in the prograde (yaw) / radial (pitch) frame
        cx, cy, R = self.rect.width // 2, y + 80, 70
        pygame.draw.circle(self.surface, self.COLOR_GRID, (cx, cy), R, 1)
        pygame.draw.line(self.surface, self.COLOR_GRID, (cx - R, cy), (cx + R, cy))
        pygame.draw.line(self.surface, self.COLOR_GRID, (cx, cy - R), (cx, cy + R))
        yaw, pitch = s['att_yaw_deg'], s['att_pitch_deg']
        # map +-180 yaw / +-90 pitch onto the disc; prograde marker at centre
        px = cx + int(R * np.clip(yaw / 180.0, -1, 1))
        py = cy - int(R * np.clip(pitch / 90.0, -1, 1))
        pygame.draw.circle(self.surface, Colors.BRIGHT_GREEN, (cx, cy), 4, 1)          # prograde
        pygame.draw.circle(self.surface, Colors.AMBER, (px, py), 5)                    # nose
        self.draw_label("PRO", cx + 6, cy + 4, font=self.FONT_MONO_SM, color=self.COLOR_TEXT_DIM)
        y = cy + R + 10
        y = self.draw_kv("PITCH", f"{pitch:8.2f} deg", y)
        y = self.draw_kv("YAW", f"{yaw:8.2f} deg", y)
        y = self.draw_kv("BANK", f"{s['att_bank_deg']:8.2f} deg", y)
        for axis, val in zip(['wx', 'wy', 'wz'], s['omega']):
            y = self.draw_kv(axis, f"{math.degrees(val):+8.3f} d/s", y)

    # ------------------------------------------------------------------ input
    def next_mode(self):
        i = self.MODES.index(self.mode)
        self.mode = self.MODES[(i + 1) % len(self.MODES)]

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.contains(event.pos):
            lx, ly = self.local(event.pos)
            for r, mode in self._osb_rects:
                if r.collidepoint(lx, ly):
                    self.mode = mode
                    break
