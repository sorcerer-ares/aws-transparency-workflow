"""Tests for individual scanner functions using mocked boto3 clients."""

from unittest.mock import MagicMock, patch
from zombie_sweeper.scanners.ec2 import scan_instances, scan_volumes, scan_snapshots, scan_eips
from zombie_sweeper.scanners.networking import scan_nat_gateways, scan_load_balancers
from zombie_sweeper.scanners.rds import scan_instances as scan_rds
from zombie_sweeper.scanners.elasticache import scan_clusters as scan_elasticache
from zombie_sweeper.scanners.containers import scan_eks_clusters, scan_ecs_clusters
from zombie_sweeper.scanners.s3 import scan_buckets
from zombie_sweeper.scanners.cloudwatch import scan_log_groups
from datetime import datetime, timezone


def test_scan_ec2_instances_mock():
    mock_client = MagicMock()
    mock_paginator = MagicMock()
    mock_client.get_paginator.return_value = mock_paginator
    mock_paginator.paginate.return_value = [
        {
            "Reservations": [
                {
                    "Instances": [
                        {
                            "InstanceId": "i-test1",
                            "InstanceType": "t3.micro",
                            "State": {"Name": "running"},
                            "LaunchTime": datetime.now(timezone.utc),
                            "Tags": [{"Key": "Name", "Value": "WebServer"}],
                            "BlockDeviceMappings": [
                                {"Ebs": {"VolumeId": "vol-root"}}
                            ],
                        }
                    ]
                }
            ]
        }
    ]

    with patch("boto3.client", return_value=mock_client):
        results = scan_instances("us-east-1")
        assert len(results) == 1
        assert results[0].resource_id == "i-test1"
        assert results[0].name == "WebServer"
        assert results[0].dependencies == ["vol-root"]


def test_scan_rds_instances_mock():
    mock_client = MagicMock()
    mock_paginator = MagicMock()
    mock_client.get_paginator.return_value = mock_paginator
    mock_paginator.paginate.return_value = [
        {
            "DBInstances": [
                {
                    "DBInstanceIdentifier": "mydb",
                    "DBInstanceClass": "db.t3.micro",
                    "Engine": "postgres",
                    "EngineVersion": "15.3",
                    "DBInstanceStatus": "available",
                    "DeletionProtection": True,
                    "AllocatedStorage": 20,
                    "TagList": [],
                }
            ]
        }
    ]

    with patch("boto3.client", return_value=mock_client):
        results = scan_rds("us-east-1")
        assert len(results) == 1
        assert results[0].resource_id == "mydb"
        # DeletionProtection = True must result in PROTECTED status
        assert results[0].status.value == "protected"


def test_s3_get_bucket_region():
    from zombie_sweeper.scanners.s3 import _get_bucket_region

    mock_s3 = MagicMock()
    mock_s3.get_bucket_location.return_value = {"LocationConstraint": "EU"}
    assert _get_bucket_region(mock_s3, "eu-bucket") == "eu-west-1"

    mock_s3.get_bucket_location.return_value = {"LocationConstraint": None}
    assert _get_bucket_region(mock_s3, "us-bucket") == "us-east-1"

    mock_s3.get_bucket_location.return_value = {"LocationConstraint": "ap-south-1"}
    assert _get_bucket_region(mock_s3, "in-bucket") == "ap-south-1"
