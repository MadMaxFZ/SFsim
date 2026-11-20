# shipos/__init__.py
"""Ship operating system: guidance, autopilot, ShipAI sequencer and telemetry.
(Named `shipos` rather than `os` so it never shadows Python's standard library.)"""

from .ship_ai import ShipAI, ATTITUDE_MODES
from .telemetry import Telemetry

__all__ = ['ShipAI', 'ATTITUDE_MODES', 'Telemetry']
