# ui/panels/hud.py

import pygame
import math
from ui.colors import Colors


class HUD:
    """
    HUD overlay drawn on top of the orbital map.
    Shows:
      - Artificial horizon / attitude indicator (top-centre)
      - Speed and altitude tape (right edge)
      - Epoch and time-warp (top-left)
    """

    def __init__(self, rect: pygame.Rect):
        self.rect = rect
        self.surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        self._state_snapshot = {}
        self._selected_spacecraft = None

        pygame.font.init()
        self._font = pygame.font.SysFont('monospace', 13)
        self._font_large = pygame.font.SysFont('monospace', 18, bold=True)
        self._font_small = pygame.font.SysFont('monospace', 11)

    def update(self, state: dict) -> None:
        self._state_snapshot = state
        if self._selected_spacecraft is None:
            names = list(state.get('spacecraft', {}).keys())
            if names:
                self._selected_spacecraft = names[0]

    def draw(self) -> pygame.Surface:
        self.surface.fill((0, 0, 0, 0))  # fully transparent
        self._draw_epoch_block()
        self._draw_speed_alt_tape()
        self._draw_attitude_indicator()
        return self.surface

    def handle_event(self, event: pygame.event) -> None:
        pass  # HUD is read-only for now

    # ------------------------------------------------------------------

    def _draw_epoch_block(self) -> None:
        epoch  = self._state_snapshot.get('epoch', '---')
        warp   = self._state_snapshot.get('time_warp', 1)
        sim_s  = self._state_snapshot.get('simulation_time_s', 0.0)

        lines = [
            f"EPOCH  {epoch}",
            f"SIM T  {self._format_elapsed(sim_s)}",
            f"WARP   x{warp}",
        ]
        y = 8
        for line in lines:
            surf = self._font.render(line, True, Colors.BRIGHT_GREEN)
            self.surface.blit(surf, (10, y))
            y += 18

    def _draw_speed_alt_tape(self) -> None:
        sc_data = self._state_snapshot.get('spacecraft', {})
        if not sc_data or self._selected_spacecraft not in sc_data:
            return
        sc = sc_data[self._selected_spacecraft]
        pos = sc['position_m']
        vel = sc['velocity_ms']
        r_km  = (sum(x**2 for x in pos) ** 0.5) / 1000
        alt_km = r_km - 6371.0
        spd_ms = (sum(x**2 for x in vel) ** 0.5)

        x = self.rect.width - 140
        y = 10
        for label, value, unit in [
            ('SPD', f"{spd_ms:>10.1f}", 'm/s'),
            ('ALT', f"{alt_km:>10.1f}", 'km'),
            ('RAD', f"{r_km:>10.1f}", 'km'),
        ]:
            lsurf = self._font.render(f"{label} {value} {unit}",
                                      True, Colors.AMBER)
            self.surface.blit(lsurf, (x, y))
            y += 18

    def _draw_attitude_indicator(self) -> None:
        """Simplified artificial horizon based on quaternion."""
        sc_data = self._state_snapshot.get('spacecraft', {})
        if not sc_data or self._selected_spacecraft not in sc_data:
            return
        sc = sc_data[self._selected_spacecraft]
        q = sc['quaternion']

        # Extract roll and pitch from quaternion
        q0, q1, q2, q3 = q
        pitch = math.asin(max(-1, min(1,  2*(q0*q2 - q3*q1))))
        roll  = math.atan2(2*(q0*q1 + q2*q3), 1 - 2*(q1**2 + q2**2))

        cx = self.rect.width // 2
        cy = 60
        r  = 40

        # Background circle
        pygame.draw.circle(self.surface, (20, 30, 40, 180), (cx, cy), r)
        pygame.draw.circle(self.surface, Colors.PANEL_BORDER, (cx, cy), r, 2)

        # Horizon line rotated by roll
        pitch_px = int(pitch * (r / (math.pi / 4)))   # scale pitch to pixels
        cos_r, sin_r = math.cos(roll), math.sin(roll)
        dx = int(r * cos_r)
        dy = int(r * sin_r)
        hy = cy + pitch_px
        pygame.draw.line(self.surface, Colors.BRIGHT_GREEN,
                         (cx - dx, hy - dy), (cx + dx, hy + dy), 2)

        # Aircraft symbol (fixed)
        pygame.draw.line(self.surface, Colors.AMBER,
                         (cx - 14, cy), (cx - 4, cy), 2)
        pygame.draw.line(self.surface, Colors.AMBER,
                         (cx + 4,  cy), (cx + 14, cy), 2)
        pygame.draw.circle(self.surface, Colors.AMBER, (cx, cy), 2)

    # ------------------------------------------------------------------

    @staticmethod
    def _format_elapsed(seconds: float) -> str:
        seconds = int(seconds)
        d = seconds // 86400
        h = (seconds % 86400) // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{d:03d}d {h:02d}:{m:02d}:{s:02d}"
