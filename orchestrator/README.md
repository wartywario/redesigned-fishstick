# Wealth-Planning Orchestrator (scaffold)

Deterministic orchestrator that drives the wealth-planning skill suite over a
`planning_case` object (`../planning_case.schema.json`). **No LLM is involved in
sequencing, hashing, or gating** — those are deterministic. The LLM's role
(parsing intake, narrating reports) happens outside and is injected via
`submit_stage`.

## Files

| File | Role |
|---|---|
| `engine.py` | Engine: case lifecycle, DAG scheduling, script invocation, provenance, content-addressable store, staleness, consolidation, gates, replay verification |
| `registry.py` | Stage registry + deterministic `build_input` adapters (the pipeline seams, using the real upstream field names) |
| `__main__.py` | CLI |
| `demo.py` | End-to-end run against the real calculator scripts |

## What it guarantees

- **Math only from scripts.** `script` stages invoke `portfolio.py` / `tax_flags.py`
  / `longevity.py`. `model`/`user` stages are injected via `submit_stage` and may
  carry no computed numbers.
- **Provenance on every stage** — input/output hashes, script version, `rng_seed`,
  and `consumed_from` (the upstream hashes seen at read time).
- **Byte-exact replay** — `verify(stage)` re-runs a script on its archived input
  and confirms the output hash matches. Seeded Monte Carlo makes even the
  stochastic stage reproducible.
- **Staleness** — editing an upstream stage changes its output hash; every
  downstream stage whose `consumed_from` no longer matches is marked `stale` and
  blocks delivery.
- **Gates** — delivery requires `compliance_review == passed`,
  `adviser_signoff == approved`, and no open HITL checkpoints. High-priority review
  flags auto-raise a checkpoint.

## Run

```bash
# end-to-end demo (writes ./_demo_run/)
python demo.py

# or drive a case manually
python -m orchestrator ./mycase new case_001
python -m orchestrator ./mycase status
python -m orchestrator ./mycase run portfolio_analysis   # after intake submitted
python -m orchestrator ./mycase verify longevity_modeling
python -m orchestrator ./mycase deliver
```

Point at a different skills root with `ORCH_SKILLS_ROOT` (defaults to
`~/.claude/skills`).

## Scope / what's stubbed

- `wealth_intake`, `reporting`, `compliance_review` are `model`/gate stages —
  injected, not auto-run. In production: intake = LLM parse, reporting = LLM
  synthesis, compliance = deterministic language classifier.
- `scenario_analysis` and `rebalancing` are registered but their scripts are not
  built yet; they stay `pending` and are `optional` in the DAG.
- Validation of a script stage's output is **shape-only** (`required` stripped),
  because script output is a partial artifact; completeness is a final-response
  gate, not a script-stage check.
