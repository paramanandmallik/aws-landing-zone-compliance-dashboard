"""Write route handlers for the Governance API.

Each handler takes (event, claims) and returns a response dict with
statusCode, headers, and body.

Requirements: 1.8, 4.1, 4.2, 4.3, 4.4, 6.3, 6.4, 6.5
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone

import boto3

from backend.shared.dynamodb import deserialize, put_item, query_by_pk, serialize
from backend.shared.models import DeploymentRequest, Observation

logger = logging.getLogger(__name__)

DATA_COLLECTOR_FUNCTION = os.environ.get("DATA_COLLECTOR_FUNCTION", "")
DEPLOYMENT_STATE_MACHINE_ARN = os.environ.get("DEPLOYMENT_STATE_MACHINE_ARN", "")
AGENT_ID = os.environ.get("AGENT_ID", "")
GOVERNANCE_API_URL = os.environ.get("GOVERNANCE_API_URL", "")

_lambda_client = None
_sfn_client = None
_bedrock_agent_client = None


def _get_lambda_client():
    global _lambda_client
    if _lambda_client is None:
        _lambda_client = boto3.client("lambda")
    return _lambda_client


def _get_sfn_client():
    global _sfn_client
    if _sfn_client is None:
        _sfn_client = boto3.client("stepfunctions")
    return _sfn_client


def _get_bedrock_agent_client():
    global _bedrock_agent_client
    if _bedrock_agent_client is None:
        _bedrock_agent_client = boto3.client("bedrock-agent-runtime")
    return _bedrock_agent_client


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


def _parse_body(event: dict) -> dict | None:
    """Parse JSON body from the API Gateway event. Returns None on failure."""
    raw = event.get("body", "")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _extract_path_id(event: dict) -> str:
    """Extract the resource ID from paths like /api/observations/{id}/accept."""
    path = event.get("requestContext", {}).get("http", {}).get("path", "")
    parts = path.strip("/").split("/")
    # Pattern: api/observations/{id}/action → id is at index 2
    if len(parts) >= 4:
        return parts[2]
    return ""


def trigger_collect(event: dict, claims: dict) -> dict:
    """POST /api/collect — invoke Data Collector Lambda asynchronously."""
    try:
        client = _get_lambda_client()
        client.invoke(
            FunctionName=DATA_COLLECTOR_FUNCTION,
            InvocationType="Event",
            Payload=json.dumps({"source": "manual", "requested_by": claims.get("sub", "")}),
        )
        return _json_response(200, {"message": "Data collection started"})
    except Exception:
        logger.exception("Failed to invoke Data Collector")
        return _json_response(502, {"error": "Failed to start data collection"})


def execute_direct(event: dict, claims: dict) -> dict:
    """POST /api/execute — execute a control/SCP action directly without approval."""
    body = _parse_body(event)
    if not body:
        return _json_response(400, {"error": "Bad request", "message": "Missing or invalid JSON body"})

    action_type = body.get("type")
    parameters = body.get("parameters")
    if not action_type or not parameters:
        return _json_response(400, {"error": "Bad request", "message": "Fields 'type' and 'parameters' are required"})

    valid_types = {"enable_control", "disable_control", "create_scp", "update_scp", "attach_scp", "detach_scp"}
    if action_type not in valid_types:
        return _json_response(400, {"error": "Bad request", "message": f"Invalid type. Must be one of: {', '.join(sorted(valid_types))}"})

    # Execute directly via the Deployment Executor Lambda
    deployment_id = str(uuid.uuid4())
    try:
        client = _get_lambda_client()
        resp = client.invoke(
            FunctionName=os.environ.get("DEPLOYMENT_EXECUTOR_FUNCTION", ""),
            InvocationType="RequestResponse",
            Payload=json.dumps({"deployment_id": deployment_id, "type": action_type, "parameters": parameters}),
        )
        result = json.loads(resp["Payload"].read().decode())
        if result.get("status") == "success":
            # Record the completed deployment
            now = datetime.now(timezone.utc).isoformat()
            deployment = DeploymentRequest(
                id=deployment_id, type=action_type, parameters=parameters,
                status="completed", requested_by=claims.get("sub", "unknown"),
                requested_at=now, completed_at=now,
            )
            try:
                put_item(deployment)
            except Exception:
                logger.warning("Failed to record deployment %s", deployment_id)
            return _json_response(200, {"data": {"id": deployment_id, "status": "completed", "message": f"{action_type} executed successfully"}})
        else:
            error_msg = result.get("error", "Execution failed")
            return _json_response(400, {"error": error_msg})
    except Exception as exc:
        logger.exception("Direct execution failed")
        return _json_response(502, {"error": f"Execution failed: {str(exc)}"})


def create_deployment(event: dict, claims: dict) -> dict:
    """POST /api/deployments — validate, start Step Functions, store record."""
    body = _parse_body(event)
    if not body:
        return _json_response(400, {"error": "Bad request", "message": "Missing or invalid JSON body"})

    deploy_type = body.get("type")
    parameters = body.get("parameters")
    if not deploy_type or not parameters:
        return _json_response(400, {
            "error": "Bad request",
            "message": "Fields 'type' and 'parameters' are required",
        })

    valid_types = {"enable_control", "disable_control", "create_scp", "update_scp", "attach_scp", "detach_scp"}
    if deploy_type not in valid_types:
        return _json_response(400, {
            "error": "Bad request",
            "message": f"Invalid deployment type. Must be one of: {', '.join(sorted(valid_types))}",
        })

    deployment_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    deployment = DeploymentRequest(
        id=deployment_id,
        type=deploy_type,
        parameters=parameters,
        status="pending",
        requested_by=claims.get("sub", "unknown"),
        requested_at=now,
    )

    try:
        sfn = _get_sfn_client()
        sfn.start_execution(
            stateMachineArn=DEPLOYMENT_STATE_MACHINE_ARN,
            name=deployment_id,
            input=json.dumps({
                "deployment_id": deployment_id,
                "type": deploy_type,
                "parameters": parameters,
                "requested_by": claims.get("sub", "unknown"),
            }),
        )
    except Exception:
        logger.exception("Failed to start Step Functions execution")
        return _json_response(502, {"error": "Deployment submission failed"})

    try:
        put_item(deployment)
    except Exception:
        logger.exception("Failed to store deployment record")
        return _json_response(500, {"error": "Internal server error"})

    return _json_response(201, {"data": {"id": deployment_id, "status": "pending"}})


def accept_observation(event: dict, claims: dict) -> dict:
    """POST /api/observations/{id}/accept — update status, submit remediation."""
    obs_id = _extract_path_id(event)
    if not obs_id:
        return _json_response(400, {"error": "Bad request", "message": "Missing observation ID"})

    items = query_by_pk(f"OBSERVATION#{obs_id}", sk_prefix="META")
    if not items:
        return _json_response(404, {"error": "Not found"})

    observation = deserialize(items[0], Observation)
    observation.status = "accepted"

    try:
        put_item(observation)
    except Exception:
        logger.exception("Failed to update observation")
        return _json_response(500, {"error": "Internal server error"})

    # If a remediation action exists, execute it directly
    if observation.remediation_action:
        try:
            deployment_id = str(uuid.uuid4())
            client = _get_lambda_client()
            resp = client.invoke(
                FunctionName=os.environ.get("DEPLOYMENT_EXECUTOR_FUNCTION", ""),
                InvocationType="RequestResponse",
                Payload=json.dumps({
                    "deployment_id": deployment_id,
                    "type": observation.remediation_action.get("type", ""),
                    "parameters": observation.remediation_action.get("parameters", {}),
                }),
            )
            result = json.loads(resp["Payload"].read().decode())
            if result.get("status") == "success":
                # Record the deployment
                now = datetime.now(timezone.utc).isoformat()
                dep = DeploymentRequest(
                    id=deployment_id,
                    type=observation.remediation_action.get("type", ""),
                    parameters=observation.remediation_action.get("parameters", {}),
                    status="completed",
                    requested_by=claims.get("sub", "unknown"),
                    requested_at=now, completed_at=now,
                )
                try: put_item(dep)
                except: pass
                return _json_response(200, {
                    "data": {"id": obs_id, "status": "accepted", "remediation": "completed"},
                })
            else:
                return _json_response(200, {
                    "data": {"id": obs_id, "status": "accepted"},
                    "warning": f"Observation accepted but remediation failed: {result.get('error', 'unknown')}",
                })
        except Exception:
            logger.exception("Failed to execute remediation")
            return _json_response(200, {
                "data": {"id": obs_id, "status": "accepted"},
                "warning": "Observation accepted but remediation execution failed",
            })

    return _json_response(200, {"data": {"id": obs_id, "status": "accepted"}})


def dismiss_observation(event: dict, claims: dict) -> dict:
    """POST /api/observations/{id}/dismiss — update status with justification."""
    obs_id = _extract_path_id(event)
    if not obs_id:
        return _json_response(400, {"error": "Bad request", "message": "Missing observation ID"})

    body = _parse_body(event)
    if not body or not body.get("justification"):
        return _json_response(400, {
            "error": "Bad request",
            "message": "Field 'justification' is required",
        })

    items = query_by_pk(f"OBSERVATION#{obs_id}", sk_prefix="META")
    if not items:
        return _json_response(404, {"error": "Not found"})

    observation = deserialize(items[0], Observation)
    observation.status = "dismissed"
    observation.dismissed_by = claims.get("sub", "unknown")
    observation.dismissal_justification = body["justification"]

    try:
        put_item(observation)
    except Exception:
        logger.exception("Failed to update observation")
        return _json_response(500, {"error": "Internal server error"})

    return _json_response(200, {"data": {"id": obs_id, "status": "dismissed"}})


def evaluate_agent(event: dict, claims: dict) -> dict:
    """POST /api/agent/evaluate — invoke Compliance Agent.

    Uses Bedrock AgentCore invoke_agent_runtime if AGENT_ID is configured,
    otherwise falls back to async Lambda invocation with Strands SDK.
    """
    evaluation_id = str(uuid.uuid4())

    # Try AgentCore runtime first
    if AGENT_ID and AGENT_ID != "PLACEHOLDER":
        try:
            ac = boto3.client("bedrock-agentcore")
            ac.invoke_agent_runtime(
                agentRuntimeId=AGENT_ID,
                sessionId=evaluation_id,
                input={
                    "text": "Evaluate the current AWS governance posture for all accounts "
                            "against NIST CSF v2.0 and RBI Master Direction on IT Governance. "
                            "Produce per-account observations with framework references."
                },
            )
            return _json_response(200, {
                "data": {"evaluation_id": evaluation_id, "status": "evaluation_started",
                         "message": "AgentCore evaluation started. Observations will appear shortly."},
            })
        except Exception:
            logger.warning("AgentCore invocation failed, falling back to Lambda-based agent")

    # Fallback: invoke via Data Collector Lambda (async Strands agent)
    try:
        client = _get_lambda_client()
        client.invoke(
            FunctionName=DATA_COLLECTOR_FUNCTION,
            InvocationType="Event",
            Payload=json.dumps({
                "source": "agent_evaluate",
                "evaluation_id": evaluation_id,
                "governance_api_url": GOVERNANCE_API_URL,
            }),
        )
        return _json_response(200, {
            "data": {"evaluation_id": evaluation_id, "status": "evaluation_started",
                     "message": "Compliance evaluation started. Observations will appear as the agent evaluates each account."},
        })
    except Exception:
        logger.exception("Failed to invoke Compliance Agent")
        return _json_response(502, {"error": "Failed to start compliance evaluation"})


def refresh_catalog(event: dict, claims: dict) -> dict:
    """POST /api/refresh-catalog — trigger data collection for control catalog only."""
    try:
        client = _get_lambda_client()
        client.invoke(
            FunctionName=DATA_COLLECTOR_FUNCTION,
            InvocationType="Event",
            Payload=json.dumps({"source": "catalog_refresh", "requested_by": claims.get("sub", "")}),
        )
        return _json_response(200, {"message": "Control catalog refresh started"})
    except Exception:
        logger.exception("Failed to invoke catalog refresh")
        return _json_response(502, {"error": "Failed to start catalog refresh"})
