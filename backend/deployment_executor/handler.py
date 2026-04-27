"""Deployment Executor Lambda — executes AWS API calls for Step Functions."""

import logging

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _enable_control(params: dict) -> dict:
    client = boto3.client("controltower")
    return client.enable_control(
        controlIdentifier=params["controlIdentifier"],
        targetIdentifier=params["targetIdentifier"],
    )


def _disable_control(params: dict) -> dict:
    client = boto3.client("controltower")
    return client.disable_control(
        controlIdentifier=params["controlIdentifier"],
        targetIdentifier=params["targetIdentifier"],
    )


def _create_scp(params: dict) -> dict:
    client = boto3.client("organizations")
    return client.create_policy(
        Content=params["Content"],
        Description=params.get("Description", ""),
        Name=params["Name"],
        Type="SERVICE_CONTROL_POLICY",
    )


def _update_scp(params: dict) -> dict:
    client = boto3.client("organizations")
    kwargs = {"PolicyId": params["PolicyId"]}
    if "Content" in params:
        kwargs["Content"] = params["Content"]
    if "Name" in params:
        kwargs["Name"] = params["Name"]
    if "Description" in params:
        kwargs["Description"] = params["Description"]
    return client.update_policy(**kwargs)


def _attach_scp(params: dict) -> dict:
    client = boto3.client("organizations")
    return client.attach_policy(
        PolicyId=params["PolicyId"],
        TargetId=params["TargetId"],
    )


def _detach_scp(params: dict) -> dict:
    client = boto3.client("organizations")
    return client.detach_policy(
        PolicyId=params["PolicyId"],
        TargetId=params["TargetId"],
    )


_DISPATCH = {
    "enable_control": _enable_control,
    "disable_control": _disable_control,
    "create_scp": _create_scp,
    "update_scp": _update_scp,
    "attach_scp": _attach_scp,
    "detach_scp": _detach_scp,
}


def handler(event, context):
    """Execute a deployment action on behalf of Step Functions.

    Event shape:
        {
            "deployment_id": "uuid",
            "type": "enable_control|disable_control|create_scp|update_scp|attach_scp|detach_scp",
            "parameters": { ... }
        }
    """
    deployment_id = event.get("deployment_id", "unknown")
    deployment_type = event.get("type")
    parameters = event.get("parameters", {})

    logger.info("Executing deployment %s type=%s", deployment_id, deployment_type)

    executor = _DISPATCH.get(deployment_type)
    if executor is None:
        return {
            "status": "failed",
            "deployment_id": deployment_id,
            "error": f"Unknown deployment type: {deployment_type}",
        }

    try:
        executor(parameters)
        return {"status": "success", "deployment_id": deployment_id}
    except Exception as exc:
        logger.exception("Deployment %s failed", deployment_id)
        return {
            "status": "failed",
            "deployment_id": deployment_id,
            "error": str(exc),
        }
