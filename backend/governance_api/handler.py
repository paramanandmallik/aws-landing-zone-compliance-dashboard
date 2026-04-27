"""Governance API Lambda handler — router with role-based access enforcement.

Manual path/method dispatch router (no web framework).
Requirements: 2.7, 7.3, 7.4, 4.9
"""

import json
import logging

from backend.governance_api.routes.read_routes import (
    get_accounts,
    get_available_controls,
    get_collection_status,
    get_controls,
    get_deployments,
    get_landing_zone,
    get_observations,
    get_ous,
    get_policies,
    get_scps,
)
from backend.governance_api.routes.write_routes import (
    accept_observation,
    create_deployment,
    dismiss_observation,
    evaluate_agent,
    execute_direct,
    refresh_catalog,
    trigger_collect,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

ROLE_HIERARCHY = ["viewer", "administrator"]


CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Authorization,Content-Type",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
}


def _json_response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": CORS_HEADERS,
        "body": json.dumps(body),
    }


def _not_found(event, claims):
    return _json_response(404, {"error": "Not found"})


# --- Route table ---
# (method, path) -> (handler_fn, required_role)
# Paths with {id} parameters use prefix matching below.

ROUTES = {
    ("GET", "/api/ous"): (get_ous, "viewer"),
    ("GET", "/api/accounts"): (get_accounts, "viewer"),
    ("GET", "/api/scps"): (get_scps, "viewer"),
    ("GET", "/api/controls"): (get_controls, "viewer"),
    ("GET", "/api/available-controls"): (get_available_controls, "viewer"),
    ("GET", "/api/landing-zone"): (get_landing_zone, "viewer"),
    ("GET", "/api/policies"): (get_policies, "viewer"),
    ("GET", "/api/collection-status"): (get_collection_status, "viewer"),
    ("POST", "/api/collect"): (trigger_collect, "administrator"),
    ("POST", "/api/execute"): (execute_direct, "administrator"),
    ("POST", "/api/refresh-catalog"): (refresh_catalog, "administrator"),
    ("POST", "/api/deployments"): (create_deployment, "administrator"),
    ("GET", "/api/deployments"): (get_deployments, "viewer"),
    ("GET", "/api/observations"): (get_observations, "viewer"),
    ("POST", "/api/agent/evaluate"): (evaluate_agent, "administrator"),
}

# Prefix routes for paths with {id} parameters
PREFIX_ROUTES = [
    ("POST", "/api/observations/", "/accept", accept_observation, "administrator"),
    ("POST", "/api/observations/", "/dismiss", dismiss_observation, "administrator"),
]


def _match_route(method: str, path: str):
    """Look up route by exact match, then prefix match. Returns (handler_fn, required_role)."""
    exact = ROUTES.get((method, path))
    if exact:
        return exact

    for rt_method, prefix, suffix, handler_fn, role in PREFIX_ROUTES:
        if method == rt_method and path.startswith(prefix) and path.endswith(suffix):
            return handler_fn, role

    return None


def handler(event, context) -> dict:
    """Lambda entry point for the Governance API.

    Extracts HTTP method/path and JWT claims from the API Gateway v2 event,
    enforces role-based access, and dispatches to the matched route handler.
    """
    http_ctx = event.get("requestContext", {}).get("http", {})
    method = http_ctx.get("method", "")
    path = http_ctx.get("path", "")

    claims = (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("jwt", {})
        .get("claims", {})
    )
    role = claims.get("custom:role", "viewer")

    logger.info("Request: %s %s (role=%s)", method, path, role)

    match = _match_route(method, path)
    if match is None:
        return _not_found(event, claims)

    handler_fn, required_role = match

    # Role hierarchy check
    try:
        caller_level = ROLE_HIERARCHY.index(role)
    except ValueError:
        caller_level = 0  # unknown role treated as lowest
    required_level = ROLE_HIERARCHY.index(required_role)

    if caller_level < required_level:
        return _json_response(403, {
            "error": "Forbidden",
            "message": "Administrator role required",
        })

    return handler_fn(event, claims)
