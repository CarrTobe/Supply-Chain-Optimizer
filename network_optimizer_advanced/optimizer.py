"""Extended, transparent MILP for a fictional US distribution network.

All data are synthetic. One planning period = a representative week. Units are
standardized shipment-equivalents; truck capacity is expressed in those units.

Optimization variables: integer TL/spot units, integer trucks and shortages;
binary operating/build choices. Safety and cycle inventory are deterministic,
linear functions of assigned mean outbound flow under stated CV assumptions.
"""
from __future__ import annotations

from copy import deepcopy
from math import asin, cos, floor, radians, sin, sqrt
from typing import Any

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix
from scipy.stats import norm

WEATHER = {
    "None": {"capacity": 1.0, "premium": 0.0, "lead_scale": 1.0, "lead_sd_add": 0.0, "transit_add": 0.0},
    "Mild": {"capacity": 0.92, "premium": 0.08, "lead_scale": 1.1, "lead_sd_add": 0.25, "transit_add": 0.25},
    "Moderate": {"capacity": 0.75, "premium": 0.20, "lead_scale": 1.25, "lead_sd_add": 0.75, "transit_add": 0.75},
    "Severe": {"capacity": 0.55, "premium": 0.40, "lead_scale": 1.5, "lead_sd_add": 1.5, "transit_add": 1.5},
    "Extreme": {"capacity": 0.25, "premium": 0.75, "lead_scale": 2.0, "lead_sd_add": 3.0, "transit_add": 3.0},
}

CENTERS = [
    {"Center": "Chicago", "Type": "Existing", "Latitude": 41.8781, "Longitude": -87.6298, "Capacity": 2900, "Storage capacity": 2200, "Handling $/unit": 1.90, "Fixed $/week": 2400, "Build cost $": 0, "Lead days": 6, "Lead SD days": 1.2, "Demand CV": 0.25, "Cycle days": 4, "Holding $/unit/week": 0.26, "Available": True, "Weather": "None"},
    {"Center": "Dallas", "Type": "Existing", "Latitude": 32.7767, "Longitude": -96.7970, "Capacity": 3150, "Storage capacity": 2600, "Handling $/unit": 1.60, "Fixed $/week": 2200, "Build cost $": 0, "Lead days": 5, "Lead SD days": 1.0, "Demand CV": 0.23, "Cycle days": 4, "Holding $/unit/week": 0.23, "Available": True, "Weather": "None"},
    {"Center": "Atlanta", "Type": "Existing", "Latitude": 33.7490, "Longitude": -84.3880, "Capacity": 2700, "Storage capacity": 2100, "Handling $/unit": 1.70, "Fixed $/week": 2000, "Build cost $": 0, "Lead days": 5, "Lead SD days": 1.3, "Demand CV": 0.27, "Cycle days": 4, "Holding $/unit/week": 0.24, "Available": True, "Weather": "None"},
    {"Center": "Los Angeles", "Type": "Existing", "Latitude": 34.0522, "Longitude": -118.2437, "Capacity": 2350, "Storage capacity": 1900, "Handling $/unit": 2.15, "Fixed $/week": 2800, "Build cost $": 0, "Lead days": 8, "Lead SD days": 1.8, "Demand CV": 0.29, "Cycle days": 4, "Holding $/unit/week": 0.31, "Available": True, "Weather": "None"},
    {"Center": "Newark", "Type": "Existing", "Latitude": 40.7357, "Longitude": -74.1724, "Capacity": 2800, "Storage capacity": 2100, "Handling $/unit": 2.35, "Fixed $/week": 2900, "Build cost $": 0, "Lead days": 7, "Lead SD days": 1.5, "Demand CV": 0.28, "Cycle days": 4, "Holding $/unit/week": 0.30, "Available": True, "Weather": "None"},
    {"Center": "Columbus (proposed)", "Type": "Candidate", "Latitude": 39.9612, "Longitude": -82.9988, "Capacity": 2400, "Storage capacity": 1950, "Handling $/unit": 1.85, "Fixed $/week": 2600, "Build cost $": 1450000, "Lead days": 5, "Lead SD days": 1.1, "Demand CV": 0.25, "Cycle days": 4, "Holding $/unit/week": 0.25, "Available": True, "Weather": "None"},
    {"Center": "Denver (proposed)", "Type": "Candidate", "Latitude": 39.7392, "Longitude": -104.9903, "Capacity": 2400, "Storage capacity": 1950, "Handling $/unit": 1.90, "Fixed $/week": 2500, "Build cost $": 1800000, "Lead days": 6, "Lead SD days": 1.4, "Demand CV": 0.26, "Cycle days": 4, "Holding $/unit/week": 0.26, "Available": True, "Weather": "None"},
    {"Center": "Memphis (proposed)", "Type": "Candidate", "Latitude": 35.1495, "Longitude": -90.0490, "Capacity": 2400, "Storage capacity": 1950, "Handling $/unit": 1.65, "Fixed $/week": 2300, "Build cost $": 1250000, "Lead days": 5, "Lead SD days": 1.1, "Demand CV": 0.25, "Cycle days": 4, "Holding $/unit/week": 0.24, "Available": True, "Weather": "None"},
]
MARKETS = [
    {"Market": "Northeast / Boston", "Latitude": 42.3601, "Longitude": -71.0589, "Demand": 1700, "Weather": "None"},
    {"Market": "Mid-Atlantic / DC", "Latitude": 38.9072, "Longitude": -77.0369, "Demand": 1600, "Weather": "None"},
    {"Market": "Southeast / Miami", "Latitude": 25.7617, "Longitude": -80.1918, "Demand": 2000, "Weather": "None"},
    {"Market": "Midwest / Detroit", "Latitude": 42.3314, "Longitude": -83.0458, "Demand": 2100, "Weather": "None"},
    {"Market": "South Central / Houston", "Latitude": 29.7604, "Longitude": -95.3698, "Demand": 1900, "Weather": "None"},
    {"Market": "West / Phoenix", "Latitude": 33.4484, "Longitude": -112.0740, "Demand": 2200, "Weather": "None"},
]

DEFAULT_SETTINGS: dict[str, Any] = {
    "demand_change_pct": 0.0,
    "weather_intensity": 1.0,
    "freight_change_pct": 0.0,
    "road_distance_factor": 1.20,
    "max_road_miles": None,
    "max_transit_days": None,
    "avg_drive_miles_per_day": 500.0,
    "ltl_base_per_unit": 4.50,
    "ltl_per_mile_per_unit": 0.014,
    "truck_capacity": 250,
    "truck_dispatch_cost": 210.0,
    "truck_cost_per_mile": 2.20,
    "min_truck_fill_pct": 0.0,
    "truckload_enabled": True,
    "spot_enabled": True,
    "safety_stock_enabled": True,
    "target_service_pct": 95.0,
    "carbon_price_per_tonne": 35.0,
    "co2_tonnes_per_unit_mile": 0.00014,
    "co2_tonnes_per_truck_mile": 0.00150,
    "unserved_penalty": 250.0,
    "minimum_fulfillment_pct": 0.0,
    "construction_enabled": True,
    "construction_budget": 4_000_000.0,
    "max_new_facilities": 2,
    "investment_years": 5.0,
    "time_limit_seconds": 20.0,
    "relative_gap": 0.005,
}


def defaults() -> tuple[list[dict], list[dict]]:
    return deepcopy(CENTERS), deepcopy(MARKETS)


def default_settings() -> dict[str, Any]:
    return deepcopy(DEFAULT_SETTINGS)


def default_lanes(centers: list[dict], markets: list[dict]) -> list[dict]:
    return [
        {"Center": c["Center"], "Market": m["Market"], "Blocked": False,
         "Road override miles": None, "Extra freight %": 0.0, "Extra transit days": 0.0, "Max trucks/week": None}
        for c in centers for m in markets
    ]


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    a = sin((lat2-lat1)/2)**2 + cos(lat1)*cos(lat2)*sin((lon2-lon1)/2)**2
    return 3958.8 * 2 * asin(min(1.0, sqrt(max(0.0, a))))


def _finite_positive(value: Any, label: str, allow_zero: bool=True) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a number") from exc
    if not np.isfinite(number) or (number < 0 if allow_zero else number <= 0):
        raise ValueError(f"{label} must be {'nonnegative' if allow_zero else 'positive'} and finite")
    return number


def _weather_effect(level: str, intensity: float) -> dict[str, float]:
    """Scale severity continuously: intensity 0 = no disruption, 1 = preset."""
    w = WEATHER[level]
    return {
        "capacity": max(0.0, 1.0 - intensity*(1.0-w["capacity"])),
        "premium": intensity*w["premium"],
        "lead_scale": 1.0+intensity*(w["lead_scale"]-1.0),
        "lead_sd_add": intensity*w["lead_sd_add"],
        "transit_add": intensity*w["transit_add"],
    }


def solve_network(
    centers: list[dict], markets: list[dict],
    settings: dict[str, Any] | None = None,
    lane_overrides: list[dict] | None = None,
) -> dict[str, Any]:
    """Solve 1-week capacitated facility location + construction + TL/LTL + stock MILP.

    Shortfall is allowed by default with a penalty. A hard minimum fulfillment
    percentage can make the model infeasible; this is reported, not hidden.
    """
    s = default_settings()
    if settings:
        unknown = set(settings)-set(s)
        if unknown:
            raise ValueError("Unknown settings: " + ", ".join(sorted(unknown)))
        s.update(settings)
    if not centers or not markets:
        raise ValueError("Add at least one distribution center and market")
    if len({c["Center"] for c in centers}) != len(centers) or len({m["Market"] for m in markets}) != len(markets):
        raise ValueError("Distribution center and market names must be unique")

    _finite_positive(s["weather_intensity"], "weather_intensity")
    for key in ("demand_change_pct", "freight_change_pct"):
        if not np.isfinite(float(s[key])) or float(s[key]) <= -100:
            raise ValueError(f"{key} must be greater than -100%")
    for key in ("target_service_pct", "minimum_fulfillment_pct", "min_truck_fill_pct"):
        _finite_positive(s[key], key)
    if not 50 <= float(s["target_service_pct"]) < 100:
        raise ValueError("Target service must be between 50% and less than 100%")
    if float(s["minimum_fulfillment_pct"]) > 100 or float(s["min_truck_fill_pct"]) > 100:
        raise ValueError("Service and truck minimum percentages cannot exceed 100")
    for key in ("road_distance_factor", "avg_drive_miles_per_day", "truck_capacity", "investment_years", "unserved_penalty", "time_limit_seconds"):
        _finite_positive(s[key], key, allow_zero=False)
    for key in ("ltl_base_per_unit", "ltl_per_mile_per_unit", "truck_dispatch_cost", "truck_cost_per_mile", "carbon_price_per_tonne", "co2_tonnes_per_unit_mile", "co2_tonnes_per_truck_mile", "construction_budget", "max_new_facilities", "relative_gap"):
        _finite_positive(s[key], key)
    for key in ("max_road_miles", "max_transit_days"):
        if s[key] is not None:
            _finite_positive(s[key], key, allow_zero=False)
    if not s["truckload_enabled"] and not s["spot_enabled"]:
        raise ValueError("Enable truckload or spot shipments (at least one shipping mode)")
    if int(s["truck_capacity"]) != s["truck_capacity"]:
        raise ValueError("Truck capacity must be a whole number")
    if int(s["max_new_facilities"]) != s["max_new_facilities"]:
        raise ValueError("Max new facilities must be a whole number")

    dc_names = [c["Center"] for c in centers]
    mk_names = [m["Market"] for m in markets]
    nc, nm = len(centers), len(markets)
    for c in centers:
        if c["Type"] not in ("Existing", "Candidate"):
            raise ValueError(f"{c['Center']}: Type must be Existing or Candidate")
        if c["Weather"] not in WEATHER:
            raise ValueError(f"{c['Center']}: unknown weather severity")
        for field in ("Capacity", "Storage capacity", "Handling $/unit", "Fixed $/week", "Build cost $", "Lead days", "Lead SD days", "Demand CV", "Cycle days", "Holding $/unit/week"):
            _finite_positive(c[field], f"{c['Center']}: {field}")
        if not -90 <= float(c["Latitude"]) <= 90 or not -180 <= float(c["Longitude"]) <= 180:
            raise ValueError(f"{c['Center']}: invalid coordinates")
    for m in markets:
        _finite_positive(m["Demand"], f"{m['Market']}: Demand")
        if m["Weather"] not in WEATHER:
            raise ValueError(f"{m['Market']}: unknown weather severity")
        if not -90 <= float(m["Latitude"]) <= 90 or not -180 <= float(m["Longitude"]) <= 180:
            raise ValueError(f"{m['Market']}: invalid coordinates")

    overrides = {}
    for lane in lane_overrides or []:
        key = (str(lane["Center"]), str(lane["Market"]))
        if key in overrides:
            raise ValueError(f"Duplicate lane override: {key}")
        overrides[key] = lane
    if set(overrides)-{(a,b) for a in dc_names for b in mk_names}:
        raise ValueError("A lane override references a center or market not in the active network")

    total_demand_per_market = np.array([int(round(float(m["Demand"])*(1+float(s["demand_change_pct"])/100))) for m in markets], dtype=int)
    total_demand = int(total_demand_per_market.sum())
    capacity = np.array([floor(float(c["Capacity"])*_weather_effect(c["Weather"],float(s["weather_intensity"]))["capacity"]) if c["Available"] else 0 for c in centers], dtype=int)
    inventory_coeff = []
    center_stock_data = []
    z = float(norm.ppf(float(s["target_service_pct"])/100))
    for i,c in enumerate(centers):
        w = _weather_effect(c["Weather"],float(s["weather_intensity"]))
        lead_mean = float(c["Lead days"])*w["lead_scale"]
        lead_sd = float(c["Lead SD days"])+w["lead_sd_add"]
        cv = float(c["Demand CV"])
        # Daily mean demand q_i / 7; std of daily demand = CV * q_i / 7.
        # SS = z*(q_i/7)*sqrt(L_i*CV_i**2 + LeadSD_i**2).
        ss_factor = z/7 * sqrt(lead_mean*cv**2+lead_sd**2) if s["safety_stock_enabled"] else 0.0
        cycle_factor = float(c["Cycle days"])/14.0
        inventory_coeff.append(ss_factor+cycle_factor)
        center_stock_data.append({"Mean replenishment lead days": lead_mean, "SD replenishment lead days": lead_sd, "Safety stock units / weekly shipped unit": ss_factor, "Cycle inventory units / weekly shipped unit": cycle_factor})

    # Variables, in this order: TL units, spot/LTL units, truck dispatch count,
    # operating binary, candidate construction binary, unserved units.
    size = nc*nm
    start_tl, start_spot, start_truck = 0, size, size*2
    start_open = size*3
    candidates = [i for i,c in enumerate(centers) if c["Type"] == "Candidate"]
    cand_idx = {i:k for k,i in enumerate(candidates)}
    start_build = start_open+nc
    start_short = start_build+len(candidates)
    nv = start_short+nm
    cost = np.zeros(nv, dtype=float)
    lower = np.zeros(nv)
    upper = np.full(nv, np.inf)
    integral = np.ones(nv, dtype=np.int8)  # integer TL/spot units, trucks, shortfall; binary facilities
    upper[start_open:start_open+nc] = 1
    upper[start_build:start_build+len(candidates)] = 1

    breakdown_components = {
        "Truckload freight": np.zeros(nv), "Spot freight": np.zeros(nv),
        "Weather / lane premium": np.zeros(nv), "Handling": np.zeros(nv),
        "Carbon charge": np.zeros(nv), "Inventory holding": np.zeros(nv),
        "Facility operating": np.zeros(nv), "Construction amortization": np.zeros(nv),
        "Unserved demand penalty": np.zeros(nv),
    }
    lane_info: dict[tuple[int,int],dict] = {}
    freight_factor = 1+float(s["freight_change_pct"])/100
    truck_capacity = int(s["truck_capacity"])
    for i,c in enumerate(centers):
        op = start_open+i
        breakdown_components["Facility operating"][op] = float(c["Fixed $/week"])
        if not c["Available"]:
            upper[op] = 0
        if i in cand_idx:
            build = start_build+cand_idx[i]
            upper[build] = 1 if s["construction_enabled"] and c["Available"] else 0
            upper[op] = upper[build]
            breakdown_components["Construction amortization"][build] = float(c["Build cost $"])/(52*float(s["investment_years"]))
        for j,m in enumerate(markets):
            k=i*nm+j
            tl,spot,trucks = start_tl+k, start_spot+k, start_truck+k
            ov=overrides.get((c["Center"],m["Market"]), {})
            override_miles = ov.get("Road override miles")
            if override_miles is None or str(override_miles).strip() == "":
                miles = haversine_miles(float(c["Latitude"]),float(c["Longitude"]),float(m["Latitude"]),float(m["Longitude"]))*float(s["road_distance_factor"])
            else:
                miles = _finite_positive(override_miles, f"{c['Center']} → {m['Market']} distance", allow_zero=False)
            extra_rate = _finite_positive(ov.get("Extra freight %", 0),"Extra lane freight %")/100
            extra_days = _finite_positive(ov.get("Extra transit days", 0),"Extra transit days")
            limit_trucks = ov.get("Max trucks/week")
            if limit_trucks is not None and str(limit_trucks).strip() != "":
                _finite_positive(limit_trucks, "Maximum weekly trucks")
                if int(limit_trucks) != float(limit_trucks):
                    raise ValueError("Max trucks/week must be a whole number")
                upper[trucks] = int(limit_trucks)
            outbound_days = 1 + miles/float(s["avg_drive_miles_per_day"]) + _weather_effect(c["Weather"],float(s["weather_intensity"]))["transit_add"] + _weather_effect(m["Weather"],float(s["weather_intensity"]))["transit_add"] + extra_days
            eligible = (not bool(ov.get("Blocked",False)))
            if s["max_road_miles"] is not None and miles>float(s["max_road_miles"])+1e-9:
                eligible = False
            if s["max_transit_days"] is not None and outbound_days>float(s["max_transit_days"])+1e-9:
                eligible = False
            if not eligible or not c["Available"]:
                upper[tl] = upper[spot] = upper[trucks] = 0
            elif not s["truckload_enabled"]:
                upper[tl] = upper[trucks] = 0
            elif not s["spot_enabled"]:
                upper[spot] = 0
            upper[trucks] = min(upper[trucks], max(0,int(capacity[i])))
            base_tl = (float(s["truck_dispatch_cost"])+float(s["truck_cost_per_mile"])*miles)*freight_factor
            base_spot = (float(s["ltl_base_per_unit"])+float(s["ltl_per_mile_per_unit"])*miles)*freight_factor
            premium = _weather_effect(c["Weather"],float(s["weather_intensity"]))["premium"]+_weather_effect(m["Weather"],float(s["weather_intensity"]))["premium"]+extra_rate
            handling = float(c["Handling $/unit"])
            carbon_spot = miles * float(s["co2_tonnes_per_unit_mile"]) * float(s["carbon_price_per_tonne"])
            carbon_truck = miles * float(s["co2_tonnes_per_truck_mile"]) * float(s["carbon_price_per_tonne"])
            holding = inventory_coeff[i]*float(c["Holding $/unit/week"])
            breakdown_components["Truckload freight"][trucks] = base_tl
            breakdown_components["Spot freight"][spot] = base_spot
            breakdown_components["Weather / lane premium"][trucks] = base_tl*premium
            breakdown_components["Weather / lane premium"][spot] = base_spot*premium
            breakdown_components["Carbon charge"][trucks] = carbon_truck
            breakdown_components["Carbon charge"][spot] = carbon_spot
            for idx in (tl,spot):
                breakdown_components["Handling"][idx] = handling
                breakdown_components["Inventory holding"][idx] = holding
            lane_info[(i,j)] = {"miles":miles,"transit_days":outbound_days,"eligible":eligible,
                                 "premium":premium,"base_tl":base_tl,"base_spot":base_spot,
                                 "handling":handling,"carbon_spot":carbon_spot,"carbon_truck":carbon_truck,"holding":holding}

    for j in range(nm):
        breakdown_components["Unserved demand penalty"][start_short+j]=float(s["unserved_penalty"])
    for values in breakdown_components.values():
        cost += values

    # Sparse linear system. Constraints: demand, weekly throughput, physical storage,
    # truck capacity, truck minimum fill, facility opening, candidate build link,
    # capital budget, max candidate builds, minimum network service.
    rows: list[tuple[dict[int,float], float, float]] = []
    def add(coeff: dict[int,float], low=-np.inf, high=np.inf):
        rows.append((coeff,float(low),float(high)))

    for j in range(nm):
        row = {start_short+j: 1.0}
        for i in range(nc):
            row[start_tl+i*nm+j] = 1.0
            row[start_spot+i*nm+j] = 1.0
        add(row, total_demand_per_market[j],total_demand_per_market[j])
    for i,c in enumerate(centers):
        throughput = {start_open+i: -int(capacity[i])}
        storage = {start_open+i: -float(c["Storage capacity"])}
        for j in range(nm):
            for start in (start_tl,start_spot):
                k = start+i*nm+j
                throughput[k] = 1.0
                storage[k] = inventory_coeff[i]
            lane=i*nm+j
            # Truck count is the common packing/consolidation decision for this lane.
            add({start_tl+lane:1, start_truck+lane:-truck_capacity}, high=0)
            add({start_truck+lane:1, start_tl+lane:-1}, high=0)  # No empty dispatched trucks
            if float(s["min_truck_fill_pct"])>0:
                add({start_tl+lane:-1, start_truck+lane:truck_capacity*float(s["min_truck_fill_pct"])/100},high=0)
        add(throughput,high=0)
        add(storage,high=0)
        if i in cand_idx:
            # A candidate facility cannot operate without a construction decision.
            add({start_open+i:1,start_build+cand_idx[i]:-1},high=0)
    if candidates:
        add({start_build+k:float(centers[i]["Build cost $"]) for i,k in cand_idx.items()},high=float(s["construction_budget"]))
        add({start_build+k:1 for k in range(len(candidates))},high=int(s["max_new_facilities"]))
    if float(s["minimum_fulfillment_pct"])>0:
        add({start_short+j:1 for j in range(nm)}, high=floor(total_demand*(1-float(s["minimum_fulfillment_pct"])/100)+1e-8))

    A=lil_matrix((len(rows),nv),dtype=float)
    lo=np.zeros(len(rows))
    hi=np.zeros(len(rows))
    for r,(coeff,lb,ub) in enumerate(rows):
        lo[r],hi[r]=lb,ub
        for k,val in coeff.items():
            if val:
                A[r,k]=val

    sol=milp(c=cost,integrality=integral,bounds=Bounds(lower,upper),constraints=LinearConstraint(A.tocsr(),lo,hi),options={"time_limit":float(s["time_limit_seconds"]),"mip_rel_gap":float(s["relative_gap"])})
    if sol.x is None:
        status = "Infeasible" if sol.status==2 else ("Time limit without a feasible solution" if sol.status==1 else "Solver error")
        raise RuntimeError(f"{status}: {sol.message}. Try loosening distance/transit limits, raising the service shortfall allowance, or allowing more capacity/builds.")
    if sol.status not in (0,1):
        raise RuntimeError("Solver could not certify a usable solution: "+str(sol.message))
    values=np.rint(sol.x).astype(np.int64)
    # Numeric solver tolerances: confirm all original constraints before accepting.
    if np.any(values<0) or np.any(values>upper+1e-5):
        raise RuntimeError("Solver result violates variable bounds")
    for coeff,lb,ub in rows:
        lhs=sum(float(values[k])*v for k,v in coeff.items())
        if lhs<lb-1e-4 or lhs>ub+1e-4:
            raise RuntimeError("Solver returned a numerically inconsistent integer solution")

    tl=values[start_tl:start_tl+size].reshape(nc,nm)
    spot=values[start_spot:start_spot+size].reshape(nc,nm)
    trucks=values[start_truck:start_truck+size].reshape(nc,nm)
    opened=values[start_open:start_open+nc]
    built=values[start_build:start_build+len(candidates)]
    unserved=values[start_short:start_short+nm]
    alloc=[]
    facility=[]
    market_rows=[]
    co2_tonnes=0.0
    weighted_miles=0.0
    stock_total=0.0
    cycle_total=0.0
    for i,c in enumerate(centers):
        shipped_i=int((tl[i]+spot[i]).sum())
        safety=shipped_i*center_stock_data[i]["Safety stock units / weekly shipped unit"]
        cycle=shipped_i*center_stock_data[i]["Cycle inventory units / weekly shipped unit"]
        stock_total+=safety
        cycle_total+=cycle
        facility.append({"Center":c["Center"],"Type":c["Type"],"Open":bool(opened[i]),
                         "Built":bool(built[cand_idx[i]]) if i in cand_idx else False,
                         "Effective throughput capacity":int(capacity[i]),"Allocated":shipped_i,
                         "Throughput utilization %":round(shipped_i/capacity[i]*100,1) if capacity[i] else 0.0,
                         "Safety stock units":round(safety,1),"Cycle inventory units":round(cycle,1),
                         "Storage capacity":float(c["Storage capacity"]),
                         "Storage utilization %":round((safety+cycle)/float(c["Storage capacity"])*100,1) if float(c["Storage capacity"]) else 0.0,
                         "Weekly holding $":round((safety+cycle)*float(c["Holding $/unit/week"]),2),
                         "Mean replenishment lead days":round(center_stock_data[i]["Mean replenishment lead days"],2),
                         "SD replenishment lead days":round(center_stock_data[i]["SD replenishment lead days"],2),
                         "Weather":c["Weather"]})
        for j,m in enumerate(markets):
            qty=int(tl[i,j]+spot[i,j]); n=int(trucks[i,j])
            if qty==0:
                continue
            lane=lane_info[(i,j)]
            co2=(n*lane["miles"]*float(s["co2_tonnes_per_truck_mile"])
                 +int(spot[i,j])*lane["miles"]*float(s["co2_tonnes_per_unit_mile"]))
            co2_tonnes+=co2
            weighted_miles+=qty*lane["miles"]
            truck_rate=lane["base_tl"]*(1+lane["premium"])
            spot_rate=lane["base_spot"]*(1+lane["premium"])
            alloc.append({"Center":c["Center"],"Market":m["Market"],"Units":qty,"Truckload units":int(tl[i,j]),"Spot units":int(spot[i,j]),
                          "Trucks dispatched":n,"Truck fill %":round(100*int(tl[i,j])/(n*truck_capacity),1) if n else 0.0,
                          "Road miles (proxy)":round(lane["miles"],1),"Outbound transit days":round(lane["transit_days"],1),
                          "Transport $":round(n*truck_rate+int(spot[i,j])*spot_rate,2),"Handling $":round(qty*lane["handling"],2),
                          "Carbon $":round(n*lane["carbon_truck"]+int(spot[i,j])*lane["carbon_spot"],2),"Holding $":round(qty*lane["holding"],2),
                          "CO2 tonnes":round(co2,2)})
    for j,m in enumerate(markets):
        delivered=int((tl[:,j]+spot[:,j]).sum())
        market_rows.append({"Market":m["Market"],"Demand":int(total_demand_per_market[j]),"Delivered":delivered,
                            "Unserved":int(unserved[j]),"Weather":m["Weather"]})
    breakdown={k:float(np.dot(v,values)) for k,v in breakdown_components.items()}
    total_cost=float(sum(breakdown.values()))
    delivered=int((tl+spot).sum())
    shortage=int(unserved.sum())
    built_names=[centers[i]["Center"] for i in candidates if built[cand_idx[i]]]
    capex=sum(float(centers[i]["Build cost $"]) for i in candidates if built[cand_idx[i]])
    if abs(float(np.dot(values,cost))-total_cost)>0.0001:
        raise RuntimeError("Cost breakdown does not match decision-variable objective")
    return {
        "total_cost":total_cost,"breakdown":breakdown,"demand":total_demand,"shipped":delivered,"unserved":shortage,
        "service_pct":100*delivered/total_demand if total_demand else 100.0,
        "cost_per_delivered":total_cost/delivered if delivered else None,
        "transport_cost":breakdown["Truckload freight"]+breakdown["Spot freight"]+breakdown["Weather / lane premium"],
        "inventory_holding_cost":breakdown["Inventory holding"],"safety_stock_units":stock_total,
        "cycle_inventory_units":cycle_total,"trucks":int(trucks.sum()),
        "avg_truck_fill_pct":100*int(tl.sum())/(int(trucks.sum())*truck_capacity) if int(trucks.sum()) else 0,
        "truckload_units":int(tl.sum()),"spot_units":int(spot.sum()),"built":built_names,"construction_capex":capex,
        "center_results":facility,"market_results":market_rows,"allocations":alloc,"co2_tonnes":co2_tonnes,
        "avg_road_miles":weighted_miles/delivered if delivered else 0,
        "solver_status":"Optimal (within configured MIP gap)" if sol.status==0 else "Feasible incumbent (time limit)",
        "mip_gap":float(getattr(sol,"mip_gap",np.nan)),
        "raw_objective":float(sol.fun),"lane_count":len([x for x in lane_info.values() if x["eligible"]]),
    }


def benchmark_scenarios() -> list[dict[str,Any]]:
    """Independent deterministic stress scenarios from the same synthetic base."""
    scenarios=[]
    presets=["Baseline","Demand +15%","Freight +20%","Midwest + Northeast storms","Southeast weather event","Newark closed","Truck rates +30%","Construction forbidden"]
    for title in presets:
        cs,ms=defaults()
        s=default_settings()
        if title=="Demand +15%": s["demand_change_pct"]=15
        if title=="Freight +20%": s["freight_change_pct"]=20
        if title=="Midwest + Northeast storms":
            for c in cs:
                if c["Center"] in ("Chicago","Newark"): c["Weather"]="Severe"
            ms[0]["Weather"]="Moderate"
        if title=="Southeast weather event":
            for c in cs:
                if c["Center"] in ("Atlanta","Memphis (proposed)"): c["Weather"]="Severe"
            ms[2]["Weather"]="Severe"
        if title=="Newark closed":
            next(c for c in cs if c["Center"]=="Newark")["Available"]=False
        if title=="Truck rates +30%": s["truck_cost_per_mile"]*=1.30
        if title=="Construction forbidden": s["construction_enabled"]=False
        result=solve_network(cs,ms,s)
        scenarios.append({"Scenario":title,"Weekly cost $":round(result["total_cost"],2),"Delivered":result["shipped"],
                          "Unserved":result["unserved"],"Service %":round(result["service_pct"],2),
                          "Trucks":result["trucks"],"Safety stock":round(result["safety_stock_units"],1),
                          "Facilities built":", ".join(result["built"]) or "None"})
    return scenarios
