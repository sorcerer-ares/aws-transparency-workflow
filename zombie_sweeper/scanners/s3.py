"""S3 bucket scanner — list-only, no deletion support in v1.

S3 is a global service; this scanner is called once (not per-region).
Bucket sizes are estimated via CloudWatch ``BucketSizeBytes`` metrics.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError

from zombie_sweeper.models import DiscoveredResource, ResourceStatus, ResourceType

logger = logging.getLogger("zombie_sweeper")


def scan_buckets() -> list[DiscoveredResource]:
    """Discover all S3 buckets in the account with estimated sizes.

    This function takes **no region argument** — S3 is global.
    """
    s3 = boto3.client("s3")
    resources: list[DiscoveredResource] = []

    try:
        resp = s3.list_buckets()
    except ClientError as exc:
        logger.warning("S3 list_buckets failed: %s", exc)
        return resources

    for bucket in resp.get("Buckets", []):
        name = bucket["Name"]
        creation_date = bucket.get("CreationDate")

        # Determine bucket region
        bucket_region = _get_bucket_region(s3, name)

        # Estimate size via CloudWatch
        size_gb = _get_bucket_size_gb(name, bucket_region)

        resources.append(DiscoveredResource(
            resource_id=name,
            resource_type=ResourceType.S3_BUCKET,
            region=bucket_region,
            name=name,
            status=ResourceStatus.ACTIVE,  # No S3 deletion in v1
            metadata={
                "size_gb": round(size_gb, 3),
                "creation_date": creation_date.isoformat() if creation_date else None,
                "location_constraint": bucket_region,
            },
            created_at=creation_date,
        ))

    return resources


def _get_bucket_region(s3_client, bucket_name: str) -> str:
    """Return the region a bucket resides in."""
    try:
        resp = s3_client.get_bucket_location(Bucket=bucket_name)
        loc = resp.get("LocationConstraint")
        # None means us-east-1, 'EU' is legacy artifact for eu-west-1
        if loc == "EU":
            return "eu-west-1"
        return loc if loc else "us-east-1"
    except ClientError as exc:
        logger.debug("get_bucket_location(%s) failed: %s", bucket_name, exc)
        return "us-east-1"


def _get_bucket_size_gb(bucket_name: str, region: str) -> float:
    """Estimate bucket size in GB via CloudWatch BucketSizeBytes metric."""
    try:
        cw = boto3.client("cloudwatch", region_name=region)
        now = datetime.now(timezone.utc)
        resp = cw.get_metric_statistics(
            Namespace="AWS/S3",
            MetricName="BucketSizeBytes",
            Dimensions=[
                {"Name": "BucketName", "Value": bucket_name},
                {"Name": "StorageType", "Value": "StandardStorage"},
            ],
            StartTime=now - timedelta(days=2),
            EndTime=now,
            Period=86400,
            Statistics=["Average"],
        )
        datapoints = resp.get("Datapoints", [])
        if datapoints:
            # Take the most recent datapoint
            latest = max(datapoints, key=lambda d: d["Timestamp"])
            return latest["Average"] / (1024 ** 3)
    except Exception as exc:
        logger.debug("CloudWatch BucketSizeBytes(%s) failed: %s", bucket_name, exc)

    return 0.0
