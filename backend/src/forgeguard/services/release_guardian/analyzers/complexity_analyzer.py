"""ComplexityAnalyzer — code complexity and churn metrics from a diff."""

from __future__ import annotations

import re

from forgeguard.services.release_guardian.models import ComplexityMetrics, FileChange

# Patterns in added lines that contribute to cyclomatic complexity delta.
# Each match counts as one branch point added.
_COMPLEXITY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\+\s*(if|elif|else)\b"),
    re.compile(r"^\+\s*(for|while)\b"),
    re.compile(r"^\+\s*(try|except|finally)\b"),
    re.compile(r"^\+\s*and\b"),
    re.compile(r"^\+\s*or\b"),
]

# File extensions to exclude from complexity analysis (binary-ish)
_BINARY_EXTENSIONS: frozenset[str] = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".woff", ".woff2",
    ".ttf", ".eot", ".pdf", ".zip", ".gz", ".tar", ".lock", ".min.js",
})

_CODE_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".java", ".rb", ".rs",
    ".c", ".cpp", ".h", ".hpp", ".cs", ".php", ".swift", ".kt",
})


def _is_code_file(filename: str) -> bool:
    lower = filename.lower()
    return any(lower.endswith(ext) for ext in _CODE_EXTENSIONS)


def _file_complexity(patch: str) -> float:
    """Count branch-point additions in a file patch."""
    count = 0.0
    for line in patch.splitlines():
        for pattern in _COMPLEXITY_PATTERNS:
            if pattern.match(line):
                count += 1.0
                break
    return count


class ComplexityAnalyzer:
    """Analyzes a list of FileChange objects for complexity and churn metrics.

    The churn_score is the fraction of code files with more than 20 lines
    changed (additions + deletions), capped at 1.0.  High churn suggests
    the change is large and potentially risky.
    """

    def analyze(self, files: list[FileChange]) -> ComplexityMetrics:
        code_files = [f for f in files if not f.is_binary]
        total_added = sum(f.additions for f in code_files)
        total_deleted = sum(f.deletions for f in code_files)

        complexity_deltas: list[float] = []
        for f in code_files:
            if _is_code_file(f.filename) and f.patch:
                delta = _file_complexity(f.patch)
                complexity_deltas.append(delta)

        max_complexity = max(complexity_deltas, default=0.0)
        total_complexity_delta = sum(complexity_deltas)

        # Churn: fraction of code files with >20 line changes
        if code_files:
            churned = sum(
                1 for f in code_files if (f.additions + f.deletions) > 20
            )
            churn_score = min(churned / len(code_files), 1.0)
        else:
            churn_score = 0.0

        return ComplexityMetrics(
            files_changed=len(files),
            lines_added=total_added,
            lines_deleted=total_deleted,
            cyclomatic_complexity_delta=round(total_complexity_delta, 2),
            max_file_complexity=round(max_complexity, 2),
            churn_score=round(churn_score, 3),
        )
