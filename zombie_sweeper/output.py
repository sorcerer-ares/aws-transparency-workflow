"""Output formatters — Rich tables, JSON, and Markdown for Switch agent chat."""

from __future__ import annotations

import json
from collections import defaultdict

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from zombie_sweeper.dependency_graph import get_phase_label
from zombie_sweeper.models import (
    DestroyPlan,
    DiscoveredResource,
    PhaseResult,
    ResourceStatus,
)

# Status → emoji mapping
_STATUS_EMOJI: dict[str, str] = {
    "active": "🟢",
    "orphaned": "🔴",
    "stopped": "🟡",
    "idle": "🟠",
    "protected": "🛡️",
}


def _status_display(status: ResourceStatus) -> str:
    emoji = _STATUS_EMOJI.get(status.value, "⚪")
    return f"{emoji} {status.value}"


# ---------------------------------------------------------------------------
# Rich table output (CLI terminal)
# ---------------------------------------------------------------------------

def render_scan_table(
    resources: list[DiscoveredResource],
    console: Console | None = None,
) -> None:
    """Print a region-grouped cost breakdown table using Rich."""
    if console is None:
        console = Console()

    by_region: dict[str, list[DiscoveredResource]] = defaultdict(list)
    for r in resources:
        by_region[r.region].append(r)

    grand_total = 0.0

    for region in sorted(by_region):
        region_resources = by_region[region]
        table = Table(title=f"🌍 {region}", show_lines=False, expand=True)
        table.add_column("Resource ID", style="cyan", no_wrap=True)
        table.add_column("Type", style="magenta")
        table.add_column("Name", style="white", max_width=30)
        table.add_column("Status", style="bold")
        table.add_column("$/month", justify="right", style="green")

        region_total = 0.0
        for r in sorted(region_resources, key=lambda x: -x.cost_monthly):
            cost = r.cost_monthly
            region_total += cost
            table.add_row(
                r.resource_id,
                r.display_type,
                r.name or "—",
                _status_display(r.status),
                f"${cost:,.2f}",
            )

        table.add_section()
        table.add_row("", "", "", Text("TOTAL", style="bold"), Text(f"${region_total:,.2f}", style="bold green"))
        grand_total += region_total
        console.print(table)
        console.print()

    console.print(
        Panel(
            f"[bold]💰 Grand total estimated monthly spend: [green]${grand_total:,.2f}[/green][/bold]\n"
            f"[dim]{len(resources)} resources across {len(by_region)} region(s)[/dim]",
            title="Summary",
            border_style="blue",
        )
    )


# ---------------------------------------------------------------------------
# Destroy plan output (Rich)
# ---------------------------------------------------------------------------

def render_destroy_plan(
    plan: DestroyPlan,
    console: Console | None = None,
) -> None:
    """Print a terraform-style destroy plan."""
    if console is None:
        console = Console()

    phase_emojis = ["🔴", "🟠", "🟡", "🟢"]

    # Group plan resources by phase
    id_to_resource = {r.resource_id: r for r in plan.resources}

    console.print()
    console.print(
        Panel(
            "[bold white]ZOMBIE SWEEPER — DESTROY PLAN[/bold white]",
            border_style="red",
            expand=True,
        )
    )

    for phase_idx, phase_ids in enumerate(plan.execution_phases):
        emoji = phase_emojis[phase_idx % len(phase_emojis)]
        label = get_phase_label(phase_idx)

        table = Table(
            title=f"{emoji} Phase {phase_idx + 1}: {label} ({len(phase_ids)} resources)",
            show_lines=False,
            expand=True,
        )
        table.add_column("Resource ID", style="cyan", no_wrap=True)
        table.add_column("Type", style="magenta")
        table.add_column("Name", style="white", max_width=28)
        table.add_column("Region", style="blue")
        table.add_column("Status")
        table.add_column("$/month", justify="right", style="green")

        for rid in phase_ids:
            r = id_to_resource.get(rid)
            if r:
                table.add_row(
                    r.resource_id,
                    r.display_type,
                    r.name or "—",
                    r.region,
                    _status_display(r.status),
                    f"${r.cost_monthly:,.2f}",
                )

        console.print(table)
        console.print()

    # Protected resources
    if plan.protected_resources:
        console.print(
            f"[bold]🛡️ Protected ({len(plan.protected_resources)} resources — will NOT be deleted):[/bold]"
        )
        for r in plan.protected_resources:
            reason = ""
            if r.metadata.get("deletion_protection"):
                reason = " [yellow](DeletionProtection — manual intervention required)[/yellow]"
            console.print(
                f"  • {r.resource_id} ({r.display_type}, {r.region}){reason}"
            )
        console.print()

    console.print(
        Panel(
            f"[bold]💰 Total estimated monthly savings: [green]${plan.total_monthly_savings:,.2f}[/green][/bold]\n\n"
            f"Run [bold cyan]zombie-sweeper apply-destroy --confirm[/bold cyan] to execute.",
            border_style="green",
        )
    )


# ---------------------------------------------------------------------------
# Execution results (Rich)
# ---------------------------------------------------------------------------

def render_execution_results(
    results: list[PhaseResult],
    console: Console | None = None,
) -> None:
    """Print phase-by-phase execution results."""
    if console is None:
        console = Console()

    total_ok = sum(len(p.succeeded) for p in results)
    total_fail = sum(len(p.failed) for p in results)
    total_skip = sum(len(p.skipped) for p in results)

    for pr in results:
        label = get_phase_label(pr.phase - 1)
        console.print(f"\n[bold]Phase {pr.phase} — {label}[/bold]")
        for rid in pr.succeeded:
            console.print(f"  ✅ {rid}")
        for f in pr.failed:
            console.print(f"  ❌ {f['id']}: {f['error']}")
        for rid in pr.skipped:
            console.print(f"  ⏭️  {rid} (skipped)")

    console.print(
        Panel(
            f"[bold green]✅ Succeeded: {total_ok}[/bold green]  "
            f"[bold red]❌ Failed: {total_fail}[/bold red]  "
            f"[dim]⏭️ Skipped: {total_skip}[/dim]",
            title="Execution Summary",
            border_style="blue",
        )
    )


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------

def render_json(resources: list[DiscoveredResource]) -> str:
    """Serialize resources to pretty-printed JSON."""
    return json.dumps(
        [r.model_dump(mode="json") for r in resources],
        indent=2,
        default=str,
    )


def render_plan_json(plan: DestroyPlan) -> str:
    """Serialize a destroy plan to pretty-printed JSON."""
    return json.dumps(plan.model_dump(mode="json"), indent=2, default=str)


# ---------------------------------------------------------------------------
# Markdown table (for Switch agent chat)
# ---------------------------------------------------------------------------

def render_markdown_table(resources: list[DiscoveredResource]) -> str:
    """Render a Markdown table suitable for chat output."""
    lines = [
        "| Resource ID | Type | Region | Status | $/month |",
        "|-------------|------|--------|--------|--------:|",
    ]
    for r in sorted(resources, key=lambda x: -x.cost_monthly):
        cost = f"${r.cost_monthly:,.2f}" if r.cost else "—"
        status = _STATUS_EMOJI.get(r.status.value, "") + " " + r.status.value
        lines.append(
            f"| `{r.resource_id}` | {r.display_type} | {r.region} | {status} | {cost} |"
        )
    return "\n".join(lines)


def render_plan_markdown(plan: DestroyPlan) -> str:
    """Render a destroy plan as Markdown for Switch agent chat."""
    lines = ["## 🧟 Zombie Sweeper — Destroy Plan\n"]

    id_to_resource = {r.resource_id: r for r in plan.resources}

    for phase_idx, phase_ids in enumerate(plan.execution_phases):
        label = get_phase_label(phase_idx)
        lines.append(f"### Phase {phase_idx + 1}: {label}\n")
        lines.append("| Resource ID | Type | Region | $/month |")
        lines.append("|-------------|------|--------|--------:|")
        for rid in phase_ids:
            r = id_to_resource.get(rid)
            if r:
                lines.append(
                    f"| `{r.resource_id}` | {r.display_type} | {r.region} | ${r.cost_monthly:,.2f} |"
                )
        lines.append("")

    if plan.protected_resources:
        lines.append("### 🛡️ Protected (will NOT be deleted)\n")
        for r in plan.protected_resources:
            note = " ⚠️ DeletionProtection — manual intervention required" if r.metadata.get("deletion_protection") else ""
            lines.append(f"- `{r.resource_id}` ({r.display_type}, {r.region}){note}")
        lines.append("")

    lines.append(f"**💰 Total estimated monthly savings: ${plan.total_monthly_savings:,.2f}**\n")
    lines.append('> Type `CONFIRM DESTROY` to execute this plan.')

    return "\n".join(lines)
