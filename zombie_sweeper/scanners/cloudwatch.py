"""CloudWatch Logs scanner.

In v1 we do NOT delete log groups.  Instead we list them and optionally
set their retention policy to 7 days to reduce storage costs.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from zombie_sweeper.models import DiscoveredResource, ResourceStatus, ResourceType

logger = logging.getLogger("zombie_sweeper")


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

def scan_log_groups(region: str) -> list[DiscoveredResource]:
    """Discover CloudWatch Log Groups in *region*."""
    logs = boto3.client("logs", region_name=region)
    resources: list[DiscoveredResource] = []

    try:
        paginator = logs.get_paginator("describe_log_groups")
        for page in paginator.paginate():
            for lg in page.get("logGroups", []):
                stored_bytes = lg.get("storedBytes", 0)
                creation_ms = lg.get("creationTime")
                created_at = (
                    datetime.fromtimestamp(creation_ms / 1000, tz=timezone.utc)
                    if creation_ms
                    else None
                )
                retention = lg.get("retentionInDays")

                resources.append(DiscoveredResource(
                    resource_id=lg["logGroupName"],
                    resource_type=ResourceType.CW_LOG_GROUP,
                    region=region,
                    arn=lg.get("logGroupArn"),
                    name=lg["logGroupName"],
                    status=ResourceStatus.ACTIVE,
                    metadata={
                        "stored_bytes": stored_bytes,
                        "stored_bytes_gb": round(stored_bytes / (1024 ** 3), 3),
                        "retention_days": retention if retention else "Never expires",
                        "creation_time_epoch": creation_ms,
                    },
                    created_at=created_at,
                ))
    except ClientError as exc:
        logger.warning("CloudWatch describe_log_groups failed in %s: %s", region, exc)

    return resources


# ---------------------------------------------------------------------------
# Retention policy setter (non-destructive cost reduction)
# ---------------------------------------------------------------------------

def set_retention_policy(
    region: str,
    log_group_name: str,
    retention_days: int = 7,
) -> bool:
    """Set the retention policy for a log group.

    Returns ``True`` on success, ``False`` on error.
    """
    logs = boto3.client("logs", region_name=region)
    try:
        logs.put_retention_policy(
            logGroupName=log_group_name,
            retentionInDays=retention_days,
        )
        logger.info(
            "Set retention=%d days for %s in %s",
            retention_days, log_group_name, region,
        )
        return True
    except ClientError as exc:
        logger.warning(
            "put_retention_policy(%s) failed in %s: %s",
            log_group_name, region, exc,
        )
        return False
