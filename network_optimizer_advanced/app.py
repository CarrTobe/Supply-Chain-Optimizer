"""Interactive advanced supply-chain network optimizer, run: streamlit run app.py.

Single-week fictional network planning, with MILP reoptimizing on input changes.
"""
from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from optimizer import WEATHER, benchmark_scenarios, default_lanes, default_settings, defaults, solve_network

st.set_page_config(page_title="Network Optimizer Pro", page_icon="🚚", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
.block-container {padding-top:1.45rem;padding-bottom:3rem;max-width:1500px}
.hero {padding:21px 26px;border-radius:14px;margin-bottom:16px;background:linear-gradient(110deg,#10314d,#0a6170);color:#fff}
.hero h1 {color:#fff;margin:0;font-size:1.85rem}.hero p {margin:7px 0 0;color:#c4e5ea}
[data-testid="stMetric"] {background:rgba(109,156,166,.09);padding:11px 13px;border:1px solid rgba(127,150,160,.2);border-radius:10px}
.small {font-size:0.85rem;color:gray}
</style>""",unsafe_allow_html=True)
st.markdown('<div class="hero"><h1>Supply Chain Network Optimizer · Advanced</h1><p>Facility construction · multi-site weather risk · replenishment safety stock · truckload consolidation · scenario planning</p></div>',unsafe_allow_html=True)
st.info("**Illustrative planning model.** All costs, demand, lead times, weather effects, and road distances are mock assumptions—not live operational data. All financial outputs are representative-week estimates.",icon="ℹ️")

base_dc, base_markets=defaults()
base_s=default_settings()

with st.sidebar:
    st.header("Scenario controls")
    st.caption("Controls rerun the optimization. Numeric fields accept typed values and precise adjustments.")
    with st.expander("📦 Demand, freight & route limits",expanded=True):
        demand_pct=st.number_input("Demand change (%)",min_value=-95.0,max_value=500.0,value=0.0,step=1.0,format="%.1f",help="Applies to every market demand in the edit table, before reoptimizing")
        freight_pct=st.number_input("Freight inflation / discount (%)",min_value=-95.0,max_value=500.0,value=0.0,step=1.0,format="%.1f",help="Scales full-truck and spot transportation rates")
        road_factor=st.number_input("Road-distance multiplier",min_value=1.0,max_value=3.0,value=1.20,step=0.01,format="%.2f",help="Haversine miles × this factor, unless a lane has a manual mileage override")
        use_dist=st.checkbox("Enforce maximum road miles",value=False)
        max_road=st.number_input("Maximum route distance (miles)",min_value=1.0,max_value=15000.0,value=1800.0,step=1.0,format="%.1f",disabled=not use_dist,help="Type any distance; eligible routes beyond this threshold are disabled")
        use_transit=st.checkbox("Enforce maximum outbound transit days",value=False)
        max_transit=st.number_input("Maximum transit days",min_value=0.1,max_value=60.0,value=7.0,step=0.1,format="%.1f",disabled=not use_transit)
        drive_rate=st.number_input("Estimated driving miles per day",min_value=100.0,max_value=1000.0,value=500.0,step=10.0)
    with st.expander("🌦️ Multi-location weather event",expanded=True):
        event_level=st.selectbox("Weather event severity",list(WEATHER),index=0)
        multi_centers=st.multiselect("Affected distribution centers",[c["Center"] for c in base_dc],default=[],help="All chosen DCs receive the event, in addition to custom weather specified in the DC editor")
        multi_markets=st.multiselect("Affected customer markets",[m["Market"] for m in base_markets],default=[],help="Market storms increase outbound cost and travel delay on inbound lanes")
        weather_intensity=st.number_input("Weather effect intensity (×)",min_value=0.0,max_value=3.0,value=1.0,step=0.05,format="%.2f",help="0 = no modeled impact, 1 = the preset impact, 1.5 = 50% larger impacts; capacity cannot be negative")
        st.caption("To set different severities at several places, use each site’s **Weather** field in Network inputs.")
    with st.expander("🚛 Truckload consolidation & rates",expanded=False):
        truck_enabled=st.checkbox("Allow full-truckload consolidation",value=True)
        spot_enabled=st.checkbox("Allow individual / spot shipments",value=True)
        truck_capacity=st.number_input("Shipping units per truck",min_value=1,max_value=5000,value=250,step=1)
        truck_dispatch=st.number_input("Fixed cost per truck ($)",min_value=0.0,max_value=50000.0,value=210.0,step=5.0,format="%.2f")
        truck_mile=st.number_input("Truck rate per mile ($)",min_value=0.0,max_value=50.0,value=2.20,step=0.05,format="%.2f")
        fill=st.number_input("Minimum truck fill (%)",min_value=0.0,max_value=100.0,value=0.0,step=1.0,format="%.1f",help="If nonzero, each dispatched truck lane must meet this aggregate fill fraction")
        spot_base=st.number_input("Spot freight per unit, base ($)",min_value=0.0,max_value=500.0,value=4.5,step=0.1,format="%.2f")
        spot_mile=st.number_input("Spot freight per unit-mile ($)",min_value=0.0,max_value=10.0,value=0.014,step=0.001,format="%.3f")
    with st.expander("📊 Inventory, service & emissions",expanded=False):
        enable_safety=st.checkbox("Calculate and hold safety stock",value=True)
        service_target=st.number_input("Inventory cycle-service target (%)",min_value=50.0,max_value=99.9,value=95.0,step=0.1,format="%.1f",help="Normal-distribution z score for replenishment protection, not the network delivery fulfillment metric")
        min_fulfillment=st.number_input("Hard minimum demand fulfillment (%)",min_value=0.0,max_value=100.0,value=0.0,step=0.5,format="%.1f",help="0 = permit penalized shortages; 100 = require every demand unit served or report infeasibility")
        shortfall=st.number_input("Penalty per unserved unit ($)",min_value=0.01,max_value=1_000_000.0,value=250.0,step=5.0,format="%.2f")
        carbon=st.number_input("Carbon shadow price ($/tonne)",min_value=0.0,max_value=2000.0,value=35.0,step=1.0,format="%.2f")
        emissions_rate=st.number_input("Spot CO₂ tonne / unit-mile",min_value=0.0,max_value=1.0,value=0.00014,step=0.00001,format="%.5f")
        emissions_truck=st.number_input("Truck CO₂ tonne / truck-mile",min_value=0.0,max_value=1.0,value=0.0015,step=0.0001,format="%.4f")
    with st.expander("🏗️ Construction & solver",expanded=False):
        allow_build=st.checkbox("Allow proposed DC construction",value=True)
        capex_budget=st.number_input("Total construction budget ($)",min_value=0.0,max_value=1_000_000_000.0,value=4_000_000.0,step=50000.0,format="%.0f",disabled=not allow_build)
        max_build=st.number_input("Maximum new facilities",min_value=0,max_value=100,value=2,step=1,disabled=not allow_build)
        years=st.number_input("Amortization / evaluation horizon (years)",min_value=0.25,max_value=40.0,value=5.0,step=0.25,format="%.2f",help="Weekly construction cost = one-time build price / (52 × horizon); this is simple straight-line equivalent, not NPV")
        time_limit=st.number_input("Solver time limit (seconds)",min_value=2.0,max_value=180.0,value=20.0,step=1.0)
        gap_pct=st.number_input("Maximum relative solver gap (%)",min_value=0.0,max_value=10.0,value=0.5,step=0.1,format="%.2f",help="0.5% means a solution within 0.5% of the solver's global best bound, when certified")

s={"demand_change_pct":demand_pct,"freight_change_pct":freight_pct,"road_distance_factor":road_factor,
   "max_road_miles":max_road if use_dist else None,"max_transit_days":max_transit if use_transit else None,
   "avg_drive_miles_per_day":drive_rate,"weather_intensity":weather_intensity,
   "truckload_enabled":truck_enabled,"spot_enabled":spot_enabled,"truck_capacity":truck_capacity,
   "truck_dispatch_cost":truck_dispatch,"truck_cost_per_mile":truck_mile,"min_truck_fill_pct":fill,
   "ltl_base_per_unit":spot_base,"ltl_per_mile_per_unit":spot_mile,"safety_stock_enabled":enable_safety,
   "target_service_pct":service_target,"minimum_fulfillment_pct":min_fulfillment,"unserved_penalty":shortfall,
   "carbon_price_per_tonne":carbon,"co2_tonnes_per_unit_mile":emissions_rate,"co2_tonnes_per_truck_mile":emissions_truck,
   "construction_enabled":allow_build,"construction_budget":capex_budget if allow_build else 0.0,
   "max_new_facilities":max_build if allow_build else 0,"investment_years":years,
   "time_limit_seconds":time_limit,"relative_gap":gap_pct/100}


def clean_table(df: pd.DataFrame) -> list[dict]:
    result=[]
    for record in df.to_dict("records"):
        for key, value in list(record.items()):
            if value is None or (not isinstance(value,(dict,list)) and pd.isna(value)):
                record[key]=None
        result.append(record)
    return result

with st.expander("✏️ Network inputs · edit sites, markets, weather, and individual routes",expanded=False):
    st.caption("Click a cell to edit it. Add or remove rows to expand your mock network. Newly added facilities require a name, type, coordinates and complete numeric parameters. Existing = available constructed site; Candidate = requires paid construction.")
    c_tab,m_tab,l_tab=st.tabs(["🏢 Distribution centers", "📍 Customer demand", "🛣️ Lane restrictions and overrides"])
    with c_tab:
        dc_df=st.data_editor(pd.DataFrame(base_dc),key="dc_edit_v2",num_rows="dynamic",hide_index=True,use_container_width=True,
            column_config={
                "Type":st.column_config.SelectboxColumn("Type",options=["Existing","Candidate"],required=True),
                "Weather":st.column_config.SelectboxColumn("Weather",options=list(WEATHER),required=True),
                "Available":st.column_config.CheckboxColumn("Available"),
                "Capacity":st.column_config.NumberColumn("Weekly throughput",min_value=0,step=1),
                "Storage capacity":st.column_config.NumberColumn("Stock storage units",min_value=0,step=1),
                "Demand CV":st.column_config.NumberColumn("Daily demand CV",min_value=0.0,step=0.01,format="%.3f"),
                "Lead days":st.column_config.NumberColumn("Mean inbound lead (days)",min_value=0.0,step=0.25),
                "Lead SD days":st.column_config.NumberColumn("Inbound lead SD (days)",min_value=0.0,step=0.1),
                "Cycle days":st.column_config.NumberColumn("Replenishment cycle (days)",min_value=0.0,step=0.25),
                "Holding $/unit/week":st.column_config.NumberColumn("Holding $/unit/week",min_value=0.0,step=0.01,format="$%.2f"),
                "Handling $/unit":st.column_config.NumberColumn("Handling $/unit",min_value=0.0,step=0.05,format="$%.2f"),
                "Fixed $/week":st.column_config.NumberColumn("Fixed $/week",min_value=0.0,step=25.0),
                "Build cost $":st.column_config.NumberColumn("Construction $",min_value=0.0,step=10000.0),
                "Latitude":st.column_config.NumberColumn("Latitude",step=0.01),
                "Longitude":st.column_config.NumberColumn("Longitude",step=0.01),
            })
        st.caption("**Weather** in each site row can be set independently; the sidebar multi-site event overrides the severity for selected locations. Storage capacity limits safety + cycle stock; weekly throughput capacity limits shipments.")
    with m_tab:
        market_df=st.data_editor(pd.DataFrame(base_markets),key="market_edit_v2",num_rows="dynamic",hide_index=True,use_container_width=True,
             column_config={"Weather":st.column_config.SelectboxColumn("Weather",options=list(WEATHER),required=True),
                            "Demand":st.column_config.NumberColumn("Weekly demand units",min_value=0,step=1),
                            "Latitude":st.column_config.NumberColumn("Latitude",step=0.01),
                            "Longitude":st.column_config.NumberColumn("Longitude",step=0.01)})
        st.caption("Demand is the number of standardized outbound shipping units expected per week. It is multiplied by the scenario-wide demand adjustment.")
    with l_tab:
        st.caption("**Road override** replaces the proxy mileage for a specific center–market lane. **Blocked** forbids shipments. **Extra freight %** changes freight charges. **Extra transit days** can violate the transit cap. **Max trucks/week** caps truckload departures; spot mode can still ship unless the route is blocked.")
        st.caption("All lane numeric cells accept small incremental edits; leave optional override or truck-count cells empty to use defaults.")

centers=clean_table(dc_df)
markets=clean_table(market_df)
if any(c.get("Center") is None for c in centers) or any(m.get("Market") is None for m in markets):
    st.error("Please fill the Center or Market name on any newly added rows.")
    st.stop()
for c in centers:
    if c["Center"] in multi_centers: c["Weather"]=event_level
for m in markets:
    if m["Market"] in multi_markets: m["Weather"]=event_level

# A network-signature-based key preserves lane edits across reruns but regenerates the
# grid after users add/remove facilities or markets.
lane_signature=hashlib.sha1(json.dumps([[c["Center"] for c in centers],[m["Market"] for m in markets]],sort_keys=True).encode()).hexdigest()[:12]
with l_tab:
    lane_df=st.data_editor(pd.DataFrame(default_lanes(centers,markets)),key="lane_v2_"+lane_signature,
        num_rows="fixed",hide_index=True,use_container_width=True,
        disabled=["Center","Market"],column_config={
            "Blocked":st.column_config.CheckboxColumn("Blocked"),
            "Road override miles":st.column_config.NumberColumn("Road override miles",min_value=0.1,step=1.0,format="%.1f"),
            "Extra freight %":st.column_config.NumberColumn("Extra freight %",min_value=0.0,max_value=1000.0,step=0.5,format="%.1f"),
            "Extra transit days":st.column_config.NumberColumn("Extra transit days",min_value=0.0,max_value=365.0,step=0.25,format="%.2f"),
            "Max trucks/week":st.column_config.NumberColumn("Max trucks/week",min_value=0,step=1),
        })
lanes=clean_table(lane_df)

# Preserve separately solved original defaults for a consistent benchmark.
@st.cache_data(show_spinner=False)
def baseline_result():
    return solve_network(*defaults())

try:
    with st.spinner("Reoptimizing inventory, construction, and transportation..."):
        current=solve_network(centers,markets,s,lanes)
        baseline=baseline_result()
except (ValueError,RuntimeError,KeyError,TypeError) as exc:
    st.error(f"Optimization is not available for this configuration: {exc}")
    st.info("Check empty added rows, restrictive limits, fulfillment target, site capacities, facility budget, and whether at least one transport mode is enabled. The solver will not silently ignore infeasible constraints.")
    st.stop()

if current["unserved"]:
    st.warning(f"**Service risk:** {current['unserved']:,} of {current['demand']:,} units unserved. The objective includes ${shortfall:,.2f} per unserved unit; inspect the market table.")
else:
    st.success("All modeled weekly demand is met by the optimized allocation.")

k1,k2,k3,k4,k5,k6=st.columns(6)
k1.metric("Total weekly cost",f"${current['total_cost']:,.0f}",f"${current['total_cost']-baseline['total_cost']:+,.0f} vs original",delta_color="inverse")
k2.metric("Fulfillment",f"{current['service_pct']:.1f}%",f"{current['unserved']:,} unserved",delta_color="off")
k3.metric("Trucks dispatched",f"{current['trucks']:,}",f"{current['avg_truck_fill_pct']:.1f}% avg TL fill",delta_color="off")
k4.metric("Safety stock",f"{current['safety_stock_units']:,.0f}","estimated shipping units",delta_color="off")
k5.metric("Construction",str(len(current['built'])),f"${current['construction_capex']:,.0f} one-time",delta_color="off")
k6.metric("Cost per delivered unit",f"${current['cost_per_delivered']:,.2f}" if current["cost_per_delivered"] is not None else "N/A")
st.caption(f"Solver: {current['solver_status']} · MIP gap {current['mip_gap']*100:.3f}% · Total cost includes facility costs, allocated construction cost, inventory holding costs, and any service shortfall penalty. The construction KPI shows one-time capex, *not* an additional weekly cost.")


def network_map(result: dict, dc: list[dict], mk: list[dict]) -> go.Figure:
    fig=go.Figure()
    d_by={x["Center"]:x for x in dc}
    m_by={x["Market"]:x for x in mk}
    r_by={x["Center"]:x for x in result["center_results"]}
    top=max((x["Units"] for x in result["allocations"]),default=1)
    for a in sorted(result["allocations"],key=lambda x:x["Units"]):
        d=d_by[a["Center"]]; m=m_by[a["Market"]]
        fig.add_trace(go.Scattergeo(lon=[d["Longitude"],m["Longitude"]],lat=[d["Latitude"],m["Latitude"]],mode="lines",
             line=dict(color="rgba(16,134,163,.45)",width=1+4*a["Units"]/top),showlegend=False,
             hovertemplate=f"{a['Center']} → {a['Market']}<br>{a['Units']:,} units/week<br>TL trucks: {a['Trucks dispatched']}<br>Road estimate: {a['Road miles (proxy)']:,.0f} mi<extra></extra>"))
    fig.add_trace(go.Scattergeo(lon=[c["Longitude"] for c in dc],lat=[c["Latitude"] for c in dc],mode="markers+text",
             text=[c["Center"].replace(" (proposed)","*") for c in dc],textposition="top center",
             marker=dict(size=[10+min(12,r_by[c["Center"]]["Allocated"]/250) for c in dc],
               color=["#159679" if r_by[c["Center"]]["Built"] else ("#124661" if r_by[c["Center"]]["Open"] else "#a8b3bd") for c in dc],
               line=dict(color="white",width=1.3)),name="DCs (green = newly built)",
             hovertext=[f"{c['Center']}<br>Open: {r_by[c['Center']]['Open']}<br>Built: {r_by[c['Center']]['Built']}<br>Allocated: {r_by[c['Center']]['Allocated']:,}" for c in dc],hoverinfo="text"))
    fig.add_trace(go.Scattergeo(lon=[m["Longitude"] for m in mk],lat=[m["Latitude"] for m in mk],mode="markers",
             marker=dict(color="#e8a04c",size=8,line=dict(width=1,color="white")),name="Markets",
             hovertext=[m["Market"] for m in mk],hoverinfo="text"))
    fig.update_geos(scope="usa",projection_type="albers usa",showland=True,landcolor="#f0f5f6",showlakes=True,lakecolor="white",showsubunits=True,subunitcolor="#cbd7db")
    fig.update_layout(height=480,margin=dict(t=10,b=15,l=0,r=0),legend=dict(orientation="h",y=-.05))
    return fig

summary_tab,map_tab,inv_tab,build_tab,scenario_tab,model_tab=st.tabs(["📊 Network overview","🗺️ Route allocation","📦 Inventory & lead times","🏗️ Facilities & construction","🧪 Scenario lab","📐 Model details"])
with summary_tab:
    left,right=st.columns([1,1])
    with left:
        st.subheader("Weekly optimization cost breakdown")
        cost_df=pd.DataFrame([{"Category":k,"Cost":v} for k,v in current["breakdown"].items() if v>0])
        if len(cost_df):
            fig=px.bar(cost_df.sort_values("Cost"),x="Cost",y="Category",orientation="h",labels={"Cost":"Weekly cost ($)"},text="Cost")
            fig.update_traces(texttemplate="$%{text:,.0f}",textposition="outside")
            fig.update_layout(height=430,margin=dict(t=15,b=15,l=5,r=40))
            st.plotly_chart(fig,use_container_width=True)
    with right:
        st.subheader("DC throughput vs effective capacity")
        util_df=pd.DataFrame(current["center_results"])
        fig=px.bar(util_df,x="Center",y=["Allocated","Effective throughput capacity"],barmode="group",
                color_discrete_sequence=["#1597ab","#a8bcc7"],labels={"value":"Units/week"})
        fig.update_layout(height=430,margin=dict(t=15,b=70,l=5,r=10),xaxis_tickangle=-35,legend=dict(orientation="h",y=1.12))
        st.plotly_chart(fig,use_container_width=True)
    st.subheader("Fulfillment exceptions")
    misses=[x for x in current["market_results"] if x["Unserved"]]
    if misses:
        st.dataframe(pd.DataFrame(misses),hide_index=True,use_container_width=True)
    else: st.write("No modeled customer-market shortfalls.")
    st.caption("A cheaper plan is not necessarily a better plan if it leaves demand unserved. Cost comparisons include explicit shortfall penalties.")

with map_tab:
    st.subheader("Optimized routes in the United States")
    st.caption("Line thickness represents volume, not route efficiency. The map draws straight lines; mileage is the great-circle × road multiplier or a user-provided override, not live road navigation.")
    st.plotly_chart(network_map(current,centers,markets),use_container_width=True)
    st.subheader("Optimized truckload and spot shipments")
    route_df=pd.DataFrame(current["allocations"])
    if len(route_df):
        st.dataframe(route_df.sort_values("Units",ascending=False),hide_index=True,use_container_width=True)
        st.download_button("Download route allocations (CSV)",route_df.to_csv(index=False),"optimized_routes.csv","text/csv")
    else: st.info("No shipment routes were selected.")
    st.metric("Mean assigned lane distance",f"{current['avg_road_miles']:,.0f} proxy miles")
    a,b=st.columns(2)
    a.metric("Units on consolidated trucks",f"{current['truckload_units']:,}")
    b.metric("Units on spot / LTL",f"{current['spot_units']:,}")
    st.caption("Truckload consolidation occurs **within each DC–market lane**, not multi-stop routing between markets. Fractional truckloads are not counted as free truck capacity: the solver uses integer truck dispatches.")

with inv_tab:
    st.subheader("Replenishment buffers and storage space")
    st.markdown("Safety stock changes with **lead time, lead-time standard deviation, demand variability, service target, and weather**. Cycle inventory changes with replenishment cycle days. These stocks consume facility storage space and accrue weekly holding costs.")
    a,b,c=st.columns(3)
    a.metric("Network safety stock",f"{current['safety_stock_units']:,.1f} units")
    b.metric("Network cycle stock",f"{current['cycle_inventory_units']:,.1f} units")
    c.metric("Weekly holding cost",f"${current['inventory_holding_cost']:,.0f}")
    inv_df=pd.DataFrame(current["center_results"])
    stock_cols=["Center","Weather","Mean replenishment lead days","SD replenishment lead days","Safety stock units","Cycle inventory units","Storage capacity","Storage utilization %","Weekly holding $"]
    st.dataframe(inv_df[stock_cols],hide_index=True,use_container_width=True)
    st.download_button("Download inventory analysis",inv_df[stock_cols].to_csv(index=False),"inventory_buffers.csv","text/csv")
    st.latex(r"SS_i = z\frac{q_i}{7}\sqrt{L_i \cdot CV_i^2 + \sigma_{L,i}^2}")
    st.caption("q = weekly allocated units, L = mean inbound replenishment days, CV = assumed daily demand standard deviation / mean, σL = lead-time standard deviation (days); z is the chosen normal quantile. The model assumes independent demand and lead-time variation, daily demand standard deviation proportional to assigned volume, and no stochastic demand pooling between markets.")

with build_tab:
    st.subheader("Facility operating and capital decisions")
    st.markdown("The model may close existing DCs, or construct candidate DCs if their cost and service benefits justify the one-time investment within the budget. Candidate construction costs are converted to **weekly equivalents** for comparison with recurring costs.")
    fac_df=pd.DataFrame(current["center_results"])
    st.dataframe(fac_df[["Center","Type","Open","Built","Allocated","Effective throughput capacity","Throughput utilization %","Storage utilization %","Weather"]],hide_index=True,use_container_width=True)
    st.write("**New facilities selected:** "+(", ".join(current["built"]) if current["built"] else "None in this scenario"))
    col1,col2,col3=st.columns(3)
    col1.metric("One-time construction selected",f"${current['construction_capex']:,.0f}")
    col2.metric("Annualized (weekly-equivalent) construction cost",f"${current['breakdown']['Construction amortization']:,.0f}/wk")
    col3.metric("Weekly facility operations",f"${current['breakdown']['Facility operating']:,.0f}/wk")
    st.caption("Candidate construction is instantaneous within this planning model. It does not include project lead time, staged capacity activation, taxes, financing, land acquisition, NPV discounting, or multi-year inventory planning.")

with scenario_tab:
    st.subheader("Scenario comparisons · separately reoptimized")
    st.caption("Save the current assumptions to keep a comparison during this browser session. Built-in benchmarks are solved from the ORIGINAL fictional dataset and not combined with your custom changes.")
    if "saved_runs_v2" not in st.session_state: st.session_state.saved_runs_v2=[]
    n1,n2,n3=st.columns([2,1,1])
    with n1:
        scenario_name=st.text_input("Scenario label",value="My network scenario",max_chars=70)
    with n2:
        st.write(" ")
        if st.button("Save current result",use_container_width=True):
            if not scenario_name.strip(): st.error("Enter a scenario label before saving")
            else:
                r={"Scenario":scenario_name.strip(),"Weekly cost $":round(current["total_cost"],2),"Delivered":current["shipped"],"Unserved":current["unserved"],"Service %":round(current["service_pct"],2),"Trucks":current["trucks"],"Safety stock":round(current["safety_stock_units"],1),"Facilities built":", ".join(current["built"]) or "None"}
                st.session_state.saved_runs_v2.append(r)
                st.success("Scenario saved in this session")
    with n3:
        st.write(" ")
        if st.button("Clear saved results",use_container_width=True):st.session_state.saved_runs_v2=[]
    run_presets=st.checkbox("Compute 8 built-in stress-test scenarios",value=False,help="Solving all presets takes extra computation; their results are cached")
    @st.cache_data(show_spinner=False)
    def preset_results(): return benchmark_scenarios()
    original={"Scenario":"Original baseline","Weekly cost $":round(baseline["total_cost"],2),"Delivered":baseline["shipped"],"Unserved":baseline["unserved"],"Service %":round(baseline["service_pct"],2),"Trucks":baseline["trucks"],"Safety stock":round(baseline["safety_stock_units"],1),"Facilities built":", ".join(baseline["built"]) or "None"}
    now={"Scenario":"Current live configuration","Weekly cost $":round(current["total_cost"],2),"Delivered":current["shipped"],"Unserved":current["unserved"],"Service %":round(current["service_pct"],2),"Trucks":current["trucks"],"Safety stock":round(current["safety_stock_units"],1),"Facilities built":", ".join(current["built"]) or "None"}
    rows=[original, now]+st.session_state.saved_runs_v2
    if run_presets:
        with st.spinner("Optimizing all stress tests..."):
            rows.extend(preset_results()[1:])
    comparisons=pd.DataFrame(rows)
    comparisons["Cost change vs baseline $"]=comparisons["Weekly cost $"]-original["Weekly cost $"]
    st.dataframe(comparisons,hide_index=True,use_container_width=True)
    fig=px.bar(comparisons,x="Scenario",y="Weekly cost $",color="Unserved",title="Optimized cost across scenarios",text="Weekly cost $",color_continuous_scale="Sunset")
    fig.update_traces(texttemplate="$%{text:,.0f}",textposition="outside")
    fig.update_layout(height=410,margin=dict(t=55,b=70,l=5,r=10),xaxis_tickangle=-25)
    st.plotly_chart(fig,use_container_width=True)
    st.download_button("Download scenario comparison (CSV)",comparisons.to_csv(index=False),"network_scenario_comparison.csv","text/csv")
    st.caption("Saved scenarios persist only while this Streamlit session remains active; export the CSV to keep them.")

with model_tab:
    st.subheader("Optimization formulation and interpretation")
    st.markdown(r"""
This is a **single-period mixed-integer linear program (MILP)**. It joins a capacitated facility-location problem, capital budgeting, fixed-charge truck dispatching, market demand allocation, and linear inventory buffers. HiGHS solves it through `scipy.optimize.milp`.

**Decisions:** $x^T_{ij}$ = integer truckload units on lane $i\to j$; $x^S_{ij}$ = integer spot units; $n_{ij}$ = integer trucks dispatched; $y_i\in\{0,1\}$ = DC operates; $b_i\in\{0,1\}$ = new candidate constructed; $u_j$ = integer market demand shortfall.

**Objective:** minimize spot transport charges + full-truck dispatch charges + handling + unit-mile carbon charges + safety/cycle stock holding + operating costs + weekly-equivalent construction costs + market shortage penalties.

**Core constraints**

$$\sum_i(x^T_{ij}+x^S_{ij})+u_j=D_j\qquad\forall j$$

$$\sum_j(x^T_{ij}+x^S_{ij})\le C_i^{weather}y_i\qquad\forall i$$

$$\sum_j(x^T_{ij}+x^S_{ij}) \cdot \big(\alpha_i+R_i/14\big)\le S_i y_i\qquad\forall i$$

$$x^T_{ij}\le Qn_{ij}\qquad\forall i,j$$

$$x^T_{ij}\ge (f/100) Qn_{ij}\qquad\forall i,j\quad\text{(if minimum truck fill enabled)}$$

$$y_i\le b_i\qquad\text{for proposed facilities}$$

$$\sum_{i\in Candidate} B_i b_i\le B^{budget},\quad \sum_{i\in Candidate}b_i\le N^{max}$$

**Inventory (linear under the model assumptions)**

$$\alpha_i=\frac{z}{7}\sqrt{L_i CV_i^2+\sigma_{L,i}^2},\quad SS_i=\alpha_i q_i,\quad I_i^{cycle}=\frac{R_i}{14}q_i$$

$q_i$ = weekly shipped volume from facility $i$, $L_i$ = replenishment lead time in days, $CV_i$ = CV of daily demand, $\sigma_{L,i}$ = lead-time standard deviation in days, $R_i$ = replenishment cycle in days. Although the safety stock *coefficient* contains a square root, it is calculated from user-entered parameters before optimization and is constant for each run, making the optimization linear. A target cycle-service probability converts to normal $z$ via inverse CDF.

**Disruptions:** Center weather reduces throughput, raises outgoing freight, and raises replenishment lead-time mean/variation. Market weather raises inbound freight and estimated delivery days. Lane overrides can ban specific routes, increase costs, or restrict truck capacity. A route distance or transit cap removes ineligible lanes.

**Solver:** SciPy MILP with the HiGHS engine. Shipments, trucks, and unmet units are nonnegative integers; site operating and construction choices are binary. The reported cost is a result for a representative week, not an NPV or a real carrier quote.
""")
    st.markdown("**Important limitations:** No real-time weather forecasts, no probabilistic simulation of storms, no inbound supplier-routing optimization, no multi-stop truck routes, no congestion/waiting times, no inventory backorders over multiple weeks, and no explicit risk pooling across customer markets. The model assumes demand and lead times are independent for the safety stock formula, stationary within a week, and uses synthetic road-mile proxies.")
    st.markdown("For a full explanation of every input, worked examples, units, model derivation, and test scenarios, open **USER_GUIDE.md** in this project's folder.")

st.divider()
st.caption("Advanced portfolio demo · Python / Streamlit / SciPy HiGHS MILP / Plotly · Synthetic data only · Original network preserved as a downloadable backup")
