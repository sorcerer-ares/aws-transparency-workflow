"""Tests for dependency ordering and phase execution planning."""

from zombie_sweeper.dependency_graph import build_execution_phases, get_phase_label, get_phase_wait_time
from zombie_sweeper.models import DiscoveredResource, ResourceStatus, ResourceType


def test_dependency_phases_ordering():
    ec2 = DiscoveredResource(
        resource_id="i-1",
        resource_type=ResourceType.EC2_INSTANCE,
        region="us-east-1",
        status=ResourceStatus.ACTIVE,
    )
    rds = DiscoveredResource(
        resource_id="db-1",
        resource_type=ResourceType.RDS_INSTANCE,
        region="us-east-1",
        status=ResourceStatus.ACTIVE,
    )
    alb = DiscoveredResource(
        resource_id="arn:aws:elasticloadbalancing:us-east-1:1:loadbalancer/app/alb-1/1",
        resource_type=ResourceType.ALB,
        region="us-east-1",
        status=ResourceStatus.ACTIVE,
    )
    nat = DiscoveredResource(
        resource_id="nat-1",
        resource_type=ResourceType.NAT_GATEWAY,
        region="us-east-1",
        status=ResourceStatus.ACTIVE,
    )
    ebs = DiscoveredResource(
        resource_id="vol-orphan",
        resource_type=ResourceType.EBS_VOLUME,
        region="us-east-1",
        status=ResourceStatus.ORPHANED,
    )
    eip = DiscoveredResource(
        resource_id="eipalloc-orphan",
        resource_type=ResourceType.ELASTIC_IP,
        region="us-east-1",
        status=ResourceStatus.ORPHANED,
    )
    s3 = DiscoveredResource(
        resource_id="my-s3-bucket",
        resource_type=ResourceType.S3_BUCKET,
        region="us-east-1",
        status=ResourceStatus.ACTIVE,
    )
    protected = DiscoveredResource(
        resource_id="i-self",
        resource_type=ResourceType.EC2_INSTANCE,
        region="us-east-1",
        status=ResourceStatus.PROTECTED,
    )

    resources = [ebs, alb, ec2, s3, rds, nat, eip, protected]
    phases = build_execution_phases(resources)

    # Protected resources and S3 buckets must be excluded
    all_phased_ids = [r.resource_id for phase in phases for r in phase]
    assert "i-self" not in all_phased_ids
    assert "my-s3-bucket" not in all_phased_ids

    # Phase 1: Compute (ec2, rds)
    phase1_ids = {r.resource_id for r in phases[0]}
    assert phase1_ids == {"i-1", "db-1"}

    # Phase 2: Networking (alb, nat)
    phase2_ids = {r.resource_id for r in phases[1]}
    assert "nat-1" in phase2_ids
    assert alb.resource_id in phase2_ids

    # Phase 3: Detached (ebs, eip)
    phase3_ids = {r.resource_id for r in phases[2]}
    assert phase3_ids == {"vol-orphan", "eipalloc-orphan"}


def test_phase_wait_time_and_labels():
    assert get_phase_wait_time(0) == 60
    assert get_phase_wait_time(1) == 30
    assert "Compute" in get_phase_label(0)
    assert "Networking" in get_phase_label(1)
