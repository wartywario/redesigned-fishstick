#!/usr/bin/env python3
"""
Scenario definitions for the guap-guide / orchestrator end-to-end test suite.

Each scenario is an *intake payload* (the only thing a real caller controls — the
guide submits intake and reporting; the engine derives every script input from it).
Scenarios are grouped:

  common   — typical, well-formed households. Should run clean and deliver.
  uncommon — valid but edge-y households (concentration, cash drag, depletion, FIRE).
  stress   — adversarial intake that *tries* to induce invalid states (phantom
             balances, negatives, degenerate horizons, silent data loss). The suite
             records whether the system CAUGHT it (errored/flagged/reconciled) or
             LEAKED it (emitted an invalid numeric state).

`expected` is the suite author's hypothesis for the run, used to flag calibration
drift; the harness reports ACTUAL behavior regardless.

  expected = "deliver" : completes, invariants hold, delivers after gates.
  expected = "safe"    : stress input is caught (failed stage and/or surfaced
                         flags/missing) with no invariant-violating numbers.
  expected = "leak"    : stress input produces an invalid numeric state (a real
                         hardening gap in the calculators, surfaced by this suite).
"""

from __future__ import annotations

import copy

NAN = float("nan")


# ── builders ─────────────────────────────────────────────────────────────────────

def household(client_age, retire_age, horizon, *, partner_age=None, state="CA",
              filing="married_filing_jointly"):
    return {
        "client_age": client_age, "partner_age": partner_age, "state": state,
        "filing_status": filing, "planned_retirement_age": retire_age,
        "planning_horizon_age": horizon, "dependents": [],
    }


def retire_goal(amount, age, infl=True):
    return [{
        "name": "Retirement income", "category": "retirement", "priority": "high",
        "target_age_or_date": age, "amount": amount, "frequency": "annual",
        "inflation_adjusted": infl,
    }]


def acct(name, atype, treatment, balance):
    return {"name": name, "type": atype, "tax_treatment": treatment, "balance": balance}


def hold(account, name, mv, basis, group, asset_class, period="long_term"):
    return {
        "account_name": account, "ticker_or_name": name, "market_value": mv,
        "cost_basis": basis, "holding_period": period, "asset_class": asset_class,
        "broad_asset_group": group,
    }


def make_intake(hh, accounts, holdings, goals, *, income=None, target=None,
                tax_profile=None, planning=None):
    return {
        "household": hh,
        "goals": goals,
        "accounts": accounts,
        "holdings": holdings,
        "income": income or [],
        "tax_profile": tax_profile or {"state": hh.get("state"),
                                       "filing_status": hh.get("filing_status")},
        "planning_context": planning or {},
        "risk_profile": ({"target_allocation": target} if target else {}),
        "expenses": [], "liabilities": [],
        "assumptions": [], "missing_information": [],
        "conflicts_or_uncertainties": [], "professional_review_flags": [],
    }


SS = lambda amt, start=67, end=95: {  # social-security income source
    "source": "Social Security", "amount": amt, "frequency": "annual",
    "start_age_or_date": start, "end_age_or_date": end,
    "inflation_adjusted": True, "taxability": "partially_taxable"}


# ── common (valid) ───────────────────────────────────────────────────────────────

COMMON = [
    {
        "id": "mass_affluent_preretiree",
        "category": "common",
        "title": "Age 62 CA household, $1.45M, single-stock concentration, charitable",
        "expected": "deliver",
        "intake": make_intake(
            household(62, 65, 92, partner_age=60),
            [acct("Taxable Brokerage", "taxable_brokerage", "taxable", 650000),
             acct("Traditional IRA", "traditional_ira", "tax_deferred", 600000),
             acct("Roth IRA", "roth_ira", "tax_free", 200000)],
            [hold("Taxable Brokerage", "ACME Corp", 300000, 40000, "equity", "single_stock"),
             hold("Taxable Brokerage", "VTI", 200000, 160000, "equity", "us_total_market_equity"),
             hold("Taxable Brokerage", "VXUS", 80000, 95000, "equity", "international_developed_equity"),
             hold("Taxable Brokerage", "XYZ Growth", 70000, None, "equity", "us_large_cap_equity"),
             hold("Traditional IRA", "Bond Index", 360000, 360000, "fixed_income", "us_bonds"),
             hold("Traditional IRA", "US Equity Index", 240000, 200000, "equity", "us_large_cap_equity"),
             hold("Roth IRA", "QQQ", 200000, 120000, "equity", "sector_equity")],
            retire_goal(90000, 65),
            income=[SS(40000)],
            target={"equity": 0.70, "fixed_income": 0.25, "cash": 0.05},
            planning={"charitable_intent": True, "retirement_within_10_years": True},
        ),
    },
    {
        "id": "young_accumulator",
        "category": "common",
        "title": "Age 30 saver, $120k, aggressive equity, 35-year horizon to 65",
        "expected": "deliver",
        "intake": make_intake(
            household(30, 65, 90, state="TX", filing="single"),
            [acct("401k", "401k", "tax_deferred", 70000),
             acct("Roth IRA", "roth_ira", "tax_free", 30000),
             acct("Brokerage", "taxable_brokerage", "taxable", 20000)],
            [hold("401k", "Target 2060", 70000, 55000, "equity", "us_total_market_equity"),
             hold("Roth IRA", "VTI", 30000, 18000, "equity", "us_total_market_equity"),
             hold("Brokerage", "VT", 20000, 17000, "equity", "global_equity")],
            retire_goal(60000, 65),
            target={"equity": 0.90, "fixed_income": 0.10},
        ),
    },
    {
        "id": "near_retiree_balanced",
        "category": "common",
        "title": "Age 60 balanced 60/40, $2.1M, retire at 65",
        "expected": "deliver",
        "intake": make_intake(
            household(60, 65, 94, partner_age=59),
            [acct("Joint Brokerage", "taxable_brokerage", "taxable", 900000),
             acct("His 401k", "401k", "tax_deferred", 800000),
             acct("Her IRA", "traditional_ira", "tax_deferred", 300000),
             acct("Savings", "savings", "taxable", 100000)],
            [hold("Joint Brokerage", "VTI", 540000, 300000, "equity", "us_total_market_equity"),
             hold("Joint Brokerage", "BND", 360000, 360000, "fixed_income", "us_bonds"),
             hold("His 401k", "S&P 500", 480000, 250000, "equity", "us_large_cap_equity"),
             hold("His 401k", "Total Bond", 320000, 320000, "fixed_income", "us_bonds"),
             hold("Her IRA", "Balanced Fund", 300000, 220000, "equity", "us_large_cap_equity"),
             hold("Savings", "Cash", 100000, 100000, "cash", "cash")],
            retire_goal(100000, 65),
            income=[SS(48000)],
            target={"equity": 0.60, "fixed_income": 0.37, "cash": 0.03},
        ),
    },
    {
        "id": "already_retired_drawdown",
        "category": "common",
        "title": "Age 72 retired, in RMD years, drawing $80k from $1.1M",
        "expected": "deliver",
        "intake": make_intake(
            household(72, 65, 95, partner_age=71),
            [acct("IRA", "traditional_ira", "tax_deferred", 800000),
             acct("Brokerage", "taxable_brokerage", "taxable", 250000),
             acct("Checking", "checking", "taxable", 50000)],
            [hold("IRA", "Conservative Allocation", 800000, 600000, "fixed_income", "us_bonds"),
             hold("Brokerage", "VTI", 250000, 90000, "equity", "us_total_market_equity"),
             hold("Checking", "Cash", 50000, 50000, "cash", "cash")],
            retire_goal(80000, 65),
            income=[SS(52000, start=72)],
            target={"equity": 0.30, "fixed_income": 0.65, "cash": 0.05},
        ),
    },
]


# ── uncommon (valid but edge-y) ──────────────────────────────────────────────────

UNCOMMON = [
    {
        "id": "vhnw_concentration",
        "category": "uncommon",
        "title": "$22M with 60% in one founder stock, charitable + estate flags",
        "expected": "deliver",
        "intake": make_intake(
            household(58, 60, 95, partner_age=57),
            [acct("Founder Brokerage", "taxable_brokerage", "taxable", 18000000),
             acct("Diversified Brokerage", "taxable_brokerage", "taxable", 3000000),
             acct("IRA", "traditional_ira", "tax_deferred", 1000000)],
            [hold("Founder Brokerage", "FOUNDR Inc", 18000000, 500000, "equity", "single_stock"),
             hold("Diversified Brokerage", "VTI", 1800000, 1200000, "equity", "us_total_market_equity"),
             hold("Diversified Brokerage", "Muni Bonds", 1200000, 1200000, "fixed_income", "municipal_bonds"),
             hold("IRA", "Index", 1000000, 700000, "equity", "us_large_cap_equity")],
            retire_goal(400000, 60),
            target={"equity": 0.65, "fixed_income": 0.30, "cash": 0.05},
            tax_profile={"state": "CA", "filing_status": "married_filing_jointly",
                         "charitable_giving_interest": True, "estate_planning_interest": True},
            planning={"charitable_intent": True, "concentrated_position": True,
                      "estate_tax_exposure": True},
        ),
    },
    {
        "id": "cash_heavy_conservative",
        "category": "uncommon",
        "title": "Age 55, $1.4M but 70% cash — drag + low growth over long horizon",
        "expected": "deliver",
        "intake": make_intake(
            household(55, 67, 96, filing="single"),
            [acct("Savings", "savings", "taxable", 700000),
             acct("Money Market", "money_market", "taxable", 300000),
             acct("IRA", "traditional_ira", "tax_deferred", 400000)],
            [hold("Savings", "Cash", 700000, 700000, "cash", "cash"),
             hold("Money Market", "MM Fund", 300000, 300000, "cash", "cash"),
             hold("IRA", "Balanced", 400000, 350000, "equity", "us_large_cap_equity")],
            retire_goal(70000, 67),
            income=[SS(36000)],
            target={"equity": 0.50, "fixed_income": 0.40, "cash": 0.10},
        ),
    },
    {
        "id": "high_spender_depletion",
        "category": "uncommon",
        "title": "Age 58, $900k, wants $120k/yr — likely depletion (valid, low success)",
        "expected": "deliver",
        "intake": make_intake(
            household(58, 60, 95, filing="single"),
            [acct("Brokerage", "taxable_brokerage", "taxable", 500000),
             acct("IRA", "traditional_ira", "tax_deferred", 400000)],
            [hold("Brokerage", "VTI", 350000, 200000, "equity", "us_total_market_equity"),
             hold("Brokerage", "BND", 150000, 150000, "fixed_income", "us_bonds"),
             hold("IRA", "S&P 500", 400000, 250000, "equity", "us_large_cap_equity")],
            retire_goal(120000, 60),
            income=[SS(30000)],
            target={"equity": 0.65, "fixed_income": 0.35},
        ),
    },
    {
        "id": "fire_early_retiree",
        "category": "uncommon",
        "title": "Age 45 retiring now, $1.6M, 50-year horizon to 95 (sequence risk)",
        "expected": "deliver",
        "intake": make_intake(
            household(45, 45, 95, filing="single"),
            [acct("Brokerage", "taxable_brokerage", "taxable", 1200000),
             acct("Roth IRA", "roth_ira", "tax_free", 400000)],
            [hold("Brokerage", "VTI", 840000, 500000, "equity", "us_total_market_equity"),
             hold("Brokerage", "BND", 360000, 360000, "fixed_income", "us_bonds"),
             hold("Roth IRA", "VT", 400000, 250000, "equity", "global_equity")],
            retire_goal(64000, 45),
            target={"equity": 0.75, "fixed_income": 0.25},
        ),
    },
]


# ── stress (adversarial — try to induce invalid states) ──────────────────────────

STRESS = [
    {
        "id": "negative_balance",
        "category": "stress",
        "title": "A holding with NEGATIVE market value — probe negative portfolio total",
        "probe": "negative market_value flows into total_portfolio_value with no guard",
        "expected": "safe",
        "intake": make_intake(
            household(60, 65, 90),
            [acct("Brokerage", "taxable_brokerage", "taxable", 500000)],
            [hold("Brokerage", "VTI", 200000, 150000, "equity", "us_total_market_equity"),
             hold("Brokerage", "Levered Short", -600000, -100000, "equity", "single_stock")],
            retire_goal(60000, 65),
            target={"equity": 0.6, "fixed_income": 0.4},
        ),
    },
    {
        "id": "phantom_holdings_exceed_accounts",
        "category": "stress",
        "title": "Holdings worth 10x the account balances — probe phantom balance",
        "probe": "holdings >> account balances; a reconciliation note must appear (else phantom)",
        "expected": "deliver",
        "intake": make_intake(
            household(60, 65, 90),
            [acct("Brokerage", "taxable_brokerage", "taxable", 100000)],
            [hold("Brokerage", "VTI", 700000, 400000, "equity", "us_total_market_equity"),
             hold("Brokerage", "BND", 300000, 300000, "fixed_income", "us_bonds")],
            retire_goal(50000, 65),
            target={"equity": 0.6, "fixed_income": 0.4},
        ),
    },
    {
        "id": "silent_string_balance",
        "category": "stress",
        "title": "Account balance as a STRING with no holdings — probe silent data loss",
        "probe": "'850000' coerced to 0; account has no holdings so its value vanishes silently",
        "expected": "safe",
        "intake": make_intake(
            household(60, 65, 90),
            [acct("Big IRA (string)", "traditional_ira", "tax_deferred", "850000"),
             acct("Brokerage", "taxable_brokerage", "taxable", 150000)],
            [hold("Brokerage", "VTI", 150000, 90000, "equity", "us_total_market_equity")],
            retire_goal(60000, 65),
        ),
    },
    {
        "id": "nan_balance",
        "category": "stress",
        "title": "A holding market value of NaN — probe NaN propagation",
        "probe": "NaN is a float; _num passes it through, poisoning total/allocations",
        "expected": "safe",
        "intake": make_intake(
            household(60, 65, 90),
            [acct("Brokerage", "taxable_brokerage", "taxable", 500000)],
            [hold("Brokerage", "VTI", 400000, 300000, "equity", "us_total_market_equity"),
             hold("Brokerage", "Mystery", NAN, None, "equity", "single_stock")],
            retire_goal(60000, 65),
        ),
    },
    {
        "id": "horizon_before_age",
        "category": "stress",
        "title": "planning_horizon_age (55) < client_age (60) — probe phantom 100% success",
        "probe": "empty projection yields success_probability 1.0 with no real simulation",
        "expected": "safe",
        "intake": make_intake(
            household(60, 58, 55),  # horizon 55 < current 60; retire 58 < current
            [acct("Brokerage", "taxable_brokerage", "taxable", 400000),
             acct("IRA", "traditional_ira", "tax_deferred", 400000)],
            [hold("Brokerage", "VTI", 400000, 250000, "equity", "us_total_market_equity"),
             hold("IRA", "BND", 400000, 400000, "fixed_income", "us_bonds")],
            retire_goal(70000, 58),
            target={"equity": 0.5, "fixed_income": 0.5},
        ),
    },
    {
        "id": "empty_portfolio",
        "category": "stress",
        "title": "No accounts and no holdings — probe whether stages fail safe",
        "probe": "portfolio & tax must error; longevity must fail on missing inputs",
        "expected": "safe",
        "intake": make_intake(
            household(60, 65, 90),
            [], [],
            retire_goal(60000, 65),
        ),
    },
    {
        "id": "zero_everything",
        "category": "stress",
        "title": "Accounts and holdings all valued at 0 — probe divide-by-zero handling",
        "probe": "total 0 must not crash; allocations 0; longevity depletes immediately at success 0",
        "expected": "deliver",
        "intake": make_intake(
            household(60, 65, 90),
            [acct("Brokerage", "taxable_brokerage", "taxable", 0),
             acct("IRA", "traditional_ira", "tax_deferred", 0)],
            [hold("Brokerage", "VTI", 0, 0, "equity", "us_total_market_equity"),
             hold("IRA", "BND", 0, 0, "fixed_income", "us_bonds")],
            retire_goal(60000, 65),
            target={"equity": 0.6, "fixed_income": 0.4},
        ),
    },
    {
        "id": "negative_spending",
        "category": "stress",
        "title": "Retirement spending of -$80k/yr — probe unbounded phantom growth",
        "probe": "negative spending becomes inflow; portfolio grows without bound, success 1.0",
        "expected": "safe",
        "intake": make_intake(
            household(60, 65, 95),
            [acct("Brokerage", "taxable_brokerage", "taxable", 500000),
             acct("IRA", "traditional_ira", "tax_deferred", 500000)],
            [hold("Brokerage", "VTI", 500000, 300000, "equity", "us_total_market_equity"),
             hold("IRA", "BND", 500000, 500000, "fixed_income", "us_bonds")],
            retire_goal(-80000, 65),
            target={"equity": 0.6, "fixed_income": 0.4},
        ),
    },
]


# ── compliance (valid intake, adversarial REPORT) ────────────────────────────────
# These reuse a known-good intake (near_retiree_balanced) so every script stage
# completes and the case reaches the compliance gate. The adversarial content is in
# the REPORT (via `report_override`), not the intake — they exercise the deterministic
# compliance classifier that drives the gate. A blocked report -> gate fail ->
# cannot deliver -> no numbers delivered -> classifies SAFE.

_BALANCED_INTAKE = copy.deepcopy(COMMON[2]["intake"])  # near_retiree_balanced

# A compliant report body (all required disclosures, no advice, no guarantee claims).
# {SP}/{TPV}/{EQ} are filled by run_suite with the REAL authoritative values; the
# override below carries the text and run_suite appends/edits as the scenario needs.
_COMPLIANT_NARRATIVE = (
    "# Wealth Planning Summary\n"
    "This analysis is for educational purposes and is not tax, legal, or investment "
    "advice. Figures are estimates based on stated assumptions and are not a guarantee "
    "of future results; past performance does not guarantee future results. Please "
    "review with a qualified financial adviser or CPA before acting.\n"
    "## Portfolio\nThe modeled figures below are probabilistic estimates, not promises.\n"
    "## Next steps\nDiscuss these considerations with your adviser."
)

COMPLIANCE = [
    {
        "id": "compliance_advice_language",
        "category": "compliance",
        "title": "Report tells the client to sell bonds and buy tech — advice language",
        "probe": "advice/action language must block the compliance gate",
        "expected": "safe",
        "intake": copy.deepcopy(_BALANCED_INTAKE),
        "report_override": {
            "narrative": _COMPLIANT_NARRATIVE
            + "\nYou should sell all your bonds and buy technology stocks.",
            "cited_numbers": [],
        },
    },
    {
        "id": "compliance_missing_disclosures",
        "category": "compliance",
        "title": "Report cites numbers but omits all required disclosures",
        "probe": "missing required disclosures must block the compliance gate",
        "expected": "safe",
        "intake": copy.deepcopy(_BALANCED_INTAKE),
        "report_override": {
            "narrative": (
                "# Wealth Planning Summary\n"
                "Your total portfolio value is approximately $2,100,000 with a 60% equity "
                "allocation. Across the simulations the modeled success probability is strong."
            ),
            "cited_numbers": [],
        },
    },
    {
        "id": "compliance_guarantee_language",
        "category": "compliance",
        "title": "Report guarantees the portfolio will last through age 95",
        "probe": "guarantee/certainty language must block the compliance gate",
        "expected": "safe",
        "intake": copy.deepcopy(_BALANCED_INTAKE),
        "report_override": {
            "narrative": _COMPLIANT_NARRATIVE
            + "\nYour portfolio is guaranteed to last through age 95.",
            "cited_numbers": [],
        },
    },
    {
        "id": "compliance_fabricated_number",
        "category": "compliance",
        "title": "Compliant prose but the cited success probability is fabricated (0.50)",
        "probe": "a cited number that contradicts the authoritative value must block the gate",
        "expected": "safe",
        "intake": copy.deepcopy(_BALANCED_INTAKE),
        "report_override": {
            "narrative": _COMPLIANT_NARRATIVE
            + "\n## Longevity\nThe modeled success probability is 50%.",
            "cited_numbers": [
                {"label": "success probability", "value": 0.50,
                 "authoritative_key": "longevity.success_probability"}
            ],
        },
    },
    {
        "id": "compliance_clean_report",
        "category": "compliance",
        "title": "Explicitly clean, compliant report — passes the gate and delivers",
        "probe": "a fully compliant report must pass the gate and deliver",
        "expected": "deliver",
        "intake": copy.deepcopy(_BALANCED_INTAKE),
        "report_override": {
            "narrative": _COMPLIANT_NARRATIVE,
            "cited_numbers": [],
        },
    },
]


SCENARIOS = COMMON + UNCOMMON + STRESS + COMPLIANCE


def get(scenario_id):
    for s in SCENARIOS:
        if s["id"] == scenario_id:
            return copy.deepcopy(s)
    raise KeyError(scenario_id)
