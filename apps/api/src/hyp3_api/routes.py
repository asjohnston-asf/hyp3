import datetime
import json
from decimal import Decimal
from os import environ
from pathlib import Path

import yaml
from flask import abort, g, jsonify, make_response, redirect, render_template, request
from flask_cors import CORS
from openapi_core.contrib.flask.views import FlaskOpenAPIView
from openapi_core.spec.shortcuts import create_spec
from openapi_core.validation.response.datatypes import ResponseValidationResult

from hyp3_api import app, auth, handlers
from hyp3_api.openapi import get_spec_yaml

api_spec_file = Path(__file__).parent / 'api-spec' / 'openapi-spec.yml'
api_spec_dict = get_spec_yaml(api_spec_file)
api_spec = create_spec(api_spec_dict)
CORS(app, origins=r'https?://([-\w]+\.)*asf\.alaska\.edu', supports_credentials=True)

AUTHENTICATED_ROUTES = ['/jobs', '/user', '/subscriptions']


@app.before_request
def check_system_available():
    if environ['SYSTEM_AVAILABLE'] != "true":
        message = 'HyP3 is currently unavailable. Please try again later.'
        error = {
            'detail': message,
            'status': 503,
            'title': 'Service Unavailable',
            'type': 'about:blank'
        }
        return make_response(jsonify(error), 503)


@app.before_request
def authenticate_user():
    cookie = request.cookies.get('asf-urs')
    auth_info = auth.decode_token(cookie)
    if auth_info is not None:
        g.user = auth_info['sub']
    else:
        if request.path in AUTHENTICATED_ROUTES and request.method != 'OPTIONS':
            abort(handlers.problem_format(401, 'Unauthorized', 'No authorization token provided'))


@app.route('/')
def redirect_to_ui():
    return redirect('/ui/')


@app.route('/openapi.json')
def get_open_api_json():
    return jsonify(api_spec_dict)


@app.route('/openapi.yaml')
def get_open_api_yaml():
    return yaml.dump(api_spec_dict)


@app.route('/ui/')
def render_ui():
    return render_template('index.html')


@app.errorhandler(404)
def error404(e):
    return handlers.problem_format(404, 'Not Found',
                                   'The requested URL was not found on the server.'
                                   ' If you entered the URL manually please check your spelling and try again.')


class CustomEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime.datetime):
            if o.tzinfo:
                # eg: '2015-09-25T23:14:42.588601+00:00'
                return o.isoformat('T')
            else:
                # No timezone present - assume UTC.
                # eg: '2015-09-25T23:14:42.588601Z'
                return o.isoformat('T') + 'Z'

        if isinstance(o, datetime.date):
            return o.isoformat()
        if isinstance(o, Decimal):
            if o == int(o):
                return int(o)
            return float(o)
        json.JSONEncoder.default(self, o)


class NonValidator():
    def __init__(self, spec):
        pass

    def validate(self, res):
        return ResponseValidationResult()


class Jobs(FlaskOpenAPIView):
    def __init__(self, spec):
        super().__init__(spec)
        self.response_validator = NonValidator

    def post(self):
        return jsonify(handlers.post_jobs(request.get_json(), g.user))

    def get(self, job_id):
        if job_id is not None:
            return jsonify(handlers.get_job_by_id(job_id))
        parameters = request.openapi.parameters.query
        start = parameters.get('start')
        end = parameters.get('end')
        return jsonify(handlers.get_jobs(
            g.user,
            start.isoformat(timespec='seconds') if start else None,
            end.isoformat(timespec='seconds') if end else None,
            parameters.get('status_code'),
            parameters.get('name'),
            parameters.get('job_type'),
            parameters.get('start_token')
        ))


class User(FlaskOpenAPIView):
    def get(self):
        return jsonify(handlers.get_user(g.user))


class Subscriptions(FlaskOpenAPIView):
    def post(self):
        parameters = request.openapi.parameters.query
        uuid = 'f90f6f2a-d3f4-46a0-a427-3e432f548916'
        return jsonify(parameters)


app.json_encoder = CustomEncoder

jobs_view = Jobs.as_view('jobs', api_spec)
app.add_url_rule('/jobs', view_func=jobs_view, methods=['GET'], defaults={'job_id': None})
app.add_url_rule('/jobs', view_func=jobs_view, methods=['POST'])
app.add_url_rule('/jobs/<job_id>', view_func=jobs_view, methods=['GET'])

user_view = User.as_view('user', api_spec)
app.add_url_rule('/user', view_func=user_view)

subscriptions_view = Subscriptions.as_view('subscriptions', api_spec)
app.add_url_rule('/subscriptions', view_func=subscriptions_view)
