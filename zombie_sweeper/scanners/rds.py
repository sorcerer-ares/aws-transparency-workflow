"""RDS instance scanner."""

from __future__ import annotations

import logging

import boto3
from botocore.exceptions import ClientError

from zombie_sweeper.models import DiscoveredResource, ResourceStatus, ResourceType
from zombie_sweeper.utils import get_name_tag

logger = logging.getLogger("zombie_sweeper")


def scan_instances(region: str) -> list[DiscoveredResource]:
    """Discover RDS DB instances in *region*.

    Instances with ``DeletionProtection`` enabled are marked as PROTECTED
    with a note that manual intervention is required.
    """
    rds = boto3.client("rds", region_name=region)
    resources: list[DiscoveredResource] = []

    try:
        paginator = rds.get_paginator("describe_db_instances")
        for page in paginator.paginate():
            for db in page.get("DBInstances", []):
                db_status = db.get("DBInstanceStatus", "available")
                deletion_prot = db.get("DeletionProtection", False)

                # Determine status
                if deletion_prot:
                    status = ResourceStatus.PROTECTED
                elif db_status == "stopped":
                    status = ResourceStatus.STOPPED
                else:
                    status = ResourceStatus.ACTIVE

                # Endpoint string
                endpoint = None
                ep = db.get("Endpoint")
                if ep:
                    endpoint = f"{ep.get('Address', '')}:{ep.get('Port', '')}"

                # RDS uses TagList (same format as EC2 Tags)
                tag_list = db.get("TagList", [])
                name = get_name_tag(tag_list) or db["DBInstanceIdentifier"]

                resources.append(DiscoveredResource(
                    resource_id=db["DBInstanceIdentifier"],
                    resource_type=ResourceType.RDS_INSTANCE,
                    region=region,
                    arn=db.get("DBInstanceArn"),
                    name=name,
                    status=status,
                    metadata={
                        "instance_class": db["DBInstanceClass"],
                        "engine": db.get("Engine"),
                        "engine_version": db.get("EngineVersion"),
                        "db_instance_status": db_status,
                        "multi_az": db.get("MultiAZ", False),
                        "allocated_storage_gb": db.get("AllocatedStorage", 0),
                        "endpoint": endpoint,
                        "deletion_protection": deletion_prot,
                        "storage_type": db.get("StorageType"),
                    },
                    created_at=db.get("InstanceCreateTime"),
                ))
    except ClientError as exc:
        logger.warning("RDS describe_db_instances failed in %s: %s", region, exc)

    return resources
