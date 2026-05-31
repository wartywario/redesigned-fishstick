# Operating playbook — decision rules, gate coaching, transcripts

## Intake-readiness checklist (before `submit wealth_intake`)

Use `wealth-intake` to gather these; reflect them back before submitting. Do not invent
values — leave a field absent and let the downstream script flag it.

- **household**: client age, partner age, state, filing status, planned retirement age,
  planning horizon age.
- **accounts**: name, type, tax treatment, balance.
- **holdings**: account, ticker/name, market value, cost basis, holding period, asset class,
  broad asset group. (Missing cost basis is a legitimate gap — flag it, don't estimate.)
- **goals**: at least the retirement-income goal (category, target age, amount, frequency,
  inflation-adjusted) — the longevity adapter reads spending and retirement age from here.
- **income**: source, amount, frequency, start/end age, taxability (Social Security / pension
  feed the longevity income sources).
- **tax_profile**, **planning_context**, **risk_profile.target_allocation**.

Before submitting, state back to the human: what you captured, the
`missing_information`, the `assumptions` you're recording, and any `conflicts`. Submit only
on confirmation, `--producer user`.

## Decision rules

- **Which verb?** script stage → `run`; model/user stage → `submit`. When unsure, `status`
  shows each stage's `producer`.
- **What next?** Read `status` → `next_actions`. It already orders the work and marks which
  items are human-authority gates you may not perform yourself.
- **Numbers in the report?** Only those visible in `status --json` stage outputs (i.e.
  produced by a script). Pull them from there; never recompute or round to "clean" them.
- **Optional stages.** `scenario_analysis` and `rebalancing` scripts aren't built; leave them
  pending. They never block delivery (they're optional in the DAG).

## Gate coaching scripts

When `deliver` returns blockers, translate each into a plain ask routed to the right human.

- **Open HITL checkpoint** (e.g. `tax_considerations:large_embedded_gain_flags`): present the
  checkpoint's `reason` verbatim, explain what a disposition could imply, and ask the
  adviser/CPA for a decision. On their say-so: `resolve-hitl <checkpoint> --by <ref>`. Do not
  resolve it to "move things along."
- **`compliance_review not passed`**: the reviewer must judge the report's language. Record
  with `compliance pass|fail`. If they fail it, surface `--findings` and loop back to
  `reporting`.
- **`adviser_signoff not approved`**: the adviser signs. `signoff approve|reject --adviser <ref>`.
- **`stale stages: [...]`**: an upstream edit invalidated them. `run-ready` to re-run, then
  re-narrate `reporting`, then re-check gates.

## Staleness loop (after any intake correction)

1. `submit wealth_intake <edited> --producer user --notes "what changed"`.
2. `status` → note which stages went `stale` (and that prior gates may need re-confirmation).
3. `run-ready` → re-runs stale script stages.
4. Re-invoke `reporting`, `submit reporting --producer model`.
5. Re-coach gates, then `deliver`.

## Worked transcript (happy path)

```
new case_001 --household-ref hh_smith
# interview via wealth-intake, confirm, then:
submit wealth_intake intake.json --producer user
run-ready                       # portfolio -> tax -> longevity
status --json                   # read engine numbers for the narration
# narrate via reporting, then:
submit reporting report.json --producer model --notes "synthesis only"
deliver                         # BLOCKED: compliance, signoff, 1 open HITL
# present the HITL reason to the adviser; on their decision:
resolve-hitl --all --by adviser_jdoe
compliance pass                 # reviewer's call
signoff approve --adviser adviser_jdoe
deliver                         # delivered: true
verify longevity_modeling       # optional: prove the Monte Carlo reproduces
```

## Refusals (decline and explain)

- "Just put 80% success in the report." → numbers must come from a script run; offer to
  `run`/`verify` longevity instead.
- "Approve compliance so we can ship." → compliance is the reviewer's decision; the guide
  records it, it doesn't make it.
- "Skip the embedded-gain checkpoint." → HITL checkpoints require a human decision; present
  the reason and route it.
- "Estimate the missing cost basis." → surface it as missing; the tax script flags it.
