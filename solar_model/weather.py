"""
One year of hourly weather for the site.

Default: a synthetic year built from pvlib's clear-sky model (Ineichen, with
Linke turbidity from pvlib's bundled climatology). Each day gets a random
clearness so the year mixes clear days (which clip) and cloudy days (which
don't), with clouds cutting direct beam more than diffuse light. Seeded, so results are repeatable.

Optional: a real Typical Meteorological Year from the EU's PVGIS service
(free, no API key). Needs internet access.
"""

import numpy as np
import pandas as pd
import pvlib

from .config import Site


def synthetic_year(site: Site, year: int = 2025, seed: int = 7) -> pd.DataFrame:
    times = pd.date_range(f"{year}-01-01 00:30", f"{year}-12-31 23:30", freq="h", tz=site.timezone)
    loc = pvlib.location.Location(site.latitude, site.longitude, site.timezone, site.altitude_m)
    clear = loc.get_clearsky(times, model="ineichen")

    # Daily clearness: mostly clear days with some cloudy ones (beta distribution, mean = site.clearness)
    rng = np.random.default_rng(seed)
    k = 6.0
    a, b = site.clearness * k, (1 - site.clearness) * k
    daily = rng.beta(a, b, size=366)
    day_idx = times.dayofyear.to_numpy() - 1
    k_t = daily[day_idx]
    ghi = clear["ghi"].to_numpy() * k_t
    # Clouds cut direct beam harder than total light; the rest arrives as diffuse.
    solpos = loc.get_solarposition(times)
    cos_z = np.clip(np.cos(np.radians(solpos["apparent_zenith"].to_numpy())), 0, None)
    dni = clear["dni"].to_numpy() * k_t ** 2
    dhi = np.maximum(ghi - dni * cos_z, 0.1 * ghi)
    doy = times.dayofyear.to_numpy()
    hour = times.hour.to_numpy() + 0.5
    seasonal = -site.seasonal_temp_swing_c * np.cos(2 * np.pi * (doy - 15) / 365)
    diurnal = site.daily_temp_swing_c * np.sin(2 * np.pi * (hour - 9) / 24)
    temp = site.annual_mean_temp_c + seasonal + diurnal

    return pd.DataFrame({"ghi": ghi, "dni": dni, "dhi": dhi, "temp_air": temp,
                         "wind_speed": site.wind_speed_ms}, index=times)


def pvgis_year(site: Site) -> pd.DataFrame:
    """Real TMY weather from PVGIS. Raises if the service can't be reached."""
    data, *_ = pvlib.iotools.get_pvgis_tmy(site.latitude, site.longitude, map_variables=True)
    data = data.tz_convert(site.timezone)
    data.index = data.index.map(lambda t: t.replace(year=2025))
    data = data.sort_index()
    return data[["ghi", "dni", "dhi", "temp_air", "wind_speed"]]
