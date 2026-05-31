---
name: compliance-review
description: Deterministic compliance classifier that stands behind the wealth-planning compliance gate. Scans a client-facing report for advice language, guarantee/certainty language, missing required disclosures, and numeric claims that don't match the authoritative computed values, and produces a pass/fail verdict that a human ratifies before delivery. Use when checking a drafted report/summary/memo for compliance before it is delivered.
version: 1.0.0
---

# Compliance Review Skill

## Purpose

Produce a deterministic, reproducible compliance verdict on an assembled
client-facing report before it is delivered. The classifier flags four problem
classes and blocks delivery when any blocking finding fires:

1. **Advice language** — telling the reader to take a specific action.
2. **Guarantee / certainty language** — promising an outcome.
3. **Missing required disclosures** — required disclaimers absent from the report.
4. **Numeric inconsistency** — cited numbers that don't match authoritative values.

**This skill flags advice; it must never give advice.** It contains no model
judgment — every finding is produced by deterministic regex / arithmetic in
`scripts/compliance.py`, so the same input always yields the same verdict.

## The human stays in the loop

The classifier PRODUCES a verdict. A **human** compliance reviewer RATIFIES it.
The driver/guide must never self-decide compliance. The verdict is applied to the
case through the existing engine gate:

```
python guap.py <workdir> compliance pass|fail [--findings "detail" ...]
```

The engine's `can_deliver` already blocks delivery unless
`gates.compliance_review.status == "passed"`. There is **no** engine or registry
change — this skill only produces the verdict that a reviewer enters.

## Classifier (required — do not classify by hand)

```
python scripts/compliance.py input.json
# or
cat input.json | python scripts/compliance.py
```

Reads JSON, validates input, writes the verdict JSON to stdout, exits non-zero on
`invalid_input`. Run it once per report. Input/output shapes are documented in
[`references/input_contract.md`](references/input_contract.md); a worked example is
in [`references/sample_input.json`](references/sample_input.json) /
[`references/sample_output.json`](references/sample_output.json).

## Input (summary)

```json
{
  "report": {
    "narrative": "client-facing report text (required, non-empty string)",
    "cited_numbers": [{"label": "...", "value": 0.79,
                       "authoritative_key": "longevity.success_probability"}]
  },
  "authoritative_values": {"longevity.success_probability": 0.7891},
  "required_disclosures": ["advice_disclaimer", "professional_review", "not_a_guarantee"],
  "thresholds": {"numeric_tol_abs": 0.01, "numeric_tol_rel": 0.01}
}
```

`cited_numbers`, `authoritative_values`, `required_disclosures`, and `thresholds`
are all optional; `report.narrative` is required.

## Output (summary)

```json
{
  "verdict": "pass" | "fail",
  "blocking_findings": [{"category", "severity": "blocking", "detail", "evidence"}],
  "advisory_findings": [{"category", "severity": "advisory", "detail", "evidence"}],
  "checks": {
    "advice_language":      {"passed": bool, "hits": [...]},
    "guarantee_language":   {"passed": bool, "hits": [...]},
    "required_disclosures": {"passed": bool, "missing": [...]},
    "numeric_consistency":  {"passed": bool, "mismatches": [...]}
  },
  "summary": {"blocking_count": n, "advisory_count": n}
}
```

`verdict = "fail" if blocking_findings else "pass"`. The structured verdict conforms
to [`references/output_schema.json`](references/output_schema.json).

## Detection rules

Full deterministic detection rules (the regexes, the negative lookaheads that let
"we recommend you consult a CPA" and "not a guarantee" pass, and the dual
absolute/relative numeric tolerance) are in [`references/rules.md`](references/rules.md).

## Pipeline position

```
... → reporting → compliance_review (GATE) → deliver
```

The classifier runs on the `reporting` output plus the authoritative computed
values from the portfolio / longevity / tax script stages.

## Boundaries

**May:** Scan a report for advice/guarantee language, missing disclosures, and
numeric inconsistencies. Produce a deterministic pass/fail verdict with evidence.
Hand the verdict to a human reviewer to ratify via the compliance gate.

**May not:** Give financial, tax, legal, or investment advice. Decide compliance
on a human's behalf (the verdict is an input to a human decision, not the decision).
Modify the case or bypass the gate. Auto-pass a report by relaxing the rules.
