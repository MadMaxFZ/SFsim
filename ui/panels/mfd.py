#!/usr/bin/python
# ui/panels/mfd.py

import pygame
from enum import Enum, auto
from ui.panel_base import PanelBase


class MFDMode(Enum):
    ORBIT   = auto()
    NAV     = auto()
    SYSTEMS = auto()
    ATTITUDE = auto()


class MFD(PanelBase):
    """
    Multi-Function Display panel.
    Cycle modes with OSB (On-Screen Button) style buttons along edges.
    """

    MODES = list(MFDMode)
    MODE_LABELS = {
        MFDMode.ORBIT:    "ORB",
        MFDMode.NAV:      "NAV",
        MFDMode.SYSTEMS:  "SYS",
        MFDMode.ATTITUDE: "ATT",
    }

    OSB_SIZE = 30
    OSB_MARGIN = 4

    def __init__(self, screen, rect, api, label="MFD"):
        super().__init__(screen, rect, api)
        self.label = label
        self.mode = MFDMode.ORBIT
        self._osb_rects = []

    def render(self) -> None:
        self.clear()
        self.draw_border()
        self._draw_header()
        self._draw_osbs()
        self._draw_content()
        self._draw_orbit_data()
        self._draw_nav_data()
        self._draw_systems_data()
        self._draw_attitude_data()

    def _draw_header(self) -> None:
        self.draw_label(
            f"{self.label} [{self.MODE_LABELS[self.mode]}]",
            6, 4, font=self.FONT_MONO_SM, color=self.COLOR_ACCENT
        )

    def _draw_osbs(self) -> None:
        """Draw mode-select buttons along the bottom edge."""
        self._osb_rects.clear()
        n = len(self.MODES)
        spacing = self.rect.width // n
        y = self.rect.height - self.OSB_SIZE - self.OSB_MARGIN
        for i, mode in enumerate(self.MODES):
            x = i * spacing + self.OSB_MARGIN
            r = pygame.Rect(x, y, self.OSB_SIZE + 10, self.OSB_SIZE)
            color = self.COLOR_ACCENT if mode == self.mode else self.COLOR_BORDER
            pygame.draw.rect(self.surface, color, r, 1)
            self.draw_label(
                self.MODE_LABELS[mode],
                r.x + 4, r.y + 6,
                font=self.FONT_MONO_SM, color=color
            )
            self._osb_rects.append((r, mode))

    def _draw_content(self) -> None:
        if self.mode == MFDMode.ORBIT:
            self._draw_orbit_data()
        elif self.mode == MFDMode.NAV:
            self._draw_nav_data()
        elif self.mode == MFDMode.SYSTEMS:
            self._draw_systems_data()
        elif self.mode == MFDMode.ATTITUDE:
            self._draw_attitude_data()

    def _draw_orbit_data(self) -> None:
        state = self.api.get_system_state()
        spacecraft = state.get('spacecraft', {})
        y = 30
        for name, data in spacecraft.items():
            self.draw_label(name, 6, y, color=self.COLOR_ACCENT)
            y += 18
            pos = data.get('position_m', [0, 0, 0])
            vel = data.get('velocity_ms', [0, 0, 0])
            r_km = (sum(p**2 for p in pos)**0.5) / 1000
            v_ms = (sum(v**2 for v in vel)**0.5)
            self.draw_label(f"R: {r_km:>10.1f} km", 6, y,
                            font=self.FONT_MONO_SM)
            y += 16
            self.draw_label(f"V: {v_ms:>10.1f} m/s", 6, y,
                            font=self.FONT_MONO_SM)
            y += 20

    def _draw_nav_data(self) -> None:
        self.draw_label("NAV - TBD", 6, 40,
                        font=self.FONT_MONO_SM, color=self.COLOR_TEXT_DIM)

    def _draw_systems_data(self) -> None:
        state = self.api.get_system_state()
        spacecraft = state.get('spacecraft', {})
        y = 30
        for name, data in spacecraft.items():
            self.draw_label(name, 6, y, color=self.COLOR_ACCENT)
            y += 18
            mass = data.get('mass_kg', 0)
            self.draw_label(f"MASS: {mass:.1f} kg", 6, y,
                            font=self.FONT_MONO_SM)
            y += 16

    def _draw_attitude_data(self) -> None:
        state = self.api.get_system_state()
        spacecraft = state.get('spacecraft', {})
        y = 30
        for name, data in spacecraft.items():
            self.draw_label(name, 6, y, color=self.COLOR_ACCENT)
            y += 18
            omega = data.get('angular_velocity_rads', [0, 0, 0])
            for axis, val in zip(['ωx', 'ωy', 'ωz'], omega):
                self.draw_label(f"{axis}: {val:+.4f} r/s", 6, y,
                                font=self.FONT_MONO_SM)
                y += 16
            y += 4

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            lx = event.pos[0] - self.rect.x
            ly = event.pos[1] - self.rect.y
            for r, mode in self._osb_rects:
                if r.collidepoint(lx, ly):
                    self.mode = mode
                    break
