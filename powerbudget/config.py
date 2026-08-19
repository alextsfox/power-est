"""
config.py — Configuration for powerbudget.py

Python API: edit the CONFIG instance at the bottom of this file.
CLI: run  python -m powerbudget --help  to see all options.
"""

import enum
from dataclasses import dataclass, field
from typing import Literal


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
    """All parameters for one power-budget simulation run.
    
    Parameters
    ----------
    latitude : float
        Latitude of the site in degrees North.
    longitude : float
        Longitude of the site in degrees East (negative for West).
    altitude : float, optional
        Altitude of the site in meters above sea level (default is 0.0).
    
    P_max : float
        Maximum power output of the solar panel (from solar panel data sheet).
    V_mp : float
        Voltage at maximum power of the solar panel (from solar panel data sheet).
    panel_efficiency : float, optional
        Real-world derating factor for the solar panel, accounting for wiring losses, soiling, etc. Default is 0.90.
        Typical soiling losses are 5-10% for dusty environments, and 1-2% for clean environments.
        Solar panel age is also a factor, with typical degradation rates of 0.5-1% per year.

    panel_azi : str or float, optional
        Azimuth of the panel normal, clockwise from North. 
        If "auto", the panel faces the equator (South in Northern Hemisphere, North in Southern Hemisphere).
        Default "auto".
    panel_elev : str or float, optional
        Elevation of the panel normal above horizontal.
        If "auto", the panel elevation is set to 90 - abs(latitude) for year-round optimal tilt.
        If "winter", the panel is tilted minus 15° (steeper, catches low sun).
        If "summer", the panel is tilted plus 15° (shallower).
        Default "winter".

    battery_ah : float
        Amp-hour capacity of the battery.
    V_batt : float, optional
        Nominal voltage of the battery (default is 12.0 V).
    max_dod : float, optional
        Maximum depth of discharge of the battery.
        For flooded Lead-Acid batteries, a typical value is 0.5.
        For Lead-Acid AGM batteries, a typical value is 0.5-0.8. 0.5 will prolong battery life, 0.8 will give more usable energy but shorten battery life.
        For LiFePO4 batteries, a typical value is 0.8-0.99. 0.8 will prolong battery life, 0.99 will give more usable energy but shorten battery life.
        Default is 0.8.
    charge_efficiency : float, optional
        Round-trip charging efficiency of the charge controller-battery system (excluding solar panels).
        For a typical Lead-Acid battery, a value of 0.85-0.90 is reasonable.
        For a typical LiFePO4 battery, a value of 0.95-0.98 is reasonable.
        For a PWM charge controller, an additional derating of V_batt / V_mp should be applied, which can be as low as 0.75 for a 12 V battery with a 36 V panel (averaged over the day).
        For a MPPT charge controller, no additional derating is needed.
        Default is 0.85.
        
    devices : dict | float, optional
        Dictionary mapping device names to Device instances, representing the devices in the system that may draw power.
        Refer to Device class for details on how to specify each device.
        Alternatively, a single float can be provided to represent a constant load in watts.
    scan_interval_sec : float
        Time interval between scans in seconds. Some devices are only active during scans, so this parameter is used to calculate their average power draw.
    comms_interval_sec : float, optional
        Time interval between communications in seconds. Some devices are only active during communications, so this parameter is used to calculate their average power draw.
    
        
    """

    # ── Location ──────────────────────────────────────────────────────────────
    latitude:  float           # degrees N
    longitude: float           # degrees E  (negative = West)
    altitude:  float = 0.0     # metres above sea level

    # ── Required hardware parameters ─────────────────────────────────────────
    P_max:       float           # rated Pmax at STC (1000 W/m², 25 °C)
    V_mp:        float           # voltage at max power (Vmp)
    panel_efficiency: float =  0.90      # real-world derating (wiring, soiling, …)
    panel_azi:  Literal['auto'] | float = "auto"
    panel_elev: Literal['auto', 'winter', 'summer'] | float = "winter"

    # ── Battery ───────────────────────────────────────────────────────────────
    battery_ah:        float
    V_batt:   float
    max_dod:           float =   0.85    # fraction, e.g. 0.80 = 80 %
    charge_efficiency: float =   0.90    # round-trip charge efficiency

    # ── Panel orientation ─────────────────────────────────────────────────────
    # panel_azi  : azimuth of the panel normal, clockwise from North
    #              float (degrees) | "auto"  → faces equator (S in N hemi, N in S hemi)
    # panel_elev : elevation of the panel normal above horizontal
    #              float (degrees) | "auto"   → optimal tilt for latitude
    #                               "winter"  → optimal minus 15° (steeper, catches low sun)
    #                               "summer"  → optimal plus  15° (shallower)

    # ── Devices ───────────────────────────────────────────────────────────────
    # Dict of  name → Device(watts, mode, active_seconds)
    #   DeviceMode.ALWAYS  draws watts continuously 24 h/day
    #   DeviceMode.SCAN    draws watts for active_seconds each scan cycle
    #   DeviceMode.COMMS   draws watts for active_seconds each comms cycle
    devices: dict | float = field(default_factory=dict)
    scan_interval_sec: float           # period between scans (s)
    comms_interval_sec: float          # period between comms  (s)



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

    P_max      = 45 * 2,
    V_mp       = 33.4,
    # panel_efficiency =  0.90,

    # backup_days       = 14,
    # daymet_start_year = 2005,
    # daymet_end_year   = 2025,
)

