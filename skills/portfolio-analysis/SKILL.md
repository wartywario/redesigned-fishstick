---
name: portfolio-analysis
description: This skill should be used when the user wants to understand or analyze their current portfolio allocation, asset-class exposure, account-level allocation, drift from a target allocation, diversification, concentration risk, cash position, taxable versus tax-advantaged asset location, rebalancing needs, or portfolio readiness for retirement modeling. Activate when the user provides portfolio holdings, account balances, or asks for inputs to cash-flow or longevity projections. Use after wealth-intake has collected account and holding information, or when the user provides holdings directly.
version: 1.0.0
---

# Portfolio Analysis Skill

## Purpose

Analyze a household's current portfolio structure, asset allocation, account-level exposures, diversification, concentration risks, drift from a target allocation, and basic rebalancing inputs.

This skill does not provide investment, tax, legal, or financial advice. Its role is to organize and analyze portfolio facts, calculate exposures, identify areas that need review, and prepare structured outputs for downstream longevity modeling, tax considerations, rebalancing, scenario analysis, and reporting workflows.

Do not recommend specific securities. Do not tell the user to buy or sell investments. Do not present portfolio changes as instructions. Frame all output as analysis, observations, or inputs for professional review.

## Core Responsibilities

1. Parse portfolio accounts and holdings.
2. Normalize holdings into a consistent structure.
3. Classify holdings by asset class when possible.
4. Calculate portfolio value and allocation percentages.
5. Calculate account-level allocation.
6. Identify concentration risks.
7. Compare current allocation to a target allocation, if provided.
8. Calculate allocation drift.
9. Identify missing data required for deeper analysis.
10. Prepare structured output for downstream modeling and rebalancing workflows.

## Required Inputs

Minimum viable inputs:

- Account names
- Account types
- Account balances
- Holdings or asset-class breakdowns
- Market value per holding or percentage allocation
- Cash balance
- Target allocation, if available
- User's age and time horizon, if available
- Risk tolerance, if available
- Tax treatment of accounts, if available

If holdings are unavailable, proceed with account-level or asset-class-level data and clearly flag the limitation.

## Account Type Normalization

Normalize account types to:

`taxable_brokerage`, `checking`, `savings`, `money_market`, `traditional_ira`, `roth_ira`, `sep_ira`, `simple_ira`, `401k`, `403b`, `457`, `hsa`, `529`, `trust`, `annuity`, `pension`, `crypto_wallet`, `real_estate`, `business_interest`, `other`

Normalize tax treatment to:

`taxable`, `tax_deferred`, `tax_free`, `tax_advantaged_health`, `education_tax_advantaged`, `illiquid_or_nonportfolio_asset`, `unknown`

## Asset Class Classification

Classify holdings into the most appropriate detailed asset class:

`us_large_cap_equity`, `us_mid_cap_equity`, `us_small_cap_equity`, `us_total_market_equity`, `international_developed_equity`, `emerging_markets_equity`, `global_equity`, `sector_equity`, `single_stock`, `employer_stock`, `us_bonds`, `international_bonds`, `short_term_bonds`, `intermediate_term_bonds`, `long_term_bonds`, `tips`, `municipal_bonds`, `high_yield_bonds`, `cash`, `money_market`, `cds`, `real_estate`, `reit`, `commodities`, `gold_precious_metals`, `crypto`, `private_equity`, `private_credit`, `annuity`, `other_alternative`, `unknown`

Map each holding to a broad asset group:

`equity`, `fixed_income`, `cash`, `real_assets`, `alternatives`, `insurance_or_annuity`, `unknown`

If a holding is a balanced fund, target-date fund, or allocation fund, classify it as `multi_asset` unless a reliable internal allocation is provided. Do not invent internal fund allocations.

## Calculations

**Use the bundled calculator — do not compute these by hand.** This skill ships a
deterministic engine at `scripts/portfolio.py` (pure Python 3.8+, no dependencies)
that performs every calculation in this section: total value, holding weights,
broad/detailed/tax-treatment allocation, per-account allocation, drift vs. target
with threshold flags, concentration flags, and cash runway. Hand aggregation across
many holdings and accounts is error-prone and not reproducible.

```
echo '{ "accounts": [...], "holdings": [...], "target_allocation": {...} }' | python scripts/portfolio.py
# or
python scripts/portfolio.py input.json
```

The exact input/output shapes and the overridable threshold defaults are documented
in [`references/schema.md`](references/schema.md). The formulas below define what the
script computes; run the script for the actual numbers, then layer on the qualitative
observations, assumptions, and review flags that you own.

### 1. Total Portfolio Value

```
portfolio_value = sum(account balances or holding market values)
```

If account balances and holding values conflict, report the conflict and state which source was used.

### 2. Holding Weights

```
holding_weight = holding_market_value / total_portfolio_value
```

### 3. Asset-Class Allocation

Calculate allocation by broad asset group and by detailed asset class.

### 4. Account-Level Allocation

Calculate asset allocation within each account.

### 5. Tax-Location Summary

Summarize where assets are held by tax treatment:

- Percent of equity in taxable accounts
- Percent of bonds in tax-deferred accounts
- Cash held inside retirement accounts versus bank accounts
- Tax-inefficient assets held in taxable accounts

Do not provide tax advice. Flag items for review by a tax professional or downstream tax-considerations skill.

### 6. Target Allocation Drift

If a target allocation is provided, calculate:

```
drift = current_allocation - target_allocation
absolute_drift = abs(drift)
```

Default drift thresholds (unless user specifies otherwise):

- Broad asset group drift > 5 percentage points: `review`
- Broad asset group drift > 10 percentage points: `high_priority_review`
- Detailed asset class drift > 3 percentage points: `review`
- Single holding above 10% of total portfolio: `concentration_review`
- Employer stock above 5% of total portfolio: `employer_stock_review`
- Cash below 3 months of expenses (if known): `cash_reserve_review`
- Cash above 24 months of expenses (if known): `cash_drag_review`

### 7. Concentration Risk

Identify:

- Single holding above 10% of total portfolio
- Employer stock above 5% of total portfolio
- Sector exposure above 20%, if known
- Crypto or speculative assets above 5%, unless user stated otherwise
- Illiquid assets above 30% of net worth, if included
- Unclassified holdings above 10% of portfolio

Frame these as risk observations, not as instructions to sell.

### 8. Liquidity and Cash Position

If spending is known:

```
cash_runway_months = cash_balance / monthly_spending
```

Classifications:

- Less than 3 months: low cash reserve
- 3–12 months: typical reserve range
- 12–24 months: elevated cash reserve
- More than 24 months: high cash reserve / potential cash drag

Adjust tone for retirees or near-retirees where larger reserves may be intentional.

### 9. Data Quality Rating

Assign one of:

- `high`: Holdings, market values, account types, and target allocation mostly complete.
- `medium`: Major balances and rough asset classes available, but holdings, basis, or target allocation are incomplete.
- `low`: Only rough totals available, or many account types/holdings are unknown.

Explain the reason in `data_quality_notes`.

## Output Language

Use:
- "The portfolio appears to be..."
- "This may warrant review..."
- "Based on the provided data..."
- "A downstream rebalancing workflow could evaluate..."
- "This is a risk observation, not a trade recommendation."

Avoid:
- "You should buy..." / "You should sell..."
- "This guarantees..." / "This is the optimal portfolio..."

## Required Output Format

```markdown
## Portfolio Analysis Summary

[Brief summary of total value, broad allocation, notable exposures, and data quality.]

## Current Allocation

[Summarize broad asset groups and key detailed asset classes.]

## Drift From Target Allocation

[If target provided, summarize major drift. If not, state that target allocation was not provided.]

## Concentration and Risk Observations

[Notable concentration, liquidity, tax-location, or unknown-classification issues.]

## Missing Information

[Items needed for higher-confidence analysis.]

## Professional Review Flags

[Items that should be reviewed before any trade, tax move, or planning decision.]

## Structured Portfolio Analysis JSON

```json
{ ... }
```
```

## JSON Schema

The full final-response JSON schema and the calculator's input/output contract live
in [`references/schema.md`](references/schema.md). Load that file when assembling the
final JSON or building calculator inputs.

## Follow-Up Question Rules

Ask follow-up questions only if missing data materially affects the requested analysis. No more than 8 questions at once.

Priority order:
1. Account balances
2. Account types and tax treatment
3. Holdings or asset-class breakdown
4. Target allocation
5. Cash balance
6. Annual or monthly spending
7. Cost basis for taxable assets
8. Risk tolerance and time horizon
9. Employer stock or concentrated positions
10. Illiquid assets or private investments

If the user wants a quick analysis, proceed with available information and clearly list assumptions and missing data.

## Assumption Rules

Record all inferred asset class or account type assumptions. Examples:

- "Assumed unspecified brokerage account is taxable."
- "Assumed money market fund is cash or cash equivalent."
- "Assumed target-date fund is multi-asset because internal allocation was not provided."
- "Assumed account balance is current market value."
- "Assumed all values are in USD."

Do not silently infer cost basis, tax bracket, fund composition, or expected returns.

## Professional Review Flags

Add flags for:

- Taxable holdings with large unrealized gains
- Missing cost basis for taxable holdings
- Employer stock concentration
- Single-stock concentration
- Large crypto exposure
- Large illiquid exposure
- Annuities, private investments, options, or equity compensation
- Margin loans
- High cash balance with unclear purpose
- Low cash reserve
- Any proposed trades or rebalancing that could create taxable gains
- Any analysis involving tax-sensitive account location

## Boundaries

You may: calculate allocations, calculate drift, identify concentration, identify missing data, flag issues for review, prepare downstream modeling inputs.

You may not: recommend specific securities, tell the user to buy or sell, give personalized tax advice, guarantee improved outcomes, present a portfolio as optimal, execute or instruct trades, replace a licensed financial adviser, CPA, or attorney.
