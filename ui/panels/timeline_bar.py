#!/usr/bin/python
# ui/panels/timeline_bar.py

import pygame
from ui.panel_base import PanelBase
from astropy.time import Time


class TimelineBar(PanelBase):
    """
    Bottom timeline bar with time warp controls and mission elapsed time.
    """

    WARP_RATES = [1, 10, 100, 1000, 10000]

    def __init__(self, screen, rect, api):
        super().__init__(screen, rect, api)
        self._warp_index = 0
        self._button_rects = []
        self._sim_time = 0.0
        self.api = api

    def update(self, sim_time: Time) -> None:
        self._sim_time = sim_time

    def render(self) -> None:
        self.clear()
        self.draw_border()
        self._draw_warp_controls()
        self._draw_epoch()

    def _draw_warp_controls(self) -> None:
        self._button_rects.clear()
        labels = ["◀◀", "◀", "▶", "▶▶", "▶▶▶"]
        warp_vals = [1, 1, 1, 10, 100]  # placeholder mapping
        x = 20
        y = self.rect.height // 2 - 15
        for i, label in enumerate(labels):
            r = pygame.Rect(x, y, 44, 30)
            pygame.draw.rect(self.surface, self.COLOR_BORDER, r, 1)
            self.draw_label(label, x + 6, y + 6,
                            font=self.FONT_MONO_SM, color=self.COLOR_TEXT)
            self._button_rects.append(r)
            x += 54

        # Current warp rate display
        self.api.time_warp = self.WARP_RATES[self._warp_index]
        self.draw_label(f"TIME WARP: x{self.api.time_warp}", x + 10,
                        self.rect.height // 2 - 8,
                        font=self.FONT_MONO_MD, color=self.COLOR_ACCENT)

    def _draw_epoch(self) -> None:
        state = self.api.get_system_state()
        epoch = state.get('epoch', '---')
        self.draw_label(f"EPOCH: {epoch}",
                        self.rect.width - 420,
                        self.rect.height // 2 - 8,
                        font=self.FONT_MONO_MD,
                        color=self.COLOR_TEXT)

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            lx = event.pos[0] - self.rect.x
            ly = event.pos[1] - self.rect.y
            for i, r in enumerate(self._button_rects):
                if r.collidepoint(lx, ly):
                    if i <= 1:
                        self._warp_index = max(0, self._warp_index - 1)
                    else:
                        self._warp_index = min(
                            len(self.WARP_RATES) - 1,
                            self._warp_index + 1
                        )
