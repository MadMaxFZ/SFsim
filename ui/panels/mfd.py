# ui/panels/mfd.py

from enum import auto, Enum

import pygame

from ui.colors import Colors


class MFDMode(Enum):
    ORBIT = auto()
    NAV = auto()
    SYSTEMS = auto()
    MAP = auto()


class MFD:
    """
    Multi-Function Display panel.

    Displays a selectable set of readout pages.
    Buttons along the bottom cycle through modes.
    """

    MODES = [MFDMode.ORBIT, MFDMode.NAV, MFDMode.SYSTEMS, MFDMode.MAP]
    MODE_LABELS = {
            MFDMode.ORBIT  : 'ORB',
            MFDMode.NAV    : 'NAV',
            MFDMode.SYSTEMS: 'SYS',
            MFDMode.MAP    : 'MAP',
            }

    BUTTON_HEIGHT = 28

    def __init__(self, rect: pygame.Rect, side: str = 'left'):
        self.rect = rect
        self.side = side
        self.surface = pygame.Surface((rect.width, rect.height))
        self._mode = MFDMode.ORBIT
        self._state_snapshot = {}
        self._selected_spacecraft = None
        self._button_rects = []

        pygame.font.init()
        self._font = pygame.font.SysFont('monospace', 12)
        self._font_title = pygame.font.SysFont('monospace', 13, bold=True)
        self._font_small = pygame.font.SysFont('monospace', 10)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, state: dict) -> None:
        self._state_snapshot = state
        if self._selected_spacecraft is None:
            names = list(state.get('spacecraft', {}).keys())
            if names:
                self._selected_spacecraft = names[0]

    def draw(self) -> pygame.Surface:
        self.surface.fill(Colors.PANEL_BG)
        self._draw_border()
        self._draw_title()
        self._draw_content()
        self._draw_mode_buttons()
        return self.surface

    def handle_event(self, event: pygame.event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            lx = event.pos[0] - self.rect.x
            ly = event.pos[1] - self.rect.y
            for i, r in enumerate(self._button_rects):
                if r.collidepoint(lx, ly):
                    self._mode = self.MODES[i % len(self.MODES)]

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _draw_border(self) -> None:
        pygame.draw.rect(self.surface, Colors.PANEL_BORDER,
                         self.surface.get_rect(), 2,
                         )

    def _draw_title(self) -> None:
        label = f"[ {self.side.upper()} MFD — {self.MODE_LABELS[self._mode]} ]"
        surf = self._font_title.render(label, True, Colors.CYAN)
        self.surface.blit(surf, (8, 6))
        pygame.draw.line(self.surface, Colors.PANEL_BORDER,
                         (4, 22), (self.rect.width - 4, 22), 1,
                         )

    def _draw_content(self) -> None:
        content_rect = pygame.Rect(
                4, 26,
                self.rect.width - 8,
                self.rect.height - 26 - self.BUTTON_HEIGHT - 4,
                )
        if self._mode == MFDMode.ORBIT:
            self._draw_orbit_page(content_rect)
        elif self._mode == MFDMode.NAV:
            self._draw_nav_page(content_rect)
        elif self._mode == MFDMode.SYSTEMS:
            self._draw_systems_page(content_rect)
        elif self._mode == MFDMode.MAP:
            self._draw_map_page(content_rect)

    def _draw_orbit_page(self, rect: pygame.Rect) -> None:
        sc_data = self._state_snapshot.get('spacecraft', {})
        if not sc_data or self._selected_spacecraft not in sc_data:
            self._print_lines(rect, ['No spacecraft'], Colors.DIM_WHITE)
            return
        sc = sc_data[self._selected_spacecraft]
        pos = sc['position_m']
        vel = sc['velocity_ms']
        r_km = (sum(x ** 2 for x in pos) ** 0.5) / 1000
        v_ms = (sum(x ** 2 for x in vel) ** 0.5)
        lines = [
                f"SC: {self._selected_spacecraft}",
                "",
                f"ALT  {r_km - 6371:.1f} km",
                f"RAD  {r_km:.1f} km",
                f"SPD  {v_ms:.1f} m/s",
                "",
                f"PX   {pos[0] / 1000:.1f} km",
                f"PY   {pos[1] / 1000:.1f} km",
                f"PZ   {pos[2] / 1000:.1f} km",
                "",
                f"VX   {vel[0]:.2f} m/s",
                f"VY   {vel[1]:.2f} m/s",
                f"VZ   {vel[2]:.2f} m/s",
                "",
                f"MASS {sc['mass_kg']:.1f} kg",
                ]
        self._print_lines(rect, lines, Colors.GREEN)

    def _draw_nav_page(self, rect: pygame.Rect) -> None:
        sc_data = self._state_snapshot.get('spacecraft', {})
        if not sc_data or self._selected_spacecraft not in sc_data:
            self._print_lines(rect, ['No spacecraft'], Colors.DIM_WHITE)
            return
        sc = sc_data[self._selected_spacecraft]
        av = sc['angular_velocity_rads']
        q = sc['quaternion']
        lines = [
                "ATTITUDE",
                "",
                f"QW   {q[0]:.4f}",
                f"QX   {q[1]:.4f}",
                f"QY   {q[2]:.4f}",
                f"QZ   {q[3]:.4f}",
                "",
                "ANG VEL (rad/s)",
                f"WX   {av[0]:.4f}",
                f"WY   {av[1]:.4f}",
                f"WZ   {av[2]:.4f}",
                ]
        self._print_lines(rect, lines, Colors.AMBER)

    def _draw_systems_page(self, rect: pygame.Rect) -> None:
        lines = [
                "SYSTEMS",
                "",
                "PWR   [NOMINAL]",
                "PROP  [NOMINAL]",
                "ADCS  [NOMINAL]",
                "COMM  [NOMINAL]",
                "",
                "(placeholder)",
                ]
        self._print_lines(rect, lines, Colors.BRIGHT_GREEN)

    def _draw_map_page(self, rect: pygame.Rect) -> None:
        bodies = self._state_snapshot.get('bodies', {})
        lines = ["BODIES"] + [""] + [
                f"{n:<10} {self._r_au(d['position_m']):.3f} AU"
                for n, d in bodies.items()
                ]
        self._print_lines(rect, lines, Colors.CYAN)

    def _draw_mode_buttons(self) -> None:
        self._button_rects = []
        n = len(self.MODES)
        bw = (self.rect.width - 8) // n
        by = self.rect.height - self.BUTTON_HEIGHT - 2
        for i, mode in enumerate(self.MODES):
            r = pygame.Rect(4 + i * bw, by, bw - 2, self.BUTTON_HEIGHT)
            self._button_rects.append(r)
            active = (mode == self._mode)
            bg = Colors.DIM_GREEN if active else Colors.DARK_GREY
            pygame.draw.rect(self.surface, bg, r)
            pygame.draw.rect(self.surface, Colors.PANEL_BORDER, r, 1)
            lbl = self._font.render(self.MODE_LABELS[mode], True,
                                    Colors.BRIGHT_GREEN if active else Colors.GREY,
                                    )
            self.surface.blit(lbl, (r.x + 4, r.y + 7))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _print_lines(self, rect: pygame.Rect,
                     lines: list, color,
                     ) -> None:
        line_h = 15
        for i, line in enumerate(lines):
            y = rect.y + i * line_h
            if y + line_h > rect.y + rect.height:
                break
            surf = self._font.render(line, True, color)
            self.surface.blit(surf, (rect.x, y))

    @staticmethod
    def _r_au(pos_m: list) -> float:
        AU = 1.496e11
        return (sum(x ** 2 for x in pos_m) ** 0.5) / AU
