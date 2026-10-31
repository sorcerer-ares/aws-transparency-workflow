"""Networking resource scanners — NAT Gateways, ALBs, NLBs."""

from __future__ import annotations

import logging

import boto3
from botocore.exceptions import ClientError

from zombie_sweeper.models import DiscoveredResource, ResourceStatus, ResourceType
from zombie_sweeper.utils import get_name_tag

logger = logging.getLogger("zombie_sweeper")


# ---------------------------------------------------------------------------
# NAT Gateways
# ---------------------------------------------------------------------------

def scan_nat_gateways(region: str) -> list[DiscoveredResource]:
    """Discover NAT Gateways in *region*.  If it exists, it costs money."""
    ec2 = boto3.client("ec2", region_name=region)
    resources: list[DiscoveredResource] = []

    try:
        paginator = ec2.get_paginator("describe_nat_gateways")
        for page in paginator.paginate(
            Filters=[{"Name": "state", "Values": ["available", "pending"]}]
        ):
            for nat in page.get("NatGateways", []):
                eip_alloc_ids = [
                    a["AllocationId"]
                    for a in nat.get("NatGatewayAddresses", [])
                    if "AllocationId" in a
                ]

                resources.append(DiscoveredResource(
                    resource_id=nat["NatGatewayId"],
                    resource_type=ResourceType.NAT_GATEWAY,
                    region=region,
                    name=get_name_tag(nat.get("Tags")),
                    status=ResourceStatus.ACTIVE,
                    metadata={
                        "state": nat["State"],
                        "subnet_id": nat.get("SubnetId"),
                        "vpc_id": nat.get("VpcId"),
                        "eip_allocation_ids": eip_alloc_ids,
                        "connectivity_type": nat.get("ConnectivityType", "public"),
                    },
                    created_at=nat.get("CreateTime"),
                    dependencies=eip_alloc_ids,
                ))
    except ClientError as exc:
        logger.warning("describe_nat_gateways failed in %s: %s", region, exc)

    return resources


# ---------------------------------------------------------------------------
# Application & Network Load Balancers (ELBv2)
# ---------------------------------------------------------------------------

def scan_load_balancers(region: str) -> list[DiscoveredResource]:
    """Discover ALBs and NLBs in *region* via the ELBv2 API."""
    elbv2 = boto3.client("elbv2", region_name=region)
    resources: list[DiscoveredResource] = []

    try:
        paginator = elbv2.get_paginator("describe_load_balancers")
        for page in paginator.paginate():
            for lb in page.get("LoadBalancers", []):
                lb_type = lb.get("Type", "application")

                # Skip Gateway LBs — they're a different billing model
                if lb_type == "gateway":
                    continue

                resource_type = (
                    ResourceType.ALB if lb_type == "application"
                    else ResourceType.NLB
                )

                az_names = [
                    az["ZoneName"]
                    for az in lb.get("AvailabilityZones", [])
                ]

                resources.append(DiscoveredResource(
                    resource_id=lb["LoadBalancerArn"],
                    resource_type=resource_type,
                    region=region,
                    arn=lb["LoadBalancerArn"],
                    name=lb.get("LoadBalancerName"),
                    status=ResourceStatus.ACTIVE,
                    metadata={
                        "dns_name": lb.get("DNSName"),
                        "type": lb_type,
                        "state": lb.get("State", {}).get("Code"),
                        "vpc_id": lb.get("VpcId"),
                        "scheme": lb.get("Scheme"),
                        "availability_zones": az_names,
                    },
                    created_at=lb.get("CreatedTime"),
                ))
    except ClientError as exc:
        logger.warning("ELBv2 describe_load_balancers failed in %s: %s", region, exc)

    return resources
