"""Read route handlers for the Governance API.

Each handler takes (event, claims) and returns a response dict with
statusCode, headers, and body.

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.8, 6.7, 4.8
"""

import json
import logging
from dataclasses import asdict

from backend.shared.dynamodb import (
    build_ou_tree,
    deserialize,
    query_by_pk,
    query_gsi1,
    scan_by_pk_prefix,
)
from backend.shared.models import (
    Account,
    ControlTowerControl,
    DeploymentRequest,
    Observation,
    OrganizationalUnit,
    ServiceControlPolicy,
)

logger = logging.getLogger(__name__)


CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Authorization,Content-Type",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
}


def _json_response(status_code: int, body) -> dict:
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps(body, default=str),
    }


def _get_query_params(event: dict) -> dict:
    return event.get("queryStringParameters") or {}


def _strip_db_keys(item: dict) -> dict:
    return {k: v for k, v in item.items() if k not in ("PK", "SK", "entity_type")}


def get_ous(event: dict, claims: dict) -> dict:
    """GET /api/ous — OU hierarchy tree."""
    items = scan_by_pk_prefix("OU#", sk_value="META")
    ous = [deserialize(item, OrganizationalUnit) for item in items]
    tree = build_ou_tree(ous)
    return _json_response(200, {"data": tree})


def filter_accounts(accounts: list[Account], params: dict) -> list[Account]:
    """Filter accounts by ou_path, status, and search text."""
    result = accounts
    ou_path = params.get("ou_path")
    if ou_path:
        result = [a for a in result if ou_path.lower() in a.ou_path.lower()]

    status = params.get("status")
    if status:
        result = [a for a in result if a.status == status]

    search = params.get("search")
    if search:
        search_lower = search.lower()
        result = [
            a for a in result
            if search_lower in a.name.lower()
            or search_lower in a.email.lower()
            or search_lower in a.id.lower()
        ]
    return result


def get_accounts(event: dict, claims: dict) -> dict:
    """GET /api/accounts — all accounts with optional filtering."""
    items = scan_by_pk_prefix("ACCOUNT#", sk_value="META")
    accounts = [deserialize(item, Account) for item in items]
    params = _get_query_params(event)
    accounts = filter_accounts(accounts, params)
    return _json_response(200, {"data": [asdict(a) for a in accounts]})


def get_scps(event: dict, claims: dict) -> dict:
    """GET /api/scps — SCPs with policy documents and targets."""
    items = scan_by_pk_prefix("SCP#", sk_value="META")
    scps = [deserialize(item, ServiceControlPolicy) for item in items]
    data = []
    for scp in scps:
        d = asdict(scp)
        target_items = query_by_pk(f"SCP#{scp.id}", sk_prefix="TARGET#")
        d["targets"] = [_strip_db_keys(t) for t in target_items]
        data.append(d)
    return _json_response(200, {"data": data})


def get_controls(event: dict, claims: dict) -> dict:
    """GET /api/controls — enabled Control Tower controls with status and OUs."""
    items = scan_by_pk_prefix("CONTROL#")
    controls = [deserialize(item, ControlTowerControl) for item in items]
    return _json_response(200, {"data": [asdict(c) for c in controls]})


def get_available_controls(event: dict, claims: dict) -> dict:
    """GET /api/available-controls — all controls from the Control Tower catalog.
    
    Returns with Cache-Control header since catalog changes infrequently.
    """
    items = scan_by_pk_prefix("AVAILABLE_CONTROL#", sk_value="META")
    data = [_strip_db_keys(item) for item in items]
    resp = _json_response(200, {"data": data})
    resp["headers"]["Cache-Control"] = "public, max-age=3600"  # Cache 1 hour
    return resp


def get_landing_zone(event: dict, claims: dict) -> dict:
    """GET /api/landing-zone — landing zone and baseline config."""
    lz_items = query_by_pk("LANDING_ZONE", sk_prefix="META")
    lz_data = _strip_db_keys(lz_items[0]) if lz_items else {}

    baseline_items = scan_by_pk_prefix("BASELINE#", sk_value="META")
    baselines = [_strip_db_keys(b) for b in baseline_items]
    return _json_response(200, {"data": {"landing_zone": lz_data, "baselines": baselines}})


def get_policies(event: dict, claims: dict) -> dict:
    """GET /api/policies — tag/backup/AI opt-out policies with targets."""
    items = scan_by_pk_prefix("POLICY#", sk_value="META")
    data = []
    for item in items:
        policy = _strip_db_keys(item)
        for field in ("content", "targets"):
            if field in policy and isinstance(policy[field], str):
                policy[field] = json.loads(policy[field])
        policy_id = item["PK"].replace("POLICY#", "")
        target_items = query_by_pk(f"POLICY#{policy_id}", sk_prefix="TARGET#")
        policy["targets"] = [_strip_db_keys(t) for t in target_items]
        data.append(policy)
    return _json_response(200, {"data": data})


def get_collection_status(event: dict, claims: dict) -> dict:
    """GET /api/collection-status — last collection timestamp and status."""
    items = query_by_pk("COLLECTION", sk_prefix="LATEST")
    data = _strip_db_keys(items[0]) if items else {}
    return _json_response(200, {"data": data})


def get_observations(event: dict, claims: dict) -> dict:
    """GET /api/observations — observations with severity/status filters via GSI1."""
    params = _get_query_params(event)
    severity = params.get("severity")
    status = params.get("status")

    if severity:
        items = query_gsi1(f"OBS#SEVERITY#{severity}")
    elif status:
        items = query_gsi1(f"OBS#STATUS#{status}")
    else:
        items = scan_by_pk_prefix("OBSERVATION#", sk_value="META")

    observations = [deserialize(item, Observation) for item in items]
    return _json_response(200, {"data": [asdict(o) for o in observations]})


def get_deployments(event: dict, claims: dict) -> dict:
    """GET /api/deployments — deployment requests with status filter via GSI1."""
    params = _get_query_params(event)
    status = params.get("status")

    if status:
        items = query_gsi1(f"DEPLOY#STATUS#{status}")
    else:
        items = scan_by_pk_prefix("DEPLOYMENT#", sk_value="META")

    deployments = [deserialize(item, DeploymentRequest) for item in items]
    return _json_response(200, {"data": [asdict(d) for d in deployments]})
