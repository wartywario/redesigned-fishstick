#!/usr/bin/env python3
"""
Allocation / drift / concentration calculator for the portfolio-analysis skill.

Pure standard library (no dependencies). Reads a JSON input object (file path as
argv[1], or stdin) and writes a JSON result object to stdout.

It deterministically computes total value, holding weights, broad/detailed/
tax-treatment allocation, per-account allocation, drift vs. a target allocation
(with the skill's default threshold flags), concentration flags, and cash runway.

It classifies nothing on its own beyond synthesizing a holding for accounts that
have a balance but no listed holdings (using the account type). All asset-class
labels must come from the caller; unknown/missing classes are surfaced, not guessed.
"""

import json
import math
import sys

BROAD_GROUPS = ["equity", "fixed_income", "cash", "real_assets",
                "alternatives", "insurance_or_annuity", "unknown"]

TAX_TREATMENTS = ["taxable", "tax_deferred", "tax_free", "tax_advantaged_health",
                  "education_tax_advantaged", "illiquid_or_nonportfolio_asset",
                  "unknown"]

# account type -> (broad group, tax treatment) for accounts with no holdings
ACCOUNT_TYPE_MAP = {
    "taxable_brokerage": ("unknown", "taxable"),
    "checking": ("cash", "taxable"),
    "savings": ("cash", "taxable"),
    "money_market": ("cash", "taxable"),
    "traditional_ira": ("unknown", "tax_deferred"),
    "sep_ira": ("unknown", "tax_deferred"),
    "simple_ira": ("unknown", "tax_deferred"),
    "401k": ("unknown", "tax_deferred"),
    "403b": ("unknown", "tax_deferred"),
    "457": ("unknown", "tax_deferred"),
    "pension": ("insurance_or_annuity", "tax_deferred"),
    "roth_ira": ("unknown", "tax_free"),
    "hsa": ("unknown", "tax_advantaged_health"),
    "529": ("unknown", "education_tax_advantaged"),
    "trust": ("unknown", "unknown"),
    "annuity": ("insurance_or_annuity", "illiquid_or_nonportfolio_asset"),
    "crypto_wallet": ("alternatives", "taxable"),
    "real_estate": ("real_assets", "illiquid_or_nonportfolio_asset"),
    "business_interest": ("alternatives", "illiquid_or_nonportfolio_asset"),
    "other": ("unknown", "unknown"),
}

DEFAULT_THRESHOLDS = {
    "broad_drift_review": 0.05,
    "broad_drift_high": 0.10,
    "detailed_drift_review": 0.03,
    "single_holding": 0.10,
    "employer_stock": 0.05,
    "speculative": 0.05,
    "unknown_holding": 0.10,
    "cash_reserve_months_low": 3,
    "cash_reserve_months_high": 24,
}


def _num(x):
    return x if isinstance(x, (int, float)) else 0.0


class InputError(Exception):
    """Raised when a caller-supplied monetary value is not a usable number."""


def _require_number(x, field, *, allow_negative=False, allow_none=True):
    """Validate a monetary input. Returns the float, or None when allowed.

    Rejects non-numeric values (e.g. a string-coded balance, which would
    otherwise be silently coerced to 0 and vanish), bool, NaN/inf, and — unless
    allow_negative — negatives. A money value that cannot be trusted must surface
    as a hard error, never as a plausible-looking 0."""
    if x is None:
        if allow_none:
            return None
        raise InputError(f"{field} is required")
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise InputError(f"{field} must be a number, got {type(x).__name__} ({x!r})")
    v = float(x)
    if not math.isfinite(v):
        raise InputError(f"{field} must be a finite number, got {x!r}")
    if v < 0 and not allow_negative:
        raise InputError(f"{field} must be non-negative, got {v}")
    return v


def validate_inputs(cfg):
    """Hard-validate every monetary field before any aggregation runs."""
    for i, a in enumerate(cfg.get("accounts") or []):
        label = a.get("name") or f"accounts[{i}]"
        _require_number(a.get("balance"), f"account '{label}' balance")
    for i, h in enumerate(cfg.get("holdings") or []):
        label = h.get("ticker_or_name") or f"holdings[{i}]"
        _require_number(h.get("market_value"), f"holding '{label}' market_value",
                        allow_none=False)
        _require_number(h.get("cost_basis"), f"holding '{label}' cost_basis")


def expand_holdings(accounts, holdings):
    """Return a working list of holdings, synthesizing one per account that has a
    balance but no listed holdings."""
    accounts = accounts or []
    holdings = [dict(h) for h in (holdings or [])]
    accounts_with_holdings = {h.get("account_name") for h in holdings}

    acct_tax = {}
    for a in accounts:
        name = a.get("name")
        atype = a.get("type")
        tt = a.get("tax_treatment") or ACCOUNT_TYPE_MAP.get(atype, ("unknown", "unknown"))[1]
        acct_tax[name] = tt
        if name not in accounts_with_holdings and _num(a.get("balance")) > 0:
            bg = ACCOUNT_TYPE_MAP.get(atype, ("unknown", "unknown"))[0]
            holdings.append({
                "account_name": name,
                "ticker_or_name": a.get("name") or "(account balance)",
                "market_value": a.get("balance"),
                "asset_class": "cash" if bg == "cash" else "unknown",
                "broad_asset_group": bg,
                "_synthetic": True,
            })

    # backfill tax treatment onto each holding from its account
    for h in holdings:
        h.setdefault("_tax_treatment",
                     acct_tax.get(h.get("account_name"), "unknown"))
        bg = h.get("broad_asset_group") or "unknown"
        if bg not in BROAD_GROUPS:
            bg = "unknown"
        h["broad_asset_group"] = bg
    return holdings


def pct_map(pairs, total):
    out = {}
    if total <= 0:
        return out
    for key, val in pairs:
        out[key] = round(out.get(key, 0.0) + val / total, 4)
    return out


def compute(cfg):
    accounts = cfg.get("accounts") or []
    holdings = expand_holdings(accounts, cfg.get("holdings"))

    total = sum(_num(h.get("market_value")) for h in holdings)
    reported = sum(_num(a.get("balance")) for a in accounts)

    # per-holding weights
    for h in holdings:
        h["portfolio_weight"] = round(_num(h.get("market_value")) / total, 4) if total else None

    broad = {g: 0.0 for g in BROAD_GROUPS}
    detailed = {}
    taxalloc = {t: 0.0 for t in TAX_TREATMENTS}
    for h in holdings:
        mv = _num(h.get("market_value"))
        broad[h["broad_asset_group"]] += mv
        ac = h.get("asset_class") or "unknown"
        detailed[ac] = detailed.get(ac, 0.0) + mv
        tt = h.get("_tax_treatment") or "unknown"
        if tt not in taxalloc:
            tt = "unknown"
        taxalloc[tt] += mv

    broad_pct = {k: round(v / total, 4) if total else 0.0 for k, v in broad.items()}
    detailed_pct = {k: round(v / total, 4) if total else 0.0 for k, v in detailed.items()}
    tax_pct = {k: round(v / total, 4) if total else 0.0 for k, v in taxalloc.items()}

    # per-account allocation
    account_allocation = []
    by_acct = {}
    for h in holdings:
        by_acct.setdefault(h.get("account_name"), []).append(h)
    for name, hs in by_acct.items():
        acct_total = sum(_num(h.get("market_value")) for h in hs)
        alloc = {g: 0.0 for g in BROAD_GROUPS}
        for h in hs:
            alloc[h["broad_asset_group"]] += _num(h.get("market_value"))
        alloc = {k: round(v / acct_total, 4) if acct_total else 0.0 for k, v in alloc.items()}
        account_allocation.append({
            "account_name": name,
            "account_value": round(acct_total, 2),
            "allocation": {k: v for k, v in alloc.items() if v},
        })

    thr = dict(DEFAULT_THRESHOLDS)
    thr.update(cfg.get("drift_thresholds", {}))

    # drift vs target
    drift = {"calculated": False, "broad_asset_group_drift": {},
             "drift_flags": [], "largest_overweights": [], "largest_underweights": []}
    target = cfg.get("target_allocation")
    if target:
        drift["calculated"] = True
        diffs = []
        for g, tval in target.items():
            cur = broad_pct.get(g, 0.0)
            d = round(cur - tval, 4)
            drift["broad_asset_group_drift"][g] = d
            diffs.append((g, d))
            if abs(d) > thr["broad_drift_high"]:
                drift["drift_flags"].append(
                    f"{g}: {'over' if d > 0 else 'under'}weight by "
                    f"{abs(d)*100:.1f}pp (high_priority_review).")
            elif abs(d) > thr["broad_drift_review"]:
                drift["drift_flags"].append(
                    f"{g}: {'over' if d > 0 else 'under'}weight by "
                    f"{abs(d)*100:.1f}pp (review).")
        overs = sorted([x for x in diffs if x[1] > 0], key=lambda x: -x[1])
        unders = sorted([x for x in diffs if x[1] < 0], key=lambda x: x[1])
        drift["largest_overweights"] = [{"asset_group": g, "drift": d} for g, d in overs[:3]]
        drift["largest_underweights"] = [{"asset_group": g, "drift": d} for g, d in unders[:3]]

    # concentration
    conc = {"largest_holdings": [], "single_holding_flags": [],
            "employer_stock_flags": [], "speculative_flags": [], "unknown_asset_flags": []}
    ranked = sorted(holdings, key=lambda h: -_num(h.get("market_value")))
    for h in ranked[:5]:
        conc["largest_holdings"].append({
            "ticker_or_name": h.get("ticker_or_name"),
            "portfolio_weight": h.get("portfolio_weight"),
        })
    for h in holdings:
        w = h.get("portfolio_weight") or 0.0
        name = h.get("ticker_or_name")
        ac = (h.get("asset_class") or "unknown")
        is_emp = ac == "employer_stock" or h.get("is_employer_stock")
        if is_emp and w > thr["employer_stock"]:
            conc["employer_stock_flags"].append(
                f"{name} is {w*100:.1f}% of portfolio (employer_stock_review).")
        if not is_emp and w > thr["single_holding"] and h["broad_asset_group"] != "cash":
            conc["single_holding_flags"].append(
                f"{name} is {w*100:.1f}% of portfolio (concentration_review).")
        if ac in ("crypto",) and w > thr["speculative"]:
            conc["speculative_flags"].append(
                f"{name} is {w*100:.1f}% of portfolio (speculative concentration).")
        if (ac == "unknown" or h["broad_asset_group"] == "unknown") and w > thr["unknown_holding"]:
            conc["unknown_asset_flags"].append(
                f"{name} is {w*100:.1f}% of portfolio and is unclassified.")

    # liquidity / cash runway
    cash_balance = round(broad["cash"], 2)
    monthly = cfg.get("monthly_spending")
    if monthly is None and cfg.get("annual_spending"):
        monthly = cfg["annual_spending"] / 12.0
    runway = None
    classification = None
    notes = []
    if monthly and monthly > 0:
        runway = round(cash_balance / monthly, 1)
        if runway < thr["cash_reserve_months_low"]:
            classification = "low cash reserve"
        elif runway <= 12:
            classification = "typical reserve range"
        elif runway <= thr["cash_reserve_months_high"]:
            classification = "elevated cash reserve"
        else:
            classification = "high cash reserve / potential cash drag"
    else:
        notes.append("Spending not provided; cash runway not calculated.")

    # balance reconciliation
    recon = []
    if reported and abs(reported - total) > 1:
        recon.append(
            f"Sum of account balances ({reported:.0f}) differs from sum of "
            f"holding values ({total:.0f}) by {reported-total:.0f}. "
            "Holding values were used for allocation.")

    return {
        "portfolio_summary": {
            "total_portfolio_value": round(total, 2),
            "sum_of_reported_account_balances": round(reported, 2) if reported else None,
            "reconciliation_notes": recon,
            "currency": "USD",
        },
        "current_allocation": {
            "broad_asset_group_allocation": broad_pct,
            "detailed_asset_class_allocation": {k: v for k, v in detailed_pct.items() if v},
            "tax_treatment_allocation": {k: v for k, v in tax_pct.items() if v},
        },
        "account_allocation": account_allocation,
        "allocation_drift": drift,
        "concentration_analysis": conc,
        "liquidity_analysis": {
            "cash_balance": cash_balance,
            "monthly_spending_used": round(monthly, 2) if monthly else None,
            "cash_runway_months": runway,
            "cash_reserve_classification": classification,
            "notes": notes,
        },
        "holdings": [
            {
                "account_name": h.get("account_name"),
                "ticker_or_name": h.get("ticker_or_name"),
                "market_value": round(_num(h.get("market_value")), 2),
                "portfolio_weight": h.get("portfolio_weight"),
                "asset_class": h.get("asset_class"),
                "broad_asset_group": h.get("broad_asset_group"),
                "synthetic_from_account_balance": bool(h.get("_synthetic")),
            }
            for h in holdings
        ],
    }


def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
    else:
        cfg = json.load(sys.stdin)
    if not cfg.get("accounts") and not cfg.get("holdings"):
        json.dump({"error": "provide at least one of 'accounts' or 'holdings'"},
                  sys.stdout, indent=2)
        sys.stdout.write("\n")
        sys.exit(1)
    try:
        validate_inputs(cfg)
    except InputError as e:
        json.dump({"error": "invalid_input", "details": [str(e)]}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        sys.exit(1)
    json.dump(compute(cfg), sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
