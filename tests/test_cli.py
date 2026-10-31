"""Tests for CLI commands."""

from unittest.mock import patch
from click.testing import CliRunner
from zombie_sweeper.cli import cli
from zombie_sweeper.models import CostEstimate, DiscoveredResource, ResourceStatus, ResourceType


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Zombie Sweeper" in result.output


def test_cli_scan_mocked():
    runner = CliRunner()
    mock_resources = [
        DiscoveredResource(
            resource_id="vol-test1",
            resource_type=ResourceType.EBS_VOLUME,
            region="us-east-1",
            status=ResourceStatus.ORPHANED,
            cost=CostEstimate(monthly_usd=12.0),
        )
    ]

    with patch("zombie_sweeper.cli._run_scan", return_value=mock_resources):
        # JSON output
        result = runner.invoke(cli, ["scan", "--output", "json"])
        assert result.exit_code == 0
        assert "vol-test1" in result.output

        # Table output
        result_table = runner.invoke(cli, ["scan", "--output", "table"])
        assert result_table.exit_code == 0
        assert "vol-test1" in result_table.output

        # Markdown output
        result_md = runner.invoke(cli, ["scan", "--output", "markdown"])
        assert result_md.exit_code == 0
        assert "vol-test1" in result_md.output


def test_cli_plan_destroy_mocked(tmp_path, monkeypatch):
    test_plan_path = tmp_path / "plan.json"
    monkeypatch.setattr("zombie_sweeper.cli.DEFAULT_PLAN_PATH", test_plan_path)

    runner = CliRunner()
    mock_resources = [
        DiscoveredResource(
            resource_id="vol-test1",
            resource_type=ResourceType.EBS_VOLUME,
            region="us-east-1",
            status=ResourceStatus.ORPHANED,
            cost=CostEstimate(monthly_usd=12.0),
        )
    ]

    with patch("zombie_sweeper.cli._run_scan", return_value=mock_resources):
        result = runner.invoke(cli, ["plan-destroy", "--orphans-only", "--output", "json"])
        assert result.exit_code == 0
        assert "vol-test1" in result.output
        assert "total_monthly_savings" in result.output
        assert test_plan_path.exists()

        result_md = runner.invoke(cli, ["plan-destroy", "--orphans-only", "--output", "markdown"])
        assert result_md.exit_code == 0
        assert "vol-test1" in result_md.output


def test_cli_apply_destroy_cached(tmp_path, monkeypatch):
    test_plan_path = tmp_path / "plan.json"
    monkeypatch.setattr("zombie_sweeper.cli.DEFAULT_PLAN_PATH", test_plan_path)
    monkeypatch.setattr("zombie_sweeper.cli._last_plan", None)

    runner = CliRunner()
    mock_resources = [
        DiscoveredResource(
            resource_id="vol-test1",
            resource_type=ResourceType.EBS_VOLUME,
            region="us-east-1",
            status=ResourceStatus.ORPHANED,
            cost=CostEstimate(monthly_usd=12.0),
        )
    ]

    # Step 1: plan-destroy generates and writes cached plan
    with patch("zombie_sweeper.cli._run_scan", return_value=mock_resources):
        res_plan = runner.invoke(cli, ["plan-destroy", "--orphans-only", "--output", "json"])
        assert res_plan.exit_code == 0

    assert test_plan_path.exists()

    # Step 2: apply-destroy in separate run loads from cached plan without prompt
    from zombie_sweeper.models import PhaseResult
    dummy_results = [PhaseResult(phase=1, succeeded=["vol-test1"])]

    with patch("zombie_sweeper.cli.execute_plan", return_value=dummy_results):
        res_apply = runner.invoke(cli, ["apply-destroy", "--confirm"])
        assert res_apply.exit_code == 0
        assert "vol-test1" in res_apply.output
        assert "Succeeded: 1" in res_apply.output
