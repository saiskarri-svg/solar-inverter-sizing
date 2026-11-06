"""
Inputs for the solar + inverter sizing tool.

Defaults describe a generic 100 MWac single-axis-tracker plant in California's
Central Valley, built from a generic ~580 W TOPCon module and a generic 1500 V
string inverter. They are illustrative, not datasheet values for a specific
product: replace them with the actual datasheets before using results.
"""

from dataclasses import dataclass, field


@dataclass
class Site:
    name: str = "Central Valley, CA"
    latitude: float = 36.8
    longitude: float = -119.8
    altitude_m: float = 100.0
    timezone: str = "Etc/GMT+8"         # fixed standard time (no daylight saving)
    record_low_c: float = -5.0          # ASHRAE extreme minimum: sets max string voltage
    design_high_c: float = 40.0         # ASHRAE 2% high: sets min string voltage
    annual_mean_temp_c: float = 17.0
    seasonal_temp_swing_c: float = 9.0  # summer vs winter mean
    daily_temp_swing_c: float = 7.0     # afternoon vs pre-dawn
    clearness: float = 0.92             # average share of clear-sky irradiance reaching the ground
    wind_speed_ms: float = 2.0


@dataclass
class Module:
    pmax_w: float = 580.0
    voc_v: float = 52.0
    vmp_v: float = 43.6
    isc_a: float = 14.1
    imp_a: float = 13.3
    temp_coeff_voc: float = -0.0025   # per degC (-0.25 %/C)
    temp_coeff_vmp: float = -0.0030   # per degC
    temp_coeff_pmax: float = -0.0029  # per degC
    length_m: float = 2.28
    width_m: float = 1.13


@dataclass
class Inverter:
    ac_kw: float = 350.0
    max_dc_v: float = 1500.0
    mppt_min_v: float = 500.0
    mppt_max_v: float = 1500.0
    num_mppt: int = 12
    max_isc_per_mppt_a: float = 60.0
    eta_nominal: float = 0.985


@dataclass
class Design:
    target_ac_mw: float = 100.0
    dc_ac_ratio: float = 1.30             # also called ILR (inverter loading ratio)
    tracking: str = "single_axis"         # "single_axis" or "fixed"
    fixed_tilt_deg: float = 25.0
    azimuth_deg: float = 180.0            # 180 = south
    tracker_max_angle_deg: float = 60.0
    gcr: float = 0.35                     # ground coverage ratio
    cell_temp_rise_c: float = 30.0        # cell temp above ambient for hot-day Vmp check
    nec_isc_factor: float = 1.25          # NEC 690.8 continuous-current multiplier


@dataclass
class Losses:
    soiling: float = 0.02
    mismatch: float = 0.01
    dc_wiring: float = 0.015
    ac_wiring_and_transformer: float = 0.015
    availability: float = 0.005

    def dc_factor(self) -> float:
        return (1 - self.soiling) * (1 - self.mismatch) * (1 - self.dc_wiring)

    def ac_factor(self) -> float:
        return (1 - self.ac_wiring_and_transformer) * (1 - self.availability)


@dataclass
class Economics:
    module_cost_per_wdc: float = 0.30
    dc_bos_cost_per_wdc: float = 0.65      # racking/trackers, DC wiring, labor
    inverter_cost_per_wac: float = 0.06
    ac_bos_cost_per_wac: float = 0.20      # MV collection, substation, interconnection
    om_per_kwdc_year: float = 15.0
    degradation_per_year: float = 0.005
    project_years: int = 30
    discount_rate: float = 0.07
    ppa_price_per_mwh: float = 45.0
    evening_price_per_mwh: float = 90.0    # value of clipped energy shifted by a DC-coupled battery
    battery_rte_dc: float = 0.92           # DC-coupled round trip (no extra inverter stage)


@dataclass
class PlantInputs:
    site: Site = field(default_factory=Site)
    module: Module = field(default_factory=Module)
    inverter: Inverter = field(default_factory=Inverter)
    design: Design = field(default_factory=Design)
    losses: Losses = field(default_factory=Losses)
    econ: Economics = field(default_factory=Economics)
