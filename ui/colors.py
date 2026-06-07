#!/usr/bin/python
# ui/colors.py

class Colors:
    """ORBITAL-style color palette. Dark cockpit theme."""
    BLACK        = (0,   0,   0)
    BACKGROUND   = (5,   8,   12)
    PANEL_BG     = (10,  15,  20)
    PANEL_BORDER = (0,   60,  80)
    DIM_GREEN    = (0,   80,  40)
    GREEN        = (0,   200, 80)
    BRIGHT_GREEN = (120, 255, 160)
    AMBER        = (255, 176, 0)
    BRIGHT_AMBER = (255, 220, 80)
    RED          = (220, 40,  40)
    BRIGHT_RED   = (255, 80,  80)
    CYAN         = (0,   200, 220)
    BRIGHT_CYAN  = (120, 240, 255)
    WHITE        = (255, 255, 255)
    DIM_WHITE    = (160, 160, 160)
    GREY         = (60,  60,  60)
    DARK_GREY    = (25,  25,  25)
    ORBIT_LINE   = (0,   100, 140)
    ORBIT_ACTIVE = (0,   200, 255)
    SUN_COLOR    = (255, 220, 80)
    GRID_LINE    = (15,  30,  35)

    # Body colors
    BODY_COLORS = {
        'Mercury': (180, 140, 100),
        'Venus':   (220, 180, 80),
        'Earth':   (60,  140, 220),
        'Moon':    (180, 180, 180),
        'Mars':    (200, 80,  40),
        'Jupiter': (200, 160, 100),
        'Saturn':  (220, 200, 140),
        'Uranus':  (140, 200, 220),
        'Neptune': (80,  100, 220),
    }

    SPACECRAFT_COLOR = (0, 255, 160)
