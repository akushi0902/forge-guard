"""CoverageAnalyzer — test coverage impact metrics from a diff."""

from __future__ import annotations

import re

from forgeguard.services.release_guardian.models import CoverageMetrics, FileChange

# Path patterns that identify test files
_TEST_PATH_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(^|/)test_[^/]+\.py$"),
    re.compile(r"(^|/).*_test\.py$"),
    re.compile(r"(^|/)tests?/"),
    re.compile(r"(^|/)spec[s]?/"),
    re.compile(r"\.test\.(ts|tsx|js|jsx)$"),
    re.compile(r"\.spec\.(ts|tsx|js|jsx)$"),
]


def _is_test_file(filename: str) -> bool:
    return any(p.search(filename) for p in _TEST_PATH_PATTERNS)


def _is_code_file(filename: str) -> bool:
    _CODE_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".java",
                        ".rb", ".rs", ".c", ".cpp", ".cs", ".php"}
    return any(filename.lower().endswith(ext) for ext in _CODE_EXTENSIONS)


class CoverageAnalyzer:
    """Estimates test coverage impact from file changes.

    The estimated_coverage_delta is a heuristic:
    - Positive if tests were added and no new code files were added
    - Negative if new code files were added without corresponding test additions
    - Zero for test-only changes (coverage stays the same or improves)

    The test_to_code_ratio measures how many added test lines exist per
    added non-test code line.
    """

    def analyze(self, files: list[FileChange]) -> CoverageMetrics:
        test_files = [f for f in files if _is_test_file(f.filename)]
        code_files = [f for f in files if _is_code_file(f.filename) and not _is_test_file(f.filename)]

        test_files_changed = len(test_files)
        test_lines_added = sum(f.additions for f in test_files)
        has_new_tests = any(f.status == "added" for f in test_files) or test_lines_added > 0

        code_lines_added = sum(f.additions for f in code_files)

        # Compute ratio: test additions per code addition
        if code_lines_added > 0:
            test_to_code_ratio = round(test_lines_added / code_lines_added, 3)
        elif test_lines_added > 0:
            test_to_code_ratio = 1.0  # only tests added
        else:
            test_to_code_ratio = 0.0

        # Estimate coverage delta: heuristic based on ratio vs. 1.0 baseline
        if code_lines_added == 0 and test_lines_added > 0:
            estimated_coverage_delta = 2.0  # test-only — small positive bump
        elif code_lines_added > 0 and test_to_code_ratio >= 1.0:
            estimated_coverage_delta = 1.0  # tests keep up with code
        elif code_lines_added > 0 and test_to_code_ratio >= 0.5:
            estimated_coverage_delta = 0.0  # partial coverage
        elif code_lines_added > 0:
            estimated_coverage_delta = -2.0  # code without tests drops coverage
        else:
            estimated_coverage_delta = 0.0

        return CoverageMetrics(
            test_files_changed=test_files_changed,
            test_lines_added=test_lines_added,
            estimated_coverage_delta=estimated_coverage_delta,
            has_new_tests=has_new_tests,
            test_to_code_ratio=test_to_code_ratio,
        )
