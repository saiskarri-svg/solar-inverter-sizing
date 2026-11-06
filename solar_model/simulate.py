"""
Hourly energy simulation, clipping, and DC/AC ratio optimization.

Chain: weather -> sun position -> tracker angle -> plane-of-array irradiance
(Hay-Davies) -> cell temperature (Faiman) -> DC power (PVWatts) -> DC losses
-> inverter efficiency (PVWatts curve) -> clipping at inverter AC rating -> AC losses.

The DC side is computed once per kWdc, so sweeping the DC/AC ratio is fast.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
import pvlib

from .config import PlantInputs


def dc_per_kwdc(p: PlantInputs, weather: pd.DataFrame) -> pd.Series:
    """Hourly DC output (kW) for 1 kWdc of modules, after DC losses."""
    s, d = p.site, p.design
    loc = pvlib.location.Location(s.latitude, s.longitude, s.timezone, s.altitude_m)
    sp = loc.get_solarposition(weather.index)

    if d.tracking == "single_axis":
        tr = pvlib.tracking.singleaxis(sp["apparent_zenith"], sp["azimuth"], axis_tilt=0,
                                       axis_azimuth=180, max_angle=d.tracker_max_angle_deg,
                                       backtrack=True, gcr=d.gcr)
        tilt, azim = tr["surface_tilt"].fillna(0), tr["surface_azimuth"].fillna(180)
    else:
        tilt, azim = d.fixed_tilt_deg, d.azimuth_deg

    poa = pvlib.irradiance.get_total_irradiance(
        tilt, azim, sp["apparent_zenith"], sp["azimuth"], weather["dni"], weather["ghi"],
        weather["dhi"], dni_extra=pvlib.irradiance.get_extra_radiation(weather.index),
        model="haydavies")["poa_global"].fillna(0).clip(lower=0)

    t_cell = pvlib.temperature.faiman(poa, weather["temp_air"], weather["wind_speed"])
    dc = pvlib.pvsystem.pvwatts_dc(poa, t_cell, 1.0, p.module.temp_coeff_pmax)
    return (dc * p.losses.dc_factor()).clip(lower=0).rename("dc_kw_per_kwdc")


def inverter_ac(pdc_kw: np.ndarray, ac_kw: float, eta_nom: float):
    """PVWatts inverter curve. Returns (ac_clipped, ac_unclipped) in kW."""
    pdc0 = ac_kw / eta_nom
    zeta = np.where(pdc_kw > 0, pdc_kw / pdc0, 1.0)
    eta = eta_nom / 0.9637 * (-0.0162 * zeta - 0.0059 / zeta + 0.9858)
    unclipped = np.where(pdc_kw > 0, np.maximum(eta * pdc_kw, 0), 0)
    return np.minimum(unclipped, ac_kw), unclipped


@dataclass
class EnergyResult:
    dc_ac_ratio: float
    dc_mw: float
    ac_mw: float
    annual_mwh: float
    clipped_mwh: float
    capacity_factor_ac: float
    specific_yield: float          # kWh per kWdc per year
    hourly: pd.DataFrame

    @property
    def clipping_pct(self) -> float:
        total = self.annual_mwh + self.clipped_mwh
        return self.clipped_mwh / total if total else 0.0


def simulate(p: PlantInputs, dc_norm: pd.Series, dc_mw: float, ac_mw: float) -> EnergyResult:
    pdc = dc_norm.to_numpy() * dc_mw * 1000
    ac, unclipped = inverter_ac(pdc, ac_mw * 1000, p.inverter.eta_nominal)
    f = p.losses.ac_factor()
    hourly = pd.DataFrame({"dc_kw": pdc, "ac_kw": ac * f, "clipped_kw": (unclipped - ac) * f},
                          index=dc_norm.index)
    annual = hourly["ac_kw"].sum() / 1000
    clipped = hourly["clipped_kw"].sum() / 1000
    return EnergyResult(dc_mw / ac_mw, dc_mw, ac_mw, annual, clipped,
                        annual / (ac_mw * 8760), annual * 1000 / (dc_mw * 1000), hourly)


def battery_recapture(result: EnergyResult, battery_mwh: float, rte: float) -> float:
    """Clipped MWh a DC-coupled battery of this size could store and later deliver, per year."""
    daily = result.hourly["clipped_kw"].resample("D").sum() / 1000
    return float(np.minimum(daily, battery_mwh).sum() * rte)


def battery_mwh_for_share(result: EnergyResult, share: float = 0.9) -> float:
    """Smallest battery (MWh) that captures `share` of annual clipped energy."""
    daily = (result.hourly["clipped_kw"].resample("D").sum() / 1000).to_numpy()
    total = daily.sum()
    if total == 0:
        return 0.0
    lo, hi = 0.0, daily.max()
    for _ in range(40):
        mid = (lo + hi) / 2
        if np.minimum(daily, mid).sum() >= share * total:
            hi = mid
        else:
            lo = mid
    return hi
