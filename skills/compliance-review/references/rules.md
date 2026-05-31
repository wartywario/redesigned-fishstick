# Compliance Review — Detection Rules

All detection is deterministic, case-insensitive (`re.IGNORECASE`), and implemented
in `scripts/compliance.py`. This document is the human-readable specification; the
script is authoritative. Do not hand-classify a report — run the script.

A finding is **blocking** (forces `verdict = "fail"`) or **advisory** (recorded but
does not affect the verdict).

## 1. Required disclosures

Missing a **required** disclosure → BLOCKING (`category: missing_disclosure`).
Missing an **advisory** disclosure (`past_performance`) → ADVISORY only.

A disclosure is PRESENT when its pattern matches the narrative:

| Key | Severity when missing | Pattern (intent) |
|---|---|---|
| `advice_disclaimer` | blocking | `\bnot\b[^.]{0,30}\b(tax\|legal\|investment\|financial)\b[^.]{0,15}\badvice\b` — "not tax, legal, or investment advice", "does not constitute investment advice" |
| `professional_review` | blocking | `\b(consult\|review\|confirm\|discuss\|speak\|work)\b[^.]{0,40}\b(adviser\|advisor\|cpa\|attorney\|professional\|planner)\b` |
| `not_a_guarantee` | blocking | `\bnot\s+(?:a\s+)?guarantee\|are\s+not\s+guaranteed\|\bno\s+guarantee` |
| `past_performance` | advisory | `past performance[^.]{0,60}(?:not\|no)\b[^.]{0,30}(?:guarantee\|indicat)` |

Default required set = `["advice_disclaimer", "professional_review", "not_a_guarantee"]`,
overridable via the `required_disclosures` input. An unknown disclosure key (no
detector) is treated as missing.

## 2. Advice language

Any hit → BLOCKING (`category: advice_language`). `ACTION` =
`buy|sell|purchase|liquidate|reallocat*|rebalanc*|convert*|invest*|allocat*|move|shift|withdraw*|divest*|trade|swap|exchange|put`.

- **Imperative:** `\byou\s+(should|must|need to|ought to|have to)\s+(\w+\s+){0,3}?` + ACTION
- **First-person reco:** `\b(we|i)\s+(recommend|advise|suggest|urge)\b` with a negative
  lookahead so `we recommend you consult / review / confirm / discuss / speak / seek / that …`
  is NOT flagged (that is a referral to a professional, not advice).
- **Possessive:** `\b(my|our)\s+(recommendation|advice)\b`
- **Best-choice:** `\bthe\s+best\s+(investment|option|choice|strategy|fund|stock|allocation)\b`

## 3. Guarantee / certainty

Any hit → BLOCKING (`category: guarantee_language`).

- `\b(risk[\s-]?free|riskless|no\s+risk|zero\s+risk|can'?t\s+lose|cannot\s+lose)\b`
- `\b(will|would)\s+(never\s+run\s+out|last\s+forever|always\s+last|definitely|certainly)\b`
- `\b(your\s+portfolio|your\s+money|the\s+plan|you)\s+will\s+(succeed|last|be\s+fine|have\s+enough|never\s+run\s+out)\b`
- **Bare `guarantee\w*`:** scan every occurrence; SKIP a match if the preceding ~16
  characters contain `not `, `no `, `n't`, `without `, or `never ` (those are
  disclosures, not claims). Remaining matches are hits. This lets "not a guarantee"
  and "does not guarantee" pass while catching "guaranteed to last".

## 4. Numeric consistency

Mismatch → BLOCKING (`category: numeric_inconsistency`).

For each `cited_numbers[i]` whose `authoritative_key` is in `authoritative_values`,
with both values finite numbers:

```
diff = abs(cited - authoritative)
mismatch  iff  diff > numeric_tol_abs  AND  diff > numeric_tol_rel * abs(authoritative)
```

Defaults `numeric_tol_abs = 0.01`, `numeric_tol_rel = 0.01`. The dual absolute/relative
test works for both probabilities and dollars:
- 0.79 vs 0.7891 → ok; 0.95 vs 0.7891 → mismatch
- $2.20M vs $2.214M → ok; $5M vs $2.2M → mismatch

Cited numbers with no matching authoritative key, or non-numeric values, are skipped
(nothing to verify against).

## Validation

- Root must be a JSON object; otherwise `{"error":"invalid_input", "details":[...]}`, exit 1.
- `report.narrative` must be a non-empty string; otherwise `invalid_input`, exit 1.

## Verdict

```
verdict = "fail" if blocking_findings else "pass"
```
