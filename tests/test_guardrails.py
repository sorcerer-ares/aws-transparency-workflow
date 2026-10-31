"""Tests for self-preservation guardrails."""

from unittest.mock import patch
from zombie_sweeper.guardrails import apply_guardrails, build_protection_set, detect_self_instance
from zombie_sweeper.models import DiscoveredResource, ResourceStatus, ResourceType


def test_detect_self_not_on_ec2():
    # Outside EC2 IMDSv2 fails or times out
    with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
        identity = detect_self_instance()
        assert identity is None


def test_protection_whitelist_and_dependencies():
    protection_set = build_protection_set(protect_ids=["i-whitelist1", "vol-critical"])

    assert "i-whitelist1" in protection_set
    assert "vol-critical" in protection_set

    # Test applying guardrails
    host_instance = DiscoveredResource(
        resource_id="i-whitelist1",
        resource_type=ResourceType.EC2_INSTANCE,
        region="us-east-1",
        status=ResourceStatus.ACTIVE,
    )
    # A volume whose dependencies include the protected instance
    attached_vol = DiscoveredResource(
        resource_id="vol-attached",
        resource_type=ResourceType.EBS_VOLUME,
        region="us-east-1",
        status=ResourceStatus.ACTIVE,
        dependencies=["i-whitelist1"],
    )
    # Normal unprotected resource
    unrelated_vol = DiscoveredResource(
        resource_id="vol-other",
        resource_type=ResourceType.EBS_VOLUME,
        region="us-east-1",
        status=ResourceStatus.ACTIVE,
        dependencies=["i-unprotected"],
    )

    resources = [host_instance, attached_vol, unrelated_vol]
    apply_guardrails(resources, protection_set)

    assert host_instance.status == ResourceStatus.PROTECTED
    assert attached_vol.status == ResourceStatus.PROTECTED
    assert unrelated_vol.status == ResourceStatus.ACTIVE
