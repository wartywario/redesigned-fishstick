# Tax Considerations — Input Contract

## Pipeline position

```
wealth-intake → portfolio-analysis → tax-considerations → rebalancing
                                                        → longevity-modeling
                                                        → scenario-analysis
                                                        → reporting
```

## Upstream field mapping

If upstream skill outputs are unavailable, proceed with partial inputs and list
all missing fields in `input_quality.missing_information`.

| Source skill | Source field | Tax skill field | Notes |
|---|---|---|---|
| wealth-intake | `household.client_age` | `household.client_age` | RMD, Medicare, QCD, planning-window flags |
| wealth-intake | `household.partner_age` | `household.partner_age` | Household-level planning; optional |
| wealth-intake | `household.state` | `household.state` | State income-tax sensitivity flags |
| wealth-intake | `household.filing_status` | `household.filing_status` | Bracket-sensitive review questions |
| wealth-intake | `accounts[]` | `accounts[]` | Account type, owner, balance, tax treatment |
| wealth-intake | `holdings[]` | `holdings[]` | Cost basis, market value, gain/loss, holding period |
| wealth-intake | `income[]` | `income[]` | Roth-conversion and income-window flags |
| wealth-intake | `expenses[]` | `planning_context.expenses[]` | Withdrawal-sequencing context only |
| wealth-intake | `tax_profile` | `tax_profile` | Existing known tax facts |
| portfolio-analysis | `portfolio_summary.total_portfolio_value` | `portfolio.total_value` | Denominator for concentration and embedded-gain flags |
| portfolio-analysis | `current_allocation` | `portfolio.current_allocation` | Context for asset-location observations |
| portfolio-analysis | `account_allocation[]` | `portfolio.account_level_allocation[]` | Account-location review |
| portfolio-analysis | `concentration_analysis` | `portfolio.concentration_risks[]` | Augmented with tax sensitivity |

## Required minimum fields (script will run with partial data but quality degrades)

- `accounts[]` or `holdings[]` — at least one required; script errors without either
- `household.client_age` — required for age-based flags (RMD, IRMAA, Roth, QCD)
- `household.state` — required for state tax flags
- `portfolio.total_value` or inferrable from accounts/holdings — required for concentration and embedded-gain percentage calculations

## Optional fields that enable additional flags

| Field | Enables |
|---|---|
| `holdings[].cost_basis` | Gain/loss calculations; missing triggers data-gap flag |
| `holdings[].holding_period` | Short/long-term classification; missing = unknown |
| `holdings[].recent_purchase_date` | Wash-sale review flag |
| `holdings[].recent_sale_date` | Wash-sale review flag |
| `tax_profile.charitable_giving_interest` | Charitable/QCD flags |
| `planning_context.income_expected_to_decrease` | Roth conversion window flag |
| `planning_context.retirement_within_10_years` | Roth conversion window flag |
| `planning_context.charitable_intent` | Charitable/QCD flags |
| `planning_context.equity_compensation` | Estate/special-situation flag |
| `planning_context.business_ownership` | Estate/special-situation flag |
| `planning_context.trust_involved` | Estate/special-situation flag |
| `planning_context.real_estate_sale` | Estate/special-situation flag |
| `planning_context.inheritance_or_estate` | Estate/special-situation flag |
| `thresholds{}` | Override any default flag threshold |

## Threshold defaults (all overridable via `thresholds` input key)

| Threshold | Default | Meaning |
|---|---|---|
| `concentration_weight_threshold` | 0.10 | Taxable holding > 10% of portfolio |
| `low_basis_gain_pct_threshold` | 0.30 | Embedded gain > 30% of market value |
| `large_embedded_gain_portfolio_pct_threshold` | 0.05 | Single gain > 5% of portfolio |
| `loss_harvest_candidate_loss_pct_threshold` | -0.05 | Unrealized loss < −5% |
| `loss_harvest_candidate_loss_amount_threshold` | -1000 | Unrealized loss < −$1,000 |
| `near_rmd_age` | 70 | Age at which to issue approaching-RMD flag |
| `rmd_age` | 73 | Age at which RMDs become mandatory |
| `near_medicare_age` | 63 | Age at which to issue approaching-IRMAA flag |
| `medicare_age` | 65 | Age at which Medicare / IRMAA applies |
| `qcd_eligible_age` | 70 | Age at which QCDs from IRAs become available |

## Downstream handoff fields

The script emits `downstream_handoff` with these sub-objects:

| Consumer skill | Key | Content |
|---|---|---|
| rebalancing | `downstream_handoff.for_rebalancing` | Embedded gains/losses, loss-harvest candidates, missing-basis accounts |
| longevity-modeling | `downstream_handoff.for_longevity_modeling` | State income-tax presence, state code |
| scenario-analysis | `downstream_handoff.for_scenario_analysis` | High-priority flags, tax-sensitive flag presence |
| reporting | `downstream_handoff.for_reporting` | Coverage rate, net embedded gain/loss, total flag count |
