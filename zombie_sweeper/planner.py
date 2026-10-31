"""Terraform-style destroy plan generator.

Builds a ``DestroyPlan`` from scanned resources using the dependency graph
to determine safe execution phases and estimated savings.
"""

from __future__ import annotations

import logging

from zombie_sweeper.dependency_graph import build_execution_phases
from zombie_sweeper.models import (
    DestroyPlan,
    DiscoveredResource,
    ResourceStatus,
    ResourceType,
)

logger = logging.getLogger("zombie_sweeper")

# Resource types excluded from deletion in v1
_NO_DELETE_TYPES: set[ResourceType] = {
    ResourceType.S3_BUCKET,
    ResourceType.CW_LOG_GROUP,
}


def generate_plan(
    resources: list[DiscoveredResource],
    *,
    target_ids: list[str] | None = None,
    target_regions: list[str] | None = None,
    nuke_mode: bool = False,
    orphans_only: bool = False,
) -> DestroyPlan:
    """Generate a destroy plan.

    Modes
    -----
    - **Selective**: ``target_ids`` specified → only those resources.
    - **Region filter**: ``target_regions`` specified → only those regions.
    - **Nuke**: ``nuke_mode=True`` → every deletable resource.
    - **Orphans-only**: ``orphans_only=True`` → only orphaned/idle resources.

    Parameters
    ----------
    resources:
        Full list from ``scan_all_regions()``, already classified and costed.
    target_ids:
        Specific resource IDs to target.
    target_regions:
        Limit to these region(s).
    nuke_mode:
        If ``True``, target everything that isn't protected.
    orphans_only:
        If ``True``, only target resources with status ORPHANED or IDLE.

    Returns
    -------
    DestroyPlan
        Always created with ``dry_run=True`` — caller must flip it to execute.
    """
    candidates = list(resources)

    # ── Filter by target scope ───────────────────────────────────────────
    if target_ids:
        id_set = set(target_ids)
        candidates = [r for r in candidates if r.resource_id in id_set]

    if target_regions:
        region_set = set(target_regions)
        candidates = [r for r in candidates if r.region in region_set]

    if orphans_only:
        candidates = [
            r for r in candidates
            if r.status in (ResourceStatus.ORPHANED, ResourceStatus.IDLE, ResourceStatus.STOPPED)
        ]

    # ── Separate destroyable from protected ──────────────────────────────
    destroyable = [
        r for r in candidates
        if r.status != ResourceStatus.PROTECTED
        and r.resource_type not in _NO_DELETE_TYPES
    ]
    protected = [
        r for r in candidates
        if r.status == ResourceStatus.PROTECTED
        or r.resource_type in _NO_DELETE_TYPES
    ]

    # ── Build phased execution plan ──────────────────────────────────────
    phases = build_execution_phases(destroyable)
    execution_phases = [
        [r.resource_id for r in phase] for phase in phases
    ]

    total_savings = sum(r.cost_monthly for r in destroyable)

    plan = DestroyPlan(
        resources=destroyable,
        total_monthly_savings=round(total_savings, 2),
        execution_phases=execution_phases,
        protected_resources=protected,
        dry_run=True,
    )

    logger.info(
        "Destroy plan: %d resources in %d phases, est. savings $%.2f/mo",
        len(destroyable), len(execution_phases), total_savings,
    )
    return plan
