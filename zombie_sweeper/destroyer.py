"""Execution engine — carries out a destroy plan phase-by-phase.

Each phase runs resource deletions in parallel using ``ThreadPoolExecutor``,
with configurable waits between phases so AWS can propagate state changes.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3
from botocore.exceptions import ClientError

from zombie_sweeper.dependency_graph import get_phase_label, get_phase_wait_time
from zombie_sweeper.models import (
    DestroyPlan,
    DiscoveredResource,
    PhaseResult,
    ResourceType,
)
from zombie_sweeper.scanners.cloudwatch import set_retention_policy

logger = logging.getLogger("zombie_sweeper")


# ---------------------------------------------------------------------------
# Per-resource-type deletion functions
# ---------------------------------------------------------------------------

def _terminate_ec2(r: DiscoveredResource) -> None:
    ec2 = boto3.client("ec2", region_name=r.region)
    ec2.terminate_instances(InstanceIds=[r.resource_id])
    waiter = ec2.get_waiter("instance_terminated")
    waiter.wait(
        InstanceIds=[r.resource_id],
        WaiterConfig={"Delay": 10, "MaxAttempts": 30},
    )


def _delete_volume(r: DiscoveredResource) -> None:
    ec2 = boto3.client("ec2", region_name=r.region)
    ec2.delete_volume(VolumeId=r.resource_id)


def _delete_snapshot(r: DiscoveredResource) -> None:
    ec2 = boto3.client("ec2", region_name=r.region)
    ec2.delete_snapshot(SnapshotId=r.resource_id)


def _release_eip(r: DiscoveredResource) -> None:
    ec2 = boto3.client("ec2", region_name=r.region)
    ec2.release_address(AllocationId=r.resource_id)


def _delete_nat_gateway(r: DiscoveredResource) -> None:
    ec2 = boto3.client("ec2", region_name=r.region)
    ec2.delete_nat_gateway(NatGatewayId=r.resource_id)
    # NAT GW deletion is async — wait via polling
    for _ in range(30):
        time.sleep(5)
        resp = ec2.describe_nat_gateways(NatGatewayIds=[r.resource_id])
        nats = resp.get("NatGateways", [])
        if nats and nats[0]["State"] == "deleted":
            return
    logger.warning("NAT GW %s did not reach 'deleted' state in time", r.resource_id)


def _delete_load_balancer(r: DiscoveredResource) -> None:
    elbv2 = boto3.client("elbv2", region_name=r.region)
    arn = r.arn or r.resource_id
    elbv2.delete_load_balancer(LoadBalancerArn=arn)
    # Wait for deprovisioning
    try:
        waiter = elbv2.get_waiter("load_balancers_deleted")
        waiter.wait(
            LoadBalancerArns=[arn],
            WaiterConfig={"Delay": 10, "MaxAttempts": 30},
        )
    except Exception:
        logger.debug("LB waiter unavailable — sleeping 15s", exc_info=True)
        time.sleep(15)


def _delete_rds(r: DiscoveredResource) -> None:
    # Skip if deletion protection is on (should be filtered already, but double-check)
    if r.metadata.get("deletion_protection"):
        raise RuntimeError(
            f"RDS {r.resource_id} has DeletionProtection enabled — "
            "manual intervention required"
        )
    rds_client = boto3.client("rds", region_name=r.region)
    rds_client.delete_db_instance(
        DBInstanceIdentifier=r.resource_id,
        SkipFinalSnapshot=True,
        DeleteAutomatedBackups=True,
    )
    waiter = rds_client.get_waiter("db_instance_deleted")
    waiter.wait(
        DBInstanceIdentifier=r.resource_id,
        WaiterConfig={"Delay": 30, "MaxAttempts": 60},
    )


def _delete_elasticache(r: DiscoveredResource) -> None:
    ec = boto3.client("elasticache", region_name=r.region)
    ec.delete_cache_cluster(CacheClusterId=r.resource_id)


def _delete_eks(r: DiscoveredResource) -> None:
    eks = boto3.client("eks", region_name=r.region)
    eks.delete_cluster(name=r.resource_id)


def _delete_ecs_cluster(r: DiscoveredResource) -> None:
    ecs = boto3.client("ecs", region_name=r.region)
    arn = r.arn or r.resource_id
    ecs.delete_cluster(cluster=arn)


# ---------------------------------------------------------------------------
# Deleter dispatch table
# ---------------------------------------------------------------------------

_DELETERS: dict[ResourceType, callable] = {
    ResourceType.EC2_INSTANCE: _terminate_ec2,
    ResourceType.EBS_VOLUME: _delete_volume,
    ResourceType.EBS_SNAPSHOT: _delete_snapshot,
    ResourceType.ELASTIC_IP: _release_eip,
    ResourceType.NAT_GATEWAY: _delete_nat_gateway,
    ResourceType.ALB: _delete_load_balancer,
    ResourceType.NLB: _delete_load_balancer,
    ResourceType.RDS_INSTANCE: _delete_rds,
    ResourceType.ELASTICACHE_CLUSTER: _delete_elasticache,
    ResourceType.EKS_CLUSTER: _delete_eks,
    ResourceType.ECS_CLUSTER: _delete_ecs_cluster,
    # S3_BUCKET intentionally omitted — no deletion in v1
    # CW_LOG_GROUP — handled separately (retention change, not deletion)
}


# ---------------------------------------------------------------------------
# Plan execution
# ---------------------------------------------------------------------------

def execute_plan(
    plan: DestroyPlan,
    max_workers: int = 8,
    progress_callback=None,
) -> list[PhaseResult]:
    """Execute a destroy plan phase-by-phase with dependency ordering.

    Parameters
    ----------
    plan:
        A ``DestroyPlan`` with ``dry_run=False``.
    max_workers:
        Thread pool size per phase.
    progress_callback:
        ``(resource_id, success: bool, error: str | None) -> None``

    Returns
    -------
    list[PhaseResult]
        One result per phase.

    Raises
    ------
    RuntimeError
        If the plan still has ``dry_run=True``.
    """
    if plan.dry_run:
        raise RuntimeError(
            "Cannot execute a dry-run plan.  "
            "Set plan.dry_run = False after user confirmation."
        )

    results: list[PhaseResult] = []

    for phase_idx, phase_ids in enumerate(plan.execution_phases):
        label = get_phase_label(phase_idx)
        phase_resources = [
            r for r in plan.resources if r.resource_id in set(phase_ids)
        ]

        logger.info(
            "⏳ Phase %d — %s (%d resources)",
            phase_idx + 1, label, len(phase_resources),
        )

        phase_result = PhaseResult(phase=phase_idx + 1)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for r in phase_resources:
                deleter = _DELETERS.get(r.resource_type)
                if deleter:
                    futures[executor.submit(deleter, r)] = r
                else:
                    phase_result.skipped.append(r.resource_id)

            for future in as_completed(futures):
                resource = futures[future]
                try:
                    future.result()
                    phase_result.succeeded.append(resource.resource_id)
                    if progress_callback:
                        progress_callback(resource.resource_id, True, None)
                except Exception as exc:
                    err = str(exc)
                    phase_result.failed.append(
                        {"id": resource.resource_id, "error": err}
                    )
                    if progress_callback:
                        progress_callback(resource.resource_id, False, err)
                    logger.error(
                        "❌ Failed to delete %s: %s", resource.resource_id, err
                    )

        results.append(phase_result)

        # Wait between phases for deletions to propagate
        wait = get_phase_wait_time(phase_idx)
        if wait > 0 and phase_idx < len(plan.execution_phases) - 1:
            logger.info("⏳ Waiting %ds for phase %d deletions to propagate…", wait, phase_idx + 1)
            time.sleep(wait)

    return results


# ---------------------------------------------------------------------------
# CloudWatch Log retention (non-destructive)
# ---------------------------------------------------------------------------

def apply_log_retention(
    resources: list[DiscoveredResource],
    retention_days: int = 7,
) -> dict[str, bool]:
    """Set retention policy on all CloudWatch Log Groups in *resources*.

    Returns a dict mapping ``log_group_name → success``.
    """
    results: dict[str, bool] = {}
    log_groups = [
        r for r in resources if r.resource_type == ResourceType.CW_LOG_GROUP
    ]
    for lg in log_groups:
        ok = set_retention_policy(lg.region, lg.resource_id, retention_days)
        results[lg.resource_id] = ok
    return results
