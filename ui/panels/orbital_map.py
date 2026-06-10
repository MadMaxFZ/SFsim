#!/usr/bin/python
# ui/panels/orbital_map.py

import pygame
import numpy as np
from astropy import units as u
from ui.panel_base import PanelBase


class OrbitalMap(PanelBase):
    """
    2D top-down ecliptic plane view of the solar system.
    Supports zoom and pan. Bodies rendered as colored dots with labels.
    Spacecraft rendered with velocity vector indicator.
    """

    BODY_COLORS = {
        'Mercury': (180, 140, 100),
        'Venus':   (220, 200, 100),
        'Earth':   ( 80, 140, 220),
        'Moon':    (180, 180, 180),
        'Mars':    (200,  80,  60),
        'Jupiter': (200, 160, 120),
        'Saturn':  (220, 200, 140),
        'Uranus':  (140, 200, 220),
        'Neptune': ( 80, 100, 220),
    }

    BODY_RADIUS_PX = {
        'Sun':     8,
        'Earth':   4,
        'Moon':    2,
        'default': 3,
    }

    AU_TO_KM = 1.496e08  # kilometers per AU

    def __init__(self, screen, rect, api):
        super().__init__(screen, rect, api)
        # Default view: 6 AU across the map width
        self.view_au = 6.0
        self.center_offset = np.array([0.0, 0.0])  # pan offset in AU
        self._dragging = False
        self._drag_start = None

    @property
    def scale(self) -> float:
        """Pixels per AU."""
        return self.rect.width / self.view_au

    def world_to_screen(self, x_m: float, y_m: float):
        """Convert meters (heliocentric) to screen pixel coords."""
        # if type(x_m) == type(1 * u.s):
        #     x_m = x_m.value
        # if type(y_m) == type(1 * u.s):
        #     y_m = y_m.value
        x_au = x_m.to(u.AU).value
        y_au = y_m.to(u.AU).value
        cx = self.rect.width / 2 + self.center_offset[0] * self.scale
        cy = self.rect.height / 2 + self.center_offset[1] * self.scale
        px = cx + x_au * self.scale
        py = cy - y_au * self.scale # y flipped for screen coords
        pass
        return int(px), int(py)

    def render(self) -> None:
        self.clear()
        self._draw_grid()
        self._draw_sun()
        self._draw_bodies()
        self._draw_spacecraft()
        self.draw_border()
        self._draw_scale_indicator()

    def _draw_grid(self) -> None:
        """Concentric AU rings."""
        cx = self.rect.width // 2 + int(self.center_offset[0] * self.scale)
        cy = self.rect.height // 2 + int(self.center_offset[1] * self.scale)
        for r_au in [0.5, 1.0, 1.5, 2.0, 3.0, 5.0]:
            r_px = int(r_au * self.scale)
            pygame.draw.circle(self.surface, self.COLOR_GRID,
                               (cx, cy), r_px, 1)

    def _draw_sun(self) -> None:
        cx = self.rect.width // 2 + int(self.center_offset[0] * self.scale)
        cy = self.rect.height // 2 + int(self.center_offset[1] * self.scale)
        pygame.draw.circle(self.surface, (255, 220, 60), (cx, cy), 8)
        pygame.draw.circle(self.surface, (255, 255, 120), (cx, cy), 4)

    def _draw_bodies(self) -> None:
        state = self.api.get_system_state()
        bodies = state.get('bodies', {})
        for name, data in bodies.items():
            pos = data.get('position_km')
            if pos is None:
                continue
            x, y = self.world_to_screen(pos[0], pos[1])
            if not (0 <= x < self.rect.width and 0 <= y < self.rect.height):
                continue
            color = self.BODY_COLORS.get(name, (200, 200, 200))
            r = self.BODY_RADIUS_PX.get(name, self.BODY_RADIUS_PX['default'])
            pygame.draw.circle(self.surface, color, (x, y), r)
            self.draw_label(name, x + r + 2, y - 6,
                            font=self.FONT_MONO_SM,
                            color=self.COLOR_TEXT_DIM)

    def _draw_spacecraft(self) -> None:
        state = self.api.get_system_state()
        spacecraft = state.get('spacecraft', {})
        for name, data in spacecraft.items():
            pos = data.get('position_km')
            if pos is None:
                continue
            x, y = self.world_to_screen(pos[0], pos[1])
            if not (0 <= x < self.rect.width and 0 <= y < self.rect.height):
                continue
            # Draw diamond marker
            size = 5
            points = [(x, y - size), (x + size, y),
                      (x, y + size), (x - size, y)]
            pygame.draw.polygon(self.surface, self.COLOR_ACCENT, points, 1)
            self.draw_label(name, x + size + 2, y - 6,
                            font=self.FONT_MONO_SM,
                            color=self.COLOR_ACCENT)

    def _draw_scale_indicator(self) -> None:
        """Draw a 1 AU scale bar in the bottom-left corner."""
        bar_au = 1.0
        bar_px = int(bar_au * self.scale)
        x0 = 20
        y0 = self.rect.height - 20
        pygame.draw.line(self.surface, self.COLOR_TEXT_DIM,
                         (x0, y0), (x0 + bar_px, y0), 1)
        pygame.draw.line(self.surface, self.COLOR_TEXT_DIM,
                         (x0, y0 - 4), (x0, y0 + 4), 1)
        pygame.draw.line(self.surface, self.COLOR_TEXT_DIM,
                         (x0 + bar_px, y0 - 4), (x0 + bar_px, y0 + 4), 1)
        self.draw_label("1 AU", x0 + bar_px // 2 - 12, y0 - 18,
                        font=self.FONT_MONO_SM, color=self.COLOR_TEXT_DIM)

    def handle_event(self, event: pygame.event.Event) -> None:
        # Translate event coords to panel-local coords
        if event.type == pygame.MOUSEBUTTONDOWN:
            lx = event.pos[0] - self.rect.x
            ly = event.pos[1] - self.rect.y
            if not (0 <= lx < self.rect.width and 0 <= ly < self.rect.height):
                return
            if event.button == 4:  # scroll up — zoom in
                self.view_au = max(0.1, self.view_au * 0.9)
            elif event.button == 5:  # scroll down — zoom out
                self.view_au = min(60.0, self.view_au * 1.1)
            elif event.button == 2:  # middle click — pan start
                self._dragging = True
                self._drag_start = (lx, ly)

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 2:
                self._dragging = False

        elif event.type == pygame.MOUSEMOTION:
            if self._dragging:
                lx = event.pos[0] - self.rect.x
                ly = event.pos[1] - self.rect.y
                dx = (lx - self._drag_start[0]) / self.scale
                dy = -(ly - self._drag_start[1]) / self.scale
                self.center_offset += np.array([dx, dy])
                self._drag_start = (lx, ly)
