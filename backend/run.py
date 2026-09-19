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


# What the build is made from. A `git pull` that touches any of these leaves the
# existing dist stale, so the launcher rebuilds rather than serving the old UI.
BUILD_INPUTS = ("src", "index.html", "package.json", "package-lock.json", "vite.config.js")


def _newest_mtime(paths) -> float:
    newest = 0.0
    for path in paths:
        if path.is_dir():
            newest = max([newest, *(f.stat().st_mtime for f in path.rglob("*") if f.is_file())])
        elif path.is_file():
            newest = max(newest, path.stat().st_mtime)
    return newest


def frontend_is_stale(frontend: Path, dist: Path) -> bool:
    """True when dist is missing or any build input changed after it was built."""
    built = dist / "index.html"
    if not built.is_file():
        return True
    return _newest_mtime(frontend / name for name in BUILD_INPUTS) > built.stat().st_mtime


def ensure_frontend_built(force: bool = False) -> bool:
    """Build frontend/dist if it's missing or out of date. Returns False if we couldn't."""
    dist = config.frontend_dist()
    frontend = config.REPO_ROOT / "frontend"

    if not force and not frontend_is_stale(frontend, dist):
        return True
    have_build = (dist / "index.html").is_file()

    npm = _npm()
    if npm is None:
        if have_build:
            # Better an older UI than none: serve what's there and say why.
            print(
                "The frontend source has changed since it was last built, but npm isn't\n"
                "on your PATH, so you're getting the older build. Install Node 18+\n"
                "(https://nodejs.org), then run:  python -m backend.run --rebuild\n",
                file=sys.stderr,
            )
            return True
        print(
            "The frontend isn't built and npm isn't on your PATH.\n"
            "Install Node 18+ (https://nodejs.org), then run:\n"
            "    cd frontend && npm install && npm run build\n",
            file=sys.stderr,
        )
        return False

    # npm rewrites node_modules/.package-lock.json on every install, so a lockfile newer
    # than it means a pull changed the dependencies.
    lockfile = frontend / "package-lock.json"
    installed = frontend / "node_modules" / ".package-lock.json"
    if not installed.is_file() or (
        lockfile.is_file() and lockfile.stat().st_mtime > installed.stat().st_mtime
    ):
        print("Installing frontend dependencies...")
        subprocess.run([npm, "install"], cwd=frontend, check=True)

    print("Building the frontend..." if not have_build else "Frontend source changed — rebuilding...")
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
