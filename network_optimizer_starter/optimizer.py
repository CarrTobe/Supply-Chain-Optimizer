"""Transparent mixed-integer optimization for a fictional US distribution network.

All numbers are synthetic. The model finds weekly shipment allocations and DC openings
that minimize freight, handling, modeled weather surcharge, carbon fee, fixed facility
cost, and penalties for unfulfilled demand.
"""
from __future__ import annotations

from copy import deepcopy
from math import asin, cos, radians, sin, sqrt
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp


CENTERS = [
    {"Center": "Chicago", "Latitude": 41.8781, "Longitude": -87.6298, "Capacity": 2900, "Handling $/unit": 1.90, "Fixed $/week": 2400, "Available": True},
    {"Center": "Dallas", "Latitude": 32.7767, "Longitude": -96.7970, "Capacity": 3150, "Handling $/unit": 1.60, "Fixed $/week": 2200, "Available": True},
    {"Center": "Atlanta", "Latitude": 33.7490, "Longitude": -84.3880, "Capacity": 2700, "Handling $/unit": 1.70, "Fixed $/week": 2000, "Available": True},
    {"Center": "Los Angeles", "Latitude": 34.0522, "Longitude": -118.2437, "Capacity": 2350, "Handling $/unit": 2.15, "Fixed $/week": 2800, "Available": True},
    {"Center": "Newark", "Latitude": 40.7357, "Longitude": -74.1724, "Capacity": 2800, "Handling $/unit": 2.35, "Fixed $/week": 2900, "Available": True},
]
MARKETS = [
    {"Market": "Northeast / Boston", "Latitude": 42.3601, "Longitude": -71.0589, "Demand": 1700},
    {"Market": "Mid-Atlantic / DC", "Latitude": 38.9072, "Longitude": -77.0369, "Demand": 1600},
    {"Market": "Southeast / Miami", "Latitude": 25.7617, "Longitude": -80.1918, "Demand": 2000},
    {"Market": "Midwest / Detroit", "Latitude": 42.3314, "Longitude": -83.0458, "Demand": 2100},
    {"Market": "South Central / Houston", "Latitude": 29.7604, "Longitude": -95.3698, "Demand": 1900},
    {"Market": "West / Phoenix", "Latitude": 33.4484, "Longitude": -112.0740, "Demand": 2200},
]

# Transparent, intentionally simplified synthetic cost assumptions.
FREIGHT_BASE_PER_SHIPMENT = 4.50
FREIGHT_PER_ROAD_MILE = 0.014
ROAD_DISTANCE_FACTOR = 1.20
CO2_TONNES_PER_SHIPMENT_ROAD_MILE = 0.00014
UNSERVED_PENALTY_PER_SHIPMENT = 250.0
WEATHER_FACTORS = {"Normal": (1.0, 0.00), "Moderate disruption": (0.80, 0.18), "Severe disruption": (0.55, 0.40)}


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight-line great-circle distance in miles (before road-distance multiplier)."""
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 3958.8 * 2 * asin(min(1.0, sqrt(a)))


def defaults() -> tuple[list[dict], list[dict]]:
    return deepcopy(CENTERS), deepcopy(MARKETS)


def solve_network(
    centers: list[dict],
    markets: list[dict],
    demand_change_pct: float = 0,
    freight_change_pct: float = 0,
    weather_center: str = "None",
    weather_severity: str = "Normal",
    carbon_price_per_tonne: float = 35,
    max_road_miles: float | None = None,
    unserved_penalty: float = UNSERVED_PENALTY_PER_SHIPMENT,
) -> dict[str, Any]:
    """Solve the DC fixed-charge transportation problem with allowed shortfalls.

    Decision variables: x_ij >= 0 shipments DC i -> market j, y_i binary open/closed,
    u_j >= 0 units of demand not fulfilled.
    Objective = shipment variable costs + center fixed costs + shortfall penalties.
    Demand is satisfied exactly by shipments plus an explicit unserved-demand variable.
    """
    nc, nm = len(centers), len(markets)
    if nc == 0 or nm == 0:
        raise ValueError("At least one DC and customer market is required")
    if demand_change_pct <= -100 or freight_change_pct <= -100:
        raise ValueError("Demand and freight multipliers must be positive")
    if weather_severity not in WEATHER_FACTORS:
        raise ValueError("Unknown weather severity")
    if carbon_price_per_tonne < 0 or unserved_penalty <= 0:
        raise ValueError("Carbon price must be nonnegative; shortage penalty positive")

    d = np.array([int(round(max(0, float(m["Demand"])) * (1 + demand_change_pct / 100))) for m in markets])
    availability = [bool(c["Available"]) for c in centers]
    capacity = np.array([max(0, int(float(c["Capacity"]))) for c in centers])
    scale, extra_weather_freight = WEATHER_FACTORS[weather_severity]
    impacts = [(weather_center == c["Center"] and weather_severity != "Normal") for c in centers]
    effective_capacity = np.array([int(np.floor(capacity[i] * (scale if impacts[i] else 1))) for i in range(nc)])
    effective_capacity = effective_capacity * np.asarray(availability, dtype=int)

    size_x = nc * nm
    size_y = nc
    total_vars = size_x + size_y + nm
    costs = np.zeros(total_vars)
    lower = np.zeros(total_vars)
    upper = np.full(total_vars, np.inf)
    integer_mask = np.zeros(total_vars, dtype=int)
    lane_info: dict[tuple[int,int], dict] = {}

    for i, c in enumerate(centers):
        for j, m in enumerate(markets):
            idx = i * nm + j
            miles = haversine_miles(float(c["Latitude"]), float(c["Longitude"]), float(m["Latitude"]), float(m["Longitude"])) * ROAD_DISTANCE_FACTOR
            base_freight = (FREIGHT_BASE_PER_SHIPMENT + FREIGHT_PER_ROAD_MILE * miles) * (1 + freight_change_pct / 100)
            weather_extra = base_freight * extra_weather_freight if impacts[i] else 0.0
            handling = float(c["Handling $/unit"])
            emissions = miles * CO2_TONNES_PER_SHIPMENT_ROAD_MILE
            carbon = carbon_price_per_tonne * emissions
            costs[idx] = base_freight + weather_extra + handling + carbon
            if max_road_miles is not None and miles > max_road_miles:
                upper[idx] = 0.0
            lane_info[(i,j)] = {"road_miles": miles, "freight_unit": base_freight, "weather_unit": weather_extra, "handling_unit": handling, "carbon_unit": carbon, "emissions_unit": emissions, "unit_total": costs[idx]}
    for i, c in enumerate(centers):
        idx = size_x + i
        costs[idx] = float(c["Fixed $/week"])
        upper[idx] = 1.0 if availability[i] else 0.0
        integer_mask[idx] = 1
    for j in range(nm):
        costs[size_x + size_y + j] = unserved_penalty

    # Market demand equalities and center capacity inequalities.
    A = np.zeros((nm + nc, total_vars))
    lb = np.full(nm + nc, -np.inf)
    ub = np.empty(nm + nc)
    for j in range(nm):
        for i in range(nc):
            A[j, i * nm + j] = 1
        A[j, size_x + size_y + j] = 1
        lb[j], ub[j] = d[j], d[j]
    for i in range(nc):
        A[nm + i, i * nm:(i + 1) * nm] = 1
        A[nm + i, size_x + i] = -effective_capacity[i]
        ub[nm + i] = 0.0

    res = milp(c=costs, integrality=integer_mask, bounds=Bounds(lower, upper), constraints=LinearConstraint(A, lb, ub), options={"time_limit": 20, "mip_rel_gap": 0.00001})
    if res.x is None or res.status not in (0, 1):
        raise RuntimeError(f"Optimizer did not return a feasible solution: {res.message}")

    x = res.x[:size_x].reshape(nc, nm)
    opened = res.x[size_x:size_x + size_y]
    unserved = res.x[size_x + size_y:]
    allocations = []
    breakdown = {"Freight": 0.0, "Weather premium": 0.0, "Handling": 0.0, "Carbon charge": 0.0, "Fixed facilities": 0.0, "Unserved penalty": 0.0}
    emissions_total = 0.0
    road_distance_weighted = 0.0
    for i in range(nc):
        for j in range(nm):
            n = float(x[i, j])
            if n < 1e-5: continue
            lane = lane_info[(i,j)]
            for label, key in (("Freight", "freight_unit"), ("Weather premium", "weather_unit"), ("Handling", "handling_unit"), ("Carbon charge", "carbon_unit")):
                breakdown[label] += n * lane[key]
            emissions_total += n * lane["emissions_unit"]
            road_distance_weighted += n * lane["road_miles"]
            allocations.append({"Center": centers[i]["Center"], "Market": markets[j]["Market"], "Shipments": int(round(n)), "Road miles (proxy)": int(round(lane["road_miles"])), "Freight $": round(n * lane["freight_unit"], 2), "Weather $": round(n * lane["weather_unit"], 2), "Handling $": round(n * lane["handling_unit"], 2), "Carbon $": round(n * lane["carbon_unit"], 2), "Total variable $": round(n * lane["unit_total"], 2), "CO2 tonnes": round(n * lane["emissions_unit"], 2)})
        breakdown["Fixed facilities"] += round(opened[i]) * costs[size_x + i]
    breakdown["Unserved penalty"] = float(np.dot(unserved, np.full(nm, unserved_penalty)))
    total_cost = float(sum(breakdown.values()))
    shipped = int(round(x.sum()))
    shortfall = int(round(unserved.sum()))
    demand = int(d.sum())
    center_results = [{"Center": centers[i]["Center"], "Capacity": int(effective_capacity[i]), "Allocated": int(round(x[i].sum())), "Utilization %": round(100 * x[i].sum() / effective_capacity[i], 1) if effective_capacity[i] else 0.0, "Open": bool(opened[i] > 0.5)} for i in range(nc)]
    market_results = [{"Market": markets[j]["Market"], "Demand": int(d[j]), "Delivered": int(round(x[:,j].sum())), "Unserved": int(round(unserved[j]))} for j in range(nm)]
    return {"total_cost": total_cost, "breakdown": {k: float(v) for k, v in breakdown.items()}, "demand": demand, "shipped": shipped, "unserved": shortfall, "service_pct": (100 * shipped / demand if demand else 100.0), "cost_per_delivered": total_cost / shipped if shipped else None, "center_results": center_results, "market_results": market_results, "allocations": allocations, "co2_tonnes": emissions_total, "avg_road_miles": (road_distance_weighted / shipped if shipped else 0), "solver_status": "Optimal" if res.status == 0 else "Feasible (time limit)", "raw_objective": float(res.fun)}


def benchmark_scenarios() -> list[dict]:
    """Independent reruns from the same clean baseline dataset."""
    out = []
    presets = [
        ("Baseline", {}),
        ("Demand +15%", {"demand_change_pct": 15}),
        ("Freight +20%", {"freight_change_pct": 20}),
        ("Severe Atlanta weather", {"weather_center": "Atlanta", "weather_severity": "Severe disruption"}),
        ("Chicago capacity -40%", {"capacity_adjust": ("Chicago", 0.6)}),
        ("Newark unavailable", {"unavailable": "Newark"}),
    ]
    for name, settings in presets:
        centers, markets = defaults()
        settings = settings.copy()
        if "capacity_adjust" in settings:
            target, factor = settings.pop("capacity_adjust")
            for c in centers:
                if c["Center"] == target: c["Capacity"] = int(c["Capacity"] * factor)
        if "unavailable" in settings:
            target = settings.pop("unavailable")
            for c in centers:
                if c["Center"] == target: c["Available"] = False
        r = solve_network(centers, markets, **settings)
        out.append({"Scenario": name, "Cost $/week": round(r["total_cost"]), "Delivered": r["shipped"], "Unserved": r["unserved"], "Service %": round(r["service_pct"], 1), "CO2 tonnes": round(r["co2_tonnes"], 1)})
    return out
