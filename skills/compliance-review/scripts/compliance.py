#!/usr/bin/env python3
"""
Deterministic compliance classifier for the compliance-review skill.
Pure Python 3.8+ standard library. No external dependencies.
Reads JSON (file path as argv[1], or stdin). Writes JSON to stdout.

WHAT THIS DOES
This is the deterministic classifier that stands behind the engine's compliance
GATE. It scans a client-facing report narrative for four problem classes and
produces a pass/fail verdict. A HUMAN (or, in the test harness, a simulated
compliance officer) ratifies that verdict via `guap.py compliance pass|fail`.

It flags:
  1. advice language        — telling the reader to take a specific action
  2. guarantee / certainty  — promising an outcome
  3. missing disclosures    — required disclaimers absent from the narrative
  4. numeric inconsistency  — cited numbers that don't match authoritative values

Any BLOCKING finding -> verdict "fail" (the gate must block delivery).

This skill FLAGS advice; it must never GIVE advice. All detection is deterministic
regex / arithmetic — no model judgment, so the verdict is reproducible.
"""

import json
import re
import sys

# ── defaults ─────────────────────────────────────────────────────────────────

DEFAULT_REQUIRED_DISCLOSURES = ["advice_disclaimer", "professional_review", "not_a_guarantee"]

DEFAULT_THRESHOLDS = {
    "numeric_tol_abs": 0.01,
    "numeric_tol_rel": 0.01,
}

# ── disclosure detectors ─────────────────────────────────────────────────────
# Each maps a disclosure key to a compiled, case-insensitive pattern that, when
# found in the narrative, proves the disclosure is PRESENT.

_DISCLOSURE_PATTERNS = {
    "advice_disclaimer": re.compile(
        r"\bnot\b[^.]{0,30}\b(?:tax|legal|investment|financial)\b[^.]{0,15}\badvice\b",
        re.IGNORECASE,
    ),
    "professional_review": re.compile(
        r"\b(?:consult|review|confirm|discuss|speak|work)\b[^.]{0,40}"
        r"\b(?:adviser|advisor|cpa|attorney|professional|planner)\b",
        re.IGNORECASE,
    ),
    "not_a_guarantee": re.compile(
        r"\bnot\s+(?:a\s+)?guarantee|are\s+not\s+guaranteed|\bno\s+guarantee",
        re.IGNORECASE,
    ),
    "past_performance": re.compile(
        r"past performance[^.]{0,60}(?:not|no)\b[^.]{0,30}(?:guarantee|indicat)",
        re.IGNORECASE,
    ),
}

# Disclosures that are advisory-only when missing (never blocking).
_ADVISORY_DISCLOSURES = {"past_performance"}

# ── advice-language detectors ────────────────────────────────────────────────

_ACTION = (
    r"(?:buy|sell|purchase|liquidate|reallocat\w*|rebalanc\w*|convert\w*|invest\w*|"
    r"allocat\w*|move|shift|withdraw\w*|divest\w*|trade|swap|exchange|put)"
)

_ADVICE_PATTERNS = [
    # imperative "you should <action>"
    re.compile(r"\byou\s+(?:should|must|need to|ought to|have to)\s+(?:\w+\s+){0,3}?" + _ACTION,
               re.IGNORECASE),
    # first-person recommendation, but NOT "we recommend you consult/seek/..." (a disclosure)
    re.compile(r"\b(?:we|i)\s+(?:recommend|advise|suggest|urge)\b"
               r"(?!\s+(?:you\s+)?(?:consult|review|confirm|discuss|speak|seek|that))",
               re.IGNORECASE),
    # possessive recommendation/advice
    re.compile(r"\b(?:my|our)\s+(?:recommendation|advice)\b", re.IGNORECASE),
    # best-choice framing
    re.compile(r"\bthe\s+best\s+(?:investment|option|choice|strategy|fund|stock|allocation)\b",
               re.IGNORECASE),
]

# ── guarantee / certainty detectors ──────────────────────────────────────────

_GUARANTEE_PATTERNS = [
    re.compile(r"\b(?:risk[\s-]?free|riskless|no\s+risk|zero\s+risk|can'?t\s+lose|cannot\s+lose)\b",
               re.IGNORECASE),
    re.compile(r"\b(?:will|would)\s+(?:never\s+run\s+out|last\s+forever|always\s+last|"
               r"definitely|certainly)\b", re.IGNORECASE),
    re.compile(r"\b(?:your\s+portfolio|your\s+money|the\s+plan|you)\s+will\s+"
               r"(?:succeed|last|be\s+fine|have\s+enough|never\s+run\s+out)\b", re.IGNORECASE),
]

# Bare "guarantee" scan: a match is a CLAIM unless preceded by a negator nearby.
_GUARANTEE_WORD = re.compile(r"guarantee\w*", re.IGNORECASE)
_GUARANTEE_NEGATORS = ("not ", "no ", "n't", "without ", "never ")


# ── helpers ──────────────────────────────────────────────────────────────────

def _snippet(text, start, end, pad=40):
    """Return a trimmed evidence snippet around a match span."""
    a = max(0, start - pad)
    b = min(len(text), end + pad)
    s = text[a:b].replace("\n", " ").strip()
    return ("…" if a > 0 else "") + s + ("…" if b < len(text) else "")


def _num(x):
    """Return x as a float if it is a real finite number, else None."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    v = float(x)
    if v != v or v in (float("inf"), float("-inf")):
        return None
    return v


# ── individual checks ────────────────────────────────────────────────────────

def check_advice_language(narrative):
    hits = []
    for pat in _ADVICE_PATTERNS:
        for m in pat.finditer(narrative):
            hits.append({"match": m.group(0).strip(),
                         "evidence": _snippet(narrative, m.start(), m.end())})
    return {"passed": not hits, "hits": hits}


def check_guarantee_language(narrative):
    hits = []
    for pat in _GUARANTEE_PATTERNS:
        for m in pat.finditer(narrative):
            hits.append({"match": m.group(0).strip(),
                         "evidence": _snippet(narrative, m.start(), m.end())})
    # bare "guarantee" word: a claim unless negated nearby (a disclosure)
    for m in _GUARANTEE_WORD.finditer(narrative):
        preceding = narrative[max(0, m.start() - 16):m.start()].lower()
        if any(neg in preceding for neg in _GUARANTEE_NEGATORS):
            continue
        hits.append({"match": m.group(0).strip(),
                     "evidence": _snippet(narrative, m.start(), m.end())})
    return {"passed": not hits, "hits": hits}


def check_required_disclosures(narrative, required):
    missing = []
    for key in required:
        pat = _DISCLOSURE_PATTERNS.get(key)
        # An unknown disclosure key cannot be auto-verified -> treat as missing.
        if pat is None or not pat.search(narrative):
            missing.append(key)
    return {"passed": not missing, "missing": missing}


def check_numeric_consistency(cited_numbers, authoritative_values, thresholds):
    tol_abs = _num(thresholds.get("numeric_tol_abs"))
    tol_rel = _num(thresholds.get("numeric_tol_rel"))
    if tol_abs is None:
        tol_abs = DEFAULT_THRESHOLDS["numeric_tol_abs"]
    if tol_rel is None:
        tol_rel = DEFAULT_THRESHOLDS["numeric_tol_rel"]

    mismatches = []
    for c in cited_numbers:
        if not isinstance(c, dict):
            continue
        key = c.get("authoritative_key")
        if key is None or key not in authoritative_values:
            continue
        cited = _num(c.get("value"))
        auth = _num(authoritative_values.get(key))
        if cited is None or auth is None:
            continue
        diff = abs(cited - auth)
        if diff > tol_abs and diff > tol_rel * abs(auth):
            mismatches.append({
                "label": c.get("label"),
                "authoritative_key": key,
                "cited_value": cited,
                "authoritative_value": auth,
                "difference": round(diff, 6),
            })
    return {"passed": not mismatches, "mismatches": mismatches}


# ── validation ───────────────────────────────────────────────────────────────

def validate(cfg):
    details = []
    if not isinstance(cfg, dict):
        return ["Root must be a JSON object"]
    report = cfg.get("report")
    if not isinstance(report, dict):
        details.append("report must be an object")
        return details
    narrative = report.get("narrative")
    if not isinstance(narrative, str) or not narrative.strip():
        details.append("report.narrative must be a non-empty string")
    return details


# ── main ─────────────────────────────────────────────────────────────────────

def run(cfg):
    errors = validate(cfg)
    if errors:
        return {"error": "invalid_input", "details": errors}

    report = cfg["report"]
    narrative = report["narrative"]
    cited_numbers = report.get("cited_numbers") or []

    authoritative_values = cfg.get("authoritative_values") or {}
    required = cfg.get("required_disclosures")
    if not isinstance(required, list):
        required = list(DEFAULT_REQUIRED_DISCLOSURES)
    thresholds = cfg.get("thresholds") or {}

    # advisory disclosure check (past_performance), evaluated separately so a
    # missing advisory disclosure never blocks.
    advisory_required = [d for d in _ADVISORY_DISCLOSURES]

    advice = check_advice_language(narrative)
    guarantee = check_guarantee_language(narrative)
    disclosures = check_required_disclosures(narrative, required)
    advisory_disclosures = check_required_disclosures(narrative, advisory_required)
    numeric = check_numeric_consistency(cited_numbers, authoritative_values, thresholds)

    blocking_findings = []
    advisory_findings = []

    for h in advice["hits"]:
        blocking_findings.append({
            "category": "advice_language", "severity": "blocking",
            "detail": "Report contains advice / action-recommendation language.",
            "evidence": h["evidence"],
        })
    for h in guarantee["hits"]:
        blocking_findings.append({
            "category": "guarantee_language", "severity": "blocking",
            "detail": "Report contains guarantee / certainty language.",
            "evidence": h["evidence"],
        })
    for key in disclosures["missing"]:
        blocking_findings.append({
            "category": "missing_disclosure", "severity": "blocking",
            "detail": f"Required disclosure missing: {key}.",
            "evidence": key,
        })
    for m in numeric["mismatches"]:
        blocking_findings.append({
            "category": "numeric_inconsistency", "severity": "blocking",
            "detail": (f"Cited number '{m.get('label')}' = {m['cited_value']} does not match "
                       f"authoritative {m['authoritative_key']} = {m['authoritative_value']}."),
            "evidence": f"{m['authoritative_key']}: cited {m['cited_value']} vs authoritative {m['authoritative_value']}",
        })

    for key in advisory_disclosures["missing"]:
        advisory_findings.append({
            "category": "missing_disclosure_advisory", "severity": "advisory",
            "detail": f"Advisory disclosure missing (not blocking): {key}.",
            "evidence": key,
        })

    verdict = "fail" if blocking_findings else "pass"

    return {
        "verdict": verdict,
        "blocking_findings": blocking_findings,
        "advisory_findings": advisory_findings,
        "checks": {
            "advice_language": advice,
            "guarantee_language": guarantee,
            "required_disclosures": disclosures,
            "numeric_consistency": numeric,
        },
        "summary": {
            "blocking_count": len(blocking_findings),
            "advisory_count": len(advisory_findings),
        },
    }


def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
    else:
        cfg = json.load(sys.stdin)

    result = run(cfg)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    if isinstance(result, dict) and result.get("error"):
        sys.exit(1)


if __name__ == "__main__":
    main()
