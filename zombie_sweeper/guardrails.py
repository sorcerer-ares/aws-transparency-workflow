"""Self-preservation guardrails.

Automatically detects the current EC2 instance via IMDSv2 and builds a
protection set that prevents Zombie Sweeper from ever deleting the host
machine, its root volume, or any user-whitelisted resources.
"""

from __future__ import annotations

import json
import logging
import urllib.request

import boto3
from botocore.exceptions import ClientError

from zombie_sweeper.models import DiscoveredResource, ResourceStatus

logger = logging.getLogger("zombie_sweeper")

_IMDS_TOKEN_URL = "http://169.254.169.254/latest/api/token"
_IMDS_IDENTITY_URL = (
    "http://169.254.169.254/latest/dynamic/instance-identity/document"
)
_IMDS_TIMEOUT = 2  # seconds


# ---------------------------------------------------------------------------
# IMDSv2 self-detection
# ---------------------------------------------------------------------------

def detect_self_instance() -> dict | None:
    """Detect the current EC2 instance via IMDSv2.

    Returns a dict with ``instanceId``, ``region``, ``instanceType``, and
    ``accountId`` if running on EC2.  Returns ``None`` otherwise.
    """
    try:
        # Step 1: acquire session token (PUT)
        token_req = urllib.request.Request(
            _IMDS_TOKEN_URL,
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "21600"},
            method="PUT",
        )
        with urllib.request.urlopen(token_req, timeout=_IMDS_TIMEOUT) as resp:
            token = resp.read().decode()

        # Step 2: fetch identity document (GET)
        doc_req = urllib.request.Request(
            _IMDS_IDENTITY_URL,
            headers={"X-aws-ec2-metadata-token": token},
        )
        with urllib.request.urlopen(doc_req, timeout=_IMDS_TIMEOUT) as resp:
            doc = json.loads(resp.read().decode())

        logger.info(
            "IMDSv2: running on instance %s (%s) in %s",
            doc.get("instanceId"),
            doc.get("instanceType"),
            doc.get("region"),
        )
        return doc

    except Exception:
        logger.debug("IMDSv2 unreachable — not running on EC2.")
        return None


# ---------------------------------------------------------------------------
# Discover resources attached to the self-instance
# ---------------------------------------------------------------------------

def get_self_attached_resources(instance_id: str, region: str) -> list[str]:
    """Return resource IDs attached to *instance_id* that must be protected.

    Includes the instance itself, its EBS root/data volumes, and security
    groups.
    """
    protected = [instance_id]
    try:
        ec2 = boto3.client("ec2", region_name=region)
        resp = ec2.describe_instances(InstanceIds=[instance_id])
        for reservation in resp.get("Reservations", []):
            for inst in reservation.get("Instances", []):
                # Attached EBS volumes
                for bdm in inst.get("BlockDeviceMappings", []):
                    ebs = bdm.get("Ebs", {})
                    vid = ebs.get("VolumeId")
                    if vid:
                        protected.append(vid)
                # Security groups
                for sg in inst.get("SecurityGroups", []):
                    sgid = sg.get("GroupId")
                    if sgid:
                        protected.append(sgid)
    except ClientError:
        logger.warning(
            "Could not describe instance %s — protecting instance ID only.",
            instance_id,
            exc_info=True,
        )
    return protected


# ---------------------------------------------------------------------------
# Build the full protection set
# ---------------------------------------------------------------------------

def build_protection_set(protect_ids: list[str] | None = None) -> set[str]:
    """Build the set of resource IDs that must **never** be deleted.

    Combines:
    * auto-detected self-instance + attached volumes / security groups
    * user-supplied ``--protect`` whitelist
    """
    protected: set[str] = set()

    # Auto-detect self
    identity = detect_self_instance()
    if identity:
        iid = identity["instanceId"]
        region = identity["region"]
        for rid in get_self_attached_resources(iid, region):
            protected.add(rid)

    # User-specified whitelist
    if protect_ids:
        protected.update(protect_ids)

    if protected:
        logger.info("Protection set (%d resources): %s", len(protected), protected)
    return protected


# ---------------------------------------------------------------------------
# Apply guardrails to scanned resources
# ---------------------------------------------------------------------------

def apply_guardrails(
    resources: list[DiscoveredResource],
    protection_set: set[str],
) -> None:
    """Mark protected resources so they are excluded from destroy plans.

    Also protects any resource whose *dependencies* overlap with the
    protection set (e.g. an EBS volume attached to the protected host).
    """
    for r in resources:
        if r.resource_id in protection_set:
            r.status = ResourceStatus.PROTECTED
            continue
        # Protect resources attached to a protected parent
        if r.dependencies and protection_set.intersection(r.dependencies):
            r.status = ResourceStatus.PROTECTED
