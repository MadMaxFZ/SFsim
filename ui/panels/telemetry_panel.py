#!/usr/bin/python
# ui/panels/telemetry_panel.py

import pygame
from ui.panel_base import PanelBase


class TelemetryPanel(PanelBase):
    """
    Horizontal strip showing key telemetry values for all spacecraft.
    """

    def render(self) -> None:
        self.clear()
        self.draw_border()
        state = self.api.get_system_state()
        spacecraft = state.get('spacecraft', {})
        x = 10
        for name, data in spacecraft.items():
            self._draw_spacecraft_strip(name, data, x)
            x += 300

    def _draw_spacecraft_strip(self, name: str, data: dict, x: int) -> None:
        y = 8
        self.draw_label(name, x, y, color=self.COLOR_ACCENT)
        y += 20
        pos = data.get('position_m', [0, 0, 0])
        vel = data.get('velocity_ms', [0, 0, 0])
        r_km = (sum(p**2 for p in pos)**0.5) / 1000
        v_ms = (sum(v**2 for v in vel)**0.5)
        omega = data.get('angular_velocity_rads', [0, 0, 0])
        omega_mag = (sum(w**2 for w in omega)**0.5)
        fields = [
            f"POS: {r_km:>12.1f} km",
            f"VEL: {v_ms:>10.2f} m/s",
            f"|ω|: {omega_mag:>10.5f} r/s",
        ]
        for field in fields:
            self.draw_label(field, x, y, font=self.FONT_MONO_SM)
            y += 16
