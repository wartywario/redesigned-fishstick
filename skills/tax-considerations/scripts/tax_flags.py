#!/usr/bin/env python3
"""
Tax-flag calculator for the tax-considerations skill.
Pure Python 3.8+ standard library. No external dependencies.
Reads JSON (file path as argv[1], or stdin). Writes JSON to stdout.

AUTHORITATIVE FORMULAS — DO NOT DEVIATE

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

This script flags and aggregates. It does not compute tax liability.
All outputs are considerations for CPA/adviser review, not advice.
"""

import json
import sys

# ── account type classification ────────────────────────────────────────────────

TAXABLE_TYPES = {"taxable_brokerage", "checking", "savings", "money_market", "crypto_wallet"}
TAX_DEFERRED_TYPES = {"traditional_ira", "sep_ira", "simple_ira", "401k", "403b", "457", "pension"}
TAX_FREE_TYPES = {"roth_ira"}
HEALTH_TYPES = {"hsa"}
EDUCATION_TYPES = {"529"}
ILLIQUID_TYPES = {"real_estate", "business_interest", "annuity"}

# States with no broad-based personal income tax (approximate; always verify with CPA)
NO_INCOME_TAX_STATES = {"AK", "FL", "NV", "SD", "TX", "WA", "WY", "TN", "NH"}

# ── default thresholds ─────────────────────────────────────────────────────────

DEFAULTS = {
    "concentration_weight_threshold": 0.10,
    "low_basis_gain_pct_threshold": 0.30,
    "large_embedded_gain_portfolio_pct_threshold": 0.05,
    "loss_harvest_candidate_loss_pct_threshold": -0.05,
    "loss_harvest_candidate_loss_amount_threshold": -1000,
    "near_rmd_age": 70,
    "rmd_age": 73,
    "near_medicare_age": 63,
    "medicare_age": 65,
    "qcd_eligible_age": 70,
}

# ── helpers ────────────────────────────────────────────────────────────────────

def _n(x):
    """Return x if numeric, else None."""
    return x if isinstance(x, (int, float)) else None


def _g(d, *keys, default=None):
    """Safe nested get."""
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k)
        if d is None:
            return default
    return d if d is not None else default


def _infer_tax_treatment(atype):
    t = (atype or "").lower().replace("-", "_").replace(" ", "_")
    if t in TAXABLE_TYPES:       return "taxable"
    if t in TAX_DEFERRED_TYPES:  return "tax_deferred"
    if t in TAX_FREE_TYPES:      return "tax_free"
    if t in HEALTH_TYPES:        return "tax_advantaged_health"
    if t in EDUCATION_TYPES:     return "education_tax_advantaged"
    if t in ILLIQUID_TYPES:      return "illiquid_or_nonportfolio_asset"
    return "unknown"


def _classify_holding_period(hp):
    if hp is None:
        return "unknown"
    s = str(hp).lower()
    if "long" in s:   return "long_term"
    if "short" in s:  return "short_term"
    return "unknown"


def _fmt_pct(v):
    if v is None: return "unknown %"
    return f"{v*100:.1f}%"


def _fmt_money(v):
    if v is None: return "$?"
    if v < 0: return f"-${abs(v):,.0f}"
    return f"${v:,.0f}"

# ── account map ────────────────────────────────────────────────────────────────

def build_account_map(accounts):
    """Return {account_name: {type, tax_treatment, balance}} for each account."""
    m = {}
    for a in (accounts or []):
        name = a.get("name")
        if not name:
            continue
        atype = (a.get("type") or "").lower()
        tt = a.get("tax_treatment") or _infer_tax_treatment(atype)
        m[name] = {
            "type": atype,
            "tax_treatment": tt,
            "balance": _n(a.get("balance")),
        }
    return m


# ── portfolio total ────────────────────────────────────────────────────────────

def resolve_portfolio_total(cfg, acct_map, holdings):
    pv = _n(_g(cfg, "portfolio", "total_value"))
    if pv and pv > 0:
        return pv, "provided"
    total_acct = sum(v["balance"] or 0 for v in acct_map.values() if v.get("balance"))
    if total_acct > 0:
        return total_acct, "calculated_from_accounts"
    total_h = sum(_n(h.get("market_value")) or 0 for h in (holdings or []))
    if total_h > 0:
        return total_h, "calculated_from_holdings"
    return None, "missing"


# ── per-holding enrichment ─────────────────────────────────────────────────────

def enrich_holdings(holdings, acct_map, total_value):
    result = []
    for h in (holdings or []):
        mv       = _n(h.get("market_value"))
        basis    = _n(h.get("cost_basis"))
        acct     = h.get("account_name")
        acct_info = acct_map.get(acct, {})
        tt = acct_info.get("tax_treatment") or _infer_tax_treatment(acct_info.get("type", ""))
        hp = _classify_holding_period(h.get("holding_period"))

        # Authoritative formulas
        ugl      = round(mv - basis, 2) if mv is not None and basis is not None else None
        ugl_pct  = round(ugl / mv, 4) if (ugl is not None and mv and mv > 0) else None
        weight   = round(mv / total_value, 4) if (mv is not None and total_value and total_value > 0) else None

        result.append({
            "ticker_or_name":          h.get("ticker_or_name"),
            "account_name":            acct,
            "account_tax_treatment":   tt,
            "market_value":            mv,
            "cost_basis":              basis,
            "holding_period":          hp,
            "unrealized_gain_loss":    ugl,
            "unrealized_gain_loss_pct": ugl_pct,
            "portfolio_weight":        weight,
            "is_taxable":              tt == "taxable",
            "has_basis":               basis is not None,
            "recent_purchase_date":    h.get("recent_purchase_date"),
            "recent_sale_date":        h.get("recent_sale_date"),
        })
    return result


# ── gain/loss aggregation ──────────────────────────────────────────────────────

def aggregate_taxable_gain_loss(enriched):
    """Compute portfolio-level taxable gain/loss per authoritative formulas."""
    taxable_mv = taxable_mv_basis = 0.0
    gain_total = loss_total = 0.0
    lt_gain = lt_loss = st_gain = st_loss = 0.0

    for h in enriched:
        if not h["is_taxable"]:
            continue
        mv  = h["market_value"] or 0.0
        ugl = h["unrealized_gain_loss"]
        taxable_mv += mv
        if h["has_basis"] and ugl is not None:
            taxable_mv_basis += mv
            gain_total += max(ugl, 0)
            loss_total += min(ugl, 0)
            hp = h["holding_period"]
            if hp == "long_term":
                lt_gain += max(ugl, 0)
                lt_loss += min(ugl, 0)
            elif hp == "short_term":
                st_gain += max(ugl, 0)
                st_loss += min(ugl, 0)

    coverage = round(taxable_mv_basis / taxable_mv, 4) if taxable_mv > 0 else None

    return {
        "taxable_market_value":                 round(taxable_mv, 2),
        "taxable_market_value_with_known_basis": round(taxable_mv_basis, 2),
        "known_taxable_basis_coverage":         coverage,
        "taxable_embedded_gain_total":          round(gain_total, 2),
        "taxable_embedded_loss_total":          round(loss_total, 2),
        "net_taxable_embedded_gain_loss":       round(gain_total + loss_total, 2),
        "long_term_gain_total":                 round(lt_gain, 2),
        "long_term_loss_total":                 round(lt_loss, 2),
        "short_term_gain_total":                round(st_gain, 2),
        "short_term_loss_total":                round(st_loss, 2),
    }


# ── flag generators ────────────────────────────────────────────────────────────

def flag_missing_basis(enriched, missing_info, unknowns):
    flags = []
    for h in enriched:
        if h["is_taxable"] and not h["has_basis"]:
            msg = (f"Missing cost basis: {h['ticker_or_name']} in taxable account "
                   f"'{h['account_name']}'. Tax impact of any disposition cannot be "
                   f"assessed without basis data.")
            flags.append({"holding": h["ticker_or_name"], "account": h["account_name"],
                          "flag": msg, "severity": "data_gap"})
            missing_info.append(f"Cost basis for {h['ticker_or_name']} ({h['account_name']})")
    return flags


def flag_unknown_account_type(enriched, acct_map, unknowns):
    flags = []
    seen = set()
    for h in enriched:
        acct = h["account_name"]
        if acct and acct not in seen:
            tt = h["account_tax_treatment"]
            if tt == "unknown":
                msg = (f"Account '{acct}' has unknown tax treatment. Tax-sensitive "
                       f"analysis for its holdings cannot be classified.")
                flags.append({"account": acct, "flag": msg, "severity": "data_gap"})
                unknowns.append(f"Tax treatment for account '{acct}'")
                seen.add(acct)
    return flags


def flag_concentration(enriched, thr, total_value):
    flags = []
    for h in enriched:
        if not h["is_taxable"]:
            continue
        w = h["portfolio_weight"]
        if w and w > thr["concentration_weight_threshold"]:
            flags.append({
                "holding": h["ticker_or_name"],
                "account": h["account_name"],
                "portfolio_weight": w,
                "flag": (f"Potential consideration for review: {h['ticker_or_name']} "
                         f"represents {_fmt_pct(w)} of total portfolio and is held in a "
                         f"taxable account. Concentration in a taxable position may create "
                         f"tax-sensitive rebalancing or disposition constraints."),
                "severity": "review",
            })
    return flags


def flag_low_basis(enriched, thr):
    flags = []
    for h in enriched:
        if not h["is_taxable"] or not h["has_basis"]:
            continue
        pct = h["unrealized_gain_loss_pct"]
        if pct is not None and pct > thr["low_basis_gain_pct_threshold"]:
            flags.append({
                "holding": h["ticker_or_name"],
                "account": h["account_name"],
                "unrealized_gain_loss": h["unrealized_gain_loss"],
                "unrealized_gain_loss_pct": pct,
                "holding_period": h["holding_period"],
                "flag": (f"Potential consideration for CPA/adviser review: "
                         f"{h['ticker_or_name']} has an embedded gain of {_fmt_pct(pct)} "
                         f"(basis {_fmt_money(h['cost_basis'])}, market value "
                         f"{_fmt_money(h['market_value'])}). Disposition or rebalancing "
                         f"may generate a taxable gain."),
                "severity": "review",
            })
    return flags


def flag_large_embedded_gains(enriched, thr, total_value):
    flags = []
    if not total_value:
        return flags
    for h in enriched:
        if not h["is_taxable"] or not h["has_basis"]:
            continue
        ugl = h["unrealized_gain_loss"]
        if ugl and ugl > 0:
            gain_pct_of_portfolio = ugl / total_value
            if gain_pct_of_portfolio > thr["large_embedded_gain_portfolio_pct_threshold"]:
                flags.append({
                    "holding": h["ticker_or_name"],
                    "account": h["account_name"],
                    "unrealized_gain": ugl,
                    "gain_as_pct_of_portfolio": round(gain_pct_of_portfolio, 4),
                    "flag": (f"Potential consideration for CPA/adviser review: "
                             f"{h['ticker_or_name']} has an embedded gain of {_fmt_money(ugl)}, "
                             f"representing {_fmt_pct(gain_pct_of_portfolio)} of total portfolio "
                             f"value. A disposition event could generate a material taxable gain."),
                    "severity": "high_priority_review",
                })
    return flags


def flag_loss_harvest_candidates(enriched, thr):
    flags = []
    for h in enriched:
        if not h["is_taxable"] or not h["has_basis"]:
            continue
        ugl = h["unrealized_gain_loss"]
        pct = h["unrealized_gain_loss_pct"]
        if (ugl is not None and ugl < thr["loss_harvest_candidate_loss_amount_threshold"]
                and pct is not None and pct < thr["loss_harvest_candidate_loss_pct_threshold"]):
            flags.append({
                "holding": h["ticker_or_name"],
                "account": h["account_name"],
                "unrealized_loss": ugl,
                "unrealized_loss_pct": pct,
                "holding_period": h["holding_period"],
                "flag": (f"Potential consideration for CPA/adviser review: "
                         f"{h['ticker_or_name']} shows an unrealized loss of {_fmt_money(ugl)} "
                         f"({_fmt_pct(pct)}). May be a candidate for tax-loss review. "
                         f"Do not execute any sale without professional review, including "
                         f"wash-sale rule analysis."),
                "severity": "review",
                "note": "This is a review flag, not a sale recommendation.",
            })
    return flags


def flag_wash_sale_review(enriched):
    """Flag when both recent purchase/sale data and a loss position exist."""
    flags = []
    for h in enriched:
        if not h["is_taxable"]:
            continue
        ugl = h["unrealized_gain_loss"]
        has_loss = ugl is not None and ugl < 0
        has_recent_activity = h.get("recent_purchase_date") or h.get("recent_sale_date")
        if has_loss and has_recent_activity:
            flags.append({
                "holding": h["ticker_or_name"],
                "account": h["account_name"],
                "flag": (f"Potential wash-sale review needed: {h['ticker_or_name']} shows "
                         f"a loss position and recent transaction activity. The wash-sale rule "
                         f"may apply if substantially identical securities were purchased within "
                         f"30 days before or after a loss sale. CPA review required before "
                         f"any action."),
                "severity": "high_priority_review",
            })
    return flags


def flag_rmd(household, acct_map, thr):
    flags = []
    age = _n(_g(household, "client_age"))
    if age is None:
        return flags

    has_tax_deferred = any(v["tax_treatment"] == "tax_deferred" for v in acct_map.values())
    if not has_tax_deferred:
        return flags

    rmd_age  = thr["rmd_age"]
    near_age = thr["near_rmd_age"]

    if age >= rmd_age:
        flags.append({
            "client_age": age,
            "flag": (f"RMD review required: Client age {age} is at or past the RMD start age "
                     f"of {rmd_age}. Required minimum distributions from tax-deferred accounts "
                     f"are mandatory. Amount and timing should be reviewed with a CPA or "
                     f"financial adviser. Failure to take RMDs may result in a significant "
                     f"excise tax."),
            "severity": "high_priority_review",
        })
    elif age >= near_age:
        flags.append({
            "client_age": age,
            "years_to_rmd": rmd_age - age,
            "flag": (f"Approaching RMD age: Client is {age}, approximately {rmd_age - age} "
                     f"year(s) from RMD start age {rmd_age}. Review of tax-deferred balances "
                     f"and RMD projections is a potential consideration for CPA/adviser planning."),
            "severity": "review",
        })
    return flags


def flag_roth_conversion(household, acct_map, income_data, planning, thr):
    flags = []
    age = _n(_g(household, "client_age"))
    if age is None:
        return flags

    has_tax_deferred = any(v["tax_treatment"] == "tax_deferred" for v in acct_map.values())
    if not has_tax_deferred:
        return flags

    rmd_age = thr["rmd_age"]

    # Per spec: flag a Roth-conversion window ONLY when income appears temporarily
    # low OR retirement-before-RMD data is supplied. Pre-RMD age alone is NOT a
    # trigger (that would fire for anyone still working with a tax-deferred account).
    years_to_rmd = rmd_age - age if age < rmd_age else 0
    income_decreasing = _g(planning, "income_expected_to_decrease", default=False)
    retirement_within_10 = _g(planning, "retirement_within_10_years", default=False)
    conversion_interest = _g(planning, "roth_conversion_interest", default=None)

    if conversion_interest is False:
        return flags  # User has explicitly indicated no interest

    # The flag is meaningful only before RMDs begin.
    window_open = (age < rmd_age) and (income_decreasing or retirement_within_10)

    if window_open:
        reason_parts = []
        if 0 < years_to_rmd <= 15:
            reason_parts.append(f"{years_to_rmd} year(s) before RMD start age {rmd_age}")
        if income_decreasing:
            reason_parts.append("income expected to decrease")
        if retirement_within_10:
            reason_parts.append("retirement expected within 10 years")

        reason = "; ".join(reason_parts) if reason_parts else "pre-RMD planning window"

        flags.append({
            "client_age": age,
            "years_to_rmd_start": years_to_rmd,
            "flag": (f"Potential consideration for CPA/adviser review: A Roth conversion "
                     f"planning discussion may be relevant ({reason}). The tax-deferred "
                     f"balance, current and future tax brackets, and RMD projections should "
                     f"be evaluated by a CPA or financial adviser before any conversion. "
                     f"This is not a conversion recommendation."),
            "severity": "review",
            "note": "This is a planning consideration flag, not a conversion recommendation.",
        })
    return flags


def flag_charitable(household, tax_profile, planning, acct_map, thr):
    flags = []
    age = _n(_g(household, "client_age"))
    charitable_intent = (
        _g(tax_profile, "charitable_giving_interest")
        or _g(planning, "charitable_intent")
    )

    if not charitable_intent:
        return flags

    qcd_age = thr["qcd_eligible_age"]
    has_tax_deferred = any(v["tax_treatment"] == "tax_deferred" for v in acct_map.values())

    if age is not None and age >= qcd_age and has_tax_deferred:
        flags.append({
            "client_age": age,
            "flag": (f"Potential consideration for CPA/adviser review: Client age {age} is "
                     f"at or past QCD eligible age {qcd_age} and has charitable intent and "
                     f"tax-deferred accounts. Qualified Charitable Distributions (QCDs) from "
                     f"IRAs may be relevant. Review with a CPA or adviser before any "
                     f"distribution."),
            "severity": "review",
        })
    elif charitable_intent:
        flags.append({
            "client_age": age,
            "flag": ("Potential consideration for CPA/adviser review: Charitable intent is "
                     "noted. Strategies such as donor-advised funds, bunching of charitable "
                     "deductions, or appreciated-asset gifting may be relevant to review. "
                     "Do not execute any charitable giving strategy without professional "
                     "guidance."),
            "severity": "review",
        })
    return flags


def flag_irmaa(household, income_data, planning, thr):
    flags = []
    age = _n(_g(household, "client_age"))
    if age is None:
        return flags

    med_age  = thr["medicare_age"]
    near_age = thr["near_medicare_age"]

    # Per spec: flag IRMAA review for Medicare-age or near-Medicare-age users ONLY
    # when potential income-changing events are present. Age alone is not a trigger.
    income_events = (
        _g(planning, "income_expected_to_increase")
        or _g(planning, "large_capital_gain_expected")
        or _g(planning, "roth_conversion_interest")
        or _g(planning, "retirement_within_10_years")
    )

    if not income_events:
        return flags

    if age >= med_age:
        flags.append({
            "client_age": age,
            "flag": ("Potential consideration for CPA/adviser review: Client is Medicare age "
                     "and has potential income-changing events. Income-related monthly "
                     "adjustment amounts (IRMAA) apply to Medicare Part B and D premiums based "
                     "on MAGI from 2 years prior. Large capital gains, Roth conversions, RMD "
                     "amounts, or other income events may affect IRMAA brackets. Review with a "
                     "CPA or adviser before any income-affecting action."),
            "severity": "review",
        })
    elif age >= near_age:
        flags.append({
            "client_age": age,
            "years_to_medicare": med_age - age,
            "flag": (f"Potential consideration for CPA/adviser review: Client is "
                     f"{med_age - age} year(s) from Medicare age and has potential "
                     f"income-changing events. IRMAA brackets look back 2 years, so income in "
                     f"the next few years may affect Medicare premiums. This may be relevant "
                     f"for Roth conversion, capital gain realization, or RMD timing discussions "
                     f"with a CPA."),
            "severity": "review",
        })
    return flags


def flag_state_tax(household):
    flags = []
    state = (_g(household, "state") or "").upper()
    if not state:
        flags.append({
            "flag": ("Missing data: State of residence not provided. State income tax "
                     "sensitivity cannot be assessed."),
            "severity": "data_gap",
        })
        return flags

    if state not in NO_INCOME_TAX_STATES:
        flags.append({
            "state": state,
            "flag": (f"State tax sensitivity: {state} has a state income tax. Capital gains "
                     f"realizations, Roth conversions, RMD amounts, and other taxable income "
                     f"events may be subject to state income tax in addition to federal tax. "
                     f"Confirm rates and rules with a CPA."),
            "severity": "review",
        })
    return flags


def flag_estate_special(tax_profile, planning):
    """Surface estate/trust/equity-comp flags when relevant signals are present."""
    flags = []
    triggers = {
        "equity_compensation": "Equity compensation or employer stock noted. Vesting, "
                               "exercise, and sale events may have complex tax consequences. "
                               "CPA and financial adviser review required.",
        "business_ownership":  "Business ownership noted. Potential tax-sensitive events "
                               "include sale, succession, or entity restructuring. CPA and "
                               "legal counsel review required.",
        "trust_involved":      "Trust involvement noted. Tax treatment of trust income, "
                               "distributions, or assets may require specialized review by "
                               "an estate attorney and CPA.",
        "real_estate_sale":    "Real estate sale noted. Depreciation recapture, capital gains "
                               "rates, and 1031 exchange considerations may apply. CPA review "
                               "required.",
        "inheritance_or_estate":"Inheritance or estate event noted. Step-up in cost basis, "
                               "estate tax, and inherited IRA rules may apply. CPA and estate "
                               "attorney review required.",
        "divorce":             "Divorce noted. Asset transfers, QDRO rules, filing status "
                               "changes, and basis allocation require legal and CPA review.",
        "cross_border_tax":    "Cross-border or non-U.S. tax exposure noted. Foreign account "
                               "reporting, treaty issues, or dual-tax exposure require "
                               "specialized CPA review.",
    }
    combined = {**(tax_profile or {}), **(planning or {})}
    for key, msg in triggers.items():
        if combined.get(key):
            flags.append({
                "trigger": key,
                "flag": f"Potential consideration for professional review: {msg}",
                "severity": "high_priority_review",
            })
    return flags


# ── professional review flag assembly ─────────────────────────────────────────

def assemble_pro_flags(flag_groups):
    """Collect high-priority items into a unified professional_review_flags list."""
    prf = []
    for group_name, items in flag_groups.items():
        for f in items:
            sev = f.get("severity", "")
            if sev in ("high_priority_review", "review"):
                prf.append({
                    "category": group_name,
                    "flag": f.get("flag"),
                    "severity": sev,
                })
    return prf


# ── downstream handoff ─────────────────────────────────────────────────────────

def build_downstream_handoff(agg, enriched, flag_groups, household):
    state = (_g(household, "state") or "").upper()

    loss_candidates = [
        {"holding": f["holding"], "unrealized_loss": f["unrealized_loss"]}
        for f in flag_groups.get("loss_harvest_candidate_flags", [])
    ]
    concentrated_low_basis = [
        {"holding": f["holding"], "unrealized_gain": f.get("unrealized_gain_loss")}
        for f in flag_groups.get("low_basis_flags", [])
    ]
    missing_basis_accts = list({
        f["account"] for f in flag_groups.get("missing_basis_flags", [])
    })

    return {
        "for_rebalancing": {
            "taxable_embedded_gain_total":    agg["taxable_embedded_gain_total"],
            "taxable_embedded_loss_total":    agg["taxable_embedded_loss_total"],
            "net_taxable_embedded_gain_loss": agg["net_taxable_embedded_gain_loss"],
            "loss_harvest_candidates":        loss_candidates,
            "concentrated_low_basis_positions": concentrated_low_basis,
            "missing_basis_accounts":         missing_basis_accts,
            "note": ("Rebalancing in taxable accounts should account for embedded gains and "
                     "losses. Do not execute trades without CPA/adviser review."),
        },
        "for_longevity_modeling": {
            "state_has_income_tax":   state not in NO_INCOME_TAX_STATES if state else None,
            "state":                  state or None,
            "note": ("State income tax status affects effective tax drag on taxable accounts. "
                     "Confirm rate with CPA before using in projections."),
        },
        "for_scenario_analysis": {
            "tax_sensitive_flags_present": any(
                len(v) > 0 for v in flag_groups.values()
            ),
            "high_priority_flags": [
                f for f in assemble_pro_flags(flag_groups)
                if f["severity"] == "high_priority_review"
            ],
        },
        "for_reporting": {
            "known_taxable_basis_coverage":   agg["known_taxable_basis_coverage"],
            "net_taxable_embedded_gain_loss": agg["net_taxable_embedded_gain_loss"],
            "total_flag_count": sum(len(v) for v in flag_groups.values()),
        },
    }


# ── input validation ───────────────────────────────────────────────────────────

def _check_number(x, field, *, allow_negative=False):
    """Raise ValueError when a present monetary value is not a usable number.
    None is allowed (genuinely-absent data); a string/NaN/inf/negative is not."""
    if x is None:
        return
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise ValueError(f"{field} must be a number, got {type(x).__name__}")
    v = float(x)
    if v != v or v in (float("inf"), float("-inf")):
        raise ValueError(f"{field} must be a finite number")
    if v < 0 and not allow_negative:
        raise ValueError(f"{field} must be non-negative, got {v}")


def validate(cfg):
    errors, missing = [], []
    if not isinstance(cfg, dict):
        return [{"error": "invalid_input", "detail": "Root must be a JSON object"}], []
    if not cfg.get("accounts") and not cfg.get("holdings"):
        missing.append("accounts or holdings (at least one required)")
    for i, a in enumerate(cfg.get("accounts") or []):
        try:
            _check_number(a.get("balance"), f"account '{a.get('name') or i}' balance")
        except ValueError as e:
            errors.append({"error": "invalid_input", "detail": str(e)})
    for i, h in enumerate(cfg.get("holdings") or []):
        label = h.get("ticker_or_name") or i
        try:
            _check_number(h.get("market_value"), f"holding '{label}' market_value")
            _check_number(h.get("cost_basis"), f"holding '{label}' cost_basis")
        except ValueError as e:
            errors.append({"error": "invalid_input", "detail": str(e)})
    return errors, missing


# ── main ───────────────────────────────────────────────────────────────────────

def run(cfg):
    errors, val_missing = validate(cfg)
    if errors or val_missing:
        return {"error": "invalid_input", "missing": val_missing, "details": errors}

    thr = dict(DEFAULTS)
    thr.update(cfg.get("thresholds") or {})

    household    = cfg.get("household") or {}
    tax_profile  = cfg.get("tax_profile") or {}
    planning     = cfg.get("planning_context") or {}
    income_data  = cfg.get("income") or []

    acct_map  = build_account_map(cfg.get("accounts"))
    holdings  = cfg.get("holdings") or []
    total, tv_source = resolve_portfolio_total(cfg, acct_map, holdings)

    enriched = enrich_holdings(holdings, acct_map, total)
    agg      = aggregate_taxable_gain_loss(enriched)

    missing_info, unknowns = [], []

    flag_groups = {
        "missing_basis_flags":         flag_missing_basis(enriched, missing_info, unknowns),
        "unknown_account_type_flags":  flag_unknown_account_type(enriched, acct_map, unknowns),
        "concentration_flags":         flag_concentration(enriched, thr, total),
        "low_basis_flags":             flag_low_basis(enriched, thr),
        "large_embedded_gain_flags":   flag_large_embedded_gains(enriched, thr, total),
        "loss_harvest_candidate_flags": flag_loss_harvest_candidates(enriched, thr),
        "wash_sale_review_flags":      flag_wash_sale_review(enriched),
        "rmd_review_flags":            flag_rmd(household, acct_map, thr),
        "roth_conversion_review_flags": flag_roth_conversion(household, acct_map, income_data, planning, thr),
        "charitable_giving_review_flags": flag_charitable(household, tax_profile, planning, acct_map, thr),
        "irmaa_review_flags":          flag_irmaa(household, income_data, planning, thr),
        "state_tax_flags":             flag_state_tax(household),
        "estate_and_special_situation_flags": flag_estate_special(tax_profile, planning),
    }

    if not total:
        missing_info.append("portfolio.total_value (could not be resolved from accounts or holdings)")

    age = _n(_g(household, "client_age"))
    if age is None:
        missing_info.append("household.client_age (required for RMD, IRMAA, Roth conversion flags)")
    if not _g(household, "state"):
        missing_info.append("household.state (required for state tax sensitivity)")
    if not _g(household, "filing_status"):
        missing_info.append("household.filing_status (required for bracket-sensitive review)")

    return {
        "input_quality": {
            "portfolio_total_value":        total,
            "portfolio_total_value_source": tv_source,
            "known_taxable_basis_coverage": agg["known_taxable_basis_coverage"],
            "taxable_holdings_with_missing_basis": [
                {"holding": f["holding"], "account": f["account"]}
                for f in flag_groups["missing_basis_flags"]
            ],
            "holdings_with_unknown_account_type": unknowns,
            "missing_information": missing_info,
            "unknowns": unknowns,
        },
        "taxable_gain_loss_snapshot": {
            **agg,
            "gain_loss_by_holding": [
                {k: h[k] for k in (
                    "ticker_or_name", "account_name", "account_tax_treatment",
                    "market_value", "cost_basis", "unrealized_gain_loss",
                    "unrealized_gain_loss_pct", "portfolio_weight", "holding_period",
                )}
                for h in enriched if h["is_taxable"]
            ],
        },
        **flag_groups,
        "professional_review_flags": assemble_pro_flags(flag_groups),
        "downstream_handoff": build_downstream_handoff(agg, enriched, flag_groups, household),
    }


def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
    else:
        cfg = json.load(sys.stdin)

    result = run(cfg)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
