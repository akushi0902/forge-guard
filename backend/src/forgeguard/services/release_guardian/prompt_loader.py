"""PromptLoader — reads and caches .txt prompt templates at startup.

Variable substitution uses str.format_map with a SafeFormatDict that leaves
missing placeholders as-is rather than raising KeyError.  Templates are loaded
once at startup (via load_all()) and served from an in-memory dict on every
subsequent call to render() — no disk I/O on the hot path.
"""

from __future__ import annotations

import threading
from pathlib import Path


class _SafeFormatDict(dict):
    """dict subclass that returns the placeholder unchanged for missing keys."""

    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"


class PromptLoader:
    """Loads and caches .txt prompt templates, renders them via str.format_map.

    Args:
        prompts_dir: Directory containing .txt template files.  Defaults to
                     the ``prompts/`` package directory alongside this module.

    Usage::

        loader = PromptLoader()
        loader.load_all()
        text = loader.render("risk_explanation", {"service_name": "payment-svc", ...})
    """

    def __init__(self, prompts_dir: Path | None = None) -> None:
        self._dir: Path = prompts_dir or Path(__file__).parent / "prompts"
        self._cache: dict[str, str] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def load_all(self) -> None:
        """Load all .txt files in prompts_dir into the in-memory cache."""
        with self._lock:
            for path in self._dir.glob("*.txt"):
                self._cache[path.stem] = path.read_text(encoding="utf-8")

    def render(self, template_name: str, variables: dict) -> str:
        """Render a named template with the supplied variable substitutions.

        Loads the template lazily on first access if not already cached.
        Missing variables are left as literal ``{key}`` placeholders.

        Args:
            template_name: Stem of the .txt file (e.g. ``"risk_explanation"``).
            variables:     Mapping of placeholder names to substitution values.

        Returns:
            Rendered template string.

        Raises:
            FileNotFoundError: If the template file does not exist.
        """
        template = self._cache.get(template_name)
        if template is None:
            path = self._dir / f"{template_name}.txt"
            content = path.read_text(encoding="utf-8")
            with self._lock:
                self._cache[template_name] = content
            template = content
        return template.format_map(_SafeFormatDict(variables))

    def is_loaded(self, template_name: str) -> bool:
        """Return True if the template is in the cache."""
        return template_name in self._cache

    @property
    def loaded_templates(self) -> list[str]:
        """Names of all currently cached templates."""
        return list(self._cache.keys())
