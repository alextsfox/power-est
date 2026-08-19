from daymetpy import daymet_timeseries
import solarpy
import pandas as pd
import numpy as np

def compute_sw_in_pot(timestamps: pd.DatetimeIndex, lat: float, lon: float, elev: float=0, alt: float=0, azi: float=0) -> pd.Series:
    """
    Compute whether or not it's daytime based on theoretical insolation

    Parameters
    ----------
    timestamps : pd.DatetimeIndex
        the timestamps representing each datapoint in your timeseries
    lat : float
        the latitude of the site (decimal degrees)
    lon : float
        the longitude of the site (decimal degrees)
    alt : float
        the altitude above sea level of the site (meters). Default 0m.
    azi : float
        the azimuth of the solar panel (degrees). Default 0° (facing North).
    elev : float
        the elevation of the solar panel (degrees). Default 90° (facing straight up).

    Returns
    -------
    sw_in_pot : pd.Series
        a pandas series with the same index as timestamps, containing the theoretical solar power incident on the panel surface (W m-2).
    """
    timestamps = timestamps.sort_values()

    panel = solarpy.solar_panel(1, 1, id_name="noname")  # surface, efficiency and name

    a = np.radians(azi)
    dec = np.radians(elev)
    vnorm = np.array([
        np.cos(dec) * np.cos(a),   # N
        np.cos(dec) * np.sin(a),   # E
        -np.sin(dec),               # D (negative = up)
    ])
    panel.set_orientation(vnorm)  # upwards
    panel.set_position(lat, lon, alt)
    dates = pd.date_range("2019-01-01", "2019-12-31 23:59:59", freq=timestamps[1] - timestamps[0])
    powers = []
    for dt in dates:
        panel.set_datetime(dt.to_pydatetime())
        powers.append(panel.power())
    powers = pd.DataFrame({"SW_IN_POT": powers, "doy": dates.dayofyear, "h": dates.hour, "m":dates.minute})

    if timestamps.name is None:
        timestamps = timestamps.rename("TIMESTAMP")
    df = pd.DataFrame({'doy':timestamps.dayofyear, 'h':timestamps.hour, 'm':timestamps.minute})
    df = df.set_index(timestamps)
    df = (
        df
        .reset_index(names=timestamps.name)
        .merge(powers, on=['doy', 'h', 'm'], how='left')
        .drop(columns=["doy", "h", "m"])
        .set_index(timestamps.name)
        .reindex(timestamps)
    )

    # leap days
    missing_dates = df.index[df["SW_IN_POT"].isna()]
    for dt in missing_dates:
        panel.set_datetime(dt.to_pydatetime())
        df.loc[dt, "SW_IN_POT"] = panel.power()
        
    return df["SW_IN_POT"]

def fetch_daymet(lat, lon, alt=0, azi=0, elev=90, start_year=2014, end_year=2024):
    """
    Pull Daymet daily data and return day-of-year aggregates:
        mean_srad   (W m-2)  — Mean Insolation Scenario radiation
        low_srad    (W m-2)  — 25th-percentile solar radiation (cloudy years)
        lowest_srad (W m-2)  — minimum solar radiation (worst day)
        min_temp_C  (degC)    — mean daily minimum temperature
        sunlight_sec (s)    — mean daylight duration
    All indexed 1-365 (day of year).

    Parameters
    ----------
    lat : float
        Latitude of the site (decimal degrees)
    lon : float
        Longitude of the site (decimal degrees)
    alt : float, optional
        Altitude of the site (meters above sea level). Default is 0.
    azi : float, optional
        Azimuth of the solar panel (degrees). Default is 0° (facing North).
    elev : float, optional
        Elevation of the solar panel (degrees). Default is 90° (facing straight up).
    start_year : int, optional
        The first year of Daymet data to fetch. Default is 2014.
    end_year : int, optional
        The last year of Daymet data to fetch. Default is 2024.
    """
    print(f"  Fetching Daymet data for ({lat}, {lon}), "
          f"{start_year}-{end_year} …  (this may take a moment)")

    # Fetch Daymet data for the specified location and time range
    daymet = daymet_timeseries(
        lon=lon, lat=lat,
        start_year=start_year, end_year=end_year,
    )
    daymet["srad"] = daymet["srad"] * daymet["dayl"] / 86400.0  # scale sunlight hours swin to full day swin

    # Calculate the theoretical daily mean solar power incident on a horizontal surface
    hourly_index = pd.date_range(start=f"{start_year}-01-01", end=f"{end_year}-12-31", freq="h")
    sw_in_pot_horizontal = compute_sw_in_pot(hourly_index, lat, lon, alt=alt, elev=90, azi=0)
    sw_in_pot_horizontal_daily = sw_in_pot_horizontal.resample("D").mean().reindex(daymet.index).interpolate(method="pchip")

    # in theory, daymet and sw_pot should match during the clearest days.
    # treat any mismatch as a gain error in daymet, and correct accordingly.
    max_pot = sw_in_pot_horizontal_daily.where(sw_in_pot_horizontal_daily > sw_in_pot_horizontal_daily.quantile(0.98)).median()
    max_daymet = daymet["srad"].where(daymet["srad"] > daymet["srad"].quantile(0.98)).median()
    daymet["srad"] *= max_pot / max_daymet

    # compute the difference in daily insolation due to inclement weather
    scale_factor = daymet["srad"] / sw_in_pot_horizontal_daily
    
    # Compute hourly theoretical insolation on the actual panel surface and multiply it by this scale factor to get a more realistic estimate of the actual insolation on the panel.
    sw_in_pot_actual = compute_sw_in_pot(hourly_index, lat, lon, alt=alt, elev=elev, azi=azi)
    sw_in_pot_actual *= scale_factor.reindex(hourly_index, method="ffill")

    df = pd.DataFrame(index=sw_in_pot_actual.index)
    df["srad_panel"] = sw_in_pot_actual
    daymet_reindex = daymet.reindex(df.index)

    # extremely rough estimate of air temperature...assume coldest at 3am, hottest at 3pm, and interpolate in between.
    df["ta"] = np.nan
    daymet_reindex = daymet_reindex.reindex(df.index).ffill()
    three_pm = df.index.hour == 15
    three_am = df.index.hour == 3
    df.loc[three_pm, "ta"] = daymet_reindex.loc[three_pm, "tmax"]
    df.loc[three_am, "ta"] = daymet_reindex.loc[three_am, "tmin"]

    df["srad_panel"].plot()

    return df

if __name__ == "__main__":
    lat, lon = 40.0, -105.0
    alt = 1600
    azi = 180
    elev = 90
    start_year = 2014
    start_year = 2020
    end_year = 2024

    daymet_df = fetch_daymet(lat, lon, alt=alt, azi=azi, elev=elev, start_year=start_year, end_year=end_year)
    # print(daymet_df.head())

    import matplotlib.pyplot as plt

    plt.show()




