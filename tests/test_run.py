import os

from backend.run import frontend_is_stale


def _touch(path, mtime):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x")
    os.utime(path, (mtime, mtime))


def test_a_missing_build_is_stale(tmp_path):
    _touch(tmp_path / "src" / "App.jsx", 100)
    assert frontend_is_stale(tmp_path, tmp_path / "dist")


def test_a_build_newer_than_its_source_is_fresh(tmp_path):
    _touch(tmp_path / "src" / "views" / "Archive.jsx", 100)
    _touch(tmp_path / "package.json", 100)
    _touch(tmp_path / "dist" / "index.html", 200)
    assert not frontend_is_stale(tmp_path, tmp_path / "dist")


def test_a_pulled_source_change_makes_the_build_stale(tmp_path):
    _touch(tmp_path / "dist" / "index.html", 200)
    _touch(tmp_path / "src" / "views" / "Archive.jsx", 300)   # nested, like a real pull
    assert frontend_is_stale(tmp_path, tmp_path / "dist")


def test_a_dependency_change_makes_the_build_stale(tmp_path):
    _touch(tmp_path / "src" / "App.jsx", 100)
    _touch(tmp_path / "dist" / "index.html", 200)
    _touch(tmp_path / "package-lock.json", 300)
    assert frontend_is_stale(tmp_path, tmp_path / "dist")
