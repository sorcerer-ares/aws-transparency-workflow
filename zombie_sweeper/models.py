"""Pydantic data models for Zombie Sweeper resources, cost estimates, and destroy plans."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ResourceType(str, Enum):
    """All supported billable AWS resource types."""

    EC2_INSTANCE = "ec2:instance"
    EBS_VOLUME = "ec2:volume"
    EBS_SNAPSHOT = "ec2:snapshot"
    ELASTIC_IP = "ec2:eip"
    NAT_GATEWAY = "ec2:nat-gateway"
    ALB = "elbv2:loadbalancer/app"
    NLB = "elbv2:loadbalancer/net"
    RDS_INSTANCE = "rds:db"
    ELASTICACHE_CLUSTER = "elasticache:cluster"
    EKS_CLUSTER = "eks:cluster"
    ECS_CLUSTER = "ecs:cluster"
    ECS_SERVICE = "ecs:service"
    S3_BUCKET = "s3:bucket"
    CW_LOG_GROUP = "logs:log-group"


class ResourceStatus(str, Enum):
    """Lifecycle / billing status of a discovered resource."""

    ACTIVE = "active"          # Running, in-use, attached
    IDLE = "idle"              # Running but low utilisation
    ORPHANED = "orphaned"      # Detached, unused, no associations
    STOPPED = "stopped"        # Stopped EC2/RDS (still billing EBS/storage)
    PROTECTED = "protected"    # Whitelisted, self-host, or deletion-protection enabled


class CostEstimate(BaseModel):
    """Estimated monthly cost for a single resource."""

    monthly_usd: float = 0.0
    source: str = "fallback_estimate"   # "cost_explorer" | "fallback_estimate"
    confidence: str = "medium"          # "high" | "medium" | "low"


class DiscoveredResource(BaseModel):
    """A single billable AWS resource discovered during scanning."""

    resource_id: str
    resource_type: ResourceType
    region: str
    arn: Optional[str] = None
    name: Optional[str] = None
    status: ResourceStatus = ResourceStatus.ACTIVE
    cost: Optional[CostEstimate] = None
    metadata: dict = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    last_used: Optional[datetime] = None
    dependencies: list[str] = Field(default_factory=list)
    deletion_order: int = 0

    # ---- Convenience helpers ------------------------------------------------

    @property
    def display_type(self) -> str:
        """Human-readable short name for the resource type."""
        _NAMES = {
            ResourceType.EC2_INSTANCE: "EC2 Instance",
            ResourceType.EBS_VOLUME: "EBS Volume",
            ResourceType.EBS_SNAPSHOT: "EBS Snapshot",
            ResourceType.ELASTIC_IP: "Elastic IP",
            ResourceType.NAT_GATEWAY: "NAT Gateway",
            ResourceType.ALB: "ALB",
            ResourceType.NLB: "NLB",
            ResourceType.RDS_INSTANCE: "RDS Instance",
            ResourceType.ELASTICACHE_CLUSTER: "ElastiCache",
            ResourceType.EKS_CLUSTER: "EKS Cluster",
            ResourceType.ECS_CLUSTER: "ECS Cluster",
            ResourceType.ECS_SERVICE: "ECS Service",
            ResourceType.S3_BUCKET: "S3 Bucket",
            ResourceType.CW_LOG_GROUP: "CW Log Group",
        }
        return _NAMES.get(self.resource_type, self.resource_type.value)

    @property
    def cost_monthly(self) -> float:
        return self.cost.monthly_usd if self.cost else 0.0


class PhaseResult(BaseModel):
    """Outcome of executing a single deletion phase."""

    phase: int
    succeeded: list[str] = Field(default_factory=list)
    failed: list[dict] = Field(default_factory=list)   # [{"id": ..., "error": ...}]
    skipped: list[str] = Field(default_factory=list)


class DestroyPlan(BaseModel):
    """A terraform-style execution plan for resource destruction."""

    resources: list[DiscoveredResource] = Field(default_factory=list)
    total_monthly_savings: float = 0.0
    execution_phases: list[list[str]] = Field(default_factory=list)
    protected_resources: list[DiscoveredResource] = Field(default_factory=list)
    dry_run: bool = True
