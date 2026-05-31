#!/usr/bin/env python3
"""
CLI for the wealth-planning orchestrator.

    python -m orchestrator <workdir> new <case_id>
    python -m orchestrator <workdir> status
    python -m orchestrator <workdir> run <stage>
    python -m orchestrator <workdir> verify <stage>
    python -m orchestrator <workdir> validate
    python -m orchestrator <workdir> deliver

`submit` (model/user stages) is intended to be driven from code; see demo.py.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
from engine import Orchestrator, DAG


def _status(orc: Orchestrator):
    case = orc.load()
    print(f"case {case['case_id']}  status={case['status']}")
    runnable = set(orc.runnable(case))
    for e in DAG:
        s = e["stage"]
        env = case["stages"].get(s)
        st = env["status"] if env else "—"
        mark = "RUNNABLE" if s in runnable else ""
        opt = " (optional)" if e.get("optional") else ""
        print(f"  {s:<20} {st:<10} {mark}{opt}")
    g = case["gates"]
    print(f"  gates: compliance={g['compliance_review']['status']} "
          f"signoff={g['adviser_signoff']['status']} "
          f"open_hitl={sum(1 for c in g['hitl_checkpoints'] if c['status']=='open')}")
    ok, reasons = orc.can_deliver(case)
    print(f"  deliverable: {ok}  {reasons if reasons else ''}")


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    workdir, cmd, *rest = sys.argv[1:]
    orc = Orchestrator(Path(workdir))

    if cmd == "new":
        orc.new_case(rest[0])
        print(f"created case {rest[0]} in {workdir}")
    elif cmd == "status":
        _status(orc)
    elif cmd == "run":
        env = orc.run_stage(orc.load(), rest[0])
        print(f"{rest[0]}: {env['status']}  output_hash={env['provenance']['output_hash']}")
    elif cmd == "verify":
        print(json.dumps(orc.verify(orc.load(), rest[0]), indent=2))
    elif cmd == "validate":
        print(orc.validate_case(orc.load()))
    elif cmd == "deliver":
        print(json.dumps(orc.deliver(orc.load()), indent=2))
    else:
        print(f"unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
