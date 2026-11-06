"""
String and inverter sizing.

Rules applied (the same checks a PV designer runs in a stringing tool):
  * Max modules per string: cold-morning Voc must stay below the inverter's
    max DC voltage (NEC 690.7 temperature correction using the record low).
  * Min modules per string: hot-afternoon Vmp must stay above the inverter's
    minimum MPPT voltage, or the inverter loses tracking.
  * Strings per MPPT: total short-circuit current x 1.25 (NEC 690.8) must not
    exceed the inverter's per-MPPT input limit.
"""

import math
from dataclasses import dataclass

from .config import PlantInputs


@dataclass
class StringDesign:
    voc_cold_v: float
    vmp_hot_v: float
    max_series: int
    min_series: int
    modules_per_string: int
    string_voc_cold_v: float
    string_vmp_hot_v: float
    string_vmp_cold_v: float
    string_kw: float
    strings_per_inverter: int
    strings_per_mppt: int
    mppt_current_a: float
    num_inverters: int
    total_strings: int
    total_modules: int
    dc_mw: float
    ac_mw: float
    actual_dc_ac_ratio: float
    land_acres: float
    checks: dict

    @property
    def ok(self) -> bool:
        return all(self.checks.values())


def size_strings(p: PlantInputs) -> StringDesign:
    m, inv, d, s = p.module, p.inverter, p.design, p.site

    voc_cold = m.voc_v * (1 + m.temp_coeff_voc * (s.record_low_c - 25))
    vmp_hot = m.vmp_v * (1 + m.temp_coeff_vmp * (s.design_high_c + d.cell_temp_rise_c - 25))
    vmp_cold = m.vmp_v * (1 + m.temp_coeff_vmp * (s.record_low_c - 25))
    max_series = math.floor(inv.max_dc_v / voc_cold)
    min_series = math.ceil(inv.mppt_min_v / vmp_hot)
    # Longest legal string: fewer strings means fewer combiners, less wire, lower cost.
    n = max(max_series, 1)

    string_kw = n * m.pmax_w / 1000
    strings_per_inv = max(1, round(inv.ac_kw * d.dc_ac_ratio / string_kw))
    strings_per_mppt = math.ceil(strings_per_inv / inv.num_mppt)
    mppt_current = strings_per_mppt * m.isc_a * d.nec_isc_factor

    num_inv = math.ceil(d.target_ac_mw * 1000 / inv.ac_kw)
    total_strings = num_inv * strings_per_inv
    total_modules = total_strings * n
    dc_mw = total_modules * m.pmax_w / 1e6
    ac_mw = num_inv * inv.ac_kw / 1000
    module_area = total_modules * m.length_m * m.width_m
    acres = module_area / d.gcr / 4046.86

    checks = {
        "Cold Voc below inverter max DC voltage": n * voc_cold <= inv.max_dc_v,
        "Hot Vmp above min MPPT voltage": n * vmp_hot >= inv.mppt_min_v,
        "Cold Vmp below max MPPT voltage": n * vmp_cold <= inv.mppt_max_v,
        "MPPT input current within limit (Isc x 1.25)": mppt_current <= inv.max_isc_per_mppt_a,
        "Valid series range (min <= max)": min_series <= max_series,
    }
    return StringDesign(voc_cold, vmp_hot, max_series, min_series, n, n * voc_cold, n * vmp_hot,
                        n * vmp_cold, string_kw, strings_per_inv, strings_per_mppt, mppt_current,
                        num_inv, total_strings, total_modules, dc_mw, ac_mw,
                        dc_mw / ac_mw, acres, checks)
