from dataclasses import replace

import numpy as np
import pytest

from solar_model import (PlantInputs, battery_recapture, dc_per_kwdc, simulate, size_strings,
                         sweep_dc_ac, synthetic_year)
from solar_model.simulate import inverter_ac


@pytest.fixture(scope="module")
def p():
    return PlantInputs()


@pytest.fixture(scope="module")
def dc_norm(p):
    return dc_per_kwdc(p, synthetic_year(p.site))


def test_cold_voc_correction(p):
    sd = size_strings(p)
    # 52 V * (1 + 0.0025 * 30 C below STC) = 55.9 V -> floor(1500 / 55.9) = 26
    assert sd.voc_cold_v == pytest.approx(55.9)
    assert sd.max_series == 26
    assert sd.string_voc_cold_v <= p.inverter.max_dc_v


def test_colder_site_means_shorter_strings(p):
    cold = replace(p, site=replace(p.site, record_low_c=-30))
    assert size_strings(cold).max_series < size_strings(p).max_series


def test_mppt_current_check_fails_when_overloaded(p):
    weak = replace(p, inverter=replace(p.inverter, max_isc_per_mppt_a=30))
    sd = size_strings(weak)
    assert not sd.checks["MPPT input current within limit (Isc x 1.25)"]
    assert not sd.ok


def test_inverter_never_exceeds_rating():
    pdc = np.linspace(0, 600, 50)
    ac, unclipped = inverter_ac(pdc, 350, 0.985)
    assert ac.max() <= 350 + 1e-9
    assert np.all(unclipped >= ac - 1e-9)


def test_higher_dc_ac_ratio_clips_more(p, dc_norm):
    low = simulate(p, dc_norm, 110, 100)
    high = simulate(p, dc_norm, 160, 100)
    assert high.clipping_pct > low.clipping_pct
    assert high.annual_mwh > low.annual_mwh


def test_tracker_beats_fixed_tilt(p, dc_norm):
    fixed = replace(p, design=replace(p.design, tracking="fixed"))
    w = synthetic_year(p.site)
    assert simulate(p, dc_norm, 130, 100).annual_mwh > simulate(fixed, dc_per_kwdc(fixed, w), 130, 100).annual_mwh


def test_lcoe_optimum_is_interior(p, dc_norm):
    s = sweep_dc_ac(p, dc_norm)
    i = s["lcoe"].idxmin()
    assert 0 < i < len(s) - 1


def test_battery_recapture_bounded_by_clipping(p, dc_norm):
    en = simulate(p, dc_norm, 150, 100)
    assert battery_recapture(en, 1e6, 1.0) == pytest.approx(en.clipped_mwh, rel=1e-6)
    assert battery_recapture(en, 10, 0.92) < en.clipped_mwh


def test_specific_yield_is_plausible_for_central_valley_tracker(p, dc_norm):
    sd = size_strings(p)
    y = simulate(p, dc_norm, sd.dc_mw, sd.ac_mw).specific_yield
    assert 1800 < y < 2600
