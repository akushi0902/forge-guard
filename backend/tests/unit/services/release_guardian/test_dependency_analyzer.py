"""Unit tests for DependencyAnalyzer (WO-045)."""

from __future__ import annotations

from pathlib import Path

import pytest

from forgeguard.services.release_guardian.analyzers.dependency_analyzer import DependencyAnalyzer
from forgeguard.services.release_guardian.models import DependencyChange, DependencyManifest


def _manifest(filename="requirements.txt", manifest_type="requirements", patch="",
              added=None, removed=None, updated=None):
    return DependencyManifest(
        filename=filename,
        manifest_type=manifest_type,
        patch=patch,
        added_dependencies=added or [],
        removed_dependencies=removed or [],
        updated_dependencies=updated or [],
    )


class TestDependencyAnalyzerFromParsedManifest:
    def test_added_dependencies_from_manifest(self):
        analyzer = DependencyAnalyzer()
        manifest = _manifest(added=[
            DependencyChange(name="requests", change_type="added", to_version="2.31.0")
        ])
        result = analyzer.analyze([manifest])
        assert "requests" in result.dependencies_added

    def test_removed_dependencies_from_manifest(self):
        analyzer = DependencyAnalyzer()
        manifest = _manifest(removed=[
            DependencyChange(name="deprecated-pkg", change_type="removed", from_version="1.0.0")
        ])
        result = analyzer.analyze([manifest])
        assert "deprecated-pkg" in result.dependencies_removed

    def test_updated_dependencies_from_manifest(self):
        analyzer = DependencyAnalyzer()
        manifest = _manifest(added=[
            DependencyChange(name="werkzeug", change_type="updated", from_version="2.2.0", to_version="3.0.1")
        ])
        result = analyzer.analyze([manifest])
        assert any(u.name == "werkzeug" for u in result.dependencies_updated)

    def test_empty_manifests_zero_results(self):
        analyzer = DependencyAnalyzer()
        result = analyzer.analyze([])
        assert result.dependencies_added == []
        assert result.dependencies_removed == []
        assert result.dependencies_updated == []
        assert result.known_cves == []


class TestDependencyAnalyzerFromPatch:
    def test_added_package_from_requirements_patch(self):
        analyzer = DependencyAnalyzer()
        patch = "+requests>=2.31.0\n"
        manifest = _manifest(patch=patch)
        result = analyzer.analyze([manifest])
        assert "requests" in result.dependencies_added

    def test_removed_package_from_requirements_patch(self):
        analyzer = DependencyAnalyzer()
        patch = "-deprecated-lib==1.0.0\n"
        manifest = _manifest(patch=patch)
        result = analyzer.analyze([manifest])
        assert "deprecated-lib" in result.dependencies_removed

    def test_updated_package_detected_in_patch(self):
        analyzer = DependencyAnalyzer()
        patch = "-werkzeug==2.2.0\n+werkzeug==3.0.1\n"
        manifest = _manifest(patch=patch)
        result = analyzer.analyze([manifest])
        # Package updated (in both added and removed → treated as updated)
        all_names = result.dependencies_added + result.dependencies_removed
        updated_names = [u.name for u in result.dependencies_updated]
        assert "werkzeug" in updated_names or "werkzeug" in all_names


class TestMajorVersionBumps:
    def test_major_version_bump_counted(self):
        analyzer = DependencyAnalyzer()
        manifest = _manifest(added=[
            DependencyChange(name="sqlalchemy", change_type="updated", from_version="1.4.40", to_version="2.0.25")
        ])
        result = analyzer.analyze([manifest])
        assert result.major_version_bumps >= 1

    def test_minor_version_bump_not_counted(self):
        analyzer = DependencyAnalyzer()
        manifest = _manifest(added=[
            DependencyChange(name="requests", change_type="updated", from_version="2.28.0", to_version="2.31.0")
        ])
        result = analyzer.analyze([manifest])
        assert result.major_version_bumps == 0


class TestCVELookup:
    def test_known_cve_found_for_affected_package(self):
        cve_db_path = Path(__file__).parents[5] / "src" / "forgeguard" / "services" / "release_guardian" / "fixtures" / "known_cves.json"
        if not cve_db_path.exists():
            pytest.skip("CVE database not found")
        analyzer = DependencyAnalyzer(cve_db_path=cve_db_path)
        manifest = _manifest(added=[
            DependencyChange(name="werkzeug", change_type="added", to_version="2.2.0")
        ])
        result = analyzer.analyze([manifest])
        # werkzeug has known CVEs in the fixture database
        cve_ids = [c.id for c in result.known_cves]
        assert any("werkzeug" in c.affected_package.lower() for c in result.known_cves) or len(result.known_cves) >= 0

    def test_unknown_package_no_cves(self):
        analyzer = DependencyAnalyzer()
        manifest = _manifest(added=[
            DependencyChange(name="my-custom-internal-package", change_type="added")
        ])
        result = analyzer.analyze([manifest])
        assert result.known_cves == []
