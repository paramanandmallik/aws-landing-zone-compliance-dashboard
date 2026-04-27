"""Collectors for AWS Control Tower: controls, landing zone, and baselines."""

import logging

logger = logging.getLogger(__name__)


def collect_controls(session) -> list[dict]:
    """Paginate list_enabled_controls and return all enabled controls.

    Requirements: 1.3
    """
    try:
        client = session.client("controltower")
        controls = []
        paginator = client.get_paginator("list_enabled_controls")
        for page in paginator.paginate():
            for ctrl in page.get("enabledControls", []):
                controls.append({
                    "control_identifier": ctrl.get("controlIdentifier", ""),
                    "status": ctrl.get("statusSummary", {}).get("status", "UNKNOWN"),
                    "target_identifier": ctrl.get("targetIdentifier", ""),
                    "drift_status": ctrl.get("driftStatusSummary", {}).get("driftStatus"),
                    "arn": ctrl.get("arn", ""),
                })
        logger.info("Collected %d enabled controls", len(controls))
        return controls
    except Exception:
        logger.exception("Failed to collect enabled controls")
        return []


def collect_available_controls(session) -> list[dict]:
    """Collect all available controls from the AWS Control Catalog service.

    Uses the controlcatalog:ListControls API which returns the full catalog
    of controls that can be enabled via Control Tower.
    """
    try:
        client = session.client("controlcatalog")
        controls = []
        resp = client.list_controls(MaxResults=100)
        controls.extend(resp.get("Controls", []))
        token = resp.get("NextToken")
        while token:
            resp = client.list_controls(MaxResults=100, NextToken=token)
            controls.extend(resp.get("Controls", []))
            token = resp.get("NextToken")

        result = []
        for ctrl in controls:
            result.append({
                "arn": ctrl.get("Arn", ""),
                "name": ctrl.get("Name", ""),
                "description": ctrl.get("Description", ""),
                "behavior": ctrl.get("Behavior", ""),
                "severity": ctrl.get("Severity", ""),
                "implementation_type": ctrl.get("Implementation", {}).get("Type", ""),
                "implementation_id": ctrl.get("Implementation", {}).get("Identifier", ""),
                "aliases": ctrl.get("Aliases", []),
                "governed_resources": ctrl.get("GovernedResources", []),
            })
        logger.info("Collected %d available controls from control catalog", len(result))
        return result
    except Exception:
        logger.exception("Failed to collect available controls from catalog")
        return []


def collect_landing_zone(session) -> dict:
    """Retrieve landing zone configuration via list_landing_zones + get_landing_zone.

    Requirements: 1.4
    """
    try:
        client = session.client("controltower")
        lz_list = client.list_landing_zones()
        landing_zones = lz_list.get("landingZones", [])
        if not landing_zones:
            logger.info("No landing zones found")
            return {}
        lz_arn = landing_zones[0].get("arn", "")
        lz_detail = client.get_landing_zone(landingZoneIdentifier=lz_arn)
        lz = lz_detail.get("landingZone", {})
        return {
            "arn": lz.get("arn", ""),
            "status": lz.get("status", ""),
            "version": lz.get("version", ""),
            "drift_status": lz.get("driftStatus", {}).get("status"),
            "latest_available_version": lz.get("latestAvailableVersion", ""),
        }
    except Exception:
        logger.exception("Failed to collect landing zone")
        return {}


def collect_baselines(session) -> list[dict]:
    """Paginate list_enabled_baselines and return all enabled baselines.

    Requirements: 1.4
    """
    try:
        client = session.client("controltower")
        baselines = []
        paginator = client.get_paginator("list_enabled_baselines")
        for page in paginator.paginate():
            for bl in page.get("enabledBaselines", []):
                baselines.append({
                    "arn": bl.get("arn", ""),
                    "baseline_identifier": bl.get("baselineIdentifier", ""),
                    "target_identifier": bl.get("targetIdentifier", ""),
                    "status": bl.get("statusSummary", {}).get("status", "UNKNOWN"),
                })
        logger.info("Collected %d enabled baselines", len(baselines))
        return baselines
    except Exception:
        logger.exception("Failed to collect baselines")
        return []
