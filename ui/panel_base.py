#!/usr/bin/python
# ui/panel_base.py

import math

import pygame

from ui.colors import Colors


class PanelBase:
    """
    Base class for all UI panels. Each panel draws into a sub-surface of the
    main screen and reads only the per-frame telemetry snapshot (`app.snap`);
    commands go through `app.ai` (ShipAI).
    """

    COLOR_BG = (8, 12, 18)
    COLOR_BORDER = (0, 140, 80)
    COLOR_TEXT = (0, 220, 120)
    COLOR_TEXT_DIM = (0, 120, 60)
    COLOR_ACCENT = (0, 255, 160)
    COLOR_WARNING = (220, 180, 0)
    COLOR_DANGER = (220, 40, 40)
    COLOR_GRID = (0, 40, 25)

    FONT_MONO_SM = None
    FONT_MONO_MD = None
    FONT_MONO_LG = None

    def __init__(self, screen: pygame.Surface, rect: pygame.Rect, app):
        self.screen = screen
        self.rect = rect
        self.app = app
        self.surface = screen.subsurface(rect)
        self._init_fonts()

    @property
    def snap(self) -> dict:
        return self.app.snap

    def _init_fonts(self) -> None:
        if PanelBase.FONT_MONO_SM is None:
            name = pygame.font.match_font('dejavusansmono,liberationmono,couriernew,monospace')
            PanelBase.FONT_MONO_SM = pygame.font.Font(name, 12)
            PanelBase.FONT_MONO_MD = pygame.font.Font(name, 15)
            PanelBase.FONT_MONO_LG = pygame.font.Font(name, 20)

    def draw_border(self, color=None, width=1) -> None:
        pygame.draw.rect(self.surface, color or self.COLOR_BORDER,
                         pygame.Rect(0, 0, self.rect.width, self.rect.height), width)

    def draw_label(self, text: str, x: int, y: int, font=None, color=None) -> None:
        surf = (font or self.FONT_MONO_MD).render(text, True, color or self.COLOR_TEXT)
        self.surface.blit(surf, (x, y))

    def draw_kv(self, key: str, value: str, y: int, color=None, x=6) -> int:
        self.draw_label(f"{key:<6}", x, y, font=self.FONT_MONO_SM, color=self.COLOR_TEXT_DIM)
        self.draw_label(value, x + 52, y, font=self.FONT_MONO_SM, color=color)
        return y + 15

    def clear(self) -> None:
        self.surface.fill(self.COLOR_BG)

    def local(self, pos):
        return pos[0] - self.rect.x, pos[1] - self.rect.y

    def contains(self, pos) -> bool:
        return self.rect.collidepoint(pos)

    def render(self) -> None:
        raise NotImplementedError

    def update(self) -> None:
        pass

    def handle_event(self, event: pygame.event.Event) -> None:
        pass


def fmt_dist(km: float) -> str:
    if km is None or not math.isfinite(km):
        return "    ---   "
    if abs(km) >= 1e7:
        return f"{km / 1.495978707e8:8.4f} AU"
    if abs(km) >= 1e5:
        return f"{km / 1e3:8.1f} Mm"
    return f"{km:8.1f} km"


def fmt_time(s: float) -> str:
    if s is None or not math.isfinite(s):
        return "---"
    s = abs(s)
    d, rem = divmod(int(s), 86400)
    h, rem = divmod(rem, 3600)
    m, sec = divmod(rem, 60)
    return f"{d}d {h:02d}:{m:02d}:{sec:02d}" if d else f"{h:02d}:{m:02d}:{sec:02d}"


def fmt_speed(kms: float) -> str:
    return f"{kms * 1000:9.1f} m/s" if abs(kms) < 100 else f"{kms:9.3f} km/s"
