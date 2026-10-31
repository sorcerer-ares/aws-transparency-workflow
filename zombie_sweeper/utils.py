"""Shared utilities — region discovery, pagination helpers, logging setup."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Generator

import boto3

logger = logging.getLogger("zombie_sweeper")


# ---------------------------------------------------------------------------
# Region helpers
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def get_enabled_regions() -> list[str]:
    """Return all enabled AWS regions for this account (cached)."""
    client = boto3.client("ec2", region_name="us-east-1")
    resp = client.describe_regions(
        Filters=[{"Name": "opt-in-status", "Values": ["opt-in-not-required", "opted-in"]}]
    )
    return sorted(r["RegionName"] for r in resp["Regions"])


@lru_cache(maxsize=1)
def get_account_id() -> str:
    """Return the current AWS account ID (cached)."""
    return boto3.client("sts").get_caller_identity()["Account"]


# ---------------------------------------------------------------------------
# Pagination helpers
# ---------------------------------------------------------------------------

def paginate(client: Any, method: str, result_key: str, **kwargs) -> Generator[dict, None, None]:
    """Generic paginator that yields individual items from *result_key*.

    Handles services that use different pagination token names automatically
    via boto3's built-in paginator.
    """
    paginator = client.get_paginator(method)
    for page in paginator.paginate(**kwargs):
        for item in page.get(result_key, []):
            yield item


def get_name_tag(tags: list[dict] | None) -> str | None:
    """Extract the 'Name' tag value from a standard AWS Tags list."""
    if not tags:
        return None
    for tag in tags:
        if tag.get("Key") == "Name":
            return tag.get("Value")
    return None


# ---------------------------------------------------------------------------
# Logging bootstrap
# ---------------------------------------------------------------------------

def setup_logging(verbosity: int = 0) -> None:
    """Configure root logger for the package."""
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logger.setLevel(level)
