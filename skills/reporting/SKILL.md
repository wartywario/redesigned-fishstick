---
name: reporting
description: Assemble wealth-planning outputs into clear reports, summaries, review memos, assumptions lists, scenario comparisons, and client-ready deliverables without performing new calculations.
version: 1.0.0
---

# Reporting Skill

## Purpose

Synthesize validated outputs from the wealth-planning skill suite into clear,
auditable, appropriately caveated reports.

This is a reporting and synthesis layer only. **It bundles no calculation script and
performs no new math.** It does not run portfolio calculations, longevity
projections, tax calculations, or trade recommendations. Every number must come from
an upstream skill output, an upstream script result, or a clearly labeled
user-provided fact. If a number is not present in an upstream output, do not invent
or estimate it — request the missing upstream output or mark the item unavailable.

## When to Use This Skill

When the user asks for: a wealth-planning report, retirement readiness summary,
portfolio review summary, tax-aware planning summary, scenario comparison report,
client-facing financial planning memo, adviser review packet, executive summary of
prior-skill analysis, or a final deliverable combining intake, portfolio, longevity,
tax, and rebalancing outputs.

## Responsibilities

1. Combine upstream outputs into a coherent report.
2. Preserve the distinction between facts, assumptions, calculations, flags, and open questions.
3. Source every numerical claim to an upstream output (see below).
4. Highlight missing data, conflicts, and uncertainty.
5. Translate technical findings into plain language.
6. Produce a consistent, review-ready format.
7. Apply advice-adjacent boundaries and professional-review caveats.
8. Avoid recommendations not supported by prior analysis.

## Non-Responsibilities

Do not: run portfolio allocation math, retirement projections, Monte Carlo, or tax
estimates by hand; recommend specific securities; tell the user to execute trades;
present tax strategies as personalized advice; guarantee outcomes or longevity; hide
assumptions or missing information; convert incomplete data into confident
conclusions. If a calculation is needed, the appropriate upstream skill or script
must produce it first.

## Inputs and Pipeline Handoff

The skill works with partial inputs but must clearly label missing upstream
components. The **authoritative mapping of each report section to the real field
names each upstream skill emits** is in
[`references/field_mapping.md`](references/field_mapping.md) — consult it before
writing, and read upstream objects using those exact paths.

Built upstream skills: `wealth-intake`, `portfolio-analysis`, `longevity-modeling`,
`tax-considerations`. The `rebalancing`, `scenario-analysis`, and `compliance-review`
skills are referenced by the report structure but are not part of the current suite;
when absent, mark their sections "not reviewed" rather than treating it as an error.

When an upstream object uses a field name different from the mapping, record the
actual name and the mapped path in **Appendix B: Source Handoff Map**. Never silently
rename or recompute.

## Reporting Principles

1. **Source every number.** Each numerical claim must trace to a validated upstream
   skill output, an upstream script result, a user-provided fact, or a clearly
   labeled assumption. Indicate the source in plain language when helpful
   ("Based on the portfolio-analysis output, the current allocation is 64% equity…").
   Do not create new numerical results in this skill.
2. **Separate facts, assumptions, and interpretation.** Use distinct labels for known
   facts, user-provided assumptions, model assumptions, calculated outputs,
   interpretation, missing data, and professional-review flags.
3. **Lead with decision-relevant insight.** Do not dump JSON. Lead with the most
   useful planning implications while staying within analytical boundaries.
4. **Preserve uncertainty.** When confidence is limited, say so: "Based on the
   available data…", "This section is limited because…", "The result may change
   materially if…", "This requires professional review before action."
5. **Actionable without becoming advice.** Frame actionable output as next steps,
   review items, or questions ("Confirm whether retirement spending is before- or
   after-tax", "Review Roth conversion windows with a CPA").

## Report Structures

Three templates — full report, short user-facing summary, and adviser-review memo —
plus the Executive Summary contents, Scenario Comparison table, and final-response
wrapper are in [`references/report_templates.md`](references/report_templates.md).
Choose the structure matching the request and omit sections whose inputs are absent.

## Language Boundaries

**Tax** — allowed: "potential tax consideration", "CPA-review item", "may be worth
evaluating", "could materially affect the result", "requires additional tax data".
Avoid: "you should convert", "you should harvest losses", "this will reduce taxes",
"this is the best tax strategy", "this is tax advice".

**Rebalancing** — allowed: "the rebalancing output flags drift in…", "the
cash-flow-first approach may reduce taxable trading", "taxable trades should be
reviewed before implementation", "the proposed action list is for adviser review,
not execution". Avoid: "buy"/"sell" as final instructions, "execute these trades",
"optimal trade", "guaranteed improvement".

**General** — avoid: "you should sell X", "this guarantees retirement success",
"convert $100,000 to Roth this year", "this is the optimal allocation".

## Data Quality Review (before finalizing)

- Are all numerical results traceable to an upstream source?
- Are user-provided assumptions clearly labeled?
- Are missing sections identified instead of guessed?
- Are tax-sensitive items flagged for professional review?
- Are trade-sensitive items framed as review items, not instructions?
- Are portfolio, longevity, tax, and rebalancing results mutually consistent?
- Are conflicts or stale assumptions listed?
- Is the report clear about scope and limitations?

## Professional Review Items

Always include a consolidated professional-review section when any upstream skill
flags: taxable trades with material gains, Roth conversions, RMD planning, charitable
giving strategies, estate planning, trusts, annuities, pensions, concentrated
employer stock, equity compensation, business ownership, real estate transactions,
cross-border tax issues, legal events (divorce, inheritance), or any specific
transaction requiring adviser, CPA, or attorney review. Source these from each
upstream skill's `professional_review_flags`.

## Boundaries

**May:** summarize findings; organize planning outputs; compare scenarios already
produced upstream; identify missing information; highlight review items; prepare
client-facing or adviser-facing language.

**May not:** produce new investment or tax recommendations; perform by-hand
calculations; invent results for missing analyses; guarantee outcomes; replace a
licensed financial adviser, CPA, or attorney.

## Definition of Done

1. Every numerical claim is sourced to user input, an upstream output, or a validated
   upstream script result.
2. Missing upstream data is listed rather than guessed.
3. Assumptions are separated from facts.
4. Professional-review flags are consolidated.
5. Advice-adjacent language has been softened into analytical/review-oriented language.
6. The report includes scope and limitations.
7. No non-existent artifact, file, script, table, or appendix is referenced.
