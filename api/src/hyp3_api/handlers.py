from datetime import datetime, timezone
from decimal import Decimal
from os import environ
from uuid import uuid4

import requests
from boto3.dynamodb.conditions import Attr, Key
from connexion import context, problem
from connexion.apps.flask_app import FlaskJSONEncoder
from dateutil.parser import parse
from flask_cors import CORS
from hyp3_api import CMR_URL, DYNAMODB_RESOURCE, connexion_app


class DecimalEncoder(FlaskJSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            if o == int(o):
                return int(o)
            return float(o)
        return super(DecimalEncoder, self).default(o)


class QuotaError(Exception):
    pass


class CmrError(Exception):
    pass


def post_jobs(body, user):
    print(body)
    if not context['is_authorized']:
        return problem(403, 'Forbidden', f'User {user} does not have permission to submit jobs.')

    try:
        check_quota_for_user(user, len(body['jobs']))
    except QuotaError as e:
        return problem(400, 'Bad Request', str(e))

    try:
        granules = [job['job_parameters']['granule'] for job in body['jobs']]
        check_granules_exist(granules)
    except requests.HTTPError:
        pass
    except CmrError as e:
        return problem(400, 'Bad Request', str(e))

    request_time = format_time(datetime.now(timezone.utc))
    table = DYNAMODB_RESOURCE.Table(environ['TABLE_NAME'])

    for job in body['jobs']:
        job['job_id'] = str(uuid4())
        job['user_id'] = user
        job['status_code'] = 'PENDING'
        job['request_time'] = request_time
        table.put_item(Item=job)

    return body


def get_jobs(user, start=None, end=None, status_code=None):
    table = DYNAMODB_RESOURCE.Table(environ['TABLE_NAME'])

    key_expression = Key('user_id').eq(user)
    if start is not None or end is not None:
        key_expression &= get_request_time_expression(start, end)

    filter_expression = Attr('job_id').exists()
    if status_code is not None:
        filter_expression &= Attr('status_code').eq(status_code)

    response = table.query(
        IndexName='user_id',
        KeyConditionExpression=key_expression,
        FilterExpression=filter_expression,
    )

    return {'jobs': response['Items']}


def format_time(time: datetime):
    if time.tzinfo is None:
        raise ValueError(f'missing tzinfo for datetime {time}')
    utc_time = time.astimezone(timezone.utc)
    return utc_time.isoformat(timespec='seconds')


def check_quota_for_user(user, number_of_jobs):
    previous_jobs = get_job_count_for_month(user)
    quota = int(environ['MONTHLY_JOB_QUOTA_PER_USER'])
    job_count = previous_jobs + number_of_jobs
    if job_count > quota:
        raise QuotaError(f'Your monthly quota is {quota} jobs. You have {quota - previous_jobs} jobs remaining.')


def get_job_count_for_month(user):
    now = datetime.now(timezone.utc)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    response = get_jobs(user, format_time(start_of_month))
    return len(response['jobs'])


def get_request_time_expression(start, end):
    key = Key('request_time')
    formatted_start = (format_time(parse(start)) if start else None)
    formatted_end = (format_time(parse(end)) if end else None)

    if formatted_start and formatted_end:
        return key.between(formatted_start, formatted_end)
    if formatted_start:
        return key.gte(formatted_start)
    if formatted_end:
        return key.lte(formatted_end)


def check_granules_exist(granules):
    cmr_parameters = {
        'producer_granule_id': granules,
        'provider': 'ASF',
        'collection_concept_ids': {
            "C1214470488-ASF",  # SENTINEL-1A_SLC
            "C1327985661-ASF",  # SENTINEL-1B_SLC
        }
    }
    response = requests.get(CMR_URL, params=cmr_parameters)
    response.raise_for_status()
    found_granules = [entry['producer_granule_id'] for entry in response.json()['feed']['entry']]
    not_found_granules = set(granules) - set(found_granules)
    if not_found_granules:
        raise CmrError(f'Some requested scenes could not be found: {",".join(not_found_granules)}')


connexion_app.app.json_encoder = DecimalEncoder
connexion_app.add_api('openapi-spec.yml', validate_responses=True, strict_validation=True)
CORS(connexion_app.app, origins=r'https?://([-\w]+\.)*asf\.alaska\.edu', supports_credentials=True)
