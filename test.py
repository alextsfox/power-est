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
    panel_elev = 20.0,
    devices = {
        "CR1000X":    Device(watts=12 * 55e-3,     mode=DeviceMode.ALWAYS),
        "VOLT116":    Device(watts=12 *  1e-3,     mode=DeviceMode.ALWAYS),
        "Hydraprobe": Device(watts=12 * 10e-3 * 9, mode=DeviceMode.SCAN, active_seconds=15),
        "LI-7200":    Device(watts=12,             mode=DeviceMode.ALWAYS),
        "Flow-Module":Device(watts=16,             mode=DeviceMode.ALWAYS),
        "LI-7500":    Device(watts=10,             mode=DeviceMode.ALWAYS),
        "CSAT3":    Device(watts=2,             mode=DeviceMode.ALWAYS),
    },

    scan_interval_sec  = 300,
    comms_interval_sec = 3600,

    battery_ah        = 125*3,
    battery_voltage   =  12.0,
    max_dod           =   0.8,

    # # CURRENT CP SYSTEM
    # # for a lead-acid AGM battery, round-trip charging losses are significant, especially for old batteries
    # # older AGM: 0.75, new AGM: 0.85, LiFePO4: 0.92-0.98, Lithium NMC 0.9-0.95
    # # round trip loss from charge controller itself: 
    # # PWM (most sunsavers, like Sunsaver 20L): doesn't convert voltage, just directly connect panel ot battery near battery voltage, wasting th difference.
    # # if V_mp is well above nominal battery voltage, the PWM will waste a lot of energy. 
    # # MPPT: can convert excess voltage into current, usually 93-98% efficient.
    # # Total derating for using a 34V panel on a 12V battery is about 0.59 * 0.75 = 0.44
    # charge_efficiency =   0.44,
    # # 100 ft (x2 for round trip) of 14AWG @ 24V, ~2.5ohm/1000ft=>0.5ohm, at 10.5A*2 I_mp
    # # gives V_drop = ~5V and ~50W of resistive power loss per panel, so about 14% loss
    # # soiling, dust, connection issues give ~25% loss
    # # 10% panel derating for age
    # # total derating 0.86*0.9*0.75 = 0.69
    # panel_efficiency =  0.58,  

    # # IMPROVED CP SYSTEM
    # for a lead-acid AGM battery, round-trip charging losses are significant, especially for old batteries
    # newer AGM: 0.8
    # round trip loss from charge controller itself: 
    # MPPT: 0.94 efficiency
    # Total derating = 0.75
    charge_efficiency =   0.75,
    # 100 ft (x2 for round trip) of 14AWG @ 66V, ~2.5ohm/1000ft=>0.5ohm, at 10.5A I_mp
    # gives V_drop = ~5V and ~50W of resistive power loss total = 0.93
    # soiling, dust, connection issues: 0.85
    # 10% panel derating for age: 0.9
    # total derating 
    panel_efficiency =  0.71,  

    panel_watts      = 270*2,
    panel_v_mp       = 33.4,
    backup_days       = 14,
    daymet_start_year = 2005,
    daymet_end_year   = 2025,
)

main(cfg)
