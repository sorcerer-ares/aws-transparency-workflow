"""Cost estimation engine — attaches per-resource monthly cost estimates.

Default mode uses the static fallback pricing catalog (zero API calls, instant).
Opt-in ``--use-cost-explorer`` queries AWS Cost Explorer for actual spend data.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError

from zombie_sweeper.models import CostEstimate, DiscoveredResource
from zombie_sweeper.pricing_catalog import estimate_monthly_cost

logger = logging.getLogger("zombie_sweeper")

# Days of Cost Explorer history to query (extrapolated to monthly)
_CE_LOOKBACK_DAYS = 7
_DAYS_IN_MONTH = 30.44


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def attach_costs(
    resources: list[DiscoveredResource],
    use_cost_explorer: bool = False,
) -> None:
    """Attach cost estimates to every resource.  Mutates *resources* in-place."""
    ce_costs: dict[str, CostEstimate] = {}

    if use_cost_explorer:
        try:
            ce_costs = _fetch_cost_explorer_data()
            logger.info("Fetched Cost Explorer data for %d resources.", len(ce_costs))
        except Exception:
            logger.warning(
                "Cost Explorer query failed — falling back to static estimates.",
                exc_info=True,
            )

    for r in resources:
        if r.resource_id in ce_costs:
            r.cost = ce_costs[r.resource_id]
        else:
            r.cost = estimate_monthly_cost(r)


# ---------------------------------------------------------------------------
# Cost Explorer integration (opt-in)
# ---------------------------------------------------------------------------

def _fetch_cost_explorer_data() -> dict[str, CostEstimate]:
    """Query AWS Cost Explorer for actual per-resource costs (last 7 days).

    Returns a dict mapping ``resource_id`` → ``CostEstimate`` with the daily
    average extrapolated to a 30.44-day month.
    """
    client = boto3.client("ce", region_name="us-east-1")

    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=_CE_LOOKBACK_DAYS)

    costs: dict[str, float] = {}
    next_token: str | None = None

    while True:
        kwargs: dict = dict(
            TimePeriod={"Start": start.isoformat(), "End": end.isoformat()},
            Granularity="DAILY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "RESOURCE_ID"}],
        )
        if next_token:
            kwargs["NextPageToken"] = next_token

        try:
            resp = client.get_cost_and_usage_with_resources(**kwargs)
        except ClientError as exc:
            # Resource-level data may not be enabled for this account
            logger.warning("CE get_cost_and_usage_with_resources failed: %s", exc)
            break

        for period in resp.get("ResultsByTime", []):
            for group in period.get("Groups", []):
                rid = group["Keys"][0]
                amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                costs[rid] = costs.get(rid, 0.0) + amount

        next_token = resp.get("NextPageToken")
        if not next_token:
            break

    # Extrapolate the N-day total to a monthly estimate
    result: dict[str, CostEstimate] = {}
    for rid, total in costs.items():
        daily_avg = total / _CE_LOOKBACK_DAYS
        monthly = round(daily_avg * _DAYS_IN_MONTH, 2)
        if monthly > 0:
            result[rid] = CostEstimate(
                monthly_usd=monthly,
                source="cost_explorer",
                confidence="high",
            )

    return result
