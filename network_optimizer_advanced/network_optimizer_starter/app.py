"""Supply Chain Network Optimization & Risk Simulation | Streamlit portfolio demo.
Run with: python -m streamlit run app.py
"""
from __future__ import annotations

import io
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from optimizer import MARKETS, CENTERS, benchmark_scenarios, defaults, solve_network

st.set_page_config(page_title="Supply Chain Network Optimizer", page_icon="🚚", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
.block-container {padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1350px;}
.hero {background:linear-gradient(110deg,#10283e,#155568);border-radius:16px;padding:22px 28px;color:white;margin-bottom:22px}
.hero h1 {margin:0 0 5px 0;font-size:2.0rem; color:white;}
.hero p {margin:0;color:#cfebf1;font-size:0.98rem;}
.mini-note {color:#516578;font-size:0.86rem;}
[data-testid="stMetric"] {background:#f2f7f8; padding:16px 18px; border-radius:12px; border:1px solid #e2eaef;}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="hero"><h1>Supply Chain Network Optimizer</h1><p>Optimize freight, facility utilization, weather risk, and service levels across a simulated U.S. distribution network.</p></div>', unsafe_allow_html=True)

with st.sidebar:
    st.header("Scenario controls")
    st.caption("Every adjustment reruns the mixed-integer solver automatically.")
    demand_change = st.slider("Overall market demand change", -30, 40, 0, 5, format="%d%%", help="Applied to edited market demand numbers")
    freight_change = st.slider("Freight rate change", -20, 50, 0, 5, format="%d%%")
    weather_severity = st.selectbox("Weather severity", ["Normal", "Moderate disruption", "Severe disruption"])
    weather_center = st.selectbox("Weather-affected facility", ["None"] + [c["Center"] for c in CENTERS], index=0, disabled=(weather_severity == "Normal"))
    carbon_price = st.slider("Carbon charge ($/tonne CO₂)", 0, 150, 35, 5)
    max_lane = st.selectbox("Maximum route distance (proxy)", ["No limit", "1,000 miles", "1,600 miles", "2,500 miles"], index=0, help="Optional service-region constraint; may cause unmet demand")
    lane_cap = {"No limit": None, "1,000 miles": 1000, "1,600 miles": 1600, "2,500 miles": 2500}[max_lane]
    st.divider()
    st.caption("All demands, prices, distances, risk factors, and facility capacities are illustrative—not company or live weather data.")

base_centers, base_markets = defaults()
with st.expander("✏️ Edit distribution centers and customer demand", expanded=False):
    st.markdown("Adjust **Capacity**, **Handling $/unit**, **Fixed $/week**, and **Available** for each facility. Market **Demand** is independently editable. Facility latitude and longitude are locked to keep route comparisons consistent.")
    left_edit, right_edit = st.columns([1.35, 1])
    with left_edit:
        st.markdown("**Distribution centers**")
        centers_df = st.data_editor(
            pd.DataFrame(base_centers), key="dc_editor", hide_index=True, use_container_width=True, num_rows="fixed",
            disabled=["Center", "Latitude", "Longitude"],
            column_config={"Capacity": st.column_config.NumberColumn("Capacity", min_value=0, step=50), "Handling $/unit": st.column_config.NumberColumn("Handling $/unit", min_value=0.0, format="$%.2f"), "Fixed $/week": st.column_config.NumberColumn("Fixed $/week", min_value=0.0, format="$%.0f"), "Available": st.column_config.CheckboxColumn("Available")},
        )
    with right_edit:
        st.markdown("**Customer markets**")
        markets_df = st.data_editor(
            pd.DataFrame(base_markets), key="market_editor", hide_index=True, use_container_width=True, num_rows="fixed",
            disabled=["Market", "Latitude", "Longitude"],
            column_config={"Demand": st.column_config.NumberColumn("Weekly demand", min_value=0, step=50)},
        )
    st.caption("To simulate a complete closure, uncheck **Available**. Weather settings in the sidebar can also reduce usable capacity.")

centers = centers_df.to_dict("records")
markets = markets_df.to_dict("records")
try:
    current = solve_network(centers, markets, demand_change_pct=demand_change, freight_change_pct=freight_change,
                            weather_center=weather_center, weather_severity=weather_severity,
                            carbon_price_per_tonne=carbon_price, max_road_miles=lane_cap)
    baseline = solve_network(*defaults())
except (ValueError, RuntimeError, TypeError) as exc:
    st.error(f"Cannot solve this configuration: {exc}")
    st.stop()

status_line = "**✓ All demand fulfilled**" if current["unserved"] == 0 else f"**⚠ {current['unserved']:,} shipments unserved** — remaining capacity or lane eligibility is insufficient"
st.markdown(status_line)

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Optimized weekly cost", f"${current['total_cost']:,.0f}", f"${current['total_cost']-baseline['total_cost']:+,.0f} vs baseline", delta_color="inverse")
m2.metric("Shipments delivered", f"{current['shipped']:,}", f"{current['shipped']-baseline['shipped']:+,} vs baseline")
m3.metric("Demand fulfillment", f"{current['service_pct']:.1f}%", f"{current['unserved']:,} not served", delta_color="off")
m4.metric("Cost / delivered shipment", f"${current['cost_per_delivered']:,.2f}" if current["cost_per_delivered"] is not None else "N/A")
m5.metric("Modeled emissions", f"{current['co2_tonnes']:,.0f} t CO₂")
st.caption("Cost includes a $250 penalty per unserved shipment. When there are shortfalls, **cost per delivered shipment** includes this penalty and must not be interpreted as a freight-only unit rate. Baseline uses unedited mock inputs and default controls.")

@st.cache_data(show_spinner=False)
def default_scenarios() -> pd.DataFrame:
    return pd.DataFrame(benchmark_scenarios())


def network_map(result: dict, center_data: list[dict], market_data: list[dict]) -> go.Figure:
    fig = go.Figure()
    c_by_name = {x["Center"]: x for x in center_data}
    m_by_name = {x["Market"]: x for x in market_data}
    maximum = max((a["Shipments"] for a in result["allocations"]), default=1)
    for a in sorted(result["allocations"], key=lambda z: z["Shipments"]):
        c,m = c_by_name[a["Center"]], m_by_name[a["Market"]]
        qty=a["Shipments"]
        fig.add_trace(go.Scattergeo(
            lon=[c["Longitude"],m["Longitude"]], lat=[c["Latitude"],m["Latitude"]],
            mode="lines", line=dict(width=0.9+4.2*qty/maximum, color="rgba(31,134,161,0.55)"),
            hovertemplate=f"{a['Center']} → {a['Market']}<br>{qty:,} shipments/week<br>Road estimate: {a['Road miles (proxy)']:,} mi<extra></extra>", showlegend=False,
        ))
    cr = {c["Center"]: c for c in result["center_results"]}
    fig.add_trace(go.Scattergeo(
        lon=[c["Longitude"] for c in center_data],lat=[c["Latitude"] for c in center_data],
        mode="markers+text",text=[c["Center"] for c in center_data],textposition="top center",
        marker=dict(size=[12+cr[c["Center"]]["Allocated"]/280 for c in center_data],color=["#10445e" if cr[c["Center"]]["Open"] else "#aebbc5" for c in center_data],line=dict(color="white",width=1.5)),
        hovertext=[f"{c['Center']}<br>Allocated: {cr[c['Center']]['Allocated']:,}<br>Effective cap: {cr[c['Center']]['Capacity']:,}" for c in center_data],hoverinfo="text",name="Distribution centers",
    ))
    mr = {m["Market"]: m for m in result["market_results"]}
    fig.add_trace(go.Scattergeo(
        lon=[m["Longitude"] for m in market_data],lat=[m["Latitude"] for m in market_data],
        mode="markers",marker=dict(size=9,color="#F2A65A",line=dict(color="white",width=1)),
        hovertext=[f"{m['Market']}<br>Delivered: {mr[m['Market']]['Delivered']:,}<br>Demand: {mr[m['Market']]['Demand']:,}" for m in market_data],hoverinfo="text",name="Markets",
    ))
    fig.update_geos(scope="usa", projection_type="albers usa",showland=True,landcolor="#f4f8f8",showlakes=True,lakecolor="#ffffff",showcoastlines=False,showsubunits=True,subunitcolor="#d9e4e9",bgcolor="#ffffff")
    fig.update_layout(margin=dict(l=0,r=0,t=18,b=2),height=460,legend=dict(orientation="h",y=-.04),paper_bgcolor="white")
    return fig

overview_tab, map_tab, scenario_tab, model_tab = st.tabs(["📊 Overview", "🗺️ Routes & facilities", "🧪 Scenario lab", "📐 Model details"])
with overview_tab:
    l,r=st.columns([1.05,0.95],gap="large")
    with l:
        st.subheader("Where the network spends")
        b = current["breakdown"]
        cost_df=pd.DataFrame({"Component":list(b),"Weekly cost":list(b.values())})
        cost_df=cost_df[cost_df["Weekly cost"]>0]
        fig=px.pie(cost_df, names="Component",values="Weekly cost", hole=.57, color_discrete_sequence=px.colors.qualitative.Safe)
        fig.update_traces(textposition="outside",textinfo="percent+label")
        fig.update_layout(height=355, showlegend=False,margin=dict(t=15,b=30,l=15,r=15))
        st.plotly_chart(fig,use_container_width=True)
    with r:
        st.subheader("Distribution center utilization")
        util_df=pd.DataFrame(current["center_results"])
        fig=px.bar(util_df, x="Center",y=["Allocated","Capacity"], barmode="group",labels={"value":"Weekly shipments","variable":"Series"}, color_discrete_map={"Allocated":"#1387A2","Capacity":"#B9CDD7"})
        fig.update_layout(height=355,margin=dict(t=15,b=50,l=5,r=8), legend=dict(orientation="h",y=1.12))
        st.plotly_chart(fig,use_container_width=True)
    with st.container():
        st.subheader("Operational exceptions")
        blocked=[m for m in current["market_results"] if m["Unserved"]>0]
        if blocked:
            for m in blocked: st.warning(f"{m['Market']}: {m['Unserved']:,} of {m['Demand']:,} weekly shipments not served")
        else:
            st.success("Every market's simulated weekly demand is satisfied.")
        c1,c2=st.columns(2)
        c1.dataframe(util_df,hide_index=True,use_container_width=True)
        c2.dataframe(pd.DataFrame(current["market_results"]),hide_index=True,use_container_width=True)
with map_tab:
    st.subheader("Optimized shipment lanes")
    st.caption("Line width is proportional to assigned weekly shipment volume. Distances are great-circle estimates × 1.20, not actual driving routes.")
    st.plotly_chart(network_map(current,centers,markets),use_container_width=True)
    st.subheader("Shipment allocation table")
    a=pd.DataFrame(current["allocations"])
    if not a.empty:
        st.dataframe(a.sort_values("Shipments",ascending=False),hide_index=True,use_container_width=True)
        st.download_button("⬇ Export shipment allocation CSV",data=a.to_csv(index=False),file_name="optimized_shipments.csv",mime="text/csv")
    else: st.info("No shipments were allocated in this scenario.")
with scenario_tab:
    st.subheader("Prebuilt what-if comparisons")
    st.caption("Each preset is independently reoptimized from the unedited baseline dataset. These are not additive scenarios. Current custom inputs are shown separately.")
    scenarios=default_scenarios().copy()
    custom=pd.DataFrame([{"Scenario":"Current custom configuration","Cost $/week":round(current["total_cost"]),"Delivered":current["shipped"],"Unserved":current["unserved"],"Service %":round(current["service_pct"],1),"CO2 tonnes":round(current["co2_tonnes"],1)}])
    table=pd.concat([scenarios, custom],ignore_index=True)
    table["Cost change vs baseline $"] = table["Cost $/week"] - int(round(baseline["total_cost"]))
    fig=px.bar(table,x="Scenario",y="Cost $/week",color="Unserved",color_continuous_scale="Sunset",text="Cost $/week",title="Weekly optimized cost by scenario")
    fig.update_traces(texttemplate="$%{text:,.0f}",textposition="outside")
    fig.update_layout(height=420,xaxis_tickangle=-25,margin=dict(t=60,b=80,l=0,r=10),coloraxis_colorbar_title="Unserved")
    st.plotly_chart(fig,use_container_width=True)
    st.dataframe(table,hide_index=True,use_container_width=True)
    st.download_button("⬇ Export scenario comparison CSV",data=table.to_csv(index=False),file_name="scenario_comparison.csv",mime="text/csv")
    st.info("A lower total cost does not necessarily indicate a better plan if demand goes unserved. Consider service %, unserved penalties, and CO₂ together.")
with model_tab:
    st.subheader("Optimization method")
    st.markdown(r"""
**Decision variables**
- $x_{ij}$: weekly shipment quantity from distribution center $i$ to market $j$.
- $y_i \in \{0,1\}$: whether distribution center $i$ operates.
- $u_j \geq 0$: weekly market demand not served.

**Minimize total weekly cost**
$$\min \sum_{i,j} x_{ij}\,(f_{ij}+w_{ij}+h_i+k_{ij})+\sum_i F_i y_i+250\sum_j u_j$$

Where $f$ = distance-based freight, $w$ = modeled weather surcharge, $h$ = handling, $k$ = carbon charge, and $F$ = weekly DC operating cost.

**Subject to**
$$\sum_i x_{ij}+u_j=D_j\quad\forall j$$
$$\sum_j x_{ij}\leq C_i^\mathrm{effective}y_i\quad\forall i$$
$$x_{ij}\geq 0,\quad u_j\geq 0,\quad y_i\in\{0,1\}$$

An optional maximum-mile restriction can disable long routes. The **HiGHS mixed-integer solver** runs through SciPy `milp`. Shipment quantities are continuous in the mathematical formulation; network-flow structure yields integral allocations in these scenarios.
""")
    st.markdown("**Model assumptions and limitations**")
    st.markdown("""
- Data is **mock data** for portfolio and learning use; no external sources or real-time weather feeds.
- Weekly demand is deterministic except for the user-selected scenario; it is not a stochastic forecast.
- Highway miles are approximated as Haversine distance × 1.20; true routes and transit times are not computed.
- Weather can reduce affected DC capacity (20% moderate, 45% severe) and increase freight from that DC (18% moderate, 40% severe).
- Carbon emissions are approximated as 0.00014 metric tonnes per shipment-road-mile, multiplied by the carbon price.
- If capacity cannot cover demand, the solver explicitly reports unserved shipments at a hypothetical $250 penalty each.
- Inventory safety stock, lead time variability, truckload consolidation, and facility construction decisions are **not** in this starter version.
""")
    st.subheader("Technical status")
    st.write(f"Solver result: **{current['solver_status']}**. This scenario's computed weekly total: **${current['total_cost']:,.2f}**.")
    st.caption("Do not interpret the results as real-world freight quotes or achievable business savings.")

st.divider()
st.caption("Independent portfolio demonstration · Python · SciPy/HiGHS MILP · Streamlit · Plotly · Synthetic data")
