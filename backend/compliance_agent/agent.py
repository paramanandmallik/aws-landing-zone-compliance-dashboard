"""Compliance Agent — Strands Agents SDK agent for governance evaluation.

Evaluates AWS governance posture per-account against:
1. NIST Cybersecurity Framework controls
2. RBI Master Direction on IT Governance recommendations

Imports are lazy to support fast cold-start on AgentCore (30s init limit).
"""

import json
import logging
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from uuid import uuid4

logger = logging.getLogger(__name__)

GOVERNANCE_API_URL = os.environ.get("GOVERNANCE_API_URL", "")
MAX_RETRIES = 3
VALID_SEVERITIES = ("critical", "high", "medium", "low")


def _db_scan(pk_prefix: str, sk_value: str = None) -> list[dict]:
    """Scan DynamoDB directly for items by PK prefix."""
    import boto3
    from boto3.dynamodb.conditions import Attr
    table_name = os.environ.get("GOVERNANCE_TABLE", "GovernanceStore")
    table = boto3.resource("dynamodb").Table(table_name)
    filter_expr = Attr("PK").begins_with(pk_prefix)
    if sk_value:
        filter_expr = filter_expr & Attr("SK").eq(sk_value)
    items = []
    resp = table.scan(FilterExpression=filter_expr)
    items.extend(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = table.scan(FilterExpression=filter_expr, ExclusiveStartKey=resp["LastEvaluatedKey"])
        items.extend(resp.get("Items", []))
    # Strip DynamoDB keys
    return [{k: v for k, v in item.items() if k not in ("PK", "SK", "entity_type", "GSI1PK", "GSI1SK")} for item in items]


def _put_observation(obs):
    """Write observation to DynamoDB without importing shared module at top level."""
    import boto3
    table_name = os.environ.get("GOVERNANCE_TABLE", "GovernanceStore")
    table = boto3.resource("dynamodb").Table(table_name)
    from dataclasses import asdict
    item = asdict(obs)
    # Add DynamoDB keys
    item["PK"] = f"OBSERVATION#{obs.id}"
    item["SK"] = "META"
    item["entity_type"] = "Observation"
    item["GSI1PK"] = f"OBS#SEVERITY#{obs.severity}"
    item["GSI1SK"] = obs.created_at
    # Serialize lists/dicts
    for k, v in list(item.items()):
        if v is None:
            del item[k]
        elif isinstance(v, (dict, list)):
            item[k] = json.dumps(v)
    table.put_item(Item=item)


def _build_agent():
    """Lazy-build the Strands agent to avoid heavy imports at module load."""
    from strands import Agent, tool
    from strands.models.bedrock import BedrockModel
    from backend.compliance_agent.prompts import SYSTEM_PROMPT

    # Import Observation here too
    from backend.shared.models import Observation as ObsModel

    @tool
    def get_governance_data(data_type: str) -> dict:
        """Retrieve governance data directly from DynamoDB.
        Args:
            data_type: One of 'ous', 'accounts', 'scps', 'controls'
        """
        type_map = {
            "ous": ("OU#", "META"),
            "accounts": ("ACCOUNT#", "META"),
            "scps": ("SCP#", "META"),
            "controls": ("CONTROL#", None),
        }
        if data_type not in type_map:
            return {"error": f"Invalid data_type. Must be one of {list(type_map.keys())}"}
        pk_prefix, sk = type_map[data_type]
        items = _db_scan(pk_prefix, sk)
        # Parse JSON fields
        for item in items:
            for k, v in list(item.items()):
                if isinstance(v, str) and v.startswith(('[', '{')):
                    try: item[k] = json.loads(v)
                    except: pass
        return {"data": items}

    @tool
    def get_account_services(account_id: str) -> dict:
        """Get AWS services actively used by a specific account.
        Args:
            account_id: The AWS account ID
        """
        return {
            "account_id": account_id,
            "services": ["IAM", "S3", "EC2", "VPC", "CloudTrail", "CloudWatch",
                         "Lambda", "RDS", "KMS", "SNS", "SQS", "DynamoDB"],
            "note": "Service list based on common patterns. Connect Config aggregator for precise inventory."
        }

    @tool
    def create_observation(
        finding: str, severity: str, affected_resources: list[str],
        recommendation: str, framework_ref: str = "",
        remediation_action: dict | None = None,
    ) -> dict:
        """Store a compliance observation with framework references.
        Args:
            finding: Description of the compliance gap
            severity: One of 'critical', 'high', 'medium', 'low'
            affected_resources: List of affected account IDs or resource ARNs
            recommendation: Specific remediation steps
            framework_ref: Framework reference (e.g. 'NIST CSF PR.AC-1 | RBI 3.1.a')
            remediation_action: Optional auto-remediation action dict
        """
        errors = []
        if not finding: errors.append("finding is required")
        if severity not in VALID_SEVERITIES: errors.append(f"severity must be one of {VALID_SEVERITIES}")
        if not affected_resources: errors.append("affected_resources is required")
        if not recommendation: errors.append("recommendation is required")
        if errors:
            return {"error": "; ".join(errors)}

        obs_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        full_finding = f"[{framework_ref}] {finding}" if framework_ref else finding

        obs = ObsModel(
            id=obs_id, finding=full_finding, severity=severity,
            affected_resources=affected_resources, recommendation=recommendation,
            remediation_action=remediation_action, status="open",
            snapshot_id=os.environ.get("SNAPSHOT_ID", "latest"),
            evaluation_id=os.environ.get("EVALUATION_ID", str(uuid4())),
            created_at=now,
        )
        _put_observation(obs)
        return {"id": obs_id, "status": "created"}

    model = BedrockModel(model_id="amazon.nova-pro-v1:0", max_tokens=4096)
    return Agent(
        model=model,
        tools=[get_governance_data, get_account_services, create_observation],
        system_prompt=SYSTEM_PROMPT,
    )


# Global lazy singleton
_agent = None

def _get_agent():
    global _agent
    if _agent is None:
        _agent = _build_agent()
    return _agent


def run_evaluation(prompt: str = "Evaluate the current AWS governance posture.") -> dict:
    """Invoke the compliance agent with retry logic."""
    agent = _get_agent()
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            result = agent(prompt)
            return {"status": "success", "result": str(result)}
        except Exception as exc:
            last_error = exc
            if attempt < MAX_RETRIES - 1:
                logger.warning("Agent failed (attempt %d/%d): %s", attempt + 1, MAX_RETRIES, exc)
                time.sleep(2 ** attempt)
    logger.error("Agent failed after %d attempts: %s", MAX_RETRIES, last_error)
    return {"status": "error", "error": str(last_error)}
