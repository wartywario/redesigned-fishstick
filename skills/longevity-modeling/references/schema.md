# Longevity Modeling — Schemas & Calculator I/O

Load this file when you need the full structured-output schema or the bundled
calculator's exact input/output contract. Day-to-day reasoning does not require
it in context.

## Structured Output Schema (full)

```json
{
  "model_metadata": {
    "model_type": null,
    "run_date": null,
    "currency": "USD",
    "success_definition": null,
    "projection_start_age": null,
    "projection_end_age": null,
    "projection_years": null
  },
  "inputs_used": {
    "starting_portfolio_value": null,
    "retirement_age": null,
    "planning_horizon_age": null,
    "annual_spending_goal": null,
    "spending_before_or_after_tax": null,
    "inflation_adjusted_spending": null,
    "external_income_sources": [],
    "major_future_cash_flows": [],
    "asset_allocation": {},
    "assumptions": {}
  },
  "base_case_results": {
    "initial_withdrawal_rate": null,
    "first_year_net_portfolio_withdrawal": null,
    "ending_portfolio_value": null,
    "lowest_portfolio_value": null,
    "depletion_occurs": null,
    "depletion_age": null,
    "surplus_or_shortfall_at_horizon": null
  },
  "monte_carlo_results": {
    "simulation_count": null,
    "success_probability": null,
    "failure_probability": null,
    "median_ending_value": null,
    "p10_ending_value": null,
    "p25_ending_value": null,
    "p75_ending_value": null,
    "p90_ending_value": null,
    "median_depletion_age_if_failed": null,
    "notes": []
  },
  "scenario_results": [
    {
      "name": null,
      "description": null,
      "changed_assumptions": {},
      "ending_portfolio_value": null,
      "success_probability": null,
      "depletion_age": null,
      "interpretation": null
    }
  ],
  "sensitivity_analysis": {
    "most_sensitive_variables": [],
    "spending_sensitivity": [],
    "inflation_sensitivity": [],
    "return_sensitivity": []
  },
  "year_by_year_projection": [
    {
      "year": null,
      "age": null,
      "beginning_portfolio_value": null,
      "external_income": null,
      "spending": null,
      "net_withdrawal": null,
      "portfolio_return": null,
      "tax_drag": null,
      "fees": null,
      "ending_portfolio_value": null
    }
  ],
  "assumptions": [],
  "missing_information": [],
  "warnings": [],
  "professional_review_flags": []
}
```

## Bundled Calculator (`scripts/longevity.py`)

Pure standard library (Python 3.8+, no numpy). Runs the deterministic base case
and a Monte Carlo simulation. **Always run this rather than computing year-by-year
arithmetic by hand** — hand projections over 30–40 years drift and are not
reproducible.

### How to run

```
python scripts/longevity.py input.json        # input from file
# or
echo '{...}' | python scripts/longevity.py     # input from stdin
```

### Input object

```json
{
  "starting_portfolio_value": 2200000,
  "current_age": 55,
  "retirement_age": 60,
  "planning_horizon_age": 95,
  "annual_spending": 120000,
  "spending_inflation_adjusted": true,
  "spending_start_age": 60,
  "pre_retirement_contribution": 0,
  "asset_allocation": {
    "equity": 0.60,
    "bonds": 0.30,
    "cash": 0.10
  },
  "return_assumptions": {
    "equity_return_nominal": 0.07,
    "bond_return_nominal": 0.045,
    "cash_return_nominal": 0.03,
    "inflation": 0.025,
    "portfolio_fee": 0.002,
    "tax_drag": 0.003,
    "equity_volatility": 0.16,
    "bond_volatility": 0.06,
    "cash_volatility": 0.01,
    "equity_bond_correlation": 0.20
  },
  "income_sources": [
    {
      "source": "Social Security",
      "amount": 35000,
      "start_age": 67,
      "end_age": 95,
      "inflation_adjusted": true
    }
  ],
  "one_time_cash_flows": [
    { "age": 70, "amount": -50000, "inflation_adjusted": false }
  ],
  "simulation_count": 10000,
  "random_seed": 12345
}
```

Notes on inputs:
- `asset_allocation` accepts `equity`/`bonds`/`cash` or the finer
  `us_equity`/`intl_equity`/`bonds`/`cash`. Weights are normalized to 1.
- `income_sources[].amount` and `annual_spending` are in **today's dollars**;
  the engine inflates them when `inflation_adjusted` is true.
- `one_time_cash_flows[].amount` is negative for an expense, positive for an inflow.
- `simulation_count: 0` skips Monte Carlo.
- `random_seed` makes Monte Carlo reproducible across runs.

### Output object

```json
{
  "engine_assumptions": {
    "blended_gross_nominal_return": 0.0585,
    "portfolio_fee": 0.002,
    "tax_drag": 0.003,
    "net_nominal_return": 0.0535,
    "blended_annual_stdev": 0.1012,
    "inflation": 0.025,
    "net_real_return_approx": 0.0285,
    "cashflow_timing": "begin_of_year"
  },
  "base_case": {
    "starting_portfolio_value": 2200000,
    "portfolio_at_retirement": 2854929.45,
    "initial_withdrawal_rate_gross": 0.0476,
    "initial_withdrawal_rate_net": 0.0476,
    "first_year_net_portfolio_withdrawal": 135768.99,
    "ending_portfolio_value": 2214117.1,
    "lowest_portfolio_value": 2200000,
    "depletion_occurs": false,
    "depletion_age": null
  },
  "monte_carlo": {
    "simulation_count": 10000,
    "success_probability": 0.524,
    "failure_probability": 0.476,
    "median_ending_value": 326339.78,
    "p10_ending_value": 0.0,
    "p25_ending_value": 0.0,
    "p75_ending_value": 4819898.94,
    "p90_ending_value": 11182016.24,
    "median_depletion_age_if_failed": 85,
    "notes": []
  },
  "year_by_year": []
}
```

Map the script output into the Structured Output Schema above when assembling the
final response: `engine_assumptions` → `inputs_used.assumptions`, `base_case` →
`base_case_results`, `monte_carlo` → `monte_carlo_results`, `year_by_year` →
`year_by_year_projection`. Compute `scenario_results` by re-running the script
once per scenario with the changed assumptions.

## Cash-Flow Timing Convention (authoritative)

The engine uses **begin-of-year cash flows**: contributions, external income,
spending, and one-time flows are applied to the beginning balance first, then the
annual return is applied to the remaining balance:

```
ending = (beginning + contributions + income - spending +/- one_time) * (1 + net_return)
```

Depletion is flagged when the post-cash-flow balance is <= 0. Always describe
results using this convention so the prose matches the numbers.
