# Reporting — Upstream Field Mapping

Reporting performs **no calculations**. It reads validated outputs from upstream
skills and assembles them. This file maps each reporting section to the **actual
field names those skills emit** (verified against the built skills, not aspirational
names). Use these exact paths when reading upstream objects. If an upstream object
is absent, mark the section unavailable — never invent or recompute the number.

## Built upstream skills and their real top-level output keys

| Skill | Actual top-level output keys |
|---|---|
| `wealth-intake` | `household`, `goals`, `accounts`, `holdings`, `income`, `expenses`, `liabilities`, `tax_profile`, `risk_profile`, `assumptions`, `missing_information`, `conflicts_or_uncertainties`, `professional_review_flags` |
| `portfolio-analysis` | `portfolio_summary`, `accounts`, `holdings`, `current_allocation`, `target_allocation`, `allocation_drift`, `concentration_analysis`, `liquidity_analysis`, `tax_location_observations`, `assumptions`, `missing_information`, `conflicts_or_uncertainties`, `professional_review_flags` |
| `longevity-modeling` | `model_metadata`, `inputs_used`, `base_case_results`, `monte_carlo_results`, `scenario_results`, `sensitivity_analysis`, `year_by_year_projection`, `assumptions`, `missing_information`, `warnings`, `professional_review_flags` |
| `tax-considerations` | `tax_considerations_summary`, `input_quality`, `taxable_gain_loss_snapshot`, `account_tax_treatment_review`, `asset_location_observations`, `rebalancing_tax_flags`, `withdrawal_tax_flags`, `roth_conversion_review_flags`, `rmd_review_flags`, `charitable_giving_review_flags`, `irmaa_review_flags`, `estate_and_special_situation_flags`, `missing_information`, `unknowns`, `professional_review_flags`, `downstream_handoff` |

## Not-yet-built skills (treat as optional / unavailable)

`rebalancing`, `scenario-analysis`, and `compliance-review` are referenced by the
report structure but are **not part of the current suite**. When their outputs are
absent, omit or mark the corresponding section "not reviewed" — this is expected,
not an error. Do not fabricate their fields.

## Section → real upstream field map

| Reporting Section | Real upstream path(s) | If absent |
|---|---|---|
| Executive Summary | `wealth_intake.goals`; `portfolio_analysis.portfolio_summary.total_portfolio_value` + `.current_allocation.broad_asset_group_allocation`; `longevity_modeling.base_case_results` + `.monte_carlo_results.success_probability`; consolidated `*.professional_review_flags` | Write a limited summary; list missing sections |
| Household & Goals | `wealth_intake.household`, `wealth_intake.goals` | Ask for intake or mark unavailable |
| Current Portfolio | `portfolio_analysis.portfolio_summary.total_portfolio_value`; `portfolio_analysis.current_allocation.broad_asset_group_allocation`; `portfolio_analysis.concentration_analysis` (`single_holding_flags`, `employer_stock_flags`, `largest_holdings`); `portfolio_analysis.liquidity_analysis` | Do not compute; mark unavailable |
| Longevity Outlook | `longevity_modeling.base_case_results` (`initial_withdrawal_rate`, `ending_portfolio_value`, `depletion_age`); `longevity_modeling.monte_carlo_results` (`success_probability`, `median_ending_value`, `p10_ending_value`); `longevity_modeling.sensitivity_analysis.most_sensitive_variables` | Do not infer; mark unavailable |
| Scenario Comparison | `scenario_analysis.*` if built; otherwise `longevity_modeling.scenario_results[]` (`name`, `description`, `depletion_age`, `interpretation`) | Omit if neither present |
| Tax Considerations | `tax_considerations.*` flag arrays; `tax_considerations.asset_location_observations`; `tax_considerations.taxable_gain_loss_snapshot`; `tax_considerations.professional_review_flags` | State tax review was not performed |
| Rebalancing Observations | `rebalancing.*` (not built) | Omit or mark "not reviewed" |
| Key Risks & Sensitivities | `longevity_modeling.sensitivity_analysis`; `longevity_modeling.warnings`; upstream `conflicts_or_uncertainties` | Preserve all material items |
| Missing Information / Data Quality | every upstream `missing_information`; `portfolio_analysis.portfolio_summary.data_quality`; `tax_considerations.input_quality`; `tax_considerations.unknowns` | Preserve all items |
| Professional Review Items | concatenated `professional_review_flags` from `wealth_intake`, `portfolio_analysis`, `longevity_modeling`, `tax_considerations` | Include consolidated list |
| Appendix: Assumptions | every upstream `assumptions`; `longevity_modeling.inputs_used.assumptions` | List what is available |

## Adapter-note rule

When an upstream object you are handed uses a field name that differs from the
paths above (e.g. an older output, or a hand-assembled object), record the actual
name and the path you mapped it to in **Appendix B: Source Handoff Map**, so every
number in the report remains traceable. Never silently rename.
