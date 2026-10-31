"""Tests for planner module."""

from zombie_sweeper.models import CostEstimate, DiscoveredResource, ResourceStatus, ResourceType
from zombie_sweeper.planner import generate_plan


def test_planner_selective_destroy():
    r1 = DiscoveredResource(
        resource_id="vol-orphan-1",
        resource_type=ResourceType.EBS_VOLUME,
        region="us-east-1",
        status=ResourceStatus.ORPHANED,
        cost=CostEstimate(monthly_usd=10.0),
    )
    r2 = DiscoveredResource(
        resource_id="vol-orphan-2",
        resource_type=ResourceType.EBS_VOLUME,
        region="us-east-1",
        status=ResourceStatus.ORPHANED,
        cost=CostEstimate(monthly_usd=20.0),
    )
    resources = [r1, r2]

    # Target only r1
    plan = generate_plan(resources, target_ids=["vol-orphan-1"])
    assert len(plan.resources) == 1
    assert plan.resources[0].resource_id == "vol-orphan-1"
    assert plan.total_monthly_savings == 10.0
    assert plan.dry_run is True


def test_planner_orphans_only():
    r_active = DiscoveredResource(
        resource_id="i-active",
        resource_type=ResourceType.EC2_INSTANCE,
        region="us-east-1",
        status=ResourceStatus.ACTIVE,
        cost=CostEstimate(monthly_usd=50.0),
    )
    r_orphan = DiscoveredResource(
        resource_id="vol-orphan",
        resource_type=ResourceType.EBS_VOLUME,
        region="us-east-1",
        status=ResourceStatus.ORPHANED,
        cost=CostEstimate(monthly_usd=15.0),
    )
    r_stopped = DiscoveredResource(
        resource_id="i-stopped",
        resource_type=ResourceType.EC2_INSTANCE,
        region="us-east-1",
        status=ResourceStatus.STOPPED,
        cost=CostEstimate(monthly_usd=0.0),
    )

    resources = [r_active, r_orphan, r_stopped]
    plan = generate_plan(resources, orphans_only=True)

    ids = {r.resource_id for r in plan.resources}
    assert ids == {"vol-orphan", "i-stopped"}
    assert plan.total_monthly_savings == 15.0


def test_planner_protected_exclusion():
    r_protected = DiscoveredResource(
        resource_id="i-protected",
        resource_type=ResourceType.EC2_INSTANCE,
        region="us-east-1",
        status=ResourceStatus.PROTECTED,
        cost=CostEstimate(monthly_usd=100.0),
    )
    r_target = DiscoveredResource(
        resource_id="i-normal",
        resource_type=ResourceType.EC2_INSTANCE,
        region="us-east-1",
        status=ResourceStatus.ACTIVE,
        cost=CostEstimate(monthly_usd=50.0),
    )
    resources = [r_protected, r_target]
    plan = generate_plan(resources, nuke_mode=True)

    assert len(plan.resources) == 1
    assert plan.resources[0].resource_id == "i-normal"
    assert len(plan.protected_resources) == 1
    assert plan.protected_resources[0].resource_id == "i-protected"
