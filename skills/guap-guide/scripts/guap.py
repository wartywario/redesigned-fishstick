#!/usr/bin/env python3
"""
guap-guide driver — the hands of the guap-guide skill.

This is a thin, deterministic wrapper around the wealth-planning Orchestrator
(engine.py). It exists because the engine's own CLI deliberately does NOT expose
`submit_stage` or the gate operations ("intended to be driven from code"). The
guap-guide *skill* (an LLM) holds the conversation and produces intake/report
content; THIS script is how it injects that content and advances the case.

It does NOT do any planning math and it does NOT decide gate outcomes. Math comes
only from the engine's `script` stages; gate approvals (compliance, signoff,
HITL) are passed in by a human and merely recorded here.

Locating the engine:
  Set GUAP_ORCH_ROOT to the directory that contains engine.py / registry.py
  (the orchestrator package). If unset, a few sensible defaults are tried.

Usage:
  python guap.py <workdir> status [--json]
  python guap.py <workdir> new <case_id> [--household-ref REF]
  python guap.py <workdir> submit <stage> <file.json|-> --producer model|user|external [--notes "..."]
  python guap.py <workdir> run <stage>
  python guap.py <workdir> run-ready
  python guap.py <workdir> verify <stage>
  python guap.py <workdir> compliance pass|fail [--findings "a" "b"]
  python guap.py <workdir> signoff approve|reject --adviser REF [--notes "..."]
  python guap.py <workdir> resolve-hitl (<checkpoint> | --all) --by REF
  python guap.py <workdir> deliver
  python guap.py <workdir> validate
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


# ── locate and import the engine ────────────────────────────────────────────────

def _find_orch_root() -> Path:
    env = os.environ.get("GUAP_ORCH_ROOT")
    candidates = []
    if env:
        candidates.append(Path(env))
    # common dev locations relative to home
    home = Path.home()
    candidates += [
        home / "projects" / "LOCALSonly" / "orchestrator",
        home / "LOCALSonly" / "orchestrator",
    ]
    for c in candidates:
        if (c / "engine.py").exists() and (c / "registry.py").exists():
            return c
    raise SystemExit(
        "Cannot locate the orchestrator package (engine.py/registry.py).\n"
        "Set GUAP_ORCH_ROOT to the directory that contains them, e.g.\n"
        "  GUAP_ORCH_ROOT=/path/to/LOCALSonly/orchestrator"
    )


ORCH_ROOT = _find_orch_root()
sys.path.insert(0, str(ORCH_ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from engine import DAG, Orchestrator  # noqa: E402
from registry import SKILLS_ROOT, STAGE_REGISTRY  # noqa: E402


# ── helpers ─────────────────────────────────────────────────────────────────────

def _producer_of(stage: str) -> str:
    return STAGE_REGISTRY.get(stage, {}).get("producer", "?")


def _script_exists(stage: str) -> bool:
    reg = STAGE_REGISTRY.get(stage, {})
    if reg.get("producer") != "script":
        return False
    rel = reg.get("script")
    return bool(rel) and (SKILLS_ROOT / rel).exists()


def _load_arg(spec: str):
    """Load a JSON payload from a file path or '-' for stdin."""
    if spec == "-":
        return json.loads(sys.stdin.read())
    return json.loads(Path(spec).read_text(encoding="utf-8"))


# ── friendly status (the main UX win over the bare engine CLI) ──────────────────

def _status_struct(orc: Orchestrator) -> dict:
    case = orc.load()
    runnable = set(orc.runnable(case))
    stages = []
    for e in DAG:
        s = e["stage"]
        env = case["stages"].get(s)
        stages.append({
            "stage": s,
            "producer": _producer_of(s),
            "status": env["status"] if env else "pending",
            "runnable": s in runnable,
            "optional": bool(e.get("optional")),
            "script_built": _script_exists(s),
        })
    g = case["gates"]
    open_hitl = [c for c in g["hitl_checkpoints"] if c["status"] == "open"]
    ok, reasons = orc.can_deliver(case)
    return {
        "case_id": case["case_id"],
        "case_status": case["status"],
        "stages": stages,
        "gates": {
            "compliance_review": g["compliance_review"]["status"],
            "adviser_signoff": g["adviser_signoff"]["status"],
            "open_hitl_checkpoints": [
                {"checkpoint": c["checkpoint"], "reason": c.get("reason", "")}
                for c in open_hitl
            ],
        },
        "consolidated": {
            k: len(case["consolidated"].get(k, []))
            for k in ("missing_information", "assumptions",
                      "conflicts_or_uncertainties", "unknowns",
                      "professional_review_flags")
        },
        "deliverable": ok,
        "blocking_reasons": reasons,
        "next_actions": _next_actions(case, runnable, ok, reasons, open_hitl),
    }


def _next_actions(case, runnable, ok, reasons, open_hitl) -> list:
    """Plain, ordered guidance on what the guide should do or ask for next."""
    if ok and case["status"] == "delivered":
        return ["Case delivered. Nothing required."]
    if ok:
        return ["All gates clear and nothing stale — run `deliver`."]
    actions = []
    # 1. content/script work first
    for s in (e["stage"] for e in DAG):
        if s not in runnable:
            continue
        prod = _producer_of(s)
        if prod == "script" and _script_exists(s):
            actions.append(f"run script stage `{s}` (engine computes it).")
        elif prod in ("model", "user"):
            who = "interview the human and submit" if prod == "user" else "produce content and submit"
            actions.append(f"{who} `{s}` (producer={prod}).")
    # 2. stale re-runs
    stale = [e["stage"] for e in DAG
             if (case["stages"].get(e["stage"]) or {}).get("status") == "stale"]
    if stale:
        actions.append(f"re-run stale stages (an upstream edit invalidated them): {stale}")
    # 3. human-authority gates (the guide may NOT self-resolve these)
    if open_hitl:
        keys = [c["checkpoint"] for c in open_hitl]
        actions.append(f"HUMAN REVIEW REQUIRED — open HITL checkpoint(s) {keys}; "
                       f"present the reason, get an explicit human decision, then `resolve-hitl --by <ref>`.")
    if "compliance_review not passed" in reasons:
        actions.append("compliance must be set by the reviewer — `compliance pass|fail` (not the guide's call).")
    if "adviser_signoff not approved" in reasons:
        actions.append("adviser must sign off — `signoff approve|reject --adviser <ref>` (a human decision).")
    return actions or ["(no runnable stages; check dependencies / blocking reasons above)"]


def _print_status_human(st: dict):
    print(f"case {st['case_id']}  status={st['case_status']}")
    print("  stages:")
    for s in st["stages"]:
        mark = "  <- RUNNABLE" if s["runnable"] else ""
        opt = " (optional)" if s["optional"] else ""
        unbuilt = "" if (s["producer"] != "script" or s["script_built"]) else " [script not built]"
        print(f"    {s['stage']:<20} {s['status']:<10} {s['producer']:<8}{mark}{opt}{unbuilt}")
    g = st["gates"]
    print(f"  gates: compliance={g['compliance_review']}  signoff={g['adviser_signoff']}  "
          f"open_hitl={len(g['open_hitl_checkpoints'])}")
    for c in g["open_hitl_checkpoints"]:
        print(f"    HITL open: {c['checkpoint']} — {c['reason']}")
    c = st["consolidated"]
    print(f"  collected: missing={c['missing_information']} flags={c['professional_review_flags']} "
          f"assumptions={c['assumptions']} unknowns={c['unknowns']}")
    print(f"  deliverable: {st['deliverable']}"
          + ("" if st["deliverable"] else f"  blocked_by={st['blocking_reasons']}"))
    print("  next:")
    for a in st["next_actions"]:
        print(f"    - {a}")


# ── commands ────────────────────────────────────────────────────────────────────

def cmd_status(orc, args):
    st = _status_struct(orc)
    if args.json:
        print(json.dumps(st, indent=2))
    else:
        _print_status_human(st)


def cmd_new(orc, args):
    orc.new_case(args.case_id, household_ref=args.household_ref)
    print(f"created case {args.case_id} in {orc.workdir}")


def cmd_submit(orc, args):
    stage = args.stage
    prod = _producer_of(stage)
    if prod == "script":
        raise SystemExit(f"`{stage}` is a script stage — use `run`, not `submit`. "
                         f"submit is only for model/user/external content.")
    payload = _load_arg(args.payload)
    env = orc.submit_stage(orc.load(), stage, payload, producer=args.producer, notes=args.notes)
    print(f"submitted {stage}: {env['status']}  output_hash={env['provenance']['output_hash']}")


def cmd_run(orc, args):
    stage = args.stage
    if _producer_of(stage) != "script":
        raise SystemExit(f"`{stage}` is a {_producer_of(stage)} stage — use `submit`, not `run`.")
    env = orc.run_stage(orc.load(), stage)
    print(f"ran {stage}: {env['status']}  "
          f"output_hash={env['provenance']['output_hash'][:26]}..  seed={env['provenance']['rng_seed']}")


def cmd_run_ready(orc, args):
    """Run every currently-runnable, BUILT script stage in DAG order."""
    ran = []
    while True:
        case = orc.load()
        runnable = orc.runnable(case)
        target = next((e["stage"] for e in DAG
                       if e["stage"] in runnable and _script_exists(e["stage"])), None)
        if not target:
            break
        env = orc.run_stage(case, target)
        ran.append((target, env["status"]))
        print(f"ran {target}: {env['status']}  hash={env['provenance']['output_hash'][:26]}..")
        if env["status"] == "failed":
            break
    if not ran:
        print("no built script stages were runnable (check upstream model/user stages).")


def cmd_verify(orc, args):
    print(json.dumps(orc.verify(orc.load(), args.stage), indent=2))


def cmd_compliance(orc, args):
    passed = args.outcome == "pass"
    orc.set_compliance(orc.load(), passed=passed, blocking=args.findings or [])
    print(f"compliance_review set: {'passed' if passed else 'failed'}")


def cmd_signoff(orc, args):
    approved = args.outcome == "approve"
    orc.signoff(orc.load(), approved=approved, adviser_ref=args.adviser, notes=args.notes)
    print(f"adviser_signoff set: {'approved' if approved else 'rejected'} by {args.adviser}")


def cmd_resolve_hitl(orc, args):
    if not args.checkpoint and not args.all:
        raise SystemExit("specify a <checkpoint> or --all")
    case = orc.load()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    touched = []
    for c in case["gates"]["hitl_checkpoints"]:
        if c["status"] != "open":
            continue
        if args.all or c["checkpoint"] == args.checkpoint:
            c["status"] = "resolved"
            c["resolved_by"] = args.by
            c["resolved_at"] = now
            touched.append(c["checkpoint"])
    if not touched:
        raise SystemExit("no matching open checkpoint(s) found.")
    orc.save(case)
    print(f"resolved HITL checkpoint(s) {touched} by {args.by}")


def cmd_deliver(orc, args):
    print(json.dumps(orc.deliver(orc.load()), indent=2))


def cmd_validate(orc, args):
    print(orc.validate_case(orc.load()))


# ── arg parsing ──────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="guap.py", description="guap-guide driver for the wealth-planning orchestrator")
    p.add_argument("workdir", help="case working directory")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status").add_argument("--json", action="store_true")

    sp = sub.add_parser("new"); sp.add_argument("case_id"); sp.add_argument("--household-ref", default=None)

    sp = sub.add_parser("submit")
    sp.add_argument("stage"); sp.add_argument("payload", help="JSON file path or '-' for stdin")
    sp.add_argument("--producer", required=True, choices=["model", "user", "external"])
    sp.add_argument("--notes", default=None)

    sub.add_parser("run").add_argument("stage")
    sub.add_parser("run-ready")
    sub.add_parser("verify").add_argument("stage")

    sp = sub.add_parser("compliance"); sp.add_argument("outcome", choices=["pass", "fail"])
    sp.add_argument("--findings", nargs="*", default=None)

    sp = sub.add_parser("signoff"); sp.add_argument("outcome", choices=["approve", "reject"])
    sp.add_argument("--adviser", required=True); sp.add_argument("--notes", default=None)

    sp = sub.add_parser("resolve-hitl")
    sp.add_argument("checkpoint", nargs="?", default=None)
    sp.add_argument("--all", action="store_true"); sp.add_argument("--by", required=True)

    sub.add_parser("deliver")
    sub.add_parser("validate")
    return p


_DISPATCH = {
    "status": cmd_status, "new": cmd_new, "submit": cmd_submit, "run": cmd_run,
    "run-ready": cmd_run_ready, "verify": cmd_verify, "compliance": cmd_compliance,
    "signoff": cmd_signoff, "resolve-hitl": cmd_resolve_hitl, "deliver": cmd_deliver,
    "validate": cmd_validate,
}


def main(argv=None):
    args = build_parser().parse_args(argv)
    orc = Orchestrator(Path(args.workdir))
    _DISPATCH[args.cmd](orc, args)


if __name__ == "__main__":
    main()
