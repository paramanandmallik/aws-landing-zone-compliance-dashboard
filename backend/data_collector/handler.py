"""Data Collector Lambda handler — orchestrates governance data collection.

Runs all collectors, writes results to DynamoDB and S3, handles partial failures.
Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8
"""

import json
import logging
import os
from datetime import datetime, timezone

import boto3

from backend.data_collector.collectors.control_tower import (
    collect_baselines,
    collect_controls,
    collect_available_controls,
    collect_landing_zone,
)
from backend.data_collector.collectors.organizations import (
    collect_accounts,
    collect_ous,
    collect_policies,
)
from backend.shared.dynamodb import batch_write, put_item, serialize
from backend.shared.models import (
    Account,
    ControlTowerControl,
    OrganizationalUnit,
    ServiceControlPolicy,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

TABLE_NAME = os.environ.get("GOVERNANCE_TABLE", "GovernanceStore")
BUCKET_NAME = os.environ.get("SNAPSHOT_BUCKET", "SnapshotArchive")

# Collector registry: name -> (function, args_factory)
COLLECTORS = {
    "accounts": collect_accounts,
    "ous": collect_ous,
    "policies": collect_policies,
    "controls": collect_controls,
    "available_controls": collect_available_controls,
    "landing_zone": collect_landing_zone,
    "baselines": collect_baselines,
}


def _run_collectors(session) -> tuple[dict, list[str]]:
    """Run all collectors, return (results_dict, errors_list)."""
    results = {}
    errors = []
    for name, fn in COLLECTORS.items():
        try:
            results[name] = fn(session)
        except Exception as exc:
            logger.error("Collector '%s' failed: %s", name, exc, exc_info=True)
            errors.append(name)
            results[name] = [] if name != "landing_zone" else {}
    return results, errors


def _build_entities(results: dict) -> list:
    """Convert raw collector dicts to model dataclasses for DynamoDB storage."""
    entities = []

    # OUs
    for ou in results.get("ous", []):
        entities.append(OrganizationalUnit(
            id=ou["id"], name=ou["name"], arn=ou["arn"],
            parent_ou_id=ou.get("parent_ou_id"), path=ou["path"],
        ))

    # Build OU lookup for account mapping
    ou_lookup = {ou["id"]: ou for ou in results.get("ous", [])}

    # Accounts — resolve ou_path from ou_id
    for acct in results.get("accounts", []):
        ou_id = acct.get("ou_id", "")
        ou_path = ""
        if ou_id and ou_id in ou_lookup:
            ou_path = ou_lookup[ou_id].get("path", "")
        entities.append(Account(
            id=acct["id"], name=acct["name"], email=acct["email"],
            status=acct["status"], arn=acct["arn"],
            ou_id=ou_id, ou_path=ou_path,
            joined_timestamp=acct["joined_timestamp"],
        ))

    # SCPs and other policies
    for pol in results.get("policies", []):
        if pol["type"] == "SERVICE_CONTROL_POLICY":
            entities.append(ServiceControlPolicy(
                id=pol["id"], name=pol["name"], arn=pol["arn"],
                description=pol.get("description", ""), content=pol.get("content", {}),
                type=pol["type"], targets=pol.get("targets", []),
            ))
        # Non-SCP policies stored as raw items below

    # Control Tower controls
    for ctrl in results.get("controls", []):
        # Resolve OU name from target_identifier
        target_id = ctrl.get("target_identifier", "")
        ou_name = ""
        # target_identifier is an OU ARN; extract OU id
        ou_id = target_id.rsplit("/", 1)[-1] if "/" in target_id else target_id
        if ou_id in ou_lookup:
            ou_name = ou_lookup[ou_id]["name"]
        entities.append(ControlTowerControl(
            control_identifier=ctrl["control_identifier"],
            status=ctrl["status"], ou_id=ou_id, ou_name=ou_name,
            drift_status=ctrl.get("drift_status"),
        ))

    return entities


def _derive_service(impl_id: str, governed_resources: list[str]) -> str:
    """Derive the AWS service name from implementation ID or governed resources."""
    text = (impl_id + " " + " ".join(str(r) for r in governed_resources)).upper()
    service_map = [
        ("S3", "S3"), ("EC2", "EC2"), ("RDS", "RDS"), ("IAM", "IAM"),
        ("LAMBDA", "Lambda"), ("EBS", "EBS"), ("VPC", "VPC"), ("ELB", "ELB"),
        ("CLOUDTRAIL", "CloudTrail"), ("CLOUDWATCH", "CloudWatch"), ("CONFIG", "Config"),
        ("KMS", "KMS"), ("SNS", "SNS"), ("SQS", "SQS"), ("DYNAMODB", "DynamoDB"),
        ("REDSHIFT", "Redshift"), ("ELASTICSEARCH", "OpenSearch"), ("OPENSEARCH", "OpenSearch"),
        ("SAGEMAKER", "SageMaker"), ("ECS", "ECS"), ("EKS", "EKS"), ("ECR", "ECR"),
        ("GUARDDUTY", "GuardDuty"), ("SECURITYHUB", "Security Hub"), ("BACKUP", "Backup"),
        ("CLOUDFRONT", "CloudFront"), ("APIGATEWAY", "API Gateway"), ("CODEBUILD", "CodeBuild"),
        ("SECRETSMANAGER", "Secrets Manager"), ("SSM", "Systems Manager"),
        ("WAFV2", "WAF"), ("WAF", "WAF"), ("NETWORK", "Networking"),
        ("AUTOSCALING", "Auto Scaling"), ("EMR", "EMR"), ("GLUE", "Glue"),
    ]
    for keyword, service in service_map:
        if keyword in text:
            return service
    return "General"


def _build_ou_account_items(results: dict) -> list[dict]:
    """Build OU-Account relationship items and available control catalog items."""
    items = []
    for acct in results.get("accounts", []):
        ou_id = acct.get("ou_id", "")
        if ou_id:
            items.append({
                "PK": f"OU#{ou_id}",
                "SK": f"ACCOUNT#{acct['id']}",
                "entity_type": "OUAccountMapping",
                "account_id": acct["id"],
            })
    # Available controls catalog
    for ctrl in results.get("available_controls", []):
        # Derive service from implementation_id or governed_resources
        impl_id = ctrl.get("implementation_id", "")
        governed = ctrl.get("governed_resources", [])
        service = _derive_service(impl_id, governed)
        items.append({
            "PK": f"AVAILABLE_CONTROL#{ctrl['arn']}",
            "SK": "META",
            "entity_type": "AvailableControl",
            "arn": ctrl["arn"],
            "name": ctrl.get("name", ""),
            "description": ctrl.get("description", ""),
            "behavior": ctrl.get("behavior", ""),
            "severity": ctrl.get("severity", ""),
            "implementation_type": ctrl.get("implementation_type", ""),
            "implementation_id": impl_id,
            "service": service,
            "governed_resources": json.dumps(governed),
        })
    return items


def _write_to_dynamodb(entities: list, ou_account_items: list[dict]) -> None:
    """Batch write entities and raw items to DynamoDB."""
    if entities:
        batch_write(entities)

    # Write OU-Account mapping items directly (not model-backed)
    if ou_account_items:
        table = boto3.resource("dynamodb").Table(TABLE_NAME)
        with table.batch_writer() as batch:
            for item in ou_account_items:
                batch.put_item(Item=item)


def _write_snapshot(results: dict, timestamp: str, status: str, errors: list[str]) -> str:
    """Write composite JSON snapshot to S3. Returns the S3 key."""
    dt = datetime.fromisoformat(timestamp)
    key = f"snapshots/{dt.year}/{dt.month:02d}/{dt.day:02d}/{timestamp}.json"
    snapshot = {
        "timestamp": timestamp,
        "collection_status": status,
        "errors": errors,
        "data": {
            "organizational_units": results.get("ous", []),
            "accounts": results.get("accounts", []),
            "scps": [p for p in results.get("policies", []) if p.get("type") == "SERVICE_CONTROL_POLICY"],
            "controls": results.get("controls", []),
            "policies": [p for p in results.get("policies", []) if p.get("type") != "SERVICE_CONTROL_POLICY"],
            "landing_zone": results.get("landing_zone", {}),
            "baselines": results.get("baselines", []),
        },
    }
    s3 = boto3.client("s3")
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=key,
        Body=json.dumps(snapshot, default=str),
        ContentType="application/json",
    )
    logger.info("Wrote snapshot to s3://%s/%s", BUCKET_NAME, key)
    return key


def _update_collection_latest(timestamp: str, status: str, errors: list[str]) -> None:
    """Update COLLECTION#LATEST record in DynamoDB."""
    table = boto3.resource("dynamodb").Table(TABLE_NAME)
    table.put_item(Item={
        "PK": "COLLECTION",
        "SK": "LATEST",
        "entity_type": "CollectionStatus",
        "timestamp": timestamp,
        "status": status,
        "errors": json.dumps(errors),
    })


def _run_agent_evaluation(event: dict) -> dict:
    """Run the Strands compliance agent for governance evaluation."""
    import os as _os
    evaluation_id = event.get("evaluation_id", "unknown")
    api_url = event.get("governance_api_url", "")

    logger.info("Starting agent evaluation %s", evaluation_id)

    # Set environment for the agent
    _os.environ["EVALUATION_ID"] = evaluation_id
    _os.environ["GOVERNANCE_API_URL"] = api_url
    _os.environ["GOVERNANCE_TABLE"] = TABLE_NAME

    try:
        from backend.compliance_agent.agent import run_evaluation
        result = run_evaluation(
            "Evaluate the current AWS governance posture for all accounts against "
            "NIST CSF v2.0 and RBI Master Direction on IT Governance. "
            "Produce per-account observations with framework references and specific "
            "Control Tower controls to enable as remediation."
        )
        logger.info("Agent evaluation %s completed: %s", evaluation_id, result.get("status"))
        return {"status": result.get("status", "error"), "evaluation_id": evaluation_id}
    except Exception as exc:
        logger.exception("Agent evaluation %s failed", evaluation_id)
        return {"status": "error", "evaluation_id": evaluation_id, "error": str(exc)}


def handler(event, context) -> dict:
    """Lambda entry point for data collection and agent evaluation.

    event may contain:
      - source: "schedule" | "manual" | "catalog_refresh" | "agent_evaluate"
      - evaluation_id: (for agent_evaluate) unique ID for this evaluation
      - governance_api_url: (for agent_evaluate) API URL for the agent to call back
    Returns: {"status": "complete"|"partial", "errors": [...], "timestamp": "ISO8601"}
    """
    source = event.get("source", "unknown")

    # Agent evaluation mode — run the Strands compliance agent
    if source == "agent_evaluate":
        return _run_agent_evaluation(event)

    timestamp = datetime.now(timezone.utc).isoformat()
    logger.info("Starting data collection at %s (source=%s)", timestamp, source)

    session = boto3.Session()

    # 1. Run all collectors
    results, errors = _run_collectors(session)

    # 2. Determine status
    status = "complete" if not errors else "partial"

    # 3. Convert to model entities and write to DynamoDB
    try:
        entities = _build_entities(results)
        ou_account_items = _build_ou_account_items(results)
        _write_to_dynamodb(entities, ou_account_items)
    except Exception as exc:
        logger.error("DynamoDB write failed: %s", exc, exc_info=True)
        errors.append("dynamodb_write")
        status = "partial"

    # 4. Write S3 snapshot
    try:
        _write_snapshot(results, timestamp, status, errors)
    except Exception as exc:
        logger.error("S3 snapshot write failed: %s", exc, exc_info=True)
        errors.append("s3_snapshot")
        status = "partial"

    # 5. Update COLLECTION#LATEST
    try:
        _update_collection_latest(timestamp, status, errors)
    except Exception as exc:
        logger.error("Failed to update COLLECTION#LATEST: %s", exc, exc_info=True)
        errors.append("collection_latest_update")
        status = "partial"

    result = {"status": status, "errors": errors, "timestamp": timestamp}
    logger.info("Data collection finished: %s", result)
    return result
