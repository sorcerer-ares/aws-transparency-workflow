"""Static hourly/monthly pricing tables for AWS resources.

Approximate on-demand prices (us-east-1 baseline) with regional multipliers.
Designed for fast, zero-API-call cost estimation during live demos.
"""

from __future__ import annotations

from zombie_sweeper.models import (
    CostEstimate,
    DiscoveredResource,
    ResourceStatus,
    ResourceType,
)

# ---------------------------------------------------------------------------
# Regional pricing multipliers (relative to us-east-1 = 1.0)
# ---------------------------------------------------------------------------

REGION_MULTIPLIERS: dict[str, float] = {
    "us-east-1": 1.0,
    "us-east-2": 1.0,
    "us-west-1": 1.05,
    "us-west-2": 1.0,
    "ca-central-1": 1.04,
    "ca-west-1": 1.06,
    "eu-west-1": 1.08,
    "eu-west-2": 1.10,
    "eu-west-3": 1.10,
    "eu-central-1": 1.12,
    "eu-central-2": 1.14,
    "eu-north-1": 1.08,
    "eu-south-1": 1.12,
    "eu-south-2": 1.14,
    "ap-south-1": 0.84,
    "ap-south-2": 0.86,
    "ap-southeast-1": 1.10,
    "ap-southeast-2": 1.12,
    "ap-southeast-3": 1.10,
    "ap-southeast-4": 1.14,
    "ap-northeast-1": 1.15,
    "ap-northeast-2": 1.12,
    "ap-northeast-3": 1.12,
    "ap-east-1": 1.14,
    "sa-east-1": 1.40,
    "me-south-1": 1.15,
    "me-central-1": 1.12,
    "af-south-1": 1.18,
    "il-central-1": 1.14,
}

# ---------------------------------------------------------------------------
# EC2 instance monthly costs (730 hours × on-demand hourly rate)
# ---------------------------------------------------------------------------

EC2_PRICES: dict[str, float] = {
    # T2 family
    "t2.nano": 4.23, "t2.micro": 8.47, "t2.small": 16.94,
    "t2.medium": 33.87, "t2.large": 67.74, "t2.xlarge": 135.49,
    # T3 family
    "t3.nano": 3.80, "t3.micro": 7.59, "t3.small": 15.18,
    "t3.medium": 30.37, "t3.large": 60.74, "t3.xlarge": 121.47,
    "t3.2xlarge": 242.94,
    # T3a family
    "t3a.nano": 3.43, "t3a.micro": 6.86, "t3a.small": 13.72,
    "t3a.medium": 27.45, "t3a.large": 54.90, "t3a.xlarge": 109.79,
    # M5 family
    "m5.large": 70.08, "m5.xlarge": 140.16, "m5.2xlarge": 280.32,
    "m5.4xlarge": 560.64, "m5.8xlarge": 1121.28,
    # M6i family
    "m6i.large": 69.35, "m6i.xlarge": 138.70, "m6i.2xlarge": 277.40,
    # M7i family
    "m7i.large": 72.71, "m7i.xlarge": 145.41,
    # C5 family
    "c5.large": 62.05, "c5.xlarge": 124.10, "c5.2xlarge": 248.20,
    "c5.4xlarge": 496.40,
    # C6i family
    "c6i.large": 61.32, "c6i.xlarge": 122.64,
    # R5 family
    "r5.large": 91.98, "r5.xlarge": 183.96, "r5.2xlarge": 367.92,
    # R6i family
    "r6i.large": 91.25, "r6i.xlarge": 182.50,
    # G4dn (GPU)
    "g4dn.xlarge": 381.24, "g4dn.2xlarge": 545.67,
    # P3 (GPU)
    "p3.2xlarge": 2233.80,
    # Default fallback
    "_default": 50.00,
}

# ---------------------------------------------------------------------------
# EBS volume monthly per-GB costs
# ---------------------------------------------------------------------------

EBS_PRICES_PER_GB: dict[str, float] = {
    "gp2": 0.10,
    "gp3": 0.08,
    "io1": 0.125,
    "io2": 0.125,
    "st1": 0.045,
    "sc1": 0.015,
    "standard": 0.05,
    "_default": 0.10,
}

# ---------------------------------------------------------------------------
# Other resource monthly costs
# ---------------------------------------------------------------------------

SNAPSHOT_PRICE_PER_GB: float = 0.05

EIP_IDLE_MONTHLY: float = 3.65       # $0.005/hr for unassociated EIP

NAT_GATEWAY_MONTHLY: float = 32.85   # $0.045/hr base (excl. data transfer)

ALB_MONTHLY: float = 16.43           # $0.0225/hr base (excl. LCU charges)

NLB_MONTHLY: float = 16.43           # $0.0225/hr base (excl. NLCU charges)

EKS_MONTHLY: float = 73.00           # $0.10/hr control plane

ECS_CLUSTER_MONTHLY: float = 0.0     # ECS clusters are free; tasks cost $$$

S3_STORAGE_PER_GB: float = 0.023     # S3 Standard per GB-month

CW_LOGS_STORAGE_PER_GB: float = 0.03  # CloudWatch Logs storage per GB-month

# ---------------------------------------------------------------------------
# RDS instance monthly costs
# ---------------------------------------------------------------------------

RDS_PRICES: dict[str, float] = {
    "db.t3.micro": 12.41, "db.t3.small": 24.82,
    "db.t3.medium": 49.64, "db.t3.large": 99.28,
    "db.t4g.micro": 11.83, "db.t4g.small": 23.65,
    "db.t4g.medium": 47.30, "db.t4g.large": 94.61,
    "db.m5.large": 125.56, "db.m5.xlarge": 251.12,
    "db.m5.2xlarge": 502.24,
    "db.m6i.large": 124.83, "db.m6i.xlarge": 249.66,
    "db.r5.large": 175.20, "db.r5.xlarge": 350.40,
    "db.r5.2xlarge": 700.80,
    "db.r6g.large": 157.68, "db.r6g.xlarge": 315.36,
    "_default": 80.00,
}

# ---------------------------------------------------------------------------
# ElastiCache node monthly costs
# ---------------------------------------------------------------------------

ELASTICACHE_PRICES: dict[str, float] = {
    "cache.t3.micro": 12.41, "cache.t3.small": 24.82,
    "cache.t3.medium": 49.64,
    "cache.t4g.micro": 11.83, "cache.t4g.small": 23.65,
    "cache.t4g.medium": 47.30,
    "cache.m5.large": 124.10, "cache.m5.xlarge": 248.20,
    "cache.r5.large": 175.20, "cache.r5.xlarge": 350.40,
    "cache.r6g.large": 157.68,
    "_default": 50.00,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def estimate_monthly_cost(resource: DiscoveredResource) -> CostEstimate:
    """Estimate the monthly USD cost of a resource from static pricing tables."""
    multiplier = REGION_MULTIPLIERS.get(resource.region, 1.0)
    base_price = _compute_base_price(resource)

    return CostEstimate(
        monthly_usd=round(base_price * multiplier, 2),
        source="fallback_estimate",
        confidence="medium",
    )


def _compute_base_price(resource: DiscoveredResource) -> float:  # noqa: C901 — switch on resource type
    """Compute the us-east-1 base price for a resource."""
    rt = resource.resource_type
    meta = resource.metadata

    if rt == ResourceType.EC2_INSTANCE:
        if resource.status == ResourceStatus.STOPPED:
            return 0.0  # EBS volumes billed separately
        itype = meta.get("instance_type", "_default")
        return EC2_PRICES.get(itype, EC2_PRICES["_default"])

    if rt == ResourceType.EBS_VOLUME:
        vtype = meta.get("volume_type", "_default")
        per_gb = EBS_PRICES_PER_GB.get(vtype, EBS_PRICES_PER_GB["_default"])
        return per_gb * meta.get("size_gb", 1)

    if rt == ResourceType.EBS_SNAPSHOT:
        return SNAPSHOT_PRICE_PER_GB * meta.get("size_gb", 1)

    if rt == ResourceType.ELASTIC_IP:
        # Associated EIPs are free; only idle ones cost money
        return EIP_IDLE_MONTHLY if resource.status == ResourceStatus.ORPHANED else 0.0

    if rt == ResourceType.NAT_GATEWAY:
        return NAT_GATEWAY_MONTHLY

    if rt == ResourceType.ALB:
        return ALB_MONTHLY

    if rt == ResourceType.NLB:
        return NLB_MONTHLY

    if rt == ResourceType.RDS_INSTANCE:
        iclass = meta.get("instance_class", "_default")
        price = RDS_PRICES.get(iclass, RDS_PRICES["_default"])
        if meta.get("multi_az"):
            price *= 2
        return price

    if rt == ResourceType.ELASTICACHE_CLUSTER:
        ntype = meta.get("node_type", "_default")
        per_node = ELASTICACHE_PRICES.get(ntype, ELASTICACHE_PRICES["_default"])
        return per_node * meta.get("num_nodes", 1)

    if rt == ResourceType.EKS_CLUSTER:
        return EKS_MONTHLY

    if rt == ResourceType.ECS_CLUSTER:
        return ECS_CLUSTER_MONTHLY

    if rt == ResourceType.S3_BUCKET:
        return S3_STORAGE_PER_GB * meta.get("size_gb", 0)

    if rt == ResourceType.CW_LOG_GROUP:
        return CW_LOGS_STORAGE_PER_GB * meta.get("stored_bytes_gb", 0)

    return 0.0
