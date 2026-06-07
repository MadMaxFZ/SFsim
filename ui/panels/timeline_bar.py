# ui/panels/timeline_bar.py

import pygame
from ui.colors import Colors


class TimelineBar:
    """
    Bottom bar: mission clock, time-warp controls, pause button.
    """

    WARP_RATES = [0, 1, 10, 100, 1_000, 10_000, 100_000]

    def __init__(self, rect: pygame.Rect, api):
        self.rect = rect
        self.api = api
        self.surface = pygame.Surface((rect.width, rect.height))
        self._paused = False
        self._warp_index = 1    # default: x1
        self._state_snapshot = {}
        self._button_rects = []

        pygame.font.init()
        self._font = pygame.font.SysFont('monospace', 14)
        self._font_large = pygame.font.SysFont('monospace', 22, bold=True)

        # Sync warp to API
        self.api.time_warp = self.WARP_RATES[self._warp_index]

    # ------------------------------------------------------------------

    def update(self, state: dict) -> None:
        self._state_snapshot = state

    def draw(self) -> pygame.Surface:
        self.surface.fill(Colors.PANEL_BG)
        pygame.draw.line(self.surface, Colors.PANEL_BORDER,
                         (0, 0), (self.rect.width, 0), 2)

        self._draw_clock()
        self._draw_warp_controls()
        self._draw_pause_button()
        return self.surface

    def handle_event(self, event: pygame.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            lx = event.pos[0] - self.rect.x
            ly = event.pos[1] - self.rect.y
            for i, r in enumerate(self._button_rects):
                if r.collidepoint(lx, ly):
                    self._handle_button(i)

    def is_paused(self) -> bool:
        return self._paused

    def current_warp(self) -> int:
        return self.WARP_RATES[self._warp_index]

    # ------------------------------------------------------------------

    def _draw_clock(self) -> None:
        epoch   = self._state_snapshot.get('epoch', '---')
        sim_s   = self._state_snapshot.get('simulation_time_s', 0.0)
        elapsed = self._format_elapsed(sim_s)

        surf = self._font_large.render(elapsed, True, Colors.BRIGHT_GREEN)
        self.surface.blit(surf, (20, 14))

        sub = self._font.render(f"EPOCH  {epoch}", True, Colors.DIM_WHITE)
        self.surface.blit(sub, (20, 46))

    def _draw_warp_controls(self) -> None:
        """Draw << | WARP xN | >> buttons."""
        self._button_rects = []
        cx = self.rect.width // 2
        cy = self.rect.height // 2

        labels = ['<<', f"WARP  x{self.WARP_RATES[self._warp_index]}", '>>']
        widths = [50, 160, 50]
        x = cx - sum(widths) // 2

        for i, (label, w) in enumerate(zip(labels, widths)):
            r = pygame.Rect(x, cy - 18, w, 36)
            self._button_rects.append(r)
            pygame.draw.rect(self.surface, Colors.DARK_GREY, r)
            pygame.draw.rect(self.surface, Colors.PANEL_BORDER, r, 1)
            color = Colors.AMBER if i == 1 else Colors.DIM_WHITE
            surf = self._font.render(label, True, color)
            self.surface.blit(surf, (r.x + (w - surf.get_width()) // 2,
                                     r.y + (36 - surf.get_height()) // 2))
            x += w + 4

    def _draw_pause_button(self) -> None:
        label = '  PAUSE  ' if not self._paused else ' RESUME  '
        color = Colors.RED if not self._paused else Colors.BRIGHT_GREEN
        r = pygame.Rect(self.rect.width - 140, self.rect.height // 2 - 18, 120, 36)
        self._button_rects.append(r)
        pygame.draw.rect(self.surface, Colors.DARK_GREY, r)
        pygame.draw.rect(self.surface, color, r, 2)
        surf = self._font.render(label, True, color)
        self.surface.blit(surf, (r.x + (120 - surf.get_width()) // 2,
                                  r.y + (36 - surf.get_height()) // 2))

    def _handle_button(self, index: int) -> None:
        # 0=<<, 1=WARP display (ignored), 2=>>, 3=PAUSE
        if index == 0:
            self._warp_index = max(0, self._warp_index - 1)
            self.api.time_warp = self.WARP_RATES[self._warp_index]
        elif index == 2:
            self._warp_index = min(len(self.WARP_RATES) - 1,
                                   self._warp_index + 1)
            self.api.time_warp = self.WARP_RATES[self._warp_index]
        elif index == 3:
            self._paused = not self._paused

    @staticmethod
    def _format_elapsed(seconds: float) -> str:
        seconds = int(seconds)
        d = seconds // 86400
        h = (seconds % 86400) // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"MET  {d:03d}d {h:02d}:{m:02d}:{s:02d}"
