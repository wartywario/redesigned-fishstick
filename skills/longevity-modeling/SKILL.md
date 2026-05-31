---
name: longevity-modeling
description: This skill should be used when the user wants to evaluate retirement readiness, portfolio longevity, sustainable withdrawals, cash-flow sufficiency, sequence-of-returns risk, spending scenarios, retirement age scenarios, goal feasibility, portfolio depletion risk, Monte Carlo simulation results, deterministic projection results, or sensitivity to inflation, returns, spending, and taxes. Activate when the user asks whether their portfolio can last, how long their money will last, or what happens under different retirement scenarios. Use after wealth-intake has produced a structured profile, or when the user provides enough direct inputs to run a projection.
version: 1.0.0
---

# Longevity Modeling Skill

## Purpose

Model whether a household's portfolio and income sources may support stated goals over a planning horizon. This skill focuses on cash-flow projection, portfolio longevity, withdrawal sustainability, scenario analysis, and sensitivity testing.

This skill does not provide investment, tax, legal, or financial advice. It produces educational and analytical projections based on explicit assumptions. It must not present projections as guarantees or tell the user to buy, sell, withdraw, convert, or rebalance specific assets.

## Core Responsibilities

1. Identify the modeling objective.
2. Confirm or infer the minimum viable inputs.
3. Separate known facts from assumptions.
4. Produce deterministic and/or probabilistic portfolio longevity projections.
5. Model annual cash flows over the planning horizon.
6. Show how results change under scenarios.
7. Flag missing data that materially affects reliability.
8. Explain results in plain language without overconfidence.
9. Prepare structured outputs for downstream reporting, tax review, or rebalancing analysis.

## Minimum Viable Inputs

- Current age
- Retirement age or goal start date
- Planning horizon age
- Current portfolio value
- Annual spending need
- Whether spending is before-tax or after-tax
- Current or target asset allocation
- Expected income sources
- Major future expenses
- Inflation assumption
- Return assumptions
- Tax drag or effective tax assumptions, if relevant

If any are missing, proceed with clearly labeled placeholder assumptions only if the user wants a rough estimate. Otherwise, ask for the missing inputs.

## Pipeline Input Adapter

This skill is designed to run after `wealth-intake` and `portfolio-analysis`, but
those skills emit different shapes. Map them before modeling:

| Longevity input field | From `wealth-intake` | From `portfolio-analysis` |
|---|---|---|
| `portfolio.total_value` | sum of `accounts[].balance` | `portfolio_summary.total_portfolio_value` |
| `portfolio.allocation` | derive from `holdings[]` if present | `current_allocation.broad_asset_group_allocation` |
| `household.*` | `household` (same keys) | n/a |
| `goals[]` | `goals` (same shape) | n/a |
| `income[]` | `income` (same shape) | n/a |

If only a total portfolio value is available (no allocation), state the
allocation as a labeled placeholder assumption before running the model.

## Preferred Input Structure

Accept structured input from prior skills in this format:

```json
{
  "household": {
    "client_age": 55,
    "partner_age": null,
    "state": "WA",
    "filing_status": "married_joint",
    "planned_retirement_age": 60,
    "planning_horizon_age": 95
  },
  "portfolio": {
    "total_value": 2250000,
    "allocation": {
      "us_equity": 0.45,
      "intl_equity": 0.15,
      "bonds": 0.30,
      "cash": 0.10
    },
    "accounts": []
  },
  "goals": [
    {
      "name": "Retirement spending",
      "category": "retirement_income",
      "priority": "high",
      "start_age": 60,
      "end_age": 95,
      "amount": 120000,
      "frequency": "annual",
      "inflation_adjusted": true,
      "before_or_after_tax": "after_tax"
    }
  ],
  "income": [
    {
      "source": "Social Security",
      "amount": 42000,
      "frequency": "annual",
      "start_age": 67,
      "end_age": 95,
      "inflation_adjusted": true,
      "taxability": "partially_taxable"
    }
  ],
  "expenses": [],
  "assumptions": {
    "inflation": 0.025,
    "equity_return_nominal": 0.07,
    "bond_return_nominal": 0.045,
    "cash_return_nominal": 0.03,
    "tax_drag_taxable": 0.006,
    "portfolio_fee": 0.002,
    "simulation_count": 10000
  }
}
```

## Modeling Modes

### 1. Deterministic Base Case

Use fixed annual assumptions for portfolio return, inflation, spending growth, income growth, tax drag, fees, and contributions or withdrawals. Use to explain mechanics and produce a simple year-by-year projection.

### 2. Scenario Analysis

Compare specific alternative assumptions:

- Retire earlier or later
- Spend more or less
- Higher inflation or lower returns
- Market downturn at retirement
- One-time major expense
- Delayed Social Security
- Reduced discretionary spending after a market decline

Use to show which factors are most important.

### 3. Monte Carlo Simulation

Use random return paths to estimate the range of possible outcomes.

Required outputs:
- Success probability
- Median ending portfolio value
- 10th, 25th, 75th, 90th percentile ending values
- Probability of depletion
- Median depletion age if failures occur
- Worst 5% outcome description

Never describe Monte Carlo results as guarantees.

## Return Assumptions

If the user provides return assumptions, use them. If missing and the user requests a rough model, use these clearly labeled placeholders (the script's `DEFAULT_RETURNS`, last reviewed 2026-05 against J.P. Morgan / Vanguard / Horizon Actuarial CMAs and Damodaran historical data):

```json
{
  "inflation": 0.025,
  "us_equity_return_nominal": 0.07,
  "intl_equity_return_nominal": 0.07,
  "bond_return_nominal": 0.045,
  "cash_return_nominal": 0.03,
  "equity_volatility": 0.16,
  "bond_volatility": 0.06,
  "cash_volatility": 0.01,
  "equity_bond_correlation": 0.20
}
```

List placeholder assumptions prominently and invite replacement with adviser-approved assumptions.

## Cash-Flow Modeling Rules

**Timing convention (authoritative — do not deviate):** cash flows are applied at
the **beginning of the year**, then the annual return is applied to the remaining
balance:

```
ending = (beginning + contributions + income - spending +/- one_time) * (1 + net_return)
net_return = blended_gross_nominal_return - portfolio_fee - tax_drag
```

This is the exact convention the bundled calculator (`scripts/longevity.py`)
implements. Always describe results using it so the prose matches the numbers.

For each projection year:

1. Start with beginning portfolio value.
2. Add contributions, if any (pre-retirement).
3. Add external income sources (inflated if inflation-adjusted).
4. Subtract goal spending and expenses (inflated if inflation-adjusted).
5. Apply any one-time cash flows.
6. Apply the net portfolio return (gross return less fees and tax drag) to the
   post-cash-flow balance.
7. Track ending portfolio value.
8. Flag depletion when the post-cash-flow balance is at or below zero; floor the
   balance at zero thereafter.

Distinguish between: pre-retirement accumulation years, transition year, retirement distribution years, later-life spending changes, and one-time goal expenses.

## Withdrawal Modeling Rules

Default withdrawal order (modeling assumption only — not advice, flag for tax review):

1. Cash bucket or cash allocation first, when explicitly available.
2. Taxable accounts next, if account-level detail is available.
3. Tax-deferred accounts next.
4. Roth accounts last.

If account-level data is unavailable, model withdrawals from the total portfolio.

## Initial Withdrawal Rate

```
initial_withdrawal_rate = first_year_net_portfolio_withdrawal / starting_portfolio_value

first_year_net_portfolio_withdrawal = annual_spending + taxes_and_fees_if_modeled - external_income
```

State whether this is gross or net of taxes.

## Success and Failure Definitions

Define success explicitly before reporting results.

Default success definition:
> The portfolio does not deplete before the planning horizon age while supporting modeled spending and income assumptions.

Alternative definitions may include: maintaining a minimum ending value, a legacy target, a cash reserve, funding all high-priority goals, or avoiding depletion before either spouse's planning age.

Include the success definition in every output.

## Key Metrics

Calculate and report:
- Starting portfolio value
- Initial withdrawal rate (gross and net of external income)
- First-year spending need
- Net annual portfolio withdrawal
- Base-case ending portfolio value
- Lowest projected portfolio value
- Depletion year or age, if any
- Success probability, if Monte Carlo is used
- Median ending portfolio value
- 10th percentile ending portfolio value
- Sensitivity to spending, inflation, and return assumptions

## Scenario Library

Standard scenarios to consider when scenario analysis is requested:

```json
[
  { "name": "Base case", "description": "Uses current assumptions." },
  { "name": "Lower return case", "description": "Reduces annual portfolio returns by 1 percentage point." },
  { "name": "Higher inflation case", "description": "Increases inflation by 1 percentage point." },
  { "name": "Higher spending case", "description": "Increases retirement spending by 10%." },
  { "name": "Lower spending case", "description": "Reduces retirement spending by 10%." },
  { "name": "Early retirement case", "description": "Moves retirement 2 years earlier." },
  { "name": "Delayed retirement case", "description": "Moves retirement 2 years later." },
  { "name": "Early bear market case", "description": "Applies a large negative return in the first retirement year followed by normal assumptions." }
]
```

Adapt scenarios to the user's goals and available data.

## Validation Checks

Before returning results, verify:

- Is annual spending monthly or annual?
- Is spending before-tax or after-tax?
- Are all ages and dates plausible?
- Does retirement age come after current age?
- Is planning horizon greater than retirement age?
- Is portfolio value positive?
- Do allocation percentages sum to approximately 100%?
- Are return assumptions nominal or real?
- Is inflation applied consistently?
- Are fees and tax drag double-counted?
- Are income sources double-counted with portfolio withdrawals?
- Are one-time expenses modeled only once?
- Is Social Security or pension start age clearly stated?
- Are results overly dependent on placeholder assumptions?

List any issues under `warnings` or `missing_information`.

## Interpretation Guidelines

Use these plain-language categories:

- **"Appears robust under the modeled assumptions"** — base case and downside scenarios remain funded.
- **"Appears workable but assumption-sensitive"** — success depends heavily on returns, inflation, or spending flexibility.
- **"Appears fragile under the modeled assumptions"** — modest negative scenarios cause depletion or severe shortfall.
- **"Insufficient information"** — core inputs are missing.

Use conditional language:
- "Under the stated assumptions..."
- "The model suggests..."
- "This result is sensitive to..."
- "A financial adviser or CPA should review..."

Never use: "You are guaranteed to be fine." / "This plan will work." / "You should retire now." / "You should buy/sell/convert/withdraw."

## Required Output Format

```markdown
## Longevity Modeling Summary

[Plain-language summary of whether the plan appears robust, fragile, or assumption-dependent.]

## Success Definition

[State the success definition used.]

## Key Results

- Starting portfolio value: ...
- Initial withdrawal rate: ...
- Base-case ending value: ...
- Estimated success probability: ...
- Depletion age, if applicable: ...

## Main Drivers

[Assumptions that most affect the result.]

## Scenario Comparison

[Table or list of major scenarios.]

## Important Limitations

[Missing data, assumptions, and professional review needs.]

## Structured Longevity JSON

```json
{ ... }
```
```

## Structured Output Schema

The full structured-output schema and the calculator's exact input/output contract
live in [`references/schema.md`](references/schema.md). Load that file when
assembling the final JSON or constructing calculator inputs.

## Handling Missing Data

If data is missing but the user wants an estimate, create a rough model with clearly labeled placeholder assumptions.

If data is missing and materially prevents a useful model, ask for no more than 8 follow-up items, prioritized:

1. Current age
2. Retirement age
3. Starting portfolio value
4. Annual spending need
5. Planning horizon age
6. Income sources
7. Asset allocation
8. Whether spending is before-tax or after-tax
9. Major future cash flows
10. Tax drag or account type data

## Professional Review Flags

Add flags for: tax-sensitive withdrawal sequencing, Roth conversions, required minimum distributions, Social Security claiming decisions, pension election decisions, annuity purchases or surrender decisions, concentrated stock liquidation, large taxable gains, estate or legacy targets, long-term care assumptions, cross-border tax or residency issues, business sale proceeds, real estate sales, charitable strategies, any case where small tax differences materially affect longevity.

## Calculator (required for any numeric result)

This skill bundles a deterministic + Monte Carlo engine at
`scripts/longevity.py` (pure Python 3.8+ standard library, no dependencies).

**Always run the script to produce numbers. Do not compute multi-year projections
or Monte Carlo percentiles by hand** — hand arithmetic over 30–40 years drifts,
is not reproducible, and Monte Carlo cannot be estimated reliably without
simulation. Run it once for the base case and once per scenario:

```
echo '{ ...input... }' | python scripts/longevity.py
# or
python scripts/longevity.py input.json
```

The exact input and output object shapes are documented in
[`references/schema.md`](references/schema.md). Map the script's `base_case`,
`monte_carlo`, and `year_by_year` output into the Structured Output Schema when
assembling the final response.

## Boundaries

You may: run educational projections, calculate portfolio depletion risk, compare scenarios, explain sensitivity to assumptions, prepare structured outputs for reporting.

You may not: guarantee outcomes, tell the user to retire, recommend specific investments or tax transactions, give legal or investment advice, replace a licensed financial adviser, CPA, or attorney, present Monte Carlo results as certainty.
