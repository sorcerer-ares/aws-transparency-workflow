"""ElastiCache cluster scanner."""

from __future__ import annotations

import logging

import boto3
from botocore.exceptions import ClientError

from zombie_sweeper.models import DiscoveredResource, ResourceStatus, ResourceType

logger = logging.getLogger("zombie_sweeper")


def scan_clusters(region: str) -> list[DiscoveredResource]:
    """Discover ElastiCache clusters in *region*."""
    ec = boto3.client("elasticache", region_name=region)
    resources: list[DiscoveredResource] = []

    try:
        paginator = ec.get_paginator("describe_cache_clusters")
        for page in paginator.paginate():
            for cluster in page.get("CacheClusters", []):
                resources.append(DiscoveredResource(
                    resource_id=cluster["CacheClusterId"],
                    resource_type=ResourceType.ELASTICACHE_CLUSTER,
                    region=region,
                    arn=cluster.get("ARN"),
                    name=cluster["CacheClusterId"],
                    status=ResourceStatus.ACTIVE,
                    metadata={
                        "node_type": cluster.get("CacheNodeType"),
                        "engine": cluster.get("Engine"),
                        "engine_version": cluster.get("EngineVersion"),
                        "status": cluster.get("CacheClusterStatus"),
                        "num_nodes": cluster.get("NumCacheNodes", 1),
                    },
                    created_at=cluster.get("CacheClusterCreateTime"),
                ))
    except ClientError as exc:
        logger.warning("ElastiCache describe_cache_clusters failed in %s: %s", region, exc)

    return resources
