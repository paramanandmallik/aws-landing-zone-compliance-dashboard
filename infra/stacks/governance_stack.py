"""Core CDK stack for the AWS Governance & Compliance Platform."""

import aws_cdk as cdk
from aws_cdk import (
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
    aws_s3_deployment as s3deploy,
    aws_cognito as cognito,
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as apigwv2_integrations,
    aws_apigatewayv2_authorizers as apigwv2_authorizers,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as sfn_tasks,
    aws_events as events,
    aws_events_targets as events_targets,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_cloudwatch as cloudwatch,
    aws_cloudtrail as cloudtrail,
)
from constructs import Construct


class GovernanceStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- DynamoDB: GovernanceStore (single-table design) ---
        self.table = dynamodb.Table(
            self,
            "GovernanceStore",
            table_name="GovernanceStore",
            partition_key=dynamodb.Attribute(name="PK", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="SK", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )
        self.table.add_global_secondary_index(
            index_name="GSI1",
            partition_key=dynamodb.Attribute(name="GSI1PK", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="GSI1SK", type=dynamodb.AttributeType.STRING),
        )

        # --- S3: Frontend hosting bucket ---
        self.frontend_bucket = s3.Bucket(
            self,
            "FrontendBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # --- S3: Snapshot archive bucket ---
        self.snapshot_bucket = s3.Bucket(
            self,
            "SnapshotArchiveBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # --- Cognito: User Pool ---
        self.user_pool = cognito.UserPool(
            self,
            "GovernanceUserPool",
            user_pool_name="GovernanceUserPool",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            custom_attributes={
                "role": cognito.StringAttribute(mutable=True),
            },
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        # --- Cognito: User Pool Client (SRP auth, no secret for SPA) ---
        self.user_pool_client = self.user_pool.add_client(
            "GovernanceUserPoolClient",
            auth_flows=cognito.AuthFlow(user_srp=True),
            generate_secret=False,
        )

        # --- Lambda code asset (shared, excludes non-backend files) ---
        lambda_code = _lambda.Code.from_asset(
            ".",
            exclude=[
                "frontend/*", "node_modules/*", ".venv/*", "cdk.out/*",
                "tests/*", ".kiro/*", ".git/*", ".vscode/*",
                "*.md", "cdk.json", "*.pyc", "__pycache__",
                "lambda_layer/*",
            ],
        )

        # --- Lambda: Data Collector ---
        self.data_collector_fn = _lambda.Function(
            self,
            "DataCollectorFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="backend.data_collector.handler.handler",
            code=lambda_code,
            memory_size=512,
            timeout=cdk.Duration.minutes(15),
            environment={
                "GOVERNANCE_TABLE": self.table.table_name,
                "SNAPSHOT_BUCKET": self.snapshot_bucket.bucket_name,
            },
        )
        self.table.grant_read_write_data(self.data_collector_fn)
        self.snapshot_bucket.grant_put(self.data_collector_fn)
        self.data_collector_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "organizations:List*",
                    "organizations:Describe*",
                    "controltower:List*",
                    "controltower:Get*",
                    "controlcatalog:List*",
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                resources=["*"],
            )
        )

        # --- Lambda: Governance API ---
        self.governance_api_fn = _lambda.Function(
            self,
            "GovernanceApiFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="backend.governance_api.handler.handler",
            code=lambda_code,
            timeout=cdk.Duration.seconds(30),
            environment={
                "GOVERNANCE_TABLE": self.table.table_name,
                "SNAPSHOT_BUCKET": self.snapshot_bucket.bucket_name,
                "DATA_COLLECTOR_FUNCTION": self.data_collector_fn.function_name,
                "AGENT_ID": "PLACEHOLDER",
            },
        )
        self.table.grant_read_write_data(self.governance_api_fn)
        self.snapshot_bucket.grant_read(self.governance_api_fn)
        self.data_collector_fn.grant_invoke(self.governance_api_fn)

        # Grant Governance API permission to invoke the Compliance Agent via Bedrock AgentCore
        self.governance_api_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeAgent"],
                resources=["*"],
            )
        )

        # --- Lambda: Deployment Executor ---
        self.deployment_executor_fn = _lambda.Function(
            self,
            "DeploymentExecutorFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="backend.deployment_executor.handler.handler",
            code=lambda_code,
            timeout=cdk.Duration.minutes(5),
        )
        self.deployment_executor_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "organizations:*",
                    "controltower:Enable*",
                    "controltower:Disable*",
                ],
                resources=["*"],
            )
        )

        # Grant Governance API permission to invoke Deployment Executor directly
        self.deployment_executor_fn.grant_invoke(self.governance_api_fn)
        self.governance_api_fn.add_environment(
            "DEPLOYMENT_EXECUTOR_FUNCTION",
            self.deployment_executor_fn.function_name,
        )

        # --- Step Functions: Deployment Orchestrator ---
        # 1. ValidateRequest — Pass state that validates the deployment request shape
        validate_request = sfn.Pass(
            self, "ValidateRequest",
            comment="Validate deployment request shape",
        )

        # 2. StoreTaskToken — DynamoDB direct integration to store task token
        #    Uses WAIT_FOR_TASK_TOKEN pattern: stores the token in DynamoDB,
        #    then waits for the Governance API to call SendTaskSuccess/Failure.
        store_task_token = sfn_tasks.DynamoPutItem(
            self, "StoreTaskToken",
            table=self.table,
            item={
                "PK": sfn_tasks.DynamoAttributeValue.from_string(
                    sfn.JsonPath.format("DEPLOYMENT#{}", sfn.JsonPath.string_at("$.deployment_id"))
                ),
                "SK": sfn_tasks.DynamoAttributeValue.from_string("TASK_TOKEN"),
                "task_token": sfn_tasks.DynamoAttributeValue.from_string(sfn.JsonPath.task_token),
                "deployment_id": sfn_tasks.DynamoAttributeValue.from_string(
                    sfn.JsonPath.string_at("$.deployment_id")
                ),
            },
            integration_pattern=sfn.IntegrationPattern.WAIT_FOR_TASK_TOKEN,
            heartbeat_timeout=sfn.Timeout.duration(cdk.Duration.hours(24)),
            result_path="$.approval_result",
        )

        # 3. ExecuteDeployment — Lambda task invoking Deployment Executor
        execute_deployment = sfn_tasks.LambdaInvoke(
            self, "ExecuteDeployment",
            lambda_function=self.deployment_executor_fn,
            payload=sfn.TaskInput.from_object({
                "deployment_id": sfn.JsonPath.string_at("$.deployment_id"),
                "type": sfn.JsonPath.string_at("$.type"),
                "parameters": sfn.JsonPath.object_at("$.parameters"),
            }),
            result_path="$.execution_result",
        )

        # 4. RefreshData — Lambda task invoking Data Collector
        refresh_data = sfn_tasks.LambdaInvoke(
            self, "RefreshData",
            lambda_function=self.data_collector_fn,
            payload=sfn.TaskInput.from_object({
                "source": "post_deployment",
            }),
            result_path="$.refresh_result",
        )

        # 5. NotifySuccess — Succeed state
        notify_success = sfn.Succeed(self, "NotifySuccess", comment="Deployment completed successfully")

        # 6. RecordFailure — Fail state (catches ExecuteDeployment errors)
        record_failure = sfn.Fail(
            self, "RecordFailure",
            cause="Deployment execution failed",
            error="DeploymentExecutionError",
        )

        # 7. RecordRejection — Succeed state (from WaitForApproval rejection)
        record_rejection = sfn.Succeed(self, "RecordRejection", comment="Deployment was rejected")

        # 8. RecordTimeout — Fail state (from WaitForApproval timeout)
        record_timeout = sfn.Fail(
            self, "RecordTimeout",
            cause="Approval timed out after 24 hours",
            error="ApprovalTimeoutError",
        )

        # Wire error handling
        # StoreTaskToken (WaitForApproval): rejection via task failure callback, timeout via heartbeat
        store_task_token.add_catch(record_rejection, errors=["RejectedError"], result_path="$.rejection")
        store_task_token.add_catch(record_timeout, errors=["States.Timeout"], result_path="$.timeout")

        # ExecuteDeployment: catch all errors → RecordFailure
        execute_deployment.add_catch(record_failure, errors=["States.ALL"], result_path="$.error")

        # Chain the happy path
        definition = validate_request.next(
            store_task_token
        ).next(
            execute_deployment
        ).next(
            refresh_data
        ).next(
            notify_success
        )

        self.deployment_state_machine = sfn.StateMachine(
            self, "DeploymentOrchestrator",
            state_machine_name="DeploymentOrchestrator",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            timeout=cdk.Duration.hours(25),
        )

        # Grant Governance API Lambda permission to start executions and send task success/failure
        self.deployment_state_machine.grant_start_execution(self.governance_api_fn)
        self.deployment_state_machine.grant_task_response(self.governance_api_fn)

        # Update the Governance API Lambda environment variable with the actual state machine ARN
        self.governance_api_fn.add_environment(
            "DEPLOYMENT_STATE_MACHINE_ARN",
            self.deployment_state_machine.state_machine_arn,
        )

        # --- API Gateway: HTTP API with Cognito JWT Authorizer ---
        issuer = f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool.user_pool_id}"
        authorizer = apigwv2_authorizers.HttpJwtAuthorizer(
            "CognitoAuthorizer",
            jwt_issuer=issuer,
            jwt_audience=[self.user_pool_client.user_pool_client_id],
        )

        self.http_api = apigwv2.HttpApi(
            self,
            "GovernanceHttpApi",
            api_name="GovernanceHttpApi",
            default_authorizer=authorizer,
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_origins=["*"],
                allow_methods=[
                    apigwv2.CorsHttpMethod.GET,
                    apigwv2.CorsHttpMethod.POST,
                    apigwv2.CorsHttpMethod.OPTIONS,
                ],
                allow_headers=["Authorization", "Content-Type"],
                max_age=cdk.Duration.hours(1),
            ),
        )

        gov_api_integration = apigwv2_integrations.HttpLambdaIntegration(
            "GovernanceApiIntegration", self.governance_api_fn
        )

        routes = [
            (apigwv2.HttpMethod.GET, "/api/ous"),
            (apigwv2.HttpMethod.GET, "/api/accounts"),
            (apigwv2.HttpMethod.GET, "/api/scps"),
            (apigwv2.HttpMethod.GET, "/api/controls"),
            (apigwv2.HttpMethod.GET, "/api/available-controls"),
            (apigwv2.HttpMethod.GET, "/api/landing-zone"),
            (apigwv2.HttpMethod.GET, "/api/policies"),
            (apigwv2.HttpMethod.GET, "/api/collection-status"),
            (apigwv2.HttpMethod.POST, "/api/collect"),
            (apigwv2.HttpMethod.POST, "/api/execute"),
            (apigwv2.HttpMethod.POST, "/api/refresh-catalog"),
            (apigwv2.HttpMethod.POST, "/api/deployments"),
            (apigwv2.HttpMethod.GET, "/api/deployments"),
            (apigwv2.HttpMethod.GET, "/api/observations"),
            (apigwv2.HttpMethod.POST, "/api/observations/{id}/accept"),
            (apigwv2.HttpMethod.POST, "/api/observations/{id}/dismiss"),
            (apigwv2.HttpMethod.POST, "/api/agent/evaluate"),
        ]
        for method, path in routes:
            self.http_api.add_routes(
                path=path,
                methods=[method],
                integration=gov_api_integration,
                authorizer=authorizer,
            )

        # Pass the HTTP API URL so the Governance API can relay it to the Compliance Agent
        # Note: We use add_environment after routes are set up, but the URL is a token
        # that resolves at deploy time. To avoid circular dependency, we construct it manually.
        self.governance_api_fn.add_environment(
            "GOVERNANCE_API_URL",
            cdk.Fn.join("", [
                "https://",
                self.http_api.http_api_id,
                ".execute-api.",
                self.region,
                ".amazonaws.com",
            ]),
        )

        # --- EventBridge: Scheduled Data Collection ---
        self.collection_rule = events.Rule(
            self,
            "DataCollectionSchedule",
            rule_name="GovernanceDataCollectionSchedule",
            schedule=events.Schedule.rate(cdk.Duration.hours(6)),
        )
        self.collection_rule.add_target(
            events_targets.LambdaFunction(self.data_collector_fn)
        )

        # --- CloudFront: Distribution for Frontend SPA ---
        self.distribution = cloudfront.Distribution(
            self,
            "FrontendDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(
                    self.frontend_bucket,
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            ),
            default_root_object="index.html",
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=cdk.Duration.seconds(0),
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=cdk.Duration.seconds(0),
                ),
            ],
        )

        # --- S3 Deployment: Frontend assets with CloudFront invalidation ---
        self.frontend_deployment = s3deploy.BucketDeployment(
            self,
            "FrontendDeployment",
            sources=[s3deploy.Source.asset("frontend/build")],
            destination_bucket=self.frontend_bucket,
            distribution=self.distribution,
            distribution_paths=["/*"],
        )

        # --- CloudWatch Alarms ---
        self.data_collector_error_alarm = cloudwatch.Alarm(
            self,
            "DataCollectorErrorAlarm",
            alarm_name="DataCollectorErrors",
            metric=self.data_collector_fn.metric_errors(
                period=cdk.Duration.minutes(5),
            ),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
        )

        self.governance_api_error_alarm = cloudwatch.Alarm(
            self,
            "GovernanceApiErrorAlarm",
            alarm_name="GovernanceApiErrors",
            metric=self.governance_api_fn.metric_errors(
                period=cdk.Duration.minutes(5),
            ),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
        )

        self.api_5xx_alarm = cloudwatch.Alarm(
            self,
            "ApiGateway5xxAlarm",
            alarm_name="GovernanceApi5xxErrors",
            metric=cloudwatch.Metric(
                namespace="AWS/ApiGateway",
                metric_name="5xx",
                dimensions_map={"ApiId": self.http_api.http_api_id},
                period=cdk.Duration.minutes(5),
                statistic="Sum",
            ),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
        )

        # --- CloudTrail: Audit logging for Organizations and Control Tower API calls ---
        self.trail = cloudtrail.Trail(
            self,
            "GovernanceAuditTrail",
            trail_name="GovernanceAuditTrail",
            is_multi_region_trail=False,
            management_events=cloudtrail.ReadWriteType.ALL,
        )

        # --- Outputs ---
        cdk.CfnOutput(self, "TableName", value=self.table.table_name)
        cdk.CfnOutput(self, "FrontendBucketName", value=self.frontend_bucket.bucket_name)
        cdk.CfnOutput(self, "SnapshotBucketName", value=self.snapshot_bucket.bucket_name)
        cdk.CfnOutput(self, "UserPoolId", value=self.user_pool.user_pool_id)
        cdk.CfnOutput(self, "UserPoolClientId", value=self.user_pool_client.user_pool_client_id)
        cdk.CfnOutput(self, "DataCollectorFunctionName", value=self.data_collector_fn.function_name)
        cdk.CfnOutput(self, "GovernanceApiFunctionName", value=self.governance_api_fn.function_name)
        cdk.CfnOutput(self, "DeploymentExecutorFunctionName", value=self.deployment_executor_fn.function_name)
        cdk.CfnOutput(self, "DeploymentStateMachineArn", value=self.deployment_state_machine.state_machine_arn)
        cdk.CfnOutput(self, "HttpApiUrl", value=self.http_api.url or "")
        cdk.CfnOutput(self, "CloudFrontDomainName", value=self.distribution.distribution_domain_name)
