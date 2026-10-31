"""EC2 resource scanners — instances, EBS volumes, EBS snapshots, Elastic IPs."""

from __future__ import annotations

import logging

import boto3
from botocore.exceptions import ClientError

from zombie_sweeper.models import DiscoveredResource, ResourceStatus, ResourceType
from zombie_sweeper.utils import get_account_id, get_name_tag

logger = logging.getLogger("zombie_sweeper")


# ---------------------------------------------------------------------------
# EC2 Instances
# ---------------------------------------------------------------------------

def scan_instances(region: str) -> list[DiscoveredResource]:
    """Discover all EC2 instances (running + stopped) in *region*."""
    ec2 = boto3.client("ec2", region_name=region)
    resources: list[DiscoveredResource] = []

    try:
        paginator = ec2.get_paginator("describe_instances")
        for page in paginator.paginate():
            for reservation in page.get("Reservations", []):
                for inst in reservation.get("Instances", []):
                    state = inst["State"]["Name"]
                    if state == "terminated":
                        continue

                    tags = inst.get("Tags", [])
                    volume_ids = [
                        bdm["Ebs"]["VolumeId"]
                        for bdm in inst.get("BlockDeviceMappings", [])
                        if "Ebs" in bdm
                    ]

                    resources.append(DiscoveredResource(
                        resource_id=inst["InstanceId"],
                        resource_type=ResourceType.EC2_INSTANCE,
                        region=region,
                        arn=inst.get("InstanceId"),  # full ARN built if needed
                        name=get_name_tag(tags),
                        status=(
                            ResourceStatus.STOPPED
                            if state == "stopped"
                            else ResourceStatus.ACTIVE
                        ),
                        metadata={
                            "instance_type": inst["InstanceType"],
                            "state": state,
                            "launch_time": inst["LaunchTime"].isoformat(),
                            "vpc_id": inst.get("VpcId"),
                            "subnet_id": inst.get("SubnetId"),
                            "volume_ids": volume_ids,
                            "platform": inst.get("PlatformDetails", "Linux/UNIX"),
                        },
                        created_at=inst["LaunchTime"],
                        dependencies=volume_ids,
                    ))
    except ClientError as exc:
        logger.warning("EC2 describe_instances failed in %s: %s", region, exc)

    return resources


# ---------------------------------------------------------------------------
# EBS Volumes
# ---------------------------------------------------------------------------

def scan_volumes(region: str) -> list[DiscoveredResource]:
    """Discover EBS volumes — detached volumes are flagged as orphaned."""
    ec2 = boto3.client("ec2", region_name=region)
    resources: list[DiscoveredResource] = []

    try:
        paginator = ec2.get_paginator("describe_volumes")
        for page in paginator.paginate():
            for vol in page.get("Volumes", []):
                attachments = vol.get("Attachments", [])
                attached_instances = [a["InstanceId"] for a in attachments]

                resources.append(DiscoveredResource(
                    resource_id=vol["VolumeId"],
                    resource_type=ResourceType.EBS_VOLUME,
                    region=region,
                    name=get_name_tag(vol.get("Tags")),
                    status=(
                        ResourceStatus.ACTIVE if attachments
                        else ResourceStatus.ORPHANED
                    ),
                    metadata={
                        "size_gb": vol["Size"],
                        "volume_type": vol["VolumeType"],
                        "state": vol["State"],
                        "attachments": attached_instances,
                        "iops": vol.get("Iops"),
                        "encrypted": vol.get("Encrypted", False),
                    },
                    created_at=vol["CreateTime"],
                    dependencies=attached_instances,
                ))
    except ClientError as exc:
        logger.warning("EC2 describe_volumes failed in %s: %s", region, exc)

    return resources


# ---------------------------------------------------------------------------
# EBS Snapshots
# ---------------------------------------------------------------------------

def scan_snapshots(region: str) -> list[DiscoveredResource]:
    """Discover EBS snapshots owned by this account."""
    ec2 = boto3.client("ec2", region_name=region)
    resources: list[DiscoveredResource] = []

    try:
        account_id = get_account_id()
        paginator = ec2.get_paginator("describe_snapshots")
        for page in paginator.paginate(OwnerIds=[account_id]):
            for snap in page.get("Snapshots", []):
                desc = snap.get("Description", "")
                name = get_name_tag(snap.get("Tags")) or desc[:80] or None

                resources.append(DiscoveredResource(
                    resource_id=snap["SnapshotId"],
                    resource_type=ResourceType.EBS_SNAPSHOT,
                    region=region,
                    name=name,
                    status=ResourceStatus.ORPHANED,  # classifier refines later
                    metadata={
                        "volume_id": snap.get("VolumeId"),
                        "size_gb": snap["VolumeSize"],
                        "state": snap["State"],
                        "description": desc,
                    },
                    created_at=snap["StartTime"],
                ))
    except ClientError as exc:
        logger.warning("EC2 describe_snapshots failed in %s: %s", region, exc)

    return resources


# ---------------------------------------------------------------------------
# Elastic IPs
# ---------------------------------------------------------------------------

def scan_eips(region: str) -> list[DiscoveredResource]:
    """Discover Elastic IPs — unassociated ones are orphaned and billable."""
    ec2 = boto3.client("ec2", region_name=region)
    resources: list[DiscoveredResource] = []

    try:
        resp = ec2.describe_addresses()
        for addr in resp.get("Addresses", []):
            is_associated = "AssociationId" in addr
            rid = addr.get("AllocationId") or addr.get("PublicIp", "unknown")

            resources.append(DiscoveredResource(
                resource_id=rid,
                resource_type=ResourceType.ELASTIC_IP,
                region=region,
                name=get_name_tag(addr.get("Tags")),
                status=(
                    ResourceStatus.ACTIVE if is_associated
                    else ResourceStatus.ORPHANED
                ),
                metadata={
                    "public_ip": addr.get("PublicIp"),
                    "instance_id": addr.get("InstanceId"),
                    "association_id": addr.get("AssociationId"),
                    "domain": addr.get("Domain"),
                    "network_interface_id": addr.get("NetworkInterfaceId"),
                },
            ))
    except ClientError as exc:
        logger.warning("EC2 describe_addresses failed in %s: %s", region, exc)

    return resources
