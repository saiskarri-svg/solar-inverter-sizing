"""
Capex, LCOE and NPV, plus a DC/AC ratio sweep to find the lowest-cost design.

Adding DC (a higher DC/AC ratio) costs module + DC BOS money and raises clipping,
but spreads the fixed inverter + interconnection cost over more MWh. The best
ratio is where LCOE bottoms out.
"""

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from .config import PlantInputs
from .simulate import EnergyResult, simulate
from .strings import size_strings


@dataclass
class Financials:
    capex: float
    annual_om: float
    lcoe_per_mwh: float
    npv: float


def _pv_factor(rate: float, years: int, degradation: float = 0.0) -> float:
    return sum((1 - degradation) ** (y - 1) / (1 + rate) ** y for y in range(1, years + 1))


def financials(p: PlantInputs, energy: EnergyResult) -> Financials:
    e = p.econ
    capex = (energy.dc_mw * 1e6 * (e.module_cost_per_wdc + e.dc_bos_cost_per_wdc)
             + energy.ac_mw * 1e6 * (e.inverter_cost_per_wac + e.ac_bos_cost_per_wac))
    om = energy.dc_mw * 1000 * e.om_per_kwdc_year
    pv_energy = energy.annual_mwh * _pv_factor(e.discount_rate, e.project_years, e.degradation_per_year)
    pv_om = om * _pv_factor(e.discount_rate, e.project_years)
    lcoe = (capex + pv_om) / pv_energy if pv_energy else float("nan")
    npv = pv_energy * e.ppa_price_per_mwh - pv_om - capex
    return Financials(capex, om, lcoe, npv)


def sweep_dc_ac(p: PlantInputs, dc_norm: pd.Series, ratios=None) -> pd.DataFrame:
    """Re-run string sizing + energy + LCOE across DC/AC ratios."""
    if ratios is None:
        ratios = np.round(np.arange(1.0, 1.61, 0.05), 2)
    rows = []
    for r in ratios:
        pr = replace(p, design=replace(p.design, dc_ac_ratio=float(r)))
        sd = size_strings(pr)
        en = simulate(pr, dc_norm, sd.dc_mw, sd.ac_mw)
        fin = financials(pr, en)
        rows.append({"target_ratio": r, "actual_ratio": sd.actual_dc_ac_ratio, "dc_mw": sd.dc_mw,
                     "annual_mwh": en.annual_mwh, "clipping_pct": en.clipping_pct,
                     "lcoe": fin.lcoe_per_mwh, "npv": fin.npv, "strings_ok": sd.ok})
    return pd.DataFrame(rows)
