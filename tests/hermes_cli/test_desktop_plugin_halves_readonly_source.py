"""A desktop half whose source is read-only (the Nix store, a deb/rpm install) still publishes.

``shutil.copytree`` keeps the source's folder modes, so the staged copy of a read-only tree is made of
``0555`` folders: the marker could not be written into it, and the staging folder could not be
removed afterwards, so every reconcile left another ``.<name>.staging-*`` folder behind.
"""

import os
import stat
from pathlib import Path

import pytest

from hermes_cli.desktop_plugin_halves import (
    INSTALL_ORIGIN,
    PACKAGE_MARKER,
    publish_desktop_tree,
    reconcile_desktop_halves,
)

pytestmark = pytest.mark.platforms("posix")

needs_permission_checks = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0,
    reason="root ignores folder write bits",
)


def _make_read_only(folder: Path) -> None:
    for path, dirs, files in os.walk(folder, topdown=False):
        for name in files:
            os.chmod(Path(path) / name, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        os.chmod(
            path,
            stat.S_IRUSR
            | stat.S_IXUSR
            | stat.S_IRGRP
            | stat.S_IXGRP
            | stat.S_IROTH
            | stat.S_IXOTH,
        )


def _restore_writable(folder: Path) -> None:
    for path, dirs, files in os.walk(folder):
        os.chmod(path, stat.S_IRWXU)
        for name in files:
            os.chmod(Path(path) / name, stat.S_IRUSR | stat.S_IWUSR)


@pytest.fixture
def read_only_store(tmp_path):
    store = tmp_path / "store" / "media"
    (store / "desktop" / "assets").mkdir(parents=True)
    (store / "plugin.yaml").write_text("name: media\n", encoding="utf-8")
    (store / "desktop" / "plugin.js").write_text("export default {}", encoding="utf-8")
    (store / "desktop" / "assets" / "icon.svg").write_text("<svg/>", encoding="utf-8")
    _make_read_only(store)
    yield store
    _restore_writable(tmp_path / "store")
    for leftover in (
        (tmp_path / "hermes").rglob("*") if (tmp_path / "hermes").exists() else ()
    ):
        if leftover.is_dir() and not leftover.is_symlink():
            os.chmod(leftover, stat.S_IRWXU)


def _staging_leftovers(app_root: Path) -> list[str]:
    return sorted(p.name for p in app_root.iterdir() if ".staging-" in p.name)


@needs_permission_checks
def test_a_read_only_package_publishes_its_desktop_half_without_leaking_staging(
    tmp_path, read_only_store
):
    root, app_root = tmp_path / "hermes", tmp_path / "hermes" / "desktop-plugins"
    (root / "plugins").mkdir(parents=True)
    (root / "plugins" / "media").symlink_to(read_only_store, target_is_directory=True)

    for _ in range(3):
        reconcile_desktop_halves(root, app_root)

    assert (app_root / "media" / "plugin.js").read_text(
        encoding="utf-8"
    ) == "export default {}"
    assert (app_root / "media" / PACKAGE_MARKER).is_file()
    assert (app_root / "media" / "assets" / "icon.svg").read_text(
        encoding="utf-8"
    ) == "<svg/>"
    assert _staging_leftovers(app_root) == []


@needs_permission_checks
def test_publishing_a_read_only_tree_twice_replaces_the_copy_and_cleans_up(
    tmp_path, read_only_store
):
    app_root = tmp_path / "hermes" / "desktop-plugins"
    marker = {
        "package": "media",
        "source": str(read_only_store / "desktop"),
        "sourceMtimeMs": 1,
    }

    publish_desktop_tree(read_only_store / "desktop", app_root / "media", marker)
    publish_desktop_tree(
        read_only_store / "desktop", app_root / "media", None, origin={"repo": "x/y"}
    )

    assert not (app_root / "media" / PACKAGE_MARKER).exists()
    assert (app_root / "media" / INSTALL_ORIGIN).is_file()
    assert _staging_leftovers(app_root) == []
