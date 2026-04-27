"""Deploy the Compliance Agent to Bedrock AgentCore Runtime.

Run this script once to register the agent with AgentCore.
After deployment, the agent can be invoked via the AgentCore runtime API.

Usage:
    python -m backend.compliance_agent.deploy_agentcore
"""

import json
import boto3
import os

AGENT_NAME = "GovernanceComplianceAgent"
REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")


def deploy():
    acc = boto3.client("bedrock-agentcore-control", region_name=REGION)

    # Check if agent runtime already exists
    existing = acc.list_agent_runtimes()
    for rt in existing.get("agentRuntimes", []):
        if rt.get("agentRuntimeName") == AGENT_NAME:
            print(f"Agent runtime already exists: {rt['agentRuntimeId']}")
            return rt["agentRuntimeId"]

    # Create the agent runtime
    print("Creating AgentCore agent runtime...")
    resp = acc.create_agent_runtime(
        agentRuntimeName=AGENT_NAME,
        description="Autonomous compliance agent that evaluates AWS governance posture "
                    "against NIST CSF v2.0 and RBI Master Direction on IT Governance. "
                    "Produces per-account observations with framework references.",
        agentRuntimeArtifact={
            "containerConfiguration": {
                "containerUri": "strands-agents",  # Strands SDK based agent
            }
        },
        modelId="anthropic.claude-sonnet-4-20250514",
        roleArn=os.environ.get("AGENT_ROLE_ARN", ""),
        environmentVariables={
            "GOVERNANCE_API_URL": os.environ.get("GOVERNANCE_API_URL", ""),
            "GOVERNANCE_TABLE": os.environ.get("GOVERNANCE_TABLE", "GovernanceStore"),
        },
    )
    runtime_id = resp["agentRuntimeId"]
    print(f"Created agent runtime: {runtime_id}")

    # Create an endpoint for the runtime
    print("Creating agent runtime endpoint...")
    ep_resp = acc.create_agent_runtime_endpoint(
        agentRuntimeId=runtime_id,
        name=f"{AGENT_NAME}-endpoint",
        description="Primary endpoint for the governance compliance agent",
    )
    endpoint_id = ep_resp.get("agentRuntimeEndpointId", "")
    print(f"Created endpoint: {endpoint_id}")

    return runtime_id


if __name__ == "__main__":
    runtime_id = deploy()
    print(f"\nAgent Runtime ID: {runtime_id}")
    print("Set this as the AGENT_ID environment variable on the Governance API Lambda.")
