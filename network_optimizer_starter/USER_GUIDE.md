# Advanced Supply Chain Network Optimizer — User & Mathematical Guide

**Version 2.0 • November 2026**  
**Stack:** Python + Streamlit + SciPy/HiGHS (MILP) + Plotly  
**Unit of analysis:** one representative week; all sites and rates are **fictional**. The 11,500 weekly units are *standardized shipping units*, not guaranteed to be physical pallets or individual packages.

This is a decision-support **optimization** application, not a live logistics platform or an end-to-end stochastic simulation. Whenever you change the inputs, the solver finds the least-cost *feasible* network configuration within the selected solver tolerance.

## 1. Run or upgrade your copy

1. **Back up** your previous starter folder if you have personal edits or GitHub changes.
2. Extract `Supply_Chain_Network_Optimizer_Advanced.zip` and open the extracted `network_optimizer_advanced` folder.
3. Open Terminal in that folder (or use VS Code's integrated terminal).
4. On **Mac**, run:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

On **Windows PowerShell**:

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

To update an **existing** installation rather than create a separate folder, replace `app.py`, `optimizer.py`, `requirements.txt`, and `tests/test_optimizer.py`; add this guide. Then reinstall the requirements and restart Streamlit. Back up any customizations first.

The program typically opens at `http://localhost:8501`. Stop it with `Ctrl+C`. If a PowerShell policy blocks virtual environment activation, execute `.venv\Scripts\python.exe -m pip install -r requirements.txt` and `.venv\Scripts\python.exe -m streamlit run app.py` directly.

## 2. How to navigate

### A. Sidebar controls

The sidebar contains six collapsible sections. **Changing a number reruns the optimizer automatically**. Most numeric inputs allow typing an exact value or clicking increment controls; there are no fixed preselected distance bands. Some calculations may take seconds, particularly after expanding the network or making a difficult mixed-integer problem.

### B. Network inputs editor

Open **“Network inputs · edit sites, markets, weather, and individual routes”**. You can change many parameters by individual facility or market, including lead-time distributions and weather severity. You can add and delete sites/markets using the editor. New rows need all required numeric attributes and valid coordinates; missing values prevent optimization until completed.

The **Lane restrictions and overrides** tab contains one row for every distribution-center/market combination. The lane table automatically regenerates if you change site or market names or add/remove one (this can reset previous lane edits; export needed scenario outputs first). If you keep the same site/market names, lane edits remain in the active Streamlit session.

### C. Six result tabs

| Tab | What you learn |
| --- | --- |
| Network overview | Full cost breakdown, weekly throughput and capacity, unmet-demand exceptions |
| Route allocation | Map, actual allocations by center/market, truck counts, fill, spot units, per-route cost, outbound transit estimate, CSV download |
| Inventory & lead times | Safety/cycle stock per center, holding cost, storage capacity and utilization, weather-adjusted replenishment lead statistics |
| Facilities & construction | Which DCs are operating, which proposed sites were built, capex, operating expense and amortized weekly construction cost |
| Scenario lab | Current vs baseline, saved scenario outcomes, eight independent presets, CSV export |
| Model details | Summary mathematical formulation, variables, constraints, and limitations |

**Status banner:** If all demand is served, it says so. If shortfalls occur, it reports how many units are unserved. If hard constraints are infeasible, you see an error rather than a fabricated optimized result.

## 3. Sidebar control reference — what each changes

### Demand, freight & route limits

| Control | Default | Effect on optimization |
| --- | ---: | --- |
| Demand change (%) | 0%, 1% step | Multiplies each market's editable baseline demand by `1 + percentage/100`; rounded to integer units. Higher demand can exhaust DC throughput/storage, require more trucks or make construction beneficial. |
| Freight inflation / discount (%) | 0%, 1% step | Multiplies both the spot per-unit rate and per-truck dispatch rate by the same factor. May change freight mode, allocations, facility choice. |
| Road-distance multiplier | 1.20, 0.01 step | Approximate highway miles = great-circle miles × multiplier; does not affect routes with a manually entered mileage override. |
| Enforce maximum road miles | Off | Turns a lane eligibility constraint on or off. |
| Maximum route distance (miles) | 1,800 when enabled, 1-mile step | **Typed numerical limit**. If lane miles exceed the threshold, both truck and spot service on that lane are prohibited. Very small values can cause unmet demand. |
| Enforce maximum outbound transit days | Off | Makes estimated transit time a hard route eligibility limit. |
| Maximum transit days | 7.0, 0.1-day step | Prohibits lanes where proxy outbound time exceeds this threshold. Storm delay and manual route delay count. |
| Estimated driving miles/day | 500, 10-mile step | Used only to estimate outbound lane days `1 + miles / drive_rate + modeled delay`. This is not inbound replenishment lead time. |

### Multi-location weather event

| Control | Default | Effect |
| --- | --- | --- |
| Weather event severity | None | Choose None, Mild, Moderate, Severe, or Extreme. The preset maps to risk multipliers described in §5. |
| Affected distribution centers | None | **Multiselect** any number of original DCs; applies the selected event to all selected DCs simultaneously. Alternatively enter distinct `Weather` severities in the per-center table. |
| Affected customer markets | None | **Multiselect** multiple markets; raises costs and outbound transit delays on their incoming lanes. Independently assign distinct market weather severities using the market table. |
| Weather effect intensity (×) | 1.00, 0.05 step | Continuously scales weather effects: 0 = no impact; 1 = preset; 1.5 = 50% greater reductions/premiums/delays. This can be typed to hundredths. DC capacity is floored at zero. |

**DC weather** lowers usable throughput, raises outgoing freight, extends the **mean inbound replenishment lead time**, increases its standard deviation, and adds outbound delay. **Market weather** adds a destination-side freight surcharge and outbound travel delay, but does not itself reduce a DC's capacity. When both ends are impacted, their freight surcharges are **added**, not compounded. Changing multiple impacted locations can cause meaningful reallocation and candidate construction.

### Truckload consolidation & rates

| Control | Default | Effect |
| --- | ---: | --- |
| Allow full-truckload consolidation | On | Permits the solver to collect multiple shipping units **on the same DC-to-market lane** in one integer truck dispatch. |
| Allow individual / spot shipments | On | Permits shipping units without occupying the model's directly dispatched truckload count, billed per unit under a higher-variable-cost spot/LTL assumption. |
| Shipping units per truck | 250, 1-unit step | Capacity `Q` of a whole truck. Higher truck capacity can reduce trucks required, but units cannot be split into fractional trucks. |
| Fixed cost per truck ($) | $210, $5 step | One charge for every full-truckload dispatch; independent of how full the truck is. |
| Truck rate per mile ($) | $2.20, $0.05 step | Adds distance-proportional cost to each full-truckload dispatch. |
| Minimum truck fill (%) | 0, 1% step | If set to e.g. 85%, dispatched truckload units on **each lane** must be at least 85% of total dispatched truck capacity. Units may switch to spot instead. |
| Spot freight per unit, base ($) | $4.50, $0.10 step | Fixed variable cost per spot unit. |
| Spot freight per unit-mile ($) | $0.014, $0.001 step | Additional spot shipment cost per mile per shipping unit. |

**Important definition:** Consolidation here is **economies of scale for full truckloads on an individual origin–destination lane**. The model does not build milk-runs, vehicle routes with multiple drop-offs, depot tours, or pickup-and-delivery schedules. Spot/LTL units have their own aggregate freight and emission factors; the app does **not** count the unknown third-party LTL carrier's physical trucks.

### Inventory, service & emissions

| Control | Default | Effect |
| --- | --- | --- |
| Calculate and hold safety stock | On | Enables service-level-based safety buffer; when off, safety stock and its holding cost are 0, but cycle inventory remains. |
| Inventory cycle-service target (%) | 95.0, 0.1% step | Changes the z-value of the assumed Normal distribution. A higher target raises safety stock, holding cost, and storage consumption. Does **not** require that percentage of customer shipments be delivered. |
| Hard minimum demand fulfillment (%) | 0, 0.5% step | Optional hard cap on shortfall: the solver must serve at least this share of demand. At 100%, zero shortfall is required. Can make scenario **infeasible**. |
| Penalty per unserved unit ($) | $250, $5 step | Soft penalty for unmet demand in objective, regardless of hard fulfillment. It is a hypothetical proxy for lost sales/expedite impact, **not** actual revenue. |
| Carbon shadow price ($/tonne) | $35, $1 step | Converts estimated CO₂ emissions into an optimization cost; 0 makes carbon reporting informational only. |
| Spot CO₂ tonne / unit-mile | 0.00014, 0.00001 step | Proxy emissions from one spot-shipped unit moved one mile. |
| Truck CO₂ tonne / truck-mile | 0.00150, 0.0001 step | Proxy emissions from **one whole** full-truckload dispatch moved one mile. Full-truck carbon depends on trucks used, making consolidation visible in estimated emissions. |

### Construction & solver

| Control | Default | Effect |
| --- | --- | --- |
| Allow proposed DC construction | On | Allows binary build choices for site rows of `Type = Candidate`. If off, candidate sites cannot operate. |
| Total construction budget ($) | $4,000,000, $50,000 step | Hard **one-time capital** budget across all selected candidate sites. Distinct from construction's weekly equivalent cost. |
| Maximum new facilities | 2, 1-site step | Upper limit on the number of candidate DCs built. |
| Amortization / evaluation horizon (years) | 5, 0.25-year step | Translates construction price into a simple `price / (52 × years)` representative-week cost in the objective. This is not a discounted-cash-flow valuation. |
| Solver time limit (seconds) | 20, 1-second step | Time available to MILP solver. Very difficult cases can return feasible but not fully certified solutions, or report no incumbent. |
| Maximum relative solver gap (%) | 0.5%, 0.1% step | Allowed difference from MILP dual bound. Smaller is more rigorous, but can be slower. “Optimal” means **within this gap**, not necessarily exact mathematical optimum. |

### Distribution-center editor (individual parameters)

| Editable field | Impact |
| --- | --- |
| Center / Type | Name / `Existing` or `Candidate`. Existing DCs are constructed but may be opened/closed; candidates require binary build. |
| Latitude / Longitude | Map positions and geographic distance estimates. |
| Capacity | Maximum **outbound weekly throughput units** before weather adjustment. Not the same as storage. |
| Storage capacity | Maximum **inventory on hand**, counting cycle plus safety stock. Does not model detailed racking or SKU compatibility. |
| Handling $/unit | Handling costs on every outbound unit, whether truckload or spot. |
| Fixed $/week | Charged only if the facility operates. |
| Build cost $ | One-time capital cost used only for candidate construction choices. |
| Lead days | Mean **inbound replenishment** time used in the safety-stock formula, changed by weather. |
| Lead SD days | Variation (standard deviation) of inbound replenishment time, changed by weather. |
| Demand CV | Standard deviation / mean for one day of outbound demand at this facility. This stays fixed as volume reallocates. |
| Cycle days | Fixed modeled replenishment interval; average cycle stock = weekly assigned volume × cycle days / 14. |
| Holding $/unit/week | Weekly carrying charge applied to average cycle + safety stock. |
| Available | If unchecked, this site cannot operate or ship; no fixed cost or build price is paid. |
| Weather | Site-specific risk level. Overrides can be applied en masse by the sidebar event planner. |

**Market editor:** Modify the market name, coordinates, weekly demand, or market weather. You can add new markets. Unit demand is deterministic within each solved scenario, *except* for the separate variability assumption used to compute inventory buffers.

### Individual lane editor

| Field | Impact |
| --- | --- |
| Blocked | Prohibits **both** truckload and spot shipments on this DC–market lane. |
| Road override miles | Replaces the synthetic geographical distance for only that origin–destination pair. Blank means auto-distance. |
| Extra freight % | Adds an extra percentage surcharge for **both** transport modes on that lane, in addition to site and market weather. |
| Extra transit days | Adds to route transit time; if max transit enabled, it can make this lane illegal. |
| Max trucks/week | Limit on **full-truckload departures** on this lane. A blank cell means unlimited. This does not cap spot shipments; use `Blocked` for a full lane shutdown. |

## 4. Mathematical model: how the solver selects decisions

### Sets and indices

- `i ∈ I`: distribution centers, existing and candidates.
- `j ∈ J`: customer markets.
- `I_new ⊆ I`: candidate new DCs.

### Decision variables (integer/binary)

- `xT_ij ≥ 0` **integer**: units sent on the DC–market lane using direct truckload freight.
- `xS_ij ≥ 0` **integer**: units sent on the lane using per-unit spot freight.
- `n_ij ≥ 0` **integer**: direct trucks dispatched on the lane.
- `y_i ∈ {0,1}`: DC operating decision.
- `b_i ∈ {0,1}`: build a candidate facility (only candidates).
- `u_j ≥ 0` **integer**: demand units left unserved at market `j`.

The solver minimizes cost. This is a **mixed-integer linear program**: costs and constraints are linear in the decisions, while integer truck counts and binary openings/builds capture discrete decisions. The library `scipy.optimize.milp` calls HiGHS.

### Objective (total expected *modeled* cost in a representative week)

Let `q_i = Σ_j (xT_ij + xS_ij)` and lane miles be `m_ij`.

- Truck cost per dispatch before incident surcharges: `T_ij = (dispatch_cost + truck_rate × m_ij) × (1+freight_change)`.
- Spot cost per unit before incident surcharges: `P_ij = (spot_base + spot_mile_rate × m_ij) × (1+freight_change)`.
- Additional route surcharge: `r_ij = weather_surcharge_origin + weather_surcharge_destination + manual_lane_surcharge`.
- Holding coefficient: `H_i = holding_rate_i × (α_i + R_i/14)`, where `α_i` is safety units divided by weekly volume.
- Truck CO₂ per dispatch: `E^T_ij = m_ij × e_truck`; spot CO₂ per unit: `E^S_ij = m_ij × e_spot`.

Minimize:

```
Z = Σ(i,j) [ n_ij*T_ij*(1+r_ij) + xS_ij*P_ij*(1+r_ij)
             + (xT_ij+xS_ij)*(handling_i + H_i)
             + carbon_price*(n_ij*E^T_ij + xS_ij*E^S_ij) ]
  + Σ(i) [ fixed_operating_i*y_i ]
  + Σ(i ∈ I_new) [ build_price_i*b_i / (52*years) ]
  + Σ(j) [ unserved_penalty*u_j ]
```

**Why:** It combines allocation, truck consolidation, operating sites, investment, inventory, and unmet-service tradeoffs on one consistent cost basis. The returned breakdown is the same objective split into cost categories.

### Constraints

**Market service balance:**

`Σ_i (xT_ij + xS_ij) + u_j = demand_j` for each market `j`.

**DC outbound weekly capacity:**

`q_i ≤ effective_throughput_i × y_i` for each DC. Weather cuts `effective_throughput_i`.

**On-hand storage inventory:**

`(α_i + R_i/14) × q_i ≤ storage_capacity_i × y_i` for each DC.

**Truck capacity and minimum load:**

`xT_ij ≤ truck_capacity × n_ij`.

`xT_ij ≥ (min_fill_pct/100) × truck_capacity × n_ij` when minimum fill is greater than zero.

`n_ij ≤ xT_ij` prevents empty dispatched trucks. Units and trucks are integer.

**New facility construction:**

`y_i ≤ b_i` for each candidate. An unopened candidate cannot serve demand, and an unbuilt candidate cannot open. If built, candidate construction price enters both the capital budget and the amortized weekly objective. Since all construction prices are nonnegative, the optimizer has no incentive to build unused facilities (except possible degenerate zero-cost choices).

**Construction capital budget and count:**

`Σ_(i∈I_new) build_price_i × b_i ≤ construction_budget`.

`Σ_(i∈I_new) b_i ≤ max_new_facilities`.

**Hard minimum fulfillment (optional):**

`Σ_j u_j ≤ floor(total_demand × (1 – min_fulfillment_pct/100))`.

**Blocked / too long routes:** If lane is blocked or exceeds a maximum miles/transit time, `xT_ij = xS_ij = n_ij = 0`. Disabled sites and disabled transport modes similarly have zero variable bounds. Truck count caps are additional variable bounds.

### Inventory calculations — why the square root still allows a MILP

Daily outbound demand mean at DC `i` is assumed `μd_i = q_i / 7` and daily standard deviation is **proportional** to mean: `σd_i = CV_i × μd_i`.

Given independent daily demand variation and independent replenishment lead time with mean `L_i` (days) and standard deviation `σL_i` (days), a commonly used approximation is:

`SS_i = z × sqrt( L_i × σd_i² + μd_i² × σL_i² )`.

Substitute the proportional standard deviation assumption:

`SS_i = (z/7) × q_i × sqrt( L_i × CV_i² + σL_i² )`.

Hence `SS_i = α_i × q_i` with `α_i` a **constant** during one solve (computed from the edited lead time, CV, weather, and service target). This allows stock calculations, holding cost, and storage capacity to remain **linear** functions of allocation. Normal quantile `z = Φ⁻¹(target_service_probability)`; e.g. 95% yields about 1.645.

Average **cycle inventory** is approximated from a fixed replenishment interval `R_i` days:

`cycle_i = μd_i × R_i/2 = q_i × R_i/14`.

The optimization includes holding expense on `SS_i + cycle_i` and requires that amount not exceed physical stock storage capacity. No SKU-level pooling or reorder-point inventory evolution is modeled.

**Why use this model:** A direct safety-stock model with endogenously varying independent demand streams and real risk pooling generally produces nonlinear/square-root assignment terms. This **volume-proportional approximation** deliberately trades detail for a stable, transparent, solvable MILP. It is not a universal safety-stock formula for all businesses.

## 5. Modeled weather severity factors

These preset values are **assumptions**, not observed probabilities or forecasted outage statistics.

| Severity | DC available throughput | Freight surcharge per impacted endpoint | DC inbound lead mean multiplier | DC lead SD increase (days) | Delivery transit addition (days) |
| --- | ---: | ---: | ---: | ---: | ---: |
| None | 100% | +0% | ×1.00 | +0 | +0 |
| Mild | 92% | +8% | ×1.10 | +0.25 | +0.25 |
| Moderate | 75% | +20% | ×1.25 | +0.75 | +0.75 |
| Severe | 55% | +40% | ×1.50 | +1.50 | +1.50 |
| Extreme | 25% | +75% | ×2.00 | +3.00 | +3.00 |

At an intensity factor `k`, for example:

`effective_capacity_i = floor(original_capacity_i × max(0, 1 – k × (1 – severity_capacity_factor)))`.

`actual_surcharge = k × severity_surcharge`.

`lead_mean_multiplier = 1 + k × (preset_lead_multiplier – 1)`.

`lead_SD_addition = k × preset_SD_addition`, and similarly for transit delay. With multiple site disruptions active, impacts enter each lane from both endpoints.

A severe storm is **not** assumed to close all lanes automatically: it increases cost, travel delay and reduces DC capacity, unless you also block the relevant lanes or site. You can choose any combination of disrupted DCs and markets, even all of them.

## 6. Five practice exercises

Try each as an independent scenario, save it in **Scenario lab**, and compare cost, service, trucks, construction, and safety stock. Revert your changes before starting the next one or label them as combined scenarios.

1. **Multi-region storm.** In the sidebar set Severe, select Chicago and Newark, and Moderate for Northeast / Boston in the market editor. Compare how trucks and allocations change. Check whether the solver builds Columbus (proposed).
2. **Inventory risk.** In DC editor increase Chicago `Lead SD days` from 1.2 to 2.4, and change target service level from 95.0% to 99.0%. Watch safety stock, holding cost, and storage utilization; long-lead DCs can become less attractive.
3. **Truckload economics.** Increase fixed truck dispatch cost from $210 to $500, then set minimum truck fill to 90%. Compare departures, average truck fill, spot shipments, and total cost.
4. **Construction contingency.** Uncheck Newark `Available`. With proposed DC construction allowed, observe whether a candidate is selected to preserve service. Then disable construction to expose a hard network capacity constraint. Set hard fulfillment to 100% and observe the correct infeasibility response.
5. **Route restriction.** Enable Maximum route distance and enter exactly 950 miles (or any other value). Examine selected lanes and unserved demand. For a single lane, enter a manual `Road override miles` value or set `Blocked`; compare reoptimization.

**What to report:** Set a fixed baseline, change *one input at a time* for sensitivity analysis, then test combined disruptions. For each trial record total cost, service %, trucks, safety inventory, facilities built, and emissions. An apparent cost decrease caused by unserved demand should not be called a savings opportunity.

## 7. Reading model outputs correctly

- **Weekly cost** is transportation + weather/lane freight premiums + handling + carbon shadow cost + weekly inventory carrying costs + weekly site operating costs + straight-line weekly-equivalent construction + penalty on any unserved demand. It is not a booked P&L.
- **Construction one-time capex** is a separate financial metric; **do not add it directly to the weekly total**, because its weekly equivalent is already included there.
- **Inventory cycle-service target** (e.g. 95%) describes the probability of avoiding a replenishment-cycle stockout *under the approximation*. It does not imply 95% of shipments are fulfilled. **Demand fulfillment %** is the actually delivered fraction of deterministic test demand.
- **Unit costs** and **CO₂ factors** are hand-chosen proxies. Neither is grounded in a specific carrier quotation, SKU weight, or emissions audit.
- **Positive shortages** indicate service risk. The problem remains mathematically feasible because the soft shortage variable exists unless a hard service requirement forbids it.
- **Capacity** is an outbound **throughput** rate; **storage** is on-hand inventory stock. They use different time dimensions but both have matching units within their own respective constraints.
- **Solver status** “Optimal (within configured MIP gap)” may mean a solution within 0.5% of the mathematically proven bound; this is normally sufficient for a demo, but is not exact optimality.
- **Network comparison** uses the original, unedited baseline for reference; preset stress tests also start from original inputs. Saved user cases capture *result summaries*, not the full set of input settings.

## 8. Model scope and potential research extensions

### Included

- Integer truck dispatch / capacity / min-fill mixed-integer decisions, with alternative spot mode.
- Two independent facility restrictions: outbound weekly throughput and on-hand storage space.
- Volume-linked safety stock, service-level z factor, lead-time **mean and variability**, cycle inventory and holding cost.
- Candidate build vs existing opening decisions, capital budget and max builds, simple weekly construction amortization.
- Simultaneous storms at multiple centers and markets, with continuous event intensity and manually blocked lanes.
- Editable synthetic data, unlimited-in-principle DC and market rows, lane overrides, CSV exports and comparisons.

### Not included

- Multi-period inventory balance, dynamic replenishment orders, backorders/carryovers, or SKU-level product categories.
- True risk pooling across independently varying markets, forecast error distributions fitted to data, stochastic programming/Monte Carlo, or probability-weighted storm scenarios.
- Actual road routing, tolls, driver hours, stop sequence, freight quotes, trailer dimensions, geocoding, or live transit/weather APIs.
- Multi-stop consolidated vehicle routing (VRP), trailers mixed across different destination lanes, third-party LTL carrier truck counts, or freight minimum charges.
- Facility **construction time**, NPV discount rates, operational start dates, phased build/expansion, salvage value, or balance-sheet effects.
- Endogenous supplier selection, inbound procurement networks, labor scheduling, warehouse picking, or fill-rate type II inventory service.

Those are logical next expansions if you want an advanced research/portfolio project; do not claim this v2 solves them.

## 9. Where to modify code

- **`optimizer.py`**: `CENTERS` and `MARKETS` = sample input tables; `DEFAULT_SETTINGS` = starting assumptions; `WEATHER` = severity multipliers; `solve_network()` = full MILP; `benchmark_scenarios()` = stress tests. This is where new business constraints should be added.
- **`app.py`**: Streamlit interface, editable tables and controls, Plotly maps/charts, saved scenario comparisons, and model explanation.
- **`tests/test_optimizer.py`**: Automated validation of demand balancing, construction decisions, weather, safety stock, trucks, lane restrictions, solver feasibility.
- **`requirements.txt`**: Installable Python dependencies; tested with SciPy's HiGHS MILP.

To run tests from inside the project folder:

```bash
python -m unittest discover -s tests -v
```

Changes in `optimizer.py` should be accompanied by a new test of the math. When publishing, disclose that this is fictional data. If you connect to actual company files, avoid publishing confidential information, client names, supplier cost information, or private coordinates.

## 10. Mathematical/reference links

- [SciPy `optimize.milp` / HiGHS](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html)
- [Streamlit numeric controls](https://docs.streamlit.io/develop/api-reference/widgets/st.number_input)
- [Streamlit editable tables](https://docs.streamlit.io/develop/api-reference/data/st.data_editor)
- [Streamlit Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud)

These are documentation links for the **software**. The supply-chain input values in this project are not sourced from them or asserted to be realistic estimates.
