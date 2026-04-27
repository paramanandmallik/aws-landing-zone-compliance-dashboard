#!/usr/bin/env python3
"""CDK app entry point for the AWS Governance & Compliance Platform."""

import aws_cdk as cdk

from stacks.governance_stack import GovernanceStack

app = cdk.App()
GovernanceStack(app, "GovernancePlatformStack")
app.synth()
