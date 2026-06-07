# ui/panels/telemetry_panel.py

import pygame
from ui.colors import Colors


class TelemetryPanel:
    """
    Horizontal strip below the orbital map.
    Shows key scalars for all spacecraft side-by-side.
    """

    def __init__(self, rect: pygame.Rect):
        self.rect = rect
        self.surface = pygame.Surface((rect.width, rect.height))
        self._state_snapshot = {}

        pygame.font.init()
        self._font = pygame.font.SysFont('monospace', 12)
        self._font_title = pygame.font.SysFont('monospace', 12, bold=True)

    def update(self, state: dict) -> None:
        self._state_snapshot = state

    def draw(self) -> pygame.Surface:
        self.surface.fill(Colors.PANEL_BG)
        pygame.draw.line(self.surface, Colors.PANEL_BORDER,
                         (0, 0), (self.rect.width, 0), 2)

        sc_data = self._state_snapshot.get('spacecraft', {})
        x = 10
        for name, sc in sc_data.items():
            pos = sc['position_m']
            vel = sc['velocity_ms']
            r_km  = (sum(p**2 for p in pos)**0.5) / 1000
            v_ms  = (sum(v**2 for v in vel)**0.5)
            alt   = r_km - 6371.0

            col_lines = [
                name,
                f"ALT {alt:.1f} km",
                f"SPD {v_ms:.1f} m/s",
                f"M   {sc['mass_kg']:.0f} kg",
            ]
            y = 6
            for i, line in enumerate(col_lines):
                color = Colors.BRIGHT_CYAN if i == 0 else Colors.GREEN
                surf = self._font.render(line, True, color)
                self.surface.blit(surf, (x, y))
                y += 16
            x += 220

        return self.surface

    def handle_event(self, event: pygame.Event) -> None:
        pass
