"""Authentication layer: SQLite-backed users + streamlit-authenticator wrapper.

The submodules use absolute imports (`from auth.users_db import ...`)
because the Streamlit app runs with cwd = project/course_planner/, so
`auth`, `db`, `agents`, `utils` are top-level packages on sys.path.
"""
