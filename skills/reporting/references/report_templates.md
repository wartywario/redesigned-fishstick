# Reporting — Output Templates

Pick the structure that matches the request. Omit sections whose upstream inputs
are unavailable (mark them, don't fabricate). Do not reference a section, table, or
appendix you did not produce.

## Full report

```markdown
# Wealth Planning Report

## 1. Executive Summary

## 2. Scope and Important Limitations

## 3. Household Profile and Goals

## 4. Current Portfolio Overview

## 5. Portfolio Longevity and Cash-Flow Outlook

## 6. Scenario Comparison

## 7. Tax Considerations

## 8. Rebalancing Observations

## 9. Key Risks and Sensitivities

## 10. Missing Information and Data Quality Issues

## 11. Professional Review Items

## 12. Suggested Next Analysis Steps

## Appendix A: Assumptions

## Appendix B: Source Handoff Map
```

## Short user-facing summary

```markdown
## Summary

## What Looks Strong

## What Needs Review

## Biggest Unknowns

## Next Inputs Needed
```

## Adviser-review memo

```markdown
# Adviser Review Memo

## Client Objective

## Data Received

## Model Outputs Reviewed

## Planning Issues Identified

## Tax Review Items

## Rebalancing Review Items

## Questions for Client

## Questions for CPA / Attorney

## Appendix: Upstream Output References
```

## Executive Summary contents

Concise; include when available:
1. The household's primary goal.
2. The current portfolio position.
3. The modeled retirement/longevity result.
4. The most important tax or rebalancing flags.
5. The top two or three risks or missing inputs.
6. A clear statement that the analysis depends on assumptions and requires
   professional review before implementation.

Do not overload with tables unless a technical report is requested.

## Scenario Comparison table

Use when scenario outputs are available (from `scenario-analysis` or
`longevity_modeling.scenario_results`). Compact table:

| Scenario | Key Change | Result | Main Risk | Notes |
|---|---|---|---|---|

Do not compute differences between scenarios unless those differences already exist
in upstream output. Directional comparisons may be described qualitatively when
clearly supported, e.g. "the delayed-retirement scenario appears stronger than the
base case because the upstream output shows a higher success metric and later
depletion age."

## Final-response wrapper (when used live in conversation)

After the report or summary, always append:
1. **Data Used** — which upstream outputs were available.
2. **Not Included / Missing** — absent sections, if any.
3. A one-line caveat that the output is analytical and should be reviewed before action.
