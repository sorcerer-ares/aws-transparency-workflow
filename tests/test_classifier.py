"""Tests for resource classification."""

from zombie_sweeper.classifier import classify_resources
from zombie_sweeper.models import DiscoveredResource, ResourceStatus, ResourceType


def test_classify_ec2_states():
    running = DiscoveredResource(
        resource_id="i-run",
        resource_type=ResourceType.EC2_INSTANCE,
        region="us-east-1",
        metadata={"state": "running"},
    )
    stopped = DiscoveredResource(
        resource_id="i-stop",
        resource_type=ResourceType.EC2_INSTANCE,
        region="us-east-1",
        metadata={"state": "stopped"},
    )
    resources = [running, stopped]
    classify_resources(resources)

    assert running.status == ResourceStatus.ACTIVE
    assert stopped.status == ResourceStatus.STOPPED


def test_classify_ebs_attachments():
    attached = DiscoveredResource(
        resource_id="vol-attached",
        resource_type=ResourceType.EBS_VOLUME,
        region="us-east-1",
        metadata={"attachments": ["i-run"]},
    )
    detached = DiscoveredResource(
        resource_id="vol-detached",
        resource_type=ResourceType.EBS_VOLUME,
        region="us-east-1",
        metadata={"attachments": []},
    )
    resources = [attached, detached]
    classify_resources(resources)

    assert attached.status == ResourceStatus.ACTIVE
    assert detached.status == ResourceStatus.ORPHANED


def test_classify_snapshot_source_volume():
    existing_vol = DiscoveredResource(
        resource_id="vol-100",
        resource_type=ResourceType.EBS_VOLUME,
        region="us-east-1",
        metadata={"attachments": ["i-run"]},
    )
    snap_valid = DiscoveredResource(
        resource_id="snap-valid",
        resource_type=ResourceType.EBS_SNAPSHOT,
        region="us-east-1",
        metadata={"volume_id": "vol-100"},
    )
    snap_orphan = DiscoveredResource(
        resource_id="snap-orphan",
        resource_type=ResourceType.EBS_SNAPSHOT,
        region="us-east-1",
        metadata={"volume_id": "vol-deleted"},
    )
    resources = [existing_vol, snap_valid, snap_orphan]
    classify_resources(resources)

    assert snap_valid.status == ResourceStatus.ACTIVE
    assert snap_orphan.status == ResourceStatus.ORPHANED


def test_classify_rds_deletion_protection():
    rds_protected = DiscoveredResource(
        resource_id="db-prod",
        resource_type=ResourceType.RDS_INSTANCE,
        region="us-east-1",
        metadata={"deletion_protection": True, "db_instance_status": "available"},
    )
    rds_stopped = DiscoveredResource(
        resource_id="db-dev",
        resource_type=ResourceType.RDS_INSTANCE,
        region="us-east-1",
        metadata={"deletion_protection": False, "db_instance_status": "stopped"},
    )
    resources = [rds_protected, rds_stopped]
    classify_resources(resources)

    assert rds_protected.status == ResourceStatus.PROTECTED
    assert rds_stopped.status == ResourceStatus.STOPPED
