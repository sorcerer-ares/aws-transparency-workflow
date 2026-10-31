"""Multi-region parallel resource discovery orchestrator.

Fans out scanner calls across all enabled AWS regions using
``ThreadPoolExecutor`` and collects results into a flat resource list.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from zombie_sweeper.models import DiscoveredResource
from zombie_sweeper.scanners import (
    cloudwatch,
    containers,
    ec2,
    elasticache,
    networking,
    rds,
    s3,
)
from zombie_sweeper.utils import get_enabled_regions

logger = logging.getLogger("zombie_sweeper")

# All regional scanners — each takes (region: str) -> list[DiscoveredResource]
_REGIONAL_SCANNERS = [
    ("EC2 Instances", ec2.scan_instances),
    ("EBS Volumes", ec2.scan_volumes),
    ("EBS Snapshots", ec2.scan_snapshots),
    ("Elastic IPs", ec2.scan_eips),
    ("NAT Gateways", networking.scan_nat_gateways),
    ("Load Balancers", networking.scan_load_balancers),
    ("RDS Instances", rds.scan_instances),
    ("ElastiCache", elasticache.scan_clusters),
    ("EKS Clusters", containers.scan_eks_clusters),
    ("ECS Clusters", containers.scan_ecs_clusters),
    ("CW Log Groups", cloudwatch.scan_log_groups),
]


def scan_region(region: str, progress_callback=None) -> list[DiscoveredResource]:
    """Run all service scanners for a single region.

    *progress_callback*, if provided, is called with ``(scanner_name, region,
    count)`` after each scanner finishes.
    """
    results: list[DiscoveredResource] = []

    for scanner_name, scanner_fn in _REGIONAL_SCANNERS:
        try:
            found = scanner_fn(region)
            results.extend(found)
            if progress_callback:
                progress_callback(scanner_name, region, len(found))
        except Exception:
            logger.warning(
                "Scanner %s failed in %s", scanner_name, region, exc_info=True
            )

    return results


def scan_all_regions(
    regions: list[str] | None = None,
    max_workers: int = 16,
    progress_callback=None,
) -> list[DiscoveredResource]:
    """Parallel scan across all (or specified) regions.

    Parameters
    ----------
    regions:
        List of region codes.  ``None`` → all enabled regions.
    max_workers:
        Thread pool size for concurrent region scanning.
    progress_callback:
        ``(scanner_name, region, count) -> None``

    Returns
    -------
    list[DiscoveredResource]
        Flat list of every discovered resource across all regions.
    """
    if regions is None:
        regions = get_enabled_regions()

    logger.info("Scanning %d region(s): %s", len(regions), ", ".join(regions))

    all_resources: list[DiscoveredResource] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_region = {
            executor.submit(scan_region, r, progress_callback): r
            for r in regions
        }

        for future in as_completed(future_to_region):
            region = future_to_region[future]
            try:
                resources = future.result()
                all_resources.extend(resources)
                logger.info(
                    "Region %s: discovered %d resources", region, len(resources)
                )
            except Exception:
                logger.error("Region %s scan failed", region, exc_info=True)

    # S3 is global — scan once outside the regional loop
    try:
        s3_resources = s3.scan_buckets()
        all_resources.extend(s3_resources)
        logger.info("S3 global scan: discovered %d buckets", len(s3_resources))
    except Exception:
        logger.error("S3 global scan failed", exc_info=True)

    logger.info("Total: %d resources discovered across %d region(s)",
                len(all_resources), len(regions))
    return all_resources
