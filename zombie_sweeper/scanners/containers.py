"""Container service scanners — EKS clusters and ECS clusters."""

from __future__ import annotations

import logging

import boto3
from botocore.exceptions import ClientError

from zombie_sweeper.models import DiscoveredResource, ResourceStatus, ResourceType

logger = logging.getLogger("zombie_sweeper")


# ---------------------------------------------------------------------------
# EKS Clusters
# ---------------------------------------------------------------------------

def scan_eks_clusters(region: str) -> list[DiscoveredResource]:
    """Discover EKS clusters in *region*."""
    eks = boto3.client("eks", region_name=region)
    resources: list[DiscoveredResource] = []

    try:
        # list_clusters uses nextToken pagination (not standard paginator)
        cluster_names: list[str] = []
        next_token: str | None = None

        while True:
            kwargs: dict = {}
            if next_token:
                kwargs["nextToken"] = next_token
            resp = eks.list_clusters(**kwargs)
            cluster_names.extend(resp.get("clusters", []))
            next_token = resp.get("nextToken")
            if not next_token:
                break

        # Describe each cluster for details
        for name in cluster_names:
            try:
                detail = eks.describe_cluster(name=name)["cluster"]
                resources.append(DiscoveredResource(
                    resource_id=name,
                    resource_type=ResourceType.EKS_CLUSTER,
                    region=region,
                    arn=detail.get("arn"),
                    name=name,
                    status=ResourceStatus.ACTIVE,
                    metadata={
                        "version": detail.get("version"),
                        "platform_version": detail.get("platformVersion"),
                        "endpoint": detail.get("endpoint"),
                        "status": detail.get("status"),
                        "role_arn": detail.get("roleArn"),
                    },
                    created_at=detail.get("createdAt"),
                ))
            except ClientError as exc:
                logger.warning("EKS describe_cluster(%s) failed in %s: %s", name, region, exc)

    except ClientError as exc:
        logger.warning("EKS list_clusters failed in %s: %s", region, exc)

    return resources


# ---------------------------------------------------------------------------
# ECS Clusters
# ---------------------------------------------------------------------------

def scan_ecs_clusters(region: str) -> list[DiscoveredResource]:
    """Discover ECS clusters in *region*.

    Clusters with no active services or running tasks are marked as IDLE.
    Individual ECS services are not scanned in v1 (too granular).
    """
    ecs = boto3.client("ecs", region_name=region)
    resources: list[DiscoveredResource] = []

    try:
        # Collect all cluster ARNs
        cluster_arns: list[str] = []
        next_token: str | None = None

        while True:
            kwargs: dict = {}
            if next_token:
                kwargs["nextToken"] = next_token
            resp = ecs.list_clusters(**kwargs)
            cluster_arns.extend(resp.get("clusterArns", []))
            next_token = resp.get("nextToken")
            if not next_token:
                break

        if not cluster_arns:
            return resources

        # describe_clusters accepts max 100 ARNs per call
        for i in range(0, len(cluster_arns), 100):
            batch = cluster_arns[i : i + 100]
            try:
                resp = ecs.describe_clusters(clusters=batch, include=["STATISTICS"])
                for cluster in resp.get("clusters", []):
                    active_svc = cluster.get("activeServicesCount", 0)
                    running_tasks = cluster.get("runningTasksCount", 0)

                    resources.append(DiscoveredResource(
                        resource_id=cluster.get("clusterName", cluster["clusterArn"]),
                        resource_type=ResourceType.ECS_CLUSTER,
                        region=region,
                        arn=cluster["clusterArn"],
                        name=cluster.get("clusterName"),
                        status=(
                            ResourceStatus.ACTIVE
                            if active_svc > 0 or running_tasks > 0
                            else ResourceStatus.IDLE
                        ),
                        metadata={
                            "status": cluster.get("status"),
                            "active_services_count": active_svc,
                            "running_tasks_count": running_tasks,
                            "registered_instances": cluster.get(
                                "registeredContainerInstancesCount", 0
                            ),
                        },
                    ))
            except ClientError as exc:
                logger.warning("ECS describe_clusters failed in %s: %s", region, exc)

    except ClientError as exc:
        logger.warning("ECS list_clusters failed in %s: %s", region, exc)

    return resources
