"""Rule-based intent classifier for AI agent queries (WO-065).

Classifies free-text queries into one of six intent categories using
keyword matching and pattern recognition.  No LLM call is made here.
"""

from __future__ import annotations

import re
from enum import Enum


class IntentCategory(str, Enum):
    """Six intent categories for the AI agent conversational interface."""

    HEALTH_SCORE = "health_score"
    FINDINGS = "findings"
    REMEDIATION = "remediation"
    RELEASE_STATUS = "release_status"
    POLICY_RULES = "policy_rules"
    GENERAL_HELP = "general_help"


# ---------------------------------------------------------------------------
# Keyword patterns per category (case-insensitive, searched left-to-right;
# first match wins).
# ---------------------------------------------------------------------------

_PATTERNS: list[tuple[IntentCategory, list[str]]] = [
    (
        IntentCategory.HEALTH_SCORE,
        [
            r"\bhealth\s*score\b",
            r"\boverall\s*score\b",
            r"\bengineering\s*score\b",
            r"\bservice\s*(score|health|rating|status)\b",
            r"\bscore\s*(breakdown|detail|summary)\b",
            r"\bhow\s+(healthy|good)\b",
            r"\bdimension\s*score\b",
            r"\bcoverage\s+score\b",
            r"\bsecurity\s+score\b",
            r"\btest\s+score\b",
        ],
    ),
    (
        IntentCategory.FINDINGS,
        [
            r"\bfinding(s)?\b",
            r"\bviolation(s)?\b",
            r"\bpolicy\s+issue(s)?\b",
            r"\bfailed\s+rule(s)?\b",
            r"\bopen\s+issue(s)?\b",
            r"\bcritical\s+(issue|finding|violation)\b",
            r"\bhigh\s+(severity|finding)\b",
            r"\bwhat.*(wrong|broken|failing)\b",
            r"\bshow\s+(me\s+)?(my\s+)?finding(s)?\b",
            r"\blist\s+(my\s+)?issue(s)?\b",
        ],
    ),
    (
        IntentCategory.REMEDIATION,
        [
            r"\bremediat(e|ion|ing)\b",
            r"\bfix(ing|es)?\b",
            r"\bhow\s+(to|do\s+I)\s+(fix|resolve|address|remediate)\b",
            r"\bresolv(e|ing|ed)\b",
            r"\bguidanc(e|ance)\b",
            r"\brecommendation(s)?\b",
            r"\bstep(s)?\s+(to|for)\s+fix\b",
            r"\bimprove\s+(score|coverage|quality)\b",
            r"\bwhat\s+should\s+I\s+do\b",
        ],
    ),
    (
        IntentCategory.RELEASE_STATUS,
        [
            r"\brelease\s*(status|decision|block|approve|risk|assessment)\b",
            r"\bcan\s+I\s+release\b",
            r"\bready\s+to\s+release\b",
            r"\bblocked?\s+(from\s+release|release)\b",
            r"\bapprove(d)?\s+release\b",
            r"\brelease\s+risk\b",
            r"\bpr\s+risk\b",
            r"\bdeployment\s*(risk|status|decision)\b",
            r"\brelease\s+gate\b",
        ],
    ),
    (
        IntentCategory.POLICY_RULES,
        [
            r"\bpolic(y|ies)\b",
            r"\bpolicy\s+rule(s)?\b",
            r"\brule(s)?\s+(list|config|definition)\b",
            r"\bthreshold(s)?\b",
            r"\bwhat\s+(are\s+the\s+)?rule(s)?\b",
            r"\bconfigur(e|ation|ations)\s+(rule|policy)\b",
            r"\bgovernance\s*rule(s)?\b",
            r"\bweight(ed|s|ing)\b",
            r"\bdimension\s+(config|definition|rule)\b",
        ],
    ),
]


class IntentClassifier:
    """Classify free-text queries into one of six intent categories.

    Classification is purely rule-based (no LLM call).  Unknown queries
    fall through to :attr:`IntentCategory.GENERAL_HELP`.
    """

    def __init__(self) -> None:
        self._compiled: list[tuple[IntentCategory, list[re.Pattern[str]]]] = [
            (cat, [re.compile(p, re.IGNORECASE) for p in patterns])
            for cat, patterns in _PATTERNS
        ]

    def classify(self, query: str) -> IntentCategory:
        """Return the best-matching :class:`IntentCategory` for *query*.

        Uses first-match-wins over the ordered pattern list.  Falls back to
        :attr:`IntentCategory.GENERAL_HELP` when no pattern matches.
        """
        if not query or not query.strip():
            return IntentCategory.GENERAL_HELP

        for category, patterns in self._compiled:
            for pattern in patterns:
                if pattern.search(query):
                    return category

        return IntentCategory.GENERAL_HELP
