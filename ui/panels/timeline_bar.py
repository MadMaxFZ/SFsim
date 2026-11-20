#!/usr/bin/python
# ui/panels/timeline_bar.py

import pygame

from ui.panel_base import PanelBase, fmt_time


class TimelineBar(PanelBase):
    """
    Bottom bar: time-warp buttons (also ',' and '.') and the mission clock.
    Warp requests go through App.set_warp so ShipOS rules can apply.
    """

    WARP_RATES = [1, 10, 100, 1000, 10000, 100000, 1000000]

    def __init__(self, screen, rect, app):
        super().__init__(screen, rect, app)
        self._buttons = []

    def render(self) -> None:
        self.clear()
        self.draw_border()
        snap = self.snap
        self._buttons.clear()
        x, y = 20, self.rect.height // 2 - 15
        for rate in self.WARP_RATES:
            r = pygame.Rect(x, y, 70, 30)
            active = rate == snap['warp_req']
            col = self.COLOR_ACCENT if active else self.COLOR_BORDER
            pygame.draw.rect(self.surface, col, r, 2 if active else 1)
            self.draw_label(f"x{rate:g}", x + 8, y + 7, font=self.FONT_MONO_SM, color=col)
            self._buttons.append((r, rate))
            x += 78
        col = self.COLOR_WARNING if snap['warp_limited'] else self.COLOR_ACCENT
        self.draw_label(f"WARP x{snap['warp_req']:g} / achieved x{snap['warp']:.0f}", x + 16, y + 6,
                        font=self.FONT_MONO_MD, color=col)
        self.draw_label(f"EPOCH {snap['epoch']}", self.rect.width - 300, y - 2, font=self.FONT_MONO_MD)
        self.draw_label(f"MET   {fmt_time(snap['t'])}", self.rect.width - 300, y + 18, font=self.FONT_MONO_MD,
                        color=self.COLOR_TEXT_DIM)

    def step(self, direction: int):
        rates = self.WARP_RATES
        cur = self.snap['warp_req'] if self.snap else 1
        i = min(range(len(rates)), key=lambda k: abs(rates[k] - cur))
        self.app.set_warp(rates[max(0, min(len(rates) - 1, i + direction))])

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.contains(event.pos):
            lx, ly = self.local(event.pos)
            for r, rate in self._buttons:
                if r.collidepoint(lx, ly):
                    self.app.set_warp(rate)
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_PERIOD:
                self.step(+1)
            elif event.key == pygame.K_COMMA:
                self.step(-1)
