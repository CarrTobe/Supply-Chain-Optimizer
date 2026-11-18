# Supply Chain Network Optimizer — Advanced Edition

![Python](https://img.shields.io/badge/Python-3.11%2B-blue) ![Solver](https://img.shields.io/badge/Optimization-SciPy%20HiGHS%20MILP-teal) ![Dashboard](https://img.shields.io/badge/Dashboard-Streamlit-red)

An interactive, synthetic distribution network optimization project. This is a substantially extended version of the prior five-center/six-market starter project.

## Quick start

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

Open the local browser address printed by Streamlit (usually `http://localhost:8501`).

**Full instructions:** Read **[USER_GUIDE.md](USER_GUIDE.md)**. It explains every dashboard control, mathematical objective/constraints, weather severity assumptions, safety stock derivation, tested examples, and limits.

## What's new in v2

- 5 existing plus 3 **proposed construction** sites, a binary build decision, one-time capital budget, maximum number of new sites, and a simple weekly construction-cost equivalent.
- Independent **replenishment safety stock** based on service level, demand CV, mean inbound lead time and inbound lead standard deviation. Inventory carrying costs and inventory storage limits are included in the solver.
- **Integer truckload consolidation** across units sharing the same center-to-market route, adjustable truck capacity, fixed dispatch + mileage costs, optional minimum fill requirement, and spot freight alternative.
- **Multi-facility and multi-market weather disruptions**, each with configurable severity and continuously adjustable intensity.
- **Typed maximum route distance**, max transit time, and per-route overrides for road miles, price, delay, truck count and route closure.
- Fully editable facilities and markets, detailed route/stock/facility outputs, scenario comparisons and CSV exports.
- Automated tests for service balance, construction, weather, inventory, truck limits, and infeasibility.

## The math, in one sentence

A **capacitated facility-location and capital-budgeting mixed-integer linear program (MILP)** with direct truck dispatch/spot shipping, linearized proportional safety stock and cycle inventory, weather-adjusted capacities/lead times/lane rates, plus explicit market shortfall penalties.

### Default baseline (synthetic)

- 11,500 standardized shipping units demanded weekly across 6 markets.
- 5 existing DCs; 3 optional new DC construction sites.
- **Baseline costs change from the original starter** because v2 has a different freight and carbon-accounting model. Do not directly compare v1 and v2 as a like-for-like savings calculation.
- All parameters are illustrative, including carbon estimates, weather multipliers and truck capacity.

## Testing

```bash
python -m unittest discover -s tests -v
```

## Publishing

Upload `app.py`, `optimizer.py`, `requirements.txt`, `README.md`, `USER_GUIDE.md`, `tests/`, and `.streamlit/` to your public GitHub repo, then deploy the repository on [Streamlit Community Cloud](https://share.streamlit.io). Never upload real company confidential data to a public project.

## Files

- `app.py` — user interface
- `optimizer.py` — optimization inputs and MILP solver
- `USER_GUIDE.md` — comprehensive documentation and examples
- `tests/test_optimizer.py` — automated correctness tests
- `start_mac.sh` / `start_windows.bat` — convenience starters

**Disclaimer:** Educational/portfolio model only. Not a warehouse management system, transportation management system, predictive weather tool, or commercial consulting recommendation.
