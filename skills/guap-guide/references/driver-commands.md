# Driver command reference — `scripts/guap.py`

The driver is a thin, deterministic wrapper around the `Orchestrator` class. It does no math
and decides no gate; it injects content and records human decisions. Every command takes the
case `<workdir>` as its first argument.

## Setup

Set `GUAP_ORCH_ROOT` to the directory containing `engine.py` / `registry.py` (the
orchestrator package). If unset, the driver tries `~/projects/LOCALSonly/orchestrator` and
`~/LOCALSonly/orchestrator`. The engine resolves the skills suite via `ORCH_SKILLS_ROOT`
(default `~/.claude/skills`).

```bash
export GUAP_ORCH_ROOT="/path/to/LOCALSonly/orchestrator"
```

## Commands

### `status [--json]`
Primary instrument. Human-readable by default; `--json` returns a structured object with:
- `stages[]`: `{stage, producer, status, runnable, optional, script_built}`
- `gates`: `compliance_review`, `adviser_signoff`, `open_hitl_checkpoints[]`
- `consolidated`: counts of missing/assumptions/conflicts/unknowns/flags
- `deliverable`, `blocking_reasons[]`
- `next_actions[]`: ordered guidance, separating guide-automatable steps from human gates

### `new <case_id> [--household-ref REF]`
Create a fresh case in `<workdir>` (`case.json` + content-addressable `cas/` store).

### `submit <stage> <file.json|-> --producer model|user|external [--notes "..."]`
Inject content for a **model/user** stage (`wealth_intake`, `reporting`). Refuses script
stages. Payload is a JSON file path or `-` for stdin.
- intake → `--producer user`
- report → `--producer model`

### `run <stage>`
Run a single **script** stage (engine invokes its calculator). Refuses model/user stages and
stages that aren't runnable.

### `run-ready`
Run every currently-runnable, **built** script stage in DAG order. Skips optional unbuilt
scripts (`scenario_analysis`, `rebalancing`) and stops on the first failure. Also re-runs
`stale` script stages, since the engine marks those runnable.

### `verify <stage>`
Replay a script stage on its archived input; prints recorded vs. replayed hash and `match`.

### `compliance pass|fail [--findings "a" "b"]`
Record the compliance reviewer's decision. **A human decision** — never the guide's.

### `signoff approve|reject --adviser REF [--notes "..."]`
Record the adviser's sign-off. **A human decision.**

### `resolve-hitl (<checkpoint> | --all) --by REF`
Mark open HITL checkpoint(s) resolved, attributing to the deciding human. **A human
decision** — present the checkpoint's reason first and get an explicit call.

### `deliver`
Attempt delivery. Returns `{delivered, blocking_reasons}`; changes nothing unless all gates
clear and nothing is stale.

### `validate`
Validate the whole case object against `planning_case.schema.json` (needs `jsonschema`).

## Exit behavior

Wrong-verb and not-runnable mistakes exit with a one-line explanation (e.g. submitting a
script stage, or running a model stage), so the guide can correct course without corrupting
the case.
