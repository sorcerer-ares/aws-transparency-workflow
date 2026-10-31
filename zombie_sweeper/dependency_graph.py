"""Resource deletion dependency ordering.

Defines the phase-based deletion order to avoid AWS ``DependencyViolation``
errors.  Resources in earlier phases are deleted first, with configurable
wait times between phases for deletions to propagate.
"""

from __future__ import annotations

from zombie_sweeper.models import DiscoveredResource, ResourceStatus, ResourceType

# ---------------------------------------------------------------------------
# Phase definitions
# ---------------------------------------------------------------------------

DELETION_PHASES: list[set[ResourceType]] = [
    # Phase 1: Compute & managed services (parallel within phase)
    {
        ResourceType.ECS_SERVICE,
        ResourceType.ECS_CLUSTER,
        ResourceType.EKS_CLUSTER,
        ResourceType.EC2_INSTANCE,
        ResourceType.RDS_INSTANCE,
        ResourceType.ELASTICACHE_CLUSTER,
    },
    # Phase 2: Networking (depends on compute being terminated)
    {
        ResourceType.ALB,
        ResourceType.NLB,
        ResourceType.NAT_GATEWAY,
    },
    # Phase 3: Detached / orphaned resources
    {
        ResourceType.ELASTIC_IP,
        ResourceType.EBS_VOLUME,
        ResourceType.EBS_SNAPSHOT,
    },
    # Phase 4: Observability & storage (lowest priority)
    {
        ResourceType.CW_LOG_GROUP,
        ResourceType.S3_BUCKET,
    },
]

PHASE_LABELS: dict[int, str] = {
    0: "Compute & Managed Services",
    1: "Networking Layer",
    2: "Detached Resources",
    3: "Observability & Storage",
}

# Seconds to wait after each phase completes before starting the next one
PHASE_WAIT_SECONDS: dict[int, int] = {
    0: 60,   # Wait for EC2/RDS termination to propagate
    1: 30,   # NAT GW deletion can take 1-2 min
    2: 5,    # EIP release is fast
    3: 0,    # Final phase — no wait needed
}

# Resource types we never delete in v1
_NO_DELETE_TYPES: set[ResourceType] = {
    ResourceType.S3_BUCKET,    # No S3 deletion in v1
    ResourceType.CW_LOG_GROUP, # Retention change only, not deletion
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_execution_phases(
    resources: list[DiscoveredResource],
) -> list[list[DiscoveredResource]]:
    """Group *resources* into ordered deletion phases.

    * Protected resources are excluded.
    * S3 buckets and CW Log Groups are excluded (not deleted in v1).
    * Only non-empty phases are returned.
    """
    candidates = [
        r for r in resources
        if r.status != ResourceStatus.PROTECTED
        and r.resource_type not in _NO_DELETE_TYPES
    ]

    phases: list[list[DiscoveredResource]] = []
    for phase_types in DELETION_PHASES:
        phase = [r for r in candidates if r.resource_type in phase_types]
        if phase:
            phases.append(phase)

    return phases


def get_phase_wait_time(phase_index: int) -> int:
    """Return the wait time (seconds) after completing phase *phase_index*."""
    return PHASE_WAIT_SECONDS.get(phase_index, 10)


def get_phase_label(phase_index: int) -> str:
    """Return a human-readable label for phase *phase_index*."""
    return PHASE_LABELS.get(phase_index, f"Phase {phase_index + 1}")
