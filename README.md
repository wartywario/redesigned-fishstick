# Wealth-Planning Skill Suite

A deterministic, advice-free wealth-planning pipeline for Claude Code: seven
model-invoked **skills** sitting on top of a pure-Python **orchestrator** that
sequences the stages, runs the calculators, enforces gates, and produces a fully
auditable planning case.

```
wealth-intake → portfolio-analysis → tax-considerations → longevity-modeling
                                                        → reporting → compliance-review (gate) → deliver
```

The `guap-guide` skill is the conversational front door that drives the
orchestrator for a human. All math comes from deterministic scripts; no LLM is
involved in sequencing, hashing, or gating. The suite analyzes, organizes, and
flags — it never gives tax, legal, or investment advice.

## What's in here

```
skills/             The 7 skills (the installable unit)
  wealth-intake/        data structuring (no script)
  portfolio-analysis/   scripts/portfolio.py
  tax-considerations/   scripts/tax_flags.py
  longevity-modeling/   scripts/longevity.py
  reporting/            synthesis layer (no script)
  compliance-review/    scripts/compliance.py  (the compliance gate's classifier)
  guap-guide/           scripts/guap.py        (the driver/front door)
orchestrator/       engine.py, registry.py, __main__.py, demo.py
tests/              run_suite.py, scenarios.py  (21-scenario end-to-end suite)
planning_case.schema.json / .example.json
install.ps1 / install.sh
```

## Requirements

- **Python 3.8+** (developed on 3.14). The calculators are pure standard library.
- `jsonschema` is **optional** — used only for schema validation; the engine
  degrades gracefully without it. Install with `pip install jsonschema` if you
  want case/output validation.
- Claude Code (to actually invoke the skills).

## Install on a new machine

```bash
git clone <this-repo> wealth-suite
cd wealth-suite

# macOS / Linux
./install.sh --set-env --verify

# Windows (PowerShell)
./install.ps1 -SetEnv -Verify
```

The installer **copies** the seven skills into `~/.claude/skills/` (re-run it to
update after `git pull`). It does not touch the orchestrator — that stays in the
cloned repo and is located at runtime via `GUAP_ORCH_ROOT`.

### The one wiring point: `GUAP_ORCH_ROOT`

`guap.py` and the test suite locate the orchestrator (engine.py / registry.py) via
the `GUAP_ORCH_ROOT` environment variable. It falls back to `~/projects/LOCALSonly/orchestrator`
and `~/LOCALSonly/orchestrator`, so:

- **Clone to `~/projects/LOCALSonly`** → zero config, it just works.
- **Clone anywhere else** → run the installer with `--set-env` / `-SetEnv` (it
  persists `GUAP_ORCH_ROOT` pointing at this repo's `orchestrator/`), or export it
  yourself:
  ```bash
  export GUAP_ORCH_ROOT="/path/to/wealth-suite/orchestrator"   # bash/zsh
  $env:GUAP_ORCH_ROOT = "C:\path\to\wealth-suite\orchestrator"  # PowerShell
  ```

`registry.py` finds the installed skills at `~/.claude/skills` by default; override
with `ORCH_SKILLS_ROOT` only if you installed them elsewhere.

## Verify the install

```bash
# compliance classifier unit tests (21 assertions)
python ~/.claude/skills/compliance-review/scripts/tests/test_compliance.py

# full end-to-end suite (expects 11 DELIVER / 10 SAFE / 0 LEAK, 21/21 matched)
GUAP_ORCH_ROOT=$PWD/orchestrator python tests/run_suite.py
```

## Updating

```bash
git pull
./install.sh        # or ./install.ps1  — re-copies the latest skills
```

## Dev note (this machine)

On the machine where the skills are authored, the working copies live in
`~/.claude/skills/`. Treat `skills/` in this repo as the shipping source: copy
edits back into `skills/` before committing (or develop against `skills/` and run
`install.ps1`/`install.sh` to push them live). The two diverge silently otherwise.
