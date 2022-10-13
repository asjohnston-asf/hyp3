import json
import os

import boto3
import dynamo


# TODO update

LAMBDA_CLIENT = boto3.client('lambda')


def invoke_worker(worker_function_arn: str, jobs: list[dict]) -> dict:
    payload = json.dumps(
        {'jobs': dynamo.util.convert_decimals_to_numbers(jobs)}
    )
    return LAMBDA_CLIENT.invoke(
        FunctionName=worker_function_arn,
        InvocationType='Event',
        Payload=payload,
    )


# TODO add logging
def lambda_handler(event, context):
    worker_function_arn = os.environ['SUBSCRIPTION_WORKER_ARN']  # TODO add this in cf
    pending_jobs = dynamo.jobs.get_jobs_waiting_for_execution(limit=400)  # TODO increase this limit, or just remove it?
    batch_size = 500  # TODO decide on appropriate value
    for i in range(0, len(pending_jobs), batch_size):
        invoke_worker(worker_function_arn, pending_jobs[i:i+batch_size])
