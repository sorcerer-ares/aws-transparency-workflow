"""Tests for pricing_catalog and cost calculation."""

from zombie_sweeper.models import DiscoveredResource, ResourceStatus, ResourceType
from zombie_sweeper.pricing_catalog import estimate_monthly_cost, REGION_MULTIPLIERS, EC2_PRICES


def test_ec2_pricing_running():
    resource = DiscoveredResource(
        resource_id="i-12345",
        resource_type=ResourceType.EC2_INSTANCE,
        region="us-east-1",
        status=ResourceStatus.ACTIVE,
        metadata={"instance_type": "t3.micro"},
    )
    cost = estimate_monthly_cost(resource)
    assert cost.monthly_usd == EC2_PRICES["t3.micro"]
    assert cost.source == "fallback_estimate"


def test_ec2_pricing_stopped():
    resource = DiscoveredResource(
        resource_id="i-stopped",
        resource_type=ResourceType.EC2_INSTANCE,
        region="us-east-1",
        status=ResourceStatus.STOPPED,
        metadata={"instance_type": "t3.micro"},
    )
    cost = estimate_monthly_cost(resource)
    # Stopped EC2 has 0 compute cost (storage billed on volume)
    assert cost.monthly_usd == 0.0


def test_ebs_volume_pricing():
    resource = DiscoveredResource(
        resource_id="vol-12345",
        resource_type=ResourceType.EBS_VOLUME,
        region="us-east-1",
        status=ResourceStatus.ACTIVE,
        metadata={"volume_type": "gp3", "size_gb": 100},
    )
    cost = estimate_monthly_cost(resource)
    # 100 GB * 0.08 = 8.00
    assert cost.monthly_usd == 8.00


def test_eip_pricing_active_vs_orphaned():
    active_eip = DiscoveredResource(
        resource_id="eip-active",
        resource_type=ResourceType.ELASTIC_IP,
        region="us-east-1",
        status=ResourceStatus.ACTIVE,
        metadata={"association_id": "assoc-123"},
    )
    orphaned_eip = DiscoveredResource(
        resource_id="eip-orphaned",
        resource_type=ResourceType.ELASTIC_IP,
        region="us-east-1",
        status=ResourceStatus.ORPHANED,
        metadata={},
    )
    assert estimate_monthly_cost(active_eip).monthly_usd == 0.0
    assert estimate_monthly_cost(orphaned_eip).monthly_usd == 3.65


def test_nat_gateway_and_alb_pricing():
    nat = DiscoveredResource(
        resource_id="nat-123",
        resource_type=ResourceType.NAT_GATEWAY,
        region="us-east-1",
        status=ResourceStatus.ACTIVE,
    )
    alb = DiscoveredResource(
        resource_id="arn:aws:elasticloadbalancing:us-east-1:123456789012:loadbalancer/app/my-alb/123",
        resource_type=ResourceType.ALB,
        region="us-east-1",
        status=ResourceStatus.ACTIVE,
    )
    assert estimate_monthly_cost(nat).monthly_usd == 32.85
    assert estimate_monthly_cost(alb).monthly_usd == 16.43


def test_regional_multiplier():
    resource = DiscoveredResource(
        resource_id="nat-ap-south-1",
        resource_type=ResourceType.NAT_GATEWAY,
        region="ap-south-1",
        status=ResourceStatus.ACTIVE,
    )
    cost = estimate_monthly_cost(resource)
    # 32.85 * 0.84 = 27.594 -> 27.59
    expected = round(32.85 * REGION_MULTIPLIERS["ap-south-1"], 2)
    assert cost.monthly_usd == expected
