#!/usr/bin/python
# ui/panels/hud.py

import pygame
import numpy as np
from ui.panel_base import PanelBase


class HUD(PanelBase):
    """
    HUD overlay on the main map view.
    Draws: mission clock, time warp indicator, selected spacecraft name.
    Artificial horizon / attitude ball is a future addition.
    """

    def __init__(self, screen, rect, api):
        super().__init__(screen, rect, api)
        # HUD uses a transparent surface
        self.surface = pygame.Surface(
            (rect.width, rect.height), pygame.SRCALPHA
        )

    def render(self) -> None:
        self.surface.fill((0, 0, 0, 0))  # fully transparent
        self._draw_mission_clock()
        self._draw_time_warp()
        self.screen.blit(self.surface, (self.rect.x, self.rect.y))

    def _draw_mission_clock(self) -> None:
        state = self.api.get_system_state()
        epoch = state.get('epoch', 'Unknown')
        text = f"EPOCH: {epoch}"
        surf = self.FONT_MONO_SM.render(text, True, self.COLOR_TEXT)
        self.surface.blit(surf, (10, 10))

    def _draw_time_warp(self) -> None:
        state = self.api.get_system_state()
        warp = state.get('time_warp', 1)
        text = f"WARP: x{warp}"
        color = self.COLOR_WARNING if warp > 1 else self.COLOR_TEXT_DIM
        surf = self.FONT_MONO_SM.render(text, True, color)
        self.surface.blit(surf, (10, 26))
