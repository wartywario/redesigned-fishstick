#!/usr/bin/env python3
"""
End-to-end demo of the orchestrator against the real calculator scripts.

Runs the age-62 CA household through: intake (submitted) -> portfolio (script)
-> tax (script) -> longevity (script) -> reporting (submitted) -> gates -> deliver.
Then demonstrates staleness (edit intake -> downstream goes stale) and replay
verification (re-run a script on its archived input; output hash must match).

Run:  python demo.py
"""

import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
from engine import Orchestrator

WORK = Path(__file__).resolve().parent / "_demo_run"

INTAKE = {
    "household": {
        "client_age": 62, "partner_age": 60, "state": "CA",
        "filing_status": "married_filing_jointly",
        "planned_retirement_age": 65, "planning_horizon_age": 92, "dependents": [],
    },
    "goals": [{
        "name": "Retirement income", "category": "retirement", "priority": "high",
        "target_age_or_date": 65, "amount": 90000, "frequency": "annual",
        "inflation_adjusted": True,
    }],
    "accounts": [
        {"name": "Taxable Brokerage", "type": "taxable_brokerage", "tax_treatment": "taxable", "balance": 650000},
        {"name": "Traditional IRA", "type": "traditional_ira", "tax_treatment": "tax_deferred", "balance": 600000},
        {"name": "Roth IRA", "type": "roth_ira", "tax_treatment": "tax_free", "balance": 200000},
    ],
    "holdings": [
        {"account_name": "Taxable Brokerage", "ticker_or_name": "ACME Corp", "market_value": 300000, "cost_basis": 40000, "holding_period": "long_term", "asset_class": "single_stock", "broad_asset_group": "equity"},
        {"account_name": "Taxable Brokerage", "ticker_or_name": "VTI", "market_value": 200000, "cost_basis": 160000, "holding_period": "long_term", "asset_class": "us_total_market_equity", "broad_asset_group": "equity"},
        {"account_name": "Taxable Brokerage", "ticker_or_name": "VXUS", "market_value": 80000, "cost_basis": 95000, "holding_period": "long_term", "asset_class": "international_developed_equity", "broad_asset_group": "equity"},
        {"account_name": "Taxable Brokerage", "ticker_or_name": "XYZ Growth Fund", "market_value": 70000, "cost_basis": None, "holding_period": None, "asset_class": "us_large_cap_equity", "broad_asset_group": "equity"},
        {"account_name": "Traditional IRA", "ticker_or_name": "Bond Index", "market_value": 360000, "cost_basis": 360000, "holding_period": "long_term", "asset_class": "us_bonds", "broad_asset_group": "fixed_income"},
        {"account_name": "Traditional IRA", "ticker_or_name": "US Equity Index", "market_value": 240000, "cost_basis": 200000, "holding_period": "long_term", "asset_class": "us_large_cap_equity", "broad_asset_group": "equity"},
        {"account_name": "Roth IRA", "ticker_or_name": "QQQ", "market_value": 200000, "cost_basis": 120000, "holding_period": "long_term", "asset_class": "sector_equity", "broad_asset_group": "equity"},
    ],
    "income": [
        {"source": "Salary", "amount": 180000, "frequency": "annual", "taxability": "taxable"},
        {"source": "Social Security", "amount": 40000, "frequency": "annual", "start_age_or_date": 67, "end_age_or_date": 92, "inflation_adjusted": True, "taxability": "partially_taxable"},
    ],
    "tax_profile": {"state": "CA", "filing_status": "married_filing_jointly", "charitable_giving_interest": True},
    "planning_context": {"charitable_intent": True, "retirement_within_10_years": True},
    "risk_profile": {"target_allocation": {"equity": 0.70, "fixed_income": 0.25, "cash": 0.05}},
    "expenses": [], "liabilities": [],
    "assumptions": ["$90,000/yr retirement spending stated by client (unconfirmed)."],
    "missing_information": ["Cost basis for XYZ Growth Fund (Taxable Brokerage)"],
    "conflicts_or_uncertainties": [], "professional_review_flags": [],
}

REPORT_OUTPUT = {"format": "full_report", "markdown_ref": "artifacts/report_v1.md"}


def line(t): print("\n" + "=" * 4, t)


def main():
    if WORK.exists():
        shutil.rmtree(WORK)
    orc = Orchestrator(WORK)
    case = orc.new_case("case_demo_01", household_ref="hh_demo")

    line("submit intake (producer=user)")
    orc.submit_stage(case, "wealth_intake", INTAKE, producer="user")
    case = orc.load(); print("  intake:", case["stages"]["wealth_intake"]["status"])

    line("run script stages in DAG order")
    for stage in ("portfolio_analysis", "tax_considerations", "longevity_modeling"):
        env = orc.run_stage(orc.load(), stage)
        print(f"  {stage}: {env['status']}  hash={env['provenance']['output_hash'][:22]}..  seed={env['provenance']['rng_seed']}")

    case = orc.load()
    port = case["stages"]["portfolio_analysis"]["output"]
    long = case["stages"]["longevity_modeling"]["output"]
    tax = case["stages"]["tax_considerations"]["output"]
    print("\n  sourced numbers (every one traceable to a script run):")
    print("   total value      :", port["portfolio_summary"]["total_portfolio_value"])
    print("   allocation       :", {k: v for k, v in port["current_allocation"]["broad_asset_group_allocation"].items() if v})
    print("   MC success       :", long["monte_carlo"]["success_probability"])
    print("   p10 ending value :", long["monte_carlo"]["p10_ending_value"])
    print("   net embedded gain:", tax["taxable_gain_loss_snapshot"]["net_taxable_embedded_gain_loss"])

    line("consolidated cross-cutting collections")
    c = case["consolidated"]
    print("  missing_information:", len(c["missing_information"]),
          "| prof_review_flags:", len(c["professional_review_flags"]),
          "| auto HITL checkpoints:", len(case["gates"]["hitl_checkpoints"]))

    line("submit reporting (producer=model, no math) + gates")
    orc.submit_stage(orc.load(), "reporting", REPORT_OUTPUT, producer="model",
                     notes="Synthesis only; numbers sourced via consumed_from.")
    case = orc.load()
    print("  try deliver before gates:", orc.deliver(case))
    # resolve the auto-raised HITL checkpoint, then gates
    for cp in case["gates"]["hitl_checkpoints"]:
        cp["status"] = "resolved"; cp["resolved_by"] = "adviser_jdoe"
    orc.save(case)
    orc.set_compliance(orc.load(), passed=True)
    orc.signoff(orc.load(), approved=True, adviser_ref="adviser_jdoe")
    print("  deliver after gates:", orc.deliver(orc.load()))

    line("replay verification (re-run script on archived input; hash must match)")
    print(" ", json.dumps(orc.verify(orc.load(), "longevity_modeling"), indent=2))

    line("staleness: edit intake -> downstream must go stale")
    case = orc.load()
    edited = dict(INTAKE); edited = json.loads(json.dumps(edited))
    edited["accounts"][0]["balance"] = 700000  # taxable brokerage changed
    orc.submit_stage(case, "wealth_intake", edited, producer="user", notes="balance corrected")
    case = orc.load()
    for s in ("portfolio_analysis", "tax_considerations", "longevity_modeling", "reporting"):
        env = case["stages"].get(s)
        print(f"  {s}: {env['status'] if env else '—'}")

    line("validate whole case against planning_case.schema.json")
    print(" ", orc.validate_case(orc.load()))

    print(f"\nDemo case + artifact store written to: {WORK}")


if __name__ == "__main__":
    main()
