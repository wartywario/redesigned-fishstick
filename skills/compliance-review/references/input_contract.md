# Compliance Review — Input Contract

## Pipeline position

```
... → reporting → compliance_review (GATE) → deliver
```

The compliance classifier runs on the assembled client-facing report (the
`reporting` stage output) plus the authoritative computed values from upstream
script stages (portfolio, longevity, tax). Its verdict is ratified by a human via
`guap.py <workdir> compliance pass|fail [--findings ...]`; the engine then blocks
or allows delivery through the existing `compliance_review` gate. The classifier
does **not** modify the case directly and there is **no** engine/registry change.

## Input shape

```json
{
  "report": {
    "narrative": "client-facing report text/markdown (required, non-empty string)",
    "cited_numbers": [
      {"label": "success probability", "value": 0.79,
       "authoritative_key": "longevity.success_probability"}
    ]
  },
  "authoritative_values": {
    "longevity.success_probability": 0.7891,
    "portfolio.total_portfolio_value": 2214117.1,
    "portfolio.equity_allocation": 0.63
  },
  "required_disclosures": ["advice_disclaimer", "professional_review", "not_a_guarantee"],
  "thresholds": {"numeric_tol_abs": 0.01, "numeric_tol_rel": 0.01}
}
```

### Fields

| Field | Required | Notes |
|---|---|---|
| `report.narrative` | **yes** | Non-empty string. Missing/blank → `{"error":"invalid_input"}`, exit 1. |
| `report.cited_numbers[]` | no | Each `{label, value, authoritative_key}`. Only entries whose `authoritative_key` appears in `authoritative_values` are checked. |
| `authoritative_values` | no | Flat `key → number` map of the engine's computed values. |
| `required_disclosures` | no | Defaults to `["advice_disclaimer","professional_review","not_a_guarantee"]`. Missing any of these is **blocking**. |
| `thresholds.numeric_tol_abs` | no | Default `0.01`. |
| `thresholds.numeric_tol_rel` | no | Default `0.01`. |

`past_performance` is checked as an **advisory** disclosure (its absence never
blocks); it is reported under `advisory_findings`.

## Authoritative-value keys (suggested)

The harness/driver populates `authoritative_values` from completed script stages:

| Key | Source |
|---|---|
| `portfolio.total_portfolio_value` | `portfolio_analysis.portfolio_summary.total_portfolio_value` |
| `portfolio.equity_allocation` | `portfolio_analysis.current_allocation.broad_asset_group_allocation.equity` |
| `longevity.success_probability` | `longevity_modeling.monte_carlo.success_probability` |

Keys are free-form strings; the only contract is that a `cited_numbers[i].authoritative_key`
must match a key in `authoritative_values` to be checked.

## CLI

```bash
python scripts/compliance.py input.json
# or
cat input.json | python scripts/compliance.py
```

Writes the verdict JSON to stdout. Exits non-zero on `invalid_input`.

## Output

See [`output_schema.json`](output_schema.json) and [`sample_output.json`](sample_output.json).
`verdict` is `"fail"` when any `blocking_findings` exist, else `"pass"`.
