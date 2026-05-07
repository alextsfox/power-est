from powerbudget.config import BudgetConfig, Device, DeviceMode
from powerbudget.powerbudget import main

cfg = BudgetConfig(
    # # WRTBI
    # latitude  =  43.197729,
    # longitude = -108.812627,
    # altitude  =  1670,
    # panel_azi  = "auto",
    # panel_elev = "winter",
    # devices = {
    #     "CR1000X":    Device(watts=12 * 55e-3,     mode=DeviceMode.ALWAYS),
    #     "VOLT116":    Device(watts=12 *  1e-3,     mode=DeviceMode.ALWAYS),
    #     "Hydraprobe": Device(watts=12 * 10e-3 * 9, mode=DeviceMode.SCAN, active_seconds=15),
    #     "IRGASON":    Device(watts=12,             mode=DeviceMode.ALWAYS),
    # },

    # scan_interval_sec  = 300,
    # comms_interval_sec = 3600,

    # battery_ah        = 150,
    # battery_voltage   =  12.0,
    # max_dod           =   0.75,
    # charge_efficiency =   0.90,

    # panel_watts      = 90,
    # panel_efficiency =  0.90,

    # backup_days       = 14,
    # daymet_start_year = 2005,
    # daymet_end_year   = 2025,

    # CP
    latitude = 41.066859,
    longitude = -106.119340,
    altitude = 2743.2,
    panel_azi  = 180.0,
    panel_elev = 0,
    devices = {
        "CR1000X":    Device(watts=12 * 55e-3,     mode=DeviceMode.ALWAYS),
        "VOLT116":    Device(watts=12 *  1e-3,     mode=DeviceMode.ALWAYS),
        "Hydraprobe": Device(watts=12 * 10e-3 * 9, mode=DeviceMode.SCAN, active_seconds=15),
        "LI-7200":    Device(watts=12,             mode=DeviceMode.ALWAYS),
        "CSAT3":    Device(watts=2,             mode=DeviceMode.ALWAYS),
    },

    scan_interval_sec  = 300,
    comms_interval_sec = 3600,

    battery_ah        = 300,
    battery_voltage   =  12.0,
    max_dod           =   0.75,
    charge_efficiency =   0.90,

    panel_watts      = 360,
    panel_efficiency =  0.90,

    backup_days       = 14,
    daymet_start_year = 2005,
    daymet_end_year   = 2025,
)

main(cfg)
