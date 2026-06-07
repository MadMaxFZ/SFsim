# ui/panels/orbital_map.py

import pygame
import numpy as np
import logging
from ui.colors import Colors

# Astronomical unit in metres — used for default scale
AU_M = 1.496e11


class OrbitalMap:
    """
    2-D top-down ecliptic-plane map rendered into a pygame Surface.

    Controls
    --------
    Mouse wheel      : zoom in / out
    Middle-drag      : pan
    Left-click body  : select / focus
    """

    MIN_SCALE = 1e-12  # px / m
    MAX_SCALE = 1e-6

    def __init__(self, rect: pygame.Rect):
        self.rect = rect
        self.surface = pygame.Surface((rect.width, rect.height))

        # View state
        self._scale = 1.5e-9  # pixels per metre (shows inner solar system)
        self._offset = np.array([rect.width / 2, rect.height / 2], dtype=float)
        self._dragging = False
        self._drag_start = None
        self._offset_start = None

        self._selected_body = None
        self._state_snapshot = {}

        # Font
        pygame.font.init()
        self._font_small = pygame.font.SysFont('monospace', 11)
        self._font_label = pygame.font.SysFont('monospace', 13, bold=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, state: dict) -> None:
        """Accept a fresh state snapshot from the API."""
        self._state_snapshot = state

    def draw(self) -> pygame.Surface:
        """Render and return the panel surface."""
        self.surface.fill(Colors.PANEL_BG)
        self._draw_grid()
        self._draw_sun()
        self._draw_bodies()
        self._draw_spacecraft()
        self._draw_hud_overlay()
        return self.surface

    def handle_event(self, event: pygame.event) -> None:
        """Handle mouse events (coordinates relative to the main window)."""
        if event.type == pygame.MOUSEBUTTONDOWN:
            lx, ly = self._to_local(event.pos)
            if not self._in_bounds(lx, ly):
                return
            if event.button == 4:  # wheel up
                self._zoom(1.15, lx, ly)
            elif event.button == 5:  # wheel down
                self._zoom(1 / 1.15, lx, ly)
            elif event.button == 2:  # middle button
                self._dragging = True
                self._drag_start = np.array([lx, ly], dtype=float)
                self._offset_start = self._offset.copy()
            elif event.button == 1:
                self._try_select(lx, ly)

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 2:
                self._dragging = False

        elif event.type == pygame.MOUSEMOTION:
            if self._dragging:
                lx, ly = self._to_local(event.pos)
                delta = np.array([lx, ly], dtype=float) - self._drag_start
                self._offset = self._offset_start + delta

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------

    def _draw_grid(self) -> None:
        """Draw faint concentric AU rings."""
        for au in [0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0]:
            r_px = int(au * AU_M * self._scale)
            cx, cy = int(self._offset[0]), int(self._offset[1])
            if r_px < 2 or r_px > 8000:
                continue
            pygame.draw.circle(self.surface, Colors.GRID_LINE, (cx, cy), r_px, 1)
            label = self._font_small.render(f"{au}AU", True, Colors.GREY)
            self.surface.blit(label, (cx + r_px + 2, cy))

    def _draw_sun(self) -> None:
        cx, cy = int(self._offset[0]), int(self._offset[1])
        pygame.draw.circle(self.surface, Colors.SUN_COLOR, (cx, cy), 6)
        glow = pygame.Surface((30, 30), pygame.SRCALPHA)
        pygame.draw.circle(glow, (255, 220, 80, 40), (15, 15), 15)
        self.surface.blit(glow, (cx - 15, cy - 15))

    def _draw_bodies(self) -> None:
        bodies = self._state_snapshot.get('bodies', {})
        for name, data in bodies.items():
            pos_m = np.array(data['position_m'])
            px, py = self._world_to_screen(pos_m)
            if not self._in_bounds(px, py):
                continue
            color = Colors.BODY_COLORS.get(name, Colors.WHITE)
            radius = 4 if name not in ('Moon',) else 2
            if name == self._selected_body:
                pygame.draw.circle(self.surface, Colors.BRIGHT_CYAN,
                                   (int(px), int(py)), radius + 3, 1,
                                   )
            pygame.draw.circle(self.surface, color, (int(px), int(py)), radius)
            lbl = self._font_label.render(name, True, color)
            self.surface.blit(lbl, (int(px) + radius + 2, int(py) - 6))

    def _draw_spacecraft(self) -> None:
        spacecraft = self._state_snapshot.get('spacecraft', {})
        for name, data in spacecraft.items():
            pos_m = np.array(data['position_m'])
            px, py = self._world_to_screen(pos_m)
            if not self._in_bounds(px, py):
                continue
            # Draw a small triangle marker
            tip = (int(px), int(py) - 7)
            bl = (int(px) - 5, int(py) + 4)
            br = (int(px) + 5, int(py) + 4)
            pygame.draw.polygon(self.surface, Colors.SPACECRAFT_COLOR, [tip, bl, br], 1)
            lbl = self._font_label.render(name, True, Colors.SPACECRAFT_COLOR)
            self.surface.blit(lbl, (int(px) + 8, int(py) - 6))

    def _draw_hud_overlay(self) -> None:
        """Scale bar and zoom level."""
        bar_m = self._round_scale_bar()
        bar_px = int(bar_m * self._scale)
        if 40 < bar_px < self.rect.width // 3:
            x0 = 20
            y0 = self.rect.height - 25
            pygame.draw.line(self.surface, Colors.DIM_WHITE,
                             (x0, y0), (x0 + bar_px, y0), 2,
                             )
            pygame.draw.line(self.surface, Colors.DIM_WHITE,
                             (x0, y0 - 4), (x0, y0 + 4), 2,
                             )
            pygame.draw.line(self.surface, Colors.DIM_WHITE,
                             (x0 + bar_px, y0 - 4), (x0 + bar_px, y0 + 4), 2,
                             )
            label_text = self._format_distance(bar_m)
            lbl = self._font_small.render(label_text, True, Colors.DIM_WHITE)
            self.surface.blit(lbl, (x0, y0 - 16))

    # ------------------------------------------------------------------
    # Coordinate helpers
    # ------------------------------------------------------------------

    def _world_to_screen(self, pos_m: np.ndarray):
        """Convert 3-D world position (m) to 2-D screen pixel coords."""
        x = pos_m[0] * self._scale + self._offset[0]
        y = -pos_m[1] * self._scale + self._offset[1]  # flip y
        return x, y

    def _to_local(self, window_pos):
        return window_pos[0] - self.rect.x, window_pos[1] - self.rect.y

    def _in_bounds(self, lx, ly) -> bool:
        return 0 <= lx < self.rect.width and 0 <= ly < self.rect.height

    def _zoom(self, factor: float, cx: float, cy: float) -> None:
        new_scale = np.clip(self._scale * factor, self.MIN_SCALE, self.MAX_SCALE)
        # Zoom toward cursor
        self._offset[0] = cx + (self._offset[0] - cx) * (new_scale / self._scale)
        self._offset[1] = cy + (self._offset[1] - cy) * (new_scale / self._scale)
        self._scale = new_scale

    def _try_select(self, lx: float, ly: float) -> None:
        best_name = None
        best_dist = 12  # pixel threshold
        for name, data in self._state_snapshot.get('bodies', {}).items():
            pos_m = np.array(data['position_m'])
            px, py = self._world_to_screen(pos_m)
            d = np.hypot(lx - px, ly - py)
            if d < best_dist:
                best_dist = d
                best_name = name
        self._selected_body = best_name

    def _round_scale_bar(self) -> float:
        """Return a 'nice' distance in metres for the scale bar."""
        target_px = 100
        raw_m = target_px / self._scale
        exp = 10 ** np.floor(np.log10(raw_m))
        for factor in [1, 2, 5, 10]:
            if factor * exp * self._scale >= 40:
                return factor * exp
        return raw_m

    @staticmethod
    def _format_distance(metres: float) -> str:
        au = metres / AU_M
        if au >= 0.1:
            return f"{au:.2f} AU"
        km = metres / 1000
        if km >= 1000:
            return f"{km / 1000:.0f} Mm"
        return f"{km:.0f} km"
