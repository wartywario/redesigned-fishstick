#!/usr/bin/env python3
"""
Stage registry for the wealth-planning orchestrator.

Declares, per stage: who produces it (script vs model/user), the script to run,
its dependencies, its output schema (for validation), and — for script stages —
a deterministic `build_input` adapter that assembles the script's input object
from prior stage outputs.

These `build_input` functions ARE the pipeline seams. They use the real emitted
field names (see each skill's references/), which is where the field-name
mismatches that broke the reporting skill get resolved once, in code, instead of
being re-derived ad hoc each run. Where intake does not supply a required modeling
input (e.g. retirement spending), the builder leaves it absent so the downstream
script surfaces it as missing — never guesses.
"""

from __future__ import annotations

import os
from pathlib import Path

SKILLS_ROOT = Path(os.environ.get("ORCH_SKILLS_ROOT", Path.home() / ".claude" / "skills"))


def stage_output(case: dict, stage: str) -> dict:
    env = case["stages"].get(stage)
    return env["output"] if env and env.get("output") else {}


# ── deterministic input adapters (the seams) ───────────────────────────────────

def build_portfolio_input(case: dict) -> dict:
    intake = stage_output(case, "wealth_intake")
    inp = {
        "accounts": intake.get("accounts", []),
        "holdings": intake.get("holdings", []),
    }
    # target allocation, if the intake/risk profile carries one
    target = (intake.get("risk_profile") or {}).get("target_allocation")
    if target:
        inp["target_allocation"] = target
    # spending for cash-runway, from goals or expenses
    spend = _retirement_amount(intake)
    if spend is not None:
        inp["annual_spending"] = spend
    return inp


def build_tax_input(case: dict) -> dict:
    intake = stage_output(case, "wealth_intake")
    port = stage_output(case, "portfolio_analysis")
    inp = {
        "household": intake.get("household", {}),
        "accounts": intake.get("accounts", []),
        "holdings": intake.get("holdings", []),
        "tax_profile": intake.get("tax_profile", {}),
        "income": intake.get("income", []),
        "planning_context": intake.get("planning_context", {}),
    }
    total = (port.get("portfolio_summary") or {}).get("total_portfolio_value")
    if total is not None:
        inp["portfolio"] = {"total_value": total}
    return inp


def build_longevity_input(case: dict) -> dict:
    intake = stage_output(case, "wealth_intake")
    port = stage_output(case, "portfolio_analysis")
    tax = stage_output(case, "tax_considerations")

    hh = intake.get("household", {})
    goals = intake.get("goals", [])
    total = (port.get("portfolio_summary") or {}).get("total_portfolio_value")
    broad = ((port.get("current_allocation") or {}).get("broad_asset_group_allocation") or {})

    retire = hh.get("planned_retirement_age") or _retirement_age(goals)
    inp = {
        "starting_portfolio_value": total,
        "current_age": hh.get("client_age"),
        "retirement_age": retire,
        "planning_horizon_age": hh.get("planning_horizon_age"),
        "annual_spending": _retirement_amount(intake),
        "spending_inflation_adjusted": True,
        "asset_allocation": {
            "equity": broad.get("equity", 0.0),
            "bonds": broad.get("fixed_income", 0.0),
            "cash": broad.get("cash", 0.0),
        },
        "return_assumptions": {},
        "income_sources": _income_sources(intake),
        "simulation_count": 10000,
        "random_seed": 12345,
    }
    # tax handoff: state income tax -> tax drag assumption (flagged for CPA confirmation)
    st = ((tax.get("downstream_handoff") or {}).get("for_longevity_modeling") or {})
    if st.get("state_has_income_tax"):
        inp["return_assumptions"]["tax_drag"] = 0.004
    return inp


# ── helpers ────────────────────────────────────────────────────────────────────

def _retirement_goal(intake: dict) -> dict | None:
    for g in intake.get("goals", []):
        if g.get("category") in ("retirement", "retirement_income"):
            return g
    return None


def _retirement_amount(intake: dict):
    g = _retirement_goal(intake)
    return g.get("amount") if g else None


def _retirement_age(goals: list):
    for g in goals:
        if g.get("category") in ("retirement", "retirement_income"):
            return g.get("target_age_or_date")
    return None


def _income_sources(intake: dict) -> list:
    out = []
    for inc in intake.get("income", []):
        src = (inc.get("source") or "").lower()
        if "social security" in src or "pension" in src:
            out.append({
                "source": inc.get("source"),
                "amount": inc.get("amount"),
                "start_age": inc.get("start_age_or_date"),
                "end_age": inc.get("end_age_or_date"),
                "inflation_adjusted": inc.get("inflation_adjusted", True),
            })
    return out


# ── registry ─────────────────────────────────────────────────────────────────────

STAGE_REGISTRY = {
    "wealth_intake": {
        "producer": "model",  # LLM parses raw input -> intake JSON (or "user" for a form)
        "skill_version": "1.0.0",
        "output_schema_ref": "wealth-intake/references/schema.json",
        "build_input": None,
    },
    "portfolio_analysis": {
        "producer": "script",
        "skill_version": "1.0.0",
        "script": "portfolio-analysis/scripts/portfolio.py",
        "script_version": "1.0.0",
        "output_schema_ref": "portfolio-analysis/references/schema.md",  # md = not machine-validated
        "build_input": build_portfolio_input,
    },
    "tax_considerations": {
        "producer": "script",
        "skill_version": "1.0.0",
        "script": "tax-considerations/scripts/tax_flags.py",
        "script_version": "1.0.0",
        "output_schema_ref": "tax-considerations/references/output_schema.json",
        "build_input": build_tax_input,
    },
    "longevity_modeling": {
        "producer": "script",
        "skill_version": "1.0.0",
        "script": "longevity-modeling/scripts/longevity.py",
        "script_version": "1.0.0",
        "output_schema_ref": "longevity-modeling/references/schema.md",
        "build_input": build_longevity_input,
    },
    "scenario_analysis": {
        "producer": "script",        # not built yet
        "skill_version": "0.0.0",
        "script": "scenario-analysis/scripts/scenarios.py",
        "script_version": "0.0.0",
        "output_schema_ref": None,
        "build_input": lambda case: {},
    },
    "rebalancing": {
        "producer": "script",        # not built yet
        "skill_version": "0.0.0",
        "script": "rebalancing/scripts/rebalance.py",
        "script_version": "0.0.0",
        "output_schema_ref": None,
        "build_input": lambda case: {},
    },
    "reporting": {
        "producer": "model",  # LLM synthesis, no math
        "skill_version": "1.0.0",
        "output_schema_ref": None,
        "build_input": None,
    },
    "compliance_review": {
        "producer": "model",  # deterministic classifier in production; modelled here as a gate
        "skill_version": "1.0.0",
        "output_schema_ref": None,
        "build_input": None,
    },
}
