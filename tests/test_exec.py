import asyncio
from pathlib import Path

from servers.exec.server import run_command


def test_runs_and_reports_exit_and_output(tmp_path: Path) -> None:
    out = asyncio.run(run_command("echo hello", str(tmp_path)))
    assert out == "(exit 0)\nhello"


def test_reports_nonzero_exit(tmp_path: Path) -> None:
    out = asyncio.run(run_command("exit 3", str(tmp_path)))
    assert out.startswith("(exit 3)")


def test_runs_in_the_configured_root(tmp_path: Path) -> None:
    (tmp_path / "marker.txt").write_text("x")
    out = asyncio.run(run_command("ls", str(tmp_path)))
    assert "marker.txt" in out


def test_timeout_kills_the_command(tmp_path: Path) -> None:
    out = asyncio.run(run_command("sleep 5", str(tmp_path), timeout=0.2))
    assert "timed out" in out
