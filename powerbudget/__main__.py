"""
__main__.py — Entry point for  python -m powerbudget

Without arguments, runs with the configuration in config.py:CONFIG.
Any flag you supply overrides only that field; everything else comes from CONFIG.

Examples
--------
# Use config.py defaults:
    python -m powerbudget

# Override location only:
    python -m powerbudget --lat 45.0 --lon -93.0

# Full custom run with explicit devices:
    python -m powerbudget \\
        --lat 45.0 --lon -93.0 --alt 300 \\
        --panel-watts 40 --panel-elev winter \\
        --battery-ah 100 --max-dod 0.75 \\
        --device "Datalogger:0.5:always" \\
        --device "Sensor:1.5:scan:15" \\
        --device "Radio:6:comms:30" \\
        --backup-days 14 --daymet-start 2010 --daymet-end 2020
"""

import argparse
import copy

from .config import BudgetConfig, Device, DeviceMode, CONFIG
from .powerbudget import main


# ─────────────────────────────────────────────────────────────────────────────
# Argument type helpers
# ─────────────────────────────────────────────────────────────────────────────

def _panel_orient(s: str) -> "str | float":
    """Accept a float degrees value or one of auto / winter / summer."""
    try:
        return float(s)
    except ValueError:
        sl = s.lower()
        if sl in ("auto", "winter", "summer"):
            return sl
        raise argparse.ArgumentTypeError(
            f"Expected a number or 'auto'/'winter'/'summer', got {s!r}"
        )


def _device(s: str) -> "tuple[str, Device]":
    """Parse  'name:watts:mode'  or  'name:watts:mode:active_seconds'."""
    parts = s.split(":")
    if len(parts) < 3:
        raise argparse.ArgumentTypeError(
            f"Device spec must be 'name:watts:mode[:active_seconds]', got {s!r}"
        )
    name = parts[0]
    try:
        watts = float(parts[1])
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Device watts must be a number, got {parts[1]!r}"
        )
    try:
        mode = DeviceMode[parts[2].upper()]
    except KeyError:
        raise argparse.ArgumentTypeError(
            f"Device mode must be always / scan / comms, got {parts[2]!r}"
        )
    active_seconds = float(parts[3]) if len(parts) > 3 else 0.0
    return name, Device(watts=watts, mode=mode, active_seconds=active_seconds)


# ─────────────────────────────────────────────────────────────────────────────
# Parser
# ─────────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="powerbudget",
        description=(
            "Solar power budget simulator. "
            "All parameters default to config.py:CONFIG; "
            "supply any flag to override that field."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    loc = p.add_argument_group("Location")
    loc.add_argument("--lat", type=float, metavar="DEG", required=True,
                     help="Latitude (degrees N)")
    loc.add_argument("--lon", type=float, metavar="DEG", required=True,
                     help="Longitude (degrees E)")
    loc.add_argument("--alt", type=float, metavar="M", default=0.0,
                     help="Altitude (metres above sea level)")

    pan = p.add_argument_group("Panel orientation")
    pan.add_argument("--panel-azi", type=_panel_orient, metavar="DEG|auto",
                     help="Azimuth of panel normal (degrees past North), or 'auto'.")
    pan.add_argument("--panel-elev", type=_panel_orient,
                     metavar="DEG|auto|winter|summer",
                     help=(
                         "Elevation of panel normal above horizontal (degrees), or "
                         "'auto' (optimal for latitude, year-round), "
                         "'winter' (auto - 15°, optimize for winter charging), "
                         "'summer' (auto + 15°, optimize for summer charging)"
                     ))

    dev = p.add_argument_group("Devices")
    dev.add_argument(
        "--device", type=_device, action="append",
        metavar="NAME:WATTS:MODE[:SECS]",
        help=(
            "Add a device. MODE is always / scan / comms. "
            "SECS = active_seconds per cycle (required for scan/comms). "
            "Repeat for multiple devices. "
            "If any --device flag is given, config.py devices are replaced entirely."
        ),
    )

    cyc = p.add_argument_group("Duty cycle")
    cyc.add_argument("--scan-interval",  type=float, metavar="SEC", required=True,
                     help="Scan cycle period (seconds)")
    cyc.add_argument("--comms-interval", type=float, metavar="SEC", default=1e10,
                     help="How often communications cycle occurs (seconds), defaults to never")

    bat = p.add_argument_group("Battery")
    bat.add_argument("--battery-ah",        type=float, metavar="AH", required=True,
                     help="Battery capacity (Ah)")
    bat.add_argument("--battery-voltage",   type=float, metavar="V",
                     help="Battery nominal voltage (V), default 12V")
    bat.add_argument("--max-dod",           type=float, metavar="FRAC",
                     help=r"Max depth of discharge, 0-1. For flooded lead-acid, recommend ~0.5. For deep cycle lead-acid ~0.75. Set to 1.0 if not using a low-voltage cutoff.")
    bat.add_argument("--charge-efficiency", type=float, metavar="FRAC", required=False, default=0.8,
                     help="Round-trip charge efficiency, 0-1, default 0.8")

    sol = p.add_argument_group("Solar panel")
    sol.add_argument("--panel-watts",      type=float, metavar="W", required=True,
                     help="Panel rated Pmax at STC (W)")
    sol.add_argument("--panel-efficiency", type=float, metavar="FRAC", default=0.9,
                     help="Real-world derating factor, 0-1, default 0.9")

    sim = p.add_argument_group("Simulation")
    sim.add_argument("--backup-days",  type=int, metavar="N", default=14,
                     help="Storm reserve simulation length (days), default 14")
    sim.add_argument("--daymet-start", type=int, metavar="YEAR", default=2010,
                     help="Daymet historical range start year, default 2010")
    sim.add_argument("--daymet-end",   type=int, metavar="YEAR", default=2025,
                     help="Daymet historical range end year, default 2025")

    return p


# ─────────────────────────────────────────────────────────────────────────────
# Build config from parsed args
# ─────────────────────────────────────────────────────────────────────────────

def _cfg_from_args(args: argparse.Namespace) -> BudgetConfig:
    """Start from CONFIG and override only the fields explicitly provided."""
    cfg = copy.copy(CONFIG)   # shallow copy — devices dict replaced if --device given

    if args.lat is not None: cfg.latitude  = args.lat
    if args.lon is not None: cfg.longitude = args.lon
    if args.alt is not None: cfg.altitude  = args.alt

    if args.panel_azi  is not None: cfg.panel_azi  = args.panel_azi
    if args.panel_elev is not None: cfg.panel_elev = args.panel_elev

    if args.device:
        cfg.devices = dict(args.device)   # list of (name, Device) tuples → dict

    if args.scan_interval  is not None: cfg.scan_interval_sec  = args.scan_interval
    if args.comms_interval is not None: cfg.comms_interval_sec = args.comms_interval

    if args.battery_ah        is not None: cfg.battery_ah        = args.battery_ah
    if args.battery_voltage   is not None: cfg.V_batt   = args.battery_voltage
    if args.max_dod           is not None: cfg.max_dod           = args.max_dod
    if args.charge_efficiency is not None: cfg.charge_efficiency = args.charge_efficiency

    if args.panel_watts      is not None: cfg.P_max      = args.panel_watts
    if args.panel_efficiency is not None: cfg.panel_efficiency = args.panel_efficiency

    if args.backup_days   is not None: cfg.backup_days       = args.backup_days
    if args.daymet_start  is not None: cfg.daymet_start_year = args.daymet_start
    if args.daymet_end    is not None: cfg.daymet_end_year   = args.daymet_end

    return cfg


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = _build_parser()
    args   = parser.parse_args()
    cfg    = _cfg_from_args(args)
    main(cfg)
