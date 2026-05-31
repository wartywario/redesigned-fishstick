#!/usr/bin/env python3
"""
Deterministic orchestrator for the wealth-planning skill suite.

Reads/writes a planning-case object (planning_case.schema.json), sequences the
stage DAG, invokes the deterministic calculator scripts for `script` stages,
accepts externally-produced output for `model`/`user` stages, records full
provenance (input/output hashes, rng_seed, consumed-from), detects staleness,
consolidates cross-cutting collections, and enforces the compliance/sign-off gates.

NO LLM is involved in sequencing, hashing, or gating — those are deterministic.
The LLM's role (parsing intake, narrating reports, adapter judgment) happens
*outside* this module and its results are injected via `submit_stage`.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from registry import STAGE_REGISTRY, SKILLS_ROOT, stage_output

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CASE_SCHEMA = PROJECT_ROOT / "planning_case.schema.json"
SCHEMA_VERSION = "1.0.0"

DAG = [
    {"stage": "wealth_intake", "depends_on": []},
    {"stage": "portfolio_analysis", "depends_on": ["wealth_intake"]},
    {"stage": "tax_considerations", "depends_on": ["wealth_intake", "portfolio_analysis"]},
    {"stage": "longevity_modeling", "depends_on": ["wealth_intake", "portfolio_analysis", "tax_considerations"]},
    {"stage": "scenario_analysis", "depends_on": ["longevity_modeling"], "optional": True},
    {"stage": "rebalancing", "depends_on": ["portfolio_analysis", "tax_considerations"], "optional": True},
    {"stage": "reporting", "depends_on": ["wealth_intake", "portfolio_analysis", "longevity_modeling", "tax_considerations"]},
    {"stage": "compliance_review", "depends_on": ["reporting"]},
]


# ── time / id / hashing ─────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_id(stage: str) -> str:
    return f"run_{stage}_{uuid.uuid4().hex[:8]}"


def canon(obj) -> bytes:
    """Canonical JSON bytes for stable hashing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def content_hash(obj) -> str:
    return "sha256:" + hashlib.sha256(canon(obj)).hexdigest()


# ── content-addressable artifact store (enables byte-replay) ────────────────────

class CAS:
    """Stores every input/output JSON as cas/<hash>.json so any run can be replayed."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, obj) -> str:
        h = content_hash(obj)
        p = self.root / (h.replace(":", "_") + ".json")
        if not p.exists():
            p.write_text(json.dumps(obj, indent=2), encoding="utf-8")
        return h

    def get(self, h: str):
        p = self.root / (h.replace(":", "_") + ".json")
        return json.loads(p.read_text(encoding="utf-8"))


# ── the orchestrator ────────────────────────────────────────────────────────────

class Orchestrator:
    def __init__(self, workdir: Path):
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.case_path = self.workdir / "case.json"
        self.cas = CAS(self.workdir / "cas")

    # -- persistence --

    def load(self) -> dict:
        return json.loads(self.case_path.read_text(encoding="utf-8"))

    def save(self, case: dict):
        case["updated_at"] = _now()
        self.case_path.write_text(json.dumps(case, indent=2), encoding="utf-8")

    def new_case(self, case_id: str, household_ref: str | None = None) -> dict:
        case = {
            "schema_version": SCHEMA_VERSION,
            "case_id": case_id,
            "household_ref": household_ref,
            "created_at": _now(),
            "updated_at": _now(),
            "status": "intake_in_progress",
            "pipeline": {"dag": DAG, "active_run_id": None},
            "stages": {},
            "consolidated": {
                "missing_information": [], "assumptions": [],
                "conflicts_or_uncertainties": [], "unknowns": [],
                "professional_review_flags": [],
            },
            "gates": {
                "compliance_review": {"status": "not_run", "run_id": None, "produced_at": None, "blocking_findings": []},
                "adviser_signoff": {"status": "pending", "adviser_ref": None, "signed_at": None, "notes": None},
                "hitl_checkpoints": [],
            },
            "audit_log": [],
        }
        self.save(case)
        return case

    # -- DAG scheduling --

    def _deps(self, stage: str) -> list[str]:
        for e in DAG:
            if e["stage"] == stage:
                return e["depends_on"]
        return []

    def runnable(self, case: dict) -> list[str]:
        """Stages whose deps are all complete and which are pending/stale/absent."""
        out = []
        for e in DAG:
            stage = e["stage"]
            env = case["stages"].get(stage)
            status = env["status"] if env else "pending"
            if status in ("complete",):
                continue
            deps_ok = all(
                (case["stages"].get(d) or {}).get("status") == "complete"
                for d in e["depends_on"]
            )
            if deps_ok:
                out.append(stage)
        return out

    # -- provenance assembly --

    def _provenance(self, case, stage, producer, output, *, input_hash=None,
                    script_name=None, script_version=None, rng_seed=None, notes=None) -> dict:
        consumed = []
        for d in self._deps(stage):
            env = case["stages"].get(d)
            if env:
                consumed.append({"stage": d, "output_hash": env["provenance"]["output_hash"]})
        prov = {
            "source_skill": stage,
            "skill_version": STAGE_REGISTRY[stage].get("skill_version", "1.0.0"),
            "producer": producer,
            "script_name": script_name,
            "script_version": script_version,
            "run_id": _run_id(stage),
            "produced_at": _now(),
            "output_hash": content_hash(output),
            "rng_seed": rng_seed,
            "consumed_from": consumed,
            "notes": notes,
        }
        if input_hash is not None:
            prov["input_hash"] = input_hash
        return prov

    def _audit(self, case, prov, stage, action, outcome):
        case["audit_log"].append({
            "run_id": prov["run_id"], "stage": stage, "action": action,
            "timestamp": prov["produced_at"], "producer": prov["producer"],
            "script_name": prov.get("script_name"), "script_version": prov.get("script_version"),
            "input_hash": prov.get("input_hash"), "output_hash": prov.get("output_hash"),
            "rng_seed": prov.get("rng_seed"), "executor": "orchestrator", "outcome": outcome,
        })

    # -- running a script stage --

    def run_stage(self, case: dict, stage: str, overrides: dict | None = None) -> dict:
        reg = STAGE_REGISTRY[stage]
        if reg["producer"] != "script":
            raise ValueError(f"{stage} is a '{reg['producer']}' stage; use submit_stage()")
        if stage not in self.runnable(case):
            raise RuntimeError(f"{stage} is not runnable (dependencies incomplete)")

        # 1. build input (the deterministic adapter seam) + apply overrides
        inp = reg["build_input"](case)
        if overrides:
            inp = _deep_merge(inp, overrides)
        input_hash = self.cas.put(inp)

        # 2. invoke the script
        script = SKILLS_ROOT / reg["script"]
        proc = subprocess.run(
            [sys.executable, str(script)],
            input=json.dumps(inp), capture_output=True, text=True,
        )
        if proc.returncode != 0 and not proc.stdout.strip():
            output = {"error": "script_failed", "missing": [], "details": [proc.stderr.strip()[:500]]}
        else:
            output = json.loads(proc.stdout)

        failed = isinstance(output, dict) and output.get("error")
        output_for_store = {} if failed else output
        output_hash = self.cas.put(output)

        rng_seed = inp.get("random_seed") if isinstance(inp, dict) else None
        prov = self._provenance(
            case, stage, "script", output,
            input_hash=input_hash, script_name=reg["script"],
            script_version=reg.get("script_version", "1.0.0"), rng_seed=rng_seed,
        )
        prov["output_hash"] = output_hash  # hash the real output (incl. error)

        case["stages"][stage] = {
            "status": "failed" if failed else "complete",
            "provenance": prov,
            "output_schema_ref": reg.get("output_schema_ref"),
            "output": output_for_store,
            "error": output if failed else None,
        }
        self._audit(case, prov, stage, "invoke", "failed" if failed else "ok")

        if not failed:
            self._validate_output(stage, output)
        self.recompute_staleness(case)
        self.consolidate(case)
        self.save(case)
        return case["stages"][stage]

    # -- submitting a model/user/external stage --

    def submit_stage(self, case: dict, stage: str, output: dict, producer: str, notes=None) -> dict:
        reg = STAGE_REGISTRY[stage]
        if producer not in ("model", "user", "external"):
            raise ValueError("producer must be model|user|external")
        input_hash = self.cas.put({"_submitted_for": stage})
        output_hash = self.cas.put(output)
        prov = self._provenance(case, stage, producer, output,
                                input_hash=input_hash, notes=notes)
        prov["output_hash"] = output_hash
        case["stages"][stage] = {
            "status": "complete",
            "provenance": prov,
            "output_schema_ref": reg.get("output_schema_ref"),
            "output": output,
            "error": None,
        }
        self._audit(case, prov, stage, "invoke", "ok")
        self.recompute_staleness(case)
        self.consolidate(case)
        self.save(case)
        return case["stages"][stage]

    # -- replay verification (proves a number is reproducible) --

    def verify(self, case: dict, stage: str) -> dict:
        """Re-run a script stage on its archived input; confirm output hash matches."""
        env = case["stages"].get(stage)
        if not env or env["provenance"]["producer"] != "script":
            return {"stage": stage, "verifiable": False, "reason": "not a completed script stage"}
        inp = self.cas.get(env["provenance"]["input_hash"])
        script = SKILLS_ROOT / env["provenance"]["script_name"]
        proc = subprocess.run([sys.executable, str(script)], input=json.dumps(inp),
                              capture_output=True, text=True)
        replayed = json.loads(proc.stdout)
        replay_hash = content_hash(replayed)
        match = replay_hash == env["provenance"]["output_hash"]
        return {
            "stage": stage, "verifiable": True, "match": match,
            "recorded_output_hash": env["provenance"]["output_hash"],
            "replayed_output_hash": replay_hash,
            "rng_seed": env["provenance"]["rng_seed"],
        }

    # -- staleness --

    def recompute_staleness(self, case: dict):
        changed = True
        while changed:
            changed = False
            for e in DAG:
                stage = e["stage"]
                env = case["stages"].get(stage)
                if not env or env["status"] not in ("complete",):
                    continue
                for c in env["provenance"].get("consumed_from", []):
                    up = case["stages"].get(c["stage"])
                    up_stale = up and up["status"] == "stale"
                    up_missing = up is None
                    up_changed = up and up["provenance"]["output_hash"] != c["output_hash"]
                    if up_missing or up_changed or up_stale:
                        env["status"] = "stale"
                        changed = True
                        break

    # -- consolidation of cross-cutting collections --

    def consolidate(self, case: dict):
        cons = {"missing_information": [], "assumptions": [],
                "conflicts_or_uncertainties": [], "unknowns": [],
                "professional_review_flags": []}
        for e in DAG:
            stage = e["stage"]
            env = case["stages"].get(stage)
            if not env or env["status"] != "complete":
                continue
            out = env["output"]
            for item in _extract_missing(out):
                cons["missing_information"].append({"source_stage": stage, "text": item})
            for a in _as_str_list(out.get("assumptions")):
                kind = "user" if stage == "wealth_intake" else ("placeholder" if stage == "longevity_modeling" else "model")
                cons["assumptions"].append({"source_stage": stage, "kind": kind, "text": a})
            for c in _as_str_list(out.get("conflicts_or_uncertainties")):
                cons["conflicts_or_uncertainties"].append({"source_stage": stage, "text": c})
            for u in _extract_unknowns(out):
                cons["unknowns"].append({"source_stage": stage, "text": u})
            for f in _extract_flags(out):
                sev = f.get("severity", "review")
                cons["professional_review_flags"].append({
                    "source_stage": stage,
                    "category": f.get("category", "general"),
                    "severity": sev if sev in ("data_gap", "review", "high_priority_review") else "review",
                    "text": f.get("flag") or f.get("text") or "",
                    "requires_human_review": sev == "high_priority_review",
                })
        case["consolidated"] = cons
        self._raise_hitl(case)

    def _raise_hitl(self, case: dict):
        existing = {c["checkpoint"]: c for c in case["gates"]["hitl_checkpoints"]}
        for f in case["consolidated"]["professional_review_flags"]:
            if f["requires_human_review"]:
                key = f"{f['source_stage']}:{f['category']}"
                if key not in existing:
                    case["gates"]["hitl_checkpoints"].append({
                        "checkpoint": key, "reason": f["text"][:160],
                        "raised_by_stage": f["source_stage"], "status": "open",
                        "resolved_by": None, "resolved_at": None,
                    })
                    existing[key] = True

    # -- gates --

    def set_compliance(self, case, passed: bool, blocking=None):
        g = case["gates"]["compliance_review"]
        g["status"] = "passed" if passed else "failed"
        g["run_id"] = _run_id("compliance_review")
        g["produced_at"] = _now()
        g["blocking_findings"] = blocking or []
        case["audit_log"].append({
            "run_id": g["run_id"], "stage": "compliance_review", "action": "gate",
            "timestamp": g["produced_at"], "producer": "script", "script_name": None,
            "script_version": "1.0.0", "input_hash": None, "output_hash": None,
            "rng_seed": None, "executor": "orchestrator",
            "outcome": "ok" if passed else "blocked",
        })
        self.save(case)

    def signoff(self, case, approved: bool, adviser_ref: str, notes=None):
        s = case["gates"]["adviser_signoff"]
        s["status"] = "approved" if approved else "rejected"
        s["adviser_ref"] = adviser_ref
        s["signed_at"] = _now()
        s["notes"] = notes
        self.save(case)

    def can_deliver(self, case) -> tuple[bool, list[str]]:
        reasons = []
        if case["gates"]["compliance_review"]["status"] != "passed":
            reasons.append("compliance_review not passed")
        if case["gates"]["adviser_signoff"]["status"] != "approved":
            reasons.append("adviser_signoff not approved")
        open_cp = [c["checkpoint"] for c in case["gates"]["hitl_checkpoints"] if c["status"] == "open"]
        if open_cp:
            reasons.append(f"open HITL checkpoints: {open_cp}")
        stale = [e["stage"] for e in DAG if (case["stages"].get(e["stage"]) or {}).get("status") == "stale"]
        if stale:
            reasons.append(f"stale stages: {stale}")
        failed = [e["stage"] for e in DAG
                  if (case["stages"].get(e["stage"]) or {}).get("status") == "failed"]
        if failed:
            reasons.append(f"failed stages: {failed}")
        reasons += self._numeric_sanity(case)
        return (not reasons), reasons

    def _numeric_sanity(self, case) -> list[str]:
        """Defense-in-depth numeric gate: block delivery if any completed stage's
        recorded numbers are unusable (negative/NaN totals, allocations outside
        [0,1] or not summing to ~1, success probability outside [0,1], non-finite
        percentiles, or a degenerate zero-year projection). The calculators now
        reject these at the source; this catches anything that ever slips past."""
        def finite(x):
            return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)

        reasons = []
        pa = (case["stages"].get("portfolio_analysis") or {}).get("output") or {}
        summary = pa.get("portfolio_summary") or {}
        total = summary.get("total_portfolio_value")
        if summary:
            if not finite(total):
                reasons.append(f"portfolio total_portfolio_value not finite: {total}")
            elif total < 0:
                reasons.append(f"portfolio total_portfolio_value negative: {total}")
        broad = (pa.get("current_allocation") or {}).get("broad_asset_group_allocation") or {}
        if broad:
            s = 0.0
            for k, v in broad.items():
                if not finite(v):
                    reasons.append(f"allocation[{k}] not finite: {v}")
                else:
                    if v < -1e-9 or v > 1 + 1e-9:
                        reasons.append(f"allocation[{k}] outside [0,1]: {v}")
                    s += v
            if finite(total) and total > 0 and abs(s - 1.0) > 1e-3:
                reasons.append(f"broad allocations sum to {s:.4f}, not ~1.0")

        lm = (case["stages"].get("longevity_modeling") or {}).get("output") or {}
        if lm:
            mc = lm.get("monte_carlo") or {}
            sp = mc.get("success_probability")
            if sp is not None and (not finite(sp) or not 0.0 <= sp <= 1.0):
                reasons.append(f"success_probability invalid: {sp}")
            for key in ("p10_ending_value", "median_ending_value", "p90_ending_value"):
                val = mc.get(key)
                if val is not None and not finite(val):
                    reasons.append(f"{key} not finite: {val}")
            yby = lm.get("year_by_year")
            if isinstance(yby, list) and len(yby) == 0:
                reasons.append("longevity simulated zero years (degenerate horizon)")

        tx = (case["stages"].get("tax_considerations") or {}).get("output") or {}
        snap = tx.get("taxable_gain_loss_snapshot") or {}
        tmv = snap.get("taxable_market_value")
        if tmv is not None and (not finite(tmv) or tmv < 0):
            reasons.append(f"taxable_market_value invalid: {tmv}")
        return reasons

    def deliver(self, case) -> dict:
        ok, reasons = self.can_deliver(case)
        if ok:
            case["status"] = "delivered"
            self.save(case)
        return {"delivered": ok, "blocking_reasons": reasons}

    # -- validation --

    def validate_case(self, case) -> str:
        try:
            import jsonschema
            jsonschema.validate(case, json.loads(CASE_SCHEMA.read_text(encoding="utf-8")))
            return "case valid against planning_case.schema.json"
        except ImportError:
            return "jsonschema not installed; skipped case validation"

    def _validate_output(self, stage, output):
        """Validate a SCRIPT stage's output.

        A script's output is an *intermediate, partial* artifact: the model adds
        the qualitative sections later, so the skill's full final-response schema
        legitimately requires keys the script does not emit. We therefore validate
        the *shape of the fields the script does emit* (types, enums, nesting)
        without enforcing `required` completeness. Completeness is a final-response
        gate (reporting/compliance), not a script-stage check.
        """
        ref = STAGE_REGISTRY[stage].get("output_schema_ref")
        if not ref or not ref.endswith(".json"):
            return
        path = SKILLS_ROOT / ref
        if not path.exists():
            return
        try:
            import jsonschema
        except ImportError:
            return
        schema = _strip_required(json.loads(path.read_text(encoding="utf-8")))
        try:
            jsonschema.validate(output, schema)
        except jsonschema.ValidationError as ex:  # type: ignore
            raise RuntimeError(f"{stage} script output violates its schema shape: {ex.message}") from ex


# ── helpers ──────────────────────────────────────────────────────────────────────

def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _as_str_list(v):
    return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []


def _extract_missing(out: dict):
    items = list(_as_str_list(out.get("missing_information")))
    iq = out.get("input_quality")
    if isinstance(iq, dict):
        items += _as_str_list(iq.get("missing_information"))
    return items


def _extract_unknowns(out: dict):
    items = list(_as_str_list(out.get("unknowns")))
    iq = out.get("input_quality")
    if isinstance(iq, dict):
        items += _as_str_list(iq.get("unknowns"))
    return items


def _extract_flags(out: dict):
    flags = out.get("professional_review_flags")
    return [f for f in flags if isinstance(f, dict)] if isinstance(flags, list) else []


def _strip_required(node):
    """Recursively drop `required` so partial (script-stage) outputs validate on
    shape only. Returns a new structure; does not mutate the input."""
    if isinstance(node, dict):
        return {k: _strip_required(v) for k, v in node.items() if k != "required"}
    if isinstance(node, list):
        return [_strip_required(x) for x in node]
    return node
