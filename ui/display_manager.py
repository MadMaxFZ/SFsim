#!/usr/bin/python
# ui/display_manager.py

import logging
from typing import Dict, Optional

import numpy as np
import pygame

from model.constants import BODIES
from shipos import ShipAI, Telemetry
from ui.panels.hud import HUD
from ui.panels.mfd import MFD, MFDMode
from ui.panels.orbital_map import OrbitalMap
from ui.panels.telemetry_panel import TelemetryPanel
from ui.panels.timeline_bar import TimelineBar

ATTITUDE_KEYS = {
    pygame.K_1: 'KILLROT', pygame.K_2: 'PROGRADE', pygame.K_3: 'RETROGRADE',
    pygame.K_4: 'NORMAL', pygame.K_5: 'ANTINORMAL', pygame.K_6: 'RADIAL_OUT',
    pygame.K_7: 'RADIAL_IN', pygame.K_8: 'TARGET', pygame.K_9: 'TGT_RETRO',
    pygame.K_0: 'OFF',
}
TARGETS = [n for n in BODIES if n != 'Sun']


class DisplayManager:
    """
    Owns the pygame window, the main loop, keyboard mapping, and the wiring
    between the model API, ShipAI and Telemetry.

    Layout:
    +-----------+--------------------------------+-----------+
    | LEFT MFD  |   ORBITAL MAP  (+ HUD overlay) | RIGHT MFD |
    |           +--------------------------------+           |
    |           |   TELEMETRY STRIP              |           |
    +-----------+--------------------------------+-----------+
    |                    TIMELINE BAR                        |
    +--------------------------------------------------------+
    """

    WIDTH = 1650
    HEIGHT = 980
    FPS_TARGET = 60
    MFD_WIDTH = 270
    TIMELINE_HEIGHT = 64
    TELEMETRY_HEIGHT = 84
    THROTTLE_RATE = 0.5          # full scale per second while Shift/Ctrl held

    def __init__(self, api, ship_name: str = "Explorer"):
        self.api = api
        self.ship_name = ship_name
        self.ai: Optional[ShipAI] = None
        self.telemetry: Optional[Telemetry] = None
        self.snap: dict = {}
        self.running = False
        self.clock = pygame.time.Clock()
        self.screen: Optional[pygame.Surface] = None
        self.panels: Dict[str, object] = {}

    # ------------------------------------------------------------------ setup
    def initialize(self, headless: bool = False) -> None:
        pygame.init()
        pygame.display.set_caption("SFsim - Spaceflight Simulator")
        if self.ship_name not in self.api.spacecraft:
            self.api.add_spacecraft_in_orbit(self.ship_name, "Earth", 400.0)
        self.ai = ShipAI(self.ship_name)
        self.api.register_controller(self.ship_name, self.ai)
        self.telemetry = Telemetry(self.api, self.ship_name, self.ai)
        flags = 0 if headless else pygame.DOUBLEBUF
        self.screen = pygame.display.set_mode((self.WIDTH, self.HEIGHT), flags)
        self._build_layout()
        self.snap = self.telemetry.update()
        logging.info(f"DisplayManager initialized at {self.WIDTH}x{self.HEIGHT}")

    def _build_layout(self) -> None:
        main_h = self.HEIGHT - self.TIMELINE_HEIGHT
        map_w = self.WIDTH - 2 * self.MFD_WIDTH
        map_rect = pygame.Rect(self.MFD_WIDTH, 0, map_w, main_h - self.TELEMETRY_HEIGHT)
        self.panels['left_mfd'] = MFD(self.screen, pygame.Rect(0, 0, self.MFD_WIDTH, main_h),
                                      self, label="L MFD", mode=MFDMode.ORBIT)
        self.panels['right_mfd'] = MFD(self.screen, pygame.Rect(self.WIDTH - self.MFD_WIDTH, 0,
                                                                self.MFD_WIDTH, main_h),
                                       self, label="R MFD", mode=MFDMode.NAV)
        self.panels['orbital_map'] = OrbitalMap(self.screen, map_rect, self)
        self.panels['hud'] = HUD(self.screen, map_rect, self)
        self.panels['telemetry'] = TelemetryPanel(
            self.screen, pygame.Rect(self.MFD_WIDTH, main_h - self.TELEMETRY_HEIGHT, map_w,
                                     self.TELEMETRY_HEIGHT), self)
        self.panels['timeline'] = TimelineBar(
            self.screen, pygame.Rect(0, main_h, self.WIDTH, self.TIMELINE_HEIGHT), self)

    # ---------------------------------------------------------------- commands
    def set_warp(self, rate: float) -> None:
        self.api.time_warp = float(rate)

    def cycle_target(self) -> None:
        cur = self.ai.target
        i = TARGETS.index(cur) if cur in TARGETS else -1
        self.ai.set_target(TARGETS[(i + 1) % len(TARGETS)])

    # -------------------------------------------------------------------- loop
    def run(self, max_frames: Optional[int] = None) -> None:
        self.running = True
        frames = 0
        while self.running:
            dt = self.clock.tick(self.FPS_TARGET) / 1000.0
            self._handle_events()
            self._handle_held_keys(dt)
            self.api.advance(dt)
            self.snap = self.telemetry.update()
            self._render()
            pygame.display.flip()
            frames += 1
            if max_frames and frames >= max_frames:
                break
        pygame.quit()

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                self._on_key(event)
            for panel in self.panels.values():
                panel.handle_event(event)

    def _on_key(self, event) -> None:
        k, ai = event.key, self.ai
        if k == pygame.K_ESCAPE:
            self.running = False
        elif k in ATTITUDE_KEYS:
            ai.set_attitude_mode(ATTITUDE_KEYS[k])
        elif k == pygame.K_TAB:
            self.cycle_target()
        elif k == pygame.K_z:
            ai.set_throttle(1.0)
        elif k == pygame.K_x:
            ai.set_throttle(0.0)
        elif k == pygame.K_b:
            mode = ai.attitude_mode if ai.attitude_mode not in ('OFF', 'KILLROT') else 'PROGRADE'
            ai.command_burn(0.010, mode)
        elif k == pygame.K_j:
            ai.command_eject()
        elif k == pygame.K_p:
            ai.command_circularize('PE')
        elif k == pygame.K_o:
            ai.command_circularize('AP')
        elif k == pygame.K_t:
            ai.command_tcm(self.api)
        elif k == pygame.K_k:
            ai.abort("pilot abort")
        elif k == pygame.K_m:
            self.panels['left_mfd'].next_mode()
        elif k == pygame.K_n:
            self.panels['right_mfd'].next_mode()

    def _handle_held_keys(self, dt: float) -> None:
        keys = pygame.key.get_pressed()
        axes = np.array([
            keys[pygame.K_e] - keys[pygame.K_q],     # roll  (body x)
            keys[pygame.K_s] - keys[pygame.K_w],     # pitch (body y)
            keys[pygame.K_d] - keys[pygame.K_a],     # yaw   (body z)
        ], float)
        self.ai.set_pilot_torque(axes)
        up = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        down = keys[pygame.K_LCTRL] or keys[pygame.K_RCTRL]
        if up or down:
            self.ai.set_throttle(self.ai.pilot_throttle + (up - down) * self.THROTTLE_RATE * dt)

    def _render(self) -> None:
        self.screen.fill((8, 12, 18))
        for name in ('orbital_map', 'left_mfd', 'right_mfd', 'telemetry', 'timeline', 'hud'):
            self.panels[name].render()
