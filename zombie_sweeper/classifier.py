"""Active vs. Orphaned/Idle resource classifier.

Applies heuristic rules to determine whether a resource is actively used,
idle, orphaned, or stopped.  Runs after scanning and before cost estimation.
"""

from __future__ import annotations

import logging

from zombie_sweeper.models import DiscoveredResource, ResourceStatus, ResourceType

logger = logging.getLogger("zombie_sweeper")


def classify_resources(resources: list[DiscoveredResource]) -> None:
    """Classify every resource in *resources* in-place.

    Must be called **after** scanning so we can cross-reference resources
    (e.g. check whether a snapshot's source volume still exists).
    """
    # Build a set of all known volume IDs so we can detect orphaned snapshots
    known_volume_ids: set[str] = {
        r.resource_id
        for r in resources
        if r.resource_type == ResourceType.EBS_VOLUME
    }

    for r in resources:
        # Never downgrade an already-protected resource
        if r.status == ResourceStatus.PROTECTED:
            continue

        new_status = _classify_one(r, known_volume_ids)
        if new_status is not None:
            r.status = new_status


def _classify_one(
    r: DiscoveredResource,
    known_volume_ids: set[str],
) -> ResourceStatus | None:
    """Return the correct status for *r*, or ``None`` to keep the current one."""
    rt = r.resource_type
    meta = r.metadata

    # -- EC2 Instances -------------------------------------------------------
    if rt == ResourceType.EC2_INSTANCE:
        if meta.get("state") == "stopped":
            return ResourceStatus.STOPPED
        return ResourceStatus.ACTIVE

    # -- EBS Volumes ---------------------------------------------------------
    if rt == ResourceType.EBS_VOLUME:
        attachments = meta.get("attachments", [])
        return ResourceStatus.ORPHANED if not attachments else ResourceStatus.ACTIVE

    # -- EBS Snapshots -------------------------------------------------------
    if rt == ResourceType.EBS_SNAPSHOT:
        source_vol = meta.get("volume_id")
        # If the source volume no longer exists the snapshot is likely orphaned
        if not source_vol or source_vol not in known_volume_ids:
            return ResourceStatus.ORPHANED
        return ResourceStatus.ACTIVE

    # -- Elastic IPs ---------------------------------------------------------
    if rt == ResourceType.ELASTIC_IP:
        return (
            ResourceStatus.ACTIVE
            if meta.get("association_id")
            else ResourceStatus.ORPHANED
        )

    # -- NAT Gateways, ALBs, NLBs -------------------------------------------
    if rt in (ResourceType.NAT_GATEWAY, ResourceType.ALB, ResourceType.NLB):
        return ResourceStatus.ACTIVE  # If it exists, it costs money

    # -- RDS Instances -------------------------------------------------------
    if rt == ResourceType.RDS_INSTANCE:
        if meta.get("deletion_protection"):
            return ResourceStatus.PROTECTED
        if meta.get("db_instance_status") == "stopped":
            return ResourceStatus.STOPPED
        return ResourceStatus.ACTIVE

    # -- ElastiCache Clusters ------------------------------------------------
    if rt == ResourceType.ELASTICACHE_CLUSTER:
        return ResourceStatus.ACTIVE

    # -- EKS Clusters -------------------------------------------------------
    if rt == ResourceType.EKS_CLUSTER:
        return ResourceStatus.ACTIVE

    # -- ECS Clusters -------------------------------------------------------
    if rt == ResourceType.ECS_CLUSTER:
        if meta.get("active_services_count", 0) > 0 or meta.get("running_tasks_count", 0) > 0:
            return ResourceStatus.ACTIVE
        return ResourceStatus.IDLE

    # -- ECS Services -------------------------------------------------------
    if rt == ResourceType.ECS_SERVICE:
        if meta.get("desired_count", 0) > 0:
            return ResourceStatus.ACTIVE
        return ResourceStatus.IDLE

    # -- S3 Buckets (list-only in v1) ----------------------------------------
    if rt == ResourceType.S3_BUCKET:
        return ResourceStatus.ACTIVE

    # -- CloudWatch Log Groups (retention change only) -----------------------
    if rt == ResourceType.CW_LOG_GROUP:
        return ResourceStatus.ACTIVE

    return None
