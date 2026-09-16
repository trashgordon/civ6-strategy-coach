"""One command to start the coach: builds the frontend if needed, then serves.

    python -m backend.run
"""

import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

from . import config


def _npm() -> str | None:
    return shutil.which("npm")


def ensure_frontend_built(force: bool = False) -> bool:
    """Build frontend/dist if it's missing. Returns False if we couldn't."""
    dist = config.frontend_dist()
    frontend = config.REPO_ROOT / "frontend"

    if dist.is_dir() and (dist / "index.html").is_file() and not force:
        return True

    npm = _npm()
    if npm is None:
        print(
            "The frontend isn't built and npm isn't on your PATH.\n"
            "Install Node 18+ (https://nodejs.org), then run:\n"
            "    cd frontend && npm install && npm run build\n",
            file=sys.stderr,
        )
        return False

    if not (frontend / "node_modules").is_dir():
        print("Installing frontend dependencies (one time)...")
        subprocess.run([npm, "install"], cwd=frontend, check=True)

    print("Building the frontend...")
    subprocess.run([npm, "run", "build"], cwd=frontend, check=True)
    return True


def main() -> int:
    import uvicorn

    force = "--rebuild" in sys.argv
    built = ensure_frontend_built(force=force)

    host, port = config.host(), config.port()
    url = f"http://{'localhost' if host in ('0.0.0.0', '127.0.0.1') else host}:{port}"

    print(f"\n  Civ VI Strategy Coach")
    print(f"  model:    {config.model()}")
    print(f"  database: {config.db_path()}")
    print(f"  serving:  {url}\n")
    if not built:
        print("  (serving the API only until the frontend is built)\n")

    if "--no-browser" not in sys.argv and built:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    uvicorn.run("backend.main:app", host=host, port=port, reload="--reload" in sys.argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
