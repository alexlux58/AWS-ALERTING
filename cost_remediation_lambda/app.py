import os
import json
import logging

import boto3

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

ssm = boto3.client("ssm")

DOC_NAME = os.environ["AUTOMATION_DOC_NAME"]
ASSUME_ROLE_ARN = os.environ["AUTOMATION_ASSUME_ROLE_ARN"]


def lambda_handler(event, context):
    """
    Remediation Lambda triggered by SNS when budget threshold is exceeded.
    Starts SSM Automation to stop instances tagged AutoStop=true.
    """
    try:
        logger.info(f"Received event: {json.dumps(event)}")

        # SNS message body varies; we don't rely on exact schema.
        # Any SNS publish triggers the automation safely (tag-scoped).
        logger.info(f"Starting SSM Automation: {DOC_NAME}")

        response = ssm.start_automation_execution(
            DocumentName=DOC_NAME,
            Parameters={
                "AutomationAssumeRole": [ASSUME_ROLE_ARN],
                "TagKey": ["AutoStop"],
                "TagValue": ["true"],
            },
        )

        execution_id = response["AutomationExecutionId"]
        logger.info(f"Started automation execution: {execution_id}")

        return {
            "ok": True,
            "automation_execution_id": execution_id,
            "document_name": DOC_NAME,
        }

    except Exception as e:
        logger.error(f"Remediation Lambda failed: {e}", exc_info=True)
        raise

