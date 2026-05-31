# Tax Considerations — Smoke Tests

Run all commands from the `tax-considerations/` directory.

## Smoke test (minimal input)

```bash
python scripts/tax_flags.py tests/smoke_input.json
```

Expected: valid JSON output with no Python exceptions and no `"error"` key.

## Full sample run

```bash
python scripts/tax_flags.py references/sample_input.json > /tmp/tax_flags_output.json
python -m json.tool /tmp/tax_flags_output.json > /dev/null && echo "sample output: valid JSON"
```

## JSON file validation

```bash
python -m json.tool references/output_schema.json > /dev/null && echo "output_schema.json: OK"
python -m json.tool references/sample_input.json  > /dev/null && echo "sample_input.json: OK"
python -m json.tool references/sample_output.json > /dev/null && echo "sample_output.json: OK"
```

## Stdin mode

```bash
cat tests/smoke_input.json | python scripts/tax_flags.py
```

## Error-handling test (missing required data)

```bash
echo '{"accounts": [], "holdings": []}' | python scripts/tax_flags.py
```

Expected: valid JSON with an `"error"` key, no stack trace.

## What to check in output

- `input_quality.known_taxable_basis_coverage` is a number between 0 and 1 (or null).
- `taxable_gain_loss_snapshot.net_taxable_embedded_gain_loss` matches manual calculation.
- Every flag text begins with "Potential consideration" or "Missing data" — never "You should".
- `professional_review_flags` contains items for every high-priority flag category triggered.
- `downstream_handoff` keys are present: `for_rebalancing`, `for_longevity_modeling`, `for_scenario_analysis`, `for_reporting`.
