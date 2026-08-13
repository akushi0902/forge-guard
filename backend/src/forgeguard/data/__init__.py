"""Data layer — SQLAlchemy models and repository implementations.

The data layer is the only layer permitted to interact with the database.
Service-layer modules must access data exclusively through the repository
interfaces defined in ``forgeguard.data.repositories``.
"""
