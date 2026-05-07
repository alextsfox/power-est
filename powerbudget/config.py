"""
config.py — Configuration for powerbudget.py

Python API: edit the CONFIG instance at the bottom of this file.
CLI: run  python -m powerbudget --help  to see all options.
"""

import enum
from dataclasses import dataclass, field


class DeviceMode(enum.Enum):
    ALWAYS = enum.auto()
    SCAN   = enum.auto()
    COMMS  = enum.auto()


@dataclass(frozen=True, slots=True)
class Device:
    watts:          float
    mode:           DeviceMode
    active_seconds: float = 0.0


@dataclass
class BudgetConfig:
    """All parameters for one power-budget simulation run."""

    # ── Location ──────────────────────────────────────────────────────────────
    latitude:  float           # degrees N
    longitude: float           # degrees E  (negative = West)

    # ── Required hardware parameters ─────────────────────────────────────────
    battery_ah:        float           # amp-hour capacity
    panel_watts:       float           # rated Pmax at STC (1000 W/m², 25 °C)
    scan_interval_sec: float           # period between scans (s)

    altitude:  float = 0.0     # metres above sea level

    # ── Panel orientation ─────────────────────────────────────────────────────
    # panel_azi  : azimuth of the panel normal, clockwise from North
    #              float (degrees) | "auto"  → faces equator (S in N hemi, N in S hemi)
    # panel_elev : elevation of the panel normal above horizontal
    #              float (degrees) | "auto"   → optimal tilt for latitude
    #                               "winter"  → optimal minus 15° (steeper, catches low sun)
    #                               "summer"  → optimal plus  15° (shallower)
    panel_azi:  "str | float" = "auto"
    panel_elev: "str | float" = "winter"

    # ── Devices ───────────────────────────────────────────────────────────────
    # Dict of  name → Device(watts, mode, active_seconds)
    #   DeviceMode.ALWAYS  draws watts continuously 24 h/day
    #   DeviceMode.SCAN    draws watts for active_seconds each scan cycle
    #   DeviceMode.COMMS   draws watts for active_seconds each comms cycle
    devices: dict = field(default_factory=dict)

    # ── Duty cycle ────────────────────────────────────────────────────────────
    comms_interval_sec: float = 3600.0   # period between comms  (s)

    # ── Battery ───────────────────────────────────────────────────────────────
    battery_voltage:   float =  12.0     # nominal volts
    # max_dod: maximum depth of discharge
    #   Flooded lead-acid:          ~0.50  (12.1 V cutoff)
    #   Sealed deep-cycle / AGM LA: ~0.60–0.80
    #   LiFePO4:                    ~0.80–0.90
    max_dod:           float =   0.80    # fraction, e.g. 0.80 = 80 %
    charge_efficiency: float =   0.90    # round-trip charge efficiency

    # ── Solar panel ───────────────────────────────────────────────────────────
    panel_efficiency: float =  0.90      # real-world derating (wiring, soiling, …)

    # ── Simulation ────────────────────────────────────────────────────────────
    backup_days:       int  = 14         # storm reserve simulation length (days)
    daymet_start_year: int  = 2010       # Daymet historical range start
    daymet_end_year:   int  = 2020       # Daymet historical range end


# ─────────────────────────────────────────────────────────────────────────────
# DEFAULT CONFIGURATION — edit this block to customise without using the CLI
# ─────────────────────────────────────────────────────────────────────────────

CONFIG = BudgetConfig(
    latitude  =  43.197729,
    longitude = -108.812627,
    # altitude  =  1670,

    # panel_azi  = "auto",
    # panel_elev = "winter",

    devices = {
        "CR1000X":    Device(watts=12 * 55e-3,     mode=DeviceMode.ALWAYS),
        "VOLT116":    Device(watts=12 *  1e-3,     mode=DeviceMode.ALWAYS),
        "Hydraprobe": Device(watts=12 * 10e-3 * 9, mode=DeviceMode.SCAN, active_seconds=15),
        "IRGASON":    Device(watts=5,             mode=DeviceMode.ALWAYS),
    },

    scan_interval_sec  = 300,
    # comms_interval_sec = 3600,

    battery_ah        = 150,
    # battery_voltage   =  12.0,
    # max_dod           =   0.75,
    # charge_efficiency =   0.90,

    panel_watts      = 45 * 2,
    # panel_efficiency =  0.90,

    # backup_days       = 14,
    # daymet_start_year = 2005,
    # daymet_end_year   = 2025,
)

