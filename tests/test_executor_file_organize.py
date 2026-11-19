"""Tests for the file_organize executor."""
import os
from pathlib import Path

import pytest

from app.executors.file_organize import execute, plan


@pytest.fixture()
def tmpdir(tmp_path):
    return tmp_path


def _make_files(base: Path, names: list[str]) -> None:
    for name in names:
        (base / name).write_text(name)


def test_plan_groups_by_extension(tmpdir):
    _make_files(tmpdir, ["a.py", "b.py", "c.txt", "d.md"])
    moves = plan({"directory": str(tmpdir), "grouping": "by_extension"})
    srcs = {Path(m["src"]).name for m in moves}
    assert srcs == {"a.py", "b.py", "c.txt", "d.md"}
    # destinations should land in extension subfolders
    for m in moves:
        dst = Path(m["dst"])
        ext = Path(m["src"]).suffix.lstrip(".")
        assert dst.parent.name == ext


def test_plan_empty_directory(tmpdir):
    moves = plan({"directory": str(tmpdir), "grouping": "by_extension"})
    assert moves == []


def test_plan_no_extension(tmpdir):
    _make_files(tmpdir, ["Makefile", "README"])
    moves = plan({"directory": str(tmpdir), "grouping": "by_extension"})
    for m in moves:
        assert Path(m["dst"]).parent.name == "no_extension"


def test_execute_moves_files(tmpdir):
    _make_files(tmpdir, ["x.py", "y.txt"])
    payload = {"directory": str(tmpdir), "grouping": "by_extension"}
    plan_steps = plan(payload)
    payload["plan"] = plan_steps
    result = execute(payload)
    assert result.status == "success"
    assert (tmpdir / "py" / "x.py").exists()
    assert (tmpdir / "txt" / "y.txt").exists()


def test_execute_failure_on_existing_destination(tmpdir):
    _make_files(tmpdir, ["z.py"])
    # pre-create the destination
    (tmpdir / "py").mkdir()
    (tmpdir / "py" / "z.py").write_text("already here")
    payload = {"directory": str(tmpdir), "grouping": "by_extension"}
    plan_steps = plan(payload)
    payload["plan"] = plan_steps
    result = execute(payload)
    assert result.status == "failure"
