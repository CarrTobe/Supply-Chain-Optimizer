# Supply Chain Network Optimization & Risk Simulation

An interactive, portfolio-ready **Streamlit** application that solves a fictional U.S. distribution network using **SciPy mixed-integer linear programming**. It allocates weekly shipments across five distribution centers and six customer markets and compares cost, service, utilization, and estimated emissions.

## Quick start (Mac / Windows / Linux)

1. Install [Python 3.11 or 3.12](https://www.python.org/downloads/) (avoid installing Python 3.14 until the dependencies support it).
2. Unzip the project, open Terminal (Mac) or PowerShell (Windows), and change into the project folder.
3. Create a virtual environment and install the dependencies:

**Mac**
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

**Windows PowerShell**
```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Your browser should open the local dashboard (typically `http://localhost:8501`). To stop the app, press `Ctrl+C` in the terminal.

If PowerShell blocks activation, use `.venv\Scripts\python.exe -m pip install -r requirements.txt` and `.venv\Scripts\python.exe -m streamlit run app.py` without activation.

## Dashboard guide

**Sidebar**: Change overall market demand, freight rates, weather severity and impacted DC, carbon price, or lane-length restriction. Changes automatically rerun the optimizer.

**Edit distribution centers and customer demand**: Expand the editing panel at the top. Update individual distribution center capacities, per-unit handling cost, fixed weekly cost, available/open status, and each market's weekly demand.

**Overview**: Read total cost, delivered volume, service level, unit cost, modeled CO₂, cost breakdown, capacity utilization, and unserved-demand alerts.

**Routes & facilities**: Inspect assigned shipments on a schematic U.S. geographic map and export optimized lane allocations to CSV.

**Scenario lab**: Compare independently solved baseline, demand growth, freight inflation, severe weather, capacity constraint, and facility shutdown; export results to CSV. These built-in scenarios use the *original* dataset so comparisons remain interpretable.

**Model details**: Read objective function, constraints, assumptions, and limitations.

## Model summary

- **Decision variables**: shipment allocation `x[dc, market]`, binary DC operation `y[dc]`, and market shortfall `u[market]`.
- **Objective**: minimize shipment freight + weather premium + handling + carbon charge + fixed DC operating costs + shortage penalties.
- **Constraints**: meet market demand with shipments or explicit unmet demand; shipments out of each DC cannot exceed its available capacity multiplied by DC operation decision; optional maximum approximate road miles per lane.
- **Solver**: `scipy.optimize.milp` (HiGHS). Shipment variables are continuous and DC open/closed variables are binary. For this transportation structure, shipments resolve to integer values.
- **Weather model**: moderate/severe disruption reduces impacted DC capacity and raises freight charges on affected routes.

### Dataset and assumptions

All data and costs are **synthetic**, not real carrier rates or verified weather forecasts.

- Five DCs: Chicago, Dallas, Atlanta, Los Angeles, Newark.
- Six demand markets: Boston, Washington D.C., Miami, Detroit, Houston, Phoenix.
- Baseline weekly demand: **11,500 shipments**.
- Road-distance proxy: great-circle miles × 1.20 (not a live routing API).
- Freight: $4.50 per shipment + $0.014 × road-distance miles, before freight-rate and weather adjustments.
- Approximate freight-related CO₂: 0.00014 metric tonnes per shipment-mile, with default $35/tonne charge.
- Shortfall penalty: $250 per unserved shipment. It is a **penalty within the objective**, not actual revenue lost.
- Weekly fixed costs only; no capital costs, detailed inventory planning, shipping modes, or multi-period planning.

The optimizer **never hides an infeasible network**: it reports and penalizes any shipments not served. Treat decisions that raise unserved volume as service-risk scenarios, not real cost-saving successes.

## Deploy for your resume portfolio

1. Create a free [GitHub](https://github.com) repository named `supply-chain-network-optimizer`.
2. Upload `app.py`, `optimizer.py`, `requirements.txt`, `README.md`, and `.streamlit/config.toml` (including the `.streamlit` folder).
3. Open [Streamlit Community Cloud](https://share.streamlit.io), sign in with GitHub, choose **Create app**, select the repository and branch, and set the entrypoint file to `app.py`.
4. Deploy. The hosted `streamlit.app` URL can be placed in your resume or LinkedIn projects section.

Do not commit secrets or real company data into a public GitHub repository.

## Test

```bash
python -m unittest discover -s tests -v
```

## How to improve it further

1. Add warehouse inventory and service-level-based safety stock.
2. Replace approximate distances with a transportation mileage matrix from an authorized routing provider.
3. Add supplier-to-DC inbound procurement legs and purchasing costs.
4. Add facility-opening decisions with capital costs and multi-year demand scenarios.
5. Compare expected costs over probabilities of weather-related outages, rather than a single deterministic stress case.

## Resume description (use after you have run and reviewed the project)

**Supply Chain Distribution Network Optimization | Independent Project**
- Built an interactive Python/Streamlit decision-support tool using mixed-integer optimization to allocate 11,500 simulated weekly shipments across five distribution centers and six demand regions.
- Modeled transportation, facility operating, carbon, and weather-disruption costs; automated scenario comparisons of freight inflation, demand shifts, DC capacity constraints, and outages.
- Visualized optimized distribution lanes and facility utilization in a dashboard, highlighting a 400-shipment weekly capacity shortfall under a simulated Newark closure.

*Keep simulated numerical results clearly identified as hypothetical.*
