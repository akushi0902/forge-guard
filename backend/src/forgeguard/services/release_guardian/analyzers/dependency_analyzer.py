"""DependencyAnalyzer — dependency change and CVE detection from a diff."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

import structlog

from forgeguard.services.release_guardian.models import (
    CVEInfo,
    DependencyChange,
    DependencyManifest,
    DependencyMetrics,
)

logger = structlog.get_logger(__name__)

_CVE_DB_PATH = Path(__file__).parent.parent / "fixtures" / "known_cves.json"

# Regex patterns for parsing dependency lines
_PIP_ADD = re.compile(r"^\+\s*([A-Za-z0-9_.\-]+)([>=<!~^]+[\d.]+[^#\n]*)?")
_PIP_REMOVE = re.compile(r"^-\s*([A-Za-z0-9_.\-]+)([>=<!~^]+[\d.]+[^#\n]*)?")
_VERSION_SPEC = re.compile(r"[>=<!~^]+\s*([\d.]+)")

# Semver major bump detection
_SEMVER = re.compile(r"^(\d+)\.")


def _extract_package_name(line: str) -> Optional[str]:
    """Extract a clean package name from a requirements/pyproject line."""
    # Strip leading +/- and whitespace
    clean = line.lstrip("+-").strip()
    # Stop at version specifier, comment, or bracket
    name = re.split(r"[>=<!~^@\s#\[]", clean)[0].strip()
    return name.lower() if name else None


def _extract_version(spec: str) -> Optional[str]:
    m = _VERSION_SPEC.search(spec)
    return m.group(1) if m else None


def _is_major_bump(from_ver: Optional[str], to_ver: Optional[str]) -> bool:
    """Return True if the major version number increased."""
    if not from_ver or not to_ver:
        return False
    mf = _SEMVER.match(from_ver)
    mt = _SEMVER.match(to_ver)
    if mf and mt:
        return int(mt.group(1)) > int(mf.group(1))
    return False


def _load_cve_db() -> dict[str, list[dict]]:
    """Load the local CVE database keyed by package name (lowercase)."""
    try:
        with open(_CVE_DB_PATH) as f:
            data = json.load(f)
        # Normalize: {package_name: [cve_entry, ...]}
        db: dict[str, list[dict]] = {}
        for entry in data.get("cves", []):
            pkg = entry.get("affected_package", "").lower()
            if pkg:
                db.setdefault(pkg, []).append(entry)
        return db
    except Exception as exc:
        logger.warning("dependency_analyzer.cve_db_load_failed", error=str(exc))
        return {}


class DependencyAnalyzer:
    """Analyzes dependency manifest diffs for changes and known CVEs.

    Supports requirements.txt, pyproject.toml (simplified), and package.json
    format detection based on filename.
    """

    def __init__(self, cve_db_path: Optional[Path] = None) -> None:
        path = cve_db_path or _CVE_DB_PATH
        try:
            with open(path) as f:
                raw = json.load(f)
            self._cve_db: dict[str, list[dict]] = {}
            for entry in raw.get("cves", []):
                pkg = entry.get("affected_package", "").lower()
                if pkg:
                    self._cve_db.setdefault(pkg, []).append(entry)
        except Exception as exc:
            logger.warning("dependency_analyzer.init_cve_db_failed", error=str(exc))
            self._cve_db = {}

    def analyze(self, manifests: list[DependencyManifest]) -> DependencyMetrics:
        all_added: list[str] = []
        all_removed: list[str] = []
        all_updated: list[DependencyChange] = []
        major_bumps = 0

        for manifest in manifests:
            added, removed, updated = self._parse_manifest(manifest)
            all_added.extend(added)
            all_removed.extend(removed)
            all_updated.extend(updated)
            major_bumps += sum(
                1 for u in updated if _is_major_bump(u.from_version, u.to_version)
            )

        # De-duplicate: a package in both added and removed is likely updated
        added_names = set(all_added)
        removed_names = set(all_removed)
        net_added = sorted(added_names - removed_names)
        net_removed = sorted(removed_names - added_names)

        # CVE lookup for all packages that changed
        all_changed_packages = added_names | removed_names | {u.name for u in all_updated}
        known_cves = self._lookup_cves(all_changed_packages)

        return DependencyMetrics(
            dependencies_added=net_added,
            dependencies_removed=net_removed,
            dependencies_updated=all_updated,
            known_cves=known_cves,
            major_version_bumps=major_bumps,
        )

    def _parse_manifest(
        self, manifest: DependencyManifest
    ) -> tuple[list[str], list[str], list[DependencyChange]]:
        """Parse a DependencyManifest diff into added/removed/updated lists."""
        # Prefer pre-parsed changes if the provider already parsed them
        if manifest.added_dependencies or manifest.removed_dependencies or manifest.updated_dependencies:
            added = [d.name for d in manifest.added_dependencies]
            removed = [d.name for d in manifest.removed_dependencies]
            return added, removed, list(manifest.updated_dependencies)

        if not manifest.patch:
            return [], [], []

        if "requirements" in manifest.filename.lower() or manifest.manifest_type == "requirements":
            return self._parse_requirements_diff(manifest.patch)
        elif "pyproject" in manifest.filename.lower() or manifest.manifest_type == "pyproject":
            return self._parse_pyproject_diff(manifest.patch)
        elif "package.json" in manifest.filename.lower() or manifest.manifest_type == "package_json":
            return self._parse_package_json_diff(manifest.patch)
        return [], [], []

    def _parse_requirements_diff(
        self, patch: str
    ) -> tuple[list[str], list[str], list[DependencyChange]]:
        added: list[str] = []
        removed: list[str] = []
        for line in patch.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                name = _extract_package_name(line)
                if name:
                    added.append(name)
            elif line.startswith("-") and not line.startswith("---"):
                name = _extract_package_name(line)
                if name:
                    removed.append(name)
        # Detect updates: same package in both added and removed
        updated = self._detect_updates(added, removed, patch)
        net_added = [n for n in added if n not in {u.name for u in updated}]
        net_removed = [n for n in removed if n not in {u.name for u in updated}]
        return net_added, net_removed, updated

    def _parse_pyproject_diff(
        self, patch: str
    ) -> tuple[list[str], list[str], list[DependencyChange]]:
        # Same heuristic as requirements for lines under [tool.poetry.dependencies]
        return self._parse_requirements_diff(patch)

    def _parse_package_json_diff(
        self, patch: str
    ) -> tuple[list[str], list[str], list[DependencyChange]]:
        added: list[str] = []
        removed: list[str] = []
        pkg_line = re.compile(r'^([+-])\s+"([^"]+)":\s+"([^"]+)"')
        for line in patch.splitlines():
            m = pkg_line.match(line)
            if m:
                sign, name, _ver = m.groups()
                if sign == "+":
                    added.append(name.lower())
                elif sign == "-":
                    removed.append(name.lower())
        updated = self._detect_updates(added, removed, patch)
        net_added = [n for n in added if n not in {u.name for u in updated}]
        net_removed = [n for n in removed if n not in {u.name for u in updated}]
        return net_added, net_removed, updated

    def _detect_updates(
        self, added: list[str], removed: list[str], patch: str
    ) -> list[DependencyChange]:
        """Match packages that appear in both added and removed as version updates."""
        added_set = set(added)
        removed_set = set(removed)
        updated_names = added_set & removed_set
        if not updated_names:
            return []

        # Try to extract from/to versions from the patch
        changes: list[DependencyChange] = []
        for name in sorted(updated_names):
            from_ver: Optional[str] = None
            to_ver: Optional[str] = None
            for line in patch.splitlines():
                if name in line.lower():
                    ver = _extract_version(line)
                    if line.startswith("-") and not from_ver:
                        from_ver = ver
                    elif line.startswith("+") and not to_ver:
                        to_ver = ver
            changes.append(DependencyChange(
                name=name,
                change_type="updated",
                from_version=from_ver,
                to_version=to_ver,
            ))
        return changes

    def _lookup_cves(self, package_names: set[str]) -> list[CVEInfo]:
        """Return CVE entries for any of the given package names."""
        result: list[CVEInfo] = []
        for name in package_names:
            entries = self._cve_db.get(name.lower(), [])
            for entry in entries:
                result.append(CVEInfo(
                    id=entry.get("id", "UNKNOWN"),
                    severity=entry.get("severity", "unknown"),
                    affected_package=entry.get("affected_package", name),
                    affected_versions=entry.get("affected_versions"),
                    description=entry.get("description"),
                ))
        return result
