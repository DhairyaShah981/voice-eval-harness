"""Smoke tests for the CLI entry point."""

from __future__ import annotations

from typer.testing import CliRunner

from voice_eval_harness import __version__
from voice_eval_harness.cli.app import app

runner = CliRunner()


def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_help_lists_init() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "init" in result.stdout


def test_init_creates_files(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["init", "--provider", "retell"])
    assert result.exit_code == 0, result.stdout
    assert (tmp_path / "voxeval.yaml").exists()
    assert (tmp_path / ".env.example").exists()
    assert (tmp_path / "agents").is_dir()
    yaml_text = (tmp_path / "voxeval.yaml").read_text()
    assert "RETELL_API_KEY" in yaml_text
    assert "name: retell" in yaml_text
