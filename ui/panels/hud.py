#!/usr/bin/python
# ui/panels/hud.py

import pygame

from ui.colors import Colors
from ui.panel_base import PanelBase, fmt_dist, fmt_speed


class HUD(PanelBase):
    """
    Transparent overlay on the main view: epoch, warp (requested/achieved),
    primary + altitude + speed, autopilot mode/program, throttle, and alarms.
    """

    def __init__(self, screen, rect, app):
        super().__init__(screen, rect, app)
        self.surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)

    def render(self) -> None:
        snap = self.snap
        self.surface.fill((0, 0, 0, 0))
        s = snap['ship']
        o = s['orbit']
        lines = [
            (f"EPOCH {snap['epoch']} TDB", self.COLOR_TEXT),
            (f"WARP  x{snap['warp_req']:g}  (achieved x{snap['warp']:.0f})",
             self.COLOR_WARNING if snap['warp_limited'] else self.COLOR_TEXT_DIM),
            (f"{o['body'].upper():<8} ALT {fmt_dist(o['alt_km'])}  SPD {fmt_speed(o['speed_kms'])}",
             self.COLOR_ACCENT),
            (f"AP {snap['ai']['mode']:<10} {snap['ai']['program'] or ''}", Colors.AMBER),
        ]
        y = 8
        for text, col in lines:
            self.surface.blit(self.FONT_MONO_MD.render(text, True, col), (10, y))
            y += 18
        # throttle bar (right edge)
        h = 160
        x, y0 = self.rect.width - 30, 40
        pygame.draw.rect(self.surface, self.COLOR_BORDER, (x, y0, 14, h), 1)
        fill = int(h * s['throttle'])
        pygame.draw.rect(self.surface, Colors.BRIGHT_AMBER, (x + 1, y0 + h - fill, 12, fill))
        self.surface.blit(self.FONT_MONO_SM.render("THR", True, self.COLOR_TEXT_DIM), (x - 4, y0 + h + 4))
        # alarms (top centre)
        ax = self.rect.width // 2
        for i, al in enumerate(snap['alarms']):
            surf = self.FONT_MONO_LG.render(al, True, Colors.BRIGHT_RED)
            self.surface.blit(surf, (ax - surf.get_width() // 2, 8 + i * 24))
        self.screen.blit(self.surface, (self.rect.x, self.rect.y))
