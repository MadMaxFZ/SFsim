#!/usr/bin/python
# ui/display_manager.py

import pygame
import logging
from typing import Dict, Optional
from astropy import units as u
from poliastro.twobody import Orbit
from poliastro.bodies import Earth
import numpy as np
from ui.panels.mfd import MFD, MFDMode
from ui.panels.hud import HUD
from ui.panels.telemetry_panel import TelemetryPanel
from ui.panels.timeline_bar import TimelineBar
from ui.panels.orbital_map import OrbitalMap
from model.spacecraft import Spacecraft


class DisplayManager:
    """
    Top-level UI manager. Owns the pygame window and dispatches
    rendering and input to child panels.

    Layout (1920x1080 default):
    ┌─────────────────────────────────────────────────────┐
    │  LEFT MFD  │      ORBITAL MAP (main view)  │ RT MFD │
    │  240x480   │         1200x900              │240x480 │
    │            ├───────────────────────────────┤        │
    │            │      TELEMETRY STRIP          │        │
    ├────────────┴───────────────────────────────┴────────┤
    │                  TIMELINE BAR  (1920x120)           │
    └─────────────────────────────────────────────────────┘
    HUD is overlaid on the main view.
    """

    WIDTH = 1650
    HEIGHT = 980
    FPS_TARGET = 60

    # Layout rects
    MFD_WIDTH = 240
    MFD_HEIGHT = 480
    TIMELINE_HEIGHT = 120
    TELEMETRY_HEIGHT = 120

    def __init__(self, api):
        self.api = api
        self.running = False
        self.clock = pygame.time.Clock()
        self.screen: Optional[pygame.Surface] = None
        self.panels: Dict[str, object] = {}

    def initialize(self) -> None:
        pygame.init()
        pygame.display.set_caption("SFsim - Spaceflight Simulator")

        initial_orbit = Orbit.circular(Earth, alt=400 * u.km)
        self.api.add_spacecraft(
                name="Explorer",
                orbit=initial_orbit,
                mass=1000.0 * u.kg
                )
        self.api.spacecraft["Explorer"].rotation.angular_velocity = np.array([0.1, 0.05, -0.02])

        self.api.register_spacecraft_hook(
                spacecraft_name="Explorer",
                callback=self.attitude_control_hook,
                hook_type="pre_attitude_control"
                )

        self.screen = pygame.display.set_mode(
                (self.WIDTH, self.HEIGHT),
                pygame.DOUBLEBUF | pygame.HWSURFACE,
                )
        self._build_layout()
        logging.info(f"DisplayManager initialized at {self.WIDTH}x{self.HEIGHT}")

    def _build_layout(self) -> None:
        main_top = 0
        main_bottom = self.HEIGHT - self.TIMELINE_HEIGHT
        main_height = main_bottom  # full height minus timeline

        left_mfd_rect = pygame.Rect(0, 0, self.MFD_WIDTH, self.MFD_HEIGHT)
        right_mfd_rect = pygame.Rect(
            self.WIDTH - self.MFD_WIDTH, 0, self.MFD_WIDTH, self.MFD_HEIGHT
        )

        map_rect = pygame.Rect(
            self.MFD_WIDTH, 0,
            self.WIDTH - 2 * self.MFD_WIDTH,
            main_height - self.TELEMETRY_HEIGHT
        )

        telemetry_rect = pygame.Rect(
            self.MFD_WIDTH,
            main_height - self.TELEMETRY_HEIGHT,
            self.WIDTH - 2 * self.MFD_WIDTH,
            self.TELEMETRY_HEIGHT
        )

        timeline_rect = pygame.Rect(
            0, self.HEIGHT - self.TIMELINE_HEIGHT,
            self.WIDTH, self.TIMELINE_HEIGHT
        )

        self.panels['left_mfd'] = MFD(
            self.screen, left_mfd_rect, self.api, label="LEFT MFD"
        )
        self.panels['right_mfd'] = MFD(
            self.screen, right_mfd_rect, self.api, label="RIGHT MFD"
        )
        self.panels['orbital_map'] = OrbitalMap(
            self.screen, map_rect, self.api
        )
        self.panels['hud'] = HUD(
            self.screen, map_rect, self.api
        )
        self.panels['telemetry'] = TelemetryPanel(
            self.screen, telemetry_rect, self.api
        )
        self.panels['timeline'] = TimelineBar(
            self.screen, timeline_rect, self.api
        )
        logging.info(f"Layout completed...")

    def run(self) -> None:
        self.running = True
        while self.running:
            dt_ms = self.clock.tick(self.FPS_TARGET)
            dt_s = dt_ms / 1000.0
            self._handle_events()
            self._update(dt_s)
            self._render()
            pygame.display.flip()
        pygame.quit()

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
            # Route input events to panels
            for panel in self.panels.values():
                if hasattr(panel, 'handle_event'):
                    panel.handle_event(event)

    def _update(self, dt: float) -> None:
        self.api.propagate_system(dt * u.s)
        for panel in self.panels.values():
            if hasattr(panel, 'update'):
                panel.update(self.api.simulation_time)

    def _render(self) -> None:
        self.screen.fill((8, 12, 18))  # near-black space background
        render_order = [
            'orbital_map',
            'left_mfd',
            'right_mfd',
            'telemetry',
            'timeline',
            'hud',   # HUD last so it overlays everything
        ]
        for name in render_order:
            panel = self.panels.get(name)
            if panel and hasattr(panel, 'render'):
                panel.render()
        self._render_fps()

    def _render_fps(self) -> None:
        fps = self.clock.get_fps()
        font = pygame.font.SysFont('monospace', 14)
        surf = font.render(f"FPS: {fps:.1f}", True, (80, 180, 80))
        self.screen.blit(surf, (self.WIDTH - 90, 4))

    def attitude_control_hook(self, time_step: u.Quantity, spacecraft: Spacecraft) -> None:
        """
        Attitude control hook implementing damping with torque clamping.

        Reads the spacecraft's actual inertia tensor to ensure the clamp
        calculation matches the dynamics model exactly, guaranteeing monotonic
        convergence to zero angular velocity with no overshoot.
        """
        kd = 50.0  # N*m / (rad/s) damping gain — only affects pre-clamp magnitude

        dt = time_step.to(u.s).value

        # Read inertia diagonal from the spacecraft's actual inertia tensor
        inertia = np.diag(np.array(spacecraft['inertia_tensor']))  # kg*m², shape (3,)

        current_omega = spacecraft['angular_velocity_rads']  # plain numpy array, rad/s)

        # Unclamped damping torque
        damping_torque = -kd * current_omega  # N*m

        # Clamp: each axis torque cannot produce delta_omega larger than |omega| on that axis
        # max_torque_i = I_i * |omega_i| / dt  →  delta_omega_i = max_torque_i * dt / I_i = |omega_i|
        max_torque = inertia * np.abs(current_omega) / dt
        clamped_torque = np.sign(damping_torque) * np.minimum(np.abs(damping_torque), max_torque)

        torque = clamped_torque * (u.N * u.m)

        logging.info(
                f"Attitude control: omega={np.array2string(current_omega, precision=4)} rad/s | "
                f"torque={np.array2string(clamped_torque, precision=3)} N*m | "
                f"inertia_diag={np.array2string(inertia, precision=1)} kg*m²"
                )
        self.api.spacecraft[spacecraft['name']].apply_torque(torque)

