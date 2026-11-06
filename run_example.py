"""
Design a 100 MWac plant, find the lowest-LCOE DC/AC ratio, and save charts to docs/.

    python run_example.py
"""

from dataclasses import replace
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from solar_model import (PlantInputs, battery_mwh_for_share, battery_recapture, dc_per_kwdc,
                         financials, simulate, size_strings, sweep_dc_ac, synthetic_year)

DOCS = Path(__file__).parent / "docs"
DOCS.mkdir(exist_ok=True)


def main():
    p = PlantInputs()
    weather = synthetic_year(p.site)
    dc_norm = dc_per_kwdc(p, weather)

    sd = size_strings(p)
    en = simulate(p, dc_norm, sd.dc_mw, sd.ac_mw)
    fin = financials(p, en)

    print(f"=== {p.design.target_ac_mw:g} MWac {p.design.tracking.replace('_', '-')} plant, {p.site.name} ===")
    print(f"String: {sd.modules_per_string} modules | cold Voc {sd.string_voc_cold_v:,.0f} V "
          f"(limit {p.inverter.max_dc_v:,.0f}) | hot Vmp {sd.string_vmp_hot_v:,.0f} V "
          f"(MPPT min {p.inverter.mppt_min_v:,.0f}) | allowed range {sd.min_series}-{sd.max_series}")
    print(f"Inverter: {sd.strings_per_inverter} strings, {sd.strings_per_mppt}/MPPT, "
          f"{sd.mppt_current_a:.1f} A per MPPT (limit {p.inverter.max_isc_per_mppt_a:g} A)")
    print(f"Plant: {sd.num_inverters} inverters, {sd.total_strings:,} strings, {sd.total_modules:,} modules, "
          f"{sd.dc_mw:.1f} MWdc / {sd.ac_mw:.1f} MWac (DC/AC {sd.actual_dc_ac_ratio:.2f}), ~{sd.land_acres:,.0f} acres")
    for name, ok in sd.checks.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print(f"Energy: {en.annual_mwh:,.0f} MWh/yr | yield {en.specific_yield:,.0f} kWh/kWdc | "
          f"AC capacity factor {en.capacity_factor_ac:.1%} | clipping {en.clipping_pct:.2%}")
    print(f"Capex ${fin.capex / 1e6:,.1f}M | LCOE ${fin.lcoe_per_mwh:.1f}/MWh")

    sweep = sweep_dc_ac(p, dc_norm)
    valid = sweep[sweep["strings_ok"]]
    best = valid.loc[valid["lcoe"].idxmin()]
    print(f"\nLowest LCOE at DC/AC {best['actual_ratio']:.2f}: ${best['lcoe']:.1f}/MWh, "
          f"clipping {best['clipping_pct']:.1%}")

    hi = replace(p, design=replace(p.design, dc_ac_ratio=1.5))
    sd_hi = size_strings(hi)
    en_hi = simulate(hi, dc_norm, sd_hi.dc_mw, sd_hi.ac_mw)
    mwh = battery_mwh_for_share(en_hi, 0.9)
    rec = battery_recapture(en_hi, mwh, p.econ.battery_rte_dc)
    print(f"At DC/AC 1.50: {en_hi.clipped_mwh:,.0f} MWh/yr clipped; a {mwh:.0f} MWh DC-coupled battery "
          f"recaptures {rec:,.0f} MWh/yr (${rec * p.econ.evening_price_per_mwh / 1e6:.2f}M at evening prices)")

    # Charts
    fig, ax1 = plt.subplots(figsize=(9, 4))
    ax1.plot(valid["actual_ratio"], valid["lcoe"], "o-", lw=2, label="LCOE")
    ax1.axvline(best["actual_ratio"], color="gray", ls="--")
    ax1.set(xlabel="DC/AC ratio", ylabel="LCOE ($/MWh)", title="Finding the lowest-cost DC/AC ratio")
    ax2 = ax1.twinx()
    ax2.bar(valid["actual_ratio"], valid["clipping_pct"] * 100, width=0.02, alpha=0.3, color="tab:red", label="Clipping")
    ax2.set_ylabel("Clipping (% of energy)")
    ax1.grid(alpha=0.3); fig.tight_layout(); fig.savefig(DOCS / "dc_ac_sweep.png", dpi=150); plt.close(fig)

    day = en_hi.hourly.loc[en_hi.hourly["clipped_kw"].resample("D").transform("sum").idxmax().strftime("%Y-%m-%d")]
    fig, ax = plt.subplots(figsize=(9, 4))
    hours = day.index.hour
    ax.plot(hours, day["dc_kw"] / 1000 * hi.losses.ac_factor(), label="DC available", lw=2)
    ax.plot(hours, day["ac_kw"] / 1000, label="AC delivered", lw=2)
    ax.fill_between(hours, day["ac_kw"] / 1000, (day["ac_kw"] + day["clipped_kw"]) / 1000, alpha=0.3,
                    color="tab:red", label="Clipped (battery can capture)")
    ax.set(xlabel="Hour", ylabel="MW", title="Clear summer day at DC/AC 1.5: inverter clipping")
    ax.legend(); ax.grid(alpha=0.3); fig.tight_layout(); fig.savefig(DOCS / "clipping_day.png", dpi=150); plt.close(fig)
    print(f"\nCharts saved to {DOCS}/")


if __name__ == "__main__":
    main()
