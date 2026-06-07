#!/usr/bin/python
# ui/panel_base.py

import pygame
from abc import ABC, abstractmethod


class PanelBase(ABC):
    """
    Base class for all UI panels.
    Each panel owns a sub-surface derived from the main screen.
    """

    # Color palette — ORBITAL-inspired green-on-dark scheme
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

    def __init__(self, screen: pygame.Surface, rect: pygame.Rect, api):
        self.screen = screen
        self.rect = rect
        self.api = api
        self.surface = screen.subsurface(rect)
        self._init_fonts()

    def _init_fonts(self) -> None:
        if PanelBase.FONT_MONO_SM is None:
            PanelBase.FONT_MONO_SM = pygame.font.SysFont('monospace', 12)
            PanelBase.FONT_MONO_MD = pygame.font.SysFont('monospace', 16)
            PanelBase.FONT_MONO_LG = pygame.font.SysFont('monospace', 22)

    def draw_border(self, color=None, width=1) -> None:
        color = color or self.COLOR_BORDER
        pygame.draw.rect(self.surface, color,
                         pygame.Rect(0, 0, self.rect.width, self.rect.height),
                         width,
                         )

    def draw_label(self, text: str, x: int, y: int,
                   font=None, color=None,
                   ) -> None:
        font = font or self.FONT_MONO_MD
        color = color or self.COLOR_TEXT
        surf = font.render(text, True, color)
        self.surface.blit(surf, (x, y))

    def clear(self) -> None:
        self.surface.fill(self.COLOR_BG)

    @abstractmethod
    def render(self) -> None:
        pass

    def update(self, dt: float) -> None:
        pass

    def handle_event(self, event: pygame.event.Event) -> None:
        pass
