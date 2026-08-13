"""Unit tests for CoverageAnalyzer (WO-045)."""

from __future__ import annotations

import pytest

from forgeguard.services.release_guardian.analyzers.coverage_analyzer import CoverageAnalyzer
from forgeguard.services.release_guardian.models import FileChange


def _fc(filename="src/app.py", status="modified", additions=10, deletions=0, patch=""):
    return FileChange(filename=filename, status=status, additions=additions, deletions=deletions, patch=patch)


class TestTestFileDetection:
    def test_test_prefix_detected(self):
        analyzer = CoverageAnalyzer()
        files = [_fc(filename="tests/test_payment.py", additions=20)]
        result = analyzer.analyze(files)
        assert result.test_files_changed == 1
        assert result.test_lines_added == 20

    def test_test_suffix_detected(self):
        analyzer = CoverageAnalyzer()
        files = [_fc(filename="src/payment_test.py", additions=15)]
        result = analyzer.analyze(files)
        assert result.test_files_changed == 1

    def test_tests_directory_detected(self):
        analyzer = CoverageAnalyzer()
        files = [_fc(filename="backend/tests/test_models.py", additions=10)]
        result = analyzer.analyze(files)
        assert result.test_files_changed == 1

    def test_spec_file_detected(self):
        analyzer = CoverageAnalyzer()
        files = [_fc(filename="src/app.test.ts", additions=8)]
        result = analyzer.analyze(files)
        assert result.test_files_changed == 1

    def test_production_file_not_test(self):
        analyzer = CoverageAnalyzer()
        files = [_fc(filename="src/payment_processor.py", additions=20)]
        result = analyzer.analyze(files)
        assert result.test_files_changed == 0


class TestHasNewTests:
    def test_new_test_file_added(self):
        analyzer = CoverageAnalyzer()
        files = [_fc(filename="tests/test_new.py", status="added", additions=50)]
        result = analyzer.analyze(files)
        assert result.has_new_tests is True

    def test_test_lines_added_sets_has_new_tests(self):
        analyzer = CoverageAnalyzer()
        files = [_fc(filename="tests/test_existing.py", additions=10)]
        result = analyzer.analyze(files)
        assert result.has_new_tests is True

    def test_no_tests_no_new_tests(self):
        analyzer = CoverageAnalyzer()
        files = [_fc(filename="src/app.py", additions=20)]
        result = analyzer.analyze(files)
        assert result.has_new_tests is False


class TestCoverageDelta:
    def test_test_only_change_positive_delta(self):
        analyzer = CoverageAnalyzer()
        files = [_fc(filename="tests/test_app.py", additions=40)]
        result = analyzer.analyze(files)
        assert result.estimated_coverage_delta > 0

    def test_code_without_tests_negative_delta(self):
        analyzer = CoverageAnalyzer()
        files = [_fc(filename="src/new_feature.py", additions=100)]
        result = analyzer.analyze(files)
        assert result.estimated_coverage_delta < 0

    def test_equal_test_code_zero_or_positive_delta(self):
        analyzer = CoverageAnalyzer()
        files = [
            _fc(filename="src/feature.py", additions=50),
            _fc(filename="tests/test_feature.py", additions=60),
        ]
        result = analyzer.analyze(files)
        assert result.estimated_coverage_delta >= 0


class TestTestToCodeRatio:
    def test_only_code_zero_ratio(self):
        analyzer = CoverageAnalyzer()
        files = [_fc(filename="src/app.py", additions=50)]
        result = analyzer.analyze(files)
        assert result.test_to_code_ratio == 0.0

    def test_only_tests_ratio_one(self):
        analyzer = CoverageAnalyzer()
        files = [_fc(filename="tests/test_app.py", additions=50)]
        result = analyzer.analyze(files)
        assert result.test_to_code_ratio == 1.0

    def test_ratio_calculated(self):
        analyzer = CoverageAnalyzer()
        files = [
            _fc(filename="src/app.py", additions=100),
            _fc(filename="tests/test_app.py", additions=50),
        ]
        result = analyzer.analyze(files)
        assert result.test_to_code_ratio == pytest.approx(0.5, abs=0.01)
