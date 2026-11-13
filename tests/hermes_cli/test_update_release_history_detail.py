"""The release-history warning in ``hermes update`` must name the file git refused (#154940).

git's lock-file failure spans several lines and puts the path on the first one
(``fatal: Unable to create '.../shallow.lock': File exists.``); the last line is
the generic ``remove the file manually to continue.``. Keeping only the last line
told the user to remove a file without saying which one.
"""
import subprocess

import pytest

from hermes_cli.update_cmd_maint import _git_failure_detail


def _git(*args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def shallow_clone_with_stale_lock(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _git("init", "-q", cwd=src)
    for n in range(3):
        _git("-c", "user.email=t@example.com", "-c", "user.name=t",
             "commit", "-q", "--allow-empty", "-m", f"c{n}", cwd=src)
    _git("tag", "v1.0.0", cwd=src)
    dst = tmp_path / "dst"
    _git("clone", "-q", "--depth", "1", src.as_uri(), str(dst), cwd=tmp_path)
    lock = dst / ".git" / "shallow.lock"
    lock.touch()
    return dst, lock


def test_lock_failure_detail_names_the_lock_file(shallow_clone_with_stale_lock):
    dst, lock = shallow_clone_with_stale_lock
    with pytest.raises(subprocess.CalledProcessError) as excinfo:
        subprocess.run(
            ["git", "fetch", "--quiet", "--unshallow", "--no-tags", "origin",
             "refs/tags/v*:refs/tags/v*"],
            cwd=dst, check=True, capture_output=True, text=True,
        )
    detail = _git_failure_detail(excinfo.value)
    assert str(lock) in detail
    assert detail.startswith("fatal:")


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (subprocess.CalledProcessError(1, ["git"], stderr="warning: noise\nerror: bad ref\nhint: retry\n"),
         "error: bad ref"),
        (subprocess.CalledProcessError(1, ["git"], stderr="first\nlast line\n"), "last line"),
        (subprocess.TimeoutExpired(["git"], 5), "timed out after 5 seconds"),
        (OSError("git not found"), "git not found"),
        (OSError(), "OSError"),
    ],
)
def test_detail_falls_back_to_the_last_line_or_the_exception(exc, expected):
    assert expected in _git_failure_detail(exc)
