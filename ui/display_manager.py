# ui/display_manager.py

import pygame
import logging
from ui.colors import Colors
from ui.panels.orbital_map import OrbitalMap
from ui.panels.mfd import MFD
from ui.panels.hud import HUD
from ui.panels.telemetry_panel import TelemetryPanel
from ui.panels.timeline_bar import TimelineBar
from astropy import units as u


class DisplayManager:
    """
    Top-level UI manager.

    Layout (1920 x 1080):
    ┌──────────┬──────────────────────────────┬──────────┐
    │ LEFT MFD │         ORBITAL MAP          │ RIGHT MFD│
    │ 240x840  │         1440x720             │ 240x840  │
    │          ├──────────────────────────────┤          │
    │          │     TELEMETRY  1440x120      │          │
    ├──────────┴──────────────────────────────┴──────────┤
    │                TIMELINE BAR  1920x120              │
    └────────────────────────────────────────────────────┘
    HUD overlaid on ORBITAL MAP.
    """

    W, H          = 1920, 1080
    MFD_W         = 240
    TIMELINE_H    = 120
    TELEMETRY_H   = 100
    FPS           = 60
    SIM_STEP_S    = 1.0        # simulation seconds advanced per real frame at warp x1

    def __init__(self, api):
        self.api = api
        self._clock = None
        self._screen = None
        self._panels = {}
        self._running = False

    def initialize(self) -> None:
        pygame.init()
        self._screen = pygame.display.set_mode((self.W, self.H))
        pygame.display.set_caption("SpaceflightSim")
        self._clock = pygame.time.Clock()
        self._build_panels()
        logging.info("DisplayManager initialized")

    def run(self) -> None:
        self._running = True
        while self._running:
            dt_real = self._clock.tick(self.FPS) / 1000.0  # real seconds

            # --- events ---
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self._running = False
                self._dispatch_event(event)

            # --- simulate ---
            timeline: TimelineBar = self._panels['timeline']
            if not timeline.is_paused():
                warp = timeline.current_warp()
                if warp > 0:
                    sim_step = self.SIM_STEP_S * warp * dt_real * u.s
                    try:
                        self.api.propagate_system(sim_step)
                    except Exception as e:
                        logging.warning(f"propagate_system error: {e}")

            # --- fetch state ---
            try:
                state = self.api.get_system_state()
            except Exception as e:
                logging.warning(f"get_system_state error: {e}")
                state = {}

            # --- update panels ---
            for panel in self._panels.values():
                panel.update(state)

            # --- draw ---
            self._screen.fill(Colors.BACKGROUND)
            self._screen.blit(
                self._panels['map'].draw(),
                (self.MFD_W, 0)
            )
            self._screen.blit(
                self._panels['hud'].draw(),
                (self.MFD_W, 0)
            )
            self._screen.blit(
                self._panels['left_mfd'].draw(),
                (0, 0)
            )
            self._screen.blit(
                self._panels['right_mfd'].draw(),
                (self.W - self.MFD_W, 0)
            )
            self._screen.blit(
                self._panels['telemetry'].draw(),
                (self.MFD_W, self.H - self.TIMELINE_H - self.TELEMETRY_H)
            )
            self._screen.blit(
                self._panels['timeline'].draw(),
                (0, self.H - self.TIMELINE_H)
            )

            pygame.display.flip()

        pygame.quit()

    # ------------------------------------------------------------------

    def _build_panels(self) -> None:
        map_w = self.W - 2 * self.MFD_W
        main_h = self.H - self.TIMELINE_H - self.TELEMETRY_H

        self._panels['map'] = OrbitalMap(
            pygame.Rect(0, 0, map_w, main_h)
        )
        self._panels['hud'] = HUD(
            pygame.Rect(0, 0, map_w, main_h)
        )
        self._panels['left_mfd'] = MFD(
            pygame.Rect(0, 0, self.MFD_W, self.H - self.TIMELINE_H),
            side='left'
        )
        self._panels['right_mfd'] = MFD(
            pygame.Rect(0, 0, self.MFD_W, self.H - self.TIMELINE_H),
            side='right'
        )
        self._panels['telemetry'] = TelemetryPanel(
            pygame.Rect(0, 0, map_w, self.TELEMETRY_H)
        )
        self._panels['timeline'] = TimelineBar(
            pygame.Rect(0, 0, self.W, self.TIMELINE_H),
            api=self.api
        )

    def _dispatch_event(self, event: pygame.Event) -> None:
        """Route events to panels, offsetting mouse coords as needed."""
        self._panels['map'].handle_event(
            self._offset_mouse_event(event, self.MFD_W, 0)
        )
        self._panels['left_mfd'].handle_event(event)
        self._panels['right_mfd'].handle_event(
            self._offset_mouse_event(event, -(self.W - self.MFD_W), 0)
        )
        self._panels['timeline'].handle_event(
            self._offset_mouse_event(event, 0, -(self.H - self.TIMELINE_H))
        )

    @staticmethod
    def _offset_mouse_event(event: pygame.Event,
                             dx: int, dy: int) -> pygame.Event:
        """Return a shallow copy of a mouse event with shifted coordinates."""
        if event.type in (pygame.MOUSEBUTTONDOWN,
                          pygame.MOUSEBUTTONUP,
                          pygame.MOUSEMOTION):
            d = event.__dict__.copy()
            x, y = d.get('pos', (0, 0))
            d['pos'] = (x + dx, y + dy)
            new_event = pygame.event.Event(event.type, d)
            return new_event
        return event
