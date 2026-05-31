# Skill-Authoring Instructions

> Lessons distilled from building the wealth-planning skill suite
> (`wealth-intake` → `portfolio-analysis` → `longevity-modeling`).
> Drop this in as a preamble/checklist for the next skill-authoring prompt.
> Each rule is tied to a concrete failure that occurred. The **Definition of Done**
> at the end is a hard gate before declaring a skill complete.

---

## 1. If the task is numerical, ship a script — never compute by hand

**What went wrong:** `longevity-modeling` and `portfolio-analysis` instructed the model
to do multi-year compounding and allocation math token-by-token. The longevity Monte
Carlo was *fabricated*: the by-hand run reported **76% success; the real engine returned
25%** — a 3× error stated with full confidence.

**Rules:**
- Any skill that compounds over time, aggregates across many rows, simulates, or computes
  percentiles MUST bundle a `scripts/<name>.py` engine and instruct: "run the script, do
  not compute by hand."
- Prefer **pure standard library** (no numpy/pandas) so it runs with zero setup. Pure-Python
  Monte Carlo at 10k×40yr is fine.
- JSON-in / JSON-out, runnable as `python scripts/x.py input.json` or via stdin. Validate
  required inputs and emit `{"error":..., "missing":[...]}` on bad input.
- Make stochastic runs reproducible (accept a `random_seed`).
- The script must **surface unknowns, not guess** (e.g. an account with no holdings →
  classified `unknown` and flagged, never silently allocated).

## 2. Pin every math convention to an exact formula

**What went wrong:** Withdrawal timing (begin- vs end-of-year) was unstated; the model's own
test violated the skill's stated step order, producing a ~$7k/yr divergence that compounded
into a different depletion age.

**Rules:**
- State the governing equation literally (e.g.
  `ending = (beginning + income − spending) × (1 + net_return)`) and label it
  "authoritative — do not deviate."
- Put the same convention in the script's docstring AND the SKILL body so prose and numbers
  can't drift.
- Define derived quantities once (`net_return = gross − fee − tax_drag`) rather than describing
  them in words.

## 3. Create every file the spec names — as a real file

**What went wrong:** `wealth-intake`'s source spec said "save the following as `schema.json`"
and "`sample_intake.json`," but both were folded into the SKILL body and never written to disk.

**Rules:**
- When a spec says "save X as a file," produce that file. Don't inline it.
- Don't document an artifact that doesn't exist (the original longevity skill advertised an
  "Optional Python Calculator Interface" with no script behind it). Either build it or delete
  the section.

## 4. Keep `SKILL.md` lean; push bulk to `references/`

**What went wrong:** Full output schemas, worked examples, and I/O blocks sat in the
always-loaded body (longevity 477 lines, portfolio ~340).

**Rules:**
- The body holds *instructions and decision rules*. Large JSON schemas, full worked examples,
  and calculator I/O contracts go in `references/*.md` (or `.json`), loaded on demand.
- Replace each moved block with a one-line pointer: "full schema in `references/schema.md` —
  load when assembling final JSON."
- Result of applying this: bodies dropped to 200 / 285 / 398 lines with no loss of capability.

## 5. Make pipeline handoffs explicit and verified

**What went wrong:** `longevity-modeling` expected `portfolio.total_value` /
`portfolio.allocation`, but neither upstream skill (`wealth-intake`, `portfolio-analysis`)
emitted that shape. The seams didn't connect.

**Rules:**
- If a skill consumes another's output, include an **input-adapter table** mapping the
  upstream field names to the ones this skill expects.
- Name the contract: the producer states "this JSON is the handoff consumed by X and Y; keep
  field names exactly." The consumer references the same schema file.
- Verify a real object flows end-to-end, not just that each skill works alone.

## 6. Frontmatter and structure basics

- `name` matches the directory; single `SKILL.md`; `description` lists concrete trigger phrases
  but stays under ~50 words (the longevity description was keyword-stuffed to ~90).
- Keep refusal/boundary language present for advice-adjacent domains (these skills must
  analyze, never recommend).

---

## Definition of Done (gate before claiming completion)

1. ☐ Every numerical claim is produced by a bundled script, **executed at least once** and
   shown to run.
2. ☐ Every file the spec names exists on disk and parses (`python -c "import json/ast"`).
3. ☐ No section describes a non-existent artifact.
4. ☐ `SKILL.md` contains rules, not bulk data; schemas/examples are in `references/`.
5. ☐ Math conventions are stated as exact formulas in both script and body.
6. ☐ Pipeline inputs/outputs have an explicit field mapping, verified end-to-end.
7. ☐ The engine surfaces missing/unknown data rather than guessing.

---

**The meta-lesson:** the most dangerous failure wasn't a crash — it was a *confident wrong
number* (76% vs 25%). For analytical skills, "looks plausible" is not verification. Make the
artifact compute, then run it.
