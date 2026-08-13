"""MockChangeDataProvider — pre-configured scenarios for demo and testing.

Loads scenarios from YAML fixture files in the fixtures/scenarios/ directory.
Enables full pipeline demonstration without GitHub API access.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import structlog
import yaml

from .models import (
    DependencyChange,
    DependencyManifest,
    DiffResult,
    FileChange,
    PRMetadata,
)
from .providers import ChangeDataProvider, ChangeDataProviderError

logger = structlog.get_logger(__name__)

_SCENARIOS_DIR = Path(__file__).parent / "fixtures" / "scenarios"


def _load_scenario(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def _build_file_change(raw: dict) -> FileChange:
    return FileChange(
        filename=raw["filename"],
        status=raw.get("status", "modified"),
        additions=raw.get("additions", 0),
        deletions=raw.get("deletions", 0),
        patch=raw.get("patch"),
        is_binary=raw.get("is_binary", False),
    )


def _build_dependency_manifest(raw: dict) -> DependencyManifest:
    added: list[DependencyChange] = []
    removed: list[DependencyChange] = []
    updated: list[DependencyChange] = []

    for entry in raw.get("added_dependencies", []):
        if isinstance(entry, dict):
            change_type = entry.get("change_type", "added")
            dc = DependencyChange(
                name=entry["name"],
                change_type=change_type,
                from_version=entry.get("from_version"),
                to_version=entry.get("to_version"),
            )
            if change_type == "updated":
                updated.append(dc)
            else:
                added.append(dc)

    for entry in raw.get("removed_dependencies", []):
        if isinstance(entry, dict):
            removed.append(DependencyChange(
                name=entry["name"],
                change_type="removed",
                from_version=entry.get("from_version"),
            ))

    for entry in raw.get("updated_dependencies", []):
        if isinstance(entry, dict):
            updated.append(DependencyChange(
                name=entry["name"],
                change_type="updated",
                from_version=entry.get("from_version"),
                to_version=entry.get("to_version"),
            ))

    return DependencyManifest(
        filename=raw["filename"],
        manifest_type=raw.get("manifest_type", "requirements"),
        added_dependencies=added,
        removed_dependencies=removed,
        updated_dependencies=updated,
        patch=raw.get("patch"),
    )


class MockChangeDataProvider(ChangeDataProvider):
    """Implements ChangeDataProvider using pre-configured YAML scenarios.

    The scenario is selected by name at construction time.  If the named
    scenario cannot be found, a ChangeDataProviderError is raised.

    Args:
        scenario_name: Name of the scenario to load (matches the 'name' key
                       in the YAML fixture file).  Use ``list_scenarios()``
                       to see available scenarios.
        scenarios_dir: Optional override for the fixtures/scenarios/ directory.
    """

    PROVIDER_NAME = "mock"

    def __init__(
        self,
        scenario_name: str,
        *,
        scenarios_dir: Optional[Path] = None,
    ) -> None:
        self._scenario_name = scenario_name
        self._dir = scenarios_dir or _SCENARIOS_DIR
        self._scenario = self._find_scenario(scenario_name)

    def _find_scenario(self, name: str) -> dict:
        for path in self._dir.glob("*.yaml"):
            try:
                data = _load_scenario(path)
                if data.get("name") == name:
                    return data
            except Exception as exc:
                logger.warning("mock_provider.scenario_load_failed", path=str(path), error=str(exc))
        raise ChangeDataProviderError(
            f"Mock scenario {name!r} not found in {self._dir}",
            endpoint="mock",
        )

    @classmethod
    def list_scenarios(cls, scenarios_dir: Optional[Path] = None) -> list[str]:
        """Return the names of all available mock scenarios."""
        d = scenarios_dir or _SCENARIOS_DIR
        names: list[str] = []
        for path in sorted(d.glob("*.yaml")):
            try:
                data = _load_scenario(path)
                if "name" in data:
                    names.append(data["name"])
            except Exception:
                pass
        return names

    async def get_commit_diff(self, commit_sha: str) -> DiffResult:
        files = [_build_file_change(f) for f in self._scenario.get("files", [])]
        total_add = sum(f.additions for f in files)
        total_del = sum(f.deletions for f in files)
        return DiffResult(
            commit_sha=self._scenario.get("commit_sha", commit_sha),
            total_additions=total_add,
            total_deletions=total_del,
            files=files,
        )

    async def get_pr_metadata(self, pr_reference: str) -> PRMetadata:
        return PRMetadata(
            pr_number=int(self._scenario.get("pr_reference", "0") or 0),
            title=self._scenario.get("description"),
            state="open",
        )

    async def get_file_changes(self, commit_sha: str) -> list[FileChange]:
        return [_build_file_change(f) for f in self._scenario.get("files", [])]

    async def get_dependency_manifests(
        self, commit_sha: str, file_paths: list[str]
    ) -> list[DependencyManifest]:
        manifests: list[DependencyManifest] = []
        for raw in self._scenario.get("dependency_manifests", []):
            if isinstance(raw, dict):
                manifests.append(_build_dependency_manifest(raw))
        return manifests
