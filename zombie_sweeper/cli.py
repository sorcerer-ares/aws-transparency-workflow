"""Click CLI — ``zombie-sweeper scan``, ``plan-destroy``, ``apply-destroy``."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from zombie_sweeper.classifier import classify_resources
from zombie_sweeper.cost_mapper import attach_costs
from zombie_sweeper.destroyer import apply_log_retention, execute_plan
from zombie_sweeper.guardrails import apply_guardrails, build_protection_set
from zombie_sweeper.inventory import scan_all_regions
from zombie_sweeper.models import DestroyPlan, DiscoveredResource, ResourceType
from zombie_sweeper.output import (
    render_destroy_plan,
    render_execution_results,
    render_json,
    render_markdown_table,
    render_plan_json,
    render_plan_markdown,
    render_scan_table,
)
from zombie_sweeper.planner import generate_plan
from zombie_sweeper.utils import setup_logging

console = Console()

DEFAULT_PLAN_PATH = Path(
    os.environ.get("ZOMBIE_SWEEPER_PLAN_PATH", "/tmp/zombie_sweeper_last_plan.json")
)

# Module-level cache so ``plan-destroy`` and ``apply-destroy`` can share state in same session
_last_scan: list[DiscoveredResource] = []
_last_plan: DestroyPlan | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_regions(all_regions: bool, regions: str | None) -> list[str] | None:
    """Return an explicit region list, or ``None`` for all enabled regions."""
    if all_regions:
        return None  # scan_all_regions will auto-discover
    if regions:
        return [r.strip() for r in regions.split(",") if r.strip()]
    # Default: only the caller's configured region
    return None


def _run_scan(
    all_regions: bool,
    regions: str | None,
    use_cost_explorer: bool,
    protect: tuple[str, ...],
) -> list[DiscoveredResource]:
    """Execute the full scan → classify → cost → guardrail pipeline."""
    global _last_scan  # noqa: PLW0603

    region_list = _parse_regions(all_regions, regions)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("🔍 Scanning AWS regions…", total=None)

        resources = scan_all_regions(regions=region_list)
        progress.update(task, description=f"🔍 Discovered {len(resources)} resources")

        progress.update(task, description="🏷️  Classifying resources…")
        classify_resources(resources)

        progress.update(task, description="💰 Estimating costs…")
        attach_costs(resources, use_cost_explorer=use_cost_explorer)

        progress.update(task, description="🛡️  Applying guardrails…")
        protection_set = build_protection_set(list(protect) if protect else None)
        apply_guardrails(resources, protection_set)

        progress.update(task, description="✅ Scan complete")

    _last_scan = resources
    return resources


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
@click.option("--profile", default=None, help="AWS profile name (sets AWS_PROFILE).")
@click.option(
    "--protect",
    multiple=True,
    help="Resource IDs to protect from deletion (repeatable).",
)
@click.option("-v", "--verbose", count=True, help="Increase log verbosity (-v info, -vv debug).")
@click.pass_context
def cli(ctx: click.Context, profile: str | None, protect: tuple[str, ...], verbose: int) -> None:
    """🧟 Zombie Sweeper — AWS Resource & Cost Sweeper."""
    ctx.ensure_object(dict)
    ctx.obj["profile"] = profile
    ctx.obj["protect"] = protect
    ctx.obj["verbose"] = verbose

    if profile:
        import os
        os.environ["AWS_PROFILE"] = profile

    setup_logging(verbose)


# ---------------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--all-regions", is_flag=True, help="Scan all enabled AWS regions.")
@click.option("--regions", default=None, help="Comma-separated region list.")
@click.option(
    "--use-cost-explorer",
    is_flag=True,
    help="Query AWS Cost Explorer for actual costs (incurs CE API charges).",
)
@click.option(
    "--output",
    "output_fmt",
    type=click.Choice(["table", "json", "markdown"]),
    default="table",
    show_default=True,
    help="Output format.",
)
@click.pass_context
def scan(
    ctx: click.Context,
    all_regions: bool,
    regions: str | None,
    use_cost_explorer: bool,
    output_fmt: str,
) -> None:
    """Scan AWS regions for billable resources."""
    protect = ctx.obj.get("protect", ())
    resources = _run_scan(all_regions, regions, use_cost_explorer, protect)

    if not resources:
        console.print("[yellow]No billable resources found.[/yellow]")
        return

    if output_fmt == "json":
        click.echo(render_json(resources))
    elif output_fmt == "markdown":
        click.echo(render_markdown_table(resources))
    else:
        render_scan_table(resources, console)


# ---------------------------------------------------------------------------
# plan-destroy
# ---------------------------------------------------------------------------

@cli.command(name="plan-destroy")
@click.option("--all-regions", is_flag=True, help="Target all enabled regions.")
@click.option("--regions", default=None, help="Comma-separated region list.")
@click.option("--ids", default=None, help="Comma-separated resource IDs to target.")
@click.option("--nuke", is_flag=True, help="Target ALL billable resources (dangerous).")
@click.option("--orphans-only", is_flag=True, help="Target only orphaned/idle/stopped resources.")
@click.option(
    "--use-cost-explorer",
    is_flag=True,
    help="Query AWS Cost Explorer for actual costs.",
)
@click.option(
    "--output",
    "output_fmt",
    type=click.Choice(["table", "json", "markdown"]),
    default="table",
    show_default=True,
)
@click.pass_context
def plan_destroy(
    ctx: click.Context,
    all_regions: bool,
    regions: str | None,
    ids: str | None,
    nuke: bool,
    orphans_only: bool,
    use_cost_explorer: bool,
    output_fmt: str,
) -> None:
    """Generate a terraform-style destroy plan."""
    global _last_plan  # noqa: PLW0603

    protect = ctx.obj.get("protect", ())
    resources = _run_scan(all_regions, regions, use_cost_explorer, protect)

    target_ids = [i.strip() for i in ids.split(",") if i.strip()] if ids else None
    target_regions = _parse_regions(all_regions, regions)

    plan = generate_plan(
        resources,
        target_ids=target_ids,
        target_regions=target_regions,
        nuke_mode=nuke,
        orphans_only=orphans_only,
    )
    _last_plan = plan

    # Persist the plan to disk so a subsequent apply-destroy process can load it
    try:
        DEFAULT_PLAN_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_PLAN_PATH.write_text(render_plan_json(plan))
    except Exception:
        pass

    if not plan.resources:
        console.print("[yellow]No resources matched the destroy criteria.[/yellow]")
        return

    if output_fmt == "json":
        click.echo(render_plan_json(plan))
    elif output_fmt == "markdown":
        click.echo(render_plan_markdown(plan))
    else:
        render_destroy_plan(plan, console)


# ---------------------------------------------------------------------------
# apply-destroy
# ---------------------------------------------------------------------------

@cli.command(name="apply-destroy")
@click.option(
    "--confirm",
    is_flag=True,
    help="Explicit confirmation — required to execute in non-interactive mode.",
)
@click.option(
    "--plan-file",
    default=None,
    type=click.Path(exists=True),
    help="Path to a saved plan JSON file.",
)
@click.option(
    "--set-log-retention",
    is_flag=True,
    help="Set CloudWatch Log Group retention to 7 days.",
)
def apply_destroy(
    confirm: bool,
    plan_file: str | None,
    set_log_retention: bool,
) -> None:
    """Execute a previously generated destroy plan.

    Requires ``--confirm`` or terminal confirmation, and a prior ``plan-destroy`` or ``--plan-file``.
    """
    global _last_plan  # noqa: PLW0603

    plan = _last_plan

    if plan_file:
        with open(plan_file) as f:
            data = json.load(f)
        plan = DestroyPlan.model_validate(data)
    elif plan is None and DEFAULT_PLAN_PATH.exists():
        try:
            with open(DEFAULT_PLAN_PATH) as f:
                data = json.load(f)
            plan = DestroyPlan.model_validate(data)
        except Exception as exc:
            console.print(f"[red]Failed to load cached plan from {DEFAULT_PLAN_PATH}: {exc}[/red]")
            sys.exit(1)

    if plan is None or not plan.resources:
        console.print(
            "[red]No destroy plan found.  Run 'plan-destroy' first or pass --plan-file.[/red]"
        )
        sys.exit(1)

    # Confirmation check
    if not confirm:
        console.print(
            f"\n[bold red]⚠️  About to destroy {len(plan.resources)} resources "
            f"(est. savings: ${plan.total_monthly_savings:,.2f}/mo).[/bold red]"
        )
        if sys.stdin and sys.stdin.isatty():
            answer = console.input("[bold]Type 'CONFIRM DESTROY' to proceed: [/bold]")
            if answer.strip() != "CONFIRM DESTROY":
                console.print("[yellow]Aborted.[/yellow]")
                sys.exit(0)
        else:
            console.print("[red]Execution aborted: --confirm flag is required in non-interactive mode.[/red]")
            sys.exit(1)

    # Flip dry_run and execute
    plan.dry_run = False

    def _progress(rid: str, success: bool, error: str | None) -> None:
        if success:
            console.print(f"  ✅ Deleted: {rid}")
        else:
            console.print(f"  ❌ Failed:  {rid} — {error}")

    results = execute_plan(plan, progress_callback=_progress)
    render_execution_results(results, console)

    # Optionally set CW log retention
    if set_log_retention:
        console.print("\n[bold]📋 Setting CloudWatch Log Group retention to 7 days…[/bold]")
        candidate_cw = [
            r for r in (_last_scan or plan.protected_resources or [])
            if r.resource_type == ResourceType.CW_LOG_GROUP
        ]
        if not candidate_cw:
            from zombie_sweeper.scanners.cloudwatch import scan_log_groups
            target_regions = list({r.region for r in plan.resources})
            for reg in target_regions:
                try:
                    candidate_cw.extend(scan_log_groups(reg))
                except Exception:
                    pass

        log_results = apply_log_retention(candidate_cw, retention_days=7)
        ok = sum(1 for v in log_results.values() if v)
        fail = sum(1 for v in log_results.values() if not v)
        console.print(f"  ✅ Updated: {ok}  ❌ Failed: {fail}")

    # Clean up cached plan file after execution
    if DEFAULT_PLAN_PATH.exists() and not plan_file:
        try:
            DEFAULT_PLAN_PATH.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# set-log-retention (standalone)
# ---------------------------------------------------------------------------

@cli.command(name="set-log-retention")
@click.option("--all-regions", is_flag=True, help="Scan all enabled regions.")
@click.option("--regions", default=None, help="Comma-separated region list.")
@click.option(
    "--days", default=7, show_default=True, help="Retention period in days."
)
@click.pass_context
def set_log_retention_cmd(
    ctx: click.Context,
    all_regions: bool,
    regions: str | None,
    days: int,
) -> None:
    """Set CloudWatch Log Group retention policy to reduce storage costs."""
    protect = ctx.obj.get("protect", ())
    resources = _run_scan(all_regions, regions, False, protect)

    from zombie_sweeper.models import ResourceType

    log_groups = [r for r in resources if r.resource_type == ResourceType.CW_LOG_GROUP]
    if not log_groups:
        console.print("[yellow]No CloudWatch Log Groups found.[/yellow]")
        return

    console.print(
        f"[bold]📋 Setting retention to {days} days on {len(log_groups)} log group(s)…[/bold]"
    )
    results = apply_log_retention(resources, retention_days=days)

    ok = sum(1 for v in results.values() if v)
    fail = sum(1 for v in results.values() if not v)
    console.print(f"  ✅ Updated: {ok}  ❌ Failed: {fail}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Package entry point."""
    cli(obj={})


if __name__ == "__main__":
    main()
