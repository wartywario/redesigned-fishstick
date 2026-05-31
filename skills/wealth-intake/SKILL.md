---
name: wealth-intake
description: This skill should be used when the user wants to analyze, model, or organize financial planning information, including retirement readiness, portfolio balancing, cash-flow planning, portfolio longevity, tax-aware planning, withdrawal planning, rebalancing, goal-based investment planning, or scenario modeling. Activate when the user shares financial data such as account balances, income, expenses, holdings, or retirement goals, or asks to organize or structure their household financial picture.
version: 1.0.0
---

# Wealth Intake Skill

## Purpose

Collect, normalize, validate, and summarize household financial information for wealth-management analysis.

This skill does not provide investment, tax, legal, or financial advice. Its role is to structure inputs, identify missing information, and prepare a clean data package for downstream portfolio analysis, retirement modeling, cash-flow planning, tax consideration review, and rebalancing workflows.

## Core Responsibilities

1. Extract relevant financial facts from the user's input.
2. Ask only for information that is necessary or highly useful.
3. Normalize the data into a consistent structure.
4. Separate known facts from assumptions.
5. Identify missing, uncertain, or conflicting information.
6. Flag sensitive areas that require professional review.
7. Prepare a structured output for downstream analysis.

Do not make portfolio recommendations. Do not recommend specific securities. Do not provide tax advice. Do not tell the user to buy, sell, convert, withdraw, or rebalance anything. This skill handles intake and organization only.

## Intake Categories

### 1. Household Profile

- Client age
- Spouse/partner age, if relevant
- Filing status
- State of residence
- Planned retirement age
- Planning horizon or target longevity age
- Dependents
- Employment status
- Income sources
- Health or longevity assumptions, only if volunteered

### 2. Goals

For each goal, capture: name, priority, target date or age, estimated amount, whether nominal or inflation-adjusted, whether one-time or recurring.

Goal types: retirement income, major purchases, education funding, home purchase or mortgage payoff, legacy or estate goals, charitable giving, emergency reserve target, risk tolerance, risk capacity, liquidity needs.

### 3. Accounts

For each account, capture: name, type, current balance, owner, tax treatment, contribution status, withdrawal restrictions, beneficiary concerns.

Account types: taxable brokerage, checking, savings, money market, traditional IRA, Roth IRA, 401(k), 403(b), 457, HSA, pension, annuity, trust, 529, employer stock plan, crypto wallet, real estate, business ownership, other assets.

### 4. Holdings

For each holding, capture: ticker or asset name, account where held, quantity, market value, cost basis, unrealized gain/loss, asset class, expense ratio, income yield, holding period, concentration concerns.

If asset class is unknown, infer cautiously and mark as an assumption.

### 5. Income

For each income source, capture: amount, frequency, start date or age, end date or age, taxability, inflation adjustment.

Income types: salary/wages, bonus, equity compensation, self-employment income, rental income, pension income, Social Security estimate, annuity income, interest/dividend income, other recurring income.

### 6. Expenses and Cash Flow

For each expense, capture: amount, frequency, start date or age, end date or age, inflation sensitivity, priority or flexibility.

Expense types: current annual spending, expected retirement spending, essential expenses, discretionary expenses, housing costs, mortgage or rent, insurance costs, healthcare costs, debt payments, planned large expenses, emergency fund target.

### 7. Liabilities

For each liability, capture: balance, interest rate, monthly payment, maturity date, tax deductibility, whether payoff is a goal.

Liability types: mortgage, credit card debt, student loans, auto loans, personal loans, business debt, margin loans, other liabilities.

### 8. Tax Profile

Capture: filing status, federal marginal bracket, state tax rate, capital gains bracket, taxable income estimate, carryforward losses, large unrealized gains, RMD relevance, Roth conversion interest, charitable giving interest, Medicare IRMAA sensitivity, tax preparer involvement.

Do not calculate detailed taxes unless a downstream tax skill is invoked.

### 9. Insurance, Estate, and Risk

Capture only if relevant or volunteered: life insurance, disability insurance, long-term care insurance, umbrella liability insurance, estate documents, trusts, beneficiary concerns, concentrated employer stock, business succession issues.

## Rules for Asking Follow-Up Questions

Ask follow-up questions only when the missing information materially affects the next step. Ask no more than 8 questions at once.

Prioritize in this order:
1. Age and retirement timeline
2. Current account balances
3. Annual spending need
4. Account types and tax treatment
5. Asset allocation or holdings
6. Income sources
7. Major future expenses
8. Cost basis for taxable assets
9. Tax profile
10. Risk tolerance and liquidity needs

If the user provides incomplete information, proceed with a partial intake and list missing information clearly.

If the user wants immediate modeling, collect minimum viable information: current age, retirement age, current portfolio value, annual spending need, current annual income, account types, rough asset allocation, major future cash flows, planning horizon, state and filing status.

## Handling Assumptions

Place all inferred or assumed facts in the `assumptions` array. Never hide assumptions inside the summary.

Examples:
- Assumed annual spending is in today's dollars.
- Assumed account balance is current market value.
- Assumed retirement spending begins at the stated retirement age.
- Assumed unspecified brokerage account is taxable.
- Assumed holdings are diversified unless concentration is stated.

## Validation Checks

Before returning output, check for:
- Account balances that do not add up
- Holdings that exceed account balance
- Missing tax treatment
- Missing retirement spending
- Missing retirement age
- Unclear nominal vs real dollar amounts
- Unclear monthly vs annual amounts
- Conflicting ages or dates
- Missing cost basis for taxable holdings
- Missing state for tax-sensitive analysis
- High concentration in one asset
- Large illiquid asset exposure
- Short cash runway

## Professional Review Flags

Add flags for: taxable trades with large gains, Roth conversions, RMD planning, estate planning, concentrated employer stock, options or equity compensation, business ownership, real estate investment sales, trusts, annuities, pensions, long-term care planning, cross-border tax issues, divorce/inheritance/major legal issues, any recommendation involving specific transactions.

## Tone

Use a professional, neutral, and structured tone. Be helpful and efficient. Avoid alarmist language and overconfidence. Make clear that this is an intake and organization step, not a final financial plan.

## Required Output Format

Return results in two parts:

### Part 1 — Human-Readable Summary

```markdown
## Intake Summary

[Brief summary of what is known.]

## Key Missing Information

[Prioritized list of missing items.]

## Assumptions

[List assumptions made.]

## Professional Review Flags

[List any flags.]

## Structured Intake JSON

```json
{ ... }
```
```

### Part 2 — Structured JSON

Emit a JSON object conforming to the machine-readable JSON Schema in
[`references/schema.json`](references/schema.json). The top-level keys are:
`household`, `goals`, `accounts`, `holdings`, `income`, `expenses`, `liabilities`,
`tax_profile`, `risk_profile`, `assumptions`, `missing_information`,
`conflicts_or_uncertainties`, `professional_review_flags`.

A fully worked example of a completed intake (the "$1.8M, retire at 60, spend $120K"
case) is in [`references/sample_intake.json`](references/sample_intake.json) — use it
as the output target for shape and for how to record partial data, assumptions, and
missing information.

This JSON is the handoff contract consumed by `portfolio-analysis` and
`longevity-modeling`; keep field names and nesting exactly as the schema specifies.

## Boundaries

You may organize data, identify gaps, and prepare inputs.

You may not:
- Recommend specific investments
- Give personalized tax advice
- Tell the user to execute trades
- Guarantee retirement success
- Present projections as certain
- Replace a licensed financial adviser, CPA, or attorney
