#!/usr/bin/env python3
"""
powerbudget.py — Solar Power Budget Simulator

Simulates annual solar power input, device load, and battery state of charge
for a given location using Daymet climate data, plus a storm-reserve simulation.

Usage: edit config.py, then run:
    python powerbudget.py
"""
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import daymetpy
import solarpy

from .config import BudgetConfig, Device, DeviceMode, CONFIG

# ─────────────────────────────────────────────────────────────────────────────
# CORE FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def compute_daily_load(devices: dict[str, Device], scan_interval_sec: float, comms_interval_sec: float) -> tuple[float, dict[str, float]]:
    """
    Return (total_wh_per_day, breakdown_dict).

    The breakdown dict maps device name -> Wh/day consumed.
    """
    scans_per_day = 86400.0 / scan_interval_sec
    comms_per_day = 86400.0 / comms_interval_sec

    breakdown = {}
    for name, dev in devices.items():
        match dev.mode:
            case DeviceMode.ALWAYS:
                wh = dev.watts * 24.0
            case DeviceMode.SCAN:
                wh = dev.watts * dev.active_seconds / 3600.0 * scans_per_day
            case DeviceMode.COMMS:
                wh = dev.watts * dev.active_seconds / 3600.0 * comms_per_day
            case _:
                raise ValueError(f"Unhandled DeviceMode '{dev.mode}' for device '{name}'.")
        breakdown[name] = wh

    total_wh = sum(breakdown.values())
    return total_wh, breakdown

def fetch_daymet(lat, lon, start_year, end_year):
    """
    Pull Daymet daily data and return day-of-year aggregates:
        mean_srad   (W/m2)  — Mean Insolation Scenario radiation
        low_srad    (W/m2)  — 25th-percentile solar radiation (cloudy years)
        lowest_srad (W/m2)  — minimum solar radiation (worst day)
        min_temp_C  (degC)    — mean daily minimum temperature
        sunlight_sec (s)    — mean daylight duration
    All indexed 1-365 (day of year).
    """
    print(f"  Fetching Daymet data for ({lat}, {lon}), "
          f"{start_year}-{end_year} …  (this may take a moment)")
    dat = daymetpy.daymet_timeseries(
        lon=lon, lat=lat,
        start_year=start_year, end_year=end_year,
    )

    idx, yday = dat.index, dat["yday"]

    # downsample to 7d, which is the approximate length of time we usually care about for storm-reserve simulations.
    # it would be unrealistic to simulate a storm that had record-low insolation for every single day of a 14-day storm.
    # more likely is that 7-day insolation will be at a record low, which is more insolation than record low insolation for 14 days straight.
    dat = dat.resample("7d").mean().reindex(idx).interpolate(method="pchip")
    dat["yday"] = yday

    mean_srad    = dat.groupby("yday")["srad"].mean()
    lowest_srad  = dat.groupby("yday")["srad"].min()

    low_srad     = dat.groupby("yday")["srad"].quantile(0.25)

    min_temp_C   = dat.groupby("yday")["tmin"].mean()
    min_temp_C = (dat.groupby("yday")["tmin"].mean() + dat.groupby("yday")["tmax"].mean()) / 2
    sunlight_sec = dat.groupby("yday")["dayl"].mean()
    return mean_srad, low_srad, lowest_srad, min_temp_C, sunlight_sec

def auto_orient_panel(cfg: BudgetConfig) -> tuple[float, float]:
    if cfg.panel_azi in ("auto", "winter", "summer"):
        azimuth = 180.0 * (-1.0 if cfg.latitude < 0 else 1.0)
    else:
        azimuth = float(cfg.panel_azi)

    if isinstance(cfg.panel_elev, (int, float)):
        elev = float(cfg.panel_elev)
    else:
        lat = abs(cfg.latitude)
        if lat <= 25:
            elev = 90.0 - 0.87 * lat
        elif lat <= 50:
            elev = 90.0 - (0.76 * lat + 3.1)
        else:
            elev = 90.0 - lat
        if cfg.panel_elev == "winter":
            elev -= 15.0
        elif cfg.panel_elev == "summer":
            elev += 15.0
    elev = max(0.0, min(90.0, elev))
    return azimuth, elev

def panel_orientation_factor(cfg: BudgetConfig) -> pd.Series:
    """Since daymet gives insolation on a horizontal surface, compute a factor to adjust insolation onto the panel based on its orientation."""
    azimuth, elev = auto_orient_panel(cfg)

    a = np.radians(azimuth)
    d = np.radians(elev)
    vnorm = np.array([
        np.cos(d) * np.cos(a),   # N
        np.cos(d) * np.sin(a),   # E
       -np.sin(d),               # D (negative = up)
    ])

    panel = solarpy.solar_panel(1.0, 1.0)
    panel.set_position(cfg.latitude, cfg.longitude, cfg.altitude)
    factors = np.zeros(365)
    for doy in range(365):
        flat_power = 0
        tilted_power = 0
        for hour in range(24):
            panel.set_datetime(datetime(2020, 1, 1) + timedelta(days=doy-1, hours=hour))

            panel.set_orientation(np.array([0, 0, -1]))  # pointing upwards
            flat_power += panel.power()

            panel.set_orientation(vnorm)  # pointing in the desired orientation
            tilted_power += panel.power()
        factors[doy] = tilted_power / flat_power
    return pd.Series(factors, index=range(1, 366))

def panel_daily_wh(p_nom: float, v_mp: float, panel_efficiency: float, srad: pd.Series, dayl: pd.Series, temp: pd.Series, cfg: BudgetConfig) -> pd.Series:
    """
    Estimate daily energy output (Wh) from the panel for each day of year.

    Derivation:
        insolation (Wh/m2) = srad [W/m2] x dayl [s] / 3600
        panel output       = panel_watts x (srad / 1000) x (dayl / 3600) x efficiency
    """
    orientation_factor = panel_orientation_factor(cfg)
    srad = srad * orientation_factor

    # 0.4% loss per degree C above 25C
    temp_derating = ((temp - 25.0) * 0.004).clip(lower=0)

    # Panel watts is given by the diode equation
    n = 1.15  # diode ideality factor
    Vt = 1.381e-23 * (temp + 273.15) / 1.602e-19  # thermal voltage = kT/q
    return (
        p_nom  # W kW_solar-1 m2
        * (panel_efficiency - temp_derating)  # -
        * (srad / 1000.0)  # current derating
        * (1 + n*Vt/v_mp * np.log(srad/1000.0))  # voltage derating
        * (dayl / 3600.0)  # h sunlight day-1
    )  # Wh day-1


def simulate_year(solar_wh_by_doy: pd.Series, daily_load_wh: float, daily_temp: pd.Series,
                  battery_wh: float, max_dod: float, charge_efficiency: float,
                  initial_charge_state: float = 1.0) -> tuple[pd.Series, pd.Series]:
    """
    Simulate battery state of charge over 365 days.

    Parameters
    ----------
    solar_wh_by_doy : pd.Series indexed by day-of-year (1-365)
    daily_load_wh   : constant daily load in Wh
    daily_temp      : pd.Series of daily mean temperatures (degC), indexed by day-of-year
    battery_wh      : total battery capacity in Wh
    max_dod         : maximum depth of discharge (fraction)
    charge_efficiency: charge efficiency (fraction)
    initial_charge_state : starting SOC (fraction, default 1.0 = full)

    Returns
    -------
    charge_state (pd.Series, length 365) — SOC fraction for each day
    battery_wh   (pd.Series, length 365) — battery capacity adjusted for temperature derating
    """
    charge_state = np.zeros(solar_wh_by_doy.size)
    current = float(initial_charge_state)

    battery_wh = np.ones(solar_wh_by_doy.shape) * battery_wh
    # adjust battery capacity for temperature derating (100% at 25C, -1% per 1C below 25C, down to a minimum of 50% capacity)
    # this estimate is conservative: in reality, the battery may be warmer than the ambient temperature, especially on sunny days.
    temp_derating_factor = (1.0 - (25.0 - daily_temp.clip(upper=25.0))*0.01).clip(lower=0.5, upper=1.0)
    effective_battery_wh = battery_wh * temp_derating_factor

    # Both bounds are expressed as fraction of NOMINAL capacity so that DoD
    # remains a fixed fraction of EFFECTIVE capacity regardless of temperature.
    #   upper = temp_derating_factor        (= effective / nominal)
    #   lower = temp_derating_factor × (1 - max_dod)
    min_soc_by_doy = temp_derating_factor * (1.0 - max_dod)

    # spinup for 10 years to reach a stable SOC before recording results
    for _ in range(10):
        for doy in solar_wh_by_doy.index:
            net = solar_wh_by_doy.at[doy] * charge_efficiency - daily_load_wh
            current = np.clip(current + net / effective_battery_wh.at[doy],
                              min_soc_by_doy.at[doy], temp_derating_factor.at[doy])
    for doy in solar_wh_by_doy.index:
        net = solar_wh_by_doy.at[doy] * charge_efficiency - daily_load_wh
        current = np.clip(current + net / effective_battery_wh.at[doy],
                          min_soc_by_doy.at[doy], temp_derating_factor.at[doy])
        charge_state[doy - 1] = current

    return pd.Series(charge_state, index=solar_wh_by_doy.index), effective_battery_wh


def simulate_storm(daily_load_wh: float, battery_wh: float, max_dod: float,
                   storm_solar_wh_day: float, charge_efficiency: float, storm_temp: float,
                   days: int, initial_charge_state: float = 1.0):
    """
    Simulate `days` of overcast / storm conditions.

    Returns
    -------
    soc_no_solar   (pd.Series, length days+1)
    soc_with_solar (pd.Series, length days+1)
        soc_with_solar uses `storm_solar_wh_day` (low-irradiance estimate).
    """
    # adjust battery capacity for temperature derating (100% at 25C, -1% per 1C below 25C, down to a minimum of 50% capacity)
    temp_derating_factor = np.clip(1.0 - (25.0 - storm_temp)*0.01, 0.5, 1.0)
    effective_battery_wh = battery_wh * temp_derating_factor

    soc_no = np.zeros(days + 1)
    soc_wi = np.zeros(days + 1)
    soc_no[0] = soc_wi[0] = float(initial_charge_state)*temp_derating_factor
    min_soc = temp_derating_factor * (1.0 - max_dod)



    solar_temp_derating = max(0.0, (25.0 - storm_temp)*0.004)  # 0.4% loss per degree C above 25C
    for i in range(days):
        soc_no[i + 1] = np.clip(soc_no[i] - daily_load_wh / effective_battery_wh, min_soc, temp_derating_factor)

        net = storm_solar_wh_day * (charge_efficiency - solar_temp_derating) - daily_load_wh
        soc_wi[i + 1] = np.clip(soc_wi[i] + net / effective_battery_wh, min_soc, temp_derating_factor)

    return pd.Series(soc_no, index=range(days + 1)), pd.Series(soc_wi, index=range(days + 1))


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main(cfg: BudgetConfig = CONFIG):
    battery_wh = cfg.V_batt * cfg.battery_ah

    # ── 1. Device load ────────────────────────────────────────────────────────
    daily_load_wh, breakdown = compute_daily_load(
        cfg.devices, cfg.scan_interval_sec, cfg.comms_interval_sec
    )

    print("\n=== Device Load Breakdown ===")
    for name, wh in breakdown.items():
        ah = wh / cfg.V_batt
        print(f"  {name:<22} {wh:7.3f} Wh/day  ({ah:.3f} Ah/day)")
    print(f"  {'─'*50}")
    print(f"  {'TOTAL':<22} {daily_load_wh:7.3f} Wh/day  "
          f"({daily_load_wh/cfg.V_batt:.3f} Ah/day @ {cfg.V_batt} V)")
    print(f"\n  Scan interval:  {cfg.scan_interval_sec/60:.0f} min  "
          f"│  Comms interval: {cfg.comms_interval_sec/60:.0f} min")

    # ── 2. Daymet climate data ────────────────────────────────────────────────
    print("\n=== Fetching Climate Data ===")
    mean_srad, low_srad, lowest_srad, min_temp_C, sunlight_sec = fetch_daymet(
        cfg.latitude, cfg.longitude, cfg.daymet_start_year, cfg.daymet_end_year
    )

    # ── 3. Solar energy ───────────────────────────────────────────────────────
    mean_solar_wh = panel_daily_wh(cfg.P_max, cfg.V_mp, cfg.panel_efficiency,
                                   mean_srad, sunlight_sec, min_temp_C, cfg)
    low_solar_wh  = panel_daily_wh(cfg.P_max, cfg.V_mp, cfg.panel_efficiency,
                                   low_srad,  sunlight_sec, min_temp_C, cfg)
    annual_solar  = float(mean_solar_wh.sum())
    annual_load   = daily_load_wh * 365

    print("\n=== Annual Energy Balance ===")
    print(f"  Panel rated output:   {cfg.P_max:.1f} W  "
          f"(efficiency derating: {cfg.panel_efficiency*100:.0f}%)")
    azimuth, elev = auto_orient_panel(cfg)
    print(f"  Panel orientation:    {elev:.1f}° elevation, {azimuth:.1f}° azimuth", end="")
    if cfg.panel_elev in ("auto", "winter", "summer") or cfg.panel_azi in ("auto", "winter", "summer"):
        message = " (set based on latitude"
        if cfg.panel_elev in ("winter", "summer"):
            message += f", optimized for {cfg.panel_elev}time"
        message += ")"
        print(message)
    else:
        print()
    print(f"  Mean annual solar power:    {annual_solar:,.0f} Wh/yr")
    print(f"  Annual device load:   {annual_load:,.0f} Wh/yr")
    net_annual = annual_solar - annual_load
    print(f"  Net balance:          {net_annual:+,.0f} Wh/yr  "
          f"({'SURPLUS' if net_annual >= 0 else 'DEFICIT'})")

    # ── 4. Battery & temperature summary ─────────────────────────────────────
    usable_wh  = battery_wh * cfg.max_dod
    usable_ah  = cfg.battery_ah * cfg.max_dod
    min_temp   = float(min_temp_C.min())
    coldest    = int(min_temp_C.idxmin())
    autonomy   = usable_wh / daily_load_wh   # days with no solar

    print("\n=== Battery & Temperature ===")
    print(f"  Battery:              {cfg.battery_ah:.1f} Ah @ {cfg.V_batt} V  "
          f"= {battery_wh:.0f} Wh total")
    print(f"  Usable ({cfg.max_dod*100:.0f}% DoD):      {usable_ah:.1f} Ah  "
          f"= {usable_wh:.0f} Wh")
    print(f"  Autonomy (no solar):  {autonomy:.1f} days")
    print(f"  Min temperature:      {min_temp:.1f} degC  (day of year {coldest})")

    # ── 5. Annual simulation ──────────────────────────────────────────────────
    soc_mean, battery_cap = simulate_year(mean_solar_wh, daily_load_wh, min_temp_C,
                             battery_wh, cfg.max_dod, cfg.charge_efficiency)
    soc_low, _  = simulate_year(low_solar_wh,  daily_load_wh, min_temp_C,
                             battery_wh, cfg.max_dod, cfg.charge_efficiency)

    print("\n=== Annual SOC Summary ===")
    print(f"  Min SOC (Mean Insolation Scenario): {soc_mean.min()*100:.1f}%  "
          f"(day {soc_mean.argmin()+1})")
    print(f"  Min SOC (25th Percentile Insolation Scenario):   {soc_low.min()*100:.1f}%  "
          f"(day {soc_low.argmin()+1})")

    # ── 6. Storm simulation ───────────────────────────────────────────────────
    # Use the worst (lowest) day from the low-irradiance series as storm solar
    worst_day   = int(low_solar_wh.idxmin())
    storm_solar = float(low_solar_wh.loc[worst_day])
    storm_temp  = float(min_temp_C.loc[worst_day])

    soc_no_sun, soc_with_sun = simulate_storm(
        daily_load_wh, battery_wh, cfg.max_dod,
        storm_solar, cfg.charge_efficiency, storm_temp,
        cfg.backup_days,
    )

    print(f"\n=== {cfg.backup_days}-Day Storm Simulation (from 100% charge) ===")
    print(f"  Min irradiance day:   day {worst_day}  "
          f"({storm_solar:.2f} Wh/day from panel)")
    print(f"  After {cfg.backup_days} days — no solar:   "
          f"{soc_no_sun.iat[-1]*100:.1f}%  "
          f"({'OK' if soc_no_sun.iat[-1] > 0 else 'DEPLETED'})")
    print(f"  After {cfg.backup_days} days — with solar: "
          f"{soc_with_sun.iat[-1]*100:.1f}%")

    # ── 7. Plots ──────────────────────────────────────────────────────────────
    doy        = np.arange(1, 366)
    storm_days = np.arange(0, cfg.backup_days + 1)
    min_soc_pct = (1 - cfg.max_dod) * 100

    fig = plt.figure(figsize=(20, 10))
    fig.suptitle(
        f"Solar Power Budget  │  Lat {cfg.latitude}°  Lon {cfg.longitude}°  │  "
        f"{cfg.P_max} W panel  │  {cfg.battery_ah} Ah @ {cfg.V_batt} V battery",
        fontsize=12, fontweight="bold",
    )
    gs = gridspec.GridSpec(2, 4, figure=fig, hspace=0.50, wspace=0.40)

    # Day-of-year → angle in radians (day 1 = top, clockwise like a calendar)
    # theta=0 is right (east) in matplotlib polar; we offset so day 1 is at top.
    theta = (doy - 1) / 365.0 * 2 * np.pi  # 0 … 2π, wrapping back to start
    theta_closed = np.append(theta, theta[0])  # close the ring for fill_between

    month_labels  = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    month_start_d = [1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335]
    month_theta   = [(d - 1) / 365.0 * 2 * np.pi for d in month_start_d]

    def _polar_month_labels(ax):
        ax.set_xticks(month_theta)
        ax.set_xticklabels(month_labels, fontsize=7)

    # Panel 1 — solar irradiance (polar)
    ax1 = fig.add_subplot(gs[0, 0], projection="polar")
    ax1.plot(theta_closed, np.append(mean_srad.values, mean_srad.values[0]),
             color="goldenrod", label=f"Mean ({cfg.daymet_start_year}–{cfg.daymet_end_year})")
    ax1.fill_between(theta_closed,
                     np.append(low_srad.values,  low_srad.values[0]),
                     np.append(mean_srad.values, mean_srad.values[0]),
                     alpha=0.3, color="goldenrod", label=f"25th Percentile ({cfg.daymet_start_year}–{cfg.daymet_end_year})")
    ax1.set_title("Daily Mean Insolation\n(W/m²)", pad=12)
    ax1.set_theta_zero_location("N")
    ax1.set_theta_direction(-1)
    _polar_month_labels(ax1)
    ax1.legend(fontsize=7, loc="lower right", bbox_to_anchor=(1.25, -0.05))

    # Panel 2 — daily energy: panel vs load (polar)
    ax2 = fig.add_subplot(gs[0, 1], projection="polar")
    ax2.plot(theta_closed, np.append(mean_solar_wh.values, mean_solar_wh.values[0]),
             color="orange", label="Solar Power Generated (Mean Insolation Scenario)")
    ax2.fill_between(theta_closed,
                     np.append(low_solar_wh.values, low_solar_wh.values[0]),
                     np.append(mean_solar_wh.values, mean_solar_wh.values[0]),
                     alpha=0.3, color="orange", label="Solar Power Generated (25th Percentile Insolation Scenario)")
    # ax2.plot(theta_closed, np.append(low_solar_wh.values, low_solar_wh.values[0]),
    #          color="orange", linestyle="--", label="Supply (25th Percentile Insolation Scenario)")
    ax2.axhline(daily_load_wh, color="C2", linestyle="-",
                label=f"Load ({daily_load_wh:.1f} Wh/day)")
    ax2.set_title("Daily Power Balance\n(Wh/day)", pad=12)
    ax2.set_theta_zero_location("N")
    ax2.set_theta_direction(-1)
    _polar_month_labels(ax2)
    ax2.legend(fontsize=7, loc="lower right", bbox_to_anchor=(1.25, -0.05))

    # Panel 3 — annual battery SOC (polar)
    ax3 = fig.add_subplot(gs[0, 2], projection="polar")
    ax3.plot(theta_closed, np.append(soc_mean * 100, soc_mean.iat[0] * 100),
             color="steelblue", label="Mean Insolation Scenario")
    ax3.fill_between(theta_closed,
                     np.append(soc_low * 100, soc_low.iat[0] * 100),
                     np.append(soc_mean * 100, soc_mean.iat[0] * 100),
                     alpha=0.3, color="steelblue", label="25th Percentile Insolation Scenario")
    # ax3.plot(theta_closed, np.append(soc_low  * 100, soc_low.iat[0]  * 100),
    #          color="steelblue", linestyle="--", label="25th Percentile Insolation Scenario")

    ax3.plot(theta_closed, np.append(battery_cap * 100, battery_cap.iat[0] * 100)/battery_wh,
             color="gray", linestyle="--", label="Effective Battery Capacity")
    ax3.plot(theta_closed, np.append(min_soc_pct*battery_cap/battery_wh, min_soc_pct*battery_cap.iat[0]/battery_wh),
             color="crimson", linestyle=":", label="Max Depth of Discharge")
    # #
    # ax3.axhline(min_soc_pct*battery_cap/battery_wh, color="crimson", linestyle=":",
    #             label="Max Depth of Discharge")
    ax3.set_title(r"Battery State of Charge (% of Nominal Capacity)", pad=12)
    ax3.set_theta_zero_location("N")
    ax3.set_theta_direction(-1)
    ax3.set_ylim(0, 105)
    _polar_month_labels(ax3)
    ax3.legend(fontsize=7, loc="lower right", bbox_to_anchor=(1.25, -0.05))

    # Panel 4 — minimum daily temperature (polar)
    # Shift values up by the minimum so the radial axis is non-negative,
    # then annotate the 0 °C ring.
    temp_vals  = min_temp_C.values
    temp_shift = max(-temp_vals.min(), 0)          # offset so r ≥ 0
    temp_r     = temp_vals + temp_shift
    zero_r     = temp_shift                        # where 0 °C sits on radial axis

    ax4 = fig.add_subplot(gs[0, 3], projection="polar")
    ax4.plot(theta_closed, np.append(temp_r, temp_r[0]), color="C4")
    ax4.axhline(zero_r, color="k", linestyle=":", linewidth=1.,
                label="0 °C")
    # Relabel radial ticks back to real temperatures
    ax4.set_ylim(temp_r.min() - 0.1*(temp_r.max() - temp_r.min()), temp_r.max() + 0.1*(temp_r.max() - temp_r.min()))
    rticks = ax4.get_yticks()
    ax4.set_yticks(rticks, [f"{v - temp_shift:.0f}" for v in rticks], fontsize=6)
    ax4.set_title("Mean Daily Min Temp\n(°C)", pad=12)
    ax4.set_theta_zero_location("N")
    ax4.set_theta_direction(-1)
    _polar_month_labels(ax4)
    ax4.legend(fontsize=7, loc="lower right", bbox_to_anchor=(1.25, -0.05))

    # Panel 5 — storm simulation (full width)
    ax5 = fig.add_subplot(gs[1, :])
    ax5.plot(storm_days, soc_no_sun   * 100, color="crimson",
             linewidth=2, label="Snow-Covered Panel (0 Wh/day)")
    ax5.plot(storm_days, soc_with_sun * 100, color="steelblue",
             linewidth=2,
             label=f"Clean Panel ({storm_solar:.1f} Wh/day)")
    ax5.axhline(min_soc_pct*battery_cap.at[worst_day]/battery_wh, color="crimson", linestyle=":",
                label="Max Depth of Discharge (temp-adjusted)")
    ax5.axhline(0, color="black", linestyle="-", linewidth=0.5)
    ax5.set_title(f"{cfg.backup_days}-Day Storm Reserve Simulation (starting from 100%, with temperature derating)")
    ax5.set_xlabel("Day of storm")
    ax5.set_ylabel(r"Battery State of Charge (% of Nominal Capacity)")
    ax5.set_xlim(0, cfg.backup_days)
    ax5.set_ylim(0, 105)
    ax5.legend(fontsize=8)

    out_path = "power_budget.png"
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    print(f"\nPlot saved -> {out_path}")
    plt.show()


if __name__ == "__main__":
    main()
