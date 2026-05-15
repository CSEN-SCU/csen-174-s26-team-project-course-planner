"""Authentication layer: SQLite-backed users + OAuth helpers.

Submodules use absolute imports (``from auth.users_db import ...``)
because the FastAPI app runs with ``cwd = project/course_planner/`` on
``sys.path`` so ``auth``, ``db``, ``agents``, ``utils`` resolve as
top-level packages.
"""
