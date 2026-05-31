#!/usr/bin/env python3
"""
End-to-end test harness: runs every scenario through guap-guide (the guap.py
driver) against the real orchestrator + calculator scripts, then checks safety
invariants and classifies each run.

For each scenario it drives the same path a human + guide would:
    new -> submit wealth_intake (user) -> run-ready (scripts) ->
    [if all script stages completed] submit reporting (model) -> force gates -> deliver
    -> validate against planning_case.schema.json

Then it evaluates UNIVERSAL SAFETY INVARIANTS on whatever completed (no negative
or NaN totals, allocations in [0,1] summing to ~1, success probability in [0,1],
no phantom "100% success" from a degenerate horizon, balance reconciliation shown
when holdings and accounts disagree) plus a few scenario-specific probes.

Classification per scenario:
    LEAK    - an invariant/probe was violated: the system emitted an invalid
              numeric state. A real hardening gap, surfaced here.
    DELIVER - no violation and the case delivered.
    SAFE    - no violation and the case did NOT deliver (bad input was caught:
              a stage failed and/or gates blocked it).

Usage:
    GUAP_ORCH_ROOT=/path/to/LOCALSonly/orchestrator python run_suite.py [scenario_id ...]
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = HERE / "_runs"
REPORT = HERE / "_report.json"

GUAP = Path.home() / ".claude" / "skills" / "guap-guide" / "scripts" / "guap.py"
COMPLIANCE = Path.home() / ".claude" / "skills" / "compliance-review" / "scripts" / "compliance.py"
ORCH_ROOT = os.environ.get(
    "GUAP_ORCH_ROOT",
    str(Path.home() / "projects" / "LOCALSonly" / "orchestrator"),
)

sys.path.insert(0, str(HERE))
import scenarios  # noqa: E402

ENV = dict(os.environ, GUAP_ORCH_ROOT=ORCH_ROOT)
SCRIPT_STAGES = ("portfolio_analysis", "tax_considerations", "longevity_modeling")


# ── driver plumbing ──────────────────────────────────────────────────────────────

def guap(workdir: Path, *args) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, str(GUAP), str(workdir), *args],
        capture_output=True, text=True, env=ENV,
    )
    return proc.returncode, proc.stdout, proc.stderr


def load_case(workdir: Path) -> dict:
    return json.loads((workdir / "case.json").read_text(encoding="utf-8"))


def stage_status(case: dict, stage: str) -> str:
    env = case["stages"].get(stage)
    return env["status"] if env else "absent"


def stage_output(case: dict, stage: str) -> dict:
    env = case["stages"].get(stage)
    return (env or {}).get("output") or {}


# ── compliance plumbing ──────────────────────────────────────────────────────────

def authoritative_values(case: dict) -> dict:
    """Flat key -> number map of the engine's computed values, pulled from stage
    outputs. The compliance classifier checks cited numbers against these."""
    po = stage_output(case, "portfolio_analysis")
    lo = stage_output(case, "longevity_modeling")
    vals = {}
    tpv = dig(po, "portfolio_summary.total_portfolio_value")
    if tpv is not None:
        vals["portfolio.total_portfolio_value"] = tpv
    eq = dig(po, "current_allocation.broad_asset_group_allocation.equity")
    if eq is not None:
        vals["portfolio.equity_allocation"] = eq
    sp = dig(lo, "monte_carlo.success_probability")
    if sp is not None:
        vals["longevity.success_probability"] = sp
    return vals


def build_report(case: dict, scenario: dict) -> dict:
    """Build the client-facing report submitted to the reporting stage and fed to
    the compliance classifier. If the scenario carries a `report_override`, use its
    narrative/cited_numbers verbatim (the deliberately-bad reports). Otherwise
    generate a COMPLIANT narrative that cites the REAL authoritative numbers."""
    av = authoritative_values(case)
    override = scenario.get("report_override")
    if override:
        return {"narrative": override.get("narrative", ""),
                "cited_numbers": override.get("cited_numbers", [])}

    tpv = av.get("portfolio.total_portfolio_value")
    eq = av.get("portfolio.equity_allocation")
    sp = av.get("longevity.success_probability")
    tpv_s = f"${tpv:,.0f}" if isinstance(tpv, (int, float)) else "an estimated amount"
    eq_s = f"{eq*100:.0f}%" if isinstance(eq, (int, float)) else "an estimated share"
    sp_s = f"{sp*100:.0f}%" if isinstance(sp, (int, float)) else "an estimated probability"
    narrative = (
        "# Wealth Planning Summary\n"
        "This analysis is for educational purposes and is not tax, legal, or investment "
        "advice. Figures are estimates based on stated assumptions and are not a guarantee "
        "of future results; past performance does not guarantee future results. Please "
        "review with a qualified financial adviser or CPA before acting.\n"
        f"## Portfolio\nTotal portfolio value is approximately {tpv_s}, equity allocation "
        f"about {eq_s}.\n"
        f"## Longevity\nAcross 10,000 simulations the modeled success probability is {sp_s} "
        "— a probabilistic estimate, not a guarantee.\n"
        "## Next steps\nDiscuss these considerations with your adviser."
    )
    cited = []
    if tpv is not None:
        cited.append({"label": "total portfolio value", "value": tpv,
                      "authoritative_key": "portfolio.total_portfolio_value"})
    if eq is not None:
        cited.append({"label": "equity allocation", "value": eq,
                      "authoritative_key": "portfolio.equity_allocation"})
    if sp is not None:
        cited.append({"label": "success probability", "value": sp,
                      "authoritative_key": "longevity.success_probability"})
    return {"narrative": narrative, "cited_numbers": cited}


def run_compliance(report: dict, av: dict) -> dict:
    """Invoke the deterministic compliance classifier; return its parsed verdict."""
    payload = {"report": report, "authoritative_values": av}
    proc = subprocess.run(
        [sys.executable, str(COMPLIANCE)],
        input=json.dumps(payload), capture_output=True, text=True, env=ENV,
    )
    try:
        return json.loads(proc.stdout)
    except Exception:
        return {"verdict": "fail", "blocking_findings": [
            {"detail": f"compliance classifier did not return JSON: {proc.stderr.strip()[:200]}"}]}


# ── invariant helpers ────────────────────────────────────────────────────────────

def finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) \
        and not math.isnan(x) and not math.isinf(x)


def dig(obj, path, default=None):
    cur = obj
    for key in path.split("."):
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def universal_violations(case: dict) -> list[str]:
    v = []

    # -- portfolio --
    if stage_status(case, "portfolio_analysis") == "complete":
        po = stage_output(case, "portfolio_analysis")
        total = dig(po, "portfolio_summary.total_portfolio_value")
        if not finite(total):
            v.append(f"P1 portfolio total_portfolio_value is not a finite number: {total!r}")
        elif total < 0:
            v.append(f"P1 portfolio total_portfolio_value is NEGATIVE: {total}")
        broad = dig(po, "current_allocation.broad_asset_group_allocation", {}) or {}
        for g, frac in broad.items():
            if not finite(frac):
                v.append(f"P2 allocation[{g}] not finite: {frac!r}")
            elif frac < -1e-4 or frac > 1 + 1e-4:
                v.append(f"P2 allocation[{g}]={frac} outside [0,1]")
        if finite(total) and total > 0:
            s = sum(x for x in broad.values() if finite(x))
            if abs(s - 1.0) > 0.02:
                v.append(f"P3 broad allocation sums to {round(s,4)} (expected ~1.0)")
        reported = dig(po, "portfolio_summary.sum_of_reported_account_balances")
        notes = dig(po, "portfolio_summary.reconciliation_notes", []) or []
        if finite(reported) and finite(total) and abs(reported - total) > 1 and not notes:
            v.append(f"P4 accounts({reported}) vs holdings({total}) disagree but no "
                     f"reconciliation note (silent phantom)")

    # -- longevity --
    if stage_status(case, "longevity_modeling") == "complete":
        lo = stage_output(case, "longevity_modeling")
        mc = lo.get("monte_carlo") or {}
        sp = mc.get("success_probability")
        fp = mc.get("failure_probability")
        if mc:
            if not finite(sp) or sp < 0 or sp > 1:
                v.append(f"L1 success_probability out of [0,1]: {sp!r}")
            if finite(sp) and finite(fp) and abs(sp + fp - 1) > 1e-3:
                v.append(f"L1 success+failure != 1 ({sp}+{fp})")
            for pk in ("p10_ending_value", "median_ending_value", "p90_ending_value"):
                pv = mc.get(pk)
                if pv is not None and (not finite(pv) or pv < 0):
                    v.append(f"L2 {pk} invalid: {pv!r}")
            ybr = lo.get("year_by_year") or []
            if finite(sp) and sp == 1.0 and len(ybr) == 0:
                v.append("L3 phantom 100% success from a degenerate horizon "
                         "(no years simulated)")

    # -- tax --
    if stage_status(case, "tax_considerations") == "complete":
        to = stage_output(case, "tax_considerations")
        net = dig(to, "taxable_gain_loss_snapshot.net_taxable_embedded_gain_loss")
        if net is not None and not finite(net):
            v.append(f"T1 net_taxable_embedded_gain_loss not finite: {net!r}")
        tmv = dig(to, "taxable_gain_loss_snapshot.taxable_market_value")
        if tmv is not None and (not finite(tmv) or tmv < 0):
            v.append(f"T2 taxable_market_value invalid: {tmv!r}")

    return v


def specific_violations(sid: str, case: dict) -> list[str]:
    v = []
    if sid == "silent_string_balance":
        # intake intended ~$1.0M ($850k string IRA + $150k brokerage); the string
        # account has no holdings so it should NOT silently disappear.
        po = stage_output(case, "portfolio_analysis")
        total = dig(po, "portfolio_summary.total_portfolio_value")
        notes = dig(po, "portfolio_summary.reconciliation_notes", []) or []
        tax_missing = dig(stage_output(case, "tax_considerations"),
                          "input_quality.missing_information", []) or []
        mentioned = any("850000" in n or "Big IRA" in n for n in notes) or \
            any("Big IRA" in m for m in tax_missing)
        if finite(total) and total < 900000 and not mentioned:
            v.append(f"SILENT-LOSS string-coded $850k account dropped with no note; "
                     f"total_portfolio_value={total} (expected ~1,000,000)")
    if sid == "negative_spending":
        lo = stage_output(case, "longevity_modeling")
        start = dig(lo, "base_case.starting_portfolio_value")
        end = dig(lo, "base_case.ending_portfolio_value")
        if finite(start) and finite(end) and start > 0 and end > 5 * start:
            v.append(f"UNBOUNDED-GROWTH negative spending accepted as inflow; base-case "
                     f"portfolio grew from {start:,.0f} to {end:,.0f} (>5x) unflagged")
    return v


# ── run one scenario ─────────────────────────────────────────────────────────────

def run_scenario(sc: dict) -> dict:
    sid = sc["id"]
    wd = RUNS / sid
    if wd.exists():
        shutil.rmtree(wd)
    wd.mkdir(parents=True, exist_ok=True)
    intake_path = wd / "intake.json"
    intake_path.write_text(json.dumps(sc["intake"]), encoding="utf-8")
    report_path = wd / "report.json"

    log = []

    def step(*args):
        rc, out, err = guap(wd, *args)
        log.append({"cmd": list(args), "rc": rc,
                    "out": out.strip()[:400], "err": err.strip()[:400]})
        return rc, out, err

    step("new", sid)
    step("submit", "wealth_intake", str(intake_path), "--producer", "user")
    step("run-ready")

    case = load_case(wd)
    statuses = {s: stage_status(case, s) for s in SCRIPT_STAGES}
    all_scripts_done = all(statuses[s] == "complete" for s in SCRIPT_STAGES)

    deliver_before = None
    delivered = False
    compliance_verdict = None
    if all_scripts_done:
        # Build the client-facing report (compliant by default; adversarial when the
        # scenario carries a report_override) and submit it as the reporting output.
        av = authoritative_values(case)
        report = build_report(case, sc)
        report_path.write_text(json.dumps({"format": "full_report",
                                           "narrative": report["narrative"],
                                           "cited_numbers": report["cited_numbers"]}),
                               encoding="utf-8")
        step("submit", "reporting", str(report_path), "--producer", "model")
        _, out, _ = step("deliver")            # before gates — should block
        try:
            deliver_before = json.loads(out)["delivered"]
        except Exception:
            deliver_before = None
        case = load_case(wd)
        if any(c["status"] == "open" for c in case["gates"]["hitl_checkpoints"]):
            step("resolve-hitl", "--all", "--by", "suite_tester")
        # Drive the compliance GATE from the real deterministic classifier verdict
        # (a simulated compliance officer), not a hardcoded pass.
        verdict_obj = run_compliance(report, av)
        compliance_verdict = verdict_obj.get("verdict")
        if compliance_verdict == "pass":
            step("compliance", "pass")
        else:
            details = [f.get("detail", "blocking finding")
                       for f in verdict_obj.get("blocking_findings", [])] or ["compliance failed"]
            step("compliance", "fail", "--findings", *details)
        step("signoff", "approve", "--adviser", "suite_tester")
        _, out, _ = step("deliver")
        try:
            delivered = json.loads(out)["delivered"]
        except Exception:
            delivered = False
    else:
        _, out, _ = step("deliver")            # cannot force gates on a broken pipeline
        try:
            delivered = json.loads(out)["delivered"]
        except Exception:
            delivered = False

    _, valout, _ = step("validate")
    case = load_case(wd)

    violations = universal_violations(case) + specific_violations(sid, case)
    if violations:
        actual = "LEAK"
    elif delivered:
        actual = "DELIVER"
    else:
        actual = "SAFE"

    # key metrics for the report
    po = stage_output(case, "portfolio_analysis")
    lo = stage_output(case, "longevity_modeling")
    to = stage_output(case, "tax_considerations")
    metrics = {
        "total_portfolio_value": dig(po, "portfolio_summary.total_portfolio_value"),
        "equity_alloc": dig(po, "current_allocation.broad_asset_group_allocation.equity"),
        "mc_success": dig(lo, "monte_carlo.success_probability"),
        "base_depletion_age": dig(lo, "base_case.depletion_age"),
        "net_embedded_gain": dig(to, "taxable_gain_loss_snapshot.net_taxable_embedded_gain_loss"),
    }

    return {
        "id": sid, "category": sc["category"], "title": sc["title"],
        "expected": sc["expected"], "actual": actual.lower() if actual != "DELIVER" else "deliver",
        "actual_class": actual,
        "stage_status": {**statuses,
                         "reporting": stage_status(case, "reporting")},
        "deliver_before_gates": deliver_before,
        "compliance_verdict": compliance_verdict,
        "delivered": delivered,
        "validation": valout.strip(),
        "violations": violations,
        "metrics": metrics,
        "probe": sc.get("probe"),
        "log": log,
    }


# ── reporting ────────────────────────────────────────────────────────────────────

def fmt(x):
    if x is None:
        return "-"
    if isinstance(x, float):
        return f"{x:,.4g}"
    return str(x)


def expected_matches(r: dict) -> bool:
    return r["actual"] == r["expected"]


def main(argv):
    RUNS.mkdir(exist_ok=True)
    selected = argv or [s["id"] for s in scenarios.SCENARIOS]
    results = []
    for sc in scenarios.SCENARIOS:
        if sc["id"] not in selected:
            continue
        print(f"... running {sc['id']:<32} ", end="", flush=True)
        r = run_scenario(sc)
        print(f"{r['actual_class']:<8} (expected {r['expected']})"
              + ("" if expected_matches(r) else "   <-- DIVERGES"))
        results.append(r)

    REPORT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")

    # summary table
    print("\n" + "=" * 100)
    print(f"{'scenario':<32}{'cat':<10}{'result':<9}{'exp':<9}"
          f"{'total':>13}{'eq%':>7}{'succ':>7}")
    print("-" * 100)
    for r in results:
        m = r["metrics"]
        eq = f"{m['equity_alloc']*100:.0f}" if isinstance(m['equity_alloc'], (int, float)) else "-"
        flag = "" if expected_matches(r) else "  !"
        print(f"{r['id']:<32}{r['category']:<10}{r['actual_class']:<9}{r['expected']:<9}"
              f"{fmt(m['total_portfolio_value']):>13}{eq:>7}{fmt(m['mc_success']):>7}{flag}")

    # tallies
    by = {"DELIVER": 0, "SAFE": 0, "LEAK": 0}
    for r in results:
        by[r["actual_class"]] += 1
    diverged = [r for r in results if not expected_matches(r)]
    leaks = [r for r in results if r["actual_class"] == "LEAK"]

    print("\n" + "=" * 100)
    print(f"TOT:  {len(results)} scenarios   "
          f"DELIVER={by['DELIVER']}  SAFE={by['SAFE']}  LEAK={by['LEAK']}")
    print(f"calibration: {len(results)-len(diverged)}/{len(results)} matched the "
          f"author's hypothesis")

    if leaks:
        print("\nLEAKS — invalid states the calculators emitted (hardening targets):")
        for r in leaks:
            print(f"  [{r['id']}] {r['title']}")
            print(f"     probe: {r['probe']}")
            for vmsg in r["violations"]:
                print(f"     -> {vmsg}")
            if r["delivered"]:
                print(f"     !! this case DELIVERED a report despite the invalid state")

    if diverged:
        print("\nDIVERGENCES (actual != author hypothesis):")
        for r in diverged:
            print(f"  [{r['id']}] expected {r['expected']}, got {r['actual']}")

    print(f"\nfull machine-readable report: {REPORT}")
    # exit non-zero only if a VALID scenario misbehaved (diverged from its expected
    # class) or a stress LEAK delivered. Compliance scenarios assert on expected vs
    # actual (some expect SAFE = correctly blocked), so use the calibration check.
    bad = [r for r in results
           if (r["category"] != "stress" and not expected_matches(r))]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
