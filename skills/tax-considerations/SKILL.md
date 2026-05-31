---
name: tax-considerations
description: Analyze tax-sensitive wealth-planning inputs, flag missing data, surface tax considerations, and prepare CPA/adviser review questions for rebalancing, withdrawals, Roth conversions, RMDs, taxable gains, charitable giving, and IRMAA.
version: 1.0.0
---

# Tax Considerations Skill

## Purpose

Identify tax-sensitive planning issues, organize tax-related facts from intake and portfolio
outputs, run deterministic flag calculations using `scripts/tax_flags.py`, surface missing
inputs and uncertainty, and produce review-ready considerations for downstream rebalancing,
withdrawal, longevity-modeling, and reporting skills.

**This is not tax advice. This is not legal advice. This is not investment advice.**
Do not recommend specific trades, Roth conversions, withdrawals, or tax strategies as final
actions. Require qualified professional review before any execution.

## When to Use This Skill

Activate when the user asks about or provides information involving: taxable brokerage
accounts, cost basis, unrealized gains or losses, capital gains realization, tax-loss
harvesting, wash-sale concerns, Roth conversion, withdrawal sequencing, required minimum
distributions, asset location, charitable giving or QCDs, estate or trust tax issues,
equity compensation or employer stock, concentrated low-basis positions, state tax
exposure, Medicare IRMAA, tax drag in projections, or rebalancing in taxable accounts.

## Core Rule

The skill may identify issues and questions. It may not prescribe final tax actions.

Use language such as: "Potential consideration for CPA/adviser review" / "This may be
tax-sensitive" / "Data needed before evaluating this" / "Do not execute without professional
review."

Avoid: "You should sell" / "You should convert" / "This will save taxes" / "This is the
optimal strategy" / "Guarantees."

## Calculator (required — do not compute flags by hand)

All gain/loss aggregation and threshold flagging must be produced by `scripts/tax_flags.py`.
Do not compute embedded gains, loss percentages, or portfolio weights by hand.

```
python scripts/tax_flags.py input.json
# or
cat input.json | python scripts/tax_flags.py
```

The script accepts JSON, validates inputs, and returns structured flag output. Run it once
per analysis. Use its output as the foundation for the final response.

Input/output shapes, all threshold defaults, and the override mechanism are documented in
[`references/input_contract.md`](references/input_contract.md).

## AUTHORITATIVE FORMULAS — DO NOT DEVIATE

```
position_unrealized_gain_loss = market_value - cost_basis
position_unrealized_gain_loss_pct = position_unrealized_gain_loss / market_value
    (null when market_value <= 0 or cost_basis is null)
position_portfolio_weight = market_value / total_portfolio_value
    (null when total_portfolio_value <= 0)
taxable_embedded_gain_total = sum(max(market_value - cost_basis, 0)
    for taxable holdings with known market_value and cost_basis)
taxable_embedded_loss_total = sum(min(market_value - cost_basis, 0)
    for taxable holdings with known market_value and cost_basis)
net_taxable_embedded_gain_loss = taxable_embedded_gain_total + taxable_embedded_loss_total
known_taxable_basis_coverage = taxable_market_value_with_known_basis / taxable_market_value
    (null when taxable_market_value <= 0)
```

These same formulas are in the script docstring. The script implements them; always use
the script output, not token-by-token arithmetic.

## Pipeline Position

```
wealth-intake → portfolio-analysis → tax-considerations → rebalancing
                                                        → longevity-modeling
                                                        → scenario-analysis
                                                        → reporting
```

Field mapping from upstream skills is in [`references/input_contract.md`](references/input_contract.md).
If upstream data is unavailable, proceed with partial inputs and list every missing field
in `input_quality.missing_information`.

## Validation Checks

Before producing output, verify:
- Are taxable account holdings missing cost basis?
- Are account types and tax treatments known for all accounts?
- Does `portfolio.total_value` exist or need to be inferred from account balances?
- Is cost-basis coverage sufficient for taxable-account analysis?
- Are holding periods known for taxable holdings?
- Are state, filing status, and estimated taxable income known?
- Are large taxable gains or concentrated taxable positions present?
- Are there tax-deferred accounts and RMD-relevant ages?
- Are charitable goals present for QCD/DAF flag evaluation?
- Are income-changing events present for IRMAA review?
- Are equity compensation, employer stock, business ownership, trusts, real estate,
  inheritance, divorce, or cross-border issues present?

Surface unknowns; do not guess.

## Flag Rules

Phrasing rules and trigger conditions for all 14 flag categories are in
[`references/tax_flag_rules.md`](references/tax_flag_rules.md).

Summary of flag categories produced by the script:
- Missing cost basis / unknown account type (data gaps)
- Concentration in taxable positions
- Low-basis holdings (embedded gain > 30% of market value)
- Large embedded gains (> 5% of portfolio value)
- Loss-harvest candidates (with "not a sale recommendation" note)
- Wash-sale review (when recent activity + loss position)
- RMD review (mandatory at 73, planning consideration approaching 70)
- Roth conversion window (considerations only — never a recommendation)
- Charitable giving / QCD (age-gated, intent-gated)
- IRMAA sensitivity (Medicare age and approaching)
- State income tax sensitivity
- Estate and special-situation flags (equity comp, business, trust, real estate, etc.)

## Required Output Format

```markdown
## Tax Considerations Summary

[Brief, specific summary. No advice. No transaction instructions.]

## Key Missing Information

[Prioritized list of missing data that materially affects tax analysis.]

## Tax-Sensitive Flags for Review

[Grouped: taxable gains/losses, rebalancing, withdrawals, Roth conversions, RMDs,
charitable/QCD, IRMAA, state tax, special situations.]

## Questions for CPA / Adviser Review

[Practical questions the user or adviser should answer before taking action.]

## Downstream Handoff

[Summary of fields passed to rebalancing, longevity modeling, scenario analysis, reporting.]

## Structured Tax Considerations JSON

```json
{ ... }
```
```

The structured JSON must conform to [`references/output_schema.json`](references/output_schema.json).
A fully worked example is in [`references/sample_output.json`](references/sample_output.json).

## Boundaries

**May:** Summarize tax facts. Identify missing information. Aggregate embedded gains and
losses using the script. Flag areas for review. Explain why something is tax-sensitive at a
high level. Generate questions for a CPA, financial planner, or attorney. Prepare structured
handoff data.

**May not:** Tell the user to buy, sell, convert, harvest, or realize anything. Give a
definitive tax liability estimate without complete data and explicit rates. Claim a strategy
will reduce taxes. Replace professional tax, legal, or investment advice. Ignore missing
basis, account type, state, filing status, or income data.
