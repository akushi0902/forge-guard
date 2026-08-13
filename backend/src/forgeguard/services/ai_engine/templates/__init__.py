"""Template storage package for the AI Engine fallback system.

Templates are stored as YAML files in the ``data/`` sub-directory,
one file per risk dimension.  The :class:`~forgeguard.services.ai_engine.template_engine.TemplateEngine`
loads and validates all templates at startup.
"""
