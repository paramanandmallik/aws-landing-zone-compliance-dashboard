"""Shared data models for the AWS Governance & Compliance Platform."""

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class OrganizationalUnit:
    id: str
    name: str
    arn: str
    parent_ou_id: str | None
    path: str  # e.g., "Root/Security/Prod"


@dataclass
class Account:
    id: str
    name: str
    email: str
    status: Literal["ACTIVE", "SUSPENDED", "PENDING_CLOSURE"]
    arn: str
    ou_id: str
    ou_path: str
    joined_timestamp: str


@dataclass
class ServiceControlPolicy:
    id: str
    name: str
    arn: str
    description: str
    content: dict  # Policy document
    type: str
    targets: list[dict] = field(default_factory=list)  # [{target_id, target_type, target_name}]


@dataclass
class ControlTowerControl:
    control_identifier: str
    status: Literal["ENABLED", "FAILED", "UNDER_CHANGE"]
    ou_id: str
    ou_name: str
    drift_status: str | None


@dataclass
class Observation:
    id: str
    finding: str
    severity: Literal["critical", "high", "medium", "low"]
    affected_resources: list[str]
    recommendation: str
    remediation_action: dict | None
    status: Literal["open", "accepted", "dismissed"]
    snapshot_id: str
    evaluation_id: str
    created_at: str
    dismissed_by: str | None = None
    dismissal_justification: str | None = None


@dataclass
class DeploymentRequest:
    id: str
    type: Literal[
        "enable_control", "disable_control",
        "create_scp", "update_scp",
        "attach_scp", "detach_scp",
    ]
    parameters: dict
    status: Literal["pending", "approved", "rejected", "executing", "completed", "failed"]
    requested_by: str
    requested_at: str
    approved_by: str | None = None
    approved_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    task_token: str | None = None  # Step Functions callback token
