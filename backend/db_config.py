"""Single database location for EventMesh backend modules.

Use EVENTMESH_DB_PATH=/var/data/events.db when a persistent disk is mounted.
When absent, local development keeps using backend/events.db.
"""
from pathlib import Path
import os


def database_path() -> Path:
    configured = os.environ.get("EVENTMESH_DB_PATH", "").strip()
    if not configured:
        return Path(__file__).resolve().parent / "events.db"

    path = Path(configured).expanduser()
    if not path.is_absolute():
        raise RuntimeError("EVENTMESH_DB_PATH must be an absolute path")
    if not path.parent.is_dir():
        raise RuntimeError(
            "EVENTMESH_DB_PATH parent directory does not exist; "
            "verify that the Render persistent disk is mounted"
        )
    return path


DB_PATH = database_path()
