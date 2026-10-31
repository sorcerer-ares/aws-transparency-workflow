"""Tests for output formatters (JSON, Markdown, Rich table)."""

import json
from zombie_sweeper.models import CostEstimate, DiscoveredResource, ResourceStatus, ResourceType
from zombie_sweeper.output import render_json, render_markdown_table, render_plan_markdown
from zombie_sweeper.planner import generate_plan


def test_render_json():
    r = DiscoveredResource(
        resource_id="i-test",
        resource_type=ResourceType.EC2_INSTANCE,
        region="us-east-1",
        status=ResourceStatus.ACTIVE,
        cost=CostEstimate(monthly_usd=10.0),
    )
    json_str = render_json([r])
    data = json.loads(json_str)
    assert len(data) == 1
    assert data[0]["resource_id"] == "i-test"
    assert data[0]["cost"]["monthly_usd"] == 10.0


def test_render_markdown_table():
    r = DiscoveredResource(
        resource_id="vol-orphan",
        resource_type=ResourceType.EBS_VOLUME,
        region="us-west-2",
        status=ResourceStatus.ORPHANED,
        cost=CostEstimate(monthly_usd=8.0),
    )
    md = render_markdown_table([r])
    assert "| `vol-orphan` | EBS Volume | us-west-2 | 🔴 orphaned | $8.00 |" in md


def test_render_plan_markdown():
    r = DiscoveredResource(
        resource_id="vol-orphan",
        resource_type=ResourceType.EBS_VOLUME,
        region="us-west-2",
        status=ResourceStatus.ORPHANED,
        cost=CostEstimate(monthly_usd=8.0),
    )
    plan = generate_plan([r], nuke_mode=True)
    md = render_plan_markdown(plan)
    assert "Zombie Sweeper — Destroy Plan" in md
    assert "vol-orphan" in md
    assert "CONFIRM DESTROY" in md
