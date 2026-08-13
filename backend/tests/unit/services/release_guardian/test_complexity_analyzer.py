"""Unit tests for ComplexityAnalyzer (WO-045)."""

from __future__ import annotations

import pytest

from forgeguard.services.release_guardian.analyzers.complexity_analyzer import ComplexityAnalyzer
from forgeguard.services.release_guardian.models import FileChange


def _fc(filename="src/app.py", status="modified", additions=10, deletions=5, patch="", is_binary=False):
    return FileChange(filename=filename, status=status, additions=additions, deletions=deletions, patch=patch, is_binary=is_binary)


class TestComplexityAnalyzerBasic:
    def test_empty_files_returns_zero_metrics(self):
        analyzer = ComplexityAnalyzer()
        result = analyzer.analyze([])
        assert result.files_changed == 0
        assert result.lines_added == 0
        assert result.lines_deleted == 0
        assert result.cyclomatic_complexity_delta == 0.0
        assert result.churn_score == 0.0

    def test_files_changed_count(self):
        analyzer = ComplexityAnalyzer()
        files = [_fc(), _fc(filename="src/other.py")]
        result = analyzer.analyze(files)
        assert result.files_changed == 2

    def test_lines_added_summed(self):
        analyzer = ComplexityAnalyzer()
        files = [_fc(additions=10), _fc(additions=20)]
        result = analyzer.analyze(files)
        assert result.lines_added == 30

    def test_lines_deleted_summed(self):
        analyzer = ComplexityAnalyzer()
        files = [_fc(deletions=5), _fc(deletions=15)]
        result = analyzer.analyze(files)
        assert result.lines_deleted == 20

    def test_binary_files_excluded_from_lines(self):
        analyzer = ComplexityAnalyzer()
        files = [
            _fc(additions=100, deletions=50, is_binary=True),
            _fc(additions=10, deletions=5),
        ]
        result = analyzer.analyze(files)
        assert result.lines_added == 10
        assert result.lines_deleted == 5


class TestComplexityAnalyzerComplexity:
    def test_if_statement_increases_complexity(self):
        analyzer = ComplexityAnalyzer()
        patch = "+if condition:\n+    do_something()\n"
        files = [_fc(patch=patch)]
        result = analyzer.analyze(files)
        assert result.cyclomatic_complexity_delta >= 1.0

    def test_for_loop_increases_complexity(self):
        analyzer = ComplexityAnalyzer()
        patch = "+for item in items:\n+    process(item)\n"
        files = [_fc(patch=patch)]
        result = analyzer.analyze(files)
        assert result.cyclomatic_complexity_delta >= 1.0

    def test_try_except_increases_complexity(self):
        analyzer = ComplexityAnalyzer()
        patch = "+try:\n+    risky()\n+except Exception:\n+    pass\n"
        files = [_fc(patch=patch)]
        result = analyzer.analyze(files)
        assert result.cyclomatic_complexity_delta >= 2.0

    def test_no_added_lines_zero_complexity(self):
        analyzer = ComplexityAnalyzer()
        patch = "-old_line\n context_line\n"
        files = [_fc(patch=patch)]
        result = analyzer.analyze(files)
        assert result.cyclomatic_complexity_delta == 0.0

    def test_max_file_complexity_is_highest(self):
        analyzer = ComplexityAnalyzer()
        patch1 = "+if a:\n+if b:\n+if c:\n"  # 3 branches
        patch2 = "+if x:\n"  # 1 branch
        files = [
            _fc(filename="src/a.py", patch=patch1),
            _fc(filename="src/b.py", patch=patch2),
        ]
        result = analyzer.analyze(files)
        assert result.max_file_complexity >= 3.0


class TestChurnScore:
    def test_no_large_files_zero_churn(self):
        analyzer = ComplexityAnalyzer()
        files = [_fc(additions=5, deletions=5)]  # 10 total changes, ≤20
        result = analyzer.analyze(files)
        assert result.churn_score == 0.0

    def test_all_large_files_full_churn(self):
        analyzer = ComplexityAnalyzer()
        files = [
            _fc(additions=15, deletions=10),  # 25 changes > 20
            _fc(filename="src/b.py", additions=20, deletions=10),  # 30 > 20
        ]
        result = analyzer.analyze(files)
        assert result.churn_score == 1.0

    def test_churn_score_in_range(self):
        analyzer = ComplexityAnalyzer()
        files = [
            _fc(additions=50, deletions=20),  # large — churned
            _fc(filename="src/b.py", additions=2, deletions=1),  # small — not churned
        ]
        result = analyzer.analyze(files)
        assert 0.0 <= result.churn_score <= 1.0
