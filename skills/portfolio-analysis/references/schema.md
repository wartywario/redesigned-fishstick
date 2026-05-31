# Portfolio Analysis — Schema & Calculator I/O

Load this file when assembling the final structured JSON or constructing calculator
inputs. Day-to-day reasoning does not need it in context.

## Bundled Calculator (`scripts/portfolio.py`)

Pure standard library (Python 3.8+, no dependencies). Deterministically computes
total value, holding weights, broad/detailed/tax-treatment allocation, per-account
allocation, drift vs. target (with the skill's threshold flags), concentration
flags, and cash runway.

**Always run this rather than computing allocation percentages, drift, or cash
runway by hand** — hand aggregation across many holdings/accounts is error-prone
and not reproducible.

### How to run

```
python scripts/portfolio.py input.json
# or
echo '{...}' | python scripts/portfolio.py
```

### Input object

```json
{
  "accounts": [
    { "name": "Taxable Brokerage", "type": "taxable_brokerage", "tax_treatment": "taxable", "balance": 700000 }
  ],
  "holdings": [
    {
      "account_name": "Taxable Brokerage",
      "ticker_or_name": "VTI",
      "market_value": 400000,
      "asset_class": "us_total_market_equity",
      "broad_asset_group": "equity",
      "is_employer_stock": false
    }
  ],
  "target_allocation": { "equity": 0.70, "fixed_income": 0.25, "cash": 0.05 },
  "annual_spending": null,
  "monthly_spending": null,
  "drift_thresholds": {}
}
```

Input notes:
- Provide at least one of `accounts` or `holdings`.
- For any account that has a `balance` but no listed holdings, the script
  synthesizes a single holding for the full balance, classifying the broad group
  from the account `type` (savings/checking/money_market → cash; real_estate →
  real_assets; annuity/pension → insurance_or_annuity; everything else → unknown).
  These appear with `"synthetic_from_account_balance": true` so the limitation is
  visible.
- `asset_class` / `broad_asset_group` must be supplied by the caller. Unknown or
  missing classes are surfaced (and flagged if > 10% of the portfolio), never guessed.
- `is_employer_stock: true` (or `asset_class: "employer_stock"`) triggers the
  employer-stock concentration threshold (5%) instead of the single-holding one (10%).
- `monthly_spending` (or `annual_spending`, divided by 12) enables cash-runway.
- `drift_thresholds` optionally overrides any default threshold (see below).

### Default thresholds (overridable via `drift_thresholds`)

| Key | Default | Meaning |
|---|---|---|
| `broad_drift_review` | 0.05 | broad group drift > 5pp → review |
| `broad_drift_high` | 0.10 | broad group drift > 10pp → high_priority_review |
| `detailed_drift_review` | 0.03 | detailed class drift > 3pp → review |
| `single_holding` | 0.10 | single holding > 10% → concentration_review |
| `employer_stock` | 0.05 | employer stock > 5% → employer_stock_review |
| `speculative` | 0.05 | crypto/speculative > 5% |
| `unknown_holding` | 0.10 | unclassified > 10% |
| `cash_reserve_months_low` | 3 | below → low cash reserve |
| `cash_reserve_months_high` | 24 | above → potential cash drag |

### Output object (shape)

```json
{
  "portfolio_summary": {
    "total_portfolio_value": 1500000,
    "sum_of_reported_account_balances": 1500000,
    "reconciliation_notes": [],
    "currency": "USD"
  },
  "current_allocation": {
    "broad_asset_group_allocation": {},
    "detailed_asset_class_allocation": {},
    "tax_treatment_allocation": {}
  },
  "account_allocation": [
    { "account_name": null, "account_value": null, "allocation": {} }
  ],
  "allocation_drift": {
    "calculated": false,
    "broad_asset_group_drift": {},
    "drift_flags": [],
    "largest_overweights": [],
    "largest_underweights": []
  },
  "concentration_analysis": {
    "largest_holdings": [],
    "single_holding_flags": [],
    "employer_stock_flags": [],
    "speculative_flags": [],
    "unknown_asset_flags": []
  },
  "liquidity_analysis": {
    "cash_balance": null,
    "monthly_spending_used": null,
    "cash_runway_months": null,
    "cash_reserve_classification": null,
    "notes": []
  },
  "holdings": []
}
```

## Final Response JSON Schema (full)

The model wraps the calculator output, adds qualitative fields it owns
(`data_quality`, `assumptions`, `tax_location_observations`,
`professional_review_flags`, etc.), and emits this:

```json
{
  "portfolio_summary": {
    "total_portfolio_value": null,
    "data_quality": null,
    "data_quality_notes": [],
    "analysis_date": null,
    "currency": "USD"
  },
  "accounts": [
    {
      "account_name": null,
      "account_type": null,
      "tax_treatment": null,
      "owner": null,
      "reported_balance": null,
      "calculated_holdings_value": null,
      "balance_difference": null,
      "allocation": {
        "equity": null,
        "fixed_income": null,
        "cash": null,
        "real_assets": null,
        "alternatives": null,
        "insurance_or_annuity": null,
        "unknown": null
      },
      "notes": []
    }
  ],
  "holdings": [
    {
      "account_name": null,
      "ticker_or_name": null,
      "holding_type": null,
      "market_value": null,
      "portfolio_weight": null,
      "asset_class": null,
      "broad_asset_group": null,
      "cost_basis": null,
      "unrealized_gain_loss": null,
      "expense_ratio": null,
      "income_yield": null,
      "classification_confidence": null,
      "assumptions": [],
      "notes": []
    }
  ],
  "current_allocation": {
    "broad_asset_group_allocation": {
      "equity": null,
      "fixed_income": null,
      "cash": null,
      "real_assets": null,
      "alternatives": null,
      "insurance_or_annuity": null,
      "unknown": null
    },
    "detailed_asset_class_allocation": {},
    "tax_treatment_allocation": {
      "taxable": null,
      "tax_deferred": null,
      "tax_free": null,
      "tax_advantaged_health": null,
      "education_tax_advantaged": null,
      "illiquid_or_nonportfolio_asset": null,
      "unknown": null
    }
  },
  "target_allocation": {
    "provided": false,
    "broad_asset_group_allocation": {},
    "detailed_asset_class_allocation": {},
    "source_or_notes": null
  },
  "allocation_drift": {
    "calculated": false,
    "broad_asset_group_drift": {},
    "detailed_asset_class_drift": {},
    "largest_overweights": [],
    "largest_underweights": [],
    "drift_flags": []
  },
  "concentration_analysis": {
    "largest_holdings": [],
    "single_holding_flags": [],
    "employer_stock_flags": [],
    "sector_flags": [],
    "illiquid_asset_flags": [],
    "unknown_asset_flags": []
  },
  "liquidity_analysis": {
    "cash_balance": null,
    "monthly_spending_used": null,
    "cash_runway_months": null,
    "cash_reserve_classification": null,
    "notes": []
  },
  "tax_location_observations": [
    {
      "topic": null,
      "observation": null,
      "accounts_or_holdings_involved": [],
      "review_with_tax_professional": false
    }
  ],
  "assumptions": [],
  "missing_information": [],
  "conflicts_or_uncertainties": [],
  "professional_review_flags": []
}
```
