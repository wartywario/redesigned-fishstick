#!/usr/bin/env python3
"""
Longevity / portfolio-depletion calculator for the longevity-modeling skill.

Pure standard library (no numpy) so it runs anywhere Python 3.8+ is installed.
Reads a JSON input object (file path as argv[1], or stdin) and writes a JSON
result object to stdout.

Modeling conventions (kept consistent with SKILL.md "Cash-Flow Modeling Rules"):
  * BEGIN-OF-YEAR cash flows: contributions, external income, spending, and any
    one-time cash flows are applied to the beginning balance FIRST, then the
    annual return is applied to the post-cash-flow balance:
        ending = (beginning + contributions + income - spending +/- one_time)
                 * (1 + net_return)
  * Returns are NOMINAL. Spending and income marked inflation_adjusted grow at
    the inflation rate from today's dollars (base = current_age).
  * net_return = blended_gross_nominal_return - portfolio_fee - tax_drag.
  * Depletion occurs when the post-cash-flow balance is <= 0 (cannot fund the
    year's spending). depletion_age is recorded; balance floored at 0 thereafter.

All assumptions are caller-supplied; this script computes, it does not advise.
"""

import json
import math
import random
import sys

# ---- default placeholder assumptions (used only when caller omits them) ----
# Long-horizon (multi-decade) nominal capital-market assumptions. Last reviewed
# 2026-05 against J.P. Morgan 2025/2026 LTCMA, Vanguard VCMM, the Horizon
# Actuarial 2024 survey (~40 firms, 20-yr horizon), and Damodaran 1928-2024
# historical data. These are deliberately conservative-but-current placeholders;
# a caller's own return_assumptions always override them.
DEFAULT_RETURNS = {
    "equity_return_nominal": 0.07,        # ~JPM 6.7% / Horizon 20-yr ~7-7.5%; below 10% hist (conservative)
    "us_equity_return_nominal": 0.07,
    "intl_equity_return_nominal": 0.07,   # current CMAs put intl >= US on valuations; held equal to US
    "bond_return_nominal": 0.045,         # ~starting US Agg yield; JPM 4.6%, Vanguard 4.3-5.3%, Horizon 4.5-5%
    "cash_return_nominal": 0.03,          # ~inflation + 0.5% real; long-run T-bill ~3-3.5%
    "inflation": 0.025,                   # CPI ~2.3-2.5%; above Fed 2% PCE target
    "portfolio_fee": 0.002,               # low-cost fund level; excludes any advisory fee
    "tax_drag": 0.003,                    # blended placeholder; tax stage can refine
    "equity_volatility": 0.16,            # diversified equity sleeve; US large-cap hist ~17-18%
    "bond_volatility": 0.06,              # US Agg hist ~5-7%
    "cash_volatility": 0.01,
    "equity_bond_correlation": 0.20,      # ~100-yr avg & current positive (inflation) regime; conservative
}

# map allocation keys -> (return key, broad bucket)
ALLOC_MAP = {
    "equity": ("equity_return_nominal", "equity"),
    "us_equity": ("us_equity_return_nominal", "equity"),
    "intl_equity": ("intl_equity_return_nominal", "equity"),
    "international_equity": ("intl_equity_return_nominal", "equity"),
    "bonds": ("bond_return_nominal", "bonds"),
    "fixed_income": ("bond_return_nominal", "bonds"),
    "cash": ("cash_return_nominal", "cash"),
}


def _g(d, key, default=None):
    return d.get(key, default) if isinstance(d, dict) else default


def _vnum(x, field, *, allow_negative=False):
    """Validate a required numeric input; raise ValueError on anything unusable."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise ValueError(f"{field} must be a number, got {type(x).__name__} ({x!r})")
    v = float(x)
    if not math.isfinite(v):
        raise ValueError(f"{field} must be a finite number, got {x!r}")
    if v < 0 and not allow_negative:
        raise ValueError(f"{field} must be non-negative, got {v}")
    return v


def validate_inputs(cfg):
    """Reject degenerate inputs that would otherwise yield a confidently wrong
    projection (negative starting value, NaN, a horizon before the current age
    that simulates zero years, or negative spending read as phantom inflow)."""
    spv = _vnum(cfg.get("starting_portfolio_value"), "starting_portfolio_value")
    ca = _vnum(cfg.get("current_age"), "current_age")
    ha = _vnum(cfg.get("planning_horizon_age"), "planning_horizon_age")
    _vnum(cfg.get("retirement_age"), "retirement_age")
    _vnum(cfg.get("annual_spending"), "annual_spending")  # negative -> phantom inflow
    if ha < ca:
        raise ValueError(
            f"planning_horizon_age ({ha:g}) must be >= current_age ({ca:g}); "
            "a shorter horizon simulates zero years and reports a meaningless "
            "100% success rate")
    return spv


def blended_return_and_vol(allocation, ra):
    """Return (gross_nominal_mean, annual_stdev) for the blended portfolio."""
    if not allocation:
        # fall back to a 60/30/10 placeholder
        allocation = {"equity": 0.60, "bonds": 0.30, "cash": 0.10}

    total_w = sum(v for v in allocation.values() if isinstance(v, (int, float)))
    if total_w <= 0:
        total_w = 1.0

    w_eq = w_bond = w_cash = 0.0
    gross = 0.0
    for k, w in allocation.items():
        if not isinstance(w, (int, float)):
            continue
        wn = w / total_w
        ret_key, bucket = ALLOC_MAP.get(k, ("cash_return_nominal", "cash"))
        gross += wn * ra.get(ret_key, DEFAULT_RETURNS[ret_key])
        if bucket == "equity":
            w_eq += wn
        elif bucket == "bonds":
            w_bond += wn
        else:
            w_cash += wn

    eq_vol = ra.get("equity_volatility", DEFAULT_RETURNS["equity_volatility"])
    bond_vol = ra.get("bond_volatility", DEFAULT_RETURNS["bond_volatility"])
    cash_vol = ra.get("cash_volatility", DEFAULT_RETURNS["cash_volatility"])
    corr = ra.get("equity_bond_correlation",
                  DEFAULT_RETURNS["equity_bond_correlation"])

    variance = (
        (w_eq * eq_vol) ** 2
        + (w_bond * bond_vol) ** 2
        + (w_cash * cash_vol) ** 2
        + 2 * w_eq * w_bond * eq_vol * bond_vol * corr
    )
    return gross, math.sqrt(max(variance, 0.0))


def _income_at(age, income_sources, current_age, inflation):
    total = 0.0
    for inc in income_sources or []:
        start = _g(inc, "start_age", current_age)
        end = _g(inc, "end_age", 200)
        if start is None or end is None:
            continue
        if start <= age <= end:
            amt = _g(inc, "amount", 0) or 0
            if _g(inc, "inflation_adjusted", True):
                amt *= (1 + inflation) ** (age - current_age)
            total += amt
    return total


def _onetime_at(age, flows, current_age, inflation):
    total = 0.0
    for f in flows or []:
        if _g(f, "age") == age:
            amt = _g(f, "amount", 0) or 0
            if _g(f, "inflation_adjusted", False):
                amt *= (1 + inflation) ** (age - current_age)
            total += amt
    return total


def project(cfg, return_path=None):
    """Run one deterministic-style path. If return_path is a list of annual
    returns, use it; otherwise use the fixed net_return. Returns dict."""
    current_age = cfg["current_age"]
    horizon = cfg["planning_horizon_age"]
    retirement_age = cfg["retirement_age"]
    spending_start = cfg.get("spending_start_age", retirement_age)
    base_spending = cfg.get("annual_spending", 0) or 0
    spend_infl = cfg.get("spending_inflation_adjusted", True)
    inflation = cfg["_inflation"]
    net_return = cfg["_net_return"]
    contribution = cfg.get("pre_retirement_contribution", 0) or 0

    balance = cfg["starting_portfolio_value"]
    rows = []
    depletion_age = None
    lowest = balance
    first_year_net_withdrawal = None
    portfolio_at_retirement = None

    for i, age in enumerate(range(current_age, horizon + 1)):
        yfn = age - current_age
        beginning = balance
        if age == retirement_age:
            portfolio_at_retirement = beginning

        contrib = contribution if age < retirement_age else 0.0
        income = _income_at(age, cfg.get("income_sources"), current_age, inflation)
        spending = 0.0
        if age >= spending_start:
            spending = base_spending * ((1 + inflation) ** yfn if spend_infl else 1)
        onetime = _onetime_at(age, cfg.get("one_time_cash_flows"),
                              current_age, inflation)

        net_withdrawal = spending - income  # portfolio-funded gap
        if age == spending_start and first_year_net_withdrawal is None:
            first_year_net_withdrawal = net_withdrawal

        pre_growth = beginning + contrib + income - spending + onetime
        if pre_growth <= 0 and depletion_age is None:
            depletion_age = age
            rows.append({
                "age": age, "beginning_portfolio_value": round(beginning, 2),
                "external_income": round(income, 2), "spending": round(spending, 2),
                "net_withdrawal": round(net_withdrawal, 2),
                "ending_portfolio_value": 0.0,
            })
            balance = 0.0
            break

        r = return_path[i] if return_path is not None else net_return
        ending = pre_growth * (1 + r)
        balance = ending
        lowest = min(lowest, ending)
        rows.append({
            "age": age, "beginning_portfolio_value": round(beginning, 2),
            "external_income": round(income, 2), "spending": round(spending, 2),
            "net_withdrawal": round(net_withdrawal, 2),
            "portfolio_return": round(r, 4),
            "ending_portfolio_value": round(ending, 2),
        })

    return {
        "rows": rows,
        "ending_portfolio_value": round(balance, 2),
        "lowest_portfolio_value": round(lowest, 2),
        "depletion_occurs": depletion_age is not None,
        "depletion_age": depletion_age,
        "first_year_net_withdrawal": first_year_net_withdrawal,
        "portfolio_at_retirement": portfolio_at_retirement,
    }


def percentile(sorted_vals, p):
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return round(sorted_vals[int(k)], 2)
    return round(sorted_vals[lo] * (hi - k) + sorted_vals[hi] * (k - lo), 2)


def monte_carlo(cfg, mean_net, stdev, n_sims):
    current_age = cfg["current_age"]
    horizon = cfg["planning_horizon_age"]
    n_years = horizon - current_age + 1
    successes = 0
    ending_vals = []
    depletion_ages = []
    rng = random.Random(cfg.get("random_seed", 12345))

    for _ in range(n_sims):
        path = [rng.gauss(mean_net, stdev) for _ in range(n_years)]
        res = project(cfg, return_path=path)
        ending_vals.append(max(res["ending_portfolio_value"], 0.0))
        if res["depletion_occurs"]:
            depletion_ages.append(res["depletion_age"])
        else:
            successes += 1

    ending_vals.sort()
    depletion_ages.sort()
    med_dep = None
    if depletion_ages:
        med_dep = depletion_ages[len(depletion_ages) // 2]

    return {
        "simulation_count": n_sims,
        "success_probability": round(successes / n_sims, 4),
        "failure_probability": round(1 - successes / n_sims, 4),
        "median_ending_value": percentile(ending_vals, 0.50),
        "p10_ending_value": percentile(ending_vals, 0.10),
        "p25_ending_value": percentile(ending_vals, 0.25),
        "p75_ending_value": percentile(ending_vals, 0.75),
        "p90_ending_value": percentile(ending_vals, 0.90),
        "median_depletion_age_if_failed": med_dep,
        "notes": [
            "Returns drawn from Normal(mean, stdev) per year, independent across "
            "years (no autocorrelation/mean reversion modeled).",
            "Ending values floored at 0 for depleted paths.",
        ],
    }


def run(cfg):
    ra = dict(DEFAULT_RETURNS)
    ra.update(cfg.get("return_assumptions", {}))
    gross, stdev = blended_return_and_vol(cfg.get("asset_allocation"), ra)
    fee = ra.get("portfolio_fee", 0.0)
    tax_drag = ra.get("tax_drag", 0.0)
    net = gross - fee - tax_drag

    cfg["_inflation"] = ra["inflation"]
    cfg["_net_return"] = net

    base = project(cfg)
    start_val = cfg["starting_portfolio_value"]
    fynw = base["first_year_net_withdrawal"]
    port_ret = base["portfolio_at_retirement"] or start_val

    iwr_gross = None
    iwr_net = None
    if fynw is not None and port_ret:
        spend_start = cfg.get("spending_start_age", cfg["retirement_age"])
        infl = ra["inflation"]
        spend_at_start = (cfg.get("annual_spending", 0) or 0)
        if cfg.get("spending_inflation_adjusted", True):
            spend_at_start *= (1 + infl) ** (spend_start - cfg["current_age"])
        iwr_gross = round(spend_at_start / port_ret, 4)
        iwr_net = round(fynw / port_ret, 4)

    n_sims = cfg.get("simulation_count", 10000)
    mc = monte_carlo(cfg, net, stdev, n_sims) if n_sims and n_sims > 0 else None

    return {
        "engine_assumptions": {
            "blended_gross_nominal_return": round(gross, 4),
            "portfolio_fee": fee,
            "tax_drag": tax_drag,
            "net_nominal_return": round(net, 4),
            "blended_annual_stdev": round(stdev, 4),
            "inflation": ra["inflation"],
            "net_real_return_approx": round(net - ra["inflation"], 4),
            "cashflow_timing": "begin_of_year",
        },
        "base_case": {
            "starting_portfolio_value": start_val,
            "portfolio_at_retirement": (round(port_ret, 2)
                                        if port_ret is not None else None),
            "initial_withdrawal_rate_gross": iwr_gross,
            "initial_withdrawal_rate_net": iwr_net,
            "first_year_net_portfolio_withdrawal": (round(fynw, 2)
                                                    if fynw is not None else None),
            "ending_portfolio_value": base["ending_portfolio_value"],
            "lowest_portfolio_value": base["lowest_portfolio_value"],
            "depletion_occurs": base["depletion_occurs"],
            "depletion_age": base["depletion_age"],
        },
        "monte_carlo": mc,
        "year_by_year": base["rows"],
    }


def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
    else:
        cfg = json.load(sys.stdin)

    required = ["starting_portfolio_value", "current_age",
                "retirement_age", "planning_horizon_age", "annual_spending"]
    missing = [k for k in required if k not in cfg]
    if missing:
        json.dump({"error": "missing required inputs", "missing": missing},
                  sys.stdout, indent=2)
        sys.stdout.write("\n")
        sys.exit(1)

    try:
        validate_inputs(cfg)
    except ValueError as e:
        json.dump({"error": "invalid_input", "details": [str(e)]}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        sys.exit(1)

    json.dump(run(cfg), sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
