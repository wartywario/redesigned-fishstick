# Engine contract — what guap-guide is driving

The orchestrator (`engine.py` + `registry.py`) is **deterministic**. No LLM is involved in
sequencing, hashing, gating, staleness, or consolidation. The LLM (this skill) only produces
content for two stages and narrates. Everything below is enforced by the engine; the guide
must not duplicate or override it.

## The stage DAG

| Stage | Producer | Depends on | Notes |
|---|---|---|---|
| `wealth_intake` | model/user | — | the household's structured facts (submitted) |
| `portfolio_analysis` | **script** | wealth_intake | `portfolio-analysis/scripts/portfolio.py` |
| `tax_considerations` | **script** | wealth_intake, portfolio_analysis | `tax-considerations/scripts/tax_flags.py` |
| `longevity_modeling` | **script** | wealth_intake, portfolio_analysis, tax_considerations | `longevity-modeling/scripts/longevity.py`; seeded Monte Carlo (`random_seed`) |
| `scenario_analysis` | script *(not built)* | longevity_modeling | optional; stays pending |
| `rebalancing` | script *(not built)* | portfolio_analysis, tax_considerations | optional; stays pending |
| `reporting` | model | wealth_intake, portfolio_analysis, longevity_modeling, tax_considerations | LLM synthesis, no math (submitted) |
| `compliance_review` | model/gate | reporting | modelled as a gate |

`script` stages → **`run`** (engine invokes the calculator). `model`/`user` stages →
**`submit`** (the guide injects content). The driver enforces this and refuses the wrong verb.

## Producers and their meaning

- **`script`** — the engine runs a bundled calculator on a deterministically-built input
  (the `build_input` adapters in `registry.py` are the seams). Output is hashed and stored.
- **`user`** — facts the human supplied (intake). Submitted with `--producer user`.
- **`model`** — LLM-produced narration (reporting). Submitted with `--producer model`.
  Must carry no computed numbers of its own; it references engine outputs via provenance.

## Provenance (every stage carries it)

`output_hash`, `input_hash`, `script_name`/`script_version`, `rng_seed`, and
`consumed_from` (the exact upstream output hashes seen at read time). This is what makes a
report's numbers traceable and what makes staleness detectable.

## Staleness

Editing an upstream stage changes its `output_hash`. Any downstream stage whose
`consumed_from` no longer matches is automatically marked `stale` and **blocks delivery**.
The guide does not compute this — it reads it from `status` and re-runs what's stale.

## Replay verification

`verify <stage>` re-runs a script stage on its archived input and confirms the output hash
matches byte-for-byte. The seeded Monte Carlo makes even the stochastic stage reproducible.
Use it to prove a number to a skeptical human.

## Gates (all human authority — the guide records, never decides)

- **`compliance_review`** — must be `passed`. Set via `compliance pass|fail`.
- **`adviser_signoff`** — must be `approved`. Set via `signoff approve|reject --adviser REF`.
- **HITL checkpoints** — auto-raised when a consolidated `professional_review_flag` has
  severity `high_priority_review` (key = `<stage>:<category>`). Must be resolved via
  `resolve-hitl ... --by REF`. The demo's large-embedded-gain flag is the canonical example.

`deliver` succeeds only when: compliance passed, signoff approved, **no** open HITL, and
**no** stale stages. Otherwise it returns `blocking_reasons` and changes nothing.

## Consolidation

After every stage change the engine rolls up `missing_information`, `assumptions`,
`conflicts_or_uncertainties`, `unknowns`, and `professional_review_flags` across completed
stages into `case["consolidated"]`, tagged by source stage. The guide surfaces these to the
human; it does not edit them.

## What the guide must never do

- Compute or adjust any planning number.
- Put a number into `wealth_intake` or `reporting` that didn't come from a script.
- Set `compliance`, `signoff`, or `resolve-hitl` on its own initiative.
- Run a stage that isn't runnable, or deliver with stale/blocked state.
