"""
Interactive solar + inverter sizing tool.

    streamlit run app.py
"""

import plotly.graph_objects as go
import streamlit as st

from solar_model import (Design, Economics, Inverter, Module, PlantInputs, Site, battery_mwh_for_share,
                         battery_recapture, dc_per_kwdc, financials, pvgis_year, simulate,
                         size_strings, sweep_dc_ac, synthetic_year)

st.set_page_config(page_title="Solar & Inverter Sizing", layout="wide")
st.title("Solar PV & Inverter Sizing")
st.caption("String sizing to NEC 690.7/690.8, hourly energy simulation with pvlib, inverter clipping, "
           "DC/AC ratio optimization and DC-coupled battery recapture. Defaults are generic, not a specific product.")

d = PlantInputs()
sb = st.sidebar
sb.header("Site")
lat = sb.number_input("Latitude", -60.0, 60.0, d.site.latitude)
lon = sb.number_input("Longitude", -180.0, 180.0, d.site.longitude)
tz_offset = sb.number_input("UTC offset (standard time)", -12, 14, -8)
t_low = sb.number_input("Record low temp (°C)", -50.0, 20.0, d.site.record_low_c)
t_high = sb.number_input("Design high temp (°C)", 20.0, 55.0, d.site.design_high_c)
t_mean = sb.number_input("Annual mean temp (°C)", -10.0, 35.0, d.site.annual_mean_temp_c)
weather_src = sb.radio("Weather", ["Synthetic (offline)", "PVGIS TMY (real, needs internet)"])
clearness = sb.slider("Clearness (synthetic only)", 0.5, 1.0, d.site.clearness, 0.01)

sb.header("Module")
pmax = sb.number_input("Pmax (W)", 100.0, 800.0, d.module.pmax_w)
voc = sb.number_input("Voc (V)", 10.0, 100.0, d.module.voc_v)
vmp = sb.number_input("Vmp (V)", 10.0, 100.0, d.module.vmp_v)
isc = sb.number_input("Isc (A)", 1.0, 25.0, d.module.isc_a)
b_voc = sb.number_input("Voc temp coeff (%/°C)", -1.0, 0.0, d.module.temp_coeff_voc * 100) / 100
g_p = sb.number_input("Pmax temp coeff (%/°C)", -1.0, 0.0, d.module.temp_coeff_pmax * 100) / 100

sb.header("Inverter")
inv_kw = sb.number_input("AC rating (kW)", 1.0, 5000.0, d.inverter.ac_kw)
vmax = sb.selectbox("Max DC voltage (V)", [600.0, 1000.0, 1500.0], index=2)
mppt_min = sb.number_input("MPPT min (V)", 50.0, 1500.0, d.inverter.mppt_min_v)
n_mppt = sb.number_input("MPPT inputs", 1, 64, d.inverter.num_mppt)
mppt_i = sb.number_input("Max Isc per MPPT (A)", 5.0, 2000.0, d.inverter.max_isc_per_mppt_a)

sb.header("Plant design")
ac_mw = sb.number_input("Target AC capacity (MW)", 0.005, 2000.0, d.design.target_ac_mw)
ratio = sb.slider("DC/AC ratio", 1.0, 1.8, d.design.dc_ac_ratio, 0.01)
tracking = sb.radio("Mounting", ["single_axis", "fixed"],
                    format_func=lambda x: "Single-axis tracker" if x == "single_axis" else "Fixed tilt")
tilt = sb.slider("Fixed tilt (°)", 0, 60, int(d.design.fixed_tilt_deg), disabled=tracking != "fixed")

sb.header("Economics")
mod_cost = sb.number_input("Module cost ($/Wdc)", 0.05, 2.0, d.econ.module_cost_per_wdc)
bos_cost = sb.number_input("DC BOS + install ($/Wdc)", 0.05, 3.0, d.econ.dc_bos_cost_per_wdc)
inv_cost = sb.number_input("Inverter cost ($/Wac)", 0.01, 1.0, d.econ.inverter_cost_per_wac)
acbos = sb.number_input("AC BOS + interconnection ($/Wac)", 0.0, 2.0, d.econ.ac_bos_cost_per_wac)
ppa = sb.number_input("PPA price ($/MWh)", 0.0, 300.0, d.econ.ppa_price_per_mwh)

tz = f"Etc/GMT{'+' if tz_offset <= 0 else '-'}{abs(int(tz_offset))}"
p = PlantInputs(
    Site(latitude=lat, longitude=lon, timezone=tz, record_low_c=t_low, design_high_c=t_high,
         annual_mean_temp_c=t_mean, clearness=clearness),
    Module(pmax_w=pmax, voc_v=voc, vmp_v=vmp, isc_a=isc, temp_coeff_voc=b_voc, temp_coeff_pmax=g_p),
    Inverter(ac_kw=inv_kw, max_dc_v=vmax, mppt_min_v=mppt_min, mppt_max_v=vmax, num_mppt=int(n_mppt),
             max_isc_per_mppt_a=mppt_i),
    Design(target_ac_mw=ac_mw, dc_ac_ratio=ratio, tracking=tracking, fixed_tilt_deg=tilt),
    econ=Economics(module_cost_per_wdc=mod_cost, dc_bos_cost_per_wdc=bos_cost,
                   inverter_cost_per_wac=inv_cost, ac_bos_cost_per_wac=acbos, ppa_price_per_mwh=ppa),
)


@st.cache_data(show_spinner="Simulating a year of weather...")
def get_weather(site: Site, source: str):
    if source.startswith("PVGIS"):
        try:
            return pvgis_year(site), "PVGIS TMY"
        except Exception as exc:  # network blocked or service down
            st.warning(f"PVGIS unavailable ({type(exc).__name__}); using synthetic weather.")
    return synthetic_year(site), "synthetic"


weather, src = get_weather(p.site, weather_src)
dc_norm = dc_per_kwdc(p, weather)
sd = size_strings(p)
en = simulate(p, dc_norm, sd.dc_mw, sd.ac_mw)
fin = financials(p, en)

def card(col, label, value, sub):
    col.metric(label, value)
    col.caption(sub)


c = st.columns(5)
card(c[0], "DC capacity", f"{sd.dc_mw:,.0f} MW", f"{sd.ac_mw:,.1f} MWac")
card(c[1], "Annual energy", f"{en.annual_mwh / 1000:,.1f} GWh", f"{en.specific_yield:,.0f} kWh/kWdc")
card(c[2], "AC capacity factor", f"{en.capacity_factor_ac:.1%}", f"{en.clipping_pct:.1%} clipped")
card(c[3], "Capex", f"${fin.capex / 1e6:,.0f}M", f"${fin.capex / (sd.dc_mw * 1e6):.2f}/Wdc")
card(c[4], "LCOE", f"${fin.lcoe_per_mwh:,.1f}", f"$/MWh vs. PPA ${ppa:g}")
st.caption(f"Weather: {src}. GHI {weather['ghi'].sum() / 1000:,.0f} kWh/m²/yr.")

st.subheader("String & inverter design")
left, right = st.columns([3, 2])
left.dataframe([
    {"Item": "Modules per string", "Value": f"{sd.modules_per_string}  (allowed {sd.min_series}–{sd.max_series})"},
    {"Item": "String Voc at record low", "Value": f"{sd.string_voc_cold_v:,.0f} V  (limit {vmax:,.0f} V)"},
    {"Item": "String Vmp on hot afternoon", "Value": f"{sd.string_vmp_hot_v:,.0f} V  (MPPT min {mppt_min:,.0f} V)"},
    {"Item": "Strings per inverter / per MPPT", "Value": f"{sd.strings_per_inverter} / {sd.strings_per_mppt}"},
    {"Item": "MPPT input current (Isc × 1.25)", "Value": f"{sd.mppt_current_a:,.1f} A  (limit {mppt_i:g} A)"},
    {"Item": "Inverters", "Value": f"{sd.num_inverters:,}"},
    {"Item": "Strings / modules", "Value": f"{sd.total_strings:,} / {sd.total_modules:,}"},
    {"Item": "Actual DC/AC ratio", "Value": f"{sd.actual_dc_ac_ratio:.2f}"},
    {"Item": "Approx. land", "Value": f"{sd.land_acres:,.0f} acres"},
], hide_index=True, use_container_width=True)
for name, ok in sd.checks.items():
    (right.success if ok else right.error)(f"{'PASS' if ok else 'FAIL'}: {name}")

st.subheader("DC/AC ratio optimization")
sweep = sweep_dc_ac(p, dc_norm)
valid = sweep[sweep["strings_ok"]]
fig = go.Figure()
fig.add_bar(x=sweep["actual_ratio"], y=sweep["clipping_pct"] * 100, name="Clipping (%)", yaxis="y2",
            opacity=0.35, marker_color="#d62728")
fig.add_scatter(x=sweep["actual_ratio"], y=sweep["lcoe"], name="LCOE ($/MWh)", mode="lines+markers",
                line=dict(width=3, color="#1f77b4"))
if not valid.empty:
    best = valid.loc[valid["lcoe"].idxmin()]
    fig.add_vline(x=best["actual_ratio"], line_dash="dash", line_color="gray",
                  annotation_text=f"Best {best['actual_ratio']:.2f}")
    st.caption(f"Lowest LCOE at DC/AC {best['actual_ratio']:.2f} (${best['lcoe']:.1f}/MWh, "
               f"{best['clipping_pct']:.1%} clipping). Ratios that fail string checks are excluded.")
fig.update_layout(height=380, xaxis_title="DC/AC ratio", yaxis_title="LCOE ($/MWh)",
                  yaxis2=dict(title="Clipping (%)", overlaying="y", side="right", showgrid=False),
                  margin=dict(t=30, b=40), legend=dict(orientation="h", y=1.1))
st.plotly_chart(fig, use_container_width=True)

st.subheader("Clipping and DC-coupled battery recapture")
l2, r2 = st.columns(2)
daily = en.hourly["clipped_kw"].resample("D").sum()
worst = daily.idxmax().strftime("%Y-%m-%d")
day = en.hourly.loc[worst]
fig2 = go.Figure([
    go.Scatter(x=day.index.hour + 0.5, y=(day["ac_kw"] + day["clipped_kw"]) / 1000, name="Available", line=dict(dash="dot")),
    go.Scatter(x=day.index.hour + 0.5, y=day["ac_kw"] / 1000, name="Delivered", line=dict(width=3)),
])
fig2.update_layout(title=f"Highest-clipping day ({worst})", xaxis_title="Hour", yaxis_title="MW",
                   height=340, margin=dict(t=50, b=40))
l2.plotly_chart(fig2, use_container_width=True)

if en.clipped_mwh > 0:
    mwh90 = battery_mwh_for_share(en, 0.9)
    rec = battery_recapture(en, mwh90, p.econ.battery_rte_dc)
    r2.metric("Clipped energy", f"{en.clipped_mwh:,.0f} MWh/yr")
    card(r2, "Battery to capture 90%", f"{mwh90:,.0f} MWh", "DC-coupled, behind the inverter")
    card(r2, "Recaptured value", f"${rec * p.econ.evening_price_per_mwh / 1e6:,.2f}M/yr",
         f"{rec:,.0f} MWh at ${p.econ.evening_price_per_mwh:g}/MWh evening price")
else:
    r2.info("No clipping at this DC/AC ratio. Raise the ratio to see battery recapture.")
