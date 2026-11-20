#!/usr/bin/python
# ui/panels/telemetry_panel.py

from ui.panel_base import PanelBase, fmt_dist, fmt_speed


class TelemetryPanel(PanelBase):
    """Horizontal strip: state vector relative to the primary, engine, and key help."""

    HELP = [
        "1 KILLROT 2 PRO 3 RETRO 4 NML 5 ANML 6 RAD+ 7 RAD- 8 TGT 9 TGT-RETRO 0 AP OFF",
        "W/S pitch  A/D yaw  Q/E roll   Shift/Ctrl throttle +/-   Z full  X cut",
        "TAB tgt  , . warp  B +10m/s  J eject  P circ@Pe  O circ@Ap  T tcm  K abort",
        "F map focus  C follow ship  PgUp/PgDn/wheel zoom  M/N cycle MFD pages",
    ]

    def render(self) -> None:
        self.clear()
        self.draw_border()
        snap = self.snap
        s = snap['ship']
        st = self.app.api.solar_system.states(snap['t'])[s['dominant']]
        r = s['r'] - st[0]
        v = s['v'] - st[1]
        x = 10
        self.draw_label(f"{s['name']}  rel {s['dominant']}", x, 6, color=self.COLOR_ACCENT)
        for i, (lbl, vec) in enumerate((("R", r), ("V", v))):
            unit = "km" if lbl == "R" else "km/s"
            txt = f"{lbl} [{vec[0]:+14.3f} {vec[1]:+14.3f} {vec[2]:+14.3f}] {unit}"
            self.draw_label(txt, x, 26 + i * 16, font=self.FONT_MONO_SM)
        fps = self.app.clock.get_fps()
        self.draw_label(f"FPS {fps:5.1f}   physics {snap['frame_cpu_ms']:5.1f} ms/frame", x, 62, font=self.FONT_MONO_SM,
                        color=self.COLOR_TEXT_DIM)
        hx = self.rect.width - 600
        for i, line in enumerate(self.HELP):
            self.draw_label(line, hx, 8 + i * 15, font=self.FONT_MONO_SM, color=self.COLOR_TEXT_DIM)
