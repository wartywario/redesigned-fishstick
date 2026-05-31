# Tax Flag Rules Reference

Guidance for interpreting, phrasing, and applying each flag category.
All flags are considerations for CPA/adviser review — not advice or instructions.

---

## 1. Taxable gain/loss flags

**Trigger:** Embedded gains or losses in taxable accounts, computed per authoritative formulas.

**Phrase as:** "Potential consideration for CPA/adviser review: [holding] has an embedded [gain/loss] of [amount] ([pct]%)."

**Do not say:** "You should realize this gain" / "This will save taxes" / "Harvest this loss."

**Include:** Market value, cost basis, unrealized gain/loss, holding period (long/short-term), portfolio weight.

---

## 2. Cost-basis gaps

**Trigger:** Any taxable holding where `cost_basis` is null.

**Phrase as:** "Missing data: Cost basis unavailable for [holding] in taxable account [account]. Tax impact of any disposition cannot be assessed."

**Required action:** List in `input_quality.missing_information`. Do not estimate basis.

---

## 3. Concentrated low-basis holdings

**Trigger:** Taxable holding where embedded gain / market value > `low_basis_gain_pct_threshold` (default 30%) AND portfolio weight > `concentration_weight_threshold` (default 10%).

**Phrase as:** "Potential consideration for CPA/adviser review: [holding] represents [pct]% of the portfolio with an embedded gain of [pct]%. Rebalancing or disposition may generate a significant taxable gain. Do not act without professional review."

**Do not prescribe:** Do not say to sell, donate, or hedge.

---

## 4. Tax-loss harvesting review

**Trigger:** Taxable holding with unrealized loss < `loss_harvest_candidate_loss_amount_threshold` (default −$1,000) AND unrealized loss pct < `loss_harvest_candidate_loss_pct_threshold` (default −5%).

**Phrase as:** "Potential consideration for CPA/adviser review: [holding] shows an unrealized loss of [amount]. May be a candidate for tax-loss review. Do not execute any sale without professional review, including wash-sale rule analysis."

**Required note:** Always append "This is a review flag, not a sale recommendation."

---

## 5. Wash-sale review

**Trigger:** Loss position in a taxable holding AND `recent_purchase_date` or `recent_sale_date` is present on the holding.

**Phrase as:** "Potential wash-sale review needed: [holding] shows a loss position and recent transaction activity. The wash-sale rule may apply if substantially identical securities were purchased within 30 days before or after a loss sale. CPA review required before any action."

**Do not:** Conclude whether the wash-sale rule applies. That is a CPA determination.

---

## 6. Asset-location observations

**These are model-generated observations, not script flags.** The model reviews the `account_tax_treatment` on each holding and notes:

- Tax-inefficient assets (bonds, REITs, high-yield) in taxable accounts
- Growth assets in tax-free (Roth) accounts
- Cash in retirement accounts vs. bank accounts

**Phrase as:** "Observation for CPA/adviser consideration: [holding type] is held in a [taxable/tax-deferred/tax-free] account. Asset location may affect after-tax returns. Review with a financial adviser."

**Do not prescribe** a move. Asset location decisions depend on tax bracket, time horizon, and other factors.

---

## 7. Rebalancing tax sensitivity

**Trigger:** Rebalancing need (from portfolio-analysis drift flags) combined with embedded gains in taxable accounts.

**Phrase as:** "Potential consideration for CPA/adviser review: Rebalancing toward target allocation may require selling positions with embedded gains in taxable accounts. Tax impact should be evaluated before execution."

**Include in `rebalancing_tax_flags`:** Holdings with largest gains that would be affected by rebalancing.

---

## 8. Roth-conversion review windows

**Trigger:** Tax-deferred account(s) present AND any of:
- Client is within 15 years of RMD age
- Income expected to decrease
- Retirement expected within 10 years

**Phrase as:** "Potential consideration for CPA/adviser review: A Roth conversion planning discussion may be relevant ([reason]). The tax-deferred balance, current and future tax brackets, and RMD projections should be evaluated by a CPA or financial adviser before any conversion. This is not a conversion recommendation."

**Never say:** "You should convert" / "This will save taxes" / "Convert $X."

---

## 9. RMD and QCD review

**RMD trigger:** Client age ≥ `rmd_age` (73) AND has tax-deferred accounts → mandatory, high-priority flag.

**Approaching RMD trigger:** Client age ≥ `near_rmd_age` (70) AND < `rmd_age` → planning consideration flag.

**QCD trigger:** Client age ≥ `qcd_eligible_age` (70) AND charitable intent AND has tax-deferred accounts.

**RMD phrase:** "RMD review required: Client age [X] is at or past the RMD start age of [Y]. Required minimum distributions from tax-deferred accounts are mandatory. Amount and timing should be reviewed with a CPA or financial adviser."

**QCD phrase:** "Potential consideration for CPA/adviser review: Client age [X] is at or past QCD eligible age [Y] and has charitable intent and tax-deferred accounts. Qualified Charitable Distributions (QCDs) from IRAs may be relevant. Review with a CPA or adviser before any distribution."

---

## 10. Withdrawal sequencing context

**These are model-generated observations, not script flags.**

Note that a default withdrawal order (taxable → tax-deferred → Roth) is a modeling assumption only, not advice.

**Phrase as:** "Potential consideration for CPA/adviser review: Withdrawal sequencing from taxable, tax-deferred, and Roth accounts affects lifetime tax exposure. The optimal sequence depends on current and future tax rates, RMD requirements, and estate goals. Professional review is required before any withdrawal strategy is implemented."

---

## 11. IRMAA sensitivity

**Trigger (at Medicare age):** Client age ≥ `medicare_age` (65).

**Trigger (approaching):** Client age ≥ `near_medicare_age` (63) and < `medicare_age`.

**Phrase as:** "Potential consideration for CPA/adviser review: [Client is Medicare age / Client is N year(s) from Medicare age.] IRMAA brackets are based on MAGI from 2 years prior. Capital gains, Roth conversions, RMD amounts, or other income events may affect Medicare Part B and D premiums. Review with a CPA or adviser before any income-affecting action."

---

## 12. State-tax sensitivity

**Trigger:** State is provided AND state is not in the known zero-income-tax-state list.

**No-state trigger:** State is missing → data-gap flag.

**Phrase as:** "State tax sensitivity: [State] has a state income tax. Capital gains realizations, Roth conversions, RMD amounts, and other taxable income events may be subject to state income tax. Confirm rates and rules with a CPA."

**Do not** include specific state tax rates unless the user provided them.

---

## 13. Estate, trust, inheritance, equity compensation, business, and real estate

**Trigger:** Any of these fields are truthy in `tax_profile` or `planning_context`:
`equity_compensation`, `business_ownership`, `trust_involved`, `real_estate_sale`, `inheritance_or_estate`, `divorce`, `cross_border_tax`.

**Phrase as:** "Potential consideration for professional review: [brief description of the complex situation]. [Relevant professional — CPA, estate attorney, financial adviser] review required."

**Always flag as high priority.** These situations frequently involve non-standard tax rules (NUA, ESOP, QDRO, §1031, foreign accounts, step-up in basis, etc.).

---

## 14. Required professional-review language

Every flag must:
- Begin with "Potential consideration for CPA/adviser review:" OR "Missing data:" OR "Potential consideration:" OR "Observation for review:"
- Never contain "You should" / "You must" / "You will save" / "This is optimal" / "This guarantees"
- For high-priority items, end with or include: "CPA/adviser review required before any action" or equivalent

The `professional_review_flags` array collects the most important items across all categories for easy adviser handoff.
