#!/usr/bin/env python3
"""
Assertion-based unit tests for compliance.py.

Run:
    python scripts/tests/test_compliance.py

Writes a PASS/FAIL summary to scripts/tests/_test_report.txt and prints it.
(Shell stdout flushing was unreliable in this environment, so the summary is
also persisted to a file that can be read back.)
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # so `import compliance` finds scripts/compliance.py

import compliance  # noqa: E402

REPORT = HERE / "_test_report.txt"

# A reusable compliant narrative: all three required disclosures, no advice,
# no guarantee claims.
COMPLIANT = (
    "# Wealth Planning Summary\n"
    "This analysis is for educational purposes and is not tax, legal, or investment advice. "
    "Figures are estimates and are not a guarantee of future results; past performance does "
    "not guarantee future results. Please review with a qualified financial adviser or CPA "
    "before acting.\n"
    "Across 10,000 simulations the modeled success probability is about 79%, a probabilistic "
    "estimate rather than a promise."
)

_results = []


def check(name, cond):
    _results.append((name, bool(cond)))


def run_tests():
    # 1. clean compliant report -> pass, 0 blocking
    r = compliance.run({"report": {"narrative": COMPLIANT}})
    check("1 clean report verdict pass", r["verdict"] == "pass")
    check("1 clean report 0 blocking", r["summary"]["blocking_count"] == 0)

    # 2. advice language -> fail, advice_language hit
    narr2 = COMPLIANT + "\nYou should sell your bonds and buy tech stocks."
    r = compliance.run({"report": {"narrative": narr2}})
    check("2 advice verdict fail", r["verdict"] == "fail")
    check("2 advice category present",
          any(f["category"] == "advice_language" for f in r["blocking_findings"]))

    # 3. numbers but no disclaimers -> fail, missing required disclosures
    narr3 = ("Your total portfolio value is approximately $2,214,117 with a 63% equity "
             "allocation. The modeled success probability is 79%.")
    r = compliance.run({"report": {"narrative": narr3}})
    check("3 missing disclosures verdict fail", r["verdict"] == "fail")
    check("3 missing disclosures listed",
          set(r["checks"]["required_disclosures"]["missing"]) ==
          {"advice_disclaimer", "professional_review", "not_a_guarantee"})

    # 4a. guarantee language -> fail
    narr4 = COMPLIANT + "\nYour portfolio is guaranteed to last through age 95."
    r = compliance.run({"report": {"narrative": narr4}})
    check("4 guarantee verdict fail", r["verdict"] == "fail")
    check("4 guarantee category present",
          any(f["category"] == "guarantee_language" for f in r["blocking_findings"]))
    # 4b. "not a guarantee" / "does not guarantee" must NOT trip the guarantee check
    narr4b = (COMPLIANT + "\nThese figures do not guarantee any particular outcome.")
    r = compliance.run({"report": {"narrative": narr4b}})
    check("4 disclosure-style guarantee not flagged",
          r["checks"]["guarantee_language"]["passed"] is True)
    check("4 disclosure-style report passes", r["verdict"] == "pass")

    # 5. cited 0.95 vs authoritative 0.7891 -> fail, numeric_inconsistency
    cfg5 = {
        "report": {"narrative": COMPLIANT,
                   "cited_numbers": [{"label": "success probability", "value": 0.95,
                                      "authoritative_key": "longevity.success_probability"}]},
        "authoritative_values": {"longevity.success_probability": 0.7891},
    }
    r = compliance.run(cfg5)
    check("5 numeric mismatch verdict fail", r["verdict"] == "fail")
    check("5 numeric mismatch category present",
          any(f["category"] == "numeric_inconsistency" for f in r["blocking_findings"]))

    # 6. cited 0.79 vs authoritative 0.7891 -> pass (within tolerance)
    cfg6 = {
        "report": {"narrative": COMPLIANT,
                   "cited_numbers": [{"label": "success probability", "value": 0.79,
                                      "authoritative_key": "longevity.success_probability"}]},
        "authoritative_values": {"longevity.success_probability": 0.7891},
    }
    r = compliance.run(cfg6)
    check("6 numeric near-match verdict pass", r["verdict"] == "pass")
    check("6 numeric near-match no mismatch",
          r["checks"]["numeric_consistency"]["passed"] is True)

    # 6b. dollar values: $2.20M vs $2.214M ok; $5M vs $2.2M mismatch
    cfg6b = {
        "report": {"narrative": COMPLIANT,
                   "cited_numbers": [
                       {"label": "tpv", "value": 2200000,
                        "authoritative_key": "portfolio.total_portfolio_value"}]},
        "authoritative_values": {"portfolio.total_portfolio_value": 2214117.1},
    }
    check("6b near dollar passes",
          compliance.run(cfg6b)["verdict"] == "pass")
    cfg6c = dict(cfg6b)
    cfg6c["report"] = {"narrative": COMPLIANT,
                       "cited_numbers": [{"label": "tpv", "value": 5000000,
                                          "authoritative_key": "portfolio.total_portfolio_value"}]}
    check("6c far dollar fails",
          compliance.run(cfg6c)["verdict"] == "fail")

    # 7. missing report.narrative -> invalid_input
    r = compliance.run({"report": {}})
    check("7 missing narrative invalid_input", r.get("error") == "invalid_input")
    r = compliance.run({})
    check("7 missing report invalid_input", r.get("error") == "invalid_input")
    r = compliance.run([1, 2, 3])
    check("7 non-dict root invalid_input", r.get("error") == "invalid_input")

    # 8. "we recommend you consult a CPA" -> NOT advice_language (lookahead)
    narr8 = COMPLIANT + "\nWe recommend you consult a CPA before making changes."
    r = compliance.run({"report": {"narrative": narr8}})
    check("8 recommend-consult not advice",
          r["checks"]["advice_language"]["passed"] is True)
    check("8 recommend-consult report passes", r["verdict"] == "pass")


def main():
    run_tests()
    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    lines = [f"[{'PASS' if ok else 'FAIL'}] {name}" for name, ok in _results]
    lines.append("")
    lines.append(f"SUMMARY: {passed}/{total} assertions passed")
    lines.append("ALL PASSED" if passed == total else "SOME FAILED")
    text = "\n".join(lines) + "\n"
    REPORT.write_text(text, encoding="utf-8")
    print(text)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
